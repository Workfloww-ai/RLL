-- 005_company_brand_licensee_rpc.sql
-- Migration: Add RPC functions for Company -> Brand -> Licensee sales hierarchy using pre-aggregated sales_daily_summary

-- 1. Composite indexes on sales_daily_summary for maximum query optimization
CREATE INDEX IF NOT EXISTS idx_sales_daily_summary_brand_lic_date 
ON public.sales_daily_summary (brand_id, licensee_id, sale_date);

CREATE INDEX IF NOT EXISTS idx_sales_daily_summary_comp_date 
ON public.sales_daily_summary (company_id, sale_date);


-- 2. RPC Function: Get Company Brands Summary (Reads from sales_daily_summary)
CREATE OR REPLACE FUNCTION public.get_company_brand_sales_summary(
    p_company_id UUID,
    p_date_from DATE,
    p_date_to DATE,
    p_hq_name TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS TABLE (
    brand_id UUID,
    brand_name TEXT,
    company_name TEXT,
    selling_licensees_count BIGINT,
    total_cases NUMERIC,
    total_bottles NUMERIC
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    WITH excluded_brands AS (
        SELECT b.brand_id 
        FROM public.brands b
        JOIN public.companies c ON b.company_id = c.company_id
        WHERE p_exclude_company IS NOT NULL 
          AND p_exclude_company != '' 
          AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company))
    ),
    company_info AS (
        SELECT c.company_id, c.company_name
        FROM public.companies c
        WHERE c.company_id = p_company_id
    ),
    comp_brands AS (
        SELECT b.brand_id, b.brand_name, ci.company_name
        FROM public.brands b
        JOIN company_info ci ON b.company_id = ci.company_id
        WHERE (p_exclude_company IS NULL OR p_exclude_company = '' OR b.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb))
    ),
    sales_agg AS (
        SELECT 
            sds.brand_id,
            COUNT(DISTINCT sds.licensee_id) AS lic_count,
            SUM(sds.total_cases) AS cases,
            SUM(sds.total_bottles) AS bottles
        FROM public.sales_daily_summary sds
        JOIN comp_brands cb ON sds.brand_id = cb.brand_id
        LEFT JOIN public.headquarters hq ON sds.headquarters_id = hq.headquarters_id
        WHERE sds.sale_date >= p_date_from 
          AND sds.sale_date <= p_date_to
          AND (p_hq_name IS NULL OR p_hq_name = '' OR p_hq_name = 'All Headquarters' OR LOWER(hq.name) = LOWER(p_hq_name))
        GROUP BY sds.brand_id
    )
    SELECT 
        cb.brand_id,
        cb.brand_name::TEXT,
        cb.company_name::TEXT,
        COALESCE(sa.lic_count, 0)::BIGINT AS selling_licensees_count,
        ROUND(COALESCE(sa.cases, 0.0), 2)::NUMERIC AS total_cases,
        ROUND(COALESCE(sa.bottles, 0.0), 2)::NUMERIC AS total_bottles
    FROM comp_brands cb
    LEFT JOIN sales_agg sa ON cb.brand_id = sa.brand_id
    ORDER BY total_cases DESC, cb.brand_name ASC;
END;
$$;


-- 3. RPC Function: Get Brand Licensees Sales Summary (Reads from sales_daily_summary)
CREATE OR REPLACE FUNCTION public.get_brand_licensees_summary(
    p_brand_id UUID,
    p_date_from DATE,
    p_date_to DATE,
    p_hq_name TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS TABLE (
    licensee_id UUID,
    licensee_name TEXT,
    trade TEXT,
    depot_name TEXT,
    total_cases NUMERIC,
    total_bottles NUMERIC
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    WITH excluded_brands AS (
        SELECT b.brand_id 
        FROM public.brands b
        JOIN public.companies c ON b.company_id = c.company_id
        WHERE p_exclude_company IS NOT NULL 
          AND p_exclude_company != '' 
          AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company))
    ),
    target_brand AS (
        SELECT b.brand_id, b.brand_name
        FROM public.brands b
        WHERE b.brand_id = p_brand_id
          AND (p_exclude_company IS NULL OR p_exclude_company = '' OR b.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb))
    )
    SELECT 
        l.licensee_id,
        l.licensee_name::TEXT,
        COALESCE(l.trade, 'Off')::TEXT AS trade,
        COALESCE(d.name, 'Unassigned')::TEXT AS depot_name,
        ROUND(SUM(sds.total_cases), 2)::NUMERIC AS total_cases,
        ROUND(SUM(sds.total_bottles), 2)::NUMERIC AS total_bottles
    FROM public.sales_daily_summary sds
    JOIN target_brand tb ON sds.brand_id = tb.brand_id
    JOIN public.licensees l ON sds.licensee_id = l.licensee_id
    LEFT JOIN public.depots d ON sds.depot_id = d.depot_id
    LEFT JOIN public.headquarters hq ON sds.headquarters_id = hq.headquarters_id
    WHERE sds.sale_date >= p_date_from 
      AND sds.sale_date <= p_date_to
      AND (p_hq_name IS NULL OR p_hq_name = '' OR p_hq_name = 'All Headquarters' OR LOWER(hq.name) = LOWER(p_hq_name))
    GROUP BY l.licensee_id, l.licensee_name, l.trade, d.name
    HAVING SUM(sds.total_cases) > 0 OR SUM(sds.total_bottles) > 0
    ORDER BY total_cases DESC, l.licensee_name ASC;
END;
$$;
