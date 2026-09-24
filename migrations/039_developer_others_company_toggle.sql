-- Migration: 039_developer_others_company_toggle.sql
-- Purpose: Implement developer-controlled "Others" company inclusion toggle infrastructure.
-- Ensures single source of truth (system_settings -> include_others_in_sales) with default TRUE.
-- Evaluates setting ONCE per RPC execution (v_include_others) for optimal EXPLAIN ANALYZE performance.

-- 1. Create System Settings Table if not exists
CREATE TABLE IF NOT EXISTS public.system_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Insert Default Setting for include_others_in_sales
INSERT INTO public.system_settings (setting_key, setting_value, description)
VALUES (
    'include_others_in_sales',
    'true',
    'When true, company Others data is included in sales calculations across all analytics, RPCs, and APIs. When false, Others is excluded.'
)
ON CONFLICT (setting_key) DO NOTHING;

-- 2. Audit Log Table for System Settings Changes
CREATE TABLE IF NOT EXISTS public.system_settings_audit_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    setting_key VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT NOT NULL,
    changed_by_user_id UUID,
    changed_by_email TEXT,
    source TEXT DEFAULT 'Admin Portal',
    changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS on Audit Log Table
ALTER TABLE IF EXISTS public.system_settings_audit_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow authenticated read on system_settings_audit_log" ON public.system_settings_audit_log;
CREATE POLICY "Allow authenticated read on system_settings_audit_log" ON public.system_settings_audit_log
    FOR SELECT USING (auth.role() = 'service_role' OR EXISTS (
        SELECT 1 FROM public.user_roles ur
        JOIN public.roles r ON ur.role_id = r.role_id
        WHERE ur.user_id = auth.uid()
          AND LOWER(r.role_name) = 'developer'
          AND ur.is_active = true
    ));

-- 3. Central PostgreSQL Helper Function for Others Inclusion
CREATE OR REPLACE FUNCTION public.get_include_others_in_sales()
RETURNS boolean
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_val TEXT;
BEGIN
    SELECT setting_value INTO v_val
    FROM public.system_settings
    WHERE setting_key = 'include_others_in_sales';

    RETURN COALESCE(LOWER(TRIM(v_val)) = 'true', true);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_include_others_in_sales() TO authenticated, service_role, anon;

-- 4. Update get_mobile_companies_summary
DROP FUNCTION IF EXISTS public.get_mobile_companies_summary(DATE, DATE, DATE, UUID);
DROP FUNCTION IF EXISTS public.get_mobile_companies_summary(DATE, DATE, DATE, UUID, TEXT);

