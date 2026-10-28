-- Migration: 047_trim_duplicate_sales_rpc_aggregation.sql
-- Description: Eliminates redundant company aggregation inside get_mobile_sales_summary_json.
-- Callers (e.g. mobile sales router) consume companies from get_mobile_companies_summary
-- and only read depots from this procedure. Eliminating duplicate group-by on multi-million rows
-- saves ~250ms of database CPU and buffer pool memory per request.

CREATE OR REPLACE FUNCTION public.get_mobile_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_hq_id       UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SET work_mem = '64MB'
SET enable_incremental_sort = off
AS $$
DECLARE
    v_include_others BOOLEAN;
    v_valid_company_ids UUID[];
    v_depot_json JSONB;
BEGIN
    v_include_others := public.get_include_others_in_sales();

    SELECT ARRAY_AGG(c.company_id) INTO v_valid_company_ids
    FROM public.companies c
    WHERE LOWER(TRIM(c.company_name)) NOT IN ('others', 'other');

    IF v_include_others THEN
        IF p_hq_id IS NOT NULL THEN
            -- Aggregated Depots (HQ-filtered, include Others)
            SELECT COALESCE(to_jsonb(json_agg(depot_row)), '[]'::jsonb)
            INTO v_depot_json
            FROM (
                SELECT
                    sds.depot_id,
                    sds.headquarters_id,
                    sds.brand_id,
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
                GROUP BY sds.depot_id, sds.headquarters_id, sds.brand_id
            ) depot_row;
        ELSE
            -- Aggregated Depots (All HQ, include Others)
            SELECT COALESCE(to_jsonb(json_agg(depot_row)), '[]'::jsonb)
            INTO v_depot_json
            FROM (
                SELECT
                    sds.depot_id,
                    sds.headquarters_id,
                    sds.brand_id,
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
                GROUP BY sds.depot_id, sds.headquarters_id, sds.brand_id
            ) depot_row;
        END IF;
    ELSE
        -- Exclude Others
        IF p_hq_id IS NOT NULL THEN
            -- Aggregated Depots (HQ-filtered, exclude Others via pushed-down ANY filter)
            SELECT COALESCE(to_jsonb(json_agg(depot_row)), '[]'::jsonb)
            INTO v_depot_json
            FROM (
                SELECT
                    sds.depot_id,
                    sds.headquarters_id,
                    sds.brand_id,
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
                GROUP BY sds.depot_id, sds.headquarters_id, sds.brand_id
            ) depot_row;
        ELSE
            -- Aggregated Depots (All HQ, exclude Others via pushed-down ANY filter)
            SELECT COALESCE(to_jsonb(json_agg(depot_row)), '[]'::jsonb)
            INTO v_depot_json
            FROM (
                SELECT
                    sds.depot_id,
                    sds.headquarters_id,
                    sds.brand_id,
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
                GROUP BY sds.depot_id, sds.headquarters_id, sds.brand_id
            ) depot_row;
        END IF;
    END IF;

    RETURN jsonb_build_object(
        'companies', '[]'::jsonb,
        'depots',    COALESCE(v_depot_json, '[]'::jsonb)
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_sales_summary_json(DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;
