-- Migration: 032_sales_fact_direct_headquarters.sql
-- Description: 
-- 1. Add headquarters_id column directly to sales_fact and index (headquarters_id, sale_date).
-- 2. Drop any legacy destructive deduplication constraint on sales_fact.
-- 3. Update refresh_sales_daily_summary_for_date to aggregate sf.headquarters_id directly from sales_fact.
-- 4. Optimize get_mobile_companies_summary RPC to eliminate statement timeouts using indexed branching.

-- 1. Add headquarters_id to sales_fact
ALTER TABLE IF EXISTS public.sales_fact
ADD COLUMN IF NOT EXISTS headquarters_id UUID REFERENCES public.headquarters(headquarters_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_sales_fact_hq_date 
ON public.sales_fact(headquarters_id, sale_date);

-- 2. Drop legacy unique deduplication constraint if still present
DROP INDEX IF EXISTS public.uq_sales_fact_txn;

-- 3. Update refresh_sales_daily_summary_for_date to read headquarters_id directly from sales_fact
CREATE OR REPLACE FUNCTION public.refresh_sales_daily_summary_for_date(p_sale_date DATE)
RETURNS VOID AS $$
DECLARE
    v_fy SMALLINT;
    v_fm SMALLINT;
BEGIN
    PERFORM set_config('statement_timeout', '120000', true);

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
            sf.headquarters_id,
            sf.brand_id,
            sf.licensee_id,
            SUM(sf.total_case) AS total_cases,
            SUM(sf.total_btl)  AS total_bottles,
            SUM(sf.total_bl)   AS total_bl
        FROM public.sales_fact sf
        WHERE sf.sale_date = p_sale_date
        GROUP BY sf.depot_id, sf.headquarters_id, sf.brand_id, sf.licensee_id
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

-- 4. High-performance indexed get_mobile_companies_summary RPC (eliminates statement timeouts)
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
        GROUP BY sds.company_id, c.company_name;
    END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_companies_summary(DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;
