-- Migration: 009_fix_summaries_and_filtering.sql
-- Purpose: Fix summary rebuild alignment, correct depot filtering on summary tables, stop BIGINT truncation, and add date query helper.

-- ── 1. Date query helper ─────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.get_distinct_sale_dates()
RETURNS TABLE(sale_date DATE) AS $$
BEGIN
    RETURN QUERY SELECT DISTINCT sf.sale_date FROM public.sales_fact sf ORDER BY sf.sale_date;
END;
$$ LANGUAGE plpgsql STABLE;

GRANT EXECUTE ON FUNCTION public.get_distinct_sale_dates() TO authenticated, service_role, anon;

-- ── 2. Rebuild Daily Summary with statement timeout protection ────────────────
CREATE OR REPLACE FUNCTION public.refresh_sales_daily_summary_for_date(p_sale_date DATE)
RETURNS VOID AS $$
BEGIN
    -- Protect against connection-level statement timeout
    PERFORM set_config('statement_timeout', '60000', true);

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

GRANT EXECUTE ON FUNCTION public.refresh_sales_daily_summary_for_date(DATE) TO authenticated, service_role, anon;

-- ── 3. Rebuild Monthly Summary from complete Daily Summary with timeout protection and depot filter ──
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

-- ── 4. Stop BIGINT truncation in mobile sales summary (drop first due to return type change) ──────────
DROP FUNCTION IF EXISTS public.get_mobile_sales_summary(DATE, DATE, UUID);

CREATE OR REPLACE FUNCTION public.get_mobile_sales_summary(
    p_start_date  DATE,
    p_target_date DATE,
    p_hq_id       UUID DEFAULT NULL
)
RETURNS TABLE (
    company_id      UUID,
    brand_id        UUID,
    depot_id        UUID,
    headquarters_id UUID,
    total_cases     NUMERIC,
    total_bottles   NUMERIC,
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
        ROUND(SUM(d.total_case), 2)::NUMERIC  AS total_cases,
        ROUND(SUM(d.total_btl), 2)::NUMERIC   AS total_bottles,
        ROUND(SUM(d.total_bl), 2)::NUMERIC    AS total_bl
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

GRANT EXECUTE ON FUNCTION public.get_mobile_sales_summary(DATE, DATE, UUID) TO authenticated, service_role, anon;

DROP FUNCTION IF EXISTS public.get_mobile_tsm_sales_summary(DATE, DATE);

CREATE OR REPLACE FUNCTION public.get_mobile_tsm_sales_summary(
    p_start_date DATE,
    p_end_date   DATE
)
RETURNS TABLE (
    user_id       UUID,
    company_id    UUID,
    brand_id      UUID,
    total_cases   NUMERIC,
    total_bottles NUMERIC,
    total_bl      NUMERIC
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        usf.user_id,
        usf.company_id,
        usf.brand_id,
        ROUND(SUM(usf.cases), 2)::NUMERIC   AS total_cases,
        ROUND(SUM(usf.bottles), 2)::NUMERIC AS total_bottles,
        ROUND(SUM(usf.bl), 2)::NUMERIC      AS total_bl
    FROM public.user_sales_fact usf
    WHERE usf.sale_date >= p_start_date
      AND usf.sale_date <= p_end_date
    GROUP BY usf.user_id, usf.company_id, usf.brand_id;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_tsm_sales_summary(DATE, DATE) TO authenticated, service_role, anon;

-- ── 5. Stop BIGINT truncation in mobile sales summary JSONs ──────────────────
CREATE OR REPLACE FUNCTION public.get_mobile_sales_summary_json(
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
            SELECT jsonb_agg(row_to_json(comp)::jsonb) FROM (
                SELECT
                    d.company_id,
                    d.brand_id,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_case ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_btl  ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_bl ELSE 0 END), 2)::NUMERIC  AS daily_bl,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_case ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_btl  ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start  THEN d.total_bl  ELSE 0 END), 2)::NUMERIC AS mtd_bl,
                    ROUND(SUM(d.total_case), 2)::NUMERIC                                                         AS ytd_cases,
                    ROUND(SUM(d.total_btl), 2)::NUMERIC                                                          AS ytd_bottles,
                    ROUND(SUM(d.total_bl), 2)::NUMERIC                                                         AS ytd_bl
                FROM public.dashboard_summary_daily d
                WHERE d.sale_date >= p_ytd_start
                  AND d.sale_date <= p_target_date
                  AND (p_hq_id IS NULL OR d.headquarters_id = p_hq_id)
                GROUP BY d.company_id, d.brand_id
            ) comp
        ),
        'depots', (
            SELECT jsonb_agg(row_to_json(dep)::jsonb) FROM (
                SELECT
                    d.depot_id,
                    d.brand_id,
                    d.headquarters_id,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_case ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date  THEN d.total_btl  ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date = p_target_date THEN d.total_bl ELSE 0 END), 2)::NUMERIC  AS daily_bl,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_case ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start   THEN d.total_btl  ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN d.sale_date >= p_mtd_start  THEN d.total_bl  ELSE 0 END), 2)::NUMERIC AS mtd_bl,
                    ROUND(SUM(d.total_case), 2)::NUMERIC                                                         AS ytd_cases,
                    ROUND(SUM(d.total_btl), 2)::NUMERIC                                                          AS ytd_bottles,
                    ROUND(SUM(d.total_bl), 2)::NUMERIC                                                         AS ytd_bl
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

