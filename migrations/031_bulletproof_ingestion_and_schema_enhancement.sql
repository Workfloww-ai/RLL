-- Migration: 031_bulletproof_ingestion_and_schema_enhancement.sql
-- Description: Unifies duplicate 'Other' company into canonical 'Others', adds office_id
-- to summary tables with covering index, removes sales_fact duplicates and creates unique index,
-- and updates daily summary refresh RPC. Applied to test_db_RLL.

-- 1. Canonical 'Others' Unification
DO $$
DECLARE
    v_others_id UUID := '9a5f44de-24a3-4815-9aa2-c81cd06fe72d';
    v_other_id  UUID := 'e7fb5698-665f-45a5-8a78-c213d5fc841d';
BEGIN
    -- If 'Other' exists, re-link brands and sales summaries to 'Others'
    IF EXISTS (SELECT 1 FROM public.companies WHERE company_id = v_other_id) THEN
        UPDATE public.brands SET company_id = v_others_id WHERE company_id = v_other_id;
        UPDATE public.sales_daily_summary SET company_id = v_others_id WHERE company_id = v_other_id;
        UPDATE public.sales_monthly_summary SET company_id = v_others_id WHERE company_id = v_other_id;
        UPDATE public.user_sales_fact SET company_id = v_others_id WHERE company_id = v_other_id;
        DELETE FROM public.companies WHERE company_id = v_other_id;
    END IF;
END $$;

-- 2. Add office_id to sales_daily_summary and sales_monthly_summary
ALTER TABLE IF EXISTS public.sales_daily_summary
ADD COLUMN IF NOT EXISTS office_id UUID REFERENCES public.offices(office_id) ON DELETE SET NULL;

ALTER TABLE IF EXISTS public.sales_monthly_summary
ADD COLUMN IF NOT EXISTS office_id UUID REFERENCES public.offices(office_id) ON DELETE SET NULL;

-- Backfill office_id from depots
UPDATE public.sales_daily_summary sds
SET office_id = d.office_id
FROM public.depots d
WHERE sds.depot_id = d.depot_id
  AND sds.office_id IS NULL
  AND d.office_id IS NOT NULL;

UPDATE public.sales_monthly_summary sms
SET office_id = d.office_id
FROM public.depots d
WHERE sms.depot_id = d.depot_id
  AND sms.office_id IS NULL
  AND d.office_id IS NOT NULL;

-- Composite covering index for sub-5ms filtering by HQ, Office, and Date
CREATE INDEX IF NOT EXISTS idx_sds_hq_office_date
ON public.sales_daily_summary(headquarters_id, office_id, sale_date);

CREATE INDEX IF NOT EXISTS idx_sms_hq_office_month
ON public.sales_monthly_summary(headquarters_id, office_id, month_start);

-- 3. Surgical Deduplication on sales_fact
-- Delete exact duplicates keeping the lowest ctid
DELETE FROM public.sales_fact a
USING public.sales_fact b
WHERE a.ctid > b.ctid
  AND a.sale_date = b.sale_date
  AND a.depot_id = b.depot_id
  AND a.brand_id = b.brand_id
  AND a.packaging_id IS NOT DISTINCT FROM b.packaging_id
  AND a.licensee_id IS NOT DISTINCT FROM b.licensee_id
  AND a.total_case IS NOT DISTINCT FROM b.total_case
  AND a.total_btl IS NOT DISTINCT FROM b.total_btl
  AND a.total_bl IS NOT DISTINCT FROM b.total_bl;

-- Add database-level unique constraint to permanently prevent duplicate ingestion
CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_fact_txn
ON public.sales_fact (
    sale_date,
    depot_id,
    brand_id,
    COALESCE(packaging_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(licensee_id, '00000000-0000-0000-0000-000000000000'::uuid),
    total_case,
    total_btl,
    total_bl
);

-- 4. Update refresh_sales_daily_summary_for_date RPC to include office_id
CREATE OR REPLACE FUNCTION public.refresh_sales_daily_summary_for_date(p_sale_date DATE)
RETURNS VOID AS $$
DECLARE
    v_fy SMALLINT;
    v_fm SMALLINT;
BEGIN
    PERFORM set_config('statement_timeout', '60000', true);

    IF EXTRACT(MONTH FROM p_sale_date) >= 4 THEN
        v_fy := EXTRACT(YEAR FROM p_sale_date)::SMALLINT;
        v_fm := (EXTRACT(MONTH FROM p_sale_date) - 3)::SMALLINT;
    ELSE
        v_fy := (EXTRACT(YEAR FROM p_sale_date) - 1)::SMALLINT;
        v_fm := (EXTRACT(MONTH FROM p_sale_date) + 9)::SMALLINT;
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
        refreshed_at
    )
    WITH agg_sales AS (
        SELECT
            sf.depot_id,
            sf.brand_id,
            sf.licensee_id,
            SUM(sf.total_case) AS total_cases,
            SUM(sf.total_btl)  AS total_bottles,
            SUM(sf.total_bl)   AS total_bl
        FROM public.sales_fact sf
        WHERE sf.sale_date = p_sale_date
        GROUP BY sf.depot_id, sf.brand_id, sf.licensee_id
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
        COALESCE(l.headquarters_id, d.headquarters_id) AS headquarters_id,
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
        NOW()
    FROM agg_sales a
    JOIN public.depots d ON a.depot_id = d.depot_id
    JOIN public.brands b ON a.brand_id = b.brand_id
    LEFT JOIN public.licensees l ON a.licensee_id = l.licensee_id
    LEFT JOIN depot_tsm dt ON a.depot_id = dt.depot_id
    LEFT JOIN depot_ase da ON a.depot_id = da.depot_id;
END;
$$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION public.refresh_sales_daily_summary_for_date(DATE) TO authenticated, service_role, anon;

-- 5. Canonical Fast Company-List and Brand-List RPCs with strict 'Others' & 'Other' exclusion
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
BEGIN
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
      AND (p_hq_id IS NULL OR sds.headquarters_id = p_hq_id)
      AND (c.company_name IS NULL OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other'))
    GROUP BY sds.company_id, c.company_name;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_companies_summary(DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;

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
BEGIN
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
      AND (c.company_name IS NULL OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other'))
    GROUP BY sds.brand_id, b.brand_name, sds.company_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_company_brands_summary(UUID[], DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;
