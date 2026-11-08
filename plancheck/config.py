"""Loading of the YAML files in ``configs/``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent


def config_dir() -> Path:
    """Directory holding the config files. ``PLANCHECK_CONFIG_DIR`` overrides the default."""
    override = os.environ.get("PLANCHECK_CONFIG_DIR")
    return Path(override) if override else _REPO_ROOT / "configs"


def load_config(name: str) -> dict[str, Any]:
    """Load ``configs/<name>.yaml`` as a mapping."""
    path = config_dir() / f"{name}.yaml"
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data
