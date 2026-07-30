from __future__ import annotations

import contextlib
import functools
import http.server
import importlib.metadata
import json
import platform
import threading
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright

from .config import build_dir, resolve_from_project
from .utils import sha256_bytes, sha256_file, write_json


CAPTURE_PIPELINE_VERSION = "2-settled-transitions"


@contextlib.contextmanager
def static_server(directory: Path):
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            return

    handler = functools.partial(QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _slide_capture_hash(deck_path: Path, slide_number: int, config) -> str:
    soup = BeautifulSoup(deck_path.read_text(encoding="utf-8"), "html.parser")
    slide = soup.select_one(f'section.slide[data-index="{slide_number:02d}"]')
    if slide is None:
        raise ValueError(f"Slide {slide_number} is missing from {deck_path}")
    styles = "\n".join(element.get_text() for element in soup.select("style"))
    digest_parts = [
        styles,
        str(slide),
        f"{config.video.width}x{config.video.height}@{config.video.fps}",
        f"playwright={importlib.metadata.version('playwright')}",
        f"platform={platform.platform()}",
        f"capture_pipeline={CAPTURE_PIPELINE_VERSION}",
        f"capture_config={config.capture.model_dump_json()}",
    ]
    for image in slide.select("img[src]"):
        source = str(image.get("src", "")).strip()
        if source.startswith(("http://", "https://", "data:")):
            digest_parts.append(source)
            continue
        asset = (deck_path.parent / source).resolve()
        if not asset.is_file():
            raise FileNotFoundError(f"Missing slide asset: {asset}")
        digest_parts.extend([source, sha256_file(asset)])
    return sha256_bytes("\n".join(digest_parts).encode("utf-8"))


def capture_slides(project_dir: Path, config, slide_numbers: list[int]) -> dict[int, Path]:
    deck_path = resolve_from_project(project_dir, config.deck)
    output_dir = build_dir(project_dir, config) / "slides"
    output_dir.mkdir(parents=True, exist_ok=True)
    layout_path = output_dir / "layout.json"
    cache_path = output_dir / "capture-cache.json"
    layout: dict[str, object] = (
        json.loads(layout_path.read_text(encoding="utf-8")) if layout_path.is_file() else {}
    )
    cache: dict[str, object] = (
        json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
    )
    outputs: dict[int, Path] = {}

    focus_by_slide: dict[int, list[str]] = {}
    for cue in config.focus_cues:
        focus_by_slide.setdefault(cue.slide, []).append(cue.selector)

    requested_hashes = {
        slide_number: _slide_capture_hash(deck_path, slide_number, config)
        for slide_number in slide_numbers
    }
    pending = [
        slide_number
        for slide_number in slide_numbers
        if not (output_dir / f"{slide_number:02d}.png").is_file()
        or cache.get(str(slide_number)) != requested_hashes[slide_number]
        or str(slide_number) not in layout
    ]
    for slide_number in slide_numbers:
        outputs[slide_number] = output_dir / f"{slide_number:02d}.png"
    if not pending:
        return outputs

    with static_server(deck_path.parent) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        write_json(
            output_dir / "capture-metadata.json",
            {
                "browser": "chromium",
                "browser_version": browser.version,
                "playwright_version": importlib.metadata.version("playwright"),
                "viewport": {"width": config.video.width, "height": config.video.height},
                "device_scale_factor": 1,
                "platform": platform.platform(),
            },
        )
        page = browser.new_page(
            viewport={"width": config.video.width, "height": config.video.height},
            device_scale_factor=1,
        )
        page.goto(f"{base_url}/{deck_path.name}#1", wait_until="networkidle")
        if config.capture.hide_selectors:
            selectors = ",".join(config.capture.hide_selectors)
            page.add_style_tag(content=f"{selectors}{{display:none!important}}")
        page.evaluate("document.fonts.ready")
        page.wait_for_function(
            "Array.from(document.images).every(image => image.complete && image.naturalWidth > 0)"
        )
        page.evaluate("window.__TRAINING_DECK_READY__ = true")
        page.wait_for_function("window.__TRAINING_DECK_READY__ === true")

        for slide_number in pending:
            page.evaluate("number => show(number - 1)", slide_number)
            page.wait_for_function(
                """number => {
                    const target = document.querySelector(
                        `section.slide[data-index="${String(number).padStart(2, '0')}"]`
                    );
                    if (!target) return false;
                    const slides = Array.from(document.querySelectorAll('section.slide'));
                    const targetStyle = getComputedStyle(target);
                    const targetVisible = targetStyle.display !== 'none'
                        && targetStyle.visibility !== 'hidden'
                        && Number(targetStyle.opacity) >= 0.99;
                    return targetVisible && slides.every(slide => {
                        if (slide === target) return true;
                        const style = getComputedStyle(slide);
                        return style.display === 'none'
                            || style.visibility === 'hidden'
                            || Number(style.opacity) <= 0.01;
                    });
                }""",
                arg=slide_number,
            )
            page.wait_for_timeout(config.capture.settle_ms)
            output = output_dir / f"{slide_number:02d}.png"
            overflow = page.locator(
                f'section.slide[data-index="{slide_number:02d}"]'
            ).evaluate(
                "element => ({x: element.scrollWidth - element.clientWidth, y: element.scrollHeight - element.clientHeight})"
            )
            if overflow["x"] > 1 or overflow["y"] > 1:
                raise ValueError(f"Slide {slide_number} overflows its viewport: {overflow}")
            page.screenshot(path=str(output), full_page=False)
            selectors: dict[str, object] = {}
            for selector in focus_by_slide.get(slide_number, []):
                box = page.locator(
                    f'section.slide[data-index="{slide_number:02d}"] {selector}'
                ).bounding_box()
                if box is None:
                    raise ValueError(f"Missing or hidden focus selector on slide {slide_number}: {selector}")
                selectors[selector] = box
            layout[str(slide_number)] = {"selectors": selectors}
            cache[str(slide_number)] = requested_hashes[slide_number]
        browser.close()

    for slide_number in pending:
        output = outputs[slide_number]
        image = Image.open(output).convert("RGB")
        stat = ImageStat.Stat(image)
        spread = sum(stat.stddev) / len(stat.stddev)
        if spread < 4.0:
            raise ValueError(f"Captured slide {slide_number} appears blank (pixel spread {spread:.2f})")
        layout[str(slide_number)]["sha256"] = sha256_file(output)  # type: ignore[index]
        layout[str(slide_number)]["pixel_spread"] = round(spread, 3)  # type: ignore[index]
    write_json(layout_path, layout)
    write_json(cache_path, cache)
    return outputs
