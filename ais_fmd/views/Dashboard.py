"""
Financial dashboard.

The original was 562 lines with every calculation inlined between layout calls.
Everything numeric now lives in `domain.budgets`, so this file is filters,
layout and chart selection.

Fixes visible here:
  F11  expenses use inverse delta colouring -- rising spend no longer reads green
  F12  % spent guards division by zero instead of producing inf
  F14  deltas are preformatted currency, not bare floats
  visual: bullet chart replaces the continuous blue ramp; sorted bars replace
          the two mismatched donuts; a waterfall shows where the money went
"""

from __future__ import annotations

import streamlit as st

from ais_fmd import auth
from ais_fmd.config.categories import BUDGETED_COMMITTEE_IDS, committee_name
from ais_fmd.data import repositories as repo
from ais_fmd.domain import budgets as budget_domain
from ais_fmd.domain.terms import (
    attach_semester,
    default_semester_index,
    ordered_semesters,
    previous_semester,
)
from ais_fmd.ui import charts, shell, theme

auth.require(auth.Role.MEMBER)

shell.environment_banner()
shell.page_header(
    "Financial Dashboard",
    "Budget against actual, spending trends, and where the money came from and went.",
)

bundle = repo.load_bundle()
semesters = ordered_semesters(bundle.terms)

if not semesters:
    shell.empty_state("No terms defined", "Add an academic term before using the dashboard.")
    st.stop()

# --- Filters -----------------------------------------------------------------

st.sidebar.header("Filters")
selected_semester = st.sidebar.selectbox(
    "Semester",
    semesters,
    index=default_semester_index(bundle.transactions, bundle.terms),
    key="dash_semester",
)

committee_options = ["All committees"] + [
    committee_name(committee_id) for committee_id in BUDGETED_COMMITTEE_IDS
]
selected_committee = st.sidebar.selectbox(
    "Committee", committee_options, key="dash_committee"
)
committee_filter = None if selected_committee == "All committees" else selected_committee

# --- Headline metrics --------------------------------------------------------

totals = budget_domain.semester_totals(bundle.transactions, bundle.terms, selected_semester)
prior = previous_semester(bundle.terms, selected_semester)
prior_totals = (
    budget_domain.semester_totals(bundle.transactions, bundle.terms, prior)
    if prior
    else {"income": 0.0, "expenses": 0.0, "net": 0.0, "count": 0}
)

# Trend series for the sparklines, so each figure carries its own context.
history = budget_domain.historical_budget_vs_actual(
    bundle.transactions, bundle.budgets, bundle.terms, committee_filter
)
trend = budget_domain.semester_totals_by_semester(
    bundle.transactions, bundle.terms, semesters
)
income_trend = [trend[semester]["income"] for semester in semesters]
expense_trend = [trend[semester]["expenses"] for semester in semesters]

shell.metric_row(
    [
        {
            "label": "Income",
            "value": totals["income"],
            "delta": totals["income"] - prior_totals["income"],
            "trend": income_trend,
            "color": theme.active().income,
        },
        {
            "label": "Expenses",
            "value": totals["expenses"],
            "delta": totals["expenses"] - prior_totals["expenses"],
            "inverse": True,  # F11
            "trend": expense_trend,
            "color": theme.active().expense,
        },
        {
            "label": "Net",
            "value": totals["net"],
            "delta": totals["net"] - prior_totals["net"],
        },
        {
            "label": "Transactions",
            "value": totals["count"],
            "delta": totals["count"] - prior_totals["count"],
            "currency": False,
        },
    ]
)

if prior:
    st.caption(f"Deltas compare against {prior}.")

st.markdown('<hr class="ais-rule" />', unsafe_allow_html=True)

# --- Budget vs actual --------------------------------------------------------

st.subheader("Budget health")

summary = budget_domain.budget_vs_actual(
    bundle.transactions, bundle.budgets, bundle.terms, selected_semester
)
if committee_filter:
    summary = summary[summary["Committee_Name"] == committee_filter]

if summary.empty:
    shell.empty_state(
        "No budget data for this selection",
        "Set committee budgets for this term on the Treasury page.",
    )
else:
    over = summary[summary["Status"] == "over"]
    approaching = summary[summary["Status"] == "approaching"]
    banner_parts = []
    if len(over):
        banner_parts.append(
            f"{shell.pill(f'{len(over)} over budget', 'over')}"
        )
    if len(approaching):
        banner_parts.append(
            f"{shell.pill(f'{len(approaching)} approaching', 'approaching')}"
        )
    if banner_parts:
        st.markdown(" &nbsp; ".join(banner_parts), unsafe_allow_html=True)

    # FINDING (visual). At [3, 2] the table got two fifths of the row and had to
    # render six columns in it, so `% Spent` and `Status` were cut off mid-cell
    # -- and `Status` is the one column that says whether a committee is in
    # trouble. Evening the split and dropping `Remaining`, which is just
    # Budget - Spent and is already the gap between the two bars in the chart
    # beside it, leaves every remaining column its full width.
    chart_column, table_column = st.columns([1, 1])
    with chart_column:
        shell.chart(charts.budget_bullet(summary), key="budget_bullet")
    with table_column:
        display = summary.copy()
        display["% Spent"] = display["% Spent"].map(
            lambda value: "—" if value is None or value != value else f"{value:.1f}%"
        )
        shell.dataframe(
            display[["Committee_Name", "Budget", "Spent", "% Spent", "Status"]].rename(
                columns={"Committee_Name": "Committee"}
            ),
            column_config={
                "Budget": st.column_config.NumberColumn(format="$%.2f"),
                "Spent": st.column_config.NumberColumn(format="$%.2f"),
                "% Spent": st.column_config.TextColumn(width="small"),
                "Status": st.column_config.TextColumn(width="small"),
            },
            height=charts._height(len(display)),
        )

