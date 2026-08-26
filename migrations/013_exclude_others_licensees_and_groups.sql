-- Migration: 013_exclude_others_licensees_and_groups.sql
-- Description: Ensure licensees with 0 non-'Others' brand sales are excluded from group licensee RPC outputs and cascading group summaries.

DROP FUNCTION IF EXISTS get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT);
DROP FUNCTION IF EXISTS get_cascading_groups_summary_json(DATE, DATE, DATE, TEXT, TEXT);

-- 1. Update get_group_licensees_summary_json RPC
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
            SELECT DISTINCT ON (UPPER(REGEXP_REPLACE(REGEXP_REPLACE(TRIM(l.licensee_name), '\s+', ' ', 'g'), '\s*-\s*', '-', 'g')))
                l.licensee_id, 
                UPPER(REGEXP_REPLACE(REGEXP_REPLACE(TRIM(l.licensee_name), '\s+', ' ', 'g'), '\s*-\s*', '-', 'g')) AS licensee_name, 
                l.trade, 
                d.name AS depot_name
            FROM public.licensees l
            LEFT JOIN public.depots d ON l.depot_id = d.depot_id
            WHERE l.group_id = p_group_id AND l.is_active = true
              AND (
                  p_depot_name IS NULL OR p_depot_name = '' OR p_depot_name = 'All Headquarters'
                  OR LOWER(TRIM(d.name)) = LOWER(TRIM(p_depot_name))
              )
              -- Exclude licensees that have NO non-excluded brand sales
              AND EXISTS (
                  SELECT 1 
                  FROM public.sales_monthly_summary sms_chk
                  WHERE sms_chk.licensee_id = l.licensee_id
                    AND (
                        p_exclude_company IS NULL OR p_exclude_company = ''
                        OR sms_chk.brand_id IS NULL
                        OR sms_chk.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
                    )
              )
            ORDER BY 
                UPPER(REGEXP_REPLACE(REGEXP_REPLACE(TRIM(l.licensee_name), '\s+', ' ', 'g'), '\s*-\s*', '-', 'g')),
                l.created_at DESC
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

-- 2. Update get_cascading_groups_summary_json RPC
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
            SELECT DISTINCT ON (l.group_id, UPPER(REGEXP_REPLACE(REGEXP_REPLACE(TRIM(l.licensee_name), '\s+', ' ', 'g'), '\s*-\s*', '-', 'g')))
                l.group_id,
                l.licensee_id,
                d.name AS depot_name
            FROM public.licensees l
            LEFT JOIN public.depots d ON l.depot_id = d.depot_id
            WHERE l.is_active = true
              AND (
                  p_hq_name IS NULL OR p_hq_name = '' OR p_hq_name = 'All Headquarters'
                  OR LOWER(TRIM(d.name)) = LOWER(TRIM(p_hq_name))
              )
              -- Exclude licensees that have NO non-excluded brand sales
              AND EXISTS (
                  SELECT 1 
                  FROM public.sales_monthly_summary sms_chk
                  WHERE sms_chk.licensee_id = l.licensee_id
                    AND (
                        p_exclude_company IS NULL OR p_exclude_company = ''
                        OR sms_chk.brand_id IS NULL
                        OR sms_chk.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
                    )
              )
            ORDER BY 
                l.group_id, 
                UPPER(REGEXP_REPLACE(REGEXP_REPLACE(TRIM(l.licensee_name), '\s+', ' ', 'g'), '\s*-\s*', '-', 'g')),
                l.created_at DESC
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
                  OR sds.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
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
                  OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
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
