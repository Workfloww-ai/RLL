-- 004_cascading_sales_rpc.sql
-- Migration: Add RPC functions and indexes for Group -> Licensee -> Brand sales hierarchy using sales_fact

-- 1. Composite indexes on sales_fact and licensees for query optimization
CREATE INDEX IF NOT EXISTS idx_sales_fact_date_lic_brand 
ON public.sales_fact (sale_date, licensee_id, brand_id);

CREATE INDEX IF NOT EXISTS idx_sales_fact_lic_date 
ON public.sales_fact (licensee_id, sale_date);

CREATE INDEX IF NOT EXISTS idx_licensees_group_depot 
ON public.licensees (group_id, depot_id);


-- 2. RPC Function: Get Cascading Groups Summary (Excludes 'Others' by default)
CREATE OR REPLACE FUNCTION public.get_cascading_groups_summary(
    p_date_from DATE,
    p_date_to DATE,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS TABLE (
    group_id UUID,
    group_name TEXT,
    total_licensees BIGINT,
    linked_depots TEXT[],
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
    active_lics AS (
        SELECT l.licensee_id, l.group_id, l.depot_id
        FROM public.licensees l
        WHERE l.is_active = true AND l.group_id IS NOT NULL
    ),
    group_lic_counts AS (
        SELECT 
            g.group_id,
            COUNT(l.licensee_id) AS lic_count,
            ARRAY_AGG(DISTINCT d.name) FILTER (WHERE d.name IS NOT NULL) AS lic_depots
        FROM public.groups g
        LEFT JOIN public.licensees l ON g.group_id = l.group_id AND l.is_active = true
        LEFT JOIN public.depots d ON l.depot_id = d.depot_id
        WHERE g.is_active = true
        GROUP BY g.group_id
    ),
    sales_agg AS (
        SELECT 
            al.group_id,
            SUM(sf.total_case) AS cases,
            SUM(sf.total_btl) AS bottles
        FROM public.sales_fact sf
        JOIN active_lics al ON sf.licensee_id = al.licensee_id
        WHERE sf.sale_date >= p_date_from 
          AND sf.sale_date <= p_date_to
          AND (p_exclude_company IS NULL OR p_exclude_company = '' OR sf.brand_id IS NULL OR sf.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb))
        GROUP BY al.group_id
    )
    SELECT 
        g.group_id,
        g.group_name::TEXT,
        COALESCE(glc.lic_count, 0)::BIGINT AS total_licensees,
        COALESCE(glc.lic_depots, ARRAY[]::TEXT[]) AS linked_depots,
        ROUND(COALESCE(sa.cases, 0.0), 2)::NUMERIC AS total_cases,
        ROUND(COALESCE(sa.bottles, 0.0), 2)::NUMERIC AS total_bottles
    FROM public.groups g
    LEFT JOIN sales_agg sa ON g.group_id = sa.group_id
    LEFT JOIN group_lic_counts glc ON g.group_id = glc.group_id
    WHERE g.is_active = true AND (COALESCE(glc.lic_count, 0) > 0 OR COALESCE(sa.cases, 0) > 0)
    ORDER BY total_cases DESC, total_licensees DESC;
END;
$$;


-- 3. RPC Function: Get Group Licensees Summary (Excludes 'Others' by default)
CREATE OR REPLACE FUNCTION public.get_group_licensees_summary(
    p_group_id UUID,
    p_date_from DATE,
    p_date_to DATE,
    p_depot_name TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS TABLE (
    licensee_id UUID,
    licensee_name TEXT,
    trade TEXT,
    licensee_depots TEXT[],
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
    group_lics AS (
        SELECT l.licensee_id, l.licensee_name, l.trade, l.depot_id, d.name AS depot_name
        FROM public.licensees l
        LEFT JOIN public.depots d ON l.depot_id = d.depot_id
        WHERE l.group_id = p_group_id AND l.is_active = true
    ),
    lic_sales AS (
        SELECT 
            sf.licensee_id,
            SUM(sf.total_case) AS cases,
            SUM(sf.total_btl) AS bottles
        FROM public.sales_fact sf
        JOIN group_lics gl ON sf.licensee_id = gl.licensee_id
        WHERE sf.sale_date >= p_date_from 
          AND sf.sale_date <= p_date_to
          AND (p_exclude_company IS NULL OR p_exclude_company = '' OR sf.brand_id IS NULL OR sf.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb))
          AND (p_depot_name IS NULL OR p_depot_name = '' OR LOWER(gl.depot_name) = LOWER(p_depot_name))
        GROUP BY sf.licensee_id
    )
    SELECT 
        gl.licensee_id,
        gl.licensee_name::TEXT,
        COALESCE(gl.trade, 'Off')::TEXT AS trade,
        CASE WHEN gl.depot_name IS NOT NULL THEN ARRAY[gl.depot_name::TEXT] ELSE ARRAY[]::TEXT[] END AS licensee_depots,
        ROUND(COALESCE(ls.cases, 0.0), 2)::NUMERIC AS total_cases,
        ROUND(COALESCE(ls.bottles, 0.0), 2)::NUMERIC AS total_bottles
    FROM group_lics gl
    LEFT JOIN lic_sales ls ON gl.licensee_id = ls.licensee_id
    WHERE (p_depot_name IS NULL OR p_depot_name = '') OR LOWER(gl.depot_name) = LOWER(p_depot_name)
    ORDER BY total_cases DESC;
END;
$$;


-- 4. RPC Function: Get Licensee Brand Sales Summary (Excludes 'Others' by default)
CREATE OR REPLACE FUNCTION public.get_licensee_brand_sales_summary(
    p_licensee_id UUID,
    p_date_from DATE,
    p_date_to DATE,
    p_depot_name TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS TABLE (
    brand_id UUID,
    brand_name TEXT,
    company_name TEXT,
    total_cases NUMERIC,
    total_bottles NUMERIC,
    sales_depots TEXT[]
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
    lic_info AS (
        SELECT l.licensee_id, d.name AS depot_name
        FROM public.licensees l
        LEFT JOIN public.depots d ON l.depot_id = d.depot_id
        WHERE l.licensee_id = p_licensee_id
    )
    SELECT 
        b.brand_id AS brand_id,
        b.brand_name::TEXT AS brand_name,
        COALESCE(c.company_name, 'Other')::TEXT AS company_name,
        ROUND(SUM(sf.total_case), 2)::NUMERIC AS total_cases,
        ROUND(SUM(sf.total_btl), 2)::NUMERIC AS total_bottles,
        CASE WHEN li.depot_name IS NOT NULL THEN ARRAY[li.depot_name::TEXT] ELSE ARRAY[]::TEXT[] END AS sales_depots
    FROM public.sales_fact sf
    JOIN public.brands b ON sf.brand_id = b.brand_id
    JOIN public.companies c ON b.company_id = c.company_id
    LEFT JOIN lic_info li ON sf.licensee_id = li.licensee_id
    WHERE sf.licensee_id = p_licensee_id
      AND sf.sale_date >= p_date_from 
      AND sf.sale_date <= p_date_to
      AND (p_exclude_company IS NULL OR p_exclude_company = '' OR sf.brand_id IS NULL OR sf.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb))
      AND (p_depot_name IS NULL OR p_depot_name = '' OR LOWER(li.depot_name) = LOWER(p_depot_name))
    GROUP BY b.brand_id, b.brand_name, c.company_name, li.depot_name
    ORDER BY total_cases DESC;
END;
$$;
