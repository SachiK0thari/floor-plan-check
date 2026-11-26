"""The measurement of the explanation layer (spec §11.4). No test here calls a real service."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import yaml

from plancheck.evaluation import explain_eval
from plancheck.evaluation.explain_eval import (
    check_adversarial,
    measure_once,
    render_markdown,
    summarise,
    update_labels,
)
from plancheck.evaluation.plans import review_plans
from plancheck.rag import explain

GOOD = "The check of {element} under {section} needs attention. Review the drawing and rerun it."


class Scripted:
    """Rejects the first output for failing findings, then writes a valid template."""

    service = "Fake service"
    model_id = "fake/model-1"

    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()

    def complete(self, system: str, user: str) -> str:
        with self._lock:
            self.calls += 1
        if "verdict: fail" in user and "<rejected>" not in user:
            return "The door is 32 in wide."
        return GOOD


@pytest.fixture(scope="module")
def artifacts() -> dict[str, explain_eval.CheckRunArtifact]:
    return {name: explain_eval._run(model) for name, model in review_plans().items()}


def test_adversarial_text_reaches_the_model_file_but_not_the_prompt(tmp_path: Path) -> None:
    results = check_adversarial(tmp_path)
    assert [r.name for r in results] == ["injection-instructions", "injection-numbers"]
    for result in results:
        assert result.injected_in == [
            "room labels",
            "door tags",
            "door ids",
            "dimension text",
            "site address",
        ]
        assert result.verdicts_match
        assert result.prompts_identical
        assert result.fragments_in_prompts == []
        assert result.findings_explained > 0
        assert result.clean


def test_the_injection_check_fails_when_drawing_text_is_not_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(explain, "hide_drawing_text", lambda text, model: text)
    results = check_adversarial(tmp_path)
    assert not all(r.clean for r in results)
    assert any("IGNORE" in r.fragments_in_prompts for r in results)


def test_one_run_counts_each_distinct_prompt_once(
    artifacts: dict[str, explain_eval.CheckRunArtifact],
) -> None:
    client = Scripted()
    run = measure_once(artifacts, client)
    prompts = run["prompts"]
    index = explain_eval._prompt_index(artifacts, client.model_id)
    assert len(prompts) == len(index)
    assert sum(p["findings"] for p in prompts) == sum(
        len(explain.wanted_findings(a)) for a in artifacts.values()
    )
    failing = [p for p in prompts if p["verdict"] == "fail"]
    assert failing
    assert all(
        p["rejections"]
        == [{"attempt": 1, "reason": "digit_outside_slot", "output": "The door is 32 in wide."}]
        for p in failing
    )
    assert all(p["template"] == GOOD and p["cited"] for p in prompts)
    # One call per distinct prompt, plus one retry for each rejected one.
    assert run["calls"] == client.calls == len(prompts) + len(failing)
    assert run["service_errors"] == []


def test_labels_are_kept_when_the_file_is_regenerated(
    tmp_path: Path, artifacts: dict[str, explain_eval.CheckRunArtifact]
) -> None:
    measured = {"model_id": "fake/model-1", "runs": [measure_once(artifacts, Scripted())]}
    path = tmp_path / "labels.yaml"
    first = update_labels(measured, path)
    assert path.read_text().startswith("# Citation support")
    assert [i["id"] for i in first["items"]] == list(range(1, len(first["items"]) + 1))
    item = first["items"][0]
    assert item["label"] is None
    assert item["sources"]
    assert item["text"]

    data = yaml.safe_load(path.read_text())
    data["items"][0]["label"] = "supported"
    data["items"][1]["label"] = "unsupported"
    data["items"][1]["note"] = "cites the scoping section"
    data["labelled_by"] = "author"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    again = update_labels(measured, path)
    assert again["labelled_by"] == "author"
    assert again["items"][0]["label"] == "supported"
    assert again["items"][1]["note"] == "cites the scoping section"

    # A labelled explanation the model no longer writes is kept and marked; others go.
    rerun = measure_once(artifacts, Scripted())
    rerun["prompts"][0]["template"] = "A different {element} text under {section}."
    third = update_labels({"model_id": "fake/model-1", "runs": [rerun]}, path)
    stale = [i for i in third["items"] if i.get("current") is False]
    assert [i["id"] for i in stale] == [again["items"][0]["id"]]
    assert len(third["items"]) == len(again["items"]) + 1


def test_the_report_gives_counts_rates_and_intervals(
    tmp_path: Path, artifacts: dict[str, explain_eval.CheckRunArtifact]
) -> None:
    run = measure_once(artifacts, Scripted())
    measured = {
        "created_at": "2026-11-25T00:00:00+00:00",
        "service": "Fake service",
        "model_id": "fake/model-1",
        "max_attempts": 2,
        "plans": len(artifacts),
        "findings_explained": 7,
        "runs": [run],
        "adversarial": [r.summary() for r in check_adversarial(tmp_path)],
    }
    labels = update_labels(measured, tmp_path / "labels.yaml")
    summary = summarise(measured, labels)
    rejection = summary["rejection"][0]
    failing = sum(p["verdict"] == "fail" for p in run["prompts"])
    assert rejection["first_rejected"] == failing
    assert rejection["first_rejections_by_reason"] == {"digit_outside_slot": failing}
    assert rejection["first_outputs"] == len(run["prompts"])
    low, high = rejection["wilson_95"]
    assert low < rejection["first_rejection_rate"] < high
    assert summary["citation_support"]["labelled"] == 0
    text = render_markdown(summary)
    assert "Not yet measured" in text
    assert "| injection-numbers |" in text

    labels["items"][0]["label"] = "supported"
    labelled = summarise(measured, labels)["citation_support"]
    assert labelled["supported"] == labelled["labelled"] == 1
    assert "1 of 1 labelled explanations supported" in render_markdown(summarise(measured, labels))
