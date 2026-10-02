"""
Which budget lines each VP's committee owns.

The website lists six committees, each with one VP. The app books money to 18
finer-grained budget lines (`config/categories.py`). A VP should see the money
for everything their committee owns, so this file says which lines roll up into
which committee.

PROVISIONAL. This mapping is a proposal that the treasurer has not confirmed.
Nothing here decides where money is booked -- it only decides which lines are
added together on a VP's page -- but a wrong line here shows a VP the wrong
budget, so confirm it before real VPs sign in. Each entry says how sure it is.

Not listed on purpose:
  * Finance (Treasury, line 2) -- the treasurer's own full view, not a VP page.
  * Operations -- no budget line is obviously theirs yet; awaiting the treasurer.
  * Passport (line 16) -- treated as outside the six committees. A VP never sees
    its transactions; only the treasurer does. Unconfirmed.

No committee currently owns more than one line, but the roll-up (a committee that
adds several lines together) is kept and tested, for the day one does.
A committee that is not listed falls back to showing just its own single line,
exactly as before, so an unmapped VP still sees something correct.

No emails here. Which Google account belongs to which committee is entered by
the treasurer on the Officer Access page, never in this public repository.
"""

from __future__ import annotations

from dataclasses import dataclass

from .categories import committee_name


@dataclass(frozen=True)
class VpCommittee:
    title: str
    # Budget-line ids this committee owns. The first is its "home" line, the id
    # a VP's profile is expected to carry.
    budget_ids: tuple[int, ...]

    @property
    def budget_names(self) -> list[str]:
        return [committee_name(cid) for cid in self.budget_ids]


VP_COMMITTEES: tuple[VpCommittee, ...] = (
    # Exact name match.
    VpCommittee("Professional Development", (10,)),
    # Exact name match.
    VpCommittee("Consulting", (7,)),
    # Marketing is an exact match. Merch (13) may belong here too -- unconfirmed.
    VpCommittee("Marketing", (9,)),
    # Membership is an exact match and owns only its own line. Passport (16) was
    # first assumed to belong here (a Membership chair runs the passport program),
    # but it is treated as OUTSIDE the six committees, so no VP sees it.
    # Meeting Food, Road Trip and Formal may belong to a committee -- unconfirmed.
    VpCommittee("Membership", (5,)),
)


def for_committee_id(committee_id: int | None) -> VpCommittee | None:
    """The VP committee that owns this budget line, or None if it is unmapped."""
    if committee_id is None:
        return None
    for committee in VP_COMMITTEES:
        if int(committee_id) in committee.budget_ids:
            return committee
    return None


def budget_ids_for(committee_id: int | None) -> tuple[int, ...]:
    """Every budget line a VP with this profile committee may see."""
    if committee_id is None:
        return ()
    owner = for_committee_id(committee_id)
    return owner.budget_ids if owner else (int(committee_id),)


def title_for(committee_id: int | None) -> str:
    owner = for_committee_id(committee_id)
    return owner.title if owner else committee_name(committee_id)
