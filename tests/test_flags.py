"""
"This isn't ours": a VP disputing a charge.

The properties that matter, each with a test that fails if it breaks:

  * a VP can flag only a charge booked to their own committee's lines, and the
    data layer enforces it (not just the page);
  * flagging never changes the charge -- only the treasurer moves money;
  * a VP sees only their own committee's flags;
  * the treasurer sees open flags in the Review Queue and can close them.

All data is the sandbox seed; all emails are invented `@sandbox.local` addresses.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ais_fmd import auth
from ais_fmd.data.sqlite_backend import SqliteBackend
from ais_fmd.domain import flags as flags_domain

# Fixtures shared with the other VP tests.
from tests.test_views import seeded_db, use_db  # noqa: F401
from tests.test_vp_portal import membership_db  # noqa: F401

OFFICER = auth.Role.OFFICER
VP = "vp@sandbox.local"
NOTE = "This was bought for a different committee's event."


def charge_in(backend: SqliteBackend, committee_id: int, *, nth: int = 0) -> int:
    frame = backend.fetch_transactions()
    rows = frame[frame["budget_category"].eq(committee_id).fillna(False)]
    return int(rows.iloc[nth]["transactionid"])


def snapshot(backend: SqliteBackend, transaction_id: int) -> dict:
    frame = backend.fetch_transactions()
    row = frame[frame["transactionid"] == transaction_id].iloc[0]
    return {
        key: (None if pd.isna(row[key]) else row[key])
        for key in ("amount", "details", "budget_category", "purpose", "transaction_date")
    }


# --- Rules (pure) --------------------------------------------------------------


def test_a_usable_note_is_trimmed_and_kept():
    cleaned, problem = flags_domain.clean_note("  Not   ours,\n it was for the other event  ")
    assert problem is None
    assert cleaned == "Not ours, it was for the other event"


@pytest.mark.parametrize("note", [None, float("nan"), "", "   ", "abc", "x" * 501])
def test_an_unusable_note_is_refused_with_a_reason(note):
    cleaned, problem = flags_domain.clean_note(note)
    assert cleaned is None
    assert problem


def test_an_open_flag_wins_over_an_older_closed_one():
    flags = pd.DataFrame(
        {
            "flag_id": [1, 2, 3],
            "transaction_id": [10, 10, 11],
            "status": ["resolved", "open", "dismissed"],
        }
    )
    assert flags_domain.status_by_transaction(flags) == {10: "open", 11: "dismissed"}
    assert flags_domain.status_by_transaction(pd.DataFrame()) == {}


def test_a_vp_reads_statuses_in_plain_words():
    assert flags_domain.vp_status_label("open") == "With the treasurer"
    assert "kept" in flags_domain.vp_status_label("dismissed").lower()


# --- The data layer ------------------------------------------------------------


def test_a_vp_can_flag_a_charge_booked_to_their_committee(seeded_db, use_db):
    use_db(seeded_db)
    backend = SqliteBackend()
    charge = charge_in(backend, 7)
    result = backend.create_flag(charge, (7,), NOTE, VP)
    assert result.ok and result.updated == 1

    flags = backend.fetch_flags()
    assert len(flags) == 1
    row = flags.iloc[0]
    assert (row["transaction_id"], row["booked_to_committee_id"], row["flagged_by"]) == (charge, 7, VP)
    assert row["status"] == "open" and row["note"] == NOTE


def test_flagging_a_charge_changes_nothing_about_it(seeded_db, use_db):
    """A flag is a message. Only the treasurer moves money."""
    use_db(seeded_db)
    backend = SqliteBackend()
    charge = charge_in(backend, 7)
    before = snapshot(backend, charge)
    backend.create_flag(charge, (7,), NOTE, VP)
    assert snapshot(backend, charge) == before


def test_a_vp_cannot_flag_another_committees_charge(seeded_db, use_db):
    use_db(seeded_db)
    backend = SqliteBackend()
    marketing_charge = charge_in(backend, 9)
    result = backend.create_flag(marketing_charge, (7,), NOTE, VP)  # a Consulting VP
    assert result.error and "not booked to your committee" in result.error
    assert backend.fetch_flags().empty


def test_an_uncategorized_charge_cannot_be_flagged(seeded_db, use_db):
    use_db(seeded_db)
    backend = SqliteBackend()
    frame = backend.fetch_transactions()
    loose = int(frame[frame["budget_category"].isna()].iloc[0]["transactionid"])
    result = backend.create_flag(loose, (7,), NOTE, VP)
    assert result.error
    assert backend.fetch_flags().empty


def test_a_charge_that_does_not_exist_is_refused(seeded_db, use_db):
    use_db(seeded_db)
    result = SqliteBackend().create_flag(10**9, (7,), NOTE, VP)
    assert result.error and "does not exist" in result.error


@pytest.mark.parametrize("note", ["", "   ", "abc", "x" * 501])
def test_a_flag_needs_a_proper_note(note, seeded_db, use_db):
    use_db(seeded_db)
    backend = SqliteBackend()
    result = backend.create_flag(charge_in(backend, 7), (7,), note, VP)
    assert result.error
    assert backend.fetch_flags().empty


def test_flagging_twice_does_not_stack_duplicates(seeded_db, use_db):
    use_db(seeded_db)
    backend = SqliteBackend()
    charge = charge_in(backend, 7)
    assert backend.create_flag(charge, (7,), NOTE, VP).updated == 1
    second = backend.create_flag(charge, (7,), "Flagging it again, just to be sure.", VP)
    assert second.unchanged == 1 and not second.error
    assert len(backend.fetch_flags()) == 1


def test_a_committee_that_owns_two_lines_can_flag_either(membership_db):
    backend = SqliteBackend()
    passport_charge = charge_in(backend, 16)
    assert backend.create_flag(passport_charge, (5,), NOTE, VP).error  # Membership line alone: no
    assert backend.create_flag(passport_charge, (5, 16), NOTE, VP).ok  # both lines: yes


def test_the_treasurer_can_close_a_flag_once_and_it_can_be_raised_again(seeded_db, use_db):
    use_db(seeded_db)
    backend = SqliteBackend()
    charge = charge_in(backend, 7)
    backend.create_flag(charge, (7,), NOTE, VP)
    flag_id = int(backend.fetch_flags().iloc[0]["flag_id"])

    assert backend.resolve_flag(flag_id, "bogus", "treasurer@sandbox.local").error
    closed = backend.resolve_flag(flag_id, "resolved", "treasurer@sandbox.local", "Moved it.")
    assert closed.ok and closed.updated == 1
    row = backend.fetch_flags().iloc[0]
    assert (row["status"], row["resolved_by"], row["resolution_note"]) == (
        "resolved", "treasurer@sandbox.local", "Moved it.",
    )
    assert backend.resolve_flag(flag_id, "dismissed", "treasurer@sandbox.local").unchanged == 1

    # Closed flags no longer block a fresh one on the same charge.
    assert backend.create_flag(charge, (7,), "Still wrong after the last review.", VP).ok
    assert len(backend.fetch_flags()) == 2


def test_a_vp_is_only_ever_given_their_own_committees_flags(seeded_db, use_db):
    use_db(seeded_db)
    backend = SqliteBackend()
    backend.create_flag(charge_in(backend, 7), (7,), "Consulting note, not ours.", VP)
    backend.create_flag(charge_in(backend, 9), (9,), "Marketing note, not ours.", VP)
    assert set(backend.fetch_flags((7,))["note"]) == {"Consulting note, not ours."}
    assert set(backend.fetch_flags((9,))["note"]) == {"Marketing note, not ours."}
    assert backend.fetch_flags(()).empty
    assert len(backend.fetch_flags(None)) == 2


def test_flagging_and_closing_are_written_to_the_audit_trail(seeded_db, use_db):
    use_db(seeded_db)
    backend = SqliteBackend()
    charge = charge_in(backend, 7)
    backend.create_flag(charge, (7,), NOTE, VP)
    backend.resolve_flag(int(backend.fetch_flags().iloc[0]["flag_id"]), "dismissed", "t@sandbox.local")
    audit = backend.fetch_audit()
    actions = set(audit[audit["transaction_id"] == charge]["action"])
    assert {"flag", "flag_resolved"} <= actions


def test_resetting_the_sandbox_clears_flags_without_a_foreign_key_error(seeded_db, use_db):
    use_db(seeded_db)
    backend = SqliteBackend()
    backend.create_flag(charge_in(backend, 7), (7,), NOTE, VP)
    backend.reset()
    assert backend.fetch_flags().empty
