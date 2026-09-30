"""
The numbers on a VP's committee page.

A VP's committee can own several budget lines (Membership owns Membership and
Passport), so the page adds them together and shows how far through the term
they are. Everything here takes plain DataFrames and numbers and returns plain
values -- no Streamlit import, so it can be tested without a browser.
"""

from __future__ import annotations

import pandas as pd

from . import budgets as budget_domain
from .money import safe_percent
from .terms import date_range_for_semester

# Below this share of the term, spending so far says little about the end of the
# term (one early purchase would be multiplied fifty-fold), so no projection is
# offered rather than a misleading one.
MIN_ELAPSED_FOR_PROJECTION = 10.0


def rollup(summary: pd.DataFrame, names: list[str]) -> dict:
    """
    Add together the budget lines called `names` from a `budget_vs_actual` frame.

    `percent` is None when the combined budget is zero (nothing to divide by),
    the same convention `safe_percent` uses everywhere else.
    """
    rows = summary[summary["Committee_Name"].isin(names)]
    budget = float(rows["Budget"].sum())
    spent = float(rows["Spent"].sum())
    return {
        "budget": budget,
        "spent": spent,
        "remaining": budget - spent,
        "percent": safe_percent(spent, budget),
    }


def status_for(percent: float | None, spent: float) -> str:
    """
    on track / approaching / over, for a combined figure.

    The thresholds deliberately match `budgets._status_for_row`, which colours
    the org-wide dashboard, so one committee never reads "on track" on one page
    and "approaching" on another. A test compares the two across a range.
    """
    if percent is None or pd.isna(percent):
        return "unbudgeted" if spent > 0 else "no budget"
    if percent > 100:
        return "over"
    if percent >= 85:
        return "approaching"
    return "on track"


def term_elapsed_percent(
    df_terms: pd.DataFrame, semester: str, *, as_of: pd.Timestamp | None = None
) -> float | None:
    """How far through the term `as_of` (default: today) is, 0-100. None if unknown."""
    window = date_range_for_semester(df_terms, semester)
    if window is None:
        return None
    start, end = window
    total_days = (end - start).days
    if total_days <= 0:
        return None
    now = as_of if as_of is not None else pd.Timestamp.today().normalize()
    elapsed_days = min(max((now - start).days, 0), total_days)
    return elapsed_days / total_days * 100


def projected_spend(spent: float, elapsed_percent: float | None) -> float | None:
    """
    Where spending lands at the end of the term if the pace so far continues.

    A straight line: spent so far divided by the share of the term used. None
    when it is too early in the term to say (see MIN_ELAPSED_FOR_PROJECTION).
    """
    if elapsed_percent is None or elapsed_percent < MIN_ELAPSED_FOR_PROJECTION:
        return None
    return spent / (elapsed_percent / 100)


def historical(
    df_transactions: pd.DataFrame,
    df_budgets: pd.DataFrame,
    df_terms: pd.DataFrame,
    names: list[str],
) -> pd.DataFrame:
    """
    Budget and spend per semester for several budget lines added together.

    `historical_budget_vs_actual` takes one line at a time; a committee that owns
    two lines needs them summed per semester. Columns match that function's, so
    the same chart draws it.
    """
    columns = ["Semester", "Budget", "Spent", "% Spent"]
    frames = [
        budget_domain.historical_budget_vs_actual(df_transactions, df_budgets, df_terms, name)
        for name in names
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=columns)

    out = (
        pd.concat(frames)
        .groupby("Semester", sort=False, as_index=False)[["Budget", "Spent"]]
        .sum()
    )
    out["% Spent"] = [
        safe_percent(spent, budget) for spent, budget in zip(out["Spent"], out["Budget"])
    ]
    return out[columns]


def budget_flow(
    expense_split: pd.DataFrame, budget: float, *, itemised: int = 5
) -> tuple[list[str], list[float], list[str]]:
    """
    Steps for a waterfall that runs Budget -> biggest spending -> what Remains.

    `expense_split` is `budgets.categorize_flow`'s Category/Amount frame, largest
    first. Everything past the `itemised` biggest purposes is carried in one
    "Other" step, so the steps always add up to the real remaining balance rather
    than to whatever the itemised bars happen to reach -- the same fix the
    org-wide waterfall needed. The last step is a Plotly "total", drawn wherever
    the bars before it land.
    """
    top = expense_split.head(itemised)
    other = float(expense_split["Amount"].sum()) - float(top["Amount"].sum())

    labels = ["Budget"] + top["Category"].tolist()
    values = [float(budget)] + [-float(amount) for amount in top["Amount"]]
    if round(other, 2) != 0:
        labels.append("Other")
        values.append(-other)
    labels.append("Remaining")
    values.append(0.0)

    measures = ["relative"] * (len(labels) - 1) + ["total"]
    return labels, values, measures
