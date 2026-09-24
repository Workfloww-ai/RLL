-- Migration: 038_chunked_batch_purge_procedure.sql
-- Description: Updates purge_batch_data_fast stored procedure to purge raw_sales_upload
-- in a chunked loop of 10,000 rows per transaction using the raw_id primary key index.
-- Eliminates WAL write spikes, table locks, and PostgREST connection timeouts on 600k+ row staging datasets.

CREATE OR REPLACE FUNCTION public.purge_batch_data_fast(p_batch_id UUID, p_chunk_size INT DEFAULT 10000)
RETURNS VOID
LANGUAGE plpgsql VOLATILE SECURITY DEFINER AS $$
DECLARE
    v_rows_deleted INT := 0;
BEGIN
    -- Chunked deletion loop for raw_sales_upload using primary key index
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

    -- Delete associated staging logs and chunk tracking
    DELETE FROM public.batch_chunks WHERE batch_id = p_batch_id;
    DELETE FROM public.upload_pipeline_logs WHERE batch_id = p_batch_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.purge_batch_data_fast(UUID, INT) TO authenticated, service_role, anon;
