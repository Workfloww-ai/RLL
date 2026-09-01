-- Migration: 018_fix_summary_table_refresh_rpcs.sql
-- Description: Fix refresh_sales_monthly_summary_for_month to accept (p_month_start DATE, p_depot_id UUID DEFAULT NULL) and ensure robust summary table auto-fill during Excel upload.

-- 1. Overload / Replace refresh_sales_monthly_summary_for_month
DROP FUNCTION IF EXISTS public.refresh_sales_monthly_summary_for_month(DATE);
DROP FUNCTION IF EXISTS public.refresh_sales_monthly_summary_for_month(DATE, UUID);

CREATE OR REPLACE FUNCTION public.refresh_sales_monthly_summary_for_month(
    p_month_start DATE,
    p_depot_id UUID DEFAULT NULL
)
RETURNS VOID AS $$
DECLARE
    v_month_end DATE := (p_month_start + INTERVAL '1 month' - INTERVAL '1 day')::DATE;
    v_fy SMALLINT;
    v_fm SMALLINT;
BEGIN
    -- Protect against connection-level statement timeout
    PERFORM set_config('statement_timeout', '60000', true);

    IF EXTRACT(MONTH FROM p_month_start) >= 4 THEN
        v_fy := EXTRACT(YEAR FROM p_month_start)::SMALLINT;
        v_fm := (EXTRACT(MONTH FROM p_month_start) - 3)::SMALLINT;
    ELSE
        v_fy := (EXTRACT(YEAR FROM p_month_start) - 1)::SMALLINT;
        v_fm := (EXTRACT(MONTH FROM p_month_start) + 9)::SMALLINT;
    END IF;

    -- Delete existing monthly summary rows for clean re-aggregation
    IF p_depot_id IS NULL THEN
        DELETE FROM public.sales_monthly_summary WHERE month_start = p_month_start;
    ELSE
        DELETE FROM public.sales_monthly_summary WHERE month_start = p_month_start AND depot_id = p_depot_id;
    END IF;

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
        COALESCE(SUM(total_cases), 0.0) AS total_cases,
        COALESCE(SUM(total_bottles), 0.0) AS total_bottles,
        COALESCE(SUM(total_bl), 0.0) AS total_bl,
        NOW()
    FROM public.sales_daily_summary
    WHERE sale_date >= p_month_start AND sale_date <= v_month_end
      AND (p_depot_id IS NULL OR depot_id = p_depot_id)
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

GRANT EXECUTE ON FUNCTION public.refresh_sales_monthly_summary_for_month(DATE, UUID) TO authenticated, service_role, anon;

-- 2. refresh_sales_daily_summary_for_date
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

GRANT EXECUTE ON FUNCTION public.refresh_sales_daily_summary_for_date(DATE) TO authenticated, service_role, anon;
