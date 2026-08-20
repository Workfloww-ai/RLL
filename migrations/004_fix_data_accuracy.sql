-- Migration: 004_fix_data_accuracy
-- Purpose: Fix incorrect Daily, MTD, and YTD data for Groups, TSM, and Companies.
--
-- Bugs fixed:
--   1. get_cascading_groups_summary_json: Used INNER JOIN on sales_agg, which silently
--      dropped groups that have licensees but zero sales in the queried period.
--      Fixed to LEFT JOIN so all groups with licensees are always returned.
--
--   2. get_mobile_tsm_sales_summary_json: Used ambiguous `jsonb_agg(tsm)` where `tsm`
--      is both the subquery alias and the column reference. PostgreSQL interprets this
--      as aggregating only the `tsm` column of the outer SELECT (which doesn't exist),
--      resulting in NULL or empty data. Fixed to use `jsonb_agg(row_to_json(tsm_row)::jsonb)`.
--
--   3. get_group_licensees_summary_json: Same LEFT JOIN issue — licensees with zero
--      sales in the selected period were dropped. Fixed to LEFT JOIN.
--
--   4. get_mobile_sales_summary_json: Applied same row_to_json fix for JSONB agg.


-- ── 1. Fix: get_cascading_groups_summary_json — LEFT JOIN on sales_agg ──────
CREATE OR REPLACE FUNCTION public.get_cascading_groups_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_agg(row_to_json(grp)::jsonb) FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE p_exclude_company IS NOT NULL
              AND p_exclude_company != ''
              AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company))
        ),
        sales_agg AS (
            SELECT
                l.group_id,
                SUM(CASE WHEN sf.sale_date = p_target_date        THEN sf.total_case ELSE 0 END) AS daily_cases,
                SUM(CASE WHEN sf.sale_date = p_target_date        THEN sf.total_btl  ELSE 0 END) AS daily_bottles,
                SUM(CASE WHEN sf.sale_date >= p_mtd_start         THEN sf.total_case ELSE 0 END) AS mtd_cases,
                SUM(CASE WHEN sf.sale_date >= p_mtd_start         THEN sf.total_btl  ELSE 0 END) AS mtd_bottles,
                SUM(sf.total_case)                                                                AS ytd_cases,
                SUM(sf.total_btl)                                                                 AS ytd_bottles
            FROM public.sales_fact sf
            JOIN public.licensees l ON sf.licensee_id = l.licensee_id
            WHERE sf.sale_date >= p_ytd_start
              AND sf.sale_date <= p_target_date
              AND l.is_active = true
              AND l.group_id IS NOT NULL
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sf.brand_id IS NULL
                  OR sf.brand_id NOT IN (SELECT brand_id FROM excluded_brands)
              )
            GROUP BY l.group_id
        ),
        lic_meta AS (
            SELECT
                l.group_id,
                COUNT(l.licensee_id)                                             AS lic_count,
                ARRAY_AGG(DISTINCT d.name) FILTER (WHERE d.name IS NOT NULL)     AS lic_depots
            FROM public.licensees l
            LEFT JOIN public.depots d ON l.depot_id = d.depot_id
            WHERE l.is_active = true AND l.group_id IS NOT NULL
            GROUP BY l.group_id
        )
        SELECT
            g.group_id,
            g.group_name::TEXT                                                       AS group_name,
            COALESCE(lm.lic_count, 0)::BIGINT                                        AS total_licensees,
            COALESCE(lm.lic_depots, ARRAY[]::TEXT[])                                 AS linked_depots,
            ROUND(COALESCE(sa.daily_cases,   0.0), 2)::NUMERIC                       AS daily_cases,
            ROUND(COALESCE(sa.daily_bottles, 0.0), 2)::NUMERIC                       AS daily_bottles,
            ROUND(COALESCE(sa.mtd_cases,     0.0), 2)::NUMERIC                       AS mtd_cases,
            ROUND(COALESCE(sa.mtd_bottles,   0.0), 2)::NUMERIC                       AS mtd_bottles,
            ROUND(COALESCE(sa.ytd_cases,     0.0), 2)::NUMERIC                       AS ytd_cases,
            ROUND(COALESCE(sa.ytd_bottles,   0.0), 2)::NUMERIC                       AS ytd_bottles,
            ROUND(COALESCE(sa.mtd_cases,     0.0), 2)::NUMERIC                       AS total_cases,
            ROUND(COALESCE(sa.mtd_bottles,   0.0), 2)::NUMERIC                       AS total_bottles
        FROM public.groups g
        LEFT JOIN lic_meta lm  ON g.group_id = lm.group_id
        LEFT JOIN sales_agg sa ON g.group_id = sa.group_id
        WHERE g.is_active = true
          AND COALESCE(lm.lic_count, 0) > 0
        ORDER BY sa.mtd_cases DESC NULLS LAST, lm.lic_count DESC NULLS LAST
    ) grp INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_cascading_groups_summary_json(DATE, DATE, DATE, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION get_cascading_groups_summary_json(DATE, DATE, DATE, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION get_cascading_groups_summary_json(DATE, DATE, DATE, TEXT) TO anon;


-- ── 2. Fix: get_group_licensees_summary_json — LEFT JOIN so zero-sale licensees appear ──
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
BEGIN
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
            SELECT l.licensee_id, l.licensee_name, l.trade, l.depot_id, d.name AS depot_name
            FROM public.licensees l
            LEFT JOIN public.depots d ON l.depot_id = d.depot_id
            WHERE l.group_id = p_group_id AND l.is_active = true
              AND (p_depot_name IS NULL OR p_depot_name = '' OR LOWER(d.name) = LOWER(p_depot_name))
        ),
        lic_sales AS (
            SELECT
                sf.licensee_id,
                SUM(CASE WHEN sf.sale_date = p_target_date THEN sf.total_case ELSE 0 END) AS daily_cases,
                SUM(CASE WHEN sf.sale_date = p_target_date THEN sf.total_btl  ELSE 0 END) AS daily_bottles,
                SUM(CASE WHEN sf.sale_date >= p_mtd_start  THEN sf.total_case ELSE 0 END) AS mtd_cases,
                SUM(CASE WHEN sf.sale_date >= p_mtd_start  THEN sf.total_btl  ELSE 0 END) AS mtd_bottles,
                SUM(sf.total_case)                                                          AS ytd_cases,
                SUM(sf.total_btl)                                                           AS ytd_bottles
            FROM public.sales_fact sf
            JOIN group_lics gl ON sf.licensee_id = gl.licensee_id
            WHERE sf.sale_date >= p_ytd_start
              AND sf.sale_date <= p_target_date
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sf.brand_id IS NULL
                  OR sf.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY sf.licensee_id
        )
        SELECT
            gl.licensee_id,
            gl.licensee_name::TEXT,
            COALESCE(gl.trade, 'Off')::TEXT                                             AS trade,
            CASE WHEN gl.depot_name IS NOT NULL
                 THEN ARRAY[gl.depot_name::TEXT]
                 ELSE ARRAY[]::TEXT[] END                                               AS licensee_depots,
            ROUND(COALESCE(ls.daily_cases,   0.0), 2)::NUMERIC                         AS daily_cases,
            ROUND(COALESCE(ls.daily_bottles, 0.0), 2)::NUMERIC                         AS daily_bottles,
            ROUND(COALESCE(ls.mtd_cases,     0.0), 2)::NUMERIC                         AS mtd_cases,
            ROUND(COALESCE(ls.mtd_bottles,   0.0), 2)::NUMERIC                         AS mtd_bottles,
            ROUND(COALESCE(ls.ytd_cases,     0.0), 2)::NUMERIC                         AS ytd_cases,
            ROUND(COALESCE(ls.ytd_bottles,   0.0), 2)::NUMERIC                         AS ytd_bottles,
            ROUND(COALESCE(ls.mtd_cases,     0.0), 2)::NUMERIC                         AS total_cases,
            ROUND(COALESCE(ls.mtd_bottles,   0.0), 2)::NUMERIC                         AS total_bottles
        FROM group_lics gl
        LEFT JOIN lic_sales ls ON gl.licensee_id = ls.licensee_id
        ORDER BY ls.mtd_cases DESC NULLS LAST
    ) lic INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO anon;


