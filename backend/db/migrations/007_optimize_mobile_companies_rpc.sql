-- 007_optimize_mobile_companies_rpc.sql
-- Optimization for get_mobile_companies_summary RPC
-- Filters non-'Others' companies upfront via inner join to leverage hash join optimization (76ms vs 230ms)

CREATE OR REPLACE FUNCTION public.get_mobile_companies_summary(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_hq_id       UUID DEFAULT NULL
)
RETURNS TABLE (
    company_id      UUID,
    company_name    TEXT,
    daily_cases     NUMERIC,
    daily_bottles   NUMERIC,
    daily_bl        NUMERIC,
    mtd_cases       NUMERIC,
    mtd_bottles     NUMERIC,
    mtd_bl          NUMERIC,
    ytd_cases       NUMERIC,
    ytd_bottles     NUMERIC,
    ytd_bl          NUMERIC
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    WITH non_others_companies AS (
        SELECT c.company_id, c.company_name
        FROM public.companies c
        WHERE c.company_name IS NOT NULL 
          AND LOWER(TRIM(c.company_name)) != 'others'
    )
    SELECT
        sds.company_id,
        noc.company_name::TEXT AS company_name,
        ROUND(SUM(CASE WHEN sds.sale_date = p_target_date THEN sds.total_cases ELSE 0 END), 2)::NUMERIC AS daily_cases,
        ROUND(SUM(CASE WHEN sds.sale_date = p_target_date THEN sds.total_bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
        ROUND(SUM(CASE WHEN sds.sale_date = p_target_date THEN sds.total_bl ELSE 0 END), 2)::NUMERIC AS daily_bl,
        ROUND(SUM(CASE WHEN sds.sale_date >= p_mtd_start THEN sds.total_cases ELSE 0 END), 2)::NUMERIC AS mtd_cases,
        ROUND(SUM(CASE WHEN sds.sale_date >= p_mtd_start THEN sds.total_bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
        ROUND(SUM(CASE WHEN sds.sale_date >= p_mtd_start THEN sds.total_bl ELSE 0 END), 2)::NUMERIC AS mtd_bl,
        ROUND(SUM(sds.total_cases), 2)::NUMERIC AS ytd_cases,
        ROUND(SUM(sds.total_bottles), 2)::NUMERIC AS ytd_bottles,
        ROUND(SUM(sds.total_bl), 2)::NUMERIC AS ytd_bl
    FROM public.sales_daily_summary sds
    INNER JOIN non_others_companies noc ON sds.company_id = noc.company_id
    WHERE sds.sale_date >= p_ytd_start
      AND sds.sale_date <= p_target_date
      AND (p_hq_id IS NULL OR sds.headquarters_id = p_hq_id)
    GROUP BY sds.company_id, noc.company_name;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_companies_summary(DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;
