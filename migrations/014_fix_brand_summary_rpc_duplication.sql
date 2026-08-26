-- Migration: 014_fix_brand_summary_rpc_duplication.sql
-- Description: Fix multiplication/duplication of daily sales in get_group_brand_sales_summary_json and get_licensee_brand_sales_summary_json.
-- Root cause: Joining sales_daily_summary directly onto sales_monthly_summary caused daily sales records to be duplicated for every month in sales_monthly_summary.

CREATE OR REPLACE FUNCTION public.get_group_brand_sales_summary_json(
    p_group_id        UUID,
    p_target_date     DATE,
    p_mtd_start       DATE,
    p_ytd_start       DATE,
    p_depot_name      TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
    v_month_start DATE;
BEGIN
    v_month_start := DATE_TRUNC('month', p_target_date)::DATE;

    SELECT jsonb_agg(row_to_json(bs)::jsonb) FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE p_exclude_company IS NOT NULL
              AND p_exclude_company != ''
              AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company))
        ),
        group_lics AS (
            SELECT l.licensee_id, d.name AS depot_name
            FROM public.licensees l
            LEFT JOIN public.depots d ON l.depot_id = d.depot_id
            WHERE l.group_id = p_group_id AND l.is_active = true
              AND (
                  p_depot_name IS NULL OR p_depot_name = '' OR p_depot_name = 'All Headquarters'
                  OR LOWER(TRIM(d.name)) = LOWER(TRIM(p_depot_name))
              )
        ),
        daily_brands AS (
            SELECT
                sds.brand_id,
                MAX(gl.depot_name)     AS depot_name,
                SUM(sds.total_cases)   AS daily_cases,
                SUM(sds.total_bottles) AS daily_bottles
            FROM public.sales_daily_summary sds
            JOIN group_lics gl ON sds.licensee_id = gl.licensee_id
            WHERE sds.sale_date = p_target_date
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sds.brand_id IS NULL
                  OR sds.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY sds.brand_id
        ),
        mtd_brands AS (
            SELECT
                sms.brand_id,
                MAX(gl.depot_name)     AS depot_name,
                SUM(sms.total_cases)   AS mtd_cases,
                SUM(sms.total_bottles) AS mtd_bottles
            FROM public.sales_monthly_summary sms
            JOIN group_lics gl ON sms.licensee_id = gl.licensee_id
            WHERE sms.month_start = v_month_start
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sms.brand_id IS NULL
                  OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY sms.brand_id
        ),
        ytd_brands AS (
            SELECT
                sms.brand_id,
                MAX(gl.depot_name)     AS depot_name,
                SUM(sms.total_cases)   AS ytd_cases,
                SUM(sms.total_bottles) AS ytd_bottles
            FROM public.sales_monthly_summary sms
            JOIN group_lics gl ON sms.licensee_id = gl.licensee_id
            WHERE sms.month_start >= DATE_TRUNC('month', p_ytd_start)::DATE
              AND sms.month_start <= v_month_start
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sms.brand_id IS NULL
                  OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY sms.brand_id
        ),
        all_group_brands AS (
            SELECT brand_id FROM mtd_brands
            UNION
            SELECT brand_id FROM daily_brands
            UNION
            SELECT brand_id FROM ytd_brands
        )
        SELECT
            b.brand_id,
            b.brand_name::TEXT                                                     AS brand_name,
            COALESCE(c.company_name, 'Brand Product')::TEXT                        AS company_name,
            COALESCE(mb.depot_name, db.depot_name, yb.depot_name, 'R.S.B.C.L.')::TEXT AS depot_name,
            ROUND(COALESCE(db.daily_cases,   0.0), 2)::NUMERIC                        AS daily_cases,
            ROUND(COALESCE(db.daily_bottles, 0.0), 2)::NUMERIC                        AS daily_bottles,
            ROUND(COALESCE(mb.mtd_cases,     0.0), 2)::NUMERIC                        AS mtd_cases,
            ROUND(COALESCE(mb.mtd_bottles,   0.0), 2)::NUMERIC                        AS mtd_bottles,
            ROUND(COALESCE(yb.ytd_cases,     0.0), 2)::NUMERIC                        AS ytd_cases,
            ROUND(COALESCE(yb.ytd_bottles,   0.0), 2)::NUMERIC                        AS ytd_bottles,
            ROUND(COALESCE(mb.mtd_cases,     0.0), 2)::NUMERIC                        AS total_cases,
            ROUND(COALESCE(mb.mtd_bottles,   0.0), 2)::NUMERIC                        AS total_bottles
        FROM all_group_brands agb
        JOIN public.brands b    ON agb.brand_id = b.brand_id
        JOIN public.companies c ON b.company_id = c.company_id
        LEFT JOIN daily_brands db ON agb.brand_id = db.brand_id
        LEFT JOIN mtd_brands mb   ON agb.brand_id = mb.brand_id
        LEFT JOIN ytd_brands yb   ON agb.brand_id = yb.brand_id
        ORDER BY COALESCE(mb.mtd_cases, 0) DESC, COALESCE(db.daily_cases, 0) DESC
    ) bs INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_group_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

