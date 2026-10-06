-- Migration: 040_fix_cascading_rpcs_hq_filtering.sql
-- Description: Fix p_hq_name / p_depot_name filtering in all 4 cascading RPC functions so that Group and Licensee sales strictly filter by selected Headquarters.

-- 1. get_cascading_groups_summary_json
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
    v_include_others := public.get_include_others_in_sales();

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
                  (p_exclude_company IS NOT NULL AND p_exclude_company != '' AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company)))
                  OR LOWER(TRIM(c.company_name)) IN ('others', 'other')
              )
        ),
        group_lic_counts AS (
            SELECT
                l.group_id,
                COUNT(DISTINCT l.licensee_id) AS total_licensees
            FROM public.licensees l
            WHERE l.is_active = true AND l.group_id IS NOT NULL
              AND (v_hq_id IS NULL OR l.headquarters_id = v_hq_id OR l.depot_id IN (SELECT depot_id FROM public.depots WHERE headquarters_id = v_hq_id))
            GROUP BY l.group_id
        ),
        group_brand_counts AS (
            SELECT
                sds.group_id,
                COUNT(DISTINCT sds.brand_id) AS total_brands
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
        )
        SELECT
            g.group_id,
            g.group_name,
            COALESCE(glc.total_licensees, 0)                      AS total_licensees,
            COALESCE(gbc.total_brands, 0)                         AS total_brands,
            COALESCE(ROUND(d_agg.daily_cases::numeric, 2), 0.0)   AS daily_cases,
            COALESCE(ROUND(d_agg.daily_bottles::numeric, 2), 0.0) AS daily_bottles,
            COALESCE(ROUND(m_agg.mtd_cases::numeric, 2), 0.0)     AS mtd_cases,
            COALESCE(ROUND(m_agg.mtd_bottles::numeric, 2), 0.0)   AS mtd_bottles,
            COALESCE(ROUND(m_agg.mtd_cases::numeric, 2), 0.0)     AS ytd_cases,
            COALESCE(ROUND(m_agg.mtd_bottles::numeric, 2), 0.0)   AS ytd_bottles,
            COALESCE(ROUND(m_agg.mtd_cases::numeric, 2), 0.0)     AS total_cases,
            COALESCE(ROUND(m_agg.mtd_bottles::numeric, 2), 0.0)   AS total_bottles
        FROM public.groups g
        LEFT JOIN group_lic_counts glc ON g.group_id = glc.group_id
        LEFT JOIN group_brand_counts gbc ON g.group_id = gbc.group_id
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

-- 2. get_group_brand_sales_summary_json
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
    v_include_others := public.get_include_others_in_sales();

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
                  (p_exclude_company IS NOT NULL AND p_exclude_company != '' AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company)))
                  OR LOWER(TRIM(c.company_name)) IN ('others', 'other')
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
        ORDER BY COALESCE(d_b.daily_cases, 0) DESC, COALESCE(m_b.mtd_cases, 0) DESC, b.brand_name ASC
    ) bs;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_group_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

-- 3. get_group_licensees_summary_json
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
    v_include_others := public.get_include_others_in_sales();

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
                  (p_exclude_company IS NOT NULL AND p_exclude_company != '' AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company)))
                  OR LOWER(TRIM(c.company_name)) IN ('others', 'other')
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
            COALESCE(ROUND(m_l.mtd_cases::numeric, 2), 0.0)   AS total_bottles
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

-- 4. get_licensee_brand_sales_summary_json
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
    v_include_others := public.get_include_others_in_sales();

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

    SELECT jsonb_agg(row_to_json(bs)::jsonb) FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE v_include_others = false
              AND (
                  (p_exclude_company IS NOT NULL AND p_exclude_company != '' AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company)))
                  OR LOWER(TRIM(c.company_name)) IN ('others', 'other')
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
              OR sf.brand_id IS NULL
              OR sf.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
          )
        GROUP BY b.brand_id, b.brand_name, c.company_name, li.depot_name
        ORDER BY mtd_cases DESC NULLS LAST
    ) bs INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

-- 5. get_mobile_company_brands_summary
DROP FUNCTION IF EXISTS public.get_mobile_company_brands_summary(UUID[], DATE, DATE, DATE, UUID);
CREATE OR REPLACE FUNCTION public.get_mobile_company_brands_summary(
    p_company_ids  UUID[],
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
AS $$
DECLARE
    v_include_others BOOLEAN;
BEGIN
    v_include_others := public.get_include_others_in_sales();

    RETURN QUERY
    SELECT
        sds.brand_id,
        COALESCE(b.brand_name, 'Generic Brand')::TEXT AS brand_name,
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
    LEFT JOIN public.brands b ON sds.brand_id = b.brand_id
    LEFT JOIN public.companies c ON sds.company_id = c.company_id
    LEFT JOIN public.depots d ON sds.depot_id = d.depot_id
    LEFT JOIN public.offices o ON d.office_id = o.office_id
    WHERE sds.sale_date >= p_ytd_start
      AND sds.sale_date <= p_target_date
      AND sds.company_id = ANY(p_company_ids)
      AND (
          p_hq_id IS NULL 
          OR o.headquarters_id = p_hq_id 
          OR (o.headquarters_id IS NULL AND sds.headquarters_id = p_hq_id)
      )
      AND (
          v_include_others = true
          OR c.company_name IS NULL
          OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other')
      )
    GROUP BY sds.brand_id, b.brand_name, sds.company_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_company_brands_summary(UUID[], DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;

