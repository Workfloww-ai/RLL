-- Migration: 005_incremental_analytics_summary_tables.sql
-- Purpose: Physical PostgreSQL summary tables for incremental Daily, MTD, and YTD sales analytics.
-- Source of truth remains sales_fact. These physical tables provide ultra-fast, idempotent serving.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── 1. Daily Physical Summary Table ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.sales_daily_summary (
    summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sale_date DATE NOT NULL,
    financial_year SMALLINT NOT NULL,
    financial_month SMALLINT NOT NULL,
    headquarters_id UUID REFERENCES public.headquarters(headquarters_id) ON DELETE SET NULL,
    depot_id UUID REFERENCES public.depots(depot_id) ON DELETE CASCADE,
    company_id UUID REFERENCES public.companies(company_id) ON DELETE CASCADE,
    brand_id UUID REFERENCES public.brands(brand_id) ON DELETE CASCADE,
    group_id UUID REFERENCES public.groups(group_id) ON DELETE SET NULL,
    licensee_id UUID REFERENCES public.licensees(licensee_id) ON DELETE SET NULL,
    tsm_user_id UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    ase_user_id UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    total_cases NUMERIC DEFAULT 0.0,
    total_bottles NUMERIC DEFAULT 0.0,
    total_bl NUMERIC DEFAULT 0.0,
    refreshed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Deterministic Unique Index for Daily Summary Grain
CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_daily_summary_grain ON public.sales_daily_summary (
    sale_date,
    depot_id,
    brand_id,
    company_id,
    COALESCE(headquarters_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(group_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(licensee_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(tsm_user_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(ase_user_id, '00000000-0000-0000-0000-000000000000'::uuid)
);

-- ── 2. Monthly Physical Summary Table ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.sales_monthly_summary (
    summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    month_start DATE NOT NULL,
    financial_year SMALLINT NOT NULL,
    financial_month SMALLINT NOT NULL,
    headquarters_id UUID REFERENCES public.headquarters(headquarters_id) ON DELETE SET NULL,
    depot_id UUID REFERENCES public.depots(depot_id) ON DELETE CASCADE,
    company_id UUID REFERENCES public.companies(company_id) ON DELETE CASCADE,
    brand_id UUID REFERENCES public.brands(brand_id) ON DELETE CASCADE,
    group_id UUID REFERENCES public.groups(group_id) ON DELETE SET NULL,
    licensee_id UUID REFERENCES public.licensees(licensee_id) ON DELETE SET NULL,
    tsm_user_id UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    ase_user_id UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    total_cases NUMERIC DEFAULT 0.0,
    total_bottles NUMERIC DEFAULT 0.0,
    total_bl NUMERIC DEFAULT 0.0,
    refreshed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Deterministic Unique Index for Monthly Summary Grain
CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_monthly_summary_grain ON public.sales_monthly_summary (
    month_start,
    depot_id,
    brand_id,
    company_id,
    COALESCE(headquarters_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(group_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(licensee_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(tsm_user_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(ase_user_id, '00000000-0000-0000-0000-000000000000'::uuid)
);

-- ── 3. Performance Query Indexes ──────────────────────────────────────────────

-- Daily Summary Query Indexes
CREATE INDEX IF NOT EXISTS idx_sds_date_hq ON public.sales_daily_summary (sale_date DESC, headquarters_id);
CREATE INDEX IF NOT EXISTS idx_sds_fy_fm ON public.sales_daily_summary (financial_year, financial_month);
CREATE INDEX IF NOT EXISTS idx_sds_company_brand ON public.sales_daily_summary (company_id, brand_id);
CREATE INDEX IF NOT EXISTS idx_sds_depot ON public.sales_daily_summary (depot_id, sale_date DESC);
CREATE INDEX IF NOT EXISTS idx_sds_group_lic ON public.sales_daily_summary (group_id, licensee_id);
CREATE INDEX IF NOT EXISTS idx_sds_tsm_ase ON public.sales_daily_summary (tsm_user_id, ase_user_id);

-- Monthly Summary Query Indexes
CREATE INDEX IF NOT EXISTS idx_sms_month_hq ON public.sales_monthly_summary (month_start DESC, headquarters_id);
CREATE INDEX IF NOT EXISTS idx_sms_fy_fm ON public.sales_monthly_summary (financial_year, financial_month);
CREATE INDEX IF NOT EXISTS idx_sms_company_brand ON public.sales_monthly_summary (company_id, brand_id);
CREATE INDEX IF NOT EXISTS idx_sms_depot ON public.sales_monthly_summary (depot_id, month_start DESC);
CREATE INDEX IF NOT EXISTS idx_sms_group_lic ON public.sales_monthly_summary (group_id, licensee_id);
CREATE INDEX IF NOT EXISTS idx_sms_tsm_ase ON public.sales_monthly_summary (tsm_user_id, ase_user_id);

-- ── 4. Incremental Aggregation Functions ─────────────────────────────────────

-- High-performance Incremental Daily Refresh Function for a specific date
CREATE OR REPLACE FUNCTION refresh_sales_daily_summary_for_date(p_sale_date DATE)
RETURNS VOID AS $$
DECLARE
    v_fy SMALLINT;
    v_fm SMALLINT;
BEGIN
    -- Determine Financial Year (April 1 - March 31) and Financial Month (1-12)
    IF EXTRACT(MONTH FROM p_sale_date) >= 4 THEN
        v_fy := EXTRACT(YEAR FROM p_sale_date)::SMALLINT;
        v_fm := (EXTRACT(MONTH FROM p_sale_date) - 3)::SMALLINT;
    ELSE
        v_fy := (EXTRACT(YEAR FROM p_sale_date) - 1)::SMALLINT;
        v_fm := (EXTRACT(MONTH FROM p_sale_date) + 9)::SMALLINT;
    END IF;

    -- Delete existing rows for this date to ensure clean, idempotent UPSERT
    DELETE FROM public.sales_daily_summary WHERE sale_date = p_sale_date;

    INSERT INTO public.sales_daily_summary (
        sale_date,
        financial_year,
        financial_month,
        headquarters_id,
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
        d.headquarters_id,
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

-- Incremental Monthly Refresh Function for a specific month
CREATE OR REPLACE FUNCTION refresh_sales_monthly_summary_for_month(p_month_start DATE)
RETURNS VOID AS $$
DECLARE
    v_month_end DATE := (p_month_start + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
    v_fy SMALLINT;
    v_fm SMALLINT;
BEGIN
    IF EXTRACT(MONTH FROM p_month_start) >= 4 THEN
        v_fy := EXTRACT(YEAR FROM p_month_start)::SMALLINT;
        v_fm := (EXTRACT(MONTH FROM p_month_start) - 3)::SMALLINT;
    ELSE
        v_fy := (EXTRACT(YEAR FROM p_month_start) - 1)::SMALLINT;
        v_fm := (EXTRACT(MONTH FROM p_month_start) + 9)::SMALLINT;
    END IF;

    -- Delete existing monthly summary rows for clean re-aggregation
    DELETE FROM public.sales_monthly_summary WHERE month_start = p_month_start;

    INSERT INTO public.sales_monthly_summary (
        month_start,
        financial_year,
        financial_month,
        headquarters_id,
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
    SELECT
        p_month_start,
        v_fy,
        v_fm,
        headquarters_id,
        depot_id,
        company_id,
        brand_id,
        group_id,
        licensee_id,
        tsm_user_id,
        ase_user_id,
        ROUND(SUM(total_cases), 2)   AS total_cases,
        ROUND(SUM(total_bottles), 2) AS total_bottles,
        ROUND(SUM(total_bl), 2)      AS total_bl,
        NOW()
    FROM public.sales_daily_summary
    WHERE sale_date >= p_month_start AND sale_date <= v_month_end
    GROUP BY
        headquarters_id,
        depot_id,
        company_id,
        brand_id,
        group_id,
        licensee_id,
        tsm_user_id,
        ase_user_id;
END;
$$ LANGUAGE plpgsql;

-- Unified Refresh Procedure for Batch Ingestion Hook
CREATE OR REPLACE FUNCTION refresh_incremental_sales_analytics(p_sale_date DATE)
RETURNS VOID AS $$
DECLARE
    v_month_start DATE := DATE_TRUNC('month', p_sale_date)::DATE;
BEGIN
    PERFORM refresh_sales_daily_summary_for_date(p_sale_date);
    PERFORM refresh_sales_monthly_summary_for_month(v_month_start);
END;
$$ LANGUAGE plpgsql;

-- ── 5. Permissions ─────────────────────────────────────────────────────────────
GRANT ALL ON TABLE public.sales_daily_summary TO authenticated, service_role;
GRANT ALL ON TABLE public.sales_monthly_summary TO authenticated, service_role;
GRANT SELECT ON TABLE public.sales_daily_summary TO anon;
GRANT SELECT ON TABLE public.sales_monthly_summary TO anon;

GRANT EXECUTE ON FUNCTION refresh_sales_daily_summary_for_date(DATE) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION refresh_sales_monthly_summary_for_month(DATE) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION refresh_incremental_sales_analytics(DATE) TO authenticated, service_role;
