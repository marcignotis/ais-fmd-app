-- ===========================================================================
-- Migration 003 -- make closing a term actually close it, in production.
--
-- WHY THIS EXISTS. Period locking (M10) was implemented only in
-- `sqlite_backend.py`, which checks `_locked_ranges()` before both imports and
-- edits. Neither Postgres RPC read `terms.locked` at all, so in production the
-- control did nothing -- while the Treasury page told the treasurer, in as many
-- words: "The check lives in the data layer, so no page can bypass it."
--
-- A control that is believed and does not hold is worse than one that is known
-- to be absent, because it is relied on. A closed term is what stops a later
-- edit silently changing a figure that has already been reported to the board.
--
-- RUN AFTER 001. This depends on `terms.locked`, which migration 001 adds. It
-- does not depend on 002 and does not care whether 002 has run.
--
-- This migration replaces both RPCs. It is safe to re-run: every statement is
-- CREATE OR REPLACE, and the semantics of an unlocked term are byte-for-byte
-- what they were before.
--
-- `apply_transaction_edits` gains two return columns, so it must be DROPped
-- rather than replaced in place -- CREATE OR REPLACE cannot change a function's
-- return type. `supabase_backend.update_transactions` reads the new columns
-- with `.get(..., 0)`, so a database still on the old two-column version keeps
-- working rather than raising; deploy order between the two does not matter.
--
-- ALSO FIXED HERE, because these functions are being rewritten anyway: all
-- three definer functions gain `SET search_path = public, pg_temp`. Without it
-- a SECURITY DEFINER function resolves unqualified names against the caller's
-- search_path, which is the classic privilege-escalation shape and is what
-- Supabase's own database linter flags as `function_search_path_mutable`.
-- Adding it changes no behaviour.
--
-- NOT fixed here, and still outstanding -- see the launch audit:
--   * both RPCs are still executable by `anon` (needs REVOKE)
--   * no table has row-level security enabled
-- Those are a deliberate, separate decision and belong in their own migration.
--
-- NEVER RUN AGAINST REAL POSTGRES. Like everything in this directory, this has
-- been written and reviewed but not executed. Run it on a throwaway project
-- first and exercise an import and an edit against both a locked and an
-- unlocked term.
-- ===========================================================================

BEGIN;

-- --- The lock predicate, in one place ---------------------------------------
--
-- Mirrors `SqliteBackend._locked_term_for`: the locked term a date falls
-- inside, or NULL. Both bounds inclusive, matching the SQLite string
-- comparison `start <= stamp <= end`. Terms are few and the index on
-- transaction_date is not involved, so a sequential scan of `terms` is
-- correct and cheap.
--
-- STABLE, not IMMUTABLE: it reads a table, and a term can be reopened inside
-- the same transaction that later inserts into it.

CREATE OR REPLACE FUNCTION public.locked_term_for(p_date date)
RETURNS text
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT t."Semester"
      FROM public.terms t
     WHERE t.locked
       AND p_date IS NOT NULL
       AND p_date BETWEEN t.start_date AND t.end_date
     ORDER BY t.start_date
     LIMIT 1;
$$;


-- --- FINDING F4 + M10: atomic statement import, honouring closed terms ------
--
-- Unchanged from 002 except for the lock check and search_path.
--
-- The whole batch is refused if ANY row lands in a closed period, rather than
-- the offending rows being filtered out. That is deliberate and matches
-- `sqlite_backend.insert_transactions`: a partial import silently drops rows
-- the treasurer believes were loaded, and leaves the statement marker
-- disagreeing with the ledger. RAISE rolls back the whole function.

