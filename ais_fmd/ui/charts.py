"""
Chart factories.

Every chart the app draws comes from here, so they cannot drift apart. The
replacements for the original charts:

  * Two donuts (income / expenses) -> sorted horizontal bars. Both were ranking
    questions, and a donut is the weakest common mark for ranking; at six to
    eight slices the labels also collided.
  * Continuous blue % ramp -> bullet chart with semantic colour. The original
    put 40% spent and 110% spent on the same scale, so the state that needs
    attention did not stand out.
  * Bare metric numbers -> KPI values with sparklines, so a figure arrives with
    its own trend rather than a single delta.
  * New: a waterfall, which is the clearest way to show where a semester's
    money actually went.

Marks are drawn as wireframe: a bright hairline edge over a low-opacity fill,
rather than a solid block of colour. On a black ground a solid fill is a hole
punched in the page, while an outline reads as something drawn on it -- and at
these saturations, six outlined bars stay distinguishable where six filled ones
merge into a single mass.
"""

from __future__ import annotations

import textwrap

import pandas as pd
import plotly.graph_objects as go

from . import theme

_HEIGHT_PER_ROW = 34
_MIN_HEIGHT = 220

# Fill opacity behind an outlined mark. High enough to read as a body, low
# enough that the edge stays the brightest part of the shape.
_FILL = 0.16
_FILL_SOFT = 0.07


def _height(rows: int, *, per_row: int = _HEIGHT_PER_ROW, base: int = 90) -> int:
    return max(_MIN_HEIGHT, base + rows * per_row)


def _translucent(hex_color: str, alpha: float) -> str:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _wire(color: str, *, fill: float = _FILL, width: float = 1.4) -> dict:
    """A wireframe mark: translucent body, bright hairline edge."""
    fill = min(fill * theme.active().fill_scale, 0.6)
    return dict(color=_translucent(color, fill), line=dict(color=color, width=width))


def _wire_many(colors: list[str], *, fill: float = _FILL, width: float = 1.4) -> dict:
    """The same, per-point, for a series whose colour varies by status."""
    fill = min(fill * theme.active().fill_scale, 0.6)
    return dict(
        color=[_translucent(c, fill) for c in colors],
        line=dict(color=colors, width=width),
    )


def _wrap(label: str, width: int = 10) -> str:
    """
    Break a long category label onto its own lines.

    FINDING (visual). The waterfall's committee names ran to twenty-plus
    characters -- "Professional Development", "Corporate Relations" -- against
    ten categories on a 480px axis. Plotly's answer is to rotate them, so the
    page ended up with a row of labels slanted at 30 degrees, colliding with
    each other and with the axis title. Wrapping at the space and keeping the
    labels horizontal fixes the cause rather than the symptom.
    """
    return "<br>".join(textwrap.wrap(str(label), width=width, break_long_words=False)) or str(label)