GRANT EXECUTE ON FUNCTION public.get_mobile_sales_summary_json(DATE, DATE, DATE, UUID) TO authenticated, service_role, anon;

CREATE OR REPLACE FUNCTION public.get_mobile_tsm_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_agg(row_to_json(tsm_row)::jsonb)
    INTO v_result
    FROM (
        SELECT
            usf.user_id,
            usf.company_id,
            usf.brand_id,
            ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
            ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
            ROUND(SUM(CASE WHEN usf.sale_date = p_target_date THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS daily_bl,
            ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
            ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
            ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS mtd_bl,
            ROUND(SUM(usf.cases), 2)::NUMERIC                                                             AS ytd_cases,
            ROUND(SUM(usf.bottles), 2)::NUMERIC                                                           AS ytd_bottles,
            ROUND(SUM(usf.bl), 2)::NUMERIC                                                              AS ytd_bl
        FROM public.user_sales_fact usf
        WHERE usf.sale_date >= p_ytd_start
          AND usf.sale_date <= p_target_date
        GROUP BY usf.user_id, usf.company_id, usf.brand_id
    ) tsm_row;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE) TO authenticated, service_role, anon;

-- ── 6. Fix Depot filtering in licensee-brand functions ──────────────────────
CREATE OR REPLACE FUNCTION public.get_group_licensees_summary_json(
    p_group_id    UUID,
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_depot_name  TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
    v_month_start DATE;
    v_depot_id UUID := NULL;
BEGIN
    v_month_start := DATE_TRUNC('month', p_target_date)::DATE;

    IF p_depot_name IS NOT NULL AND p_depot_name != '' THEN
        SELECT depot_id INTO v_depot_id FROM public.depots WHERE LOWER(name) = LOWER(p_depot_name) LIMIT 1;
    END IF;

    SELECT jsonb_agg(row_to_json(lic)::jsonb) FROM (
        WITH excluded_brands AS (
            SELECT b.brand_id
            FROM public.brands b
            JOIN public.companies c ON b.company_id = c.company_id
            WHERE p_exclude_company IS NOT NULL
              AND p_exclude_company != ''
              AND LOWER(TRIM(c.company_name)) = LOWER(TRIM(p_exclude_company))
        ),
        group_lics AS (
            SELECT l.licensee_id, l.licensee_name, l.trade, d.name AS depot_name
            FROM public.licensees l
            LEFT JOIN public.depots d ON l.depot_id = d.depot_id
            WHERE l.group_id = p_group_id AND l.is_active = true
        ),
        daily_lic AS (
            SELECT
                sds.licensee_id,
                SUM(sds.total_cases)   AS daily_cases,
                SUM(sds.total_bottles) AS daily_bottles
            FROM public.sales_daily_summary sds
            JOIN group_lics gl ON sds.licensee_id = gl.licensee_id
            WHERE sds.sale_date = p_target_date
              AND (v_depot_id IS NULL OR sds.depot_id = v_depot_id)
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sds.brand_id IS NULL
                  OR sds.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY sds.licensee_id
        ),
        mtd_lic AS (
            SELECT
                sms.licensee_id,
                SUM(sms.total_cases)   AS mtd_cases,
                SUM(sms.total_bottles) AS mtd_bottles
            FROM public.sales_monthly_summary sms
            JOIN group_lics gl ON sms.licensee_id = gl.licensee_id
            WHERE sms.month_start = v_month_start
              AND (v_depot_id IS NULL OR sms.depot_id = v_depot_id)
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sms.brand_id IS NULL
                  OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY sms.licensee_id
        ),
        ytd_lic AS (
            SELECT
                sms.licensee_id,
                SUM(sms.total_cases)   AS ytd_cases,
                SUM(sms.total_bottles) AS ytd_bottles
            FROM public.sales_monthly_summary sms
            JOIN group_lics gl ON sms.licensee_id = gl.licensee_id
            WHERE sms.month_start >= DATE_TRUNC('month', p_ytd_start)::DATE
              AND sms.month_start <= v_month_start
              AND (v_depot_id IS NULL OR sms.depot_id = v_depot_id)
              AND (
                  p_exclude_company IS NULL OR p_exclude_company = ''
                  OR sms.brand_id IS NULL
                  OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
              )
            GROUP BY sms.licensee_id
        )
        SELECT
            gl.licensee_id,
            gl.licensee_name::TEXT,
            COALESCE(gl.trade, 'Off')::TEXT                                             AS trade,
            COALESCE(gl.depot_name, 'Unassigned')::TEXT                                 AS depot_name,
            CASE WHEN gl.depot_name IS NOT NULL
                 THEN ARRAY[gl.depot_name::TEXT]
                 ELSE ARRAY[]::TEXT[] END                                               AS licensee_depots,
            ROUND(COALESCE(dl.daily_cases,   0.0), 2)::NUMERIC                         AS daily_cases,
            ROUND(COALESCE(dl.daily_bottles, 0.0), 2)::NUMERIC                         AS daily_bottles,
            ROUND(COALESCE(ml.mtd_cases,     0.0), 2)::NUMERIC                         AS mtd_cases,
            ROUND(COALESCE(ml.mtd_bottles,   0.0), 2)::NUMERIC                         AS mtd_bottles,
            ROUND(COALESCE(yl.ytd_cases,     0.0), 2)::NUMERIC                         AS ytd_cases,
            ROUND(COALESCE(yl.ytd_bottles,   0.0), 2)::NUMERIC                         AS ytd_bottles,
            ROUND(COALESCE(ml.mtd_cases,     0.0), 2)::NUMERIC                         AS total_cases,
            ROUND(COALESCE(ml.mtd_bottles,   0.0), 2)::NUMERIC                         AS total_bottles
        FROM group_lics gl
        LEFT JOIN daily_lic dl ON gl.licensee_id = dl.licensee_id
        LEFT JOIN mtd_lic ml   ON gl.licensee_id = ml.licensee_id
        LEFT JOIN ytd_lic yl   ON gl.licensee_id = yl.licensee_id
        WHERE (p_depot_name IS NULL OR p_depot_name = '' OR LOWER(gl.depot_name) = LOWER(p_depot_name) OR dl.daily_cases > 0 OR ml.mtd_cases > 0 OR yl.ytd_cases > 0)
        ORDER BY ml.mtd_cases DESC NULLS LAST
    ) lic INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_group_licensees_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;

CREATE OR REPLACE FUNCTION public.get_licensee_brand_sales_summary_json(
    p_licensee_id UUID,
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_depot_name  TEXT DEFAULT NULL,
    p_exclude_company TEXT DEFAULT 'Others'
)
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
    v_month_start DATE;
    v_depot_id UUID := NULL;
BEGIN
    v_month_start := DATE_TRUNC('month', p_target_date)::DATE;

    IF p_depot_name IS NOT NULL AND p_depot_name != '' THEN
        SELECT depot_id INTO v_depot_id FROM public.depots WHERE LOWER(name) = LOWER(p_depot_name) LIMIT 1;
    END IF;

    SELECT jsonb_agg(row_to_json(bs)::jsonb) FROM (
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
            b.brand_id,
            b.brand_name::TEXT                                                                              AS brand_name,
            COALESCE(c.company_name, 'Other')::TEXT                                                         AS company_name,
            COALESCE(MAX(li.depot_name), 'Unassigned')::TEXT                                                AS depot_name,
            ROUND(SUM(CASE WHEN sds.sale_date = p_target_date THEN sds.total_cases ELSE 0 END), 2)::NUMERIC  AS daily_cases,
            ROUND(SUM(CASE WHEN sds.sale_date = p_target_date THEN sds.total_bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_cases ELSE 0 END), 2)::NUMERIC  AS mtd_cases,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
            ROUND(SUM(sms.total_cases), 2)::NUMERIC                                                         AS ytd_cases,
            ROUND(SUM(sms.total_bottles),  2)::NUMERIC                                                      AS ytd_bottles,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_cases ELSE 0 END), 2)::NUMERIC  AS total_cases,
            ROUND(SUM(CASE WHEN sms.month_start = v_month_start THEN sms.total_bottles ELSE 0 END), 2)::NUMERIC AS total_bottles,
            CASE WHEN MAX(li.depot_name) IS NOT NULL
                 THEN ARRAY[MAX(li.depot_name)::TEXT]
                 ELSE ARRAY[]::TEXT[] END                                                                       AS sales_depots
        FROM public.sales_monthly_summary sms
        LEFT JOIN public.sales_daily_summary sds ON sms.licensee_id = sds.licensee_id 
                                                 AND sms.brand_id = sds.brand_id 
                                                 AND sds.sale_date = p_target_date
                                                 AND (v_depot_id IS NULL OR sds.depot_id = v_depot_id)
        JOIN public.brands b    ON sms.brand_id   = b.brand_id
        JOIN public.companies c ON b.company_id   = c.company_id
        LEFT JOIN lic_info li   ON sms.licensee_id = li.licensee_id
        WHERE sms.licensee_id = p_licensee_id
          AND sms.month_start >= DATE_TRUNC('month', p_ytd_start)::DATE
          AND sms.month_start <= v_month_start
          AND (v_depot_id IS NULL OR sms.depot_id = v_depot_id)
          AND (
              p_exclude_company IS NULL OR p_exclude_company = ''
              OR sms.brand_id IS NULL
              OR sms.brand_id NOT IN (SELECT eb.brand_id FROM excluded_brands eb)
          )
        GROUP BY b.brand_id, b.brand_name, c.company_name
        ORDER BY mtd_cases DESC NULLS LAST
    ) bs INTO v_result;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_licensee_brand_sales_summary_json(UUID, DATE, DATE, DATE, TEXT, TEXT) TO authenticated, service_role, anon;
