"""
Which pages a signed-in person can navigate to.

A VP (an Officer, see `Identity.committee_scoped`) gets exactly three pages:
the org-wide Home for context, their own committee's dashboard, and their own
committee's transactions. Everything else -- including pages that are open to
any role, like the org-wide Dashboard and Transactions -- is left out of their
navigation, and Streamlit only serves pages that are in the navigation, so a
page that is not listed cannot be reached by typing its URL either.

Kept out of `app.py` so it can be tested without running the whole app, and so
edits to the full `PAGES` list there do not conflict with edits here.
"""

from __future__ import annotations

from .auth import Identity, Role

DASHBOARD_PATH = "ais_fmd/views/Dashboard.py"
MY_COMMITTEE_PATH = "ais_fmd/views/Officer.py"

# (path, title, icon, minimum role) -- the same shape as `PAGES` in app.py.
VP_PAGES: list[tuple[str, str, str, Role]] = [
    ("ais_fmd/views/Home.py", "Home", ":material/home:", Role.MEMBER),
    ("ais_fmd/views/Officer.py", "My Committee", ":material/badge:", Role.OFFICER),
    ("ais_fmd/views/MyTransactions.py", "My Transactions", ":material/table_rows:", Role.OFFICER),
]


def visible_pages(
    identity: Identity, pages: list[tuple[str, str, str, Role]]
) -> list[tuple[str, str, str, Role]]:
    """The pages `identity` may see: the VP set for a VP, else `pages` filtered by role."""
    source = VP_PAGES if identity.committee_scoped else pages
    visible = [page for page in source if identity.can(page[3])]
    if identity.read_only:
        visible = _my_committee_after_dashboard(visible)
    return visible


def _my_committee_after_dashboard(
    pages: list[tuple[str, str, str, Role]],
) -> list[tuple[str, str, str, Role]]:
    """
    The President's own budget is the first thing they look at after the org-wide
    Dashboard, so My Committee sits directly under it. Only the order changes.
    """
    mine = [page for page in pages if page[0] == MY_COMMITTEE_PATH]
    dashboard = [i for i, page in enumerate(pages) if page[0] == DASHBOARD_PATH]
    if not mine or not dashboard:
        return pages
    rest = [page for page in pages if page[0] != MY_COMMITTEE_PATH]
    at = next(i for i, page in enumerate(rest) if page[0] == DASHBOARD_PATH) + 1
    return rest[:at] + mine + rest[at:]