CREATE OR REPLACE FUNCTION public.get_licensee_brand_sales_summary_json(
    p_licensee_id     UUID,
    p_target_date     DATE,
    p_mtd_start       DATE,
    p_ytd_start       DATE,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
    v_month_start DATE;
BEGIN
    v_month_start := DATE_TRUNC('month', p_target_date)::DATE;

    SELECT jsonb_agg(row_to_json(bs)::jsonb) FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE p_exclude_company IS NOT NULL
              AND p_exclude_company != ''
              AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company))
        ),
        lic_info AS (
            SELECT l.licensee_id, d.name AS depot_name
            FROM public.licensees l
            LEFT JOIN public.depots d ON l.depot_id = d.depot_id
            WHERE l.licensee_id = p_licensee_id
        ),
        daily_brands AS (
            SELECT
                sds.brand_id,
                SUM(sds.total_cases)   AS daily_cases,
                SUM(sds.total_bottles) AS daily_bottles
            FROM public.sales_daily_summary sds
            WHERE sds.licensee_id = p_licensee_id
              AND sds.sale_date = p_target_date
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sds.brand_id IS NULL
                  OR sds.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY sds.brand_id
        ),
        mtd_brands AS (
            SELECT
                sms.brand_id,
                SUM(sms.total_cases)   AS mtd_cases,
                SUM(sms.total_bottles) AS mtd_bottles
            FROM public.sales_monthly_summary sms
            WHERE sms.licensee_id = p_licensee_id
              AND sms.month_start = v_month_start
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sms.brand_id IS NULL
                  OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY sms.brand_id
        ),
        ytd_brands AS (
            SELECT
                sms.brand_id,
                SUM(sms.total_cases)   AS ytd_cases,
                SUM(sms.total_bottles) AS ytd_bottles
            FROM public.sales_monthly_summary sms
            WHERE sms.licensee_id = p_licensee_id
              AND sms.month_start >= DATE_TRUNC('month', p_ytd_start)::DATE
              AND sms.month_start <= v_month_start
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sms.brand_id IS NULL
                  OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY sms.brand_id
        ),
        all_lic_brands AS (
            SELECT brand_id FROM mtd_brands
            UNION
            SELECT brand_id FROM daily_brands
            UNION
            SELECT brand_id FROM ytd_brands
        )
        SELECT
            b.brand_id,
            b.brand_name::TEXT                                                     AS brand_name,
            COALESCE(c.company_name, 'Other')::TEXT                                AS company_name,
            COALESCE(li.depot_name, 'Unassigned')::TEXT                            AS depot_name,
            ROUND(COALESCE(db.daily_cases,   0.0), 2)::NUMERIC                        AS daily_cases,
            ROUND(COALESCE(db.daily_bottles, 0.0), 2)::NUMERIC                        AS daily_bottles,
            ROUND(COALESCE(mb.mtd_cases,     0.0), 2)::NUMERIC                        AS mtd_cases,
            ROUND(COALESCE(mb.mtd_bottles,   0.0), 2)::NUMERIC                        AS mtd_bottles,
            ROUND(COALESCE(yb.ytd_cases,     0.0), 2)::NUMERIC                        AS ytd_cases,
            ROUND(COALESCE(yb.ytd_bottles,   0.0), 2)::NUMERIC                        AS ytd_bottles,
            ROUND(COALESCE(mb.mtd_cases,     0.0), 2)::NUMERIC                        AS total_cases,
            ROUND(COALESCE(mb.mtd_bottles,   0.0), 2)::NUMERIC                        AS total_bottles,
            CASE WHEN li.depot_name IS NOT NULL
                 THEN ARRAY[li.depot_name::TEXT]
                 ELSE ARRAY[]::TEXT[] END                                          AS sales_depots
        FROM all_lic_brands alb
        JOIN public.brands b    ON alb.brand_id = b.brand_id
        JOIN public.companies c ON b.company_id = c.company_id
        CROSS JOIN lic_info li
        LEFT JOIN daily_brands db ON alb.brand_id = db.brand_id
        LEFT JOIN mtd_brands mb   ON alb.brand_id = mb.brand_id
        LEFT JOIN ytd_brands yb   ON alb.brand_id = yb.brand_id
        ORDER BY COALESCE(mb.mtd_cases, 0) DESC, COALESCE(db.daily_cases, 0) DESC
    ) bs INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT) TO authenticated, service_role, anon;
