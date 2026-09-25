-- ===========================================================================
-- NO LONGER NEEDED (2026-09-23): treasury ruled merchant memory out of
-- categorization, so nothing reads `committee_counts` any more. Safe to skip.
--
-- Migration 004 -- record what a merchant has ACTUALLY been filed as, not just
-- what it was filed as most recently.
--
-- RUN AFTER 001 (which creates `merchants`). Independent of 002 and 003.
--
-- WHY. `merchants` stored one `committee_id` per merchant, and the categorizer
-- applied it at 0.95 confidence, short-circuiting every other signal. That is
-- correct for a merchant which only ever means one thing -- a website host is
-- always Technology, a print shop is always Merch -- and wrong for one that
-- legitimately spans committees. A bar can be a Membership social, a Consulting
-- client dinner, or a Professional Development event, and a single stored answer
-- cannot say so: whichever committee was confirmed last silently won every
-- future transaction from that merchant, erasing every earlier decision.
--
-- The project's own measurements are what made this concrete. `salty dog saloon`
-- is settled as **Consulting** across 10 human decisions, while the hardcoded
-- "bar merchant -> Membership" scoring signal measured 38% precision and, fitted
-- against real labels, earned a weight of exactly 0.00. That signal has been
-- removed; this column is what replaces it with evidence.
--
-- `committee_counts` holds the whole distribution as a compact string,
-- "5:3,7:7" -- the same encoding `members.alt_keys` already uses for its list,
-- rather than a join table for what is at most a handful of integers per row.
-- `committee_id` is kept and now holds the *dominant* reading, so anything still
-- reading that column sees a merchant's most common committee instead of its
-- most recent one.
--
-- ADDITIVE AND REVERSIBLE. One nullable column. A NULL means "no distribution
-- recorded", which `MerchantRule.decisions` reads as a single decision for the
-- stored `committee_id` -- so rows written before this migration keep behaving
-- exactly as they did. Nothing is dropped, retyped, or backfilled destructively.
-- ===========================================================================

BEGIN;

ALTER TABLE public.merchants
    ADD COLUMN IF NOT EXISTS committee_counts text;

COMMENT ON COLUMN public.merchants.committee_counts IS
    'Committee decision distribution for this merchant, "id:count" pairs joined '
    'by commas (e.g. "5:3,7:7"). NULL means no distribution recorded, which is '
    'read as one decision for committee_id. Written by '
    'domain.categorize.merchants.MerchantMemory.';

COMMIT;

-- ===========================================================================
-- OPTIONAL BACKFILL -- run only after `labeled_examples` has real content.
--
-- `labeled_examples` records every review-queue decision with the original
-- description and the committee the human chose, so the true distribution can be
-- derived from what actually happened rather than from the denormalised counter.
-- That is the honest source; `merchants` is the cache.
--
-- Deliberately NOT run automatically, and left commented out, for two reasons:
-- deriving a merchant key from a raw description is done by
-- `domain.categorize.merchants.merchant_key`, which strips card numbers, store
-- numbers, reference codes and trailing state codes in a specific order that SQL
-- would have to duplicate and could drift from; and on a database where
-- `labeled_examples` is empty this would overwrite good counters with nothing.
--
-- Use `MerchantMemory.from_labels(...)` from Python instead, which calls the
-- real `merchant_key`. This block is kept only to record that the data is there
-- and where it lives.
-- ===========================================================================

-- SELECT count(*) AS decisions_available FROM public.labeled_examples;
