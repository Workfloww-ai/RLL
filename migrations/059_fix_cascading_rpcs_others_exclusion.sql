-- Migration 059: Fix cascading RPCs to respect Others toggle parameter and exclude competitor brands
--
-- Target DB: test_db (wgpxmvrbbgpzkomdutlk) -> staging verification -> live_db upon confirmation.

-- ── 1. get_cascading_groups_summary_json ──────────────────────────────────────────
DROP FUNCTION IF EXISTS public.get_cascading_groups_summary_json(DATE, DATE, DATE, TEXT, TEXT);
CREATE OR REPLACE FUNCTION public.get_cascading_groups_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_hq_name     TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_include_others BOOLEAN;
    v_result JSONB;
    v_hq_id UUID := NULL;
BEGIN
    -- If caller explicitly passed p_exclude_company as 'Others' or non-empty, honor caller's parameter!
    IF p_exclude_company IS NOT NULL AND TRIM(p_exclude_company) != '' THEN
        v_include_others := false;
    ELSE
        v_include_others := public.get_include_others_in_sales();
    END IF;

    IF p_hq_name IS NOT NULL AND TRIM(p_hq_name) != '' AND TRIM(p_hq_name) != 'All Headquarters' THEN
        SELECT headquarters_id INTO v_hq_id
        FROM public.headquarters
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(p_hq_name))
           OR LOWER(TRIM(name)) ILIKE '%' || LOWER(TRIM(p_hq_name)) || '%'
        LIMIT 1;

        IF v_hq_id IS NULL THEN
            SELECT headquarters_id INTO v_hq_id
            FROM public.depots
            WHERE LOWER(TRIM(name)) = LOWER(TRIM(p_hq_name))
               OR LOWER(TRIM(name)) ILIKE '%' || LOWER(TRIM(p_hq_name)) || '%'
            LIMIT 1;
        END IF;
    END IF;

    SELECT jsonb_agg(row_to_json(grp)::jsonb) INTO v_result FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE v_include_others = false
              AND (
                  LOWER(TRIM(c.company_name)) IN ('others', 'other', 'others company', 'other company')
                  OR LOWER(TRIM(c.company_name)) LIKE 'others %'
                  OR LOWER(TRIM(c.company_name)) LIKE 'other %'
                  OR LOWER(TRIM(c.company_name)) LIKE 'comp_%'
                  OR LOWER(TRIM(c.company_name)) LIKE 'comp %'
                  OR LOWER(TRIM(COALESCE(c.category, ''))) = 'others'
              )
        ),
        group_brand_counts AS (
            SELECT
                sds.group_id,
                COUNT(DISTINCT sds.brand_id)    AS total_brands,
                COUNT(DISTINCT sds.licensee_id) AS total_licensees
            FROM public.sales_daily_summary sds
            LEFT JOIN excluded_brands eb ON sds.brand_id = eb.brand_id
            WHERE sds.sale_date >= p_mtd_start
              AND sds.sale_date <= p_target_date
              AND sds.group_id IS NOT NULL
              AND eb.brand_id IS NULL
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id OR sds.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
            GROUP BY sds.group_id
        ),
        daily_agg AS (
            SELECT
                sds.group_id,
                SUM(sds.total_cases)   AS daily_cases,
                SUM(sds.total_bottles) AS daily_bottles
            FROM public.sales_daily_summary sds
            LEFT JOIN excluded_brands eb ON sds.brand_id = eb.brand_id
            WHERE sds.sale_date = p_target_date
              AND sds.group_id IS NOT NULL
              AND eb.brand_id IS NULL
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id OR sds.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
            GROUP BY sds.group_id
        ),
        mtd_agg AS (
            SELECT
                sds.group_id,
                SUM(sds.total_cases)   AS mtd_cases,
                SUM(sds.total_bottles) AS mtd_bottles
            FROM public.sales_daily_summary sds
            LEFT JOIN excluded_brands eb ON sds.brand_id = eb.brand_id
            WHERE sds.sale_date >= p_mtd_start
              AND sds.sale_date <= p_target_date
              AND sds.group_id IS NOT NULL
              AND eb.brand_id IS NULL
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id OR sds.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
            GROUP BY sds.group_id
        ),
        group_lic_fallback AS (
            SELECT
                l.group_id,
                COUNT(DISTINCT l.licensee_id) AS total_licensees
            FROM public.licensees l
            WHERE l.is_active = true AND l.group_id IS NOT NULL
              AND (v_hq_id IS NULL OR l.headquarters_id = v_hq_id OR l.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
            GROUP BY l.group_id
        )
        SELECT
            g.group_id,
            g.group_name,
            COALESCE(gbc.total_licensees, glf.total_licensees, 0) AS total_licensees,
            COALESCE(gbc.total_brands, 0)                         AS total_brands,
            COALESCE(ROUND(d_agg.daily_cases::numeric, 2), 0.0)   AS daily_cases,
            COALESCE(ROUND(d_agg.daily_bottles::numeric, 2), 0.0) AS daily_bottles,
            COALESCE(ROUND(m_agg.mtd_cases::numeric, 2), 0.0)     AS mtd_cases,
            COALESCE(ROUND(m_agg.mtd_bottles::numeric, 2), 0.0)   AS mtd_bottles,
            COALESCE(ROUND(m_agg.mtd_cases::numeric, 2), 0.0)     AS ytd_cases,
            COALESCE(ROUND(m_agg.mtd_bottles::numeric, 2), 0.0)   AS ytd_bottles,
            COALESCE(ROUND(m_agg.mtd_cases::numeric, 2), 0.0)     AS total_cases,
            COALESCE(ROUND(m_agg.mtd_cases::numeric, 2), 0.0)     AS total_bottles
        FROM public.groups g
        LEFT JOIN group_brand_counts gbc ON g.group_id = gbc.group_id
        LEFT JOIN group_lic_fallback glf ON g.group_id = glf.group_id
        LEFT JOIN daily_agg d_agg ON g.group_id = d_agg.group_id
        LEFT JOIN mtd_agg m_agg   ON g.group_id = m_agg.group_id
        WHERE g.is_active = true
          AND (
              COALESCE(m_agg.mtd_cases, 0) > 0 OR
              COALESCE(d_agg.daily_cases, 0) > 0
          )
        ORDER BY COALESCE(d_agg.daily_cases, 0) DESC, COALESCE(m_agg.mtd_cases, 0) DESC, g.group_name ASC
    ) grp;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_cascading_groups_summary_json(DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

-- ── 2. get_group_brand_sales_summary_json ─────────────────────────────────────────
DROP FUNCTION IF EXISTS public.get_group_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT);
CREATE OR REPLACE FUNCTION public.get_group_brand_sales_summary_json(
    p_group_id        UUID,
    p_target_date     DATE,
    p_mtd_start       DATE,
    p_ytd_start       DATE,
    p_depot_name      TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_include_others BOOLEAN;
    v_result JSONB;
    v_hq_id UUID := NULL;
BEGIN
    IF p_exclude_company IS NOT NULL AND TRIM(p_exclude_company) != '' THEN
        v_include_others := false;
    ELSE
        v_include_others := public.get_include_others_in_sales();
    END IF;

    IF p_depot_name IS NOT NULL AND TRIM(p_depot_name) != '' AND TRIM(p_depot_name) != 'All Headquarters' THEN
        SELECT headquarters_id INTO v_hq_id
        FROM public.headquarters
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(p_depot_name))
           OR LOWER(TRIM(name)) ILIKE '%' || LOWER(TRIM(p_depot_name)) || '%'
        LIMIT 1;

        IF v_hq_id IS NULL THEN
            SELECT headquarters_id INTO v_hq_id
            FROM public.depots
            WHERE LOWER(TRIM(name)) = LOWER(TRIM(p_depot_name))
               OR LOWER(TRIM(name)) ILIKE '%' || LOWER(TRIM(p_depot_name)) || '%'
            LIMIT 1;
        END IF;
    END IF;

    SELECT jsonb_agg(row_to_json(bs)::jsonb) INTO v_result FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE v_include_others = false
              AND (
                  LOWER(TRIM(c.company_name)) IN ('others', 'other', 'others company', 'other company')
                  OR LOWER(TRIM(c.company_name)) LIKE 'others %'
                  OR LOWER(TRIM(c.company_name)) LIKE 'other %'
                  OR LOWER(TRIM(c.company_name)) LIKE 'comp_%'
                  OR LOWER(TRIM(c.company_name)) LIKE 'comp %'
                  OR LOWER(TRIM(COALESCE(c.category, ''))) = 'others'
              )
        ),
        daily_brands AS (
            SELECT
                sds.brand_id,
                SUM(sds.total_cases)   AS daily_cases,
                SUM(sds.total_bottles) AS daily_bottles
            FROM public.sales_daily_summary sds
            LEFT JOIN excluded_brands eb ON sds.brand_id = eb.brand_id
            WHERE sds.group_id = p_group_id
              AND sds.sale_date = p_target_date
              AND eb.brand_id IS NULL
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id OR sds.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
            GROUP BY sds.brand_id
        ),
        mtd_brands AS (
            SELECT
                sds.brand_id,
                SUM(sds.total_cases)   AS mtd_cases,
                SUM(sds.total_bottles) AS mtd_bottles
            FROM public.sales_daily_summary sds
            LEFT JOIN excluded_brands eb ON sds.brand_id = eb.brand_id
            WHERE sds.group_id = p_group_id
              AND sds.sale_date >= p_mtd_start
              AND sds.sale_date <= p_target_date
              AND eb.brand_id IS NULL
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id OR sds.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
            GROUP BY sds.brand_id
        )
        SELECT
            b.brand_id,
            b.brand_name,
            c.company_name,
            COALESCE(ROUND(d_b.daily_cases::numeric, 2), 0.0)   AS daily_cases,
            COALESCE(ROUND(d_b.daily_bottles::numeric, 2), 0.0) AS daily_bottles,
            COALESCE(ROUND(m_b.mtd_cases::numeric, 2), 0.0)     AS mtd_cases,
            COALESCE(ROUND(m_b.mtd_bottles::numeric, 2), 0.0)   AS mtd_bottles,
            COALESCE(ROUND(m_b.mtd_cases::numeric, 2), 0.0)     AS ytd_cases,
            COALESCE(ROUND(m_b.mtd_bottles::numeric, 2), 0.0)   AS ytd_bottles,
            COALESCE(ROUND(m_b.mtd_cases::numeric, 2), 0.0)     AS total_cases,
            COALESCE(ROUND(m_b.mtd_bottles::numeric, 2), 0.0)   AS total_bottles
        FROM public.brands b
        JOIN public.companies c ON b.company_id = c.company_id
        LEFT JOIN daily_brands d_b ON b.brand_id = d_b.brand_id
        LEFT JOIN mtd_brands m_b   ON b.brand_id = m_b.brand_id
        WHERE (COALESCE(m_b.mtd_cases, 0) > 0 OR COALESCE(d_b.daily_cases, 0) > 0)
          AND (
              v_include_others = true
              OR b.brand_id NOT IN (SELECT brand_id FROM excluded_brands)
          )
        ORDER BY COALESCE(d_b.daily_cases, 0) DESC, COALESCE(m_b.mtd_cases, 0) DESC, b.brand_name ASC
    ) bs;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_group_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

