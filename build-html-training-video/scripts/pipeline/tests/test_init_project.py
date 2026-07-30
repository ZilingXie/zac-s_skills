from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup


SCRIPT = Path(__file__).parents[2] / "init_project.py"


def test_init_project_adapts_copy_and_preserves_original(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    html = source / "deck.html"
    original = """<!doctype html><html><body><main>
    <div class="slide"><h1>One</h1><img src="assets/evidence.png"></div>
    <div class="slide"><h1>Two</h1></div>
    </main></body></html>"""
    html.write_text(original, encoding="utf-8")
    asset = source / "assets" / "evidence.png"
    asset.parent.mkdir()
    asset.write_bytes(b"fake-image")
    transcript = source / "transcript.md"
    transcript.write_text(
        "## Slide 1 - One\n\nFirst sentence.\n\n## Slide 2 - Two\n\nSecond sentence.\n",
        encoding="utf-8",
    )
    project = tmp_path / "project"
    output = tmp_path / "output"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--html", str(html),
            "--transcript", str(transcript),
            "--project-dir", str(project),
            "--output-dir", str(output),
            "--name", "example-training",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert html.read_text(encoding="utf-8") == original
    normalized = BeautifulSoup((project / "source" / "deck.html").read_text(), "html.parser")
    slides = normalized.select("section.slide[data-index]")
    assert [slide["data-index"] for slide in slides] == ["01", "02"]
    assert [slide["data-title"] for slide in slides] == ["One", "Two"]
    assert any("window.show" in (script.string or "") for script in normalized.select("script"))
    assert (project / "source" / "assets" / "evidence.png").is_file()
    assert str(output) in (project / "video.yaml").read_text(encoding="utf-8")


def test_init_project_rejects_mismatched_slide_count_without_partial_directory(tmp_path):
    html = tmp_path / "deck.html"
    html.write_text('<section class="slide">Only one</section>', encoding="utf-8")
    transcript = tmp_path / "transcript.md"
    transcript.write_text(
        "## Slide 1 - One\n\nFirst.\n\n## Slide 2 - Two\n\nSecond.\n",
        encoding="utf-8",
    )
    project = tmp_path / "project"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--html", str(html),
            "--transcript", str(transcript),
            "--project-dir", str(project),
            "--output-dir", str(tmp_path / "output"),
            "--name", "example-training",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "slide count mismatch" in result.stderr
    assert not project.exists()


def test_init_project_rejects_missing_local_resource_without_partial_directory(tmp_path):
    html = tmp_path / "deck.html"
    html.write_text(
        '<section class="slide"><img src="missing.png"></section>',
        encoding="utf-8",
    )
    transcript = tmp_path / "transcript.md"
    transcript.write_text("## Slide 1 - One\n\nFirst.\n", encoding="utf-8")
    project = tmp_path / "project"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--html", str(html),
            "--transcript", str(transcript),
            "--project-dir", str(project),
            "--output-dir", str(tmp_path / "output"),
            "--name", "example-training",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Missing local HTML resource" in result.stderr
    assert not project.exists()
