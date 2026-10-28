-- Rollback: 048_hybrid_ytd_sales_summary_rpc_rollback.sql
-- Description: Reverts get_mobile_companies_summary and get_mobile_company_brands_summary
-- back to the version from 045_optimize_mobile_sales_rpcs.sql.

-- 1. Rollback get_mobile_companies_summary
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
SET work_mem = '64MB'
SET enable_incremental_sort = off
AS $$
DECLARE
    v_include_others BOOLEAN;
    v_valid_company_ids UUID[];
BEGIN
    v_include_others := public.get_include_others_in_sales();

    SELECT ARRAY_AGG(c.company_id) INTO v_valid_company_ids
    FROM public.companies c
    WHERE LOWER(TRIM(c.company_name)) NOT IN ('others', 'other');

    IF v_include_others THEN
        IF p_hq_id IS NOT NULL THEN
            RETURN QUERY
            WITH agg AS (
                SELECT
                    sds.company_id,
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
                WHERE sds.headquarters_id = p_hq_id
                  AND sds.sale_date >= p_ytd_start
                  AND sds.sale_date <= p_target_date
                GROUP BY sds.company_id
            )
            SELECT
                a.company_id,
                COALESCE(c.company_name, 'Other')::TEXT AS company_name,
                a.daily_cases, a.daily_bottles, a.daily_bl,
                a.mtd_cases, a.mtd_bottles, a.mtd_bl,
                a.ytd_cases, a.ytd_bottles, a.ytd_bl
            FROM agg a
            LEFT JOIN public.companies c ON a.company_id = c.company_id;
        ELSE
            RETURN QUERY
            WITH agg AS (
                SELECT
                    sds.company_id,
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
                WHERE sds.sale_date >= p_ytd_start
                  AND sds.sale_date <= p_target_date
                GROUP BY sds.company_id
            )
            SELECT
                a.company_id,
                COALESCE(c.company_name, 'Other')::TEXT AS company_name,
                a.daily_cases, a.daily_bottles, a.daily_bl,
                a.mtd_cases, a.mtd_bottles, a.mtd_bl,
                a.ytd_cases, a.ytd_bottles, a.ytd_bl
            FROM agg a
            LEFT JOIN public.companies c ON a.company_id = c.company_id;
        END IF;
    ELSE
        IF p_hq_id IS NOT NULL THEN
            RETURN QUERY
            WITH agg AS (
                SELECT
                    sds.company_id,
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
                WHERE sds.headquarters_id = p_hq_id
                  AND sds.company_id = ANY(v_valid_company_ids)
                  AND sds.sale_date >= p_ytd_start
                  AND sds.sale_date <= p_target_date
                GROUP BY sds.company_id
            )
            SELECT
                a.company_id,
                COALESCE(c.company_name, 'Other')::TEXT AS company_name,
                a.daily_cases, a.daily_bottles, a.daily_bl,
                a.mtd_cases, a.mtd_bottles, a.mtd_bl,
                a.ytd_cases, a.ytd_bottles, a.ytd_bl
            FROM agg a
            LEFT JOIN public.companies c ON a.company_id = c.company_id;
        ELSE
            RETURN QUERY
            WITH agg AS (
                SELECT
                    sds.company_id,
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
                WHERE sds.company_id = ANY(v_valid_company_ids)
                  AND sds.sale_date >= p_ytd_start
                  AND sds.sale_date <= p_target_date
                GROUP BY sds.company_id
            )
            SELECT
                a.company_id,
                COALESCE(c.company_name, 'Other')::TEXT AS company_name,
                a.daily_cases, a.daily_bottles, a.daily_bl,
                a.mtd_cases, a.mtd_bottles, a.mtd_bl,
                a.ytd_cases, a.ytd_bottles, a.ytd_bl
            FROM agg a
            LEFT JOIN public.companies c ON a.company_id = c.company_id;
        END IF;
    END IF;
END;
$$;

-- 2. Rollback get_mobile_company_brands_summary
CREATE OR REPLACE FUNCTION public.get_mobile_company_brands_summary(
    p_company_ids UUID[],
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_hq_id       UUID DEFAULT NULL
)
RETURNS TABLE (
    brand_id        UUID,
    brand_name      TEXT,
    company_id      UUID,
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
SET work_mem = '64MB'
SET enable_incremental_sort = off
AS $$
BEGIN
    RETURN QUERY
    WITH agg AS (
        SELECT
            sds.brand_id,
            sds.company_id,
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
        WHERE sds.sale_date >= p_ytd_start
          AND sds.sale_date <= p_target_date
          AND sds.company_id = ANY(p_company_ids)
          AND (p_hq_id IS NULL OR sds.headquarters_id = p_hq_id)
        GROUP BY sds.brand_id, sds.company_id
    )
    SELECT
        a.brand_id,
        COALESCE(b.brand_name, 'Generic Brand')::TEXT AS brand_name,
        a.company_id,
        a.daily_cases,
        a.daily_bottles,
        a.daily_bl,
        a.mtd_cases,
        a.mtd_bottles,
        a.mtd_bl,
        a.ytd_cases,
        a.ytd_bottles,
        a.ytd_bl
    FROM agg a
    LEFT JOIN public.brands b ON a.brand_id = b.brand_id;
END;
$$;