-- ── 3. get_group_licensees_summary_json ───────────────────────────────────────────
DROP FUNCTION IF EXISTS public.get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT);
CREATE OR REPLACE FUNCTION public.get_group_licensees_summary_json(
    p_group_id        UUID,
    p_target_date     DATE,
    p_mtd_start       DATE,
    p_ytd_start       DATE,
    p_depot_name      TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_include_others BOOLEAN;
    v_result JSONB;
    v_hq_id UUID := NULL;
BEGIN
    IF p_exclude_company IS NOT NULL AND TRIM(p_exclude_company) != '' THEN
        v_include_others := false;
    ELSE
        v_include_others := public.get_include_others_in_sales();
    END IF;

    IF p_depot_name IS NOT NULL AND TRIM(p_depot_name) != '' AND TRIM(p_depot_name) != 'All Headquarters' THEN
        SELECT headquarters_id INTO v_hq_id
        FROM public.headquarters
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(p_depot_name))
           OR LOWER(TRIM(name)) ILIKE '%' || LOWER(TRIM(p_depot_name)) || '%'
        LIMIT 1;

        IF v_hq_id IS NULL THEN
            SELECT headquarters_id INTO v_hq_id
            FROM public.depots
            WHERE LOWER(TRIM(name)) = LOWER(TRIM(p_depot_name))
               OR LOWER(TRIM(name)) ILIKE '%' || LOWER(TRIM(p_depot_name)) || '%'
            LIMIT 1;
        END IF;
    END IF;

    SELECT jsonb_agg(row_to_json(lic)::jsonb) INTO v_result FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE v_include_others = false
              AND (
                  LOWER(TRIM(c.company_name)) IN ('others', 'other', 'others company', 'other company')
                  OR LOWER(TRIM(c.company_name)) LIKE 'others %'
                  OR LOWER(TRIM(c.company_name)) LIKE 'other %'
                  OR LOWER(TRIM(c.company_name)) LIKE 'comp_%'
                  OR LOWER(TRIM(c.company_name)) LIKE 'comp %'
                  OR LOWER(TRIM(COALESCE(c.category, ''))) = 'others'
              )
        ),
        lic_brand_counts AS (
            SELECT
                sds.licensee_id,
                COUNT(DISTINCT sds.brand_id) AS total_brands
            FROM public.sales_daily_summary sds
            LEFT JOIN excluded_brands eb ON sds.brand_id = eb.brand_id
            WHERE sds.group_id = p_group_id
              AND sds.sale_date >= p_mtd_start
              AND sds.sale_date <= p_target_date
              AND eb.brand_id IS NULL
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id OR sds.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
            GROUP BY sds.licensee_id
        ),
        daily_lics AS (
            SELECT
                sds.licensee_id,
                SUM(sds.total_cases)   AS daily_cases,
                SUM(sds.total_bottles) AS daily_bottles
            FROM public.sales_daily_summary sds
            LEFT JOIN excluded_brands eb ON sds.brand_id = eb.brand_id
            WHERE sds.group_id = p_group_id
              AND sds.sale_date = p_target_date
              AND eb.brand_id IS NULL
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id OR sds.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
            GROUP BY sds.licensee_id
        ),
        mtd_lics AS (
            SELECT
                sds.licensee_id,
                SUM(sds.total_cases)   AS mtd_cases,
                SUM(sds.total_bottles) AS mtd_bottles
            FROM public.sales_daily_summary sds
            LEFT JOIN excluded_brands eb ON sds.brand_id = eb.brand_id
            WHERE sds.group_id = p_group_id
              AND sds.sale_date >= p_mtd_start
              AND sds.sale_date <= p_target_date
              AND eb.brand_id IS NULL
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id OR sds.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
            GROUP BY sds.licensee_id
        )
        SELECT
            l.licensee_id,
            l.licensee_name,
            d.name AS depot_name,
            COALESCE(lbc.total_brands, 0)                       AS total_brands,
            COALESCE(ROUND(d_l.daily_cases::numeric, 2), 0.0)   AS daily_cases,
            COALESCE(ROUND(d_l.daily_bottles::numeric, 2), 0.0) AS daily_bottles,
            COALESCE(ROUND(m_l.mtd_cases::numeric, 2), 0.0)     AS mtd_cases,
            COALESCE(ROUND(m_l.mtd_bottles::numeric, 2), 0.0)   AS mtd_bottles,
            COALESCE(ROUND(m_l.mtd_cases::numeric, 2), 0.0)     AS ytd_cases,
            COALESCE(ROUND(m_l.mtd_bottles::numeric, 2), 0.0)   AS ytd_bottles,
            COALESCE(ROUND(m_l.mtd_cases::numeric, 2), 0.0)     AS total_cases,
            COALESCE(ROUND(m_l.mtd_cases::numeric, 2), 0.0)     AS total_bottles
        FROM public.licensees l
        LEFT JOIN public.depots d ON l.depot_id = d.depot_id
        LEFT JOIN lic_brand_counts lbc ON l.licensee_id = lbc.licensee_id
        LEFT JOIN daily_lics d_l ON l.licensee_id = d_l.licensee_id
        LEFT JOIN mtd_lics m_l   ON l.licensee_id = m_l.licensee_id
        WHERE l.group_id = p_group_id
          AND (v_hq_id IS NULL OR l.headquarters_id = v_hq_id OR l.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
          AND (COALESCE(m_l.mtd_cases, 0) > 0 OR COALESCE(d_l.daily_cases, 0) > 0)
        ORDER BY COALESCE(d_l.daily_cases, 0) DESC, COALESCE(m_l.mtd_cases, 0) DESC, l.licensee_name ASC
    ) lic;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

