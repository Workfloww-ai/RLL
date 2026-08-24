-- Migration: 010_canonical_mobile_functions.sql
-- Purpose: Optimize company-brand queries, create canonical company and brand RPCs, and provide unique depot helper.

-- ── 1. Create Optimized Composite Index ──────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sds_date_hq_comp_brand 
ON public.sales_daily_summary (sale_date, headquarters_id, company_id, brand_id);

-- ── 2. Unique Depot Helper Function ──────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.get_affected_depots_for_month(p_month_start DATE)
RETURNS TABLE(depot_id UUID) AS $$
DECLARE
    v_month_end DATE := (p_month_start + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
BEGIN
    RETURN QUERY 
    SELECT DISTINCT sds.depot_id 
    FROM public.sales_daily_summary sds 
    WHERE sds.sale_date >= p_month_start AND sds.sale_date <= v_month_end
      AND sds.depot_id IS NOT NULL;
END;
$$ LANGUAGE plpgsql STABLE;

GRANT EXECUTE ON FUNCTION public.get_affected_depots_for_month(DATE) TO authenticated, service_role, anon;

-- ── 3. Canonical Company-List Function ────────────────────────────────────────
DROP FUNCTION IF EXISTS public.get_mobile_companies_summary(DATE, DATE, DATE, UUID);

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
      AND (c.company_name IS NULL OR LOWER(TRIM(c.company_name)) != 'others')
    GROUP BY sds.company_id, c.company_name;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_companies_summary(DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;

-- ── 4. Canonical Brand-Drilldown Function ─────────────────────────────────────
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
    WHERE sds.sale_date >= p_ytd_start
      AND sds.sale_date <= p_target_date
      AND sds.company_id = ANY(p_company_ids)
      AND (p_hq_id IS NULL OR sds.headquarters_id = p_hq_id)
    GROUP BY sds.brand_id, b.brand_name, sds.company_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_company_brands_summary(UUID[], DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;