CREATE OR REPLACE FUNCTION public.get_mobile_companies_summary(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_hq_id       UUID DEFAULT NULL
)
RETURNS TABLE (
    company_id      UUID,
    company_name    TEXT,
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
        sds.company_id,
        COALESCE(c.company_name, 'Other')::TEXT AS company_name,
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
    LEFT JOIN public.companies c ON sds.company_id = c.company_id
    LEFT JOIN public.depots d ON sds.depot_id = d.depot_id
    LEFT JOIN public.offices o ON d.office_id = o.office_id
    WHERE sds.sale_date >= p_ytd_start
      AND sds.sale_date <= p_target_date
      AND (p_hq_id IS NULL OR o.headquarters_id = p_hq_id OR (o.headquarters_id IS NULL AND sds.headquarters_id = p_hq_id))
      AND (
          v_include_others = true
          OR c.company_name IS NULL
          OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other')
      )
    GROUP BY sds.company_id, c.company_name;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_companies_summary(DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;

-- 5. Update get_mobile_company_brands_summary
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
    WHERE sds.sale_date >= p_ytd_start
      AND sds.sale_date <= p_target_date
      AND sds.company_id = ANY(p_company_ids)
      AND (p_hq_id IS NULL OR sds.headquarters_id = p_hq_id)
      AND (
          v_include_others = true
          OR c.company_name IS NULL
          OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other')
      )
    GROUP BY sds.brand_id, b.brand_name, sds.company_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_company_brands_summary(UUID[], DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;

-- 6. Update get_cascading_groups_summary_json
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
BEGIN
    v_include_others := public.get_include_others_in_sales();

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

GRANT EXECUTE ON FUNCTION public.get_cascading_groups_summary_json(DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

-- 7. Update get_group_licensees_summary_json
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
BEGIN
    v_include_others := public.get_include_others_in_sales();

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
            COALESCE(lbc.total_brands, 0)                         AS total_brands,
            COALESCE(ROUND(d_lic.daily_cases::numeric, 2), 0.0)   AS daily_cases,
            COALESCE(ROUND(d_lic.daily_bottles::numeric, 2), 0.0) AS daily_bottles,
            COALESCE(ROUND(m_lic.mtd_cases::numeric, 2), 0.0)     AS mtd_cases,
            COALESCE(ROUND(m_lic.mtd_bottles::numeric, 2), 0.0)   AS mtd_bottles,
            COALESCE(ROUND(m_lic.mtd_cases::numeric, 2), 0.0)     AS ytd_cases,
            COALESCE(ROUND(m_lic.mtd_bottles::numeric, 2), 0.0)   AS ytd_bottles,
            COALESCE(ROUND(m_lic.mtd_cases::numeric, 2), 0.0)     AS total_cases,
            COALESCE(ROUND(m_lic.mtd_bottles::numeric, 2), 0.0)   AS total_bottles
        FROM public.licensees l
        LEFT JOIN lic_brand_counts lbc ON l.licensee_id = lbc.licensee_id
        LEFT JOIN daily_lics d_lic ON l.licensee_id = d_lic.licensee_id
        LEFT JOIN mtd_lics m_lic   ON l.licensee_id = m_lic.licensee_id
        WHERE l.group_id = p_group_id AND l.is_active = true
          AND (
              COALESCE(m_lic.mtd_cases, 0) > 0 OR
              COALESCE(d_lic.daily_cases, 0) > 0
          )
        ORDER BY COALESCE(d_lic.daily_cases, 0) DESC, COALESCE(m_lic.mtd_cases, 0) DESC, l.licensee_name ASC
    ) lic;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

-- 8. Update get_group_brand_sales_summary_json
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
BEGIN
    v_include_others := public.get_include_others_in_sales();

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
        WHERE (
            v_include_others = true
            OR c.company_name IS NULL
            OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other')
        )
        ORDER BY COALESCE(d_b.daily_cases, 0) DESC, COALESCE(m_b.mtd_cases, 0) DESC, b.brand_name ASC
    ) bs;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_group_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

-- 9. Update get_licensee_brand_sales_summary_json
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
BEGIN
    v_include_others := public.get_include_others_in_sales();

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

-- 10. Update get_mobile_sales_summary_json
CREATE OR REPLACE FUNCTION public.get_mobile_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_hq_id       UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_include_others BOOLEAN;
    v_comp_json  JSONB;
    v_depot_json JSONB;
BEGIN
    v_include_others := public.get_include_others_in_sales();

    -- 1. Aggregated Companies
    SELECT COALESCE(jsonb_agg(row_to_json(comp_row)::jsonb), '[]'::jsonb)
    INTO v_comp_json
    FROM (
        SELECT
            sds.company_id,
            COALESCE(c.company_name, 'Other')::TEXT AS company_name,
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
        LEFT JOIN public.companies c ON sds.company_id = c.company_id
        WHERE sds.sale_date >= p_ytd_start
          AND sds.sale_date <= p_target_date
          AND (p_hq_id IS NULL OR sds.headquarters_id = p_hq_id)
          AND (
              v_include_others = true
              OR c.company_name IS NULL
              OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other')
          )
        GROUP BY sds.company_id, c.company_name
    ) comp_row;

    -- 2. Aggregated Depots & Brands under HQ
    SELECT COALESCE(jsonb_agg(row_to_json(depot_row)::jsonb), '[]'::jsonb)
    INTO v_depot_json
    FROM (
        SELECT
            sds.depot_id,
            sds.headquarters_id,
            sds.brand_id,
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
        LEFT JOIN public.companies c ON sds.company_id = c.company_id
        WHERE sds.sale_date >= p_ytd_start
          AND sds.sale_date <= p_target_date
          AND (p_hq_id IS NULL OR sds.headquarters_id = p_hq_id)
          AND (
              v_include_others = true
              OR c.company_name IS NULL
              OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other')
          )
        GROUP BY sds.depot_id, sds.headquarters_id, sds.brand_id
    ) depot_row;

    RETURN jsonb_build_object(
        'companies', v_comp_json,
        'depots',    v_depot_json
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_sales_summary_json(DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;

-- 11. Update get_mobile_tsm_sales_summary_json
CREATE OR REPLACE FUNCTION public.get_mobile_tsm_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_include_others BOOLEAN;
    v_result JSONB;
BEGIN
    v_include_others := public.get_include_others_in_sales();

    SELECT jsonb_agg(row_to_json(tsm_row)::jsonb)
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
        LEFT JOIN public.companies c ON usf.company_id = c.company_id
        WHERE usf.sale_date >= p_ytd_start
          AND usf.sale_date <= p_target_date
          AND (
              v_include_others = true
              OR c.company_name IS NULL
              OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other')
          )
        GROUP BY usf.user_id, usf.company_id, usf.brand_id
    ) tsm_row;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE) TO authenticated, service_role, anon;

-- 12. Update get_mobile_sales_summary (table returning)
CREATE OR REPLACE FUNCTION public.get_mobile_sales_summary(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE
)
RETURNS TABLE (
    company_id    UUID,
    brand_id      UUID,
    depot_id      UUID,
    daily_cases   NUMERIC,
    daily_bottles NUMERIC,
    daily_bl      NUMERIC,
    mtd_cases     NUMERIC,
    mtd_bottles   NUMERIC,
    mtd_bl        NUMERIC,
    ytd_cases     NUMERIC,
    ytd_bottles   NUMERIC,
    ytd_bl        NUMERIC
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_include_others BOOLEAN;
BEGIN
    v_include_others := public.get_include_others_in_sales();

    RETURN QUERY
    SELECT
        sds.company_id,
        sds.brand_id,
        sds.depot_id,
        ROUND(SUM(CASE WHEN sds.sale_date = p_target_date  THEN sds.total_cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
        ROUND(SUM(CASE WHEN sds.sale_date = p_target_date  THEN sds.total_bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
        ROUND(SUM(CASE WHEN sds.sale_date = p_target_date  THEN sds.total_bl      ELSE 0 END), 2)::NUMERIC AS daily_bl,
        ROUND(SUM(CASE WHEN sds.sale_date >= p_mtd_start   THEN sds.total_cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
        ROUND(SUM(CASE WHEN sds.sale_date >= p_mtd_start   THEN sds.total_bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
        ROUND(SUM(CASE WHEN sds.sale_date >= p_mtd_start   THEN sds.total_bl      ELSE 0 END), 2)::NUMERIC AS mtd_bl,
        ROUND(SUM(sds.total_cases), 2)::NUMERIC                                                             AS ytd_cases,
        ROUND(SUM(sds.total_bottles), 2)::NUMERIC                                                           AS ytd_bottles,
        ROUND(SUM(sds.total_bl), 2)::NUMERIC                                                              AS ytd_bl
    FROM public.sales_daily_summary sds
    LEFT JOIN public.companies c ON sds.company_id = c.company_id
    WHERE sds.sale_date >= p_ytd_start
      AND sds.sale_date <= p_target_date
      AND (
          v_include_others = true
          OR c.company_name IS NULL
          OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other')
      )
    GROUP BY sds.company_id, sds.brand_id, sds.depot_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_sales_summary(DATE, DATE, DATE) TO authenticated, service_role, anon;

-- 13. Update get_mobile_tsm_sales_summary (table returning)
CREATE OR REPLACE FUNCTION public.get_mobile_tsm_sales_summary(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE
)
RETURNS TABLE (
    user_id       UUID,
    company_id    UUID,
    brand_id      UUID,
    daily_cases   NUMERIC,
    daily_bottles NUMERIC,
    daily_bl      NUMERIC,
    mtd_cases     NUMERIC,
    mtd_bottles   NUMERIC,
    mtd_bl        NUMERIC,
    ytd_cases     NUMERIC,
    ytd_bottles   NUMERIC,
    ytd_bl        NUMERIC
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_include_others BOOLEAN;
BEGIN
    v_include_others := public.get_include_others_in_sales();

    RETURN QUERY
    SELECT
        usf.user_id,
        usf.company_id,
        usf.brand_id,
        ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
        ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
        ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.bl ELSE 0 END), 2)::NUMERIC      AS daily_bl,
        ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
        ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
        ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.bl ELSE 0 END), 2)::NUMERIC      AS mtd_bl,
        ROUND(SUM(usf.cases), 2)::NUMERIC                                                             AS ytd_cases,
        ROUND(SUM(usf.bottles), 2)::NUMERIC                                                           AS ytd_bottles,
        ROUND(SUM(usf.bl), 2)::NUMERIC                                                              AS ytd_bl
    FROM public.user_sales_fact usf
    LEFT JOIN public.companies c ON usf.company_id = c.company_id
    WHERE usf.sale_date >= p_ytd_start
      AND usf.sale_date <= p_target_date
      AND (
          v_include_others = true
          OR c.company_name IS NULL
          OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other')
      )
    GROUP BY usf.user_id, usf.company_id, usf.brand_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_tsm_sales_summary(DATE, DATE, DATE) TO authenticated, service_role, anon;
