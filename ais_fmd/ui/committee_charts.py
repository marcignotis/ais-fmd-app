"""
Charts specific to a VP's committee page.

Kept out of `ui/charts.py`, which the UI team owns, so the two teams can edit
without colliding. Everything here follows the same conventions: colours from
the active palette (so it works in light and dark), no data fetching, and an
`empty_figure` placeholder when there is nothing to draw.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from . import charts, theme


def _translucent(hex_color: str, alpha: float) -> str:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def pace_chart(
    spend: pd.DataFrame,
    budget: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    today: pd.Timestamp | None = None,
) -> go.Figure:
    """
    Money spent so far against the straight line a budget would follow if spent
    evenly across the term.

    The solid line is cumulative spend, stopping where the data stops. The dashed
    line runs from $0 at the start of the term to the full budget at the end, so
    "ahead of pace" is simply "above the dashed line". The dotted ceiling is the
    budget itself. A faint vertical marks today when it falls inside the term.
    """
    if budget <= 0 and (spend.empty or float(spend["spent"].max()) <= 0):
        return charts.empty_figure("No budget or spending to plot yet.")

    p = theme.active()
    last_spent = float(spend["spent"].iloc[-1]) if not spend.empty else 0.0
    over = budget > 0 and last_spent > budget
    spend_color = p.over if over else p.expense

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            name="On pace",
            x=[start, end],
            y=[0.0, float(budget)],
            mode="lines",
            line=dict(color=p.budget, width=1.6, dash="dash"),
            hovertemplate="On pace  $%{y:,.2f}<extra></extra>",
        )
    )
    if not spend.empty:
        figure.add_trace(
            go.Scatter(
                name="Spent",
                x=spend["date"],
                y=spend["spent"],
                mode="lines",
                line=dict(color=spend_color, width=2.2),
                fill="tozeroy",
                fillcolor=_translucent(spend_color, 0.12 * theme.active().fill_scale),
                hovertemplate="%{x|%b %d}  $%{y:,.2f}<extra></extra>",
            )
        )

    if budget > 0:
        figure.add_shape(
            type="line",
            xref="x", x0=start, x1=end,
            yref="y", y0=float(budget), y1=float(budget),
            line=dict(color=p.budget, width=1, dash="dot"),
        )
        figure.add_annotation(
            x=end, y=float(budget), xanchor="right", yanchor="bottom",
            text="Budget", showarrow=False,
            font=dict(color=p.ink_mute, size=10),
        )

    if today is not None and start <= today <= end:
        figure.add_shape(
            type="line",
            xref="x", x0=today, x1=today,
            yref="paper", y0=0, y1=1,
            line=dict(color=p.ink_mute, width=1, dash="dot"),
        )

    figure.update_layout(
        height=340,
        yaxis=dict(title=None, tickprefix="$", separatethousands=True, rangemode="tozero"),
        xaxis=dict(title=None, showgrid=False, range=[start, end]),
        legend=dict(orientation="h", y=1.1, x=0),
    )
    return figure


# --- My Plan ------------------------------------------------------------------


def plan_vs_actual(sheet: pd.DataFrame, *, actual: str = "Spent", actual_label: str = "Spent") -> go.Figure:
    """
    One pair of horizontal bars per category: the plan, and what has actually
    gone out (this term's spending, or for next term what the same season cost).
    Planned is the quiet grey, actual the ink; an actual bar past its plan turns
    the over colour, and each bar carries its value, so nothing rests on colour.
    """
    if sheet is None or sheet.empty or not (sheet["Planned"].sum() or sheet[actual].sum()):
        return charts.empty_figure("Nothing planned or spent yet.")
    p = theme.active()
    rows = sheet.iloc[::-1]  # biggest plan at the top
    over = rows[actual] > rows["Planned"]
    figure = go.Figure()
    figure.add_trace(go.Bar(
        name="Planned", y=rows["Category"], x=rows["Planned"], orientation="h",
        offsetgroup="planned", marker=dict(color=p.line_edge), text=[f"${v:,.0f}" for v in rows["Planned"]],
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Planned $%{x:,.2f}<extra></extra>",
    ))
    # Within budget and over budget are separate traces sharing one slot, so the
    # legend shows both meanings instead of whichever colour the first bar had.
    for name, mask, color in ((actual_label, ~over, p.ink), ("Over plan", over, p.over)):
        if not mask.any() and name == "Over plan":
            continue
        figure.add_trace(go.Bar(
            name=name, y=rows["Category"], x=rows[actual].where(mask), orientation="h",
            offsetgroup="actual", marker=dict(color=color),
            text=[f"${v:,.0f}" if m else "" for v, m in zip(rows[actual], mask)],
            textposition="outside", cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>" + actual_label + " $%{x:,.2f}<extra></extra>",
        ))
    figure.update_layout(
        barmode="group", bargap=0.35, bargroupgap=0.12,
        height=max(220, 70 * len(rows) + 60),
        margin=dict(l=8, r=48, t=8, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        xaxis=dict(tickprefix="$", separatethousands=True, showgrid=True, zeroline=False),
        yaxis=dict(title=None),
    )
    return figure


def plan_donut(slices: pd.DataFrame) -> go.Figure:
    """
    Where the plan goes: one ring slice per category, in the palette's fixed
    order, with the category and its share written on the slice and the total
    in the middle. A 2px surface gap between slices keeps neighbours apart.
    """
    if slices is None or slices.empty:
        return charts.empty_figure("Nothing planned yet.")
    p = theme.active()
    # The team palette's neutrals only, dark and light alternating so neighbours
    # stand apart. Its oranges are left out on purpose: next to this ring, orange
    # means "over plan", and a status colour is never reused for a category.
    palette = [c for c in (p.categorical or theme.CATEGORICAL) if c.upper() not in {
        p.over.upper(), p.accent.upper(), theme.ACCENT_DIM.upper(), "#F08A5D", "#FFB59A",
    }]
    palette = sorted(palette, key=lambda c: int(c.lstrip("#")[:2], 16))
    palette = [palette[i // 2] if i % 2 == 0 else palette[-(i // 2) - 1] for i in range(len(palette))]
    total = float(slices["Planned"].sum())
    figure = go.Figure(go.Pie(
        labels=slices["Category"], values=slices["Planned"], hole=0.62, sort=False,
        direction="clockwise",
        marker=dict(colors=palette[: len(slices)], line=dict(color=p.surface, width=2)),
        textinfo="label+percent", textposition="outside", automargin=True,
        hovertemplate="<b>%{label}</b><br>$%{value:,.2f} · %{percent}<extra></extra>",
    ))
    figure.update_layout(
        height=320, showlegend=False, margin=dict(l=8, r=8, t=24, b=24),
        annotations=[dict(
            text=f"${total:,.0f}<br><span style='font-size:12px'>planned</span>",
            x=0.5, y=0.5, showarrow=False, font=dict(size=20, color=p.ink),
        )],
    )
    return figure


# --- My Committee: this term against past terms ---------------------------------


def same_point_bars(frame: pd.DataFrame, typical: float | None, typical_label: str = "usual") -> go.Figure:
    """
    One horizontal bar per term: how much of that term's budget was spent by the
    same point in the term. This term is the ink bar at the top, past terms the
    quiet grey ones; each bar is labelled with its percentage, and a dashed line
    marks what is usual, so the answer reads without the legend.
    """
    if frame is None or frame.empty:
        return charts.empty_figure("Nothing to compare yet.")
    p = theme.active()
    rows = frame.iloc[::-1]  # this term at the top
    labels = [f"{term} (now)" if now else term for term, now in zip(rows["Term"], rows["Now"])]
    figure = go.Figure(go.Bar(
        y=labels, x=rows["Used"], orientation="h",
        marker=dict(color=[p.ink if now else p.line_edge for now in rows["Now"]]),
        text=[f"{value:.0f}%" for value in rows["Used"]], textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:.0f}% of its budget by this point<extra></extra>",
        showlegend=False,
    ))
    top = max(float(rows["Used"].max()), float(typical or 0), 100.0)
    if typical is not None:
        figure.add_vline(
            x=typical, line=dict(color=p.ink_soft, width=1.5, dash="dash"),
            annotation_text=f"{typical_label} {typical:.0f}%", annotation_position="top",
            annotation_font=dict(size=11, color=p.ink_soft),
        )
    figure.update_layout(
        height=max(160, 44 * len(rows) + 60), bargap=0.45,
        margin=dict(l=8, r=40, t=28, b=8),
        xaxis=dict(range=[0, top * 1.12], ticksuffix="%", showgrid=True, zeroline=False),
        yaxis=dict(title=None),
    )
    return figure
