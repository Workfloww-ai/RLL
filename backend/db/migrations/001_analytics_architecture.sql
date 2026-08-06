-- Migration: 001_analytics_architecture.sql
-- Description: Sets up enterprise analytics summary tables, financial calendar fields, unique constraints, and stored refresh functions.

-- 1. Extend dim_calendar with financial year attributes if missing
ALTER TABLE IF EXISTS public.dim_calendar
    ADD COLUMN IF NOT EXISTS financial_year_start SMALLINT,
    ADD COLUMN IF NOT EXISTS financial_year_label TEXT,
    ADD COLUMN IF NOT EXISTS financial_month SMALLINT;

-- Function to populate dim_calendar financial year fields safely
CREATE OR REPLACE FUNCTION populate_dim_calendar_fy()
RETURNS VOID AS $$
BEGIN
    UPDATE public.dim_calendar
    SET 
        financial_year_start = CASE 
            WHEN EXTRACT(MONTH FROM date_id) >= 4 THEN EXTRACT(YEAR FROM date_id)::SMALLINT
            ELSE (EXTRACT(YEAR FROM date_id) - 1)::SMALLINT
        END,
        financial_year_label = CASE 
            WHEN EXTRACT(MONTH FROM date_id) >= 4 
                THEN EXTRACT(YEAR FROM date_id)::TEXT || '-' || LPAD(((EXTRACT(YEAR FROM date_id) + 1) % 100)::TEXT, 2, '0')
            ELSE (EXTRACT(YEAR FROM date_id) - 1)::TEXT || '-' || LPAD((EXTRACT(YEAR FROM date_id) % 100)::TEXT, 2, '0')
        END,
        financial_month = CASE 
            WHEN EXTRACT(MONTH FROM date_id) >= 4 THEN (EXTRACT(MONTH FROM date_id) - 3)::SMALLINT
            ELSE (EXTRACT(MONTH FROM date_id) + 9)::SMALLINT
        END
    WHERE financial_year_start IS NULL OR financial_year_label IS NULL OR financial_month IS NULL;
END;
$$ LANGUAGE plpgsql;

SELECT populate_dim_calendar_fy();

-- 2. Fact Table Useful Access Indexes (Partition-friendly)
CREATE INDEX IF NOT EXISTS idx_sales_fact_batch_id ON public.sales_fact(batch_id);
CREATE INDEX IF NOT EXISTS idx_sales_fact_date_depot ON public.sales_fact(sale_date, depot_id) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_sales_fact_date_brand ON public.sales_fact(sale_date, brand_id) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_sales_fact_composite ON public.sales_fact(sale_date, depot_id, brand_id) WHERE is_active = true;

-- 3. Daily Summary Constraints and Indexes
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_dashboard_summary_daily'
    ) THEN
        -- Deduplicate before applying constraint
        DELETE FROM public.dashboard_summary_daily a
        USING public.dashboard_summary_daily b
        WHERE a.summary_id < b.summary_id
          AND a.sale_date = b.sale_date
          AND a.depot_id = b.depot_id
          AND a.brand_id = b.brand_id;

        ALTER TABLE public.dashboard_summary_daily 
            ADD CONSTRAINT uq_dashboard_summary_daily UNIQUE (sale_date, depot_id, brand_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_daily_summary_date ON public.dashboard_summary_daily(sale_date);
CREATE INDEX IF NOT EXISTS idx_daily_summary_depot_date ON public.dashboard_summary_daily(depot_id, sale_date);
CREATE INDEX IF NOT EXISTS idx_daily_summary_brand_date ON public.dashboard_summary_daily(brand_id, sale_date);
CREATE INDEX IF NOT EXISTS idx_daily_summary_hq_date ON public.dashboard_summary_daily(headquarters_id, sale_date);

-- 4. Monthly Summary Constraints and Indexes
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_dashboard_summary_monthly'
    ) THEN
        -- Deduplicate before applying constraint
        DELETE FROM public.dashboard_summary_monthly a
        USING public.dashboard_summary_monthly b
        WHERE a.summary_id < b.summary_id
          AND a.month_start = b.month_start
          AND a.depot_id = b.depot_id
          AND a.brand_id = b.brand_id;

        ALTER TABLE public.dashboard_summary_monthly 
            ADD CONSTRAINT uq_dashboard_summary_monthly UNIQUE (month_start, depot_id, brand_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_monthly_summary_month ON public.dashboard_summary_monthly(month_start);
CREATE INDEX IF NOT EXISTS idx_monthly_summary_fy ON public.dashboard_summary_monthly(financial_year_start);
CREATE INDEX IF NOT EXISTS idx_monthly_summary_depot ON public.dashboard_summary_monthly(depot_id, month_start);
CREATE INDEX IF NOT EXISTS idx_monthly_summary_brand ON public.dashboard_summary_monthly(brand_id, month_start);
CREATE INDEX IF NOT EXISTS idx_monthly_summary_hq ON public.dashboard_summary_monthly(headquarters_id, month_start);

-- 5. Batch Chunks FK, Constraint, and Indexes
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'batch_chunks_batch_id_fkey'
    ) THEN
        ALTER TABLE public.batch_chunks
            ADD CONSTRAINT batch_chunks_batch_id_fkey 
            FOREIGN KEY (batch_id) REFERENCES public.upload_batches(batch_id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_batch_chunks_id_num'
    ) THEN
        ALTER TABLE public.batch_chunks
            ADD CONSTRAINT uq_batch_chunks_id_num UNIQUE (batch_id, chunk_number);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_batch_chunks_status ON public.batch_chunks(batch_id, status);

