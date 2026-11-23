"""Runnable exact-input demo: import -> saved check run -> reports and BIM exports."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

from pypdf import PdfReader

from plancheck.compliance.artifacts import CheckRunArtifact, create_run
from plancheck.compliance.registry import resolve
from plancheck.compliance.report import export_report
from plancheck.export.bcf import export_bcf
from plancheck.export.dxf import export_dxf
from plancheck.export.gltf import export_gltf
from plancheck.export.ifc import export_ifc
from plancheck.export.svg import plan_svg
from plancheck.ingest.dxf import import_dxf
from plancheck.ingest.vector_pdf import import_vector_pdf
from plancheck.model.types import ProjectContext
from plancheck.rag.client import LLMClient, LLMError, default_client
from plancheck.rag.explain import ExplanationRun, explain_run

EXPLANATIONS_FILE = "explanations.json"


def input_kind(path: Path) -> Literal["dxf", "vector_pdf", "raster"]:
    suffix = path.suffix.lower()
    if suffix == ".dxf":
        return "dxf"
    if suffix == ".pdf":
        reader = PdfReader(path)
        for page in reader.pages:
            content = page.get_contents()
            if content is not None and any(
                op in (b"m", b"l", b"re") for _, op in content.operations
            ):
                return "vector_pdf"
        return "raster"
    if suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
        return "raster"
    raise ValueError("unsupported file type; expected DXF, PDF, or a raster drawing")


def process(
    path: Path,
    output: Path,
    project: ProjectContext | None = None,
    rulesets: list[str] | None = None,
    mm_per_point: float | None = None,
    extra_coverage_notes: list[str] | None = None,
    explainer: LLMClient | None = None,
) -> Path:
    kind = input_kind(path)
    if kind == "raster":
        raise NotImplementedError(
            "raster extraction is not implemented (milestones M3-M6); no verdicts were generated"
        )
    model = (
        import_dxf(path, project)
        if kind == "dxf"
        else import_vector_pdf(path, project, mm_per_point)
    )
    artifact = create_run(
        model, resolve(rulesets or ["ada_2010"]), extra_coverage_notes=extra_coverage_notes
    )
    output.mkdir(parents=True, exist_ok=True)
    artifact.save(output / "run.json")
    if model.location_extraction is not None:
        (output / "location-evidence.json").write_text(
            model.location_extraction.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    (output / "plan.svg").write_text(plan_svg(model, artifact.report), encoding="utf-8")
    write_reports(artifact, output, explain_run(artifact, explainer) if explainer else None)
    ifc = export_ifc(model, output / "model.ifc")
    export_bcf(artifact, output / "issues.bcfzip", ifc)
    export_dxf(model, output / "model.dxf")
    export_gltf(model, output / "model.glb")
    return output


def write_reports(
    artifact: CheckRunArtifact, output: Path, explanations: ExplanationRun | None = None
) -> None:
    """Write the readable reports, and the explanations beside them when there are any."""
    if explanations is not None:
        (output / EXPLANATIONS_FILE).write_text(
            explanations.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    export_report(artifact, output / "report.html", explanations)
    export_report(artifact, output / "report.md", explanations)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--project", type=Path, help="explicit project-context JSON; absent fields stay unknown"
    )
    parser.add_argument("--ruleset", action="append", dest="rulesets")
    parser.add_argument("--scale-mm-per-point", type=float)
    parser.add_argument(
        "--explain",
        action="store_true",
        help="have a language model explain the findings; sends finding data, with no "
        "drawing text, to the service in configs/explain.yaml",
    )
    args = parser.parse_args()
    project = ProjectContext.model_validate_json(args.project.read_text()) if args.project else None
    try:
        process(
            args.input,
            args.output,
            project,
            args.rulesets,
            args.scale_mm_per_point,
            explainer=default_client() if args.explain else None,
        )
    except (ValueError, NotImplementedError, LLMError) as error:
        parser.error(str(error))
    print(f"Saved run, readable reports, IFC, BCF, DXF and GLB: {args.output}")


if __name__ == "__main__":
    main()
