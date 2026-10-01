"""
"This isn't ours": the VP and treasurer pages.

The data rules (who can flag what, that flagging never changes a charge) are tested
in test_flags.py. These tests drive the real pages through both sides of the flow:
a VP flagging a charge, and the treasurer seeing and closing it in the Review Queue.
"""

from __future__ import annotations

import pytest

from ais_fmd import auth
from ais_fmd.data.sqlite_backend import SqliteBackend

# Fixtures and helpers shared with the other VP tests.
from tests.test_flags import NOTE, OFFICER, VP, charge_in, snapshot  # noqa: F401
from tests.test_views import VIEWS, assert_clean, seeded_db, use_db  # noqa: F401
from tests.test_vp_portal import run_as  # noqa: F401


def test_a_vp_flags_a_charge_through_the_page_and_nothing_else_changes(seeded_db, use_db):
    use_db(seeded_db)
    app = run_as(VIEWS / "MyTransactions.py", OFFICER, 7, mytxn_semester="All")
    assert_clean(app, "My Transactions as the Consulting VP")

    app.selectbox(key="flag_charge_0").select_index(0)
    app.text_area(key="flag_note_0").input(NOTE)
    app.button(key="flag_submit_0").click()
    app.run()
    assert_clean(app, "after flagging a charge")

    backend = SqliteBackend()
    flags = backend.fetch_flags()
    assert len(flags) == 1
    flagged = int(flags.iloc[0]["transaction_id"])
    assert flags.iloc[0]["booked_to_committee_id"] == 7
    assert snapshot(backend, flagged)["budget_category"] == 7  # still booked where it was
    assert any("Flagged" in block.value for block in app.success)

    table = app.dataframe[0].value
    assert "Flag" in table.columns
    assert "With the treasurer" in set(table["Flag"])


def test_the_page_refuses_a_flag_with_no_note(seeded_db, use_db):
    use_db(seeded_db)
    app = run_as(VIEWS / "MyTransactions.py", OFFICER, 7, mytxn_semester="All")
    app.button(key="flag_submit_0").click()
    app.run()
    assert_clean(app, "submitting a flag with no note")
    assert SqliteBackend().fetch_flags().empty


def test_a_vp_sees_only_their_own_flags_on_the_page(seeded_db, use_db):
    use_db(seeded_db)
    backend = SqliteBackend()
    backend.create_flag(charge_in(backend, 7), (7,), "Consulting note, not ours.", VP)
    backend.create_flag(charge_in(backend, 9), (9,), "Marketing note, not ours.", VP)

    app = run_as(VIEWS / "MyTransactions.py", OFFICER, 7, mytxn_semester="All")
    assert_clean(app, "My Transactions as the Consulting VP")
    notes = set()
    for element in app.dataframe:
        if "Your note" in element.value.columns:
            notes |= set(element.value["Your note"])
    assert notes == {"Consulting note, not ours."}


def test_the_treasurer_sees_a_flag_in_the_review_queue(seeded_db, use_db):
    use_db(seeded_db)
    backend = SqliteBackend()
    backend.create_flag(charge_in(backend, 7), (7,), NOTE, VP)
    app = run_as(VIEWS / "ReviewQueue.py", auth.Role.TREASURER)
    assert_clean(app, "Review Queue with an open flag")
    assert any(NOTE in block.value for block in app.markdown)


@pytest.mark.parametrize(
    ("button_prefix", "expected_status"),
    [("flag_resolve_", "resolved"), ("flag_dismiss_", "dismissed")],
)
def test_the_treasurer_closes_a_flag_and_the_charge_stays_where_it_was(
    button_prefix, expected_status, seeded_db, use_db
):
    use_db(seeded_db)
    backend = SqliteBackend()
    charge = charge_in(backend, 7)
    backend.create_flag(charge, (7,), NOTE, VP)
    before = snapshot(backend, charge)
    flag_id = int(backend.fetch_flags().iloc[0]["flag_id"])

    app = run_as(VIEWS / "ReviewQueue.py", auth.Role.TREASURER)
    app.text_input(key=f"flag_reply_{flag_id}").input("Looked into it.")
    app.button(key=f"{button_prefix}{flag_id}").click()
    app.run()
    assert_clean(app, "closing a flag from the Review Queue")

    row = backend.fetch_flags().iloc[0]
    assert (row["status"], row["resolution_note"]) == (expected_status, "Looked into it.")
    assert snapshot(backend, charge) == before  # closing a flag does not move money
