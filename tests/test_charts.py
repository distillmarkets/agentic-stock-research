"""Smoke tests for distill_toolkit.charts on synthetic numbers: made-up
quantiles and paths, chosen only to exercise every chart shape."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from distill_toolkit import charts as C


def test_every_chart_shape_renders(tmp_path):
    labels = ["a", "b", "c"]
    q = pd.DataFrame({0.1: [-40, -30, -20], 0.25: [-10, -8, -5], 0.5: [0, 1, 2],
                      0.75: [10, 12, 14], 0.9: [40, 45, 50]}, index=labels)
    fig, (ax, ax2) = C.figure("Headline.", "subtitle", panels=2, widths=(3, 2))
    C.quantile_bars(ax, labels, q, label_median=True)
    C.grouped_bars(ax2, labels, {"one": [1, 2, 3], "two": [2, 3, 4]}, fmt="{:.0f}%")
    C.label(ax, "panel", "sub")
    C.finish(ax, pct=True)
    C.finish(ax2, pct=True)
    C.save(fig, tmp_path / "a.png", "synthetic source line " * 8)

    fig, (ax,) = C.figure("Headline only.")
    x = np.arange(1, 13)
    C.paths(ax, x, {"s": (x * 1.0, x - 5.0, x + 5.0), "t": (-x * 0.5, -x - 3.0, -x + 3.0)})
    C.finish(ax, pct=True)
    C.save(fig, tmp_path / "b.png")

    fig, (ax,) = C.figure("Signed bars.")
    C.bars(ax, ["x", "y", "z"], [3, -2, 0.4], signed=True, fmt="{:+.0f}")
    C.finish(ax)
    C.save(fig, tmp_path / "c.png")
    assert all((tmp_path / n).stat().st_size > 1000 for n in ("a.png", "b.png", "c.png"))


LONG_HEADLINE = (
    "A headline long enough to need three lines at single-panel width, with a $2.4bn "
    "figure in it and a $1.10 per-share number, so nothing is truncated and nothing "
    "turns into mathtext along the way."
)


def test_a_long_headline_with_dollar_signs_wraps_instead_of_truncating(tmp_path):
    fig, (ax,) = C.figure(LONG_HEADLINE, "subtitle with $300m in it")
    C.bars(ax, ["a", "b"], [1.0, 2.0])
    C.finish(ax)
    C.save(fig, tmp_path / "wrap.png", "source line naming a $300m cohort")
    assert (tmp_path / "wrap.png").stat().st_size > 1000


def test_escape_leaves_an_already_escaped_dollar_alone():
    assert C.escape("$2bn") == r"\$2bn"
    assert C.escape(r"\$2bn") == r"\$2bn"


def test_bars_puts_a_negative_label_below_the_column_and_leaves_headroom():
    fig, (ax,) = C.figure("Signed bars.")
    C.bars(ax, ["a", "b"], [4.0, -3.0], signed=True)
    negatives = [t for t in ax.texts if t.get_text() == "-3"]
    assert negatives and negatives[0].get_va() == "top"
    lo, hi = ax.get_ylim()
    assert lo < -3.0 and hi > 4.0
    plt.close(fig)


def test_grouped_bars_leaves_room_for_the_legend_above_a_negative_series():
    fig, (ax,) = C.figure("Grouped.")
    C.grouped_bars(ax, ["a", "b"], {"one": [-2.0, -4.0], "two": [-1.0, -3.0]}, fmt="{:+.0f}")
    lo, hi = ax.get_ylim()
    # A multiplicative stretch of a negative top would have pushed the axis DOWN.
    assert hi > 0 and lo < -4.0
    plt.close(fig)


def test_quantile_bars_labels_in_the_units_it_is_given(tmp_path):
    labels = ["a", "b"]
    q = pd.DataFrame({0.1: [1.0, 2.0], 0.25: [2.0, 3.0], 0.5: [3.0, 4.0],
                      0.75: [4.0, 5.0], 0.9: [5.0, 6.0]}, index=labels)
    fig, (ax,) = C.figure("Multiples, not percents.")
    C.quantile_bars(ax, labels, q, fmt="{:.1f}x", label_median=True)
    drawn = {t.get_text() for t in ax.texts}
    assert "1.0x" in drawn and "median 3.0x" in drawn
    plt.close(fig)


def test_lines_stack_grid_and_the_date_marks_render(tmp_path):
    x = np.arange(1, 13)
    fig, (ax,) = C.figure("Monotone curves need a line, not a wash.")
    C.lines(ax, x, {"low": np.linspace(0, 40, 12), "high": np.linspace(0, 41, 12)})
    C.finish(ax, pct=True)
    C.save(fig, tmp_path / "lines.png")

    dates = pd.bdate_range("2021-01-04", periods=60)
    fig, axes = C.stack("A stack on one date axis.", "sub", heights=(2, 1), size=(8, 6))
    axes[0].plot(dates, np.arange(60, dtype=float), color=C.BRAND)
    C.date_bars(axes[1], dates[::10], np.arange(6, dtype=float), width_days=5.0)
    C.date_ticks(axes[0], dates[::20], [10.0, 10.0, 10.0])
    C.date_ticks(axes[0], [], [])  # an empty event set draws nothing
    C.save(fig, tmp_path / "stack.png")

    fig, axes = C.grid("Small multiples.", None, rows=1, cols=2, size=(8, 3))
    for a in axes:
        C.bars(a, ["a", "b"], [1.0, 2.0])
    C.save(fig, tmp_path / "grid.png")
    assert all((tmp_path / n).stat().st_size > 1000 for n in ("lines.png", "stack.png", "grid.png"))


def test_an_absurdly_long_headline_still_leaves_axes_to_draw_in(tmp_path):
    fig, (ax,) = C.figure("word " * 400, "sub " * 200, size=(6.0, 3.0))
    C.bars(ax, ["a"], [1.0])
    C.save(fig, tmp_path / "long.png")
    assert (tmp_path / "long.png").stat().st_size > 1000


# ---- error bars on the bar marks ------------------------------------------
def _whisker_bounds(ax):
    """The (lo, hi) pair of every vertical rule drawn on the axes."""
    out = []
    for coll in ax.collections:
        for seg in coll.get_segments():
            out.append((round(float(seg[0][1]), 6), round(float(seg[1][1]), 6)))
    return out


def test_bars_draws_the_interval_it_is_given():
    fig, (ax,) = C.figure("Bars with intervals.")
    C.bars(ax, ["a", "b", "c"], [1.0, 2.0, -3.0],
           err=[(0.5, 1.5), (1.2, 2.8), (-4.0, -2.0)])
    assert _whisker_bounds(ax) == [(0.5, 1.5), (1.2, 2.8), (-4.0, -2.0)]


def test_bars_leaves_room_for_a_bound_beyond_the_column():
    fig, (ax,) = C.figure("Wide interval.")
    C.bars(ax, ["a"], [1.0], err=[(-9.0, 12.0)])
    lo, hi = ax.get_ylim()
    assert lo <= -9.0 and hi >= 12.0


def test_bars_without_err_is_unchanged():
    fig, (ax,) = C.figure("No intervals.")
    C.bars(ax, ["a", "b"], [1.0, 2.0])
    assert _whisker_bounds(ax) == []


def test_bars_takes_the_two_row_form_too():
    fig, (ax,) = C.figure("Two rows.")
    C.bars(ax, ["a", "b", "c"], [1.0, 2.0, 3.0],
           err=np.array([[0.5, 1.5, 2.5], [1.5, 2.5, 3.5]]))
    assert _whisker_bounds(ax) == [(0.5, 1.5), (1.5, 2.5), (2.5, 3.5)]


def test_bars_refuses_bounds_that_do_not_match_the_columns():
    fig, (ax,) = C.figure("Mismatch.")
    with pytest.raises(ValueError, match="expected"):
        C.bars(ax, ["a", "b", "c"], [1.0, 2.0, 3.0], err=[(0.5, 1.5), (1.5, 2.5)])
    with pytest.raises(ValueError, match="pairs"):
        C.bars(ax, ["a", "b"], [1.0, 2.0], err=[0.5, 1.5])


def test_grouped_bars_puts_a_whisker_on_the_series_that_has_one(tmp_path):
    fig, (ax,) = C.figure("Grouped with intervals on one series.")
    C.grouped_bars(ax, ["a", "b"], {"one": [1.0, 2.0], "two": [3.0, 4.0]},
                   err={"one": [(0.5, 1.5), (1.5, 2.5)]})
    assert _whisker_bounds(ax) == [(0.5, 1.5), (1.5, 2.5)]
    C.finish(ax)
    C.save(fig, tmp_path / "grouped.png", "synthetic source line")
    assert (tmp_path / "grouped.png").stat().st_size > 1000
