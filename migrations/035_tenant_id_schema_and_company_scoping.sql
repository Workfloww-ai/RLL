-- Migration 035: Tenant ID Everywhere, User Company Association & Company Sales Scoping
-- Target DB: test_db_RLL (kcwowusanrtvccmipjzu)

-- 1. Ensure public.tenant_config default tenant exists
INSERT INTO public.tenant_config (
    tenant_id,
    tenant_slug,
    app_name,
    logo_url,
    favicon_url,
    splash_screen_url,
    pinned_company_name,
    excluded_companies,
    is_active
) VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'rll',
    'LucidX360',
    '/images/rll logo.svg',
    NULL,
    NULL,
    'Rajasthan Liquor Limited',
    ARRAY['Others'],
    true
) ON CONFLICT (tenant_slug) DO UPDATE
SET is_active = true,
    updated_at = NOW();

-- 2. Add tenant_id to all core tables with default 'a0000000-0000-0000-0000-000000000001'

-- public.users
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid,
ADD COLUMN IF NOT EXISTS company_id UUID,
ADD COLUMN IF NOT EXISTS company_name TEXT;

-- public.companies
ALTER TABLE public.companies 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid,
ADD COLUMN IF NOT EXISTS logo_url TEXT;

-- public.sales_fact
ALTER TABLE public.sales_fact 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid;

-- public.sales_daily_summary
ALTER TABLE public.sales_daily_summary 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid;

-- public.sales_monthly_summary
ALTER TABLE public.sales_monthly_summary 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid;

-- public.user_sales_fact
ALTER TABLE public.user_sales_fact 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid;

-- public.upload_batches
ALTER TABLE public.upload_batches 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid;

-- public.raw_sales_upload
ALTER TABLE public.raw_sales_upload 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid;

-- Master tables
ALTER TABLE public.headquarters 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid;

ALTER TABLE public.depots 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid;

ALTER TABLE public.licensees 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid;

ALTER TABLE public.brands 
ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenant_config(tenant_id) DEFAULT 'a0000000-0000-0000-0000-000000000001'::uuid;

-- Backfill any existing NULL tenant_id
UPDATE public.users SET tenant_id = 'a0000000-0000-0000-0000-000000000001'::uuid WHERE tenant_id IS NULL;
UPDATE public.companies SET tenant_id = 'a0000000-0000-0000-0000-000000000001'::uuid WHERE tenant_id IS NULL;
UPDATE public.headquarters SET tenant_id = 'a0000000-0000-0000-0000-000000000001'::uuid WHERE tenant_id IS NULL;
UPDATE public.depots SET tenant_id = 'a0000000-0000-0000-0000-000000000001'::uuid WHERE tenant_id IS NULL;
UPDATE public.licensees SET tenant_id = 'a0000000-0000-0000-0000-000000000001'::uuid WHERE tenant_id IS NULL;
UPDATE public.brands SET tenant_id = 'a0000000-0000-0000-0000-000000000001'::uuid WHERE tenant_id IS NULL;

