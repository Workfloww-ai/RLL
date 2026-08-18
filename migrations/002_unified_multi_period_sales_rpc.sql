-- Migration: 002_unified_multi_period_sales_rpc
-- Purpose: Fix Daily, MTD, and YTD data accuracy & eliminate PostgREST 1000-row truncation:
--   1. Perform single-pass conditional SQL aggregations (CASE WHEN) for Daily, MTD, and YTD.
--   2. Return aggregated JSONB payload from PostgreSQL so PostgREST row limits never truncate results.
--   3. Add composite indexes for date range queries with HQ filtering.

-- ── Composite Index ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_dsd_sale_date_hq_comp
    ON public.dashboard_summary_daily (sale_date DESC, headquarters_id, company_id);

-- ── RPC: get_mobile_sales_summary_json ─────────────────────────────────────
-- Aggregates company and depot sales with distinct Daily, MTD, and YTD metrics into JSONB.

CREATE OR REPLACE FUNCTION get_mobile_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_hq_id       UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'companies', (
            SELECT jsonb_agg(comp) FROM (
                SELECT
                    d.company_id,
                    d.brand_id,
                    SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_case ELSE 0 END)::BIGINT AS daily_cases,
                    SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_btl ELSE 0 END)::BIGINT  AS daily_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_bl ELSE 0 END), 2) AS daily_bl,
                    SUM(CASE WHEN d.sale_date >= p_mtd_start THEN d.total_case ELSE 0 END)::BIGINT  AS mtd_cases,
                    SUM(CASE WHEN d.sale_date >= p_mtd_start THEN d.total_btl ELSE 0 END)::BIGINT   AS mtd_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start THEN d.total_bl ELSE 0 END), 2)  AS mtd_bl,
                    SUM(d.total_case)::BIGINT                                                        AS ytd_cases,
                    SUM(d.total_btl)::BIGINT                                                         AS ytd_bottles,
                    ROUND(SUM(d.total_bl), 2)                                                        AS ytd_bl
                FROM public.dashboard_summary_daily d
                WHERE d.sale_date >= p_ytd_start
                  AND d.sale_date <= p_target_date
                  AND (p_hq_id IS NULL OR d.headquarters_id = p_hq_id)
                GROUP BY d.company_id, d.brand_id
            ) comp
        ),
        'depots', (
            SELECT jsonb_agg(dep) FROM (
                SELECT
                    d.depot_id,
                    d.brand_id,
                    d.headquarters_id,
                    SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_case ELSE 0 END)::BIGINT AS daily_cases,
                    SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_btl ELSE 0 END)::BIGINT  AS daily_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_bl ELSE 0 END), 2) AS daily_bl,
                    SUM(CASE WHEN d.sale_date >= p_mtd_start THEN d.total_case ELSE 0 END)::BIGINT  AS mtd_cases,
                    SUM(CASE WHEN d.sale_date >= p_mtd_start THEN d.total_btl ELSE 0 END)::BIGINT   AS mtd_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start THEN d.total_bl ELSE 0 END), 2)  AS mtd_bl,
                    SUM(d.total_case)::BIGINT                                                        AS ytd_cases,
                    SUM(d.total_btl)::BIGINT                                                         AS ytd_bottles,
                    ROUND(SUM(d.total_bl), 2)                                                        AS ytd_bl
                FROM public.dashboard_summary_daily d
                WHERE d.sale_date >= p_ytd_start
                  AND d.sale_date <= p_target_date
                  AND (p_hq_id IS NULL OR d.headquarters_id = p_hq_id)
                GROUP BY d.depot_id, d.brand_id, d.headquarters_id
            ) dep
        )
    ) INTO v_result;

    RETURN COALESCE(v_result, '{"companies":[],"depots":[]}'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_mobile_sales_summary_json(DATE, DATE, DATE, UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION get_mobile_sales_summary_json(DATE, DATE, DATE, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION get_mobile_sales_summary_json(DATE, DATE, DATE, UUID) TO anon;

-- ── RPC: get_mobile_tsm_sales_summary_json ───────────────────────────────
-- Aggregates user_sales_fact server-side into JSONB with Daily, MTD, and YTD metrics.

CREATE OR REPLACE FUNCTION get_mobile_tsm_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_agg(tsm) FROM (
        SELECT
            usf.user_id,
            usf.company_id,
            usf.brand_id,
            SUM(CASE WHEN usf.sale_date = p_target_date THEN usf.cases ELSE 0 END)::BIGINT   AS daily_cases,
            SUM(CASE WHEN usf.sale_date = p_target_date THEN usf.bottles ELSE 0 END)::BIGINT AS daily_bottles,
            ROUND(SUM(CASE WHEN usf.sale_date = p_target_date THEN usf.bl ELSE 0 END), 2)   AS daily_bl,
            SUM(CASE WHEN usf.sale_date >= p_mtd_start THEN usf.cases ELSE 0 END)::BIGINT    AS mtd_cases,
            SUM(CASE WHEN usf.sale_date >= p_mtd_start THEN usf.bottles ELSE 0 END)::BIGINT   AS mtd_bottles,
            ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start THEN usf.bl ELSE 0 END), 2)    AS mtd_bl,
            SUM(usf.cases)::BIGINT                                                           AS ytd_cases,
            SUM(usf.bottles)::BIGINT                                                         AS ytd_bottles,
            ROUND(SUM(usf.bl), 2)                                                            AS ytd_bl
        FROM public.user_sales_fact usf
        WHERE usf.sale_date >= p_ytd_start
          AND usf.sale_date <= p_target_date
        GROUP BY usf.user_id, usf.company_id, usf.brand_id
    ) tsm INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION get_mobile_tsm_sales_summary_json(DATE, DATE, DATE) TO authenticated;
GRANT EXECUTE ON FUNCTION get_mobile_tsm_sales_summary_json(DATE, DATE, DATE) TO service_role;
GRANT EXECUTE ON FUNCTION get_mobile_tsm_sales_summary_json(DATE, DATE, DATE) TO anon;
