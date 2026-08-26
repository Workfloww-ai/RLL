-- Migration: 011_cascading_groups_and_brands_rpc.sql
-- Purpose: Optimized RPCs for Group-level Brand Sales, Group Licensees, and Licensee Brand Sales with accurate period metrics, total_brands calculation, HQ filtering, and company 'Others' exclusion.

-- ── 1. get_cascading_groups_summary_json ──────────────────────────────
CREATE OR REPLACE FUNCTION public.get_cascading_groups_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_exclude_company TEXT DEFAULT 'Others',
    p_hq_name     TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
    v_month_start DATE;
BEGIN
    v_month_start := DATE_TRUNC('month', p_target_date)::DATE;

    SELECT jsonb_agg(row_to_json(grp)::jsonb) FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE p_exclude_company IS NOT NULL
              AND p_exclude_company != ''
              AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company))
        ),
        active_group_lics AS (
            SELECT l.licensee_id, l.group_id, d.name AS depot_name
            FROM public.licensees l
            LEFT JOIN public.depots d ON l.depot_id = d.depot_id
            LEFT JOIN public.headquarters hq ON d.headquarters_id = hq.headquarters_id
            WHERE l.is_active = true AND l.group_id IS NOT NULL
              AND (
                  p_hq_name IS NULL OR p_hq_name = '' OR p_hq_name = 'All Headquarters'
                  OR LOWER(TRIM(hq.name)) = LOWER(TRIM(p_hq_name))
              )
        ),
        daily_agg AS (
            SELECT
                agl.group_id,
                SUM(sds.total_cases)   AS daily_cases,
                SUM(sds.total_bottles) AS daily_bottles
            FROM public.sales_daily_summary sds
            JOIN active_group_lics agl ON sds.licensee_id = agl.licensee_id
            WHERE sds.sale_date = p_target_date
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sds.brand_id IS NULL
                  OR sds.brand_id NOT IN (SELECT brand_id FROM excluded_brands)
              )
            GROUP BY agl.group_id
        ),
        mtd_agg AS (
            SELECT
                agl.group_id,
                SUM(sms.total_cases)   AS mtd_cases,
                SUM(sms.total_bottles) AS mtd_bottles
            FROM public.sales_monthly_summary sms
            JOIN active_group_lics agl ON sms.licensee_id = agl.licensee_id
            WHERE sms.month_start = v_month_start
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sms.brand_id IS NULL
                  OR sms.brand_id NOT IN (SELECT brand_id FROM excluded_brands)
              )
            GROUP BY agl.group_id
        ),
        ytd_agg AS (
            SELECT
                agl.group_id,
                SUM(sms.total_cases)   AS ytd_cases,
                SUM(sms.total_bottles) AS ytd_bottles
            FROM public.sales_monthly_summary sms
            JOIN active_group_lics agl ON sms.licensee_id = agl.licensee_id
            WHERE sms.month_start >= DATE_TRUNC('month', p_ytd_start)::DATE
              AND sms.month_start <= v_month_start
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sms.brand_id IS NULL
                  OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY agl.group_id
        ),
        brand_meta AS (
            SELECT
                agl.group_id,
                COUNT(DISTINCT sms.brand_id) AS brand_count
            FROM public.sales_monthly_summary sms
            JOIN active_group_lics agl ON sms.licensee_id = agl.licensee_id
            WHERE sms.month_start >= DATE_TRUNC('month', p_ytd_start)::DATE
              AND sms.month_start <= v_month_start
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sms.brand_id IS NULL
                  OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY agl.group_id
        ),
        lic_meta AS (
            SELECT
                agl.group_id,
                COUNT(agl.licensee_id) AS lic_count,
                MAX(agl.depot_name) AS primary_depot
            FROM active_group_lics agl
            GROUP BY agl.group_id
        )
        SELECT
            g.group_id,
            g.group_name::TEXT                                                       AS group_name,
            COALESCE(lm.lic_count, 0)::BIGINT                                        AS total_licensees,
            COALESCE(bm.brand_count, 0)::BIGINT                                      AS total_brands,
            CASE WHEN lm.primary_depot IS NOT NULL
                 THEN ARRAY[lm.primary_depot::TEXT]
                 ELSE ARRAY[]::TEXT[] END                                            AS group_depots,
            ROUND(COALESCE(da.daily_cases,   0.0), 2)::NUMERIC                       AS daily_cases,
            ROUND(COALESCE(da.daily_bottles, 0.0), 2)::NUMERIC                       AS daily_bottles,
            ROUND(COALESCE(ma.mtd_cases,     0.0), 2)::NUMERIC                       AS mtd_cases,
            ROUND(COALESCE(ma.mtd_bottles,   0.0), 2)::NUMERIC                       AS mtd_bottles,
            ROUND(COALESCE(ya.ytd_cases,     0.0), 2)::NUMERIC                       AS ytd_cases,
            ROUND(COALESCE(ya.ytd_bottles,   0.0), 2)::NUMERIC                       AS ytd_bottles,
            ROUND(COALESCE(ma.mtd_cases,     0.0), 2)::NUMERIC                       AS total_cases,
            ROUND(COALESCE(ma.mtd_bottles,   0.0), 2)::NUMERIC                       AS total_bottles
        FROM public.groups g
        JOIN lic_meta lm  ON g.group_id = lm.group_id
        LEFT JOIN brand_meta bm ON g.group_id = bm.group_id
        LEFT JOIN daily_agg da ON g.group_id = da.group_id
        LEFT JOIN mtd_agg ma   ON g.group_id = ma.group_id
        LEFT JOIN ytd_agg ya   ON g.group_id = ya.group_id
        WHERE g.is_active = true
          AND COALESCE(lm.lic_count, 0) > 0
        ORDER BY ma.mtd_cases DESC NULLS LAST, lm.lic_count DESC NULLS LAST
    ) grp INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_cascading_groups_summary_json(DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

-- ── 2. NEW: get_group_brand_sales_summary_json ──────────────────────────────
CREATE OR REPLACE FUNCTION public.get_group_brand_sales_summary_json(
    p_group_id    UUID,
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_depot_name  TEXT DEFAULT NULL,
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
        )
        SELECT
            b.brand_id,
            b.brand_name::TEXT                                                                              AS brand_name,
            COALESCE(c.company_name, 'Brand Product')::TEXT                                                 AS company_name,
            COALESCE(MAX(gl.depot_name), 'R.S.B.C.L.')::TEXT                                                AS depot_name,
            ROUND(SUM(CASE WHEN sds.sale_date = p_target_date THEN sds.total_cases ELSE 0 END), 2)::NUMERIC  AS daily_cases,
            ROUND(SUM(CASE WHEN sds.sale_date = p_target_date THEN sds.total_bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_cases ELSE 0 END), 2)::NUMERIC  AS mtd_cases,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
            ROUND(SUM(sms.total_cases), 2)::NUMERIC                                                         AS ytd_cases,
            ROUND(SUM(sms.total_bottles),  2)::NUMERIC                                                      AS ytd_bottles,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_cases ELSE 0 END), 2)::NUMERIC  AS total_cases,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_bottles ELSE 0 END), 2)::NUMERIC AS total_bottles
        FROM public.sales_monthly_summary sms
        JOIN group_lics gl ON sms.licensee_id = gl.licensee_id
        LEFT JOIN public.sales_daily_summary sds ON sms.licensee_id = sds.licensee_id AND sms.brand_id = sds.brand_id AND sds.sale_date = p_target_date
        JOIN public.brands b    ON sms.brand_id   = b.brand_id
        JOIN public.companies c ON b.company_id   = c.company_id
        WHERE sms.month_start >= DATE_TRUNC('month', p_ytd_start)::DATE
          AND sms.month_start <= v_month_start
          AND (
              p_exclude_company IS NULL OR p_exclude_company = ''
              OR sms.brand_id IS NULL
              OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
          )
        GROUP BY b.brand_id, b.brand_name, c.company_name
        ORDER BY mtd_cases DESC NULLS LAST
    ) bs INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_group_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