def empty_figure(message: str) -> go.Figure:
    """A chart-shaped placeholder, so layout does not jump when data is absent."""
    p = theme.active()
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        showarrow=False,
        font=dict(family=theme._MONO, color=p.ink_mute, size=11),
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
    )
    figure.update_layout(
        height=_MIN_HEIGHT,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return figure


def budget_bullet(df: pd.DataFrame) -> go.Figure:
    """
    Budget health as a bullet chart.

    Each committee is one row: a hollow bar for the allocation -- the envelope
    the committee is working inside -- and a solid-edged bar for actual spend,
    coloured by status. Over-budget reads instantly because it is a different
    colour and it breaks out of its envelope, not merely because it is longer.

    The separate "Allocation" tick trace the original drew is gone: the hollow
    bar already terminates exactly at the allocation, so the tick was a second
    mark saying the same thing in the same place.
    """
    if df.empty:
        return empty_figure("No budget data for this selection.")

    p = theme.active()
    data = df.sort_values("Spent", ascending=True)
    names = data["Committee_Name"].tolist()
    statuses = [p.status_colors.get(s, p.unbudgeted) for s in data["Status"]]

    figure = go.Figure()

    figure.add_trace(
        go.Bar(
            name="Allocated",
            y=names,
            x=data["Budget"],
            orientation="h",
            marker=dict(
                color="rgba(0,0,0,0)",
                line=dict(color=p.line_edge, width=1),
            ),
            width=0.66,
            hovertemplate="<b>%{y}</b><br>Allocated  $%{x:,.2f}<extra></extra>",
        )
    )

    figure.add_trace(
        go.Bar(
            name="Spent",
            y=names,
            x=data["Spent"],
            orientation="h",
            marker=_wire_many(statuses, fill=0.22, width=1.4),
            width=0.34,
            customdata=data[["% Spent", "Budget", "Status"]].values,
            hovertemplate=(
                "<b>%{y}</b><br>Spent      $%{x:,.2f}<br>"
                "Allocated  $%{customdata[1]:,.2f}<br>"
                "Used       %{customdata[0]:.1f}%<br>"
                "Status     %{customdata[2]}<extra></extra>"
            ),
        )
    )

    figure.update_layout(
        barmode="overlay",
        height=_height(len(data)),
        xaxis=dict(title=None, tickprefix="$", separatethousands=True),
        yaxis=dict(title=None, showgrid=False, ticks="", linecolor=p.line),
        legend=dict(orientation="h", y=1.04, x=0),
    )
    return figure


def ranked_bar(
    df: pd.DataFrame,
    *,
    label_column: str,
    value_column: str,
    color: str,
    title: str | None = None,
    max_rows: int = 12,
) -> go.Figure:
    """Sorted horizontal bars -- the donut replacement."""
    if df.empty:
        return empty_figure("Nothing to show for this selection.")

    p = theme.active()
    data = df.sort_values(value_column, ascending=False).head(max_rows)
    data = data.sort_values(value_column, ascending=True)
    total = float(df[value_column].sum()) or 1.0
    share = data[value_column] / total * 100

    figure = go.Figure(
        go.Bar(
            y=data[label_column],
            x=data[value_column],
            orientation="h",
            marker=_wire(color),
            text=[f"{value:,.0f}" for value in data[value_column]],
            textposition="outside",
            textfont=dict(family=theme._MONO, color=p.ink_mute, size=10),
            cliponaxis=False,
            customdata=share,
            hovertemplate="<b>%{y}</b><br>$%{x:,.2f}<br>%{customdata:.1f}% of total<extra></extra>",
        )
    )
    figure.update_layout(
        height=_height(len(data)),
        xaxis=dict(title=None, tickprefix="$", separatethousands=True),
        yaxis=dict(title=None, showgrid=False, ticks="", linecolor=p.line),
        showlegend=False,
    )
    # Only set a title when there is one -- passing None leaves an empty title
    # object that Plotly renders as the literal string "undefined".
    if title:
        figure.update_layout(title=title)
    # FINDING (visual). The outside value labels were drawn past the end of the
    # longest bar and then clipped by the plot area, so the largest figure --
    # the one most worth reading -- was the one cut in half. 1.18x was not
    # enough headroom once the labels became monospaced; 1.30 clears them, and
    # cliponaxis=False stops the axis cropping them regardless.
    figure.update_xaxes(range=[0, float(data[value_column].max()) * 1.30])
    return figure


def waterfall(
    labels: list[str],
    values: list[float],
    measures: list[str],
    *,
    title: str | None = None,
) -> go.Figure:
    """Opening -> income -> expenses -> closing, as one continuous story."""
    if not labels:
        return empty_figure("Not enough data for a waterfall.")

    p = theme.active()
    figure = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=measures,
            x=[_wrap(label) for label in labels],
            y=values,
            connector=dict(line=dict(color=p.line_lit, width=1, dash="dot")),
            increasing=dict(marker=_wire(p.income)),
            decreasing=dict(marker=_wire(p.expense)),
            totals=dict(marker=_wire(p.budget, fill=0.24)),
            hovertemplate="<b>%{x}</b><br>$%{y:,.2f}<extra></extra>",
        )
    )
    figure.update_layout(
        height=420,
        showlegend=False,
        yaxis=dict(title=None, tickprefix="$", separatethousands=True),
        # Horizontal, wrapped labels -- see _wrap. tickangle is pinned to 0 so
        # Plotly cannot decide to rotate them again once they get tight.
        xaxis=dict(title=None, tickangle=0, showgrid=False),
        margin=dict(l=8, r=8, t=34, b=48),
    )
    if title:
        figure.update_layout(title=title)
    return figure


