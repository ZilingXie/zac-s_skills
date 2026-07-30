from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .capture import capture_slides
from .config import build_dir, load_config
from .golden import approve_goldens
from .manifest import write_build_manifest
from .media import artifact_directory, assemble_narration, render_selection
from .models import SynthesisResult
from .prepare import create_plan, load_plan, save_plan, validate_project_inputs
from .qa import verify_artifact
from .tts import synthesize_slides


def _with_slides(parser: argparse.ArgumentParser, default: str = "all") -> None:
    parser.add_argument(
        "--slides",
        default=default,
        help="Slide selection: all, 3, 3-4, or 1,3,5",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="training-video")
    parser.add_argument("--project", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--approve", action="store_true")
    _with_slides(subparsers.add_parser("capture"))
    _with_slides(subparsers.add_parser("synthesize"))
    _with_slides(subparsers.add_parser("compose"))
    build = subparsers.add_parser("build")
    _with_slides(build)
    build.add_argument("--approve-narration", action="store_true")
    sample = subparsers.add_parser("sample")
    sample.add_argument("--slide", type=int, default=3)
    approve_golden = subparsers.add_parser("approve-golden")
    _with_slides(approve_golden, default="3")
    approve_golden.add_argument("--confirm", action="store_true")
    _with_slides(subparsers.add_parser("inspect"), default="3")
    return parser


def _parse_slides(value: str, total: int) -> list[int]:
    if value.strip().lower() == "all":
        return list(range(1, total + 1))
    result: set[int] = set()
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"Invalid descending slide range: {token}")
            result.update(range(start, end + 1))
        else:
            result.add(int(token))
    slides = sorted(result)
    if not slides or slides[0] < 1 or slides[-1] > total:
        raise ValueError(f"Slide selection must be within 1-{total}: {value}")
    return slides


def _selection_dir(project_dir: Path, config, plan, slides: list[int]) -> Path:
    return artifact_directory(build_dir(project_dir, config), slides, len(plan.slides))


def _load_synthesis(project_dir: Path, config) -> SynthesisResult:
    path = build_dir(project_dir, config) / "tts-manifest.json"
    if not path.is_file():
        raise FileNotFoundError("Missing tts-manifest.json; run synthesize first")
    return SynthesisResult.model_validate_json(path.read_text(encoding="utf-8"))


def _load_current_approved_plan(project_dir: Path, config):
    plan = load_plan(project_dir, config)
    if not plan.approved:
        raise ValueError(
            "narration-plan.json is not approved; review it and run prepare --approve"
        )
    current = create_plan(project_dir, config, approved=True)
    if plan.model_dump(mode="json") != current.model_dump(mode="json"):
        raise ValueError(
            "narration-plan.json is stale relative to the transcript or pronunciation mappings; "
            "run prepare and approve it again"
        )
    return plan


def _compose(
    project_dir: Path,
    config,
    plan,
    slides: list[int],
    synthesis: SynthesisResult,
) -> dict[str, str]:
    selected_ids = {
        sentence.id
        for slide in plan.slides
        if slide.number in set(slides)
        for sentence in slide.sentences
    }
    manifest_ids = {sentence.id for sentence in synthesis.sentences}
    if not selected_ids.issubset(manifest_ids):
        missing = sorted(selected_ids - manifest_ids)
        raise ValueError(f"TTS manifest does not cover the selected slides: {missing}")

    artifact_dir = _selection_dir(project_dir, config, plan, slides)
    narration, timings = assemble_narration(
        project_dir, config, plan, slides, artifact_dir
    )
    clean, captioned = render_selection(
        project_dir, config, plan, slides, narration, timings, artifact_dir
    )
    qa_json, qa_html = verify_artifact(
        project_dir,
        config,
        plan,
        slides,
        clean,
        captioned,
        narration,
        timings,
        artifact_dir,
    )
    outputs = {
        "clean": clean,
        "captioned": captioned,
        "narration": narration,
        "captions_srt": artifact_dir / "captions.srt",
        "captions_vtt": artifact_dir / "captions.vtt",
        "captions_ass": artifact_dir / "captions.ass",
        "chapters": artifact_dir / "chapters.json",
        "scene_plan": artifact_dir / "scene-plan.json",
        "qa_json": qa_json,
        "qa_html": qa_html,
    }
    manifest = write_build_manifest(
        project_dir, config, plan, timings, synthesis, artifact_dir, outputs
    )
    if len(slides) == 1:
        prefix = f"slide-{slides[0]:02d}"
        shutil.copy2(clean, artifact_dir / f"{prefix}-clean.mp4")
        shutil.copy2(captioned, artifact_dir / f"{prefix}-captioned.mp4")
    return {
        "clean": str(clean),
        "captioned": str(captioned),
        "qa_json": str(qa_json),
        "qa_html": str(qa_html),
        "manifest": str(manifest),
    }


def main() -> int:
    args = _parser().parse_args()
    project_dir = args.project.resolve()
    try:
        config = load_config(project_dir)
        if args.command == "validate":
            print(json.dumps(validate_project_inputs(project_dir, config), indent=2))
            return 0
        if args.command == "prepare":
            plan = create_plan(project_dir, config, approved=args.approve)
            print(save_plan(project_dir, config, plan))
            return 0

        fresh_plan = create_plan(project_dir, config, approved=False)
        if args.command == "sample":
            plan = fresh_plan.model_copy(update={"approved": True})
            save_plan(project_dir, config, plan)
            slides = _parse_slides(str(args.slide), len(plan.slides))
        elif args.command in {"synthesize", "compose"}:
            plan = _load_current_approved_plan(project_dir, config)
            slides = _parse_slides(args.slides, len(plan.slides))
        elif args.command == "build":
            if args.approve_narration:
                plan = fresh_plan.model_copy(update={"approved": True})
                save_plan(project_dir, config, plan)
            else:
                plan = _load_current_approved_plan(project_dir, config)
            slides = _parse_slides(args.slides, len(plan.slides))
        else:
            plan = fresh_plan
            slides = _parse_slides(args.slides, len(plan.slides))

        if args.command == "capture":
            outputs = capture_slides(project_dir, config, slides)
            print(json.dumps({str(key): str(value) for key, value in outputs.items()}, indent=2))
        elif args.command == "approve-golden":
            screenshots = capture_slides(project_dir, config, slides)
            print(
                approve_goldens(
                    project_dir,
                    config,
                    slides,
                    screenshots,
                    confirmed=args.confirm,
                )
            )
        elif args.command == "synthesize":
            result = synthesize_slides(project_dir, config, plan, slides)
            print(result.model_dump_json(indent=2))
        elif args.command in {"sample", "build"}:
            validate_project_inputs(project_dir, config)
            capture_slides(project_dir, config, slides)
            synthesis = synthesize_slides(project_dir, config, plan, slides)
            print(json.dumps(_compose(project_dir, config, plan, slides, synthesis), indent=2))
        elif args.command == "compose":
            print(
                json.dumps(
                    _compose(project_dir, config, plan, slides, _load_synthesis(project_dir, config)),
                    indent=2,
                )
            )
        elif args.command == "inspect":
            artifact_dir = _selection_dir(project_dir, config, plan, slides)
            report = artifact_dir / "qa-report.json"
            if not report.is_file():
                raise FileNotFoundError(f"No build report found: {report}")
            print(report.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
