# Input Contract

## HTML deck

The supported input is a static HTML bundle whose slides are already present in the DOM. Local CSS, JavaScript, images, fonts, audio, and video referenced by relative paths are copied into an isolated working project. Remote HTTP resources remain remote and must load without authentication.

The preferred structure is:

```html
<section class="slide active" data-index="01" data-title="Topic">...</section>
<section class="slide" data-index="02" data-title="Method">...</section>
<script>
  function show(index) { /* activate exactly one slide */ }
</script>
```

`init_project.py` also recognizes `.slide`, `[data-slide]`, `main > section`, and `body > section`. It creates a working HTML copy, assigns sequential `data-index` values, and installs a deterministic global `show(index)` function. It never modifies the original HTML.

The automatic adapter is not intended for React applications, authenticated pages, iframes, or pages that fetch slide content after load. Export these inputs to static HTML first.

## Narration

Use one continuous Markdown file with sequential headings:

```markdown
## Slide 1 - Topic

First sentence for the first page. Second sentence for the first page.

## Slide 2 - Method

Narration for the second page.
```

The HTML and transcript must contain the same sequential slide numbers. Blank slides and headings outside this form are rejected.

`source_text` and `caption_text` may retain identifiers, numbers, units, and parameter notation. `spoken_text` must contain English letters, spaces, and normal sentence punctuation only. Use `pronunciations.yaml` for exact replacements such as:

```yaml
mappings:
  che.video.enable_auto_fallback_sw_encoder=false: C H E dot video dot enable auto fallback S W encoder equals false
```

## Outputs

The complete build is written directly to the requested output directory:

- `video-captioned.mp4`: delivery file with burned sentence captions
- `video-clean.mp4`: optional internal version without burned captions
- `captions.srt`, `captions.vtt`, `captions.ass`
- `chapters.json` and embedded MP4 chapters
- `narration.wav` and `sentence-timings.json`
- `qa-report.json`, `qa-report.html`, and `build-manifest.json`

The pipeline produces H.264 video, AAC mono narration, 1920x1080 resolution, 30 FPS, and approximately minus sixteen LUFS by default. It does not add background music.
