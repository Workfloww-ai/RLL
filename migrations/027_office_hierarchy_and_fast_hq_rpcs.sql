-- Migration: 027_office_hierarchy_and_fast_hq_rpcs.sql
-- Purpose: Establish Office -> Headquarters hierarchy, add covering performance indexes,
-- and provide canonical high-performance RPCs for mobile analytics on test_db_RLL.
-- NO hardcoded string lists. All relations populated dynamically from DB metadata & transactions.

-- ── 1. Enhance offices table schema ──────────────────────────────────────────
ALTER TABLE IF EXISTS public.offices 
ADD COLUMN IF NOT EXISTS headquarters_id UUID REFERENCES public.headquarters(headquarters_id);

-- Add index on offices.headquarters_id
CREATE INDEX IF NOT EXISTS idx_offices_hq_id ON public.offices(headquarters_id);

-- Populate offices.headquarters_id dynamically from transaction summaries and depot links
UPDATE public.offices o
SET headquarters_id = sds.headquarters_id
FROM (
    SELECT DISTINCT depot_id, headquarters_id
    FROM public.sales_daily_summary
    WHERE headquarters_id IS NOT NULL
) sds
JOIN public.depots d ON sds.depot_id = d.depot_id
WHERE d.office_id = o.office_id
  AND o.headquarters_id IS NULL;

-- ── 2. Composite Covering Indexes for High-Performance Querying ────────────────
CREATE INDEX IF NOT EXISTS idx_sds_hq_date_comp_brand 
ON public.sales_daily_summary (headquarters_id, sale_date, company_id, brand_id);

CREATE INDEX IF NOT EXISTS idx_usf_date_user_comp_brand 
ON public.user_sales_fact (sale_date DESC, user_id, company_id, brand_id);

-- ── 3. Canonical Company-List RPC ─────────────────────────────────────────────
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

-- ── 4. Canonical Brand-Drilldown RPC ──────────────────────────────────────────
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
    LEFT JOIN public.companies c ON sds.company_id = c.company_id
    WHERE sds.sale_date >= p_ytd_start
      AND sds.sale_date <= p_target_date
      AND sds.company_id = ANY(p_company_ids)
      AND (p_hq_id IS NULL OR sds.headquarters_id = p_hq_id)
      AND (c.company_name IS NULL OR LOWER(TRIM(c.company_name)) != 'others')
    GROUP BY sds.brand_id, b.brand_name, sds.company_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_company_brands_summary(UUID[], DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;

-- ── 5. Single-Pass Mobile Sales JSON RPC ──────────────────────────────────────
DROP FUNCTION IF EXISTS public.get_mobile_sales_summary_json(DATE, DATE, DATE, UUID);

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
    v_comp_json  JSONB;
    v_depot_json JSONB;
BEGIN
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
          AND (c.company_name IS NULL OR LOWER(TRIM(c.company_name)) != 'others')
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
          AND (c.company_name IS NULL OR LOWER(TRIM(c.company_name)) != 'others')
        GROUP BY sds.depot_id, sds.headquarters_id, sds.brand_id
    ) depot_row;

    RETURN jsonb_build_object(
        'companies', v_comp_json,
        'depots', v_depot_json
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_sales_summary_json(DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;
