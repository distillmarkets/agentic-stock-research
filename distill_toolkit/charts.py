"""House charts for the toolkit's studies.

A small set of chart shapes the studies keep needing, styled once, on
matplotlib so they render in a notebook, a script, or CI with no extra
dependency. Every chart is a static image of aggregates: no per-firm record
ever leaves your machine through one of these.

The look follows the Distill Markets design language: warm-neutral surface,
one accent, hairline grid, marks that stay thin, text in ink tokens rather
than series colours. Series colours were validated for colour-vision
separation; up and down are reserved for sign and never used for identity.

Usage::

    from distill_toolkit import charts as C
    fig, (ax, ax2) = C.figure("Headline in one sentence.", "what, when, from where", widths=(3, 2))
    C.quantile_bars(ax, labels, q)          # q: DataFrame with columns .1 .25 .5 .75 .9
    C.bars(ax2, labels, values, fmt="{:.0f}%")
    C.finish(ax, "%"); C.finish(ax2, "%")
    C.save(fig, "out.png", source_text="Distill panel 2026-09-03; Stooq bundle Aug 2026")

Three figure geometries: ``figure`` for a row of panels, ``stack`` for panels
sharing one date axis, ``grid`` for small multiples. Marks: ``bars``,
``grouped_bars``, ``quantile_bars``, ``paths`` and ``lines`` sit on category or
horizon positions; ``date_bars`` and ``date_ticks`` sit on real dates.
"""

from __future__ import annotations

import logging
import textwrap
from collections.abc import Iterable, Mapping, Sequence

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import dates as mdates
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter

# ---- tokens ---------------------------------------------------------------
SURFACE = "#fcfeff"
INK = "#171b22"
INK2 = "#5c646f"
MUTED = "#81878f"
GRID = "#e4e8ed"
BASELINE = "#c9ced6"

BRAND = "#2971c6"
BRAND_LIGHT = "#90baf1"
BRAND_WASH = "#e0ecfc"
AMBER = "#b47819"
TEAL = "#008fa8"
SERIES = (BRAND, AMBER, TEAL)  # fixed order, never cycled past three

UP = "#009962"
DOWN = "#c5372f"

SANS = ["Geist", "Inter", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]
MONO = ["Geist Mono", "SF Mono", "Menlo", "DejaVu Sans Mono"]


def theme() -> None:
    """Apply the house style to matplotlib. Idempotent; called by ``figure``."""
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": SANS,
        "font.size": 9.5,
        "figure.facecolor": SURFACE,
        "figure.dpi": 110,
        "savefig.dpi": 170,
        "savefig.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": BASELINE,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "grid.linestyle": "-",
        "axes.axisbelow": True,
        "axes.titlelocation": "left",
        "axes.labelcolor": INK2,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK2,
        "ytick.labelcolor": INK2,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "text.color": INK,
        "lines.linewidth": 2,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
    })


def escape(text: str) -> str:
    """Escape ``$`` so matplotlib renders it as a dollar sign, not as mathtext.

    A pair of dollar signs anywhere in a string switches matplotlib into
    mathtext, which swallows the text between them and sometimes raises. Every
    string this module draws goes through here.
    """
    return text.replace("\\$", "$").replace("$", r"\$")


def _wrap(text: str, fig, fontsize: float) -> tuple[str, int]:
    """Wrap to the figure width at the given point size. Returns ``(text, n_lines)``.

    Sentences are the house headline style, and a sentence is longer than one
    line at any figure width worth using, so the block wraps and the layout
    below it moves down. Truncation is never the answer: the clipped half of a
    headline is the half that states the finding.
    """
    chars = max(20, int(fig.get_figwidth() * 0.97 * 72 / (fontsize * 0.53)))
    lines = textwrap.wrap(text, chars) or [""]
    return escape("\n".join(lines)), len(lines)


def _headline(fig, headline: str, subtitle: str | None, bottom: float,
              left: float = 0.07, right: float = 0.985, hspace: float | None = None) -> float:
    """Draw the headline block and leave the axes the space below it.

    Measured in inches from the top, so the same block sits correctly on a wide
    single row and on a tall stack. Returns the ``top`` fraction it left free.
    """
    h = fig.get_figheight()
    head, n_head = _wrap(headline, fig, 13.5)
    fig.text(0.012, 1 - 0.115 / h, head, ha="left", va="top", fontsize=13.5,
             fontweight="semibold", color=INK, linespacing=1.25)
    used = 0.115 + 0.235 * n_head
    if subtitle:
        sub, n_sub = _wrap(subtitle, fig, 9.5)
        fig.text(0.012, 1 - (used + 0.03) / h, sub, ha="left", va="top",
                 fontsize=9.5, color=INK2, linespacing=1.3)
        used += 0.03 + 0.17 * n_sub
    # A headline long enough to eat the whole figure still has to leave axes to
    # draw in; matplotlib raises rather than clipping if it does not.
    top = max(1 - (used + 0.55) / h, bottom + 0.08)
    adjust = {"top": top, "bottom": bottom, "left": left, "right": right}
    if hspace is not None:
        adjust["hspace"] = hspace
    fig.subplots_adjust(**adjust)
    return top


