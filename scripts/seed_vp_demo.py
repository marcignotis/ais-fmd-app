"""
Add fake demo transactions for the VP committees to the SANDBOX database.

The normal seed books almost nothing to Membership or Passport and spreads most
committees' spending over a single purpose, so a VP's page comes up nearly empty.
This tops each VP committee up to a chosen share of its budget over the last
three terms, with several purposes, a few refunds or deposits coming in, and a
mix of states (on track, approaching, over), so every chart and table on My
Committee and My Transactions has something to draw.

Everything here is invented: made-up venues and vendors, no real names, card
numbers or amounts from any statement. It refuses to run outside the sandbox.

    .venv\\Scripts\\python scripts/seed_vp_demo.py

Safe to run twice (the second run says it was already loaded). "Reset & reseed
data" in the sidebar wipes it along with everything else; run this again after.
Restart Streamlit afterwards, or wait a few minutes for its cache to expire.
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from ais_fmd import settings
from ais_fmd.config.categories import ACCOUNT_WELLS_FARGO, committee_name
from ais_fmd.data.sqlite_backend import SqliteBackend
from ais_fmd.domain.dedupe import assign_natural_keys

FILE_NAME = "vp_demo_seed.csv"
ACTOR = "vp-demo-seed@sandbox.local"

# The terms to fill and how far into the latest one the demo data reaches. The
# regular seed already runs to late October of Fall 2026.
TERM_IDS = ("FA25", "SP26", "FA26")
LATEST_DATA_DAY = date(2026, 10, 22)

# Share of each term's budget to bring a line up to: {line: {term: share}}.
# Chosen to give every status. Existing spending counts toward the share, and a
# line already past its target is left alone, never reduced.
TARGET_SHARE = {
    5: {"FA25": 0.62, "SP26": 0.80, "FA26": 0.88},   # Membership: approaching
    16: {"FA25": 0.40, "SP26": 0.75, "FA26": 1.12},  # Passport: over
    10: {"FA25": 0.55, "SP26": 0.70, "FA26": 0.45},  # Professional Development: on track
    7: {"FA25": 0.50, "SP26": 0.90, "FA26": 0.60},   # Consulting
    9: {"FA25": 0.50, "SP26": 0.70, "FA26": 0.50},   # Marketing (already over in Fall 2026)
}

# (purpose, weight, vendor names). Invented vendors only.
SPENDING = {
    5: [
        ("Social Events", 0.45, ["TOPGOLF GAINESVILLE", "BOWLING LANES GNV", "POTTERY STUDIO GNV"]),
        ("Food & Drink", 0.35, ["ARCADE BAR GNV", "TACO SHACK GNV", "PIZZA PALACE GNV"]),
        ("Misc.", 0.20, ["LAKE PARK ENTRY FEES", "PARTY SUPPLIES OUTLET"]),
    ],
    16: [
        ("ISOM Passport", 0.55, ["PASSPORT STAMPS PRINT SHOP", "PASSPORT BOOKLETS PRINTING"]),
        ("Food & Drink", 0.30, ["CULTURAL NIGHT CATERING", "WORLD FOODS MARKET GNV"]),
        ("Social Events", 0.15, ["INTL STUDENT MIXER VENUE"]),
    ],
    10: [
        ("Professional Events", 0.50, ["INDUSTRY PANEL VENUE", "CAREER NIGHT HALL RENTAL"]),
        ("Professional Development", 0.30, ["WORKSHOP SPEAKER HONORARIUM", "ONLINE COURSE LICENSES"]),
        ("Food & Drink", 0.20, ["CATERED WORKSHOP LUNCH", "COFFEE CART GNV"]),
    ],
    7: [
        ("Technology", 0.40, ["CLOUD HOSTING CREDITS", "PROJECT TOOLS SUBSCRIPTION"]),
        ("Food & Drink", 0.35, ["CLIENT KICKOFF LUNCH", "TEAM WORKING DINNER"]),
        ("Misc.", 0.25, ["CLIENT GIFT BASKETS", "PRESENTATION PRINTING"]),
    ],
    9: [
        ("Marketing", 0.50, ["BANNER PRINTING GNV", "FLYER PRINTING GNV"]),
        ("Merch", 0.30, ["EMBROIDERY SHOP GNV", "STICKER PRINTER"]),
        ("Technology", 0.20, ["WEBSITE HOSTING", "DESIGN TOOL SUBSCRIPTION"]),
    ],
}

# Money coming back in, so "Money received" has something to show:
# (line, purpose, details, amount, term).
INCOMING = [
    (10, "Sponsorship / Donation", "CORPORATE WORKSHOP SPONSOR DEPOSIT", 300.00, "SP26"),
    (10, "Sponsorship / Donation", "CORPORATE CAREER NIGHT SPONSOR DEPOSIT", 450.00, "FA26"),
    (5, "Refunded", "VENUE DEPOSIT REFUND", 75.00, "SP26"),
    (9, "Refunded", "PRINT ORDER REFUND", 42.50, "FA26"),
    (16, "Sponsorship / Donation", "CULTURAL NIGHT SPONSOR DEPOSIT", 200.00, "FA26"),
]


def _describe(vendor: str, day: date, rng: random.Random) -> str:
    """A bank-statement-looking line with an invented reference number."""
    return (
        f"PURCHASE AUTHORIZED ON {day:%m/%d} {vendor} GAINESVILLE FL "
        f"S{rng.randint(100000, 999999)}"
    )


def _split(total: float, parts: int, rng: random.Random) -> list[float]:
    """`total` divided into `parts` uneven amounts that add up to it exactly."""
    weights = [rng.uniform(0.5, 1.5) for _ in range(parts)]
    scale = total / sum(weights)
    amounts = [round(weight * scale, 2) for weight in weights]
    amounts[-1] = round(total - sum(amounts[:-1]), 2)
    return amounts


def build_records(terms: dict[str, tuple[date, date]], budgets: dict, spent: dict) -> list[dict]:
    rng = random.Random(20261001)
    records: list[dict] = []

    for line, shares in TARGET_SHARE.items():
        for term_id in TERM_IDS:
            if term_id not in terms:
                continue
            budget = budgets.get((term_id, line))
            if not budget:
                continue
            needed = round(shares[term_id] * budget - spent.get((term_id, line), 0.0), 2)
            if needed < 20:
                continue

            start, end = terms[term_id]
            end = min(end, LATEST_DATA_DAY)
            window = max((end - start).days, 1)
            categories = SPENDING[line]

            for purpose, weight, vendors in categories:
                share = round(needed * weight, 2)
                if share < 5:
                    continue
                count = max(2, int(share // 55))
                for amount in _split(share, count, rng):
                    day = start + timedelta(days=rng.randint(0, window))
                    records.append(
                        {
                            "transaction_date": day.isoformat(),
                            "amount": -abs(amount),
                            "details": _describe(rng.choice(vendors), day, rng),
                            "budget_category": line,
                            "purpose": purpose,
                            "account": ACCOUNT_WELLS_FARGO,
                        }
                    )

    for line, purpose, details, amount, term_id in INCOMING:
        if term_id not in terms:
            continue
        start, end = terms[term_id]
        end = min(end, LATEST_DATA_DAY)
        day = start + timedelta(days=rng.randint(0, max((end - start).days, 1)))
        records.append(
            {
                "transaction_date": day.isoformat(),
                "amount": amount,
                "details": f"DEPOSIT {day:%m/%d} {details}",
                "budget_category": line,
                "purpose": purpose,
                "account": ACCOUNT_WELLS_FARGO,
            }
        )

    records.sort(key=lambda record: record["transaction_date"])
    return records


def main() -> int:
    if not settings.is_sandbox():
        print("Refusing to run: this adds fake data and only runs in the sandbox.")
        return 1

    backend = SqliteBackend()

    uploaded = backend.fetch_uploaded_files()
    if not uploaded.empty and FILE_NAME in set(uploaded["file_name"]):
        print(f"{FILE_NAME} is already loaded. Reset & reseed data first to start over.")
        return 0

    terms_frame = backend.fetch_terms()
    budgets_frame = backend.fetch_budgets()
    if terms_frame.empty or budgets_frame.empty:
        print("No terms or budgets yet. Start the app once so it seeds the sandbox, then run this.")
        return 1

    terms = {
        row["TermID"]: (date.fromisoformat(str(row["start_date"])[:10]), date.fromisoformat(str(row["end_date"])[:10]))
        for _, row in terms_frame.iterrows()
    }
    budgets = {
        (row["termid"], int(row["committeeid"])): float(row["budget_amount"] or 0)
        for _, row in budgets_frame.iterrows()
    }

    # What each line has already spent per term, so targets top up, never double up.
    spent: dict[tuple[str, int], float] = {}
    transactions = backend.fetch_transactions()
    for _, row in transactions.iterrows():
        if row["amount"] >= 0 or pd.isna(row["budget_category"]):
            continue
        day = row["transaction_date"].date()
        for term_id, (start, end) in terms.items():
            if start <= day <= end:
                key = (term_id, int(row["budget_category"]))
                spent[key] = spent.get(key, 0.0) + abs(float(row["amount"]))
                break

    records = assign_natural_keys(build_records(terms, budgets, spent))
    receipt = backend.insert_transactions(records, FILE_NAME, ACTOR)
    if not receipt.ok:
        print(f"Could not load the demo data: {receipt.error}")
        return 1

    print(f"Added {receipt.inserted} fake transactions ({receipt.duplicates_skipped} duplicates skipped).")
    for line in TARGET_SHARE:
        added = sum(1 for record in records if record["budget_category"] == line)
        print(f"  {committee_name(line):<26} +{added} rows")
    print("Restart Streamlit to see them straight away.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