-- ── 3. get_group_licensees_summary_json ─────────────────────────────
CREATE OR REPLACE FUNCTION public.get_group_licensees_summary_json(
    p_group_id    UUID,
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_depot_name  TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
    v_month_start DATE;
BEGIN
    v_month_start := DATE_TRUNC('month', p_target_date)::DATE;

    SELECT jsonb_agg(row_to_json(lic)::jsonb) FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE p_exclude_company IS NOT NULL
              AND p_exclude_company != ''
              AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company))
        ),
        group_lics AS (
            SELECT l.licensee_id, l.licensee_name, l.trade, d.name AS depot_name
            FROM public.licensees l
            LEFT JOIN public.depots d ON l.depot_id = d.depot_id
            WHERE l.group_id = p_group_id AND l.is_active = true
              AND (
                  p_depot_name IS NULL OR p_depot_name = '' OR p_depot_name = 'All Headquarters'
                  OR LOWER(TRIM(d.name)) = LOWER(TRIM(p_depot_name))
              )
        ),
        brand_cnt AS (
            SELECT
                sms.licensee_id,
                COUNT(DISTINCT sms.brand_id) AS total_brands
            FROM public.sales_monthly_summary sms
            JOIN group_lics gl ON sms.licensee_id = gl.licensee_id
            WHERE sms.month_start >= DATE_TRUNC('month', p_ytd_start)::DATE
              AND sms.month_start <= v_month_start
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sms.brand_id IS NULL
                  OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY sms.licensee_id
        ),
        daily_lic AS (
            SELECT
                sds.licensee_id,
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
            GROUP BY sds.licensee_id
        ),
        mtd_lic AS (
            SELECT
                sms.licensee_id,
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
            GROUP BY sms.licensee_id
        ),
        ytd_lic AS (
            SELECT
                sms.licensee_id,
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
            GROUP BY sms.licensee_id
        )
        SELECT
            gl.licensee_id,
            gl.licensee_name::TEXT,
            COALESCE(gl.trade, 'Off')::TEXT                                             AS trade,
            COALESCE(gl.depot_name, 'Unassigned')::TEXT                                 AS depot_name,
            COALESCE(bc.total_brands, 0)::BIGINT                                       AS total_brands,
            CASE WHEN gl.depot_name IS NOT NULL
                 THEN ARRAY[gl.depot_name::TEXT]
                 ELSE ARRAY[]::TEXT[] END                                               AS licensee_depots,
            ROUND(COALESCE(dl.daily_cases,   0.0), 2)::NUMERIC                         AS daily_cases,
            ROUND(COALESCE(dl.daily_bottles, 0.0), 2)::NUMERIC                         AS daily_bottles,
            ROUND(COALESCE(ml.mtd_cases,     0.0), 2)::NUMERIC                         AS mtd_cases,
            ROUND(COALESCE(ml.mtd_bottles,   0.0), 2)::NUMERIC                         AS mtd_bottles,
            ROUND(COALESCE(yl.ytd_cases,     0.0), 2)::NUMERIC                         AS ytd_cases,
            ROUND(COALESCE(yl.ytd_bottles,   0.0), 2)::NUMERIC                         AS ytd_bottles,
            ROUND(COALESCE(ml.mtd_cases,     0.0), 2)::NUMERIC                         AS total_cases,
            ROUND(COALESCE(ml.mtd_bottles,   0.0), 2)::NUMERIC                         AS total_bottles
        FROM group_lics gl
        LEFT JOIN brand_cnt bc ON gl.licensee_id = bc.licensee_id
        LEFT JOIN daily_lic dl ON gl.licensee_id = dl.licensee_id
        LEFT JOIN mtd_lic ml   ON gl.licensee_id = ml.licensee_id
        LEFT JOIN ytd_lic yl   ON gl.licensee_id = yl.licensee_id
        ORDER BY ml.mtd_cases DESC NULLS LAST
    ) lic INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

