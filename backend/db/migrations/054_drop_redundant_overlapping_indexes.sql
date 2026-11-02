-- ==============================================================================
-- Migration: 054_drop_redundant_overlapping_indexes.sql
-- Description: Consolidates indexes by dropping 8 redundant overlapping index variants
-- on user_sales_fact, sales_fact, and sales_daily_summary.
--
-- Reclaims ~1.64 GB of wasted disk space without affecting any active query functionality.
-- All active queries are fully preserved via canonical Migration 051 covering indexes:
-- 1. idx_usf_tenant_user_date_covering (User/TSM/ASE/HQ-scoped Index-Only Scans)
-- 2. idx_usf_tenant_date_user_covering (Statewide All-HQ Index-Only Scans)
-- 3. idx_sales_fact_date_lic_brand (Cascading sales date lookups)
-- 4. uq_sales_daily_summary_grain (Summary grain uniqueness & lookups)
--
-- Space Reclaimed Breakdown:
-- - idx_usf_perf_sales_user_date:            ~434 MB
-- - idx_usf_user_date_comp_brand_covering:   ~288 MB
-- - idx_usf_comp_date_covering:              ~288 MB
-- - idx_usf_date_user_comp_brand:             ~77 MB
-- - idx_sales_fact_brand_lic_date:           ~177 MB
-- - idx_sales_fact_lic_date:                  ~44 MB
-- - idx_sds_comp_date_brand:                 ~179 MB
-- - idx_sales_daily_summary_brand_lic_date:  ~153 MB
-- TOTAL RECLAIMED DISK SPACE:                ~1,640 MB (~1.64 GB)
-- ==============================================================================

BEGIN;

-- 1. Drop 4 redundant overlapping indexes on user_sales_fact (~1.08 GB saved)
DROP INDEX IF EXISTS public.idx_usf_perf_sales_user_date;
DROP INDEX IF EXISTS public.idx_usf_user_date_comp_brand_covering;
DROP INDEX IF EXISTS public.idx_usf_comp_date_covering;
DROP INDEX IF EXISTS public.idx_usf_date_user_comp_brand;

-- 2. Drop 2 redundant overlapping indexes on sales_fact (~221 MB saved)
DROP INDEX IF EXISTS public.idx_sales_fact_brand_lic_date;
DROP INDEX IF EXISTS public.idx_sales_fact_lic_date;

-- 3. Drop 2 redundant overlapping indexes on sales_daily_summary (~332 MB saved)
DROP INDEX IF EXISTS public.idx_sds_comp_date_brand;
DROP INDEX IF EXISTS public.idx_sales_daily_summary_brand_lic_date;

COMMIT;