-- 3. High-performance Indexes
CREATE INDEX IF NOT EXISTS idx_users_tenant ON public.users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_phone ON public.users(phone);
CREATE INDEX IF NOT EXISTS idx_sales_fact_tenant ON public.sales_fact(tenant_id, sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_daily_summary_tenant ON public.sales_daily_summary(tenant_id, sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_monthly_summary_tenant ON public.sales_monthly_summary(tenant_id, month_start);

-- 4. Update refresh_sales_daily_summary_for_date to preserve tenant_id
CREATE OR REPLACE FUNCTION public.refresh_sales_daily_summary_for_date(p_sale_date DATE)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_fy SMALLINT;
    v_fm SMALLINT;
    v_month INT;
    v_year INT;
BEGIN
    v_month := EXTRACT(MONTH FROM p_sale_date);
    v_year  := EXTRACT(YEAR  FROM p_sale_date);

    IF v_month >= 4 THEN
        v_fy := v_year;
        v_fm := v_month - 3;
    ELSE
        v_fy := v_year - 1;
        v_fm := v_month + 9;
    END IF;

    DELETE FROM public.sales_daily_summary WHERE sale_date = p_sale_date;

    INSERT INTO public.sales_daily_summary (
        sale_date,
        financial_year,
        financial_month,
        headquarters_id,
        office_id,
        depot_id,
        company_id,
        brand_id,
        group_id,
        licensee_id,
        tsm_user_id,
        ase_user_id,
        total_cases,
        total_bottles,
        total_bl,
        refreshed_at,
        tenant_id
    )
    WITH agg_sales AS (
        SELECT
            sf.depot_id,
            sf.headquarters_id,
            sf.brand_id,
            sf.licensee_id,
            COALESCE(sf.tenant_id, 'a0000000-0000-0000-0000-000000000001'::uuid) AS tenant_id,
            SUM(sf.total_case) AS total_cases,
            SUM(sf.total_btl)  AS total_bottles,
            SUM(sf.total_bl)   AS total_bl
        FROM public.sales_fact sf
        WHERE sf.sale_date = p_sale_date
        GROUP BY sf.depot_id, sf.headquarters_id, sf.brand_id, sf.licensee_id, sf.tenant_id
    ),
    depot_roles AS (
        SELECT DISTINCT ON (ud.depot_id, r.role_name)
            ud.depot_id,
            r.role_name,
            ud.user_id
        FROM public.user_depot ud
        JOIN public.user_roles ur ON ud.user_id = ur.user_id AND ur.is_active = true
        JOIN public.roles r ON ur.role_id = r.role_id
        WHERE UPPER(r.role_name) IN ('TSM', 'ASE')
    ),
    depot_tsm AS (
        SELECT depot_id, user_id AS tsm_user_id FROM depot_roles WHERE UPPER(role_name) = 'TSM'
    ),
    depot_ase AS (
        SELECT depot_id, user_id AS ase_user_id FROM depot_roles WHERE UPPER(role_name) = 'ASE'
    )
    SELECT
        p_sale_date,
        v_fy,
        v_fm,
        COALESCE(a.headquarters_id, l.headquarters_id, d.headquarters_id) AS headquarters_id,
        COALESCE(l.office_id, d.office_id) AS office_id,
        a.depot_id,
        b.company_id,
        a.brand_id,
        l.group_id,
        a.licensee_id,
        dt.tsm_user_id,
        da.ase_user_id,
        ROUND(a.total_cases, 2),
        ROUND(a.total_bottles, 2),
        ROUND(a.total_bl, 2),
        NOW(),
        a.tenant_id
    FROM agg_sales a
    JOIN public.depots d ON a.depot_id = d.depot_id
    JOIN public.brands b ON a.brand_id = b.brand_id
    LEFT JOIN public.licensees l ON a.licensee_id = l.licensee_id
    LEFT JOIN depot_tsm dt ON a.depot_id = dt.depot_id
    LEFT JOIN depot_ase da ON a.depot_id = da.depot_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.refresh_sales_daily_summary_for_date(DATE) TO authenticated, service_role, anon;

-- 5. Update get_mobile_companies_summary to support optional p_company_name scoping
DROP FUNCTION IF EXISTS public.get_mobile_companies_summary(DATE, DATE, DATE, UUID);
DROP FUNCTION IF EXISTS public.get_mobile_companies_summary(DATE, DATE, DATE, UUID, TEXT);
CREATE OR REPLACE FUNCTION public.get_mobile_companies_summary(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_hq_id       UUID DEFAULT NULL,
    p_company_name TEXT DEFAULT NULL
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
BEGIN
    IF p_hq_id IS NOT NULL THEN
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
        WHERE sds.headquarters_id = p_hq_id
          AND sds.sale_date >= p_ytd_start
          AND sds.sale_date <= p_target_date
          AND (c.company_name IS NULL OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other'))
          AND (p_company_name IS NULL OR LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_company_name)))
        GROUP BY sds.company_id, c.company_name;
    ELSE
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
        WHERE sds.sale_date >= p_ytd_start
          AND sds.sale_date <= p_target_date
          AND (c.company_name IS NULL OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other'))
          AND (p_company_name IS NULL OR LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_company_name)))
        GROUP BY sds.company_id, c.company_name;
    END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_companies_summary(DATE, DATE, DATE, UUID, TEXT) TO authenticated, service_role, anon;
