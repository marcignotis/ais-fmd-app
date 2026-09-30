"""
My Transactions -- a VP's own committee's ledger, read-only.

The committee comes from the signed-in identity (`identity.committee_id`) and is
never a widget, so there is nothing on the page a VP could change to see another
committee's rows. Only rows booked to that committee are ever put in the table.

Read-only on purpose: a VP who thinks a charge is booked to the wrong committee
tells the treasurer; they do not recategorize it themselves.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ais_fmd import auth
from ais_fmd.config import vp_committees
from ais_fmd.config.categories import committee_name
from ais_fmd.data import repositories as repo
from ais_fmd.domain.terms import attach_semester, default_semester_index, ordered_semesters
from ais_fmd.ui import shell

identity = auth.require(auth.Role.OFFICER)

shell.environment_banner()

committee_id = identity.committee_id
if committee_id is None:
    shell.page_header("My Transactions", "Every charge booked to your committee.")
    shell.empty_state(
        "No committee assigned to your account",
        " Ask the treasurer to add your email under Officer Access.",
    )
    st.stop()

shell.page_header(
    "My Transactions",
    f"Every charge and deposit booked to {vp_committees.title_for(committee_id)}.",
)

bundle = repo.load_bundle()
if bundle.transactions.empty:
    shell.empty_state("No transactions yet", " Nothing has been uploaded.")
    st.stop()

# --- Scope: this committee only, before any filter is applied ----------------

# A committee can own several budget lines (Membership owns Membership and
# Passport); all of them are "mine". Anything outside them is never selected.
line_ids = vp_committees.budget_ids_for(committee_id)
tagged = attach_semester(bundle.transactions, bundle.terms)
mine = tagged[tagged["budget_category"].isin(line_ids)]

# --- Filters -----------------------------------------------------------------

semesters = ordered_semesters(bundle.terms)
semester_options = ["All"] + semesters
default_index = default_semester_index(bundle.transactions, bundle.terms) + 1 if semesters else 0

filter_columns = st.columns([2, 2, 3])
with filter_columns[0]:
    semester_choice = st.selectbox(
        "Semester", semester_options, index=default_index, key="mytxn_semester"
    )
with filter_columns[1]:
    type_choice = st.selectbox("Type", ["All", "Income", "Expense"], key="mytxn_type")
with filter_columns[2]:
    search = st.text_input("Search details", placeholder="merchant, note…", key="mytxn_search")

line_choice = "All"
if len(line_ids) > 1:
    line_choice = st.selectbox(
        "Budget line",
        ["All"] + [committee_name(cid) for cid in line_ids],
        key="mytxn_line",
    )

view = mine
if line_choice != "All":
    line_id = next(cid for cid in line_ids if committee_name(cid) == line_choice)
    view = view[view["budget_category"] == line_id]
if semester_choice != "All":
    view = view[view["Semester"] == semester_choice]
if type_choice == "Income":
    view = view[view["amount"] > 0]
elif type_choice == "Expense":
    view = view[view["amount"] < 0]
if search.strip():
    view = view[view["details"].str.contains(search.strip(), case=False, na=False, regex=False)]

view = view.sort_values("transaction_date", ascending=False)

# --- Summary and table -------------------------------------------------------

charged = float(-view.loc[view["amount"] < 0, "amount"].sum())
received = float(view.loc[view["amount"] > 0, "amount"].sum())

shell.metric_row(
    [
        {"label": "Charged", "value": charged, "inverse": True},
        {"label": "Received", "value": received},
        {"label": "Transactions", "value": len(view), "currency": False},
    ]
)

if view.empty:
    shell.empty_state("Nothing matches these filters", " Try widening the search.")
    st.stop()

table = pd.DataFrame(
    {
        "Date": pd.to_datetime(view["transaction_date"]).dt.date,
        "Amount": view["amount"],
        "Purpose": view["purpose"].fillna("—"),
        "Details": view["details"].fillna("").astype(str),
    }
)
if len(line_ids) > 1:
    table.insert(1, "Line", view["budget_category"].map(committee_name))

shell.dataframe(
    table,
    column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")},
    height=520,
)
st.caption(
    "Read-only. If a charge looks like it belongs to another committee, tell the treasurer."
)
