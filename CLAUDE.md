# KherveBook — notes for Claude

KherveBook is a Jupyter-inspired computational notebook built on
PyQt5 + matplotlib. One document mixes runnable Python code cells,
Markdown text cells and LaTeX equation cells — like Jupyter, but a
native desktop app in the Kherve family (KherveFitting, KherveSheet,
KhervePDF, KherveDOC, KhervePlot, KherveDraw).

## Build / run

- Python 3.12 / 3.13 with PyQt5 + matplotlib + numpy.
- Run via `python KherveBook.py` or `python -m khervebook`.
- **Full LaTeX** in latex cells needs the `tectonic` binary (PATH or
  ~/bin) + PyMuPDF; without them, documents fall back to a
  lightweight text renderer (`latextext.py`) and equations to
  matplotlib mathtext. Compile = `latexcompile.py` (background
  QThread; workers held in a module set, never parented to a cell).
- Crash log: `%TEMP%/khervebook_crash.log`.
- **Packaging** (Windows): PyInstaller **one-folder** build via
  `packaging/KherveBook.spec` → `pyinstaller packaging/KherveBook.spec
  --noconfirm`, producing `dist/KherveBook/KherveBook.exe` beside its
  runtime folder. The exe icon is `packaging/khervebook.ico`, generated
  from the in-app mark by `python packaging/make_icon.py` (re-run after
  editing `icons.py`). Then `python packaging/build_installer.py` wraps
  that folder into two `dist/` artifacts: a per-user NSIS installer
  `KherveBook-Setup-<ver>.exe` (needs `makensis`; from
  `packaging/installer.nsi`) and a copy-and-run `KherveBook-<ver>-
  portable.zip`. `dist/`, `build/` are gitignored.
- **Version string** is derived at runtime in `_version.py` from
  `git rev-list --count HEAD` and `git rev-parse --short HEAD`,
  cached with `lru_cache`. Falls back to `_FALLBACK = "0.1.0"`
  outside a git checkout. Title bar reads `KherveBook v0.1.N+sha`.
  The version bumps automatically on every commit — never edit a
  version constant by hand.

## File size policy

Every module in `khervebook/` should stay near **1500 lines**. If a
change would push a file meaningfully past that, split the new code
into a new module and import.

## Project layout

