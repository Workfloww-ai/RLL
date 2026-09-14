-- Migration: 008_fix_sales_summary_hq_credit.sql
-- Description: Credit sales to Licensee's Headquarters (COALESCE(l.headquarters_id, d.headquarters_id))
-- so cross-depot fulfillment correctly reflects in the licensee's assigned headquarters territory.

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
        COALESCE(l.headquarters_id, d.headquarters_id) AS headquarters_id,
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
