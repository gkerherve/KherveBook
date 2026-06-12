# KherveBook

A Jupyter-inspired computational notebook as a native desktop app,
built with Python, PyQt5 and matplotlib. One document mixes:

- **Python code cells** — executed in a shared in-process kernel with
  `In [n]:` counters, stdout/stderr capture, Jupyter-style echo of the
  trailing expression, and inline matplotlib figures.
- **Markdown cells** — rendered rich text; double-click to edit.
- **LaTeX cells** — equations rendered via matplotlib mathtext.

Part of the Kherve software family (KherveFitting, KherveSheet,
KhervePDF, KherveDOC, KhervePlot).

## Run

```
pip install -r requirements.txt
python KherveBook.py
```

Shift+Enter runs the current cell and moves to the next one.
Documents are saved as `.kbook` (JSON).

## License

GPL-3.0 — see [LICENSE](LICENSE).
