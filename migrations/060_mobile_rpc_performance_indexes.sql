-- ==============================================================================
-- Migration: 060_mobile_rpc_performance_indexes.sql
-- Description: Targeted indexes for accelerating mobile RPCs:
--              1. get_cascading_groups_summary_json
--              2. get_group_licensees_summary_json
--              3. get_licensee_brand_sales_summary_json
--              4. get_mobile_companies_summary
--              5. get_mobile_tsm_sales_summary_json
-- Target DB: test_db (wgpxmvrbbgpzkomdutlk)
-- ==============================================================================

BEGIN;

--------------------------------------------------------------------------------
-- 1. Headquarters Filtering on Master Tables
-- Used by: get_cascading_groups_summary_json & get_group_licensees_summary_json
-- Eliminates sequential table scans on licensees & depots when HQ is filtered.
--------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_licensees_hq_group 
    ON public.licensees (headquarters_id, group_id)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_depots_headquarters_id 
    ON public.depots (headquarters_id);

--------------------------------------------------------------------------------
-- 2. Cascading Group & Licensee Sales Aggregations
-- Used by: get_cascading_groups_summary_json & get_group_licensees_summary_json
-- Allows instant seek on group_id + index range scan on sale_date.
--------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_sds_group_date_lic 
    ON public.sales_daily_summary (group_id, sale_date DESC, licensee_id);

CREATE INDEX IF NOT EXISTS idx_sds_lic_date 
    ON public.sales_daily_summary (licensee_id, sale_date DESC);

--------------------------------------------------------------------------------
-- 3. Licensee Drilldown to Brands
-- Used by: get_licensee_brand_sales_summary_json
-- Allows instant seek on licensee_id across 1 year of sales in sales_fact.
--------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_sales_fact_lic_date 
    ON public.sales_fact (licensee_id, sale_date DESC);

--------------------------------------------------------------------------------
-- 4. Fast TSM/ASE Headquarters Resolution
-- Used by: get_mobile_tsm_sales_summary_json
-- Resolves user_ids for a headquarters under a specific tenant in 0ms.
--------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_uhm_tenant_hq 
    ON public.user_headquarters_mapping (tenant_id, headquarters_id);

COMMIT;

