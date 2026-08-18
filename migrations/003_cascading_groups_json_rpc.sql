-- Migration: 003_cascading_groups_json_rpc
-- Purpose: Optimize Groups -> Licensees -> Brand Sales cascading hierarchy by:
--   1. Performing single-pass conditional SQL aggregations (CASE WHEN) for Daily, MTD, and YTD.
--   2. Returning aggregated JSONB payloads to eliminate PostgREST 1,000-row table truncation.
--   3. Adding composite indexes on sales_fact and licensees.

-- ── Composite Indexes ────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sales_fact_date_lic_brand 
    ON public.sales_fact (sale_date DESC, licensee_id, brand_id);

CREATE INDEX IF NOT EXISTS idx_sales_fact_lic_date 
    ON public.sales_fact (licensee_id, sale_date DESC);

CREATE INDEX IF NOT EXISTS idx_licensees_group_depot 
    ON public.licensees (group_id, depot_id);


-- ── 1. RPC Function: get_cascading_groups_summary_json ───────────────────────
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
    SELECT jsonb_agg(grp) FROM (
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
                SUM(CASE WHEN sf.sale_date = p_target_date THEN sf.total_case ELSE 0 END) AS daily_cases,
                SUM(CASE WHEN sf.sale_date = p_target_date THEN sf.total_btl ELSE 0 END)  AS daily_bottles,
                SUM(CASE WHEN sf.sale_date >= p_mtd_start THEN sf.total_case ELSE 0 END)  AS mtd_cases,
                SUM(CASE WHEN sf.sale_date >= p_mtd_start THEN sf.total_btl ELSE 0 END)   AS mtd_bottles,
                SUM(sf.total_case) AS ytd_cases,
                SUM(sf.total_btl)  AS ytd_bottles
            FROM public.sales_fact sf
            JOIN public.licensees l ON sf.licensee_id = l.licensee_id
            WHERE sf.sale_date >= p_ytd_start 
              AND sf.sale_date <= p_target_date
              AND l.is_active = true 
              AND l.group_id IS NOT NULL
              AND (p_exclude_company IS NULL OR p_exclude_company = '' OR sf.brand_id IS NULL OR sf.brand_id NOT IN (SELECT brand_id FROM excluded_brands))
            GROUP BY l.group_id
        ),
        lic_meta AS (
            SELECT
                l.group_id,
                COUNT(l.licensee_id) AS lic_count,
                ARRAY_AGG(DISTINCT d.name) FILTER (WHERE d.name IS NOT NULL) AS lic_depots
            FROM public.licensees l
            LEFT JOIN public.depots d ON l.depot_id = d.depot_id
            WHERE l.is_active = true AND l.group_id IS NOT NULL
            GROUP BY l.group_id
        )
        SELECT 
            g.group_id,
            g.group_name::TEXT AS group_name,
            COALESCE(lm.lic_count, 0)::BIGINT AS total_licensees,
            COALESCE(lm.lic_depots, ARRAY[]::TEXT[]) AS linked_depots,
            ROUND(COALESCE(sa.daily_cases, 0.0), 2)::NUMERIC   AS daily_cases,
            ROUND(COALESCE(sa.daily_bottles, 0.0), 2)::NUMERIC AS daily_bottles,
            ROUND(COALESCE(sa.mtd_cases, 0.0), 2)::NUMERIC     AS mtd_cases,
            ROUND(COALESCE(sa.mtd_bottles, 0.0), 2)::NUMERIC   AS mtd_bottles,
            ROUND(COALESCE(sa.ytd_cases, 0.0), 2)::NUMERIC     AS ytd_cases,
            ROUND(COALESCE(sa.ytd_bottles, 0.0), 2)::NUMERIC   AS ytd_bottles,
            ROUND(COALESCE(sa.mtd_cases, 0.0), 2)::NUMERIC     AS total_cases,
            ROUND(COALESCE(sa.mtd_bottles, 0.0), 2)::NUMERIC   AS total_bottles
        FROM public.groups g
        JOIN sales_agg sa ON g.group_id = sa.group_id
        LEFT JOIN lic_meta lm ON g.group_id = lm.group_id
        WHERE g.is_active = true
        ORDER BY mtd_cases DESC, total_licensees DESC
    ) grp INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_cascading_groups_summary_json(DATE, DATE, DATE, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION get_cascading_groups_summary_json(DATE, DATE, DATE, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION get_cascading_groups_summary_json(DATE, DATE, DATE, TEXT) TO anon;


-- ── 2. RPC Function: get_group_licensees_summary_json ───────────────────────
CREATE OR REPLACE FUNCTION public.get_group_licensees_summary_json(
    p_group_id UUID,
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_depot_name TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_agg(lic) FROM (
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
        ),
        lic_sales AS (
            SELECT 
                sf.licensee_id,
                SUM(CASE WHEN sf.sale_date = p_target_date THEN sf.total_case ELSE 0 END) AS daily_cases,
                SUM(CASE WHEN sf.sale_date = p_target_date THEN sf.total_btl ELSE 0 END)  AS daily_bottles,
                SUM(CASE WHEN sf.sale_date >= p_mtd_start THEN sf.total_case ELSE 0 END)  AS mtd_cases,
                SUM(CASE WHEN sf.sale_date >= p_mtd_start THEN sf.total_btl ELSE 0 END)   AS mtd_bottles,
                SUM(sf.total_case) AS ytd_cases,
                SUM(sf.total_btl)  AS ytd_bottles
            FROM public.sales_fact sf
            JOIN group_lics gl ON sf.licensee_id = gl.licensee_id
            WHERE sf.sale_date >= p_ytd_start 
              AND sf.sale_date <= p_target_date
              AND (p_exclude_company IS NULL OR p_exclude_company = '' OR sf.brand_id IS NULL OR sf.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb))
              AND (p_depot_name IS NULL OR p_depot_name = '' OR LOWER(gl.depot_name) = LOWER(p_depot_name))
            GROUP BY sf.licensee_id
        )
        SELECT 
            gl.licensee_id,
            gl.licensee_name::TEXT,
            COALESCE(gl.trade, 'Off')::TEXT AS trade,
            CASE WHEN gl.depot_name IS NOT NULL THEN ARRAY[gl.depot_name::TEXT] ELSE ARRAY[]::TEXT[] END AS licensee_depots,
            ROUND(COALESCE(ls.daily_cases, 0.0), 2)::NUMERIC   AS daily_cases,
            ROUND(COALESCE(ls.daily_bottles, 0.0), 2)::NUMERIC AS daily_bottles,
            ROUND(COALESCE(ls.mtd_cases, 0.0), 2)::NUMERIC     AS mtd_cases,
            ROUND(COALESCE(ls.mtd_bottles, 0.0), 2)::NUMERIC   AS mtd_bottles,
            ROUND(COALESCE(ls.ytd_cases, 0.0), 2)::NUMERIC     AS ytd_cases,
            ROUND(COALESCE(ls.ytd_bottles, 0.0), 2)::NUMERIC   AS ytd_bottles,
            ROUND(COALESCE(ls.mtd_cases, 0.0), 2)::NUMERIC     AS total_cases,
            ROUND(COALESCE(ls.mtd_bottles, 0.0), 2)::NUMERIC   AS total_bottles
        FROM group_lics gl
        LEFT JOIN lic_sales ls ON gl.licensee_id = ls.licensee_id
        WHERE (p_depot_name IS NULL OR p_depot_name = '') OR LOWER(gl.depot_name) = LOWER(p_depot_name)
        ORDER BY mtd_cases DESC
    ) lic INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO anon;


-- ── 3. RPC Function: get_licensee_brand_sales_summary_json ──────────────────
CREATE OR REPLACE FUNCTION public.get_licensee_brand_sales_summary_json(
    p_licensee_id UUID,
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_depot_name TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_agg(bs) FROM (
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
            b.brand_id AS brand_id,
            b.brand_name::TEXT AS brand_name,
            COALESCE(c.company_name, 'Other')::TEXT AS company_name,
            ROUND(SUM(CASE WHEN sf.sale_date = p_target_date THEN sf.total_case ELSE 0 END), 2)::NUMERIC AS daily_cases,
            ROUND(SUM(CASE WHEN sf.sale_date = p_target_date THEN sf.total_btl ELSE 0 END), 2)::NUMERIC  AS daily_bottles,
            ROUND(SUM(CASE WHEN sf.sale_date >= p_mtd_start THEN sf.total_case ELSE 0 END), 2)::NUMERIC   AS mtd_cases,
            ROUND(SUM(CASE WHEN sf.sale_date >= p_mtd_start THEN sf.total_btl ELSE 0 END), 2)::NUMERIC    AS mtd_bottles,
            ROUND(SUM(sf.total_case), 2)::NUMERIC                                                         AS ytd_cases,
            ROUND(SUM(sf.total_btl), 2)::NUMERIC                                                          AS ytd_bottles,
            ROUND(SUM(CASE WHEN sf.sale_date >= p_mtd_start THEN sf.total_case ELSE 0 END), 2)::NUMERIC   AS total_cases,
            ROUND(SUM(CASE WHEN sf.sale_date >= p_mtd_start THEN sf.total_btl ELSE 0 END), 2)::NUMERIC    AS total_bottles,
            CASE WHEN li.depot_name IS NOT NULL THEN ARRAY[li.depot_name::TEXT] ELSE ARRAY[]::TEXT[] END AS sales_depots
        FROM public.sales_fact sf
        JOIN public.brands b ON sf.brand_id = b.brand_id
        JOIN public.companies c ON b.company_id = c.company_id
        LEFT JOIN lic_info li ON sf.licensee_id = li.licensee_id
        WHERE sf.licensee_id = p_licensee_id
          AND sf.sale_date >= p_ytd_start 
          AND sf.sale_date <= p_target_date
          AND (p_exclude_company IS NULL OR p_exclude_company = '' OR sf.brand_id IS NULL OR sf.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb))
          AND (p_depot_name IS NULL OR p_depot_name = '' OR LOWER(li.depot_name) = LOWER(p_depot_name))
        GROUP BY b.brand_id, b.brand_name, c.company_name, li.depot_name
        ORDER BY mtd_cases DESC
    ) bs INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO anon;
