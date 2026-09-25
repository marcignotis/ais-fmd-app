"""
Give every existing transaction the fingerprint deduplication depends on.

WHY THIS IS NEEDED BEFORE ANY HISTORICAL UPLOAD.

`transactions.natural_key` is the deduplication identity: a hash of date,
amount, normalised description, account, and an occurrence ordinal that
distinguishes two genuinely identical same-day purchases. Migration 001 adds the
column and a **partial** unique index over it:

    CREATE UNIQUE INDEX ... ON transactions (natural_key) WHERE natural_key IS NOT NULL

The partial clause is what lets the migration be additive -- existing rows,
which have no key, do not collide with each other. The cost is that those rows
participate in no deduplication at all. Re-uploading a statement they came from
inserts every row a second time, silently, and the ledger's totals double for
that period.

This script computes the key each existing row would have been given and writes
it back. Run once, after migration 001, before uploading anything historical.

    # see what would change, write nothing (default)
    python scripts/prod/backfill_natural_keys.py

    # actually write
    python scripts/prod/backfill_natural_keys.py --apply

    # against the sandbox instead of production
    python scripts/prod/backfill_natural_keys.py --sandbox --apply

WHAT IT WILL NOT DO
  * It never touches amount, date, description, account, committee or purpose.
    The only column written is `natural_key`.
  * It never overwrites a key that is already set. Re-running is a no-op.
  * It refuses to write anything if two rows would be given the same key, since
    that means the ordinal assignment is wrong and writing it would make a real
    future transaction look like a duplicate. That is the one failure mode here
    that actually costs you data, so it is a hard stop rather than a warning.

ORDERING IS THE WHOLE PROBLEM. `assign_natural_keys` numbers identical rows
0, 1, 2... in the order it sees them, and a future re-upload numbers them the
same way *within that file*. So the ordinals only line up if this script walks
the existing rows in the order the statement did. Rows are therefore sorted by
(date, then transactionid) -- transactionid being insertion order, which for an
imported statement is file order. Where that assumption cannot hold the
collision check above catches it.

CREDENTIALS are read exactly as `inspect_supabase.py` reads them; see that file.
The service/secret key is required, because this writes.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "prod"))

from ais_fmd.domain.dedupe import assign_natural_keys  # noqa: E402

PAGE = 1000


# --- Supabase (production) ---------------------------------------------------

def _write_credentials() -> tuple[str, str]:
    """
    (url, key) with a key that can write.

    Deliberately separate from `inspect_supabase.load_credentials`, which
    prefers the read-only publishable key. A backfill needs the secret key --
    and asking for it explicitly, rather than silently falling back, means you
    always know which key a run used.
    """
    import os
    import tomllib

    url = key = ""
    secrets_path = REPO_ROOT / ".streamlit" / "secrets.toml"
    if secrets_path.exists():
        with secrets_path.open("rb") as handle:
            section = tomllib.load(handle).get("supabase", {})
        url = str(section.get("url", "")).strip()
        for name in ("secret_key", "service_key", "SUPABASE_SERVICE_KEY"):
            value = str(section.get(name, "") or "").strip()
            if value:
                key = value
                break

    url = url or os.environ.get("SUPABASE_URL", "").strip()
    key = key or os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

    if not (url and key):
        raise SystemExit(
            "No Supabase write credentials found.\n\n"
            "This script writes, so it needs the secret key, not the publishable one.\n"
            "Add it to .streamlit/secrets.toml (gitignored):\n\n"
            "    [supabase]\n"
            '    url = "https://<your-ref>.supabase.co"\n'
            '    secret_key = "sb_secret_..."\n'
        )
    return url.rstrip("/"), key


def _request(url: str, key: str, path: str, *, params=None, method="GET", body=None,
             extra_headers=None):
    query = urllib.parse.urlencode(params or {})
    request = urllib.request.Request(
        f"{url}/rest/v1/{path}" + (f"?{query}" if query else ""),
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
    )
    request.add_header("apikey", key)
    request.add_header("Authorization", f"Bearer {key}")
    request.add_header("Content-Type", "application/json")
    for name, value in (extra_headers or {}).items():
        request.add_header(name, value)
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read().decode()
    return json.loads(payload) if payload.strip() else []


def _fetch_supabase(url: str, key: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        batch = _request(
            url, key, "transactions",
            params={
                "select": "transactionid,transaction_date,amount,details,account,natural_key",
                "order": "transaction_date.asc,transactionid.asc",
                "limit": PAGE,
                "offset": offset,
            },
        )
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        offset += PAGE


def _write_supabase(url: str, key: str, updates: list[tuple[int, str]]) -> int:
    written = 0
    for transaction_id, natural_key in updates:
        _request(
            url, key, "transactions",
            params={"transactionid": f"eq.{transaction_id}"},
            method="PATCH",
            body={"natural_key": natural_key},
            extra_headers={"Prefer": "return=minimal"},
        )
        written += 1
        if written % 200 == 0:
            print(f"    {written:,} / {len(updates):,}...", flush=True)
    return written


# --- SQLite (sandbox) --------------------------------------------------------

def _fetch_sqlite() -> list[dict]:
    import sqlite3

    from ais_fmd import settings

    connection = sqlite3.connect(settings.sandbox_db_path())
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT transactionid, transaction_date, amount, details, account, natural_key "
            "FROM transactions ORDER BY transaction_date ASC, transactionid ASC"
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def _write_sqlite(updates: list[tuple[int, str]]) -> int:
    import sqlite3

    from ais_fmd import settings

    connection = sqlite3.connect(settings.sandbox_db_path())
    try:
        connection.executemany(
            "UPDATE transactions SET natural_key = ? WHERE transactionid = ?",
            [(key, tid) for tid, key in updates],
        )
        connection.commit()
    finally:
        connection.close()
    return len(updates)


# --- The work ----------------------------------------------------------------

def plan(rows: list[dict]) -> tuple[list[tuple[int, str]], list[str], dict]:
    """
    (updates, problems, summary).

    `updates` is only ever rows whose key is currently empty. Rows that already
    have one are counted and left alone -- re-running must never rewrite a key,
    because a changed key is a row that stops matching its own past.
    """
    keyed = assign_natural_keys(
        [
            {
                "transaction_date": row.get("transaction_date"),
                "amount": row.get("amount"),
                "details": row.get("details"),
                "account": row.get("account"),
            }
            for row in rows
        ]
    )

    updates: list[tuple[int, str]] = []
    already = 0
    for row, computed in zip(rows, keyed):
        existing = str(row.get("natural_key") or "").strip()
        if existing:
            already += 1
            continue
        updates.append((int(row["transactionid"]), computed["natural_key"]))

    problems: list[str] = []

    # Every key this run would write must be unique, and must not collide with a
    # key already stored. Either would make a genuine future transaction look
    # like a duplicate and be silently dropped on import -- the one outcome here
    # that loses real data.
    counts = Counter(key for _, key in updates)
    for key, count in counts.items():
        if count > 1:
            offenders = [str(tid) for tid, k in updates if k == key][:6]
            problems.append(
                f"{count} rows would share the key {key[:16]}... "
                f"(transactionids {', '.join(offenders)})"
            )
    stored = {str(row.get("natural_key") or "").strip() for row in rows} - {""}
    for key in counts:
        if key in stored:
            problems.append(f"key {key[:16]}... already exists on another row")

    return updates, problems, {
        "total": len(rows),
        "already_keyed": already,
        "to_write": len(updates),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    parser.add_argument("--sandbox", action="store_true", help="target the local SQLite file")
    args = parser.parse_args()

    if args.sandbox:
        print("Target: local SQLite sandbox\n")
        rows = _fetch_sqlite()
    else:
        url, key = _write_credentials()
        print(f"Target: {url}\n")
        rows = _fetch_supabase(url, key)

    if not rows:
        print("No transactions found. Nothing to do.")
        return 0

    updates, problems, summary = plan(rows)

    print(f"  transactions          {summary['total']:,}")
    print(f"  already fingerprinted {summary['already_keyed']:,}")
    print(f"  would be written      {summary['to_write']:,}")
    print()

    if problems:
        print("REFUSING TO WRITE -- the computed keys are not unique.\n")
        for problem in problems[:10]:
            print(f"  {problem}")
        if len(problems) > 10:
            print(f"  ... and {len(problems) - 10} more")
        print(
            "\nA duplicate key would make a real future transaction look like a\n"
            "duplicate and be dropped on import. Work out why the ordinals collide\n"
            "before running this again -- the likely cause is that the row order\n"
            "here differs from the order the original statement was imported in."
        )
        return 1

    if not updates:
        print("Every transaction already has a fingerprint. Nothing to do.")
        return 0

    if not args.apply:
        print("Dry run. Sample of what would be written:\n")
        for transaction_id, natural_key in updates[:5]:
            print(f"  transactionid {transaction_id:<8} -> {natural_key}")
        print(f"\nRe-run with --apply to write {len(updates):,} key(s).")
        return 0

    print(f"Writing {len(updates):,} key(s)...")
    written = _write_sqlite(updates) if args.sandbox else _write_supabase(url, key, updates)
    print(f"\nDone. {written:,} transaction(s) now carry a fingerprint.")
    print("Re-uploading a statement these rows came from will now be a no-op.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
