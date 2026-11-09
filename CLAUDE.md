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
- the occasional black/partial render image when zooming in Silhouette is a Silhouette bug.

## Testing in the browser

- Never alter the author's saved state: set `NO_REMEMBER = true` in the page before changing
  settings (otherwise localStorage `stencilit.*` is overwritten), and back up / restore
  `presets_utilisateur.json` if a test saves presets or palettes.
- Use `samples/test_visage.png` (or `test_synthetique.png`). **Never use `samples/2400x0.jpg`**:
  personal photo, git-ignored, must not appear in screenshots, commits or the README.

## Conventions

- Code, comments, README and commit messages in English.
- Geometry is in mm; rasterisation at `px_per_mm`.
- Commit, tag or push only when asked. The GitHub repo (jdelahayes/StencilIt) is public.
