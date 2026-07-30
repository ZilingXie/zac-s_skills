---
name: build-html-training-video
description: Use when converting a static HTML slide deck and per-slide narration into a Microsoft Speech narrated MP4 with sentence-level burned captions on Apple Silicon macOS, including technical-term pronunciation normalization, chapter metadata, media QA, and resumable caching.
---

# Build HTML Training Video

Turn an HTML presentation and per-slide Markdown narration into a captioned MP4. Use the bundled pipeline instead of writing one-off TTS or FFmpeg commands.

## Workflow

1. Read [`references/input-contract.md`](references/input-contract.md).
2. Verify that the source is a static deck whose slides already exist in the DOM. Do not modify the user's originals.
3. Copy `.env.example` to `.env` in this skill folder and have the user provide `AZURE_SPEECH_KEY`. Never print or commit the key.
4. Run `scripts/setup.sh` once on the Apple Silicon Mac.
5. Create a working project:

```bash
scripts/init_project.py \
  --html /absolute/path/deck.html \
  --transcript /absolute/path/transcript.md \
  --project-dir /absolute/path/video-project \
  --output-dir /absolute/path/video-output \
  --name training-name
```

6. Prepare the narration without calling TTS:

```bash
scripts/training-video --project /absolute/path/video-project prepare
```

7. Review `narration-plan.json` under the configured output directory. Ensure every `spoken_text` value contains English words and normal sentence punctuation only. Add exact source-to-spoken mappings to `pronunciations.yaml` for dotted parameters, identifiers, units, or product-specific pronunciation, then rerun `prepare` until validation passes. Keep the original notation in captions.
8. Build only after the narration plan is reviewed:

```bash
scripts/training-video --project /absolute/path/video-project build \
  --slides all \
  --approve-narration
```

9. Read `qa-report.json` and inspect at least one frame from every chapter. Do not deliver a failed build, a blank frame, residual slide transition, clipped evidence, or overlapping captions.
10. Deliver `video-captioned.mp4`. Mention `captions.srt`, `captions.vtt`, and `qa-report.html` as supporting artifacts. Treat `video-clean.mp4` as optional internal output.

## Safety

- Use Microsoft Speech only. The default is `japanwest` with `en-US-AndrewMultilingualNeural`; change region, voice, or rate only in the working project's `video.yaml`.
- Keep `.env`, generated WAV files, caches, and MP4 files out of Git.
- Never place the key in YAML, command arguments, logs, manifests, or final responses.
- Stop before TTS if the HTML, transcript, assets, slide count, selectors, or spoken-text validation fails.
- Do not claim support for React applications, authenticated pages, or decks that load slides from runtime APIs. Export those to a static HTML deck first.

