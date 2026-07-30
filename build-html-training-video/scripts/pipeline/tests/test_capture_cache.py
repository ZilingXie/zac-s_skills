from training_video.capture import _slide_capture_hash
from training_video.models import ProjectConfig


def test_slide_hash_changes_only_for_modified_slide(tmp_path):
    deck = tmp_path / "deck.html"
    deck.write_text(
        """<style>.slide { color: white; }</style>
        <section class="slide" data-index="01">One</section>
        <section class="slide" data-index="02">Two</section>""",
        encoding="utf-8",
    )
    config = ProjectConfig(name="test", deck="deck.html", transcript="transcript.md")
    first_before = _slide_capture_hash(deck, 1, config)
    second_before = _slide_capture_hash(deck, 2, config)

    deck.write_text(deck.read_text(encoding="utf-8").replace(">One<", ">Changed<"), encoding="utf-8")

    assert _slide_capture_hash(deck, 1, config) != first_before
    assert _slide_capture_hash(deck, 2, config) == second_before