- `KherveBook.py` — entry script.
- `khervebook/` — package; `python -m khervebook` is the alternative entry.
  - `__init__.py`    — `APP_NAME`, version import.
  - `__main__.py`    — module entry point.
  - `_version.py`    — git-based version string.
  - `app.py`         — `main()`, crash log, Fusion style + theme.
  - `style.py`       — QSS theme: flat light, white cell cards, blue
                       selected-cell bar (KherveFitting-Qt family look).
  - `icons.py`       — qtawesome MDI icon wrapper (32px toolbar icons,
                       same size as KherveSheet).
  - `mainwindow.py`  — `MainWindow` shell: menus, Jupyter-style toolbar,
                       cell-type combo, .kbook I/O.
  - `celltoolbar.py` — second toolbar row that swaps with the focused
                       cell type (markdown/note/code/latex/sheet/svg/file
                       tools). The Note cell's full rich-text + pen toolbar
                       lives here (not in the cell), driving the focused
                       NoteCell's methods.
  - `explorer.py`    — dockable file tree (Ctrl+B) rooted at a chosen
                       folder; drag source for cell drops.
  - `ai_providers.py`— AI provider registry (Claude/ChatGPT/Mistral/
                       Ollama/Local) + urllib chat calls.
  - `ai_chat.py`     — AI Assistant dock (bottom-left): chat, settings,
                       fenced-block replies. The system prompt feeds the
                       model the full content of every cell (svg bodies
                       hidden); replies add new cells or replace an
                       existing one (```python cell=N) — any type except
                       svg — applied as one undoable macro.
  - `examples.py`    — Examples menu registry (name, category, builder),
                       like KherveSheet's.
  - `sheet_examples.py` — ~50 spreadsheet examples ported from
                       KherveSheet, each restyled as markdown + a live
                       sheet cell (+ a chart where numeric); Excel
                       formulas translated to Python by `_xl2py`.
                       Merged into `examples.py`'s `EXAMPLES`.
  - `importers.py`   — .ksheet (HDF5), .kdocz/.kdoc.json, .ktex,
                       .xlsx/.xlsm and image/PDF importers. Excel
                       workbooks (openpyxl) become one multi-sheet sheet
                       cell — values as-is, formulas as their cached
                       value or a Python translation. PNG/JPG and each
                       PDF page become a self-contained SVG cell (bytes
                       embedded base64), fit-to-width and travel in .kbook.
  - `ipynb.py`       — Jupyter/Colab .ipynb import & export (lossless
                       round-trip via cell metadata).
  - `notebook.py`    — `NotebookWidget`: scrollable cell column, shared
                       kernel, cell clipboard/convert, context menu,
                       JSON (de)serialisation.
  - `cells.py`       — `CellWidget` base (gutter run button) +
                       `CodeCell` (line-number gutter), `MarkdownCell`,
                       `LatexCell`; the editor has a find bar (Ctrl+F)
                       and, for prose cells, a right-click Synonyms menu;
                       code cells add a right-click Highlight Theme menu.
                       `CellWidget.focus_editor()` focuses a cell's primary
                       editor (note/file override it — their editor isn't
                       the base plain-text one).
  - `notecell.py`    — `NoteCell`: a WYSIWYG "Word"-style rich-text page
                       (a QTextEdit you format live — bold/italic/headings/
                       lists/colour/font, tools in the CellToolBar) with a
                       transparent **pen/ink overlay** for freehand
                       annotation. `source` is JSON
                       `{"kbook_note":1,"html":…,"ink":{ref_w,strokes}}` so
                       text + ink round-trip together.
  - `filepreview.py` — best-effort previews for structured attachment
                       formats shown in a File cell: `.xlsx` (openpyxl),
                       `.ksheet` (HDF5 workbook) and `.kfit` (KherveFitting
                       HDF5 + zlib-JSON). `describe()` returns
                       `{"header","parts":[{"name","text"}]}` — one part per
                       sheet / core level — so the cell offers a selector to
                       read each. The kfit core-level list comes from the
                       project JSON (authoritative; the HDF5 `core_levels`
                       group may hold only the shown one). Optional-
                       dependency-safe; returns None to fall back to the
                       "binary, kept as-is" note.
  - `filecell.py`    — `FileCell`: holds **one or more** attached files
                       (each an `_Attachment`), showing a preview per file
                       (text snippet / image thumbnail / structured-format
                       summary via `filepreview`; other binaries kept but
                       not previewed). **Hybrid**, per file — small files
                       (≤ `EMBED_LIMIT`, 256 KiB) embed base64 in the
                       `.kbook`; larger files are written to a sidecar
                       `<stem>_files/` folder beside the notebook (so the
                       per-document Git repo versions them) and only a
                       relative path is stored. Code cells reach an
                       attachment by name via the kernel helper
                       `kf("data.csv")`, returning an absolute path
                       (embedded files extracted to a temp file on demand);
                       `kf()` with no arg returns the notebook's folder.
                       `NotebookWidget.set_document_path`/`prepare_save`
                       plumb the folder in; `materialize()` externalises
                       large attachments on save.
  - `kfitcell.py`    — `KFitCell`: holds one KherveFitting `.kfit` and shows
                       it as a **Plot** (KherveFitting's own look: black
                       scatter, grey dashed background, shaded peaks,
                       blue envelope, green residuals lifted above the
                       data) or a **Data** table, switched by tabs, with a
                       drop-down over the project's sheets and an "Open in
                       KherveFitting" button (AppBridge, reload on save).
                       Storage is the File cell's hybrid (`_Attachment`):
                       embedded under 256 KiB, sidecar folder above it.
  - `kfitio.py`      — reads `.kfit` (HDF5 + zlib-JSON project, with the
                       bulky arrays as HDF5 datasets) into `KFitProject` /
                       `KFitSheet`. Every technique uses the same three
                       keys (`B.E.`, `Raw Data`, `Background`), so the
                       technique — and hence the axis labels and whether x
                       runs high→low — is read from the *sheet name*, via
                       a table ported from KherveFitting's
                       `Plot_Operations`.
  - `kfitmodels.py`  — peak lineshapes (GL/SGL, Voigt, Pseudo-Voigt, LA,
                       LA*G, LF, DS, DS*G, ExpGauss, A*GL/A*SGL, SB),
                       ported from KherveFitting's `Peak_Functions` and
                       wired the way its `update_overall_fit_and_residuals`
                       does, since a `.kfit` stores peak *parameters*, never
                       the curves. `peak_curve()` returns None for a model
                       it cannot draw (DL, TLA) so the cell says so rather
                       than showing a wrong fit.
  - `hltheme.py`     — named highlight themes for Python cells (Monokai,
                       Dracula, Solarized, …) + the QSettings-persisted
                       choice; "Auto" follows the app light/dark theme.
  - `thesaurus.py`   — synonyms via the free Datamuse API (offline-safe).
  - `sheetcell.py`   — `SheetCell`: embedded workbook (many sheets +
                       plots, one view at a time via a left drop-down);
                       `=` formulas in Python with A1 refs/ranges over
                       the kernel namespace, recomputed live as you type.
                       Right-click → Create Plot charts the selected
                       range as a persisted static plot view.
  - `svgcell.py`     — `SvgCell`: renders and draws on an SVG via
                       QSvgRenderer (KhervePaint saves .svg). Shows a canvas
                       by default (a blank one for a new/empty cell); the
                       drawing tools (select/pen/line/rect/ellipse/text,
                       colour, width, undo, grid+snap+unit, canvas W/H,
                       shape, Library, edit source, render, Open in
                       KhervePaint) live in the CellToolBar and drive
                       `set_tool`/`pick_color`/… . `open_in_paint` hands the
                       drawing to the sibling `khervepaint` app and reloads
                       on save (polls the shared file so KhervePaint edits
                       reflect back). `insert_object` drops a KhervePaint
                       library object into the drawing.
  - `paintlibrary.py`— reads the sibling KhervePaint app's reusable-object
                       library (its per-user `objects` folder) live, so
                       objects saved in KhervePaint appear in KherveBook's
                       SVG "Library" menu. No cross-project import.
  - `appbridge.py`   — `AppBridge`: opens a cell's content in a sibling
                       Kherve app (KhervePaint/KhervePY/KherveSheet/
                       KherveFitting) on a temp file and reloads the cell
                       when that app saves, by polling the file's mtime.
                       Each cell supplies a writer + a reload callback
                       (SvgCell/CodeCell/SheetCell/KFitCell `open_in_*`).
                       `script=` launches an app that has no `-m` package
                       entry (KherveFitting is one wxPython script).
  - `ksheetio.py`    — minimal read/write of KherveSheet's `.ksheet` (HDF5)
                       core grid, for the sheet-cell round-trip through
                       KherveSheet (matches its `_save_to_ksheet` schema).
  - `jscell.py`      — `JsCell`: a JavaScript/HTML cell rendered in a
                       QtWebEngine view (D3/Plotly/canvas); falls back to
                       a hint if PyQtWebEngine is absent.
  - `plotcanvas.py`  — `PlotCanvas`: a live matplotlib figure embedded as
                       a Qt canvas + the zoom/pan/save navigation toolbar,
                       used when "Interactive Plots" is on.
  - `kernel.py`      — in-process Python kernel: shared namespace
                       (np/plt/pd/scipy/dask preloaded; da/dd aliases),
                       timeout guard, stdout/stderr capture,
                       trailing-expression echo, figure/image capture
                       (PNG, or live Figures when `interactive_figures`).
                       `ks("A1")` reads a sheet grid; `ks("A1", value)`
                       writes back into the live sheet.
  - `welcome.py`     — pre-run example notebook shown on startup.
  - `undo_commands.py` — QUndoCommand classes for cell structure
                       (add/remove/move/convert); they keep the live
                       widget so an undone delete restores its output.
  - `git_backend.py` — per-notebook Git (pygit2): the .kbook's folder is
                       its own repo (fresh repos start on `dev`; a save
                       inside an existing repo commits there, never
                       nests). Auto-commit on save (`file_stem` stages
                       only that notebook's files), fast-forward-only
                       pull, and push (libgit2 SSH/HTTPS, falling back to
                       the system `git` CLI for Windows Credential
                       Manager). Also branch/history/diff/restore helpers.
                       No-ops gracefully when pygit2 is absent.
  - `remote_dialog.py` — Git → Connect to GitHub/GitLab: add/edit/remove
                       remotes in plain language.
  - `history_dialog.py` — Git → Version history: painted DAG commit
                       graph, per-commit diff, branch switch/create/delete,
                       and "restore this version".
  - `updater.py`     — self-update from GitHub Releases
                       (`gkerherve/KherveBook`, the same source the
                       khervetools.com site reads). Silent startup check
                       (3 s after launch, off the GUI thread) + Help >
                       Check for Updates; a What's New dialog renders the
                       release notes, then the NSIS installer is
                       downloaded and run with `/S` from a throwaway
                       PowerShell helper that waits for this process to
                       exit and reopens the app. Only an *installed* copy
                       self-updates (the running exe's folder must match
                       `HKCU\Software\KherveBook\InstallDir`); portable
                       and source copies get the download link instead.
                       Set `KHERVEBOOK_UPDATE_TEST_EXE` to an installed
                       KherveBook.exe to exercise the real update from a
                       source checkout.
  - `userguide.py`   — the Help > User Guide window (scrollable HTML).
- `tests/` — pytest suite (offscreen Qt; run `python -m pytest tests/`).
- `requirements.txt`, `LICENSE` (GPL-3.0).

## Document format

`.kbook` is JSON: `{"format": "kbook", "version": 6, "cells":
[{"type": "code"|"markdown"|"note"|"latex"|"sheet"|"svg"|"js"|"file"
|"kfit", "source": "...", optional "title", "collapsed", "column",
"width", "height"}]}`. A `kfit` cell's `source` is JSON
`{"kbook_kfit":1,"file":{name,size,embed|path},"sheet":…,"view":
"plot"|"data"}` — same hybrid storage as a file attachment. A `note`
cell's `source` is JSON
`{"kbook_note":1,"html":…,"ink":…}`; a `file` cell's `source` is JSON
`{"kbook_files":1,"files":[{"name","size","embed"(base64)|"path"(sidecar
rel)},…]}` (the legacy single-file `{"kbook_file":1,…}` still loads) —
large attachments live in the `<stem>_files/` folder, not the JSON. The
optional per-cell keys: `title` (heading shown at the top),
`collapsed` (minimised to its title/summary), `column` (sits beside
the previous cell in the same row), `width`/`height` (px, from the
drag-resize grips; a sheet's `height` sizes its grid). A sheet cell's `source` is itself JSON: `{"sheets":
[{"name", "rows", "cols", "data": {"A1": "raw text or =formula"}}],
"active": "<sheet name>"}` (the legacy single-grid `{"rows","cols",
"data"}` still loads). When a cell gains new persisted properties,
bump `FORMAT_VERSION` in `notebook.py` and keep `load_json` backward
compatible. Jupyter/Colab `.ipynb` import/export is in `ipynb.py`
(File menu); latex/sheet cells carry their type+source in cell
metadata for a lossless round-trip.

## UI conventions

- **Cell-based document**: vertical column of cells, Shift+Enter runs the
  current cell and advances (creating a trailing code cell if needed).
- **Gutter labels**: `In [n]:` for code (Jupyter style), `md` / `tex` for text.
- Markdown/LaTeX cells render on run; double-click the rendered view to edit.
- Kernel menu: Restart clears the shared namespace and the `In [n]` counters.
- **Window style**: Fusion as default.

## Reuse from KherveSheet

KherveSheet (`../KherveSheet/khervesheet/`) already has a richer
Python execution engine (`python_engine.py`) and LaTeX equation
rendering (`equation.py`). Port from there rather than reinventing —
but copy and adapt, never import across project boundaries.

## Roadmap

- Make cell title/column/collapse/resize undoable too (extend the stack).
- Inline `$...$` math inside Markdown cells.
- AI tool-calling (let the assistant run/edit cells directly).

Done: timeout-guarded kernel, code syntax highlighting, `.ipynb`
import/export, full LaTeX via tectonic, themes, sheet cells, undo/redo
for cell structure, xlsx/image/PDF import, User Guide, per-notebook Git
history + push/pull to GitHub (`git_backend.py` + Git menu).

## Undo / redo policy

**Every user-visible change should become undoable** as the app
matures. Cell text edits get QPlainTextEdit's local undo; cell
add/remove/move/type-change/cut/paste are on the notebook's shared
`QUndoStack` via `undo_commands.py`. `Ctrl+Z`/`Ctrl+Shift+Z` undo text
in the focused editor first, then fall back to cell structure. The
commands keep the live widget (not a serialised copy), so an undone
delete or convert brings the cell back with its output. Internal
mutators `_attach_cell`/`_detach_cell`/`_swap_cell` do the mechanics;
`add_cell` stays the non-undoable primitive for load/examples. New
undoable actions should add a command, not mutate `self.cells`
directly.

## Persistence policy

**All cell properties must round-trip through `.kbook`.** When adding
a property, update `to_dict()` in `cells.py` and `load_json` in
`notebook.py` together.

## Commit / push policy

**Every change must land as a commit on the `dev` branch and be pushed
immediately.** No batching. No exceptions. No `Co-Authored-By:` trailer.

Commit subjects under 70 chars; body explains *why*, not what.

**Commit message prefix** — every subject line must start with one of:

- `fix:` — bug fix
- `feat:` — new feature or option
- `refactor:` — code restructuring, no behavior change
- `style:` — formatting, UI tweaks
- `docs:` — documentation only
- `perf:` — performance improvement

## Licensing

GPL-3.0. New source files must carry the short GPL notice at the top.
