"""
Categorization orchestration.

The order is the whole point:

    1. The card roster  -- a purchase on a card treasury has confirmed for the
                           current officer cohort is that card's committee.
                           Outranks everything (treasury ruling, 2026-09-23).
    2. Exact rules      -- unambiguous markers: exact dues amount, a memo, the
                           sign of a transfer. Certainties.
    3. Scoring          -- keyword, weekday and amount evidence, gated on
                           confidence; the uncertain rest goes to a human
    4. The model        -- only what is genuinely left over

The original ran the model *first*, over every transaction, and then overrode
most of its answers with Python rules -- paying for answers it discarded. This
inverts that.

MERCHANT MEMORY IS GONE (2026-09-23). A tier between 2 and 3 used to book a
merchant the way a human had filed it before. Treasury ruled it out: the same
merchant serves too many committees -- Consulting food and Meeting Food
especially come from the same restaurants -- for its history to predict the
next purchase, and a remembered merchant was able to override the card, which
is the one piece of evidence that actually says whose spending it was. What a
treasurer decides in the Review Queue is still logged as a label (for the
spot-check and evaluation tools); it just no longer turns into a rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .llm import LLMOutcome, classify_residual
from .predicates import (
    UNMATCHED,
    Classification,
    DuesSchedule,
    exact_rules,
    first_match,
)
from .scoring import AUTO_APPLY_THRESHOLD, CardRegistry, ScoredResult, score


@dataclass
class CategorizationRun:
    """Results plus the accounting needed to show what the run cost."""

    classifications: list[Classification] = field(default_factory=list)
    llm: LLMOutcome = field(default_factory=LLMOutcome)
    # Scored results by row position, including ones held back as too uncertain
    # to apply. The review queue reads these to show its reasoning.
    proposals: dict[int, ScoredResult] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.classifications)

    @property
    def counts_by_source(self) -> dict[str, int]:
        counts = {"rule": 0, "scored": 0, "llm": 0, "none": 0}
        for item in self.classifications:
            counts[item.source] = counts.get(item.source, 0) + 1
        return counts

    @property
    def held_for_review(self) -> dict[int, ScoredResult]:
        """Scored proposals that did not clear the threshold — the flagged outliers."""
        return {
            index: scored
            for index, scored in self.proposals.items()
            if not self.classifications[index].is_assigned
        }

    @property
    def assigned(self) -> int:
        return sum(1 for item in self.classifications if item.is_assigned)

    @property
    def coverage(self) -> float:
        return (self.assigned / self.total * 100) if self.total else 0.0

    @property
    def rows_sent_to_model(self) -> int:
        return self.counts_by_source["none"] + self.counts_by_source["llm"]

    @property
    def rows_resolved_locally(self) -> int:
        return self.counts_by_source["rule"]

    def summary_line(self) -> str:
        counts = self.counts_by_source
        return (
            f"{self.total} transactions: {counts['rule']} by exact rule, "
            f"{counts['scored']} by scoring, {counts['llm']} by model, "
            f"{counts['none']} left for review "
            f"({len(self.held_for_review)} of those carry a proposal)."
        )


def categorize_records(
    records: list[dict],
    *,
    cards: CardRegistry | None = None,
    dues: DuesSchedule | None = None,
    threshold: float = AUTO_APPLY_THRESHOLD,
) -> CategorizationRun:
    """
    Classify a list of transaction dicts.

    A scored result is only accepted when its confidence clears `threshold`;
    below that it is kept as a *proposal* -- committee, confidence and evidence
    intact -- and the row goes to the review queue rather than being booked on a
    coin-flip. `run.proposals` carries those so the queue can show its
    reasoning instead of an empty cell.

    `dues` supplies per-term dues rates. Omitted, `rule_dues` falls back to the
    Fall 2024 constant it always used -- see `predicates.DuesSchedule`.
    """
    registry = cards or CardRegistry()
    # Bound once, not per row: `exact_rules` builds a partial when a schedule is
    # supplied, and this loop runs 892 times on the real table.
    rules = exact_rules(dues)
    results: list[Classification] = [UNMATCHED] * len(records)
    proposals: dict[int, ScoredResult] = {}
    residual: list[tuple[int, dict]] = []

    for index, record in enumerate(records):
        # The card first. A confirmed card in its cohort's dates says whose
        # spending this was, and nothing below -- merchant, weekday, amount --
        # is allowed to argue with it.
        carded = registry.certain(record)
        if carded is not None:
            results[index] = carded
            continue

        # Certainties: an exact dues amount, a memo, a transfer's sign.
        exact = first_match(record, rules)
        if exact.is_assigned:
            results[index] = exact
            continue

        # An unassigned result that still carries a rule string is a *hint*: the
        # rules recognised what kind of row this is without being able to name a
        # committee. `rule_reimbursement` is the case that matters -- an outgoing
        # transfer is now a question rather than an automatic booking to
        # Refunded, and the review queue reads `match_rule` to phrase it. Keep it
        # as the fallback and carry on: scoring may still find a real answer.
        if exact.rule:
            results[index] = exact

        scored = score(record, cards=registry)
        if scored.winner is not None:
            proposals[index] = scored
            if scored.confidence >= threshold:
                results[index] = scored.as_classification()
                continue

        # Unscored, or scored too close to call: a human or the model decides.
        residual.append((index, record))

    outcome = classify_residual(residual)
    for index, classification in outcome.classifications.items():
        results[index] = classification

    return CategorizationRun(classifications=results, llm=outcome, proposals=proposals)


def categorize_frame(
    df: pd.DataFrame,
    *,
    dues: DuesSchedule | None = None,
) -> tuple[pd.DataFrame, CategorizationRun]:
    """
    Categorize a parsed statement frame.

    Adds: budget_category, purpose, match_rule, match_confidence, match_source.

    FINDING F18 (fragility). The original realigned results with
    `df.loc[mask, col] = enhanced.loc[mask, col].values`, which was correct only
    because an upstream reset_index happened to leave the frames aligned. Results
    are built as plain lists indexed by position and assigned once, so there is
    no alignment to get wrong.
    """
    out = df.reset_index(drop=True).copy()
    if out.empty:
        for column in ("budget_category", "purpose", "match_rule", "match_confidence", "match_source"):
            out[column] = pd.Series(dtype="object")
        return out, CategorizationRun()

    records = out.to_dict("records")
    run = categorize_records(records, dues=dues)

    out["budget_category"] = [item.committee_id for item in run.classifications]
    out["purpose"] = [item.purpose for item in run.classifications]
    out["match_rule"] = [item.rule for item in run.classifications]
    out["match_confidence"] = [item.confidence for item in run.classifications]
    out["match_source"] = [item.source for item in run.classifications]
    return out, run
