"""The materials-characterisation technique example sets (EDX, EELS, TGA,
BET, SIMS, NMR, and the expanded XRD) register with the expected counts.

Execution of every example (loads + runs all code cells without error) is
covered by tests/test_notebook.py::test_examples_run_clean.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import pytest

#: minimum number of examples expected per technique category.
EXPECTED = {"XRD": 12, "EDX": 5, "EELS": 5, "TGA": 5,
            "BET": 5, "SIMS": 4, "NMR": 5}


@pytest.mark.parametrize("category,count", list(EXPECTED.items()))
def test_technique_category_present(category, count):
    from khervebook.examples import EXAMPLES
    names = [n for n, c, _b in EXAMPLES if c == category]
    assert len(names) >= count, f"{category}: {len(names)} < {count}"
    assert len(names) == len(set(names)), f"{category} has duplicate names"


def test_spectroscopy_category_renamed_to_arpes():
    from khervebook.examples import EXAMPLES
    cats = {c for _n, c, _b in EXAMPLES}
    assert "Spectroscopy" not in cats     # renamed
    assert "ARPES" in cats


def test_no_xps_quantification_example():
    from khervebook.examples import EXAMPLES
    names = [n for n, _c, _b in EXAMPLES]
    assert "XPS Quantification (XPS)" not in names


def test_all_example_names_unique():
    from khervebook.examples import EXAMPLES
    names = [n for n, _c, _b in EXAMPLES]
    assert len(names) == len(set(names))
