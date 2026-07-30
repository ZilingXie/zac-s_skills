from training_video.transcript import parse_transcript, split_sentences


def test_sentence_split_keeps_parameter_intact():
    paragraph = "Set rtc.video.threshold first. Then validate the stream."
    assert split_sentences(paragraph) == [
        "Set rtc.video.threshold first.",
        "Then validate the stream.",
    ]


def test_sentence_split_protects_abbreviations():
    paragraph = "Use controlled variables, e.g. charging state. Then compare the result."
    assert split_sentences(paragraph) == [
        "Use controlled variables, e.g. charging state.",
        "Then compare the result.",
    ]


def test_parses_generic_multislide_transcript(tmp_path):
    transcript = tmp_path / "transcript.md"
    transcript.write_text(
        "## Slide 1 - Topic\n\nIntroduce the topic.\n\n"
        "## Slide 2 - Method\n\nExplain the method.\n",
        encoding="utf-8",
    )

    slides = parse_transcript(transcript)

    assert len(slides) == 2
    assert slides[0].number == 1
    assert slides[-1].number == 2
