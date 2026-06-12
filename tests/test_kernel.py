"""Kernel tests: namespace, rich outputs, timeout, errors.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import pytest

from khervebook.kernel import Kernel


@pytest.fixture()
def kernel():
    k = Kernel()
    k.timeout = 2.0
    return k


def test_trailing_expression_echo(kernel):
    res = kernel.run("x = 2 + 2\nx")
    assert res.ok
    assert res.result_repr == "4"


def test_namespace_shared_between_runs(kernel):
    kernel.run("a = 10")
    res = kernel.run("a * 2")
    assert res.result_repr == "20"


def test_seeded_numpy(kernel):
    res = kernel.run("print(np.arange(3).sum())")
    assert res.ok
    assert res.stdout.strip() == "3"


def test_pyplot_figure_captured_once(kernel):
    res = kernel.run("plt.plot([1, 2, 3])\nplt.gcf()")
    assert res.ok
    assert len(res.figures) == 1
    assert res.result_repr == ""


def test_bare_figure_rendered(kernel):
    res = kernel.run(
        "from matplotlib.figure import Figure\n"
        "f = Figure()\nf.gca().plot([1, 2])\nf")
    assert res.ok
    assert len(res.figures) == 1
    assert res.result_repr == ""


def test_ndarray_image_rendered(kernel):
    res = kernel.run("(np.random.rand(8, 8, 3) * 255).astype('uint8')")
    assert res.ok
    assert len(res.figures) == 1


def test_timeout_aborts_infinite_loop(kernel):
    res = kernel.run("while True:\n    pass")
    assert not res.ok
    assert "TimeoutError" in res.error


def test_timeout_disabled(kernel):
    kernel.timeout = 0
    res = kernel.run("sum(range(10))")
    assert res.result_repr == "45"


def test_runtime_error_traceback(kernel):
    res = kernel.run("1/0")
    assert not res.ok
    assert "ZeroDivisionError" in res.error


def test_syntax_error(kernel):
    res = kernel.run("def broken(:")
    assert not res.ok
    assert "SyntaxError" in res.error


def test_reset_clears_namespace(kernel):
    kernel.run("a = 1")
    kernel.reset()
    res = kernel.run("a")
    assert not res.ok
    assert kernel.exec_count == 1