-- ── 4. get_licensee_brand_sales_summary_json ───────────────────────
CREATE OR REPLACE FUNCTION public.get_licensee_brand_sales_summary_json(
    p_licensee_id UUID,
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_depot_name  TEXT DEFAULT NULL,
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
        )
        SELECT
            b.brand_id,
            b.brand_name::TEXT                                                                              AS brand_name,
            COALESCE(c.company_name, 'Other')::TEXT                                                         AS company_name,
            COALESCE(MAX(li.depot_name), 'Unassigned')::TEXT                                                AS depot_name,
            ROUND(SUM(CASE WHEN sds.sale_date = p_target_date THEN sds.total_cases ELSE 0 END), 2)::NUMERIC  AS daily_cases,
            ROUND(SUM(CASE WHEN sds.sale_date = p_target_date THEN sds.total_bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_cases ELSE 0 END), 2)::NUMERIC  AS mtd_cases,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
            ROUND(SUM(sms.total_cases), 2)::NUMERIC                                                         AS ytd_cases,
            ROUND(SUM(sms.total_bottles),  2)::NUMERIC                                                      AS ytd_bottles,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_cases ELSE 0 END), 2)::NUMERIC  AS total_cases,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_bottles ELSE 0 END), 2)::NUMERIC AS total_bottles,
            CASE WHEN MAX(li.depot_name) IS NOT NULL
                 THEN ARRAY[MAX(li.depot_name)::TEXT]
                 ELSE ARRAY[]::TEXT[] END                                                                       AS sales_depots
        FROM public.sales_monthly_summary sms
        LEFT JOIN public.sales_daily_summary sds ON sms.licensee_id = sds.licensee_id AND sms.brand_id = sds.brand_id AND sds.sale_date = p_target_date
        JOIN public.brands b    ON sms.brand_id   = b.brand_id
        JOIN public.companies c ON b.company_id   = c.company_id
        LEFT JOIN lic_info li   ON sms.licensee_id = li.licensee_id
        WHERE sms.licensee_id = p_licensee_id
          AND sms.month_start >= DATE_TRUNC('month', p_ytd_start)::DATE
          AND sms.month_start <= v_month_start
          AND (
              p_exclude_company IS NULL OR p_exclude_company = ''
              OR sms.brand_id IS NULL
              OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
          )
        GROUP BY b.brand_id, b.brand_name, c.company_name
        ORDER BY mtd_cases DESC NULLS LAST
    ) bs INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;