CREATE OR REPLACE FUNCTION public.import_statement(
    p_records   jsonb,
    p_file_name text,
    p_actor     text
)
RETURNS TABLE (inserted integer, skipped integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_inserted integer := 0;
    v_total    integer := 0;
    v_id       integer;
    v_row      jsonb;
    v_blocked  text;
BEGIN
    -- M10: check every row before writing any of them.
    SELECT string_agg(DISTINCT term, ', ' ORDER BY term)
      INTO v_blocked
      FROM (
          SELECT public.locked_term_for((r ->> 'transaction_date')::date) AS term
            FROM jsonb_array_elements(p_records) AS r
      ) candidates
     WHERE term IS NOT NULL;

    IF v_blocked IS NOT NULL THEN
        RAISE EXCEPTION
            '% is closed. Reopen the term on the Treasury page to import transactions dated inside it.',
            v_blocked
            USING ERRCODE = 'raise_exception';
    END IF;

    FOR v_row IN SELECT * FROM jsonb_array_elements(p_records)
    LOOP
        v_total := v_total + 1;

        INSERT INTO public.transactions
            (transaction_date, amount, details, budget_category,
             purpose, account, source_file, natural_key)
        VALUES (
            (v_row ->> 'transaction_date')::date,
            (v_row ->> 'amount')::numeric,
             v_row ->> 'details',
            NULLIF(v_row ->> 'budget_category', '')::integer,
            NULLIF(v_row ->> 'purpose', ''),
             v_row ->> 'account',
            p_file_name,
             v_row ->> 'natural_key'
        )
        ON CONFLICT (natural_key) WHERE natural_key IS NOT NULL DO NOTHING
        RETURNING transactionid INTO v_id;

        IF v_id IS NOT NULL THEN
            v_inserted := v_inserted + 1;
            INSERT INTO public.transaction_audit
                (transaction_id, action, new_value, actor)
            VALUES (v_id, 'insert', v_row ->> 'details', p_actor);
        END IF;
    END LOOP;

    INSERT INTO public.uploaded_files (file_name, row_count, uploaded_by)
    VALUES (p_file_name, v_inserted, p_actor)
    ON CONFLICT (file_name) DO UPDATE
        SET row_count = EXCLUDED.row_count,
            uploaded_at = now();

    RETURN QUERY SELECT v_inserted, v_total - v_inserted;
END;
$$;


-- --- FINDING F6 + M10: batched edits, honouring closed terms ----------------
--
-- Returns a third column, `blocked`, and skips those rows rather than refusing
-- the batch. This also matches `sqlite_backend.update_transactions`, and the
-- asymmetry with `import_statement` above is intentional: an import is one
-- document that must land whole, whereas an edit batch is a set of independent
-- decisions and applying the fifteen that are allowed is more useful than
-- refusing all sixteen. `blocked_terms` names what to reopen.

DROP FUNCTION IF EXISTS public.apply_transaction_edits(jsonb, text);

CREATE OR REPLACE FUNCTION public.apply_transaction_edits(
    p_changes jsonb,
    p_actor   text
)
RETURNS TABLE (updated integer, unchanged integer, blocked integer, blocked_terms text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_updated   integer := 0;
    v_unchanged integer := 0;
    v_blocked   integer := 0;
    v_terms     text[]  := ARRAY[]::text[];
    v_closed    text;
    v_row       jsonb;
    v_id        integer;
    v_purpose   text;
    v_committee integer;
    v_old       record;
BEGIN
    FOR v_row IN SELECT * FROM jsonb_array_elements(p_changes)
    LOOP
        v_id        := (v_row ->> 'transactionid')::integer;
        v_purpose   := NULLIF(v_row ->> 'purpose', '');
        v_committee := NULLIF(v_row ->> 'budget_category', '')::integer;

        SELECT purpose, budget_category, transaction_date INTO v_old
        FROM public.transactions WHERE transactionid = v_id;

        IF NOT FOUND THEN
            CONTINUE;
        END IF;

        -- M10: a closed period is read-only.
        v_closed := public.locked_term_for(v_old.transaction_date);
        IF v_closed IS NOT NULL THEN
            v_blocked := v_blocked + 1;
            IF NOT (v_closed = ANY (v_terms)) THEN
                v_terms := array_append(v_terms, v_closed);
            END IF;
            CONTINUE;
        END IF;

        IF v_old.purpose IS NOT DISTINCT FROM v_purpose
           AND v_old.budget_category IS NOT DISTINCT FROM v_committee THEN
            v_unchanged := v_unchanged + 1;
            CONTINUE;
        END IF;

        UPDATE public.transactions
           SET purpose = v_purpose, budget_category = v_committee
         WHERE transactionid = v_id;

        IF v_old.purpose IS DISTINCT FROM v_purpose THEN
            INSERT INTO public.transaction_audit
                (transaction_id, action, field, old_value, new_value, actor)
            VALUES (v_id, 'update', 'purpose', v_old.purpose, v_purpose, p_actor);
        END IF;

        IF v_old.budget_category IS DISTINCT FROM v_committee THEN
            INSERT INTO public.transaction_audit
                (transaction_id, action, field, old_value, new_value, actor)
            VALUES (v_id, 'update', 'budget_category',
                    v_old.budget_category::text, v_committee::text, p_actor);
        END IF;

        v_updated := v_updated + 1;
    END LOOP;

    RETURN QUERY SELECT
        v_updated,
        v_unchanged,
        v_blocked,
        array_to_string(v_terms, ', ');
END;
$$;


COMMIT;

-- ===========================================================================
-- DELIBERATELY NOT TOUCHED HERE: public.current_role_rank()
--
-- It is the third SECURITY DEFINER function and it also lacks `search_path`,
-- so it looks like it belongs in this migration. It does not, for two reasons
-- worth writing down rather than rediscovering:
--
--   1. It is unreachable. Its only callers are the RLS policies in
--      schema_postgres.sql, none of which are enabled in this deployment.
--
--   2. It would not compile against the current schema anyway. It selects
--      `FROM public.profiles WHERE user_id = auth.uid()`, but migration 002
--      redefined `profiles` to be keyed on `email` with no `user_id` column at
--      all -- the deliberate pivot to Streamlit's own OIDC login, documented at
--      the top of that table's definition.
--
-- Fixing it means first deciding how a verified caller identity reaches the
-- Postgres session, which under the current architecture it never does. That is
-- a design decision, not a migration, and guessing at one here would leave a
-- plausible-looking function that has never been reasoned about. Left alone on
-- purpose.
-- ===========================================================================