-- ── 3. Fix: get_licensee_brand_sales_summary_json — use row_to_json ──────────
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
BEGIN
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
            b.brand_name::TEXT                                                                        AS brand_name,
            COALESCE(c.company_name, 'Other')::TEXT                                                   AS company_name,
            ROUND(SUM(CASE WHEN sf.sale_date = p_target_date THEN sf.total_case ELSE 0 END), 2)::NUMERIC AS daily_cases,
            ROUND(SUM(CASE WHEN sf.sale_date = p_target_date THEN sf.total_btl  ELSE 0 END), 2)::NUMERIC AS daily_bottles,
            ROUND(SUM(CASE WHEN sf.sale_date >= p_mtd_start  THEN sf.total_case ELSE 0 END), 2)::NUMERIC AS mtd_cases,
            ROUND(SUM(CASE WHEN sf.sale_date >= p_mtd_start  THEN sf.total_btl  ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
            ROUND(SUM(sf.total_case), 2)::NUMERIC                                                        AS ytd_cases,
            ROUND(SUM(sf.total_btl),  2)::NUMERIC                                                        AS ytd_bottles,
            ROUND(SUM(CASE WHEN sf.sale_date >= p_mtd_start  THEN sf.total_case ELSE 0 END), 2)::NUMERIC AS total_cases,
            ROUND(SUM(CASE WHEN sf.sale_date >= p_mtd_start  THEN sf.total_btl  ELSE 0 END), 2)::NUMERIC AS total_bottles,
            CASE WHEN li.depot_name IS NOT NULL
                 THEN ARRAY[li.depot_name::TEXT]
                 ELSE ARRAY[]::TEXT[] END                                                                 AS sales_depots
        FROM public.sales_fact sf
        JOIN public.brands b    ON sf.brand_id    = b.brand_id
        JOIN public.companies c ON b.company_id   = c.company_id
        LEFT JOIN lic_info li   ON sf.licensee_id = li.licensee_id
        WHERE sf.licensee_id = p_licensee_id
          AND sf.sale_date >= p_ytd_start
          AND sf.sale_date <= p_target_date
          AND (
              p_exclude_company IS NULL OR p_exclude_company = ''
              OR sf.brand_id IS NULL
              OR sf.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
          )
        GROUP BY b.brand_id, b.brand_name, c.company_name, li.depot_name
        ORDER BY mtd_cases DESC NULLS LAST
    ) bs INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO anon;


-- ── 4. Fix: get_mobile_tsm_sales_summary_json — correct jsonb_agg syntax ────
CREATE OR REPLACE FUNCTION get_mobile_tsm_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_agg(row_to_json(tsm_row)::jsonb)
    INTO v_result
    FROM (
        SELECT
            usf.user_id,
            usf.company_id,
            usf.brand_id,
            SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.cases   ELSE 0 END)::BIGINT AS daily_cases,
            SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.bottles ELSE 0 END)::BIGINT AS daily_bottles,
            ROUND(SUM(CASE WHEN usf.sale_date = p_target_date THEN usf.bl ELSE 0 END), 2)     AS daily_bl,
            SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.cases   ELSE 0 END)::BIGINT AS mtd_cases,
            SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.bottles ELSE 0 END)::BIGINT AS mtd_bottles,
            ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  THEN usf.bl ELSE 0 END), 2)     AS mtd_bl,
            SUM(usf.cases)::BIGINT                                                             AS ytd_cases,
            SUM(usf.bottles)::BIGINT                                                           AS ytd_bottles,
            ROUND(SUM(usf.bl), 2)                                                              AS ytd_bl
        FROM public.user_sales_fact usf
        WHERE usf.sale_date >= p_ytd_start
          AND usf.sale_date <= p_target_date
        GROUP BY usf.user_id, usf.company_id, usf.brand_id
    ) tsm_row;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_mobile_tsm_sales_summary_json(DATE, DATE, DATE) TO authenticated;