def figure(headline: str, subtitle: str | None = None, panels: int = 1,
           widths: Sequence[float] | None = None, size: tuple[float, float] | None = None):
    """A figure with a left-aligned headline and muted subtitle above ``panels`` axes.

    The headline block wraps to the figure width and the axes start below
    whatever it takes. Returns ``(fig, axes)`` where ``axes`` is always a list.
    """
    theme()
    size = size or (5.6 * panels if panels > 1 else 8.0, 4.6)
    gs = {"wspace": 0.3}
    if widths:
        gs["width_ratios"] = list(widths)
    fig, axes = plt.subplots(1, panels, figsize=size, gridspec_kw=gs)
    axes = list(np.atleast_1d(axes))
    _headline(fig, headline, subtitle, bottom=0.17)
    return fig, axes


def stack(headline: str, subtitle: str | None, heights: Sequence[float],
          size: tuple[float, float] = (9.5, 11.0)):
    """A vertical stack of panels on one shared x axis, under one headline block.

    For a set of series that share a date range and nothing else: a price, a
    revenue history, a share count, filing marks. ``heights`` are relative panel
    heights. Returns ``(fig, axes)`` with the axes top to bottom.
    """
    theme()
    fig, axes = plt.subplots(len(heights), 1, figsize=size, sharex=True,
                             gridspec_kw={"height_ratios": list(heights)})
    axes = list(np.atleast_1d(axes))
    _headline(fig, headline, subtitle, bottom=1.15 / size[1], left=0.095, right=0.975, hspace=0.60)
    for ax in axes:
        ax.grid(axis="y")
        ax.tick_params(length=0)
    return fig, axes


def grid(headline: str, subtitle: str | None, rows: int, cols: int,
         size: tuple[float, float] = (12.5, 9.0)):
    """Small multiples under one shared headline block. Returns ``(fig, flat_axes)``.

    One question asked of many cohorts at once, where the comparison between
    panels is the point and each panel's own chrome should stay quiet.
    """
    theme()
    fig, axes = plt.subplots(rows, cols, figsize=size)
    axes = list(np.atleast_1d(axes).ravel())
    _headline(fig, headline, subtitle, bottom=1.05 / size[1], left=0.075, right=0.985, hspace=0.62)
    fig.subplots_adjust(wspace=0.30)
    return fig, axes


def label(ax, title: str, sub: str | None = None) -> None:
    """Panel title in ink and an optional muted line under it."""
    ax.set_title(escape(title), fontsize=10.5, fontweight="semibold", color=INK,
                 pad=24 if sub else 10)
    if sub:
        ax.text(0, 1.03, escape(sub), transform=ax.transAxes, fontsize=8.5, color=MUTED,
                va="bottom")


def finish(ax, ylabel: str | None = None, pct: bool = False, zero_line: bool = True) -> None:
    """Recessive chrome: hairline grid, baseline only, optional zero rule, formatted ticks."""
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color=INK2)
    if pct:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    else:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}" if abs(v) >= 10 or v == 0 else f"{v:g}"))
    lo, hi = ax.get_ylim()
    if zero_line and lo < 0 < hi:
        ax.axhline(0, color=BASELINE, lw=0.9, zorder=1)
    ax.tick_params(length=0)


def source(fig, text: str) -> None:
    """Footer naming the data and its vintage, wrapped to the figure width."""
    width_chars = int(fig.get_figwidth() * 15)
    fig.text(0.012, 0.012, escape("\n".join(textwrap.wrap(text, width_chars))), ha="left",
             va="bottom", fontsize=8, color=MUTED, linespacing=1.4)


def save(fig, path, source_text: str | None = None) -> None:
    if source_text:
        source(fig, source_text + " General information, not financial product advice.")
    fig.savefig(path)
    plt.close(fig)


