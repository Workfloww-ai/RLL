-- ==============================================================================
-- Migration: 059_essential_upload_performance_indexes.sql
-- Description: Essential indexes to accelerate file uploads, batch status polling,
--              and chunked staging purges while strictly avoiding write bloat.
-- Target DB: test_db (wgpxmvrbbgpzkomdutlk)
-- ==============================================================================

BEGIN;

--------------------------------------------------------------------------------
-- 1. Fast Batch Purge & Reading for Staging Tables
-- Eliminates sequential table scans during chunked delete in purge_batch_data_fast
-- and paginated read in get_raw_sales_for_batch.
--------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_raw_sales_upload_batch_id 
    ON public.raw_sales_upload (batch_id);

CREATE INDEX IF NOT EXISTS idx_upload_validation_errors_batch_id 
    ON public.upload_validation_errors (batch_id);

CREATE INDEX IF NOT EXISTS idx_upload_pipeline_logs_batch_id 
    ON public.upload_pipeline_logs (batch_id);

--------------------------------------------------------------------------------
-- 2. Fast Rollback & Batch Overwrite on User Sales Fact
-- Eliminates table scans during DELETE FROM user_sales_fact WHERE batch_id = ?
--------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_user_sales_fact_batch_id 
    ON public.user_sales_fact (batch_id);

--------------------------------------------------------------------------------
-- 3. Fast Upload Queue Lock & Concurrency Status Check
-- Accelerates is_upload_active and get_lock_status checks
--------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_upload_batches_tenant_status 
    ON public.upload_batches (tenant_id, status);

COMMIT;