GRANT EXECUTE ON FUNCTION get_mobile_tsm_sales_summary_json(DATE, DATE, DATE) TO service_role;
GRANT EXECUTE ON FUNCTION get_mobile_tsm_sales_summary_json(DATE, DATE, DATE) TO anon;


-- ── 5. Fix: get_mobile_sales_summary_json — correct jsonb_agg syntax ────────
CREATE OR REPLACE FUNCTION get_mobile_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_hq_id       UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'companies', (
            SELECT jsonb_agg(row_to_json(comp)::jsonb) FROM (
                SELECT
                    d.company_id,
                    d.brand_id,
                    SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_case ELSE 0 END)::BIGINT AS daily_cases,
                    SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_btl  ELSE 0 END)::BIGINT AS daily_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_bl ELSE 0 END), 2)  AS daily_bl,
                    SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_case ELSE 0 END)::BIGINT AS mtd_cases,
                    SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_btl  ELSE 0 END)::BIGINT AS mtd_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start  THEN d.total_bl  ELSE 0 END), 2) AS mtd_bl,
                    SUM(d.total_case)::BIGINT                                                         AS ytd_cases,
                    SUM(d.total_btl)::BIGINT                                                          AS ytd_bottles,
                    ROUND(SUM(d.total_bl), 2)                                                         AS ytd_bl
                FROM public.dashboard_summary_daily d
                WHERE d.sale_date >= p_ytd_start
                  AND d.sale_date <= p_target_date
                  AND (p_hq_id IS NULL OR d.headquarters_id = p_hq_id)
                GROUP BY d.company_id, d.brand_id
            ) comp
        ),
        'depots', (
            SELECT jsonb_agg(row_to_json(dep)::jsonb) FROM (
                SELECT
                    d.depot_id,
                    d.brand_id,
                    d.headquarters_id,
                    SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_case ELSE 0 END)::BIGINT AS daily_cases,
                    SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_btl  ELSE 0 END)::BIGINT AS daily_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_bl ELSE 0 END), 2)  AS daily_bl,
                    SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_case ELSE 0 END)::BIGINT AS mtd_cases,
                    SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_btl  ELSE 0 END)::BIGINT AS mtd_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start  THEN d.total_bl  ELSE 0 END), 2) AS mtd_bl,
                    SUM(d.total_case)::BIGINT                                                         AS ytd_cases,
                    SUM(d.total_btl)::BIGINT                                                          AS ytd_bottles,
                    ROUND(SUM(d.total_bl), 2)                                                         AS ytd_bl
                FROM public.dashboard_summary_daily d
                WHERE d.sale_date >= p_ytd_start
                  AND d.sale_date <= p_target_date
                  AND (p_hq_id IS NULL OR d.headquarters_id = p_hq_id)
                GROUP BY d.depot_id, d.brand_id, d.headquarters_id
            ) dep
        )
    ) INTO v_result;

    RETURN COALESCE(v_result, '{"companies":[],"depots":[]}'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_mobile_sales_summary_json(DATE, DATE, DATE, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION get_mobile_sales_summary_json(DATE, DATE, DATE, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION get_mobile_sales_summary_json(DATE, DATE, DATE, UUID) TO anon;
