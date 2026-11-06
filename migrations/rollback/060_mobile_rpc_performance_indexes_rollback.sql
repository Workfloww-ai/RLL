-- ==============================================================================
-- Rollback Migration: 060_mobile_rpc_performance_indexes_rollback.sql
-- ==============================================================================

BEGIN;

DROP INDEX IF EXISTS public.idx_licensees_hq_group;
DROP INDEX IF EXISTS public.idx_depots_headquarters_id;
DROP INDEX IF EXISTS public.idx_sds_group_date_lic;
DROP INDEX IF EXISTS public.idx_sds_lic_date;
DROP INDEX IF EXISTS public.idx_sales_fact_lic_date;
DROP INDEX IF EXISTS public.idx_uhm_tenant_hq;

COMMIT;

