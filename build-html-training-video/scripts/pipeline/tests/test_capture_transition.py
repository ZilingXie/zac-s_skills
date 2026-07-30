from PIL import Image

from training_video.capture import capture_slides
from training_video.models import ProjectConfig


def test_capture_waits_until_previous_slide_is_fully_hidden(tmp_path):
    deck = tmp_path / "deck.html"
    deck.write_text(
        """<!doctype html><html><head><style>
        html,body { margin:0; width:100%; height:100%; overflow:hidden; }
        .slide { position:absolute; inset:0; opacity:0; visibility:hidden;
                 transition:opacity 360ms ease, visibility 360ms; }
        .slide.active { opacity:1; visibility:visible; }
        #one { background:#ff0000; }
        #two { background:#0000ff; }
        h1 { color:white; margin:40px; font:700 32px sans-serif; }
        </style></head><body>
        <section id="one" class="slide active" data-index="01"><h1>One</h1></section>
        <section id="two" class="slide" data-index="02"><h1>Two</h1></section>
        <script>
        const slides = [...document.querySelectorAll('.slide')];
        function show(index) {
          slides.forEach((slide, position) => slide.classList.toggle('active', position === index));
        }
        </script></body></html>""",
        encoding="utf-8",
    )
    config = ProjectConfig(
        name="transition-test",
        deck="deck.html",
        transcript="transcript.md",
        build_dir="build",
        video={"width": 320, "height": 180, "fps": 30},
        capture={"settle_ms": 0},
    )

    outputs = capture_slides(tmp_path, config, [1, 2])

    second = Image.open(outputs[2]).convert("RGB")
    red, green, blue = second.getpixel((160, 90))
    assert blue > 250
    assert red < 5
    assert green < 5
