-- Migration: 016_group_and_licensee_counts.sql
-- Description: Update get_cascading_groups_summary_json and get_group_licensees_summary_json to compute exact total_licensees and total_brands for every group card and licensee card.

-- 1. get_cascading_groups_summary_json
CREATE OR REPLACE FUNCTION public.get_cascading_groups_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_hq_name     TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
BEGIN
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

-- 2. get_group_licensees_summary_json
CREATE OR REPLACE FUNCTION public.get_group_licensees_summary_json(
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
BEGIN
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
          AND (COALESCE(m_l.mtd_cases, 0) > 0 OR COALESCE(d_l.daily_cases, 0) > 0)
        ORDER BY COALESCE(d_l.daily_cases, 0) DESC, COALESCE(m_l.mtd_cases, 0) DESC, l.licensee_name ASC
    ) lic;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;
