-- ==============================================================================
-- Rollback Migration: 054_drop_redundant_overlapping_indexes_rollback.sql
-- Description: Re-creates the 8 redundant indexes if rollback is needed.
-- ==============================================================================

BEGIN;

CREATE INDEX IF NOT EXISTS idx_usf_perf_sales_user_date
    ON public.user_sales_fact (sale_date DESC, user_id, company_id, brand_id)
    INCLUDE (cases, bottles, bl);

CREATE INDEX IF NOT EXISTS idx_usf_user_date_comp_brand_covering
    ON public.user_sales_fact (user_id, sale_date, company_id, brand_id);

CREATE INDEX IF NOT EXISTS idx_usf_comp_date_covering 
    ON public.user_sales_fact (company_id, sale_date DESC) 
    INCLUDE (user_id, brand_id, cases, bottles, bl);

CREATE INDEX IF NOT EXISTS idx_usf_date_user_comp_brand 
    ON public.user_sales_fact (sale_date DESC, user_id, company_id, brand_id);

CREATE INDEX IF NOT EXISTS idx_sales_fact_brand_lic_date
    ON public.sales_fact (brand_id, licensee_id, sale_date);

CREATE INDEX IF NOT EXISTS idx_sales_fact_lic_date
    ON public.sales_fact (licensee_id, sale_date DESC);

CREATE INDEX IF NOT EXISTS idx_sds_comp_date_brand
    ON public.sales_daily_summary (company_id, sale_date, brand_id);

CREATE INDEX IF NOT EXISTS idx_sales_daily_summary_brand_lic_date
    ON public.sales_daily_summary (brand_id, licensee_id, sale_date);

COMMIT;