# ---- marks ----------------------------------------------------------------
def _rounded_bar(ax, x, height, width, color, radius=0.035):
    """A bar with a rounded data-end and a square baseline end."""
    if height == 0:
        return
    y0, h = (0, height) if height > 0 else (height, -height)
    r = min(radius, width / 2)
    patch = FancyBboxPatch((x - width / 2, y0), width, h,
                           boxstyle=f"round,pad=0,rounding_size={r}", mutation_aspect=1,
                           facecolor=color, edgecolor="none", zorder=2)
    ax.add_patch(patch)
    # square off the baseline end by covering the rounding on that side
    cover_h = min(h, r * 3)
    ax.add_patch(matplotlib.patches.Rectangle(
        (x - width / 2, 0 if height > 0 else -cover_h), width, cover_h,
        facecolor=color, edgecolor="none", zorder=2))


def _colors_for(series, colors) -> list[str]:
    """One colour per series, refusing to silently drop the ones past the palette.

    The house palette is three, because three is what stays separable under
    colour-vision simulation. A fourth series is a decision about the chart, not
    something to discover from a line that never appeared.
    """
    out = list(colors or SERIES[: len(series)])
    if len(out) < len(series):
        raise ValueError(
            f"{len(series)} series but {len(out)} colours: the house palette holds "
            f"{len(SERIES)}. Split the panel, or pass colors= explicitly."
        )
    return out


def _value_labels(ax, xs, values, fmt: str, fontsize: float = 8.5, color: str = INK2) -> None:
    """Value on the cap of each column, and under it when the column points down.

    A label pinned above the cap of a negative column sits inside the plot area
    on top of the bar it belongs to, where it reads as the neighbour's.
    """
    for x, v in zip(xs, np.asarray(values, dtype=float)):
        if np.isnan(v):
            continue
        ax.annotate(escape(fmt.format(v)), (x, v), ha="center",
                    va="bottom" if v >= 0 else "top",
                    xytext=(0, 3 if v >= 0 else -3), textcoords="offset points",
                    fontsize=fontsize, color=color)


def _headroom(ax, values, top: float = 0.12, bottom: float = 0.12) -> None:
    """Widen the y limits so labels, and a legend, have somewhere to sit.

    Scaled by the span of the data rather than multiplied into the current
    limit: a multiplicative stretch does nothing when the top of the axis is
    near zero and inverts when it is negative, which is how a legend ends up
    over the tallest column.
    """
    values = np.asarray(list(values), dtype=float)
    if not values.size or np.isnan(values).all():
        return
    span = float(np.nanmax(np.abs(values))) or 1.0
    lo, hi = ax.get_ylim()
    new_lo = min(lo, float(np.nanmin(values)) - span * bottom) if np.nanmin(values) < 0 else lo
    ax.set_ylim(new_lo, max(hi, float(np.nanmax(values)) + span * top))


