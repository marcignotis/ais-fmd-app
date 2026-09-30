"""
Module M11 -- committee officer portal.

A scoped view for a committee chair: their budget, their spend, their remaining,
and a way to raise a reimbursement — without seeing or being able to change
anything belonging to another committee.

This is the page that depends on FINDING F2 being fixed. Under the original
shared-password model there was no way to give a chair sight of their own budget
without handing them the keys to everything.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ais_fmd import auth
from ais_fmd.config import vp_committees
from ais_fmd.config.categories import BUDGETED_COMMITTEE_IDS, committee_name
from ais_fmd.data import repositories as repo
from ais_fmd.domain import budgets as budget_domain
from ais_fmd.domain import reimbursements as reimb
from ais_fmd.domain import vp_metrics
from ais_fmd.domain.money import format_currency
from ais_fmd.domain.terms import attach_semester, default_semester_index, ordered_semesters
from ais_fmd.ui import charts, shell, theme

identity = auth.require(auth.Role.OFFICER)

shell.environment_banner()
shell.page_header(
    "My Committee",
    "Your budget, your spending, and your outstanding reimbursements.",
)

bundle = repo.load_bundle()
semesters = ordered_semesters(bundle.terms)

if not semesters:
    shell.empty_state("No terms defined")
    st.stop()

# --- Which committee ---------------------------------------------------------
#
# In production the committee comes from the signed-in profile. A treasurer or
# admin can look at any committee; an officer sees only their own.

can_choose = identity.can(auth.Role.TREASURER)

# An officer whose profile has no committee sees nothing rather than a picker:
# a picker would let them open any committee, which is the one thing this page
# exists to prevent.
if not can_choose and identity.committee_id is None:
    shell.empty_state(
        "No committee assigned to your account",
        " Ask the treasurer to add your email under Officer Access.",
    )
    st.stop()

controls = st.columns([2, 2])
with controls[0]:
    if can_choose:
        committee_names = [committee_name(cid) for cid in BUDGETED_COMMITTEE_IDS]
        default_index = (
            committee_names.index(committee_name(identity.committee_id))
            if identity.committee_id in BUDGETED_COMMITTEE_IDS
            else 0
        )
        picked_name = st.selectbox("Committee", committee_names, index=default_index)
        committee_id = next(
            cid for cid in BUDGETED_COMMITTEE_IDS if committee_name(cid) == picked_name
        )
    else:
        committee_id = identity.committee_id
        st.markdown(f"**Committee**  \n{vp_committees.title_for(committee_id)}")

# A committee can own several budget lines (Membership owns Membership and
# Passport). Everything below is about all of them together; an unmapped
# committee is just its own single line, exactly as before.
line_ids = vp_committees.budget_ids_for(committee_id)
line_names = [committee_name(cid) for cid in line_ids]
chosen_name = vp_committees.title_for(committee_id)

with controls[1]:
    semester = st.selectbox(
        "Semester",
        semesters,
        index=default_semester_index(bundle.transactions, bundle.terms),
        key="officer_semester",
    )

if not can_choose:
    st.caption(
        "You are seeing only your own committee. Treasurers can view any committee."
    )

# --- Position ----------------------------------------------------------------

summary = budget_domain.budget_vs_actual(
    bundle.transactions, bundle.budgets, bundle.terms, semester
)
lines = summary[summary["Committee_Name"].isin(line_names)]

if lines.empty:
    shell.empty_state(
        f"No budget or spending recorded for {chosen_name} in {semester}",
        "Ask the treasurer to set an allocation for this term.",
    )
    st.stop()

position = vp_metrics.rollup(summary, line_names)
percent = position["percent"]
status = vp_metrics.status_for(percent, position["spent"])

metrics = st.columns(4)
metrics[0].metric("Budget", format_currency(position["budget"]))
metrics[1].metric("Spent", format_currency(position["spent"]))
metrics[2].metric("Remaining", format_currency(position["remaining"]))
metrics[3].metric("Used", "—" if percent is None else f"{percent:.0f}%")

status_style = {"over": "over", "approaching": "approaching", "on track": "on track"}
st.markdown(
    shell.pill(status, status_style.get(status, "muted")),
    unsafe_allow_html=True,
)
if percent is not None:
    st.progress(min(percent / 100, 1.0))

# Pace: money used against the share of the term that has passed. Spending 60%
# of a budget means something different in week 3 than in week 12.
elapsed = vp_metrics.term_elapsed_percent(bundle.terms, semester)
if elapsed is not None and percent is not None:
    pace = f"{percent:.0f}% of the budget is spent and {elapsed:.0f}% of {semester} has passed."
    projected = vp_metrics.projected_spend(position["spent"], elapsed)
    if projected is not None:
        gap = position["budget"] - projected
        pace += (
            f" At this pace the term ends with {format_currency(projected)} spent, "
            + (
                f"{format_currency(gap)} under budget."
                if gap >= 0
                else f"{format_currency(-gap)} over budget."
            )
        )
    shell.say(pace, caption=True)

if status == "over":
    shell.notify(
        "warning",
        f"{chosen_name} is over its allocation by "
        f"{format_currency(abs(position['remaining']))}. Speak to the treasurer "
        f"before committing anything further.",
    )

if len(line_names) > 1:
    st.markdown("#### By budget line")
    by_line = lines.rename(columns={"Committee_Name": "Budget line"})
    by_line["% Spent"] = by_line["% Spent"].map(
        lambda value: "—" if value is None or value != value else f"{value:.1f}%"
    )
    shell.dataframe(
        by_line[["Budget line", "Budget", "Spent", "Remaining", "% Spent", "Status"]],
        column_config={
            "Budget": st.column_config.NumberColumn(format="$%.2f"),
            "Spent": st.column_config.NumberColumn(format="$%.2f"),
            "Remaining": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

# --- Spending ----------------------------------------------------------------

st.markdown('<hr class="ais-rule" />', unsafe_allow_html=True)
st.markdown("#### Your spending this term")

scoped = attach_semester(bundle.transactions, bundle.terms)
scoped = scoped[(scoped["Semester"] == semester) & scoped["budget_category"].isin(line_ids)]

if scoped.empty:
    shell.empty_state("Nothing recorded against this committee yet")
else:
    table_column, chart_column = st.columns([3, 2])
    with table_column:
        display = scoped.sort_values("transaction_date", ascending=False)
        table = pd.DataFrame(
            {
                "Date": pd.to_datetime(display["transaction_date"]).dt.date,
                "Amount": display["amount"],
                "Purpose": display["purpose"].fillna("—"),
                "Details": display["details"].astype(str).str.slice(0, 70),
            }
        )
        if len(line_ids) > 1:
            table.insert(1, "Line", display["budget_category"].map(committee_name))
        shell.dataframe(
            table,
            column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")},
            height=360,
        )
    with chart_column:
        by_purpose = budget_domain.categorize_flow(scoped, budget_domain.EXPENSE)
        shell.chart(
            charts.ranked_bar(
                by_purpose,
                label_column="Category",
                value_column="Amount",
                color=theme.active().expense,
            ),
            key="officer_purposes",
        )

# --- Reimbursements ----------------------------------------------------------
#
# Reimbursements are cut from the MVP: the page is unloaded from app.py's
# navigation and the tables live in the deferred migration 002. This section
# used to call `repo.load_reimbursements()` unconditionally, which against a
# database with only migration 001 applied queries a relation that does not
# exist -- taking down the whole page rather than hiding one section of it.
#
# Asking the backend whether it can answer, rather than assuming it can, keeps
# the section working in the sandbox (where the tables do exist) and silent in
# production until 002 runs. Turning the feature back on needs no change here.

st.markdown('<hr class="ais-rule" />', unsafe_allow_html=True)

try:
    requests = repo.load_reimbursements()
    reimbursements_available = True
except Exception:  # noqa: BLE001 - a missing table is a deployment state, not an error
    requests = pd.DataFrame()
    reimbursements_available = False

if not reimbursements_available:
    st.caption(
        "Reimbursement tracking is not enabled on this deployment yet. Your "
        "budget and spending above are unaffected."
    )
    st.stop()

st.markdown("#### Reimbursements for this committee")

if requests.empty:
    shell.empty_state(
        "No requests raised",
        "Submit one from the Reimbursements page — it will be pre-assigned to this committee.",
    )
else:
    mine = requests[requests["committee_id"].isin(line_ids)]
    if mine.empty:
        shell.empty_state("No requests for this committee yet")
    else:
        outstanding = mine[mine["status"].isin([reimb.PENDING, reimb.APPROVED])]
        if not outstanding.empty:
            shell.say(
                f"{len(outstanding)} outstanding, totalling "
                f"{format_currency(outstanding['amount'].sum())} — this is committed "
                f"but not yet reflected in the spend figure above.",
                caption=True,
            )
        shell.dataframe(
            reimb.display_frame(mine),
            column_config={
                "Amount": st.column_config.NumberColumn(format="$%.2f"),
                "Submitted": st.column_config.DatetimeColumn(format="MMM D, YYYY"),
            },
        )
