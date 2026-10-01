"""
"This isn't ours" -- a VP disputing a charge.

A VP who thinks a charge is booked to the wrong committee flags it with a note.
The flag goes to the treasurer's Review Queue. The VP never changes the booking:
only the treasurer decides which committee money is booked to, so a flag is a
message, not an edit. Resolving or dismissing it is also the treasurer's call.

Pure rules and display helpers only -- no Streamlit, no database -- so they can
be tested on their own and shared by every backend.
"""

from __future__ import annotations

import pandas as pd

OPEN = "open"
RESOLVED = "resolved"
DISMISSED = "dismissed"

# What a treasurer may close a flag as. A flag is created open; never created
# resolved.
CLOSING_STATUSES = (RESOLVED, DISMISSED)

MIN_NOTE_LENGTH = 5
MAX_NOTE_LENGTH = 500

# How each status reads to a VP, who does not think in "dismissed".
_VP_LABELS = {
    OPEN: "With the treasurer",
    RESOLVED: "Resolved",
    DISMISSED: "Treasurer kept it as booked",
}


def clean_note(note: object) -> tuple[str | None, str | None]:
    """
    (cleaned note, None) when usable, or (None, reason) when not.

    A flag with no explanation is no use to the treasurer, who would have to ask
    the VP what they meant, so a note is required. An upper bound keeps one flag
    from becoming an essay (or a place to paste something that does not belong
    in a public-facing log).
    """
    if note is None or (isinstance(note, float) and pd.isna(note)):
        return None, "Say why this charge is not yours."
    text = " ".join(str(note).split())
    if len(text) < MIN_NOTE_LENGTH:
        return None, f"Add a few words on why (at least {MIN_NOTE_LENGTH} characters)."
    if len(text) > MAX_NOTE_LENGTH:
        return None, f"Keep it under {MAX_NOTE_LENGTH} characters (this is {len(text)})."
    return text, None


def vp_status_label(status: object) -> str:
    return _VP_LABELS.get(str(status), str(status))


def status_by_transaction(flags: pd.DataFrame) -> dict[int, str]:
    """
    Latest status per transaction, with an open flag always winning.

    A charge can be flagged, resolved, then flagged again later; the table that
    marks "which of my charges are flagged" should show the live one.
    """
    if flags is None or flags.empty:
        return {}
    ordered = flags.copy()
    ordered["_rank"] = ordered["status"].map(lambda value: 0 if value == OPEN else 1)
    ordered = ordered.sort_values(["_rank", "flag_id"], ascending=[True, False])
    first = ordered.drop_duplicates("transaction_id", keep="first")
    return {int(row["transaction_id"]): str(row["status"]) for _, row in first.iterrows()}


def with_charges(flags: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    """Each flag next to the charge it is about (date, amount, details, booked to)."""
    if flags is None or flags.empty:
        return pd.DataFrame()
    charges = transactions[
        ["transactionid", "transaction_date", "amount", "details", "budget_category", "purpose"]
    ].rename(columns={"transactionid": "transaction_id"})
    return flags.merge(charges, on="transaction_id", how="left")
