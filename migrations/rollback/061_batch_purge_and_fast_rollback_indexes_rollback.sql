-- ==============================================================================
-- Rollback Migration: 061_batch_purge_and_fast_rollback_indexes_rollback.sql
-- Description: Drops batch indexes and rollback procedures introduced in 061.
-- Target DB: test_db (wgpxmvrbbgpzkomdutlk)
-- ==============================================================================

DROP FUNCTION IF EXISTS public.rollback_batch_data(UUID, INT);

-- Restore original 038 definition of purge_batch_data_fast
CREATE OR REPLACE FUNCTION public.purge_batch_data_fast(p_batch_id UUID, p_chunk_size INT DEFAULT 10000)
RETURNS VOID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER AS $$
DECLARE
    v_rows_deleted INT := 0;
BEGIN
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

    DELETE FROM public.batch_chunks WHERE batch_id = p_batch_id;
    DELETE FROM public.upload_pipeline_logs WHERE batch_id = p_batch_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.purge_batch_data_fast(UUID, INT) TO authenticated, service_role, anon;

DROP INDEX IF EXISTS public.idx_sales_fact_batch_id;
DROP INDEX IF EXISTS public.idx_user_sales_fact_batch_id;
DROP INDEX IF EXISTS public.idx_raw_sales_upload_batch_id;
DROP INDEX IF EXISTS public.idx_batch_chunks_batch_id;
DROP INDEX IF EXISTS public.idx_upload_pipeline_logs_batch_id;
DROP INDEX IF EXISTS public.idx_upload_validation_errors_batch_id;
DROP INDEX IF EXISTS public.idx_sds_date_cases;
DROP INDEX IF EXISTS public.idx_sms_month_cases;
