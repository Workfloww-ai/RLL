-- ==============================================================================
-- Rollback Migration: 059_essential_upload_performance_indexes_rollback.sql
-- ==============================================================================

BEGIN;

DROP INDEX IF EXISTS public.idx_raw_sales_upload_batch_id;
DROP INDEX IF EXISTS public.upload_validation_errors_batch_id;
DROP INDEX IF EXISTS public.upload_pipeline_logs_batch_id;
DROP INDEX IF EXISTS public.idx_user_sales_fact_batch_id;
DROP INDEX IF EXISTS public.idx_upload_batches_tenant_status;

COMMIT;

