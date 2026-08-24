-- Migration: 008_fast_summary_table_refresh.sql
-- Purpose: Fast, non-blocking RPCs for refreshing sales_daily_summary and sales_monthly_summary directly from sales_fact.
-- Eliminates statement timeouts (57014) caused by unindexed user/role joins.

CREATE OR REPLACE FUNCTION public.refresh_sales_daily_summary_for_date(p_sale_date DATE)
RETURNS VOID AS $$
BEGIN
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
        total_cases,
        total_bottles,
        total_bl,
        refreshed_at
    )
    SELECT
        sf.sale_date,
        (CASE WHEN EXTRACT(MONTH FROM sf.sale_date) >= 4 THEN EXTRACT(YEAR FROM sf.sale_date)::SMALLINT ELSE (EXTRACT(YEAR FROM sf.sale_date) - 1)::SMALLINT END) AS financial_year,
        (CASE WHEN EXTRACT(MONTH FROM sf.sale_date) >= 4 THEN (EXTRACT(MONTH FROM sf.sale_date) - 3)::SMALLINT ELSE (EXTRACT(MONTH FROM sf.sale_date) + 9)::SMALLINT END) AS financial_month,
        d.headquarters_id,
        sf.depot_id,
        b.company_id,
        sf.brand_id,
        l.group_id,
        sf.licensee_id,
        ROUND(SUM(sf.total_case), 2) AS total_cases,
        ROUND(SUM(sf.total_btl), 2)  AS total_bottles,
        ROUND(SUM(sf.total_bl), 2)   AS total_bl,
        NOW()
    FROM public.sales_fact sf
    JOIN public.depots d ON sf.depot_id = d.depot_id
    JOIN public.brands b ON sf.brand_id = b.brand_id
    LEFT JOIN public.licensees l ON sf.licensee_id = l.licensee_id
    WHERE sf.sale_date = p_sale_date
    GROUP BY
        sf.sale_date,
        d.headquarters_id,
        sf.depot_id,
        b.company_id,
        sf.brand_id,
        l.group_id,
        sf.licensee_id;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION public.refresh_sales_monthly_summary_for_month(p_month_start DATE)
RETURNS VOID AS $$
DECLARE
    v_month_end DATE := (p_month_start + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
BEGIN
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
        total_cases,
        total_bottles,
        total_bl,
        refreshed_at
    )
    SELECT
        p_month_start,
        (CASE WHEN EXTRACT(MONTH FROM p_month_start) >= 4 THEN EXTRACT(YEAR FROM p_month_start)::SMALLINT ELSE (EXTRACT(YEAR FROM p_month_start) - 1)::SMALLINT END) AS financial_year,
        (CASE WHEN EXTRACT(MONTH FROM p_month_start) >= 4 THEN (EXTRACT(MONTH FROM p_month_start) - 3)::SMALLINT ELSE (EXTRACT(MONTH FROM p_month_start) + 9)::SMALLINT END) AS financial_month,
        d.headquarters_id,
        sf.depot_id,
        b.company_id,
        sf.brand_id,
        l.group_id,
        sf.licensee_id,
        ROUND(SUM(sf.total_case), 2) AS total_cases,
        ROUND(SUM(sf.total_btl), 2)  AS total_bottles,
        ROUND(SUM(sf.total_bl), 2)   AS total_bl,
        NOW()
    FROM public.sales_fact sf
    JOIN public.depots d ON sf.depot_id = d.depot_id
    JOIN public.brands b ON sf.brand_id = b.brand_id
    LEFT JOIN public.licensees l ON sf.licensee_id = l.licensee_id
    WHERE sf.sale_date >= p_month_start AND sf.sale_date <= v_month_end
    GROUP BY
        d.headquarters_id,
        sf.depot_id,
        b.company_id,
        sf.brand_id,
        l.group_id,
        sf.licensee_id;
END;
$$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION refresh_sales_daily_summary_for_date(DATE) TO authenticated, service_role, anon;
GRANT EXECUTE ON FUNCTION refresh_sales_monthly_summary_for_month(DATE) TO authenticated, service_role, anon;