-- 6. Stored Idempotent Aggregation Functions
CREATE OR REPLACE FUNCTION refresh_dashboard_daily(p_sale_date DATE)
RETURNS VOID AS $$
BEGIN
    INSERT INTO public.dashboard_summary_daily (
        sale_date, depot_id, brand_id, headquarters_id, total_case, total_btl, total_bl, refreshed_at
    )
    SELECT 
        sf.sale_date,
        sf.depot_id,
        sf.brand_id,
        d.headquarters_id,
        SUM(sf.total_case) as total_case,
        SUM(sf.total_btl) as total_btl,
        SUM(sf.total_bl) as total_bl,
        NOW()
    FROM public.sales_fact sf
    JOIN public.depots d ON sf.depot_id = d.depot_id
    WHERE sf.sale_date = p_sale_date AND sf.is_active = true
    GROUP BY sf.sale_date, sf.depot_id, sf.brand_id, d.headquarters_id
    ON CONFLICT (sale_date, depot_id, brand_id) DO UPDATE SET
        headquarters_id = EXCLUDED.headquarters_id,
        total_case = EXCLUDED.total_case,
        total_btl = EXCLUDED.total_btl,
        total_bl = EXCLUDED.total_bl,
        refreshed_at = NOW();
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION refresh_dashboard_monthly(p_date DATE)
RETURNS VOID AS $$
DECLARE
    v_month_start DATE := DATE_TRUNC('month', p_date)::DATE;
    v_fy_start SMALLINT;
BEGIN
    SELECT CASE 
        WHEN EXTRACT(MONTH FROM v_month_start) >= 4 THEN EXTRACT(YEAR FROM v_month_start)::SMALLINT
        ELSE (EXTRACT(YEAR FROM v_month_start) - 1)::SMALLINT
    END INTO v_fy_start;

    INSERT INTO public.dashboard_summary_monthly (
        month_start, financial_year_start, depot_id, brand_id, headquarters_id, total_case, total_btl, total_bl, refreshed_at
    )
    SELECT 
        v_month_start,
        v_fy_start,
        depot_id,
        brand_id,
        headquarters_id,
        SUM(total_case),
        SUM(total_btl),
        SUM(total_bl),
        NOW()
    FROM public.dashboard_summary_daily
    WHERE sale_date >= v_month_start AND sale_date < (v_month_start + INTERVAL '1 month')::DATE
    GROUP BY depot_id, brand_id, headquarters_id
    ON CONFLICT (month_start, depot_id, brand_id) DO UPDATE SET
        financial_year_start = EXCLUDED.financial_year_start,
        headquarters_id = EXCLUDED.headquarters_id,
        total_case = EXCLUDED.total_case,
        total_btl = EXCLUDED.total_btl,
        total_bl = EXCLUDED.total_bl,
        refreshed_at = NOW();
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION refresh_sales_analytics(p_sale_date DATE)
RETURNS VOID AS $$
BEGIN
    PERFORM refresh_dashboard_daily(p_sale_date);
    PERFORM refresh_dashboard_monthly(p_sale_date);
END;
$$ LANGUAGE plpgsql;

-- 7. Ensure Monthly Partitions for sales_fact
CREATE TABLE IF NOT EXISTS public.sales_fact_2026_04 PARTITION OF public.sales_fact FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE IF NOT EXISTS public.sales_fact_2026_05 PARTITION OF public.sales_fact FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE IF NOT EXISTS public.sales_fact_2026_06 PARTITION OF public.sales_fact FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE IF NOT EXISTS public.sales_fact_2026_07 PARTITION OF public.sales_fact FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE IF NOT EXISTS public.sales_fact_2026_08 PARTITION OF public.sales_fact FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE IF NOT EXISTS public.sales_fact_2026_09 PARTITION OF public.sales_fact FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE IF NOT EXISTS public.sales_fact_2026_10 PARTITION OF public.sales_fact FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE IF NOT EXISTS public.sales_fact_2026_11 PARTITION OF public.sales_fact FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE IF NOT EXISTS public.sales_fact_2026_12 PARTITION OF public.sales_fact FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
CREATE TABLE IF NOT EXISTS public.sales_fact_2027_01 PARTITION OF public.sales_fact FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');
CREATE TABLE IF NOT EXISTS public.sales_fact_2027_02 PARTITION OF public.sales_fact FOR VALUES FROM ('2027-02-01') TO ('2027-03-01');
CREATE TABLE IF NOT EXISTS public.sales_fact_2027_03 PARTITION OF public.sales_fact FOR VALUES FROM ('2027-03-01') TO ('2027-04-01');

