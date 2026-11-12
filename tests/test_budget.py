from __future__ import annotations

import json
from pathlib import Path

from plancheck.evaluation.budget import study, write_budget


def test_budget_seed_reproducibility_and_zero_noise(tmp_path: Path) -> None:
    first = study(trials=2, seed=123)
    assert first == study(trials=2, seed=123)
    assert {row["check"] for row in first["summaries"]} == {
        "opening_clear_width",
        "corridor_min_width",
        "door_maneuvering_clearance",
        "turning_space",
        "accessible_route_exists",
    }
    zero = [row for row in first["samples"] if row["sigma_mm"] == 0 and row["scale_sigma"] == 0]
    assert zero
    assert all(row["matched"] == row["trials"] for row in zero)
    # Tiny samples must not be advertised as certified 95% stability.
    assert all(row["geometry_sigma_mm"] is None for row in first["summaries"])
    write_budget(first, tmp_path)
    assert json.loads((tmp_path / "accuracy-budget.json").read_text()) == first
    assert "not established" in (tmp_path / "accuracy-budget.md").read_text()
