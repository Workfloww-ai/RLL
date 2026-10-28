-- Rollback: 049_fix_tsm_sales_include_others_toggle_rollback.sql
-- Description: Reverts get_mobile_tsm_sales_summary_json back to strictly excluding Others.

CREATE OR REPLACE FUNCTION public.get_mobile_tsm_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_user_ids    UUID[] DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
SET work_mem = '64MB'
SET enable_incremental_sort = off
AS $$
DECLARE
    v_valid_company_ids UUID[];
    v_result JSONB;
BEGIN
    SELECT ARRAY_AGG(c.company_id) INTO v_valid_company_ids
    FROM public.companies c
    WHERE LOWER(TRIM(c.company_name)) NOT IN ('others', 'other');

    IF p_user_ids IS NOT NULL AND cardinality(p_user_ids) > 0 THEN
        SELECT COALESCE(to_jsonb(json_agg(tsm_row)), '[]'::jsonb)
        INTO v_result
        FROM (
            SELECT
                usf.user_id,
                usf.company_id,
                usf.brand_id,
                ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
                ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                ROUND(SUM(CASE WHEN usf.sale_date = p_target_date THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS daily_bl,
                ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS mtd_bl,
                ROUND(SUM(usf.cases), 2)::NUMERIC                                                             AS ytd_cases,
                ROUND(SUM(usf.bottles), 2)::NUMERIC                                                           AS ytd_bottles,
                ROUND(SUM(usf.bl), 2)::NUMERIC                                                              AS ytd_bl
            FROM public.user_sales_fact usf
            WHERE usf.user_id = ANY(p_user_ids)
              AND usf.company_id = ANY(v_valid_company_ids)
              AND usf.sale_date >= p_ytd_start
              AND usf.sale_date <= p_target_date
            GROUP BY usf.user_id, usf.company_id, usf.brand_id
        ) tsm_row;
    ELSE
        SELECT COALESCE(to_jsonb(json_agg(tsm_row)), '[]'::jsonb)
        INTO v_result
        FROM (
            SELECT
                usf.user_id,
                usf.company_id,
                usf.brand_id,
                ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
                ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                ROUND(SUM(CASE WHEN usf.sale_date = p_target_date THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS daily_bl,
                ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS mtd_bl,
                ROUND(SUM(usf.cases), 2)::NUMERIC                                                             AS ytd_cases,
                ROUND(SUM(usf.bottles), 2)::NUMERIC                                                           AS ytd_bottles,
                ROUND(SUM(usf.bl), 2)::NUMERIC                                                              AS ytd_bl
            FROM public.user_sales_fact usf
            WHERE usf.company_id = ANY(v_valid_company_ids)
              AND usf.sale_date >= p_ytd_start
              AND usf.sale_date <= p_target_date
            GROUP BY usf.user_id, usf.company_id, usf.brand_id
        ) tsm_row;
    END IF;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[]) TO authenticated, service_role, anon;
