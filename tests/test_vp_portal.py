"""
VP portal: navigation, and proof that a VP only ever sees their own committee.

The navigation tests are pure. The isolation tests render the real pages
headlessly as an Officer for every budgeted committee and compare what is on
screen against the database, row for row -- an exact match, so a leak of even
one other-committee row fails.
"""

from __future__ import annotations

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from ais_fmd import auth, nav
from ais_fmd.config.categories import BUDGETED_COMMITTEE_IDS, committee_name

# Fixtures and helpers shared with the other headless view tests.
from tests.test_views import ROOT, TIMEOUT, VIEWS, assert_clean, seeded_db, use_db  # noqa: F401

OFFICER = auth.Role.OFFICER


def run_as(path, role, committee_id=None, **session) -> AppTest:
    app = AppTest.from_file(str(path), default_timeout=TIMEOUT)
    app.session_state[auth.SESSION_KEY] = auth.Identity(
        email="vp@sandbox.local", role=role, committee_id=committee_id
    )
    for key, value in session.items():
        app.session_state[key] = value
    return app.run()


# --- Navigation (pure) ---------------------------------------------------------

FULL_PAGES = [
    ("ais_fmd/views/Dashboard.py", "Dashboard", "i", auth.Role.MEMBER),
    ("ais_fmd/views/Transactions.py", "Transactions", "i", auth.Role.MEMBER),
    ("ais_fmd/views/Treasury.py", "Treasury", "i", auth.Role.TREASURER),
]


def test_a_vp_gets_exactly_three_pages():
    vp = auth.Identity(email="vp@x.edu", role=OFFICER, committee_id=8)
    titles = [page[1] for page in nav.visible_pages(vp, FULL_PAGES)]
    assert titles == ["Home", "My Committee", "My Transactions"]


def test_a_vp_never_gets_a_page_that_shows_every_committee():
    vp = auth.Identity(email="vp@x.edu", role=OFFICER, committee_id=8)
    paths = {page[0] for page in nav.visible_pages(vp, FULL_PAGES)}
    assert not paths & {page[0] for page in FULL_PAGES}


def test_a_treasurer_keeps_the_full_navigation():
    treasurer = auth.Identity(email="t@x.edu", role=auth.Role.TREASURER)
    assert nav.visible_pages(treasurer, FULL_PAGES) == FULL_PAGES


def test_a_member_is_not_given_the_vp_pages():
    member = auth.Identity(email="m@x.edu", role=auth.Role.MEMBER)
    titles = [page[1] for page in nav.visible_pages(member, FULL_PAGES)]
    assert titles == ["Dashboard", "Transactions"]


@pytest.mark.parametrize("path", [page[0] for page in nav.VP_PAGES])
def test_every_vp_page_exists_and_is_gated(path):
    source = (ROOT / path).read_text(encoding="utf-8")
    assert "auth.require" in source or path.endswith("Home.py")


# --- Isolation (headless renders) ---------------------------------------------


def _committee_rows(committee_id: int) -> list[tuple]:
    """What the database holds for one committee, in a comparable shape."""
    from ais_fmd.data.sqlite_backend import SqliteBackend

    frame = SqliteBackend().fetch_transactions()
    rows = frame[frame["budget_category"].eq(committee_id).fillna(False)]
    return sorted(
        (
            str(pd.Timestamp(date).date()),
            round(float(amount), 2),
            "" if pd.isna(details) else str(details),
        )
        for date, amount, details in zip(rows["transaction_date"], rows["amount"], rows["details"])
    )


def test_the_seed_gives_the_isolation_tests_something_to_prove(seeded_db, use_db):
    use_db(seeded_db)
    populated = [cid for cid in BUDGETED_COMMITTEE_IDS if _committee_rows(cid)]
    assert len(populated) >= 3, "too few committees have rows for these tests to mean anything"


@pytest.mark.parametrize("committee_id", BUDGETED_COMMITTEE_IDS)
def test_a_vp_sees_exactly_their_committees_transactions(committee_id, seeded_db, use_db):
    use_db(seeded_db)
    app = run_as(VIEWS / "MyTransactions.py", OFFICER, committee_id, mytxn_semester="All")
    assert_clean(app, f"My Transactions as the {committee_name(committee_id)} VP")

    expected = _committee_rows(committee_id)
    if not expected:
        assert not app.dataframe
        return

    shown = app.dataframe[0].value
    got = sorted(
        (str(pd.Timestamp(date).date()), round(float(amount), 2), str(details))
        for date, amount, details in zip(shown["Date"], shown["Amount"], shown["Details"])
    )
    assert got == expected


def test_an_officer_with_no_committee_sees_nothing(seeded_db, use_db):
    use_db(seeded_db)
    for view in ("MyTransactions.py", "Officer.py"):
        app = run_as(VIEWS / view, OFFICER, None)
        assert_clean(app, f"{view} as an officer with no committee")
        assert not app.dataframe, f"{view} showed data to an officer with no committee"
        assert not app.selectbox, f"{view} offered a picker to an officer with no committee"


def test_a_vp_cannot_pick_another_committee_on_my_committee(seeded_db, use_db):
    use_db(seeded_db)
    app = run_as(VIEWS / "Officer.py", OFFICER, 8)
    assert_clean(app, "My Committee as the Meeting Food VP")
    assert "Committee" not in [box.label for box in app.selectbox]
    assert committee_name(8) in " ".join(block.value for block in app.markdown)


def test_a_treasurer_can_still_pick_any_committee(seeded_db, use_db):
    use_db(seeded_db)
    app = run_as(VIEWS / "Officer.py", auth.Role.TREASURER)
    assert_clean(app, "My Committee as the treasurer")
    assert "Committee" in [box.label for box in app.selectbox]


def test_home_points_a_vp_only_at_pages_they_have(seeded_db, use_db):
    use_db(seeded_db)
    app = run_as(VIEWS / "Home.py", OFFICER, 8)
    assert_clean(app, "Home as a VP")
    text = " ".join(block.value for block in app.markdown)
    assert "My Transactions" in text
    assert "Review Queue" not in text
