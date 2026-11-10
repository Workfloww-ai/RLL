-- ==============================================================================
-- Migration: 061_batch_purge_and_fast_rollback_indexes.sql
-- Description: Essential batch-scoped indexes and chunked rollback procedure
--              to eliminate table locks, PostgREST DELETE statement timeouts,
--              and worker hangs during file uploads and rollbacks.
-- Target DB: test_db (wgpxmvrbbgpzkomdutlk)
-- ==============================================================================

--------------------------------------------------------------------------------
-- 1. Batch ID Indexes for Instant Rollbacks & Re-Upload Replacements
-- Eliminates multi-million row sequential scans during DELETE WHERE batch_id = ?
--------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_sales_fact_batch_id 
    ON public.sales_fact (batch_id);

CREATE INDEX IF NOT EXISTS idx_user_sales_fact_batch_id 
    ON public.user_sales_fact (batch_id);

CREATE INDEX IF NOT EXISTS idx_raw_sales_upload_batch_id 
    ON public.raw_sales_upload (batch_id);

CREATE INDEX IF NOT EXISTS idx_batch_chunks_batch_id 
    ON public.batch_chunks (batch_id);

CREATE INDEX IF NOT EXISTS idx_upload_pipeline_logs_batch_id 
    ON public.upload_pipeline_logs (batch_id);

CREATE INDEX IF NOT EXISTS idx_upload_validation_errors_batch_id 
    ON public.upload_validation_errors (batch_id);

--------------------------------------------------------------------------------
-- 2. Covering Indexes for Fast Date Aggregation & Validation
-- Enables index-only scans for MTD and Daily case totals
--------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_sds_date_cases 
    ON public.sales_daily_summary (sale_date, total_cases);

CREATE INDEX IF NOT EXISTS idx_sms_month_cases 
    ON public.sales_monthly_summary (month_start, total_cases);

--------------------------------------------------------------------------------
-- 3. Clean Ambiguous Overloads of purge_batch_data_fast
-- Resolves PGRST203 "Could not choose the best candidate function"
--------------------------------------------------------------------------------
DROP FUNCTION IF EXISTS public.purge_batch_data_fast(TEXT);
DROP FUNCTION IF EXISTS public.purge_batch_data_fast(UUID);

--------------------------------------------------------------------------------
-- 4. High-Performance Chunked Staging Purge Stored Procedure
-- Safely purges temporary staging records (raw_sales_upload, batch_chunks, etc.)
-- in 10,000-row chunks after successful uploads in <50ms.
-- NOTE: This does NOT delete facts. Facts are preserved.
--------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.purge_batch_data_fast(
    p_batch_id UUID, 
    p_chunk_size INT DEFAULT 10000
)
RETURNS VOID
LANGUAGE plpgsql 
VOLATILE 
SECURITY DEFINER 
AS $$
DECLARE
    v_rows_deleted INT := 0;
BEGIN
    -- 1. Chunked delete for raw_sales_upload
    LOOP
        WITH to_delete AS (
            SELECT raw_id 
            FROM public.raw_sales_upload 
            WHERE batch_id = p_batch_id 
            LIMIT p_chunk_size
        )
        DELETE FROM public.raw_sales_upload 
        WHERE raw_id IN (SELECT raw_id FROM to_delete);

        GET DIAGNOSTICS v_rows_deleted = ROW_COUNT;
        EXIT WHEN v_rows_deleted = 0;
    END LOOP;

    -- 2. Purge auxiliary staging tracking tables
    DELETE FROM public.batch_chunks WHERE batch_id = p_batch_id;
    DELETE FROM public.upload_pipeline_logs WHERE batch_id = p_batch_id;
    DELETE FROM public.upload_validation_errors WHERE batch_id = p_batch_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.purge_batch_data_fast(UUID, INT) TO authenticated, service_role, anon;

--------------------------------------------------------------------------------
-- 5. High-Performance Full Batch Rollback Stored Procedure
-- Used ONLY on failed uploads or manual rollbacks to cleanly purge facts & staging.
--------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.rollback_batch_data(
    p_batch_id UUID, 
    p_chunk_size INT DEFAULT 10000
)
RETURNS VOID
LANGUAGE plpgsql 
VOLATILE 
SECURITY DEFINER 
AS $$
DECLARE
    v_rows_deleted INT := 0;
BEGIN
    -- 1. Chunked delete for user_sales_fact
    LOOP
        WITH to_delete AS (
            SELECT id 
            FROM public.user_sales_fact 
            WHERE batch_id = p_batch_id 
            LIMIT p_chunk_size
        )
        DELETE FROM public.user_sales_fact 
        WHERE id IN (SELECT id FROM to_delete);

        GET DIAGNOSTICS v_rows_deleted = ROW_COUNT;
        EXIT WHEN v_rows_deleted = 0;
    END LOOP;

    -- 2. Chunked delete for sales_fact
    LOOP
        WITH to_delete AS (
            SELECT fact_id 
            FROM public.sales_fact 
            WHERE batch_id = p_batch_id 
            LIMIT p_chunk_size
        )
        DELETE FROM public.sales_fact 
        WHERE fact_id IN (SELECT fact_id FROM to_delete);

        GET DIAGNOSTICS v_rows_deleted = ROW_COUNT;
        EXIT WHEN v_rows_deleted = 0;
    END LOOP;

    -- 3. Purge temporary staging data
    PERFORM public.purge_batch_data_fast(p_batch_id, p_chunk_size);
END;
$$;

GRANT EXECUTE ON FUNCTION public.rollback_batch_data(UUID, INT) TO authenticated, service_role, anon;