-- ── 4. get_licensee_brand_sales_summary_json ──────────────────────────────────────
DROP FUNCTION IF EXISTS public.get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT);
CREATE OR REPLACE FUNCTION public.get_licensee_brand_sales_summary_json(
    p_licensee_id UUID,
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_depot_name  TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_include_others BOOLEAN;
    v_result JSONB;
    v_hq_id UUID := NULL;
BEGIN
    IF p_exclude_company IS NOT NULL AND TRIM(p_exclude_company) != '' THEN
        v_include_others := false;
    ELSE
        v_include_others := public.get_include_others_in_sales();
    END IF;

    IF p_depot_name IS NOT NULL AND TRIM(p_depot_name) != '' AND TRIM(p_depot_name) != 'All Headquarters' THEN
        SELECT headquarters_id INTO v_hq_id
        FROM public.headquarters
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(p_depot_name))
           OR LOWER(TRIM(name)) ILIKE '%' || LOWER(TRIM(p_depot_name)) || '%'
        LIMIT 1;

        IF v_hq_id IS NULL THEN
            SELECT headquarters_id INTO v_hq_id
            FROM public.depots
            WHERE LOWER(TRIM(name)) = LOWER(TRIM(p_depot_name))
               OR LOWER(TRIM(name)) ILIKE '%' || LOWER(TRIM(p_depot_name)) || '%'
            LIMIT 1;
        END IF;
    END IF;

    SELECT jsonb_agg(row_to_json(bs)::jsonb) INTO v_result FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE v_include_others = false
              AND (
                  LOWER(TRIM(c.company_name)) IN ('others', 'other', 'others company', 'other company')
                  OR LOWER(TRIM(c.company_name)) LIKE 'others %'
                  OR LOWER(TRIM(c.company_name)) LIKE 'other %'
                  OR LOWER(TRIM(c.company_name)) LIKE 'comp_%'
                  OR LOWER(TRIM(c.company_name)) LIKE 'comp %'
                  OR LOWER(TRIM(COALESCE(c.category, ''))) = 'others'
              )
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
          AND (v_hq_id IS NULL OR sf.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
          AND (
              v_include_others = true
              OR b.brand_id NOT IN (SELECT brand_id FROM excluded_brands)
          )
        GROUP BY b.brand_id, b.brand_name, c.company_name, li.depot_name
        ORDER BY mtd_cases DESC NULLS LAST
    ) bs;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

