"""
Bulk merchant grouping (M4b / P3).

What is left of bulk mapping after treasury ruled merchant memory out of
categorization (2026-09-23): the grouping and proposal logic in
`categorize/bulk.py`, which is still pure and still tested here. The
`propose_merchants.py` script that turned proposals into merchant rules, and
the rule-ordering tests that guarded it, were removed with the merchant tier.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ais_fmd.domain.categorize import bulk


def record(details: str, amount: float, date: str = "2025-09-17") -> dict:
    return {
        "details": details,
        "amount": amount,
        "transaction_date": date,
        "account": "Wells Fargo",
    }


# --- Grouping ----------------------------------------------------------------

def test_store_number_variants_collapse_into_one_decision():
    """The whole point: one decision, not one per store."""
    rows = [
        record("PURCHASE AUTHORIZED ON 09/17 CHIPOTLE 1462 GAINESVILLE FL", -42.10),
        record("PURCHASE AUTHORIZED ON 10/02 CHIPOTLE 1893 GAINESVILLE FL", -38.55),
        record("PURCHASE AUTHORIZED ON 10/09 CHIPOTLE 1462 GAINESVILLE FL", -51.00),
    ]
    groups = bulk.group_residual(rows)
    assert len(groups) == 1
    assert groups[0].row_count == 3


def test_display_name_is_the_merchant_not_the_statement_prefix():
    """
    Every raw row starts "PURCHASE AUTHORIZED ON <date>", which identifies
    nothing. The label must be the merchant.
    """
    groups = bulk.group_residual(
        [record("PURCHASE AUTHORIZED ON 09/13 PUBLIX #1234 GAINESVILLE FL", -27.31)]
    )
    assert "publix" in groups[0].display_name.lower()
    assert "authorized" not in groups[0].display_name.lower()


def test_member_transfers_never_become_merchant_groups():
    """A rule keyed on a member's name would mis-categorise everything they pay."""
    rows = [record("ZELLE FROM JANE DOE ON 07/08 REF # ABC123", 20.0)]
    groups = bulk.group_residual(rows)
    assert all(group.kind != bulk.KIND_MERCHANT for group in groups)


# --- Memo extraction ---------------------------------------------------------

@pytest.mark.parametrize(
    "details,expected",
    [
        ("ZELLE FROM PARKER LANE ON 09/20 REF # BACQZL9WFMD1 PARKER LANE HEADSHOT", "headshot"),
        ("ZELLE FROM LEO ON 11/01 REF # BACBGEVAAPVX HOODIE  TSHIRT  LEONAR", "merch"),
        ("ZELLE FROM ANON ON 09/20 REF # BACFAPGQWS2V", ""),
    ],
)
def test_memo_theme_reads_what_the_payment_was_for(details, expected):
    """
    These 120 rows were invisible to merchant memory by design, and nothing
    else was reading the memo the member typed.
    """
    assert bulk.memo_theme(details) == expected


def test_memo_keywords_survive_run_together_words():
    """Real memos concatenate: 'PEI CHI WANGHEADSHOT'."""
    assert bulk.memo_theme("ZELLE FROM X ON 09/20 REF # AB1 PEI CHI WANGHEADSHOT") == "headshot"


# --- Proposals ---------------------------------------------------------------

def test_bar_merchant_proposes_membership():
    groups = bulk.group_residual(
        [record("PURCHASE AUTHORIZED ON 09/17 MACDINTONS GAINESVILLE FL", -88.00)]
    )
    assert bulk.propose(groups[0]).committee_id == 5


def test_food_on_meeting_weekdays_proposes_meeting_food():
    # 2025-09-16 and 2025-09-17 are a Tuesday and a Wednesday.
    rows = [
        record("PURCHASE AUTHORIZED ON 09/16 PUBLIX GAINESVILLE FL", -40.0, "2025-09-18"),
        record("PURCHASE AUTHORIZED ON 09/17 PUBLIX GAINESVILLE FL", -35.0, "2025-09-19"),
    ]
    proposal = bulk.propose(bulk.group_residual(rows)[0])
    assert proposal.committee_id == 8
    assert not proposal.needs_decision


def test_food_off_meeting_weekdays_refuses_to_guess():
    """
    The honest outcome. A Saturday Publix run is not meeting food, and which
    line it belongs to is a decision about real money.
    """
    rows = [
        record("PURCHASE AUTHORIZED ON 09/20 PUBLIX GAINESVILLE FL", -40.0, "2025-09-22"),
        record("PURCHASE AUTHORIZED ON 09/21 PUBLIX GAINESVILLE FL", -35.0, "2025-09-23"),
    ]
    proposal = bulk.propose(bulk.group_residual(rows)[0])
    assert proposal.committee_id is None
    assert proposal.needs_decision


def test_bank_deposits_are_never_auto_assigned():
    """$15,400 of deposits must not be booked by a keyword."""
    rows = [record("MOBILE DEPOSIT : REF NUMBER :408071", 1500.0) for _ in range(3)]
    proposal = bulk.propose(bulk.group_residual(rows)[0])
    assert proposal.committee_id is None
    assert proposal.needs_decision


def test_returns_propose_refunded():
    rows = [record("PURCHASE RETURN AUTHORIZED ON 04/12 AMAZON.COM", 37.39)]
    assert bulk.propose(bulk.group_residual(rows)[0]).committee_id == 17


def test_proposal_carries_row_count_and_total():
    rows = [
        record("PURCHASE AUTHORIZED ON 09/16 PUBLIX GAINESVILLE FL", -40.0),
        record("PURCHASE AUTHORIZED ON 09/17 PUBLIX GAINESVILLE FL", -35.0),
    ]
    proposal = bulk.propose(bulk.group_residual(rows)[0])
    assert proposal.row_count == 2
    assert proposal.total_amount == Decimal("-75.00")


# --- Override detection ------------------------------------------------------

def test_report_warns_when_a_mapping_would_rebook_classified_rows():
    """
    The hazard bulk mapping introduces and the review queue does not.

    One Publix row is on the consulting card, so a rule already books it to
    Consulting. Mapping the merchant to Meeting Food would silently move it.
    """
    classified = record("PURCHASE AUTHORIZED ON 09/16 PUBLIX CARD 8408 GAINESVILLE FL", -20.0)
    residual = [record("PURCHASE AUTHORIZED ON 09/20 PUBLIX GAINESVILLE FL", -40.0, "2025-09-22")]

    report = bulk.build_report(
        residual,
        all_records=[classified, *residual],
        committee_ids=[7, None],
    )
    proposal = report.proposals[0]
    assert proposal.already_classified == {7: 1}

    from dataclasses import replace

    as_food = replace(proposal, committee_id=8, confidence=0.9)
    assert as_food.override_count == 1
    assert "Consulting" in as_food.override_warning()


def test_no_warning_when_the_mapping_agrees_with_existing_classifications():
    rows = [record("PURCHASE AUTHORIZED ON 09/20 PUBLIX GAINESVILLE FL", -40.0)]
    report = bulk.build_report(rows, all_records=rows, committee_ids=[8])
    from dataclasses import replace

    proposal = replace(report.proposals[0], committee_id=8)
    assert proposal.override_count == 0
    assert proposal.override_warning() == ""
