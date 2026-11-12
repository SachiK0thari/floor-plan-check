"""Generate and exercise the three synthetic review plans through both exact input paths."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from plancheck.compliance.artifacts import CheckRunArtifact
from plancheck.evaluation.plans import review_plans
from plancheck.evaluation.validate import signatures
from plancheck.export.dxf import export_dxf
from plancheck.ingest.vector_pdf import export_vector_pdf
from plancheck.pipeline import process


def generate_demo(output: Path) -> None:
    expected = yaml.safe_load(Path("eval/compliance/expected.yaml").read_text())
    output.mkdir(parents=True, exist_ok=True)
    for name, model in review_plans().items():
        folder = output / name
        folder.mkdir(exist_ok=True)
        (folder / "project.json").write_text(model.project.model_dump_json(indent=2))
        dxf = export_dxf(model, folder / "source.dxf")
        pdf = export_vector_pdf(model, folder / "source.pdf")
        for kind, path in (("dxf", dxf), ("pdf", pdf)):
            result = process(path, folder / kind, model.project)
            artifact = CheckRunArtifact.load(result / "run.json")
            if signatures(artifact.report) != expected["plans"][name]:
                raise ValueError(f"{name}/{kind} does not match expected verdicts")
    (output / "README.txt").write_text(
        "Synthetic analytic demo. All exact-path signatures matched.\n"
        "Author hand-checks, independent CAD plots, "
        "and real local-code verification remain pending.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("out/demo"))
    args = parser.parse_args()
    generate_demo(args.output)
    print(f"DXF and tagged vector-PDF demo results: {args.output}")


if __name__ == "__main__":
    main()
