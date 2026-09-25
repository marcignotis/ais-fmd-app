"""
Static guards for the class of bug a fully green suite kept missing.

Every one of these was found by reading, not by a failing test, and the reason
is the same in each case: `tests/test_views.py` renders each page in three
scenarios, but nothing drives a *write* through the widgets. A line that only
executes after a button is pressed is, as far as the suite is concerned, not
executed at all -- so a wrong argument count or a rebound variable on that line
runs for the first time in front of a treasurer.

Driving every write path headlessly is the real fix (HANDOFF.md §8.2, P9) and
is a much larger job. These are the cheap half: parse the view files and check
the shapes that went wrong, so the specific mistakes cannot recur silently while
that work is outstanding.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from ais_fmd.ui import shell

VIEWS = sorted((Path(__file__).resolve().parent.parent / "ais_fmd" / "views").glob("*.py"))
VIEW_IDS = [path.name for path in VIEWS]


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# --- The Treasury.py crash ----------------------------------------------------
#
# `shell.notify(f"{rate_term} already had those rates.")` -- one argument to a
# two-argument function. TypeError, blanking the page, on the "you saved dues
# rates that had not changed" path. 22 other call sites were correct.

_SHELL_ARITY = {
    "notify": 2,     # (kind, text)
    "pill": 1,       # (label, kind="muted")
    "say": 1,        # (text, *, caption=False)
    "empty_state": 1,
    "error_state": 1,
    "page_header": 1,
    "money_safe": 1,
}


@pytest.mark.parametrize("path", VIEWS, ids=VIEW_IDS)
def test_shell_helpers_are_called_with_enough_positional_arguments(path: Path) -> None:
    offenders: list[str] = []
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
            continue
        if func.value.id != "shell":
            continue
        required = _SHELL_ARITY.get(func.attr)
        if required is None:
            continue
        # A *args splat could supply any number; don't guess.
        if any(isinstance(arg, ast.Starred) for arg in node.args):
            continue
        supplied = len(node.args) + len(node.keywords)
        if supplied < required:
            offenders.append(
                f"{path.name}:{node.lineno} shell.{func.attr}() got {supplied} "
                f"argument(s), needs {required}"
            )

    assert not offenders, (
        "A shell helper is called with too few arguments, which is a TypeError "
        "at render time:\n  " + "\n  ".join(offenders)
    )


def test_shell_arity_table_matches_the_real_signatures() -> None:
    """
    The guard above is only as good as its table, so pin the table to reality.

    Without this, adding a required parameter to `shell.notify` would leave the
    check silently asserting the old arity.
    """
    for name, expected in _SHELL_ARITY.items():
        function = getattr(shell, name)
        parameters = inspect.signature(function).parameters.values()
        required = sum(
            1
            for parameter in parameters
            if parameter.default is inspect.Parameter.empty
            and parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )
        assert required == expected, (
            f"shell.{name} now takes {required} required positional argument(s), "
            f"not {expected}. Update _SHELL_ARITY."
        )


# --- The Roster.py crash ------------------------------------------------------
#
# `result` held the page's reconciliation object; a button handler rebound it to
# an UpdateResult. On success `st.rerun()` hid it, but on the failure path the
# script carried on into the next tab and raised AttributeError on an object of
# the wrong type. Views are exec'd as flat scripts, so every assignment is a
# module-level rebind and this is easy to do by accident.

# Names whose meaning is established once near the top of a view and relied on
# far below. Rebinding one inside a conditional or a loop is the bug.
_LOAD_BEARING_NAMES = {"result", "bundle", "identity", "terms", "semesters", "summary"}


@pytest.mark.parametrize("path", VIEWS, ids=VIEW_IDS)
def test_load_bearing_names_are_not_rebound_inside_a_branch(path: Path) -> None:
    tree = _tree(path)

    top_level: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    top_level.add(target.id)

    watched = top_level & _LOAD_BEARING_NAMES
    if not watched:
        pytest.skip(f"{path.name} establishes none of the watched names at module level")

    offenders: list[str] = []
    for node in tree.body:
        # Only descend into module-level control flow: a rebind inside a nested
        # function has its own scope and cannot clobber the outer name.
        if not isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Assign):
                continue
            # `summary = summary[summary["x"] == y]` narrows a value in place and
            # keeps its type. That is the ordinary pandas filter idiom and is
            # exactly what Dashboard.py does; it is not the bug. The bug is
            # rebinding the name to something *unrelated*, which is what makes
            # every line below read an object of the wrong type. Reading the old
            # value on the right-hand side is the signal that separates them.
            reads_itself = {
                child.id for child in ast.walk(inner.value) if isinstance(child, ast.Name)
            }
            for target in inner.targets:
                if not (isinstance(target, ast.Name) and target.id in watched):
                    continue
                if target.id in reads_itself:
                    continue
                offenders.append(f"{path.name}:{inner.lineno} rebinds `{target.id}`")

    assert not offenders, (
        "A name established at the top of the view is rebound inside a branch. "
        "Views are exec'd as flat scripts, so this overwrites the value every "
        "line below still reads -- Roster.py did exactly this and turned a "
        "failed save into an AttributeError two tabs later. Use a distinct "
        "name:\n  " + "\n  ".join(offenders)
    )
