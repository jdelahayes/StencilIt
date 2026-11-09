# StencilIt – notes for Claude

See README.md for what the app does and how it is organised. This file only lists the rules that
are not obvious from the code.

## Run

- Server: `.venv/Scripts/python app.py` → http://127.0.0.1:5000 (or `lancer.bat`).
- Restart the server after any Python change (`app.py`, `stencilit/*.py`); `static/` is served live.
- Layer computation is parallel; `STENCILIT_PARALLEL=thread|process|none` (`none` helps debugging).

## Translations (main pitfall)

- **UI source strings are French.** `static/index.html` (HTML text, attributes, JS strings, TIPS)
  is written in French and translated at runtime by `static/i18n.js` (exact-match `EN` dictionary
  plus regex patterns, applied by a MutationObserver). Default language is English.
- Every new or changed UI text, tooltip or server message shown in the UI **must get an entry in
  `i18n.js`**, otherwise English users see French. Elements marked `data-noi18n` are skipped.
- `I18N.start()` must stay after the code that builds the DOM (setupColumns, applyTips,
  setupAccordion) in `init`.
- Exports work the other way round: `stencilit/svg_export.py` strings are English, wrapped in
  `T()`, with French in `_FR`; the language comes from `?lang=` (contextvar `_LANG`).
- Keys of `…_infos.json` are a file format (project re-opening): never translate or rename them.
- `tools/extract_strings.py` lists French strings to check coverage.

## Silhouette Studio compatibility (Inkscape export)

Hard-won constraints, verified by the author in Silhouette Studio – do not "clean up":
- embedded images are JPEG at full resolution, with **no `clip-path`**;
- hidden layers carry both `style="display:none"` and the `display="none"` attribute;
- the occasional black/partial render image when zooming in Silhouette is a Silhouette bug;
- Silhouette skips part of the shapes of a layer made of many separate polygons: `…_silhouette.svg`
  keeps **one single compound `<path>` per layer** (openings + sheet outline + marks). Generating
  `.studio3` files directly was investigated and is not needed.

## Object selection (MobileSAM)

- `stencilit/semantic.py`: optional `onnxruntime`; models downloaded on first use into `models/`
  (git-ignored), pinned by size + SHA-256. Never commit the `.onnx` files.
- Embedding cached per session (`sess["sem"]`); a subject mask containing an object selection is
  "exact" (`subject_exact`, project key `masque_sujet_exact`): used as is, no GrabCut.

## Testing in the browser

- Never alter the author's saved state: set `NO_REMEMBER = true` in the page before changing
  settings (otherwise localStorage `stencilit.*` is overwritten), and back up / restore
  `presets_utilisateur.json` if a test saves presets or palettes.
- Use `samples/test_visage.png` (or `test_synthetique.png`). `samples/2400x0.jpg` is a personal
  photo (git-ignored): it may be used for local tests and calibration, but **must never be
  committed nor appear in screenshots, the README or any published output**.

## Conventions

- Code, comments, README and commit messages in English.
- Geometry is in mm; rasterisation at `px_per_mm`.
- Commit, tag or push only when asked. The GitHub repo (jdelahayes/StencilIt) is public.