st.markdown('<hr class="ais-rule" />', unsafe_allow_html=True)

# --- Where the money went ----------------------------------------------------

st.subheader("Where the money went")

scoped = attach_semester(bundle.transactions, bundle.terms)
scoped = scoped[scoped["Semester"] == selected_semester]
if committee_filter:
    target_id = next(
        (cid for cid in BUDGETED_COMMITTEE_IDS if committee_name(cid) == committee_filter),
        None,
    )
    if target_id is not None:
        scoped = scoped[scoped["budget_category"] == target_id]

# FINDING (visual). This section used to be one row: the waterfall in three
# fifths of it, and the income/expense breakdowns squeezed into the other two
# as a pair of tabs. That cost twice over. The breakdowns had about 400px to
# render category names like "Professional Development", so the labels ate most
# of the width the bars needed -- and putting them behind tabs meant only ever
# seeing one of the two, on a page whose entire subject is income against
# expenditure. They are the comparison; hiding half of it behind a click is the
# wrong default.
#
# The waterfall now takes the full width, and the two breakdowns sit side by
# side beneath it, both visible, each with roughly half the page instead of a
# fifth of it.
# FINDING (correctness). The waterfall ran Income, the top eight committees,
# then a bar labelled "Net" -- but that bar is a Plotly `total`, so it shows
# wherever the preceding steps happen to land, not the semester's actual
# net. Two things were being dropped on the way there: every committee past
# the eighth, and all unbudgeted spend, since `spending_by_committee` is
# called with `budgeted_only=True`. For Fall 2026 that put the chart's "Net"
# at -$3,301.50 against a real net of -$4,301.22 -- a $999.72 gap, shown
# directly beneath a KPI tile displaying the correct figure. Two different
# nets on one screen, and the wrong one was the one with a story attached.
#
# Everything not itemised is now carried in a single "Other" step, so the
# bars sum to the real net by construction rather than by luck.
spending = budget_domain.spending_by_committee(scoped, budgeted_only=True)
ITEMISED = 5
top = spending.head(ITEMISED)
# Whatever the itemised bars do not account for: the committees past the
# cut, plus expenses against no budget at all.
other = totals["expenses"] - float(top["Spent"].sum())

labels = ["Income"] + top["Committee_Name"].tolist()
values = [totals["income"]] + [-float(value) for value in top["Spent"]]
if round(other, 2) != 0:
    labels.append("Other")
    values.append(-other)
labels.append("Net")
values.append(0.0)
measures = ["relative"] * (len(labels) - 1) + ["total"]

shell.chart(
    charts.waterfall(labels, values, measures, title=f"{selected_semester} flow"),
    key="waterfall",
)
shell.say(
    f"Income less the {ITEMISED} largest committees; everything else — "
    f"smaller committees and unbudgeted spend — is grouped as Other.",
    caption=True,
)

expense_column, income_column = st.columns([1, 1])

with expense_column:
    st.markdown("#### Expenses by category")
    expense_split = budget_domain.categorize_flow(scoped, budget_domain.EXPENSE)
    shell.chart(
        charts.ranked_bar(
            expense_split,
            label_column="Category",
            value_column="Amount",
            color=theme.active().expense,
        ),
        key="expense_split",
    )

with income_column:
    st.markdown("#### Income by source")
    income_split = budget_domain.categorize_flow(scoped, budget_domain.INCOME)
    shell.chart(
        charts.ranked_bar(
            income_split,
            label_column="Category",
            value_column="Amount",
            color=theme.active().income,
        ),
        key="income_split",
    )

st.markdown('<hr class="ais-rule" />', unsafe_allow_html=True)

# --- Trend and burn rate -----------------------------------------------------

st.subheader("Across semesters")

trend_column, burn_column = st.columns([3, 2])

with trend_column:
    shell.chart(charts.trend_bars(history), key="trend")

with burn_column:
    st.markdown("**Projected burn**")
    burn = budget_domain.burn_rate_projection(
        bundle.transactions, bundle.budgets, bundle.terms, selected_semester
    )
    if committee_filter:
        burn = burn[burn["Committee_Name"] == committee_filter]
    at_risk = burn[burn["Note"].isin({"Projected to exhaust before term end", "Already over budget"})]
    if at_risk.empty:
        shell.empty_state("Nothing projected to overrun", "Every committee finishes within budget at the current pace.")
    else:
        # FINDING (visual). `Note` carried sentences -- "Projected to exhaust
        # before term end" -- in the narrowest column on the page, so every row
        # ended in an ellipsis. The sentence only ever takes two values, and
        # both fit in a word once the column is named for what it reports.
        compact = at_risk.copy()
        compact["Risk"] = compact["Note"].map(
            lambda note: "Over budget" if note == "Already over budget" else "Will exhaust"
        )
        shell.dataframe(
            compact[["Committee_Name", "Daily Burn", "Projected Exhaustion", "Risk"]].rename(
                columns={"Committee_Name": "Committee", "Daily Burn": "Per day"}
            ),
            column_config={
                "Per day": st.column_config.NumberColumn(format="$%.2f"),
                "Projected Exhaustion": st.column_config.DateColumn(format="MMM D, YYYY"),
                "Risk": st.column_config.TextColumn(width="small"),
            },
        )