def _bounds(err, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Normalise an ``err`` argument to ``(lows, highs)`` in the values' own units.

    Accepts ``[(lo, hi), ...]``, one pair per column, which is the shape an
    interval comes back from ``cluster_bootstrap`` and its relatives in. A
    ``(2, n)`` array of lows and highs is taken too, unless ``n`` is 2 and the
    input is square, where the pair form wins because that is the documented
    one. Absolute bounds, never deltas: an asymmetric percentile interval has no
    single half-width, and subtracting the point estimate to get one is how a
    bootstrap interval gets drawn as a standard error.
    """
    e = np.asarray(err, dtype=float)
    if e.ndim != 2:
        raise ValueError("err must be a sequence of (lo, hi) pairs or a (2, n) array")
    if e.shape == (n, 2):
        return e[:, 0], e[:, 1]
    if e.shape == (2, n):
        return e[0], e[1]
    raise ValueError(f"err has shape {e.shape}; expected ({n}, 2) pairs or (2, {n})")


def _err_marks(ax, xs, err, n: int, color: str = INK2) -> np.ndarray:
    """Draw the interval whiskers and return every bound, for the headroom."""
    lo, hi = _bounds(err, n)
    ax.vlines(xs, lo, hi, color=color, lw=1.4, zorder=5)
    return np.concatenate([lo, hi])


def bars(ax, labels: Sequence[str], values: Iterable[float], color: str | Sequence[str] = BRAND,
         fmt: str = "{:.0f}", width: float = 0.52, label_values: bool = True,
         signed: bool = False, err=None) -> None:
    """Thin columns with the value on the cap. ``signed=True`` colours by sign (up/down).

    ``err`` draws an interval whisker on each column, as ``[(lo, hi), ...]`` in
    the values' own units. A cohort statistic without its interval invites the
    reader to rank bins that a firm-clustered bootstrap cannot separate, and
    three studies drew these by hand with ``ax.vlines`` before it lived here.
    The whiskers are in the ink tone, not the series colour: they are chrome on
    the mark, not a second series.
    """
    values = np.asarray(list(values), dtype=float)
    xs = np.arange(len(labels))
    colors = [UP if v >= 0 else DOWN for v in values] if signed else (
        [color] * len(values) if isinstance(color, str) else list(color))
    ax.bar(xs, values, width=width, color=colors, edgecolor="none", zorder=2)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_xlim(-0.6, len(labels) - 0.4)
    extent = values
    if err is not None:
        extent = np.concatenate([values, _err_marks(ax, xs, err, len(values))])
    if label_values:
        _value_labels(ax, xs, values, fmt, fontsize=8.5)
        _headroom(ax, extent, top=0.12, bottom=0.12)
    elif err is not None:
        _headroom(ax, extent, top=0.08, bottom=0.08)


def grouped_bars(ax, labels: Sequence[str], series: Mapping[str, Iterable[float]],
                 colors: Sequence[str] | None = None, fmt: str = "{:.0f}",
                 label_values: bool = True, legend_loc: str = "upper right",
                 err: Mapping[str, object] | None = None) -> None:
    """Grouped columns with a surface gap between neighbours and a legend.

    The y limits leave room above the tallest column for the legend and below
    the lowest for a negative column's label, so neither has to be repaired by
    the caller.

    ``err`` maps a series name to its ``[(lo, hi), ...]`` bounds and may cover
    only some of the series; the whiskers sit on each series' own column
    positions and are counted in the headroom, so a legend never lands on one.
    """
    names = list(series)
    colors = _colors_for(names, colors)
    n = len(names)
    xs = np.arange(len(labels))
    group_w = 0.62
    w = group_w / n
    every = []
    for i, (name, vals) in enumerate(series.items()):
        vals = np.asarray(list(vals), dtype=float)
        every.append(vals)
        pos = xs - group_w / 2 + w * (i + 0.5)
        ax.bar(pos, vals, width=w * 0.9, color=colors[i], edgecolor="none", zorder=2, label=name)
        if err is not None and name in err:
            every.append(_err_marks(ax, pos, err[name], len(vals)))
        if label_values:
            _value_labels(ax, pos, vals, fmt, fontsize=8)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    # The legend sits inside the axes, so it needs its own headroom on top of
    # whatever the value labels took.
    _headroom(ax, np.concatenate(every) if every else [], top=0.30, bottom=0.14)
    ax.legend(loc=legend_loc)


def quantile_bars(ax, labels: Sequence[str], q, color: str = BRAND, fmt: str = "{:.0f}%",
                  tail_labels: bool = True, label_median: bool = False) -> None:
    """Distribution as a range mark: 10th-90th line, 25th-75th bar, median dot.

    ``q`` is a DataFrame indexed like ``labels`` with columns 0.1, 0.25, 0.5,
    0.75, 0.9. ``fmt`` formats both the tail and the median label, so a panel of
    dollars, multiples or scores reads in its own units rather than in percent.
    """
    xs = np.arange(len(labels))
    ax.vlines(xs, q[0.1], q[0.9], color=BRAND_LIGHT if color == BRAND else color, lw=2, alpha=0.9 if color == BRAND else 0.45, zorder=2)
    ax.vlines(xs, q[0.25], q[0.75], color=color, lw=9, zorder=3)
    ax.scatter(xs, q[0.5], s=42, color=SURFACE, edgecolor=INK, linewidth=1.2, zorder=4)
    if tail_labels:
        for x, v in zip(xs, q[0.1]):
            ax.annotate(escape(fmt.format(v)), (x, v), ha="center", va="top", xytext=(0, -5),
                        textcoords="offset points", fontsize=8.5, color=INK2)
    if label_median:
        for x, v in zip(xs, q[0.5]):
            ax.annotate(escape("median " + fmt.format(v)), (x, v), ha="left", va="center",
                        xytext=(9, 0), textcoords="offset points", fontsize=8.5, color=INK2)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_xlim(-0.6, len(labels) - 0.4)
    lo, hi = float(q[0.1].min()), float(q[0.9].max())
    ax.set_ylim(lo - (hi - lo) * 0.14, hi + (hi - lo) * 0.06)


def paths(ax, x: Sequence[float], series: Mapping[str, tuple], colors: Sequence[str] | None = None,
          band_alpha: float = 0.10, end_labels: bool = True, fmt: str = "{:+.0f}%") -> None:
    """Median paths with an interquartile wash and a ringed end marker.

    ``series`` maps a name to ``(median, lower, upper)`` arrays over ``x``.
    ``fmt`` formats the end label, as it does in ``lines``, so a panel of
    points, dollars or multiples does not read as a signed percentage.
    """
    colors = _colors_for(series, colors)
    x = np.asarray(x)
    for (name, (med, lo, hi)), c in zip(series.items(), colors):
        med, lo, hi = (np.asarray(a, dtype=float) for a in (med, lo, hi))
        ax.fill_between(x, lo, hi, color=c, alpha=band_alpha, linewidth=0, zorder=1)
        ax.plot(x, med, color=c, lw=2, label=name, zorder=3)
        ax.scatter([x[-1]], [med[-1]], s=52, color=c, edgecolor=SURFACE, linewidth=2, zorder=4)
        if end_labels:
            end = 0.0 if abs(med[-1]) < 0.5 else med[-1]
            ax.annotate(escape(fmt.format(end)), (x[-1], end), xytext=(8, 0),
                        textcoords="offset points", va="center", fontsize=9, color=INK2)
    ax.set_xlim(x[0] - 0.5, x[-1] + (x[-1] - x[0]) * 0.12)
    ax.legend(loc="lower left")


def lines(ax, x: Sequence[float], series: Mapping[str, Iterable[float]],
          colors: Sequence[str] | None = None, end_labels: bool = True,
          fmt: str = "{:.0f}%", legend_loc: str = "lower left") -> None:
    """Plain or monotone lines with a ringed end marker and, optionally, end labels.

    ``paths`` draws a median with an interquartile wash, which is the wrong mark
    for a curve that is not a distribution: a survival curve, a cumulative
    incidence, a share over time. Here each series is one array over ``x``.

    End labels are pushed apart until neighbouring series are readable, using
    the y limits at call time, so set them first if the defaults are not wanted.
    """
    colors = _colors_for(series, colors)
    x = np.asarray(x, dtype=float)
    ys = []
    for (name, y), c in zip(series.items(), colors):
        y = np.asarray(list(y), dtype=float)
        ys.append(y)
        ax.plot(x, y, color=c, lw=2, label=name, zorder=3)
        ax.scatter([x[-1]], [y[-1]], s=44, color=c, edgecolor=SURFACE, linewidth=2, zorder=4)
    ax.set_xlim(x[0] - (x[-1] - x[0]) * 0.02, x[-1] + (x[-1] - x[0]) * 0.17)
    if end_labels:
        lo, hi = ax.get_ylim()
        gap = (hi - lo) * 0.045
        placed: list[float] = []
        for val, c in sorted(((float(y[-1]), c) for y, c in zip(ys, colors)), key=lambda t: t[0]):
            pos = val if not placed else max(val, placed[-1] + gap)
            placed.append(pos)
            ax.annotate(escape(fmt.format(val)), (x[-1], pos), xytext=(8, 0),
                        textcoords="offset points", va="center", fontsize=8.5, color=c)
    ax.legend(loc=legend_loc)


# ---- marks on a date axis -------------------------------------------------
def date_bars(ax, dates, values: Iterable[float], width_days: float = 250.0,
              color: str = AMBER, alpha: float = 1.0) -> None:
    """Columns at real dates, so they can share an axis with a daily series.

    ``bars`` places its columns at ``arange(len(labels))``, which cannot line up
    with a price series drawn on a date axis. ``width_days`` is the column width
    in days, not a fraction of a category slot.
    """
    xs = mdates.date2num([np.datetime64(d, "D").astype("datetime64[s]").item() for d in dates])
    ax.bar(xs, list(values), width=width_days, color=color, edgecolor="none",
           zorder=2, alpha=alpha, align="center")


def date_ticks(ax, dates, heights: Iterable[float], color: str = INK2, base: float = 0.0,
               lw: float = 1.4, alpha: float = 0.9) -> None:
    """Event marks on a date axis: a thin rule from ``base`` to ``base + height``.

    For dated events against a series drawn underneath: a filing, a revision, an
    insider transaction. Nothing is drawn for an empty set of dates.
    """
    dates = list(dates)
    if not len(dates):
        return
    xs = mdates.date2num([np.datetime64(d, "D").astype("datetime64[s]").item() for d in dates])
    ax.vlines(xs, base, base + np.asarray(list(heights), dtype=float),
              color=color, lw=lw, alpha=alpha, zorder=3)
