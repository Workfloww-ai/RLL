-- Migration: 029_fix_dynamic_office_hq_and_deduplicate.sql
-- Purpose: 
-- 1. Dynamically update offices.headquarters_id using majority statistical count (zero hardcoding).
-- 2. Deduplicate sales_fact and sales_daily_summary records.
-- 3. Update sales_daily_summary.headquarters_id from office.headquarters_id so all summary rows match the dynamic hierarchy.

-- ── 1. Dynamically Update offices.headquarters_id (Zero Hardcoding) ─────────
WITH office_majority_hq AS (
    SELECT 
        d.office_id, 
        sds.headquarters_id, 
        COUNT(*) AS invoice_count,
        ROW_NUMBER() OVER (PARTITION BY d.office_id ORDER BY COUNT(*) DESC) AS rnk
    FROM public.sales_daily_summary sds
    JOIN public.depots d ON sds.depot_id = d.depot_id
    WHERE sds.headquarters_id IS NOT NULL 
      AND d.office_id IS NOT NULL
    GROUP BY d.office_id, sds.headquarters_id
)
UPDATE public.offices o
SET headquarters_id = omh.headquarters_id
FROM office_majority_hq omh
WHERE o.office_id = omh.office_id 
  AND omh.rnk = 1;

-- Also update sales_daily_summary rows to match office.headquarters_id
UPDATE public.sales_daily_summary sds
SET headquarters_id = o.headquarters_id
FROM public.depots d
JOIN public.offices o ON d.office_id = o.office_id
WHERE sds.depot_id = d.depot_id
  AND o.headquarters_id IS NOT NULL
  AND (sds.headquarters_id IS NULL OR sds.headquarters_id != o.headquarters_id);

-- ── 2. Deduplicate sales_fact ───────────────────────────────────────────────
DELETE FROM public.sales_fact a
USING public.sales_fact b
WHERE a.fact_id > b.fact_id
  AND a.sale_date = b.sale_date
  AND a.depot_id = b.depot_id
  AND a.brand_id = b.brand_id
  AND a.licensee_id IS NOT DISTINCT FROM b.licensee_id
  AND a.total_case IS NOT DISTINCT FROM b.total_case
  AND a.total_btl IS NOT DISTINCT FROM b.total_btl
  AND a.batch_id IS NOT DISTINCT FROM b.batch_id;

-- ── 3. Deduplicate sales_daily_summary & Sync ──────────────────────────────
DELETE FROM public.sales_daily_summary s1
USING public.sales_daily_summary s2
WHERE s1.summary_id > s2.summary_id
  AND s1.sale_date = s2.sale_date
  AND s1.depot_id = s2.depot_id
  AND s1.brand_id = s2.brand_id
  AND s1.company_id IS NOT DISTINCT FROM s2.company_id;

WITH sf_summary AS (
    SELECT 
        sf.sale_date,
        sf.depot_id,
        sf.brand_id,
        b.company_id,
        d.office_id,
        o.headquarters_id,
        ROUND(SUM(sf.total_case)::numeric, 2) AS calc_cases,
        ROUND(SUM(sf.total_btl)::numeric, 2) AS calc_btl,
        ROUND(SUM(sf.total_bl)::numeric, 2) AS calc_bl
    FROM public.sales_fact sf
    JOIN public.brands b ON sf.brand_id = b.brand_id
    JOIN public.depots d ON sf.depot_id = d.depot_id
    LEFT JOIN public.offices o ON d.office_id = o.office_id
    GROUP BY sf.sale_date, sf.depot_id, sf.brand_id, b.company_id, d.office_id, o.headquarters_id
)
UPDATE public.sales_daily_summary sds
SET 
    total_cases = sfs.calc_cases,
    total_bottles = sfs.calc_btl,
    total_bl = sfs.calc_bl,
    headquarters_id = sfs.headquarters_id
FROM sf_summary sfs
WHERE sds.sale_date = sfs.sale_date
  AND sds.depot_id = sfs.depot_id
  AND sds.brand_id = sfs.brand_id;
