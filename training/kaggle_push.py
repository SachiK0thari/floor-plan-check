"""Upload a training module to Kaggle as a script and start it.

Usage::

    python -m training.kaggle_push prep --owner <kaggle-user>
    python -m training.kaggle_push train --owner <kaggle-user>

Each job is one module from this folder plus a short driver that supplies the Kaggle paths.
The module file is uploaded unchanged apart from its final ``__main__`` block, which is
replaced by the driver. Requires the ``kaggle`` command-line tool and an API token
(``~/.kaggle/access_token``). Kernels are created private.

Follow a run with ``kaggle kernels status <owner>/<slug>`` and fetch its files with
``kaggle kernels output <owner>/<slug> -p <dir>``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAIN_GUARD = 'if __name__ == "__main__":\n    sys.exit(main())\n'

PREP_DRIVER = """if __name__ == "__main__":
    import shutil
    import tarfile

    _out = Path("/kaggle/temp/cubicasa_masks")
    _code = main(["--data", "/kaggle/input", "--out", str(_out)])
    _work = Path("/kaggle/working")
    for _name in ("index.jsonl", "vocab.json", "errors.jsonl"):
        shutil.copy(_out / _name, _work / _name)
    # One archive, not ~15,000 files: notebook output is unreliable past 500 files.
    with tarfile.open(_work / "cubicasa_masks.tar", "w") as _tar:
        _tar.add(_out, arcname="cubicasa_masks")
    print("archive bytes:", (_work / "cubicasa_masks.tar").stat().st_size)
    sys.exit(_code)
"""

TRAIN_DRIVER = """if __name__ == "__main__":
    sys.exit(main(["--kaggle"]))
"""


@dataclass(frozen=True)
class Job:
    slug: str
    module: str
    driver: str
    datasets: list[str] = field(default_factory=list)
    kernels: list[str] = field(default_factory=list)  # slugs under the same owner
    gpu: bool = False
    internet: bool = False


JOBS = {
    "prep": Job(
        slug="plancheck-cubicasa-prep",
        module="cubicasa_prep.py",
        driver=PREP_DRIVER,
        datasets=["qmarva/cubicasa5k"],
    ),
    "train": Job(
        slug="plancheck-seg-train",
        module="train_seg.py",
        driver=TRAIN_DRIVER,
        kernels=["plancheck-cubicasa-prep"],
        gpu=True,
        internet=True,  # ImageNet encoder weights come from download.pytorch.org
    ),
}


def build(job: Job, owner: str, folder: Path) -> Path:
    """Write the script and kernel-metadata.json for ``job`` into ``folder``."""
    source = (HERE / job.module).read_text(encoding="utf-8")
    if source.count(MAIN_GUARD) != 1 or not source.endswith(MAIN_GUARD):
        raise ValueError(f"{job.module} must end with the standard __main__ block")
    code = source[: -len(MAIN_GUARD)] + job.driver
    (folder / job.module).write_text(code, encoding="utf-8")
    metadata = {
        "id": f"{owner}/{job.slug}",
        "title": job.slug,
        "code_file": job.module,
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": job.gpu,
        "enable_tpu": False,
        "enable_internet": job.internet,
        "dataset_sources": job.datasets,
        "kernel_sources": [f"{owner}/{k}" for k in job.kernels],
        "competition_sources": [],
        "model_sources": [],
    }
    path = folder / "kernel-metadata.json"
    path.write_text(json.dumps(metadata, indent=2))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Push a training job to Kaggle.")
    parser.add_argument("job", choices=sorted(JOBS))
    parser.add_argument("--owner", default=os.environ.get("KAGGLE_USERNAME"))
    parser.add_argument("--dry-run", action="store_true", help="write the folder, do not push")
    args = parser.parse_args(argv)
    if not args.owner:
        parser.error("--owner or KAGGLE_USERNAME is required")
    job = JOBS[args.job]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        build(job, args.owner, folder)
        if args.dry_run:
            print((folder / "kernel-metadata.json").read_text())
            return 0
        command = ["kaggle", "kernels", "push", "-p", str(folder)]
        if job.gpu:
            command += ["--accelerator", "NvidiaTeslaT4"]
        return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
