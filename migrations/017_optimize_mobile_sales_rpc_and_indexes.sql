-- Migration: 017_optimize_mobile_sales_rpc_and_indexes.sql
-- Purpose: Accelerate /mobile/sales query execution using covering composite indexes and optimized RPC JSON aggregation.

-- 1. Composite Covering Indexes for dashboard_summary_daily
CREATE INDEX IF NOT EXISTS idx_dsd_perf_sales_date_hq
    ON public.dashboard_summary_daily (sale_date DESC, headquarters_id, company_id, brand_id)
    INCLUDE (total_case, total_btl, total_bl);

CREATE INDEX IF NOT EXISTS idx_dsd_perf_depot_sales_date
    ON public.dashboard_summary_daily (depot_id, sale_date DESC, headquarters_id, brand_id)
    INCLUDE (total_case, total_btl, total_bl);

-- 2. Composite Covering Indexes for user_sales_fact
CREATE INDEX IF NOT EXISTS idx_usf_perf_sales_user_date
    ON public.user_sales_fact (sale_date DESC, user_id, company_id, brand_id)
    INCLUDE (cases, bottles, bl);

-- 3. Optimized RPC get_mobile_sales_summary_json with 'Others' exclusion
CREATE OR REPLACE FUNCTION public.get_mobile_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_hq_id       UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_others_id UUID;
    v_result JSONB;
BEGIN
    -- Resolve company 'Others' ID to exclude at DB level per project guidelines
    SELECT company_id INTO v_others_id
    FROM public.companies
    WHERE LOWER(company_name) = 'others'
    LIMIT 1;

    SELECT jsonb_build_object(
        'companies', (
            SELECT COALESCE(jsonb_agg(row_to_json(comp)::jsonb), '[]'::jsonb) FROM (
                SELECT
                    d.company_id,
                    d.brand_id,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_case ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_btl  ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_bl ELSE 0 END), 2)::NUMERIC  AS daily_bl,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_case ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_btl  ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start  THEN d.total_bl  ELSE 0 END), 2)::NUMERIC AS mtd_bl,
                    ROUND(SUM(d.total_case), 2)::NUMERIC                                                         AS ytd_cases,
                    ROUND(SUM(d.total_btl), 2)::NUMERIC                                                          AS ytd_bottles,
                    ROUND(SUM(d.total_bl), 2)::NUMERIC                                                         AS ytd_bl
                FROM public.dashboard_summary_daily d
                WHERE d.sale_date >= p_ytd_start
                  AND d.sale_date <= p_target_date
                  AND (p_hq_id IS NULL OR d.headquarters_id = p_hq_id)
                  AND (v_others_id IS NULL OR d.company_id != v_others_id)
                GROUP BY d.company_id, d.brand_id
            ) comp
        ),
        'depots', (
            SELECT COALESCE(jsonb_agg(row_to_json(dep)::jsonb), '[]'::jsonb) FROM (
                SELECT
                    d.depot_id,
                    d.brand_id,
                    d.headquarters_id,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_case ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_btl  ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_bl ELSE 0 END), 2)::NUMERIC  AS daily_bl,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_case ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_btl  ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start  THEN d.total_bl  ELSE 0 END), 2)::NUMERIC AS mtd_bl,
                    ROUND(SUM(d.total_case), 2)::NUMERIC                                                         AS ytd_cases,
                    ROUND(SUM(d.total_btl), 2)::NUMERIC                                                          AS ytd_bottles,
                    ROUND(SUM(d.total_bl), 2)::NUMERIC                                                         AS ytd_bl
                FROM public.dashboard_summary_daily d
                WHERE d.sale_date >= p_ytd_start
                  AND d.sale_date <= p_target_date
                  AND (p_hq_id IS NULL OR d.headquarters_id = p_hq_id)
                  AND (v_others_id IS NULL OR d.company_id != v_others_id)
                GROUP BY d.depot_id, d.brand_id, d.headquarters_id
            ) dep
        )
    ) INTO v_result;

    RETURN COALESCE(v_result, '{"companies":[],"depots":[]}'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_sales_summary_json(DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;