def sparkline(values: list[float], *, color: str | None = None) -> go.Figure:
    """
    A small trend with an emphasised endpoint.

    Sized to sit under a metric, with chrome stripped -- the shape is the
    message, the axes would only add noise. The endpoint is drawn hollow so it
    reads as a plotted point rather than a dot of colour.
    """
    p = theme.active()
    color = color or p.accent
    if not values:
        return empty_figure("")

    figure = go.Figure(
        go.Scatter(
            y=values,
            mode="lines",
            line=dict(color=color, width=1.4, shape="spline", smoothing=0.4),
            fill="tozeroy",
            fillcolor=_translucent(color, 0.10),
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            y=[values[-1]],
            x=[len(values) - 1],
            mode="markers",
            marker=dict(
                color=p.void,
                size=5,
                line=dict(color=color, width=1.4),
            ),
            hoverinfo="skip",
        )
    )
    figure.update_layout(
        height=54,
        margin=dict(l=0, r=2, t=6, b=0),
        showlegend=False,
        xaxis=dict(visible=False, fixedrange=True),
        yaxis=dict(visible=False, fixedrange=True),
    )
    return figure


def trend_bars(df: pd.DataFrame) -> go.Figure:
    """Budget against actual across semesters."""
    if df.empty:
        return empty_figure("No historical data yet.")

    p = theme.active()
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            name="Allocated",
            x=df["Semester"],
            y=df["Budget"],
            marker=_wire(p.budget, fill=_FILL_SOFT),
            hovertemplate="Allocated  $%{y:,.2f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Bar(
            name="Actual",
            x=df["Semester"],
            y=df["Spent"],
            marker=_wire(p.expense),
            hovertemplate="Spent      $%{y:,.2f}<extra></extra>",
        )
    )
    figure.update_layout(
        barmode="group",
        height=380,
        yaxis=dict(title=None, tickprefix="$", separatethousands=True),
        xaxis=dict(title=None, showgrid=False),
    )
    return figure


# REMOVED: `category_treemap`. Written for "more categories than bars can
# hold", called by nothing -- `ranked_bar` is what every page uses, and with
# 16 committees it has never run out of room. Deleted rather than kept on the
# chance it is wanted, since a treemap encoding spend by area is a real design
# decision and would deserve rethinking rather than reviving.


def sponsorship_trend_bars(df: pd.DataFrame) -> go.Figure:
    """
    Sponsorship goal against amount raised, across semesters.

    Same grouped-bar shape as `trend_bars`, coloured for income rather than
    spending (green, not orange) since raised sponsorship money is income,
    not an expense. A semester with no goal set simply has no blue bar for
    that x position -- Plotly skips a NaN value rather than drawing a $0 bar,
    which is the correct reading: "no target", not "target of zero".
    """
    if df.empty:
        return empty_figure("No sponsorship history yet.")

    p = theme.active()
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            name="Goal",
            x=df["Semester"],
            y=df["Goal"],
            marker=_wire(p.budget, fill=_FILL_SOFT),
            hovertemplate="Goal      $%{y:,.2f}<extra></extra>",
        )
    )
    figure.add_trace(
        go.Bar(
            name="Raised",
            x=df["Semester"],
            y=df["Raised"],
            marker=_wire(p.income),
            hovertemplate="Raised    $%{y:,.2f}<extra></extra>",
        )
    )
    figure.update_layout(
        barmode="group",
        height=380,
        yaxis=dict(title=None, tickprefix="$", separatethousands=True),
        xaxis=dict(title=None, showgrid=False),
    )
    return figure


def confidence_histogram(confidences: list[float]) -> go.Figure:
    """How certain the categorizer was, for the review queue."""
    if not confidences:
        return empty_figure("Nothing categorized yet.")
    p = theme.active()
    figure = go.Figure(
        go.Histogram(
            x=confidences,
            nbinsx=10,
            marker=_wire(p.accent_alt),
            hovertemplate="Confidence %{x}<br>%{y} transactions<extra></extra>",
        )
    )
    figure.update_layout(
        height=220,
        xaxis=dict(title="Match confidence", range=[0, 1]),
        yaxis=dict(title="Transactions"),
        showlegend=False,
    )
    return figure
