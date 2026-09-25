-- ===========================================================================
-- Migration 005 -- record how many rows each spot-check stands for.
--
-- RUN AFTER 001 (which creates `labeled_examples`). Independent of 002-004.
--
-- WHY. The spot-check sample is skewed on purpose: every committee gets at
-- least one row however rare it is, and each committee's largest amounts are
-- picked deliberately rather than at random. That makes it good at finding
-- mistakes and bad at measuring accuracy -- the raw share of checked rows the
-- categorizer got right over-counts rare committees and large amounts.
--
-- `sample_weight` is how many auto-applied rows a checked row stands for: 1 for
-- a deliberately-picked large amount, (rows left in its stratum) / (random
-- picks) for a random one. `spotcheck.agreement` uses it to turn the sample
-- back into an estimate of accuracy across every auto-applied row, with a
-- margin of error. See `domain/categorize/spotcheck.py`.
--
-- ADDITIVE AND REVERSIBLE. One nullable column. NULL means "recorded before
-- weights existed" (or not a spot-check at all); those rows still count towards
-- the raw agreement figure and are left out of the weighted one.
--
--   Undo:  ALTER TABLE public.labeled_examples DROP COLUMN sample_weight;
-- ===========================================================================

ALTER TABLE public.labeled_examples
    ADD COLUMN IF NOT EXISTS sample_weight double precision;

COMMENT ON COLUMN public.labeled_examples.sample_weight IS
    'Spot-checks only: how many auto-applied rows this checked row stands for. '
    'NULL for other labels and for spot-checks recorded before weights existed.';
