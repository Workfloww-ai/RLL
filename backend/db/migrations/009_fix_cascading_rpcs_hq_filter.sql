-- Migration: 009_fix_cascading_rpcs_hq_filter.sql
-- Description: Add strict Headquarters filtering (p_hq_name / p_depot_name) to all 4 cascading summary RPCs 
-- and refresh sales_monthly_summary to align with corrected sales_daily_summary HQ assignments.

-- 1. Refresh sales_monthly_summary for July 2026
SELECT public.refresh_sales_monthly_summary_for_month('2026-07-01');

-- 2. Update get_cascading_groups_summary_json
CREATE OR REPLACE FUNCTION public.get_cascading_groups_summary_json(
    p_target_date DATE,
    p_mtd_start DATE,
    p_ytd_start DATE,
    p_hq_name TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE SECURITY DEFINER
AS $$
DECLARE
    v_result JSONB;
    v_hq_id UUID := NULL;
BEGIN
    IF p_hq_name IS NOT NULL AND TRIM(p_hq_name) != '' AND TRIM(p_hq_name) != 'All Headquarters' THEN
        SELECT headquarters_id INTO v_hq_id
        FROM public.headquarters
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(p_hq_name))
           OR LOWER(TRIM(name)) ILIKE '%' || LOWER(TRIM(p_hq_name)) || '%'
        LIMIT 1;
    END IF;

    SELECT jsonb_agg(row_to_json(grp)::jsonb) INTO v_result FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE p_exclude_company IS NOT NULL
              AND p_exclude_company != ''
              AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company))
        ),
        group_lic_counts AS (
            SELECT
                l.group_id,
                COUNT(DISTINCT l.licensee_id) AS total_licensees
            FROM public.licensees l
            WHERE l.is_active = true AND l.group_id IS NOT NULL
              AND (v_hq_id IS NULL OR l.headquarters_id = v_hq_id)
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
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id)
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
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id)
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
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id)
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

-- 3. Update get_group_brand_sales_summary_json
CREATE OR REPLACE FUNCTION public.get_group_brand_sales_summary_json(
    p_group_id UUID,
    p_target_date DATE,
    p_mtd_start DATE,
    p_ytd_start DATE,
    p_depot_name TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE SECURITY DEFINER
AS $$
DECLARE
    v_result JSONB;
    v_hq_id UUID := NULL;
BEGIN
    IF p_depot_name IS NOT NULL AND TRIM(p_depot_name) != '' AND TRIM(p_depot_name) != 'All Headquarters' THEN
        SELECT headquarters_id INTO v_hq_id
        FROM public.headquarters
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(p_depot_name))
           OR LOWER(TRIM(name)) ILIKE '%' || LOWER(TRIM(p_depot_name)) || '%'
        LIMIT 1;
    END IF;

    SELECT jsonb_agg(row_to_json(bs)::jsonb) INTO v_result FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE p_exclude_company IS NOT NULL
              AND p_exclude_company != ''
              AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company))
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
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id)
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
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id)
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

-- 4. Update get_group_licensees_summary_json
CREATE OR REPLACE FUNCTION public.get_group_licensees_summary_json(
    p_group_id UUID,
    p_target_date DATE,
    p_mtd_start DATE,
    p_ytd_start DATE,
    p_depot_name TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE SECURITY DEFINER
AS $$
DECLARE
    v_result JSONB;
    v_hq_id UUID := NULL;
BEGIN
    IF p_depot_name IS NOT NULL AND TRIM(p_depot_name) != '' AND TRIM(p_depot_name) != 'All Headquarters' THEN
        SELECT headquarters_id INTO v_hq_id
        FROM public.headquarters
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(p_depot_name))
           OR LOWER(TRIM(name)) ILIKE '%' || LOWER(TRIM(p_depot_name)) || '%'
        LIMIT 1;
    END IF;

    SELECT jsonb_agg(row_to_json(lic)::jsonb) INTO v_result FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE p_exclude_company IS NOT NULL
              AND p_exclude_company != ''
              AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company))
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
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id)
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
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id)
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
              AND (v_hq_id IS NULL OR sds.headquarters_id = v_hq_id)
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
          AND (v_hq_id IS NULL OR l.headquarters_id = v_hq_id)
          AND (COALESCE(m_l.mtd_cases, 0) > 0 OR COALESCE(d_l.daily_cases, 0) > 0)
        ORDER BY COALESCE(d_l.daily_cases, 0) DESC, COALESCE(m_l.mtd_cases, 0) DESC, l.licensee_name ASC
    ) lic;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

-- Grant permissions
GRANT EXECUTE ON FUNCTION public.get_cascading_groups_summary_json TO authenticated, service_role, anon;
GRANT EXECUTE ON FUNCTION public.get_group_brand_sales_summary_json TO authenticated, service_role, anon;
GRANT EXECUTE ON FUNCTION public.get_group_licensees_summary_json TO authenticated, service_role, anon;
