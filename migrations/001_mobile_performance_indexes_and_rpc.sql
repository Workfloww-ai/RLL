-- Migration: 001_mobile_performance_indexes_and_rpc
-- Purpose: Speed up /mobile/sales endpoint by:
--   1. Adding composite indexes for date/HQ/company/brand/depot queries
--   2. Creating an RPC function that aggregates sales in the DB (avoids fetching raw rows)

-- ── Composite Indexes ────────────────────────────────────────────────────────

-- Index 1: Primary query pattern — date range + optional HQ filter
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dsd_date_hq
    ON public.dashboard_summary_daily (sale_date DESC, headquarters_id);

-- Index 2: Company + brand aggregation grouping
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dsd_company_brand
    ON public.dashboard_summary_daily (company_id, brand_id);

-- Index 3: Depot-level grouping with date
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dsd_depot_date
    ON public.dashboard_summary_daily (depot_id, sale_date DESC);

-- ── RPC: get_mobile_sales_summary ────────────────────────────────────────────
-- Aggregates dashboard_summary_daily into ~50-200 rows server-side.
-- Replaces the current pattern of fetching 30,000+ rows in Python chunks.

CREATE OR REPLACE FUNCTION get_mobile_sales_summary(
    p_start_date  DATE,
    p_target_date DATE,
    p_hq_id       UUID DEFAULT NULL
)
RETURNS TABLE (
    company_id      UUID,
    brand_id        UUID,
    depot_id        UUID,
    headquarters_id UUID,
    total_cases     BIGINT,
    total_bottles   BIGINT,
    total_bl        NUMERIC
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.company_id,
        d.brand_id,
        d.depot_id,
        d.headquarters_id,
        SUM(d.total_case)::BIGINT      AS total_cases,
        SUM(d.total_btl)::BIGINT       AS total_bottles,
        ROUND(SUM(d.total_bl), 2)      AS total_bl
    FROM public.dashboard_summary_daily d
    WHERE d.sale_date >= p_start_date
      AND d.sale_date <= p_target_date
      AND (p_hq_id IS NULL OR d.headquarters_id = p_hq_id)
    GROUP BY
        d.company_id,
        d.brand_id,
        d.depot_id,
        d.headquarters_id;
END;
$$;

-- Grant execute permission to roles used by Supabase client
GRANT EXECUTE ON FUNCTION get_mobile_sales_summary(DATE, DATE, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION get_mobile_sales_summary(DATE, DATE, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION get_mobile_sales_summary(DATE, DATE, UUID) TO anon;

-- ── user_sales_fact Indexes ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_usf_sale_date_user
    ON public.user_sales_fact (sale_date DESC, user_id);

CREATE INDEX IF NOT EXISTS idx_usf_sale_date_company
    ON public.user_sales_fact (sale_date DESC, company_id);

-- ── RPC: get_mobile_tsm_sales_summary ─────────────────────────────────────────
-- Aggregates user_sales_fact server-side by user_id, company_id, brand_id.
-- Replaces the python while-loop fetching 30,000+ user_sales_fact rows.

CREATE OR REPLACE FUNCTION get_mobile_tsm_sales_summary(
    p_start_date DATE,
    p_end_date   DATE
)
RETURNS TABLE (
    user_id       UUID,
    company_id    UUID,
    brand_id      UUID,
    total_cases   BIGINT,
    total_bottles BIGINT,
    total_bl      NUMERIC
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        usf.user_id,
        usf.company_id,
        usf.brand_id,
        SUM(usf.cases)::BIGINT   AS total_cases,
        SUM(usf.bottles)::BIGINT AS total_bottles,
        ROUND(SUM(usf.bl), 2)    AS total_bl
    FROM public.user_sales_fact usf
    WHERE usf.sale_date >= p_start_date
      AND usf.sale_date <= p_end_date
    GROUP BY usf.user_id, usf.company_id, usf.brand_id;
END;
$$;

GRANT EXECUTE ON FUNCTION get_mobile_tsm_sales_summary(DATE, DATE) TO authenticated;
GRANT EXECUTE ON FUNCTION get_mobile_tsm_sales_summary(DATE, DATE) TO service_role;
GRANT EXECUTE ON FUNCTION get_mobile_tsm_sales_summary(DATE, DATE) TO anon;

