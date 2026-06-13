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
                       cell type (markdown/code/latex/sheet tools).
  - `explorer.py`    — dockable file tree (Ctrl+B) rooted at a chosen
                       folder; drag source for cell drops.
  - `ai_providers.py`— AI provider registry (Claude/ChatGPT/Mistral/
                       Ollama/Local) + urllib chat calls.
  - `ai_chat.py`     — AI Assistant dock (bottom-left): chat, settings,
                       fenced-block replies inserted as cells.
  - `examples.py`    — Examples menu registry (name, category, builder),
                       like KherveSheet's.
  - `importers.py`   — .ksheet (HDF5) and .kdocz/.kdoc.json importers.
  - `notebook.py`    — `NotebookWidget`: scrollable cell column, shared
                       kernel, cell clipboard/convert, context menu,
                       JSON (de)serialisation.
  - `cells.py`       — `CellWidget` base (gutter run button) +
                       `CodeCell`, `MarkdownCell`, `LatexCell`.
  - `sheetcell.py`   — `SheetCell`: embedded workbook (many sheets +
                       plots, one view at a time via a left drop-down);
                       `=` formulas in Python with A1 refs/ranges over
                       the kernel namespace, recomputed live as you type.
  - `kernel.py`      — in-process Python kernel: shared namespace
                       (np/plt/pd/scipy preloaded), timeout guard,
                       stdout/stderr capture, trailing-expression echo,
                       figure/image capture.
  - `welcome.py`     — pre-run example notebook shown on startup.
- `tests/` — pytest suite (offscreen Qt; run `python -m pytest tests/`).
- `requirements.txt`, `LICENSE` (GPL-3.0).

## Document format

`.kbook` is JSON: `{"format": "kbook", "version": 3, "cells":
[{"type": "code"|"markdown"|"latex"|"sheet", "source": "...",
optional "title", "collapsed", "column"}]}`. The optional per-cell
keys: `title` (heading shown at the top), `collapsed` (minimised to
its title/summary), `column` (sits beside the previous cell in the
same row). A sheet cell's `source` is itself JSON: `{"sheets":
[{"name", "rows", "cols", "data": {"A1": "raw text or =formula"}}],
"active": "<sheet name>"}` (the legacy single-grid `{"rows","cols",
"data"}` still loads). When a cell gains new persisted properties,
bump `FORMAT_VERSION` in `notebook.py` and keep `load_json` backward
compatible. Importing/exporting `.ipynb` is on the roadmap.

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

- Port KherveSheet's `python_engine.py` execution model (timeouts,
  richer output types).
- `.ipynb` import/export.
- Syntax highlighting in code cells; undo/redo across cell operations.
- Inline `$...$` math inside Markdown cells.
- Per-document Git history (port `git_backend.py` from KherveSheet).

## Undo / redo policy

**Every user-visible change should become undoable** as the app
matures: cell edits already get QPlainTextEdit's local undo, but cell
add/remove/move/type-change must move onto a shared QUndoStack
(mirroring KherveSheet's `undo_commands.py`).

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
