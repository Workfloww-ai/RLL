-- Comprehensive Schema Reconstruction with UUID Primary Keys & Seed Data

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. Users Table
CREATE TABLE IF NOT EXISTS public.users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name TEXT,
    last_name TEXT,
    email TEXT UNIQUE,
    phone TEXT,
    manager_id UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID,
    updated_by UUID
);

-- 2. Roles Table
CREATE TABLE IF NOT EXISTS public.roles (
    role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_name TEXT UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    updated_by UUID REFERENCES public.users(user_id) ON DELETE SET NULL
);

-- 3. User Roles Mapping Table
CREATE TABLE IF NOT EXISTS public.user_roles (
    user_role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES public.roles(role_id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_user_role UNIQUE (user_id, role_id)
);

-- 4. ASE TSM Hierarchy Mapping Table
CREATE TABLE IF NOT EXISTS public.ase_tsm_mapping (
    hierarchy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tsm_user_id UUID REFERENCES public.users(user_id) ON DELETE CASCADE,
    ase_user_id UUID REFERENCES public.users(user_id) ON DELETE CASCADE,
    tsm_user_role_id UUID REFERENCES public.user_roles(user_role_id) ON DELETE SET NULL,
    ase_user_role_id UUID REFERENCES public.user_roles(user_role_id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Offices Table
CREATE TABLE IF NOT EXISTS public.offices (
    office_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    state TEXT DEFAULT 'Rajasthan',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Headquarters Table
CREATE TABLE IF NOT EXISTS public.headquarters (
    headquarters_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Circles Table
CREATE TABLE IF NOT EXISTS public.circles (
    circle_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    office_id UUID REFERENCES public.offices(office_id) ON DELETE SET NULL,
    headquarters_id UUID REFERENCES public.headquarters(headquarters_id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Depots Table
CREATE TABLE IF NOT EXISTS public.depots (
    depot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    office_id UUID REFERENCES public.offices(office_id) ON DELETE SET NULL,
    headquarters_id UUID REFERENCES public.headquarters(headquarters_id) ON DELETE SET NULL,
    circle_id UUID REFERENCES public.circles(circle_id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. User Depot Assignment Table
CREATE TABLE IF NOT EXISTS public.user_depot (
    assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    depot_id UUID NOT NULL REFERENCES public.depots(depot_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_user_depot UNIQUE (user_id, depot_id)
);

-- 10. Groups Table
CREATE TABLE IF NOT EXISTS public.groups (
    group_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 11. Companies Table
CREATE TABLE IF NOT EXISTS public.companies (
    company_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name TEXT UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 12. Licensees Table
CREATE TABLE IF NOT EXISTS public.licensees (
    licensee_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    licensee_name TEXT UNIQUE NOT NULL,
    trade TEXT,
    group_id UUID REFERENCES public.groups(group_id) ON DELETE SET NULL,
    headquarters_id UUID REFERENCES public.headquarters(headquarters_id) ON DELETE SET NULL,
    office_id UUID REFERENCES public.offices(office_id) ON DELETE SET NULL,
    circle_id UUID REFERENCES public.circles(circle_id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 13. Brands Table
CREATE TABLE IF NOT EXISTS public.brands (
    brand_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_name TEXT UNIQUE NOT NULL,
    company_id UUID REFERENCES public.companies(company_id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 14. Packagings Table
CREATE TABLE IF NOT EXISTS public.packagings (
    packaging_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    packing_raw TEXT UNIQUE NOT NULL,
    bottle_size_ml NUMERIC DEFAULT 0.0,
    units_per_case INT DEFAULT 1,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 15. Upload Batches Table
CREATE TABLE IF NOT EXISTS public.upload_batches (
    batch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file TEXT,
    file_name TEXT,
    storage_path TEXT,
    load_type TEXT DEFAULT 'daily',
    covers_start DATE,
    covers_end DATE,
    row_count INT,
    total_rows INT DEFAULT 0,
    imported_rows INT DEFAULT 0,
    failed_rows INT DEFAULT 0,
    duplicate_rows INT DEFAULT 0,
    processing_time_seconds NUMERIC DEFAULT 0.0,
    status TEXT DEFAULT 'pending',
    upload_status TEXT DEFAULT 'pending',
    remarks TEXT,
    is_active BOOLEAN DEFAULT true,
    uploaded_by UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    created_by UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    updated_by UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    browser_info TEXT,
    client_ip TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 16. Batch Chunks Table
CREATE TABLE IF NOT EXISTS public.batch_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID REFERENCES public.upload_batches(batch_id) ON DELETE CASCADE,
    chunk_number INT,
    start_row INT,
    end_row INT,
    row_count INT,
    inserted_rows INT DEFAULT 0,
    status TEXT DEFAULT 'pending',
    retry_count INT DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_batch_chunks UNIQUE (batch_id, chunk_number)
);

-- 17. Raw Sales Upload Staging Table (Temporary)
CREATE TABLE IF NOT EXISTS public.raw_sales_upload (
    raw_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID REFERENCES public.upload_batches(batch_id) ON DELETE CASCADE,
    sale_date_raw TEXT,
    company_raw TEXT,
    licensee_raw TEXT,
    trade_raw TEXT,
    group_name_raw TEXT,
    hq_raw TEXT,
    deo_office_raw TEXT,
    circle_office_raw TEXT,
    depot_raw TEXT,
    ase_raw TEXT,
    asm_tsm_raw TEXT,
    brand_name_raw TEXT,
    packing_raw TEXT,
    total_case NUMERIC DEFAULT 0.0,
    total_btl NUMERIC DEFAULT 0.0,
    total_bl NUMERIC DEFAULT 0.0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 18. Upload Pipeline Logs Table
CREATE TABLE IF NOT EXISTS public.upload_pipeline_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID REFERENCES public.upload_batches(batch_id) ON DELETE CASCADE,
    step TEXT,
    status TEXT,
    message TEXT,
    logged_at TIMESTAMPTZ DEFAULT NOW()
);

-- 19. Upload Validation Errors Table
CREATE TABLE IF NOT EXISTS public.upload_validation_errors (
    error_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID REFERENCES public.upload_batches(batch_id) ON DELETE CASCADE,
    raw_id UUID REFERENCES public.raw_sales_upload(raw_id) ON DELETE CASCADE,
    column_name TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 20. Dimension Calendar Table
CREATE TABLE IF NOT EXISTS public.dim_calendar (
    date_id DATE PRIMARY KEY,
    year INT,
    quarter INT,
    month INT,
    month_name TEXT,
    day INT,
    day_of_week INT,
    day_name TEXT,
    is_weekend BOOLEAN DEFAULT false,
    financial_year_start SMALLINT,
    financial_year_label TEXT,
    financial_month SMALLINT,
    is_active BOOLEAN DEFAULT true
);

-- 21. Partitioned Sales Fact Table
CREATE TABLE IF NOT EXISTS public.sales_fact (
    fact_id UUID DEFAULT gen_random_uuid(),
    sale_date DATE NOT NULL,
    depot_id UUID REFERENCES public.depots(depot_id) ON DELETE CASCADE,
    licensee_id UUID REFERENCES public.licensees(licensee_id) ON DELETE CASCADE,
    brand_id UUID REFERENCES public.brands(brand_id) ON DELETE CASCADE,
    packaging_id UUID REFERENCES public.packagings(packaging_id) ON DELETE CASCADE,
    total_case NUMERIC DEFAULT 0.0,
    total_btl NUMERIC DEFAULT 0.0,
    total_bl NUMERIC DEFAULT 0.0,
    batch_id UUID REFERENCES public.upload_batches(batch_id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (fact_id, sale_date)
) PARTITION BY RANGE (sale_date);

-- 22. Daily Dashboard Summary Table
CREATE TABLE IF NOT EXISTS public.dashboard_summary_daily (
    summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sale_date DATE NOT NULL,
    depot_id UUID REFERENCES public.depots(depot_id) ON DELETE CASCADE,
    brand_id UUID REFERENCES public.brands(brand_id) ON DELETE CASCADE,
    company_id UUID REFERENCES public.companies(company_id) ON DELETE CASCADE,
    headquarters_id UUID REFERENCES public.headquarters(headquarters_id) ON DELETE SET NULL,
    total_case NUMERIC DEFAULT 0.0,
    total_btl NUMERIC DEFAULT 0.0,
    total_bl NUMERIC DEFAULT 0.0,
    refreshed_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_dashboard_summary_daily UNIQUE (sale_date, depot_id, brand_id, company_id)
);

-- 23. Monthly Dashboard Summary Table
CREATE TABLE IF NOT EXISTS public.dashboard_summary_monthly (
    summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    month_start DATE NOT NULL,
    financial_year_start SMALLINT,
    depot_id UUID REFERENCES public.depots(depot_id) ON DELETE CASCADE,
    brand_id UUID REFERENCES public.brands(brand_id) ON DELETE CASCADE,
    company_id UUID REFERENCES public.companies(company_id) ON DELETE CASCADE,
    headquarters_id UUID REFERENCES public.headquarters(headquarters_id) ON DELETE SET NULL,
    total_case NUMERIC DEFAULT 0.0,
    total_btl NUMERIC DEFAULT 0.0,
    total_bl NUMERIC DEFAULT 0.0,
    refreshed_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_dashboard_summary_monthly UNIQUE (month_start, depot_id, brand_id, company_id)
);

-- 24. User Auth Logs Table
CREATE TABLE IF NOT EXISTS public.user_auth_logs (
    auth_log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.users(user_id) ON DELETE CASCADE,
    action TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed Standard System Roles (UUID role_id)
INSERT INTO public.roles (role_name, description, is_active)
VALUES
    ('Leader', 'Leadership / Management Role', true),
    ('TSM', 'Territory Sales Manager', true),
    ('ASE', 'Area Sales Executive', true),
    ('Admin', 'System Administrator', true)
ON CONFLICT (role_name) DO UPDATE SET is_active = true;

-- Aggregation Helper Stored Procedures
CREATE OR REPLACE FUNCTION refresh_dashboard_daily(p_sale_date DATE)
RETURNS VOID AS $$
BEGIN
    INSERT INTO public.dashboard_summary_daily (
        sale_date, depot_id, brand_id, company_id, headquarters_id, total_case, total_btl, total_bl, refreshed_at
    )
    SELECT 
        sf.sale_date,
        sf.depot_id,
        sf.brand_id,
        sf.company_id,
        d.headquarters_id,
        SUM(sf.total_case) as total_case,
        SUM(sf.total_btl) as total_btl,
        SUM(sf.total_bl) as total_bl,
        NOW()
    FROM public.sales_fact sf
    JOIN public.depots d ON sf.depot_id = d.depot_id
    WHERE sf.sale_date = p_sale_date AND sf.is_active = true
    GROUP BY sf.sale_date, sf.depot_id, sf.brand_id, sf.company_id, d.headquarters_id
    ON CONFLICT (sale_date, depot_id, brand_id, company_id) DO UPDATE SET
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
        month_start, financial_year_start, depot_id, brand_id, company_id, headquarters_id, total_case, total_btl, total_bl, refreshed_at
    )
    SELECT 
        v_month_start,
        v_fy_start,
        depot_id,
        brand_id,
        company_id,
        headquarters_id,
        SUM(total_case),
        SUM(total_btl),
        SUM(total_bl),
        NOW()
    FROM public.dashboard_summary_daily
    WHERE sale_date >= v_month_start AND sale_date < (v_month_start + INTERVAL '1 month')::DATE
    GROUP BY depot_id, brand_id, company_id, headquarters_id
    ON CONFLICT (month_start, depot_id, brand_id, company_id) DO UPDATE SET
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
