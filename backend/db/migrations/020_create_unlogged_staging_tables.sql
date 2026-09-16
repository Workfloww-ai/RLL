-- ============================================================
-- Migration: 020_create_unlogged_staging_tables.sql
-- Phase 3: PostgreSQL UNLOGGED Zero-WAL Staging & Set-Based SQL Resolution
-- ============================================================

-- 1. Create UNLOGGED Staging Table for zero-WAL ingestion
CREATE UNLOGGED TABLE IF NOT EXISTS public.staging_raw_sales_upload (
    staging_id BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id UUID NOT NULL,
    batch_id UUID NOT NULL,
    sale_date_raw TEXT NOT NULL,
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
    total_case NUMERIC DEFAULT 0,
    total_btl NUMERIC DEFAULT 0,
    total_bl NUMERIC DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for batch-scoped queries and fast resolution joins
CREATE INDEX IF NOT EXISTS idx_staging_batch_id ON public.staging_raw_sales_upload (batch_id);

-- B-Tree Expression Indexes on Master Tables for 1-second B-Tree Index Joins
CREATE INDEX IF NOT EXISTS idx_brands_lower_name ON public.brands (LOWER(TRIM(brand_name)));
CREATE INDEX IF NOT EXISTS idx_licensees_lower_name ON public.licensees (LOWER(TRIM(licensee_name)));
CREATE INDEX IF NOT EXISTS idx_depots_lower_name ON public.depots (LOWER(TRIM(name)));
CREATE INDEX IF NOT EXISTS idx_packagings_lower_name ON public.packagings (LOWER(TRIM(packing_raw)));
CREATE INDEX IF NOT EXISTS idx_headquarters_lower_name ON public.headquarters (LOWER(TRIM(name)));

-- Helper functions for space-resilient text normalization
CREATE OR REPLACE FUNCTION public.norm_text(p_text TEXT)
RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT REGEXP_REPLACE(LOWER(TRIM(COALESCE(p_text, ''))), '\s+', ' ', 'g');
$$;

CREATE OR REPLACE FUNCTION public.norm_text_nospace(p_text TEXT)
RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT REGEXP_REPLACE(LOWER(TRIM(COALESCE(p_text, ''))), '[\s\-_.]+', '', 'g');
$$;

-- 2. Set-Based Foreign Key Resolution and Atomic Fact Insertion Procedure
CREATE OR REPLACE FUNCTION public.resolve_and_insert_sales_facts(
    p_batch_id UUID,
    p_tenant_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_total_rows INT := 0;
    v_unmapped_rows INT := 0;
    v_inserted_rows INT := 0;
    v_first_error TEXT := NULL;
BEGIN
    -- Check if staging records exist for this batch
    SELECT COUNT(*) INTO v_total_rows
    FROM public.staging_raw_sales_upload
    WHERE batch_id = p_batch_id;

    IF v_total_rows = 0 THEN
        RETURN jsonb_build_object(
            'status', 'failed',
            'error_message', 'No staging records found for batch ' || p_batch_id::text,
            'imported_rows', 0,
            'failed_rows', 0
        );
    END IF;

    -- Step 0: Auto-create missing master companies, brands, licensees, packagings, and depots
    -- 0a. Missing Companies
    INSERT INTO public.companies (company_id, company_name, is_active)
    SELECT gen_random_uuid(), s.company_raw, true
    FROM (
        SELECT DISTINCT LOWER(TRIM(company_raw)) AS comp_clean, TRIM(company_raw) AS company_raw
        FROM public.staging_raw_sales_upload
        WHERE batch_id = p_batch_id
          AND company_raw IS NOT NULL AND TRIM(company_raw) <> ''
          AND LOWER(TRIM(company_raw)) NOT IN ('others', 'other')
    ) s
    LEFT JOIN public.companies c ON LOWER(TRIM(c.company_name)) = s.comp_clean
    WHERE c.company_id IS NULL
    ON CONFLICT (company_name) DO NOTHING;

    -- 0b. Missing Brands
    INSERT INTO public.brands (brand_id, brand_name, company_id, is_active)
    SELECT DISTINCT ON (LOWER(TRIM(s.brand_name_raw)))
        gen_random_uuid(),
        TRIM(s.brand_name_raw),
        c.company_id,
        true
    FROM public.staging_raw_sales_upload s
    LEFT JOIN public.companies c ON LOWER(TRIM(c.company_name)) = LOWER(TRIM(s.company_raw))
    LEFT JOIN public.brands b ON LOWER(TRIM(b.brand_name)) = LOWER(TRIM(s.brand_name_raw))
    WHERE s.batch_id = p_batch_id
      AND s.brand_name_raw IS NOT NULL AND TRIM(s.brand_name_raw) <> ''
      AND b.brand_id IS NULL
    ON CONFLICT (brand_name) DO NOTHING;

    -- 0c. Missing Licensees
    INSERT INTO public.licensees (licensee_id, licensee_name, trade, is_active)
    SELECT DISTINCT ON (LOWER(TRIM(s.licensee_raw)))
        gen_random_uuid(),
        TRIM(s.licensee_raw),
        CASE WHEN LOWER(TRIM(s.trade_raw)) = 'on' THEN 'On' ELSE 'Off' END,
        true
    FROM public.staging_raw_sales_upload s
    LEFT JOIN public.licensees l ON LOWER(TRIM(l.licensee_name)) = LOWER(TRIM(s.licensee_raw))
    WHERE s.batch_id = p_batch_id
      AND s.licensee_raw IS NOT NULL AND TRIM(s.licensee_raw) <> ''
      AND l.licensee_id IS NULL
    ON CONFLICT (licensee_name) DO NOTHING;

    -- 0d. Missing Packagings
    INSERT INTO public.packagings (packaging_id, packing_raw, bottle_size_ml, is_active)
    SELECT DISTINCT ON (LOWER(TRIM(s.packing_raw)))
        gen_random_uuid(),
        TRIM(s.packing_raw),
        750.0,
        true
    FROM public.staging_raw_sales_upload s
    LEFT JOIN public.packagings p ON LOWER(TRIM(p.packing_raw)) = LOWER(TRIM(s.packing_raw))
    WHERE s.batch_id = p_batch_id
      AND s.packing_raw IS NOT NULL AND TRIM(s.packing_raw) <> ''
      AND p.packaging_id IS NULL
    ON CONFLICT (packing_raw) DO NOTHING;

    -- 0e. Missing Depots
    INSERT INTO public.depots (depot_id, name, is_active)
    SELECT DISTINCT ON (LOWER(TRIM(s.depot_raw)))
        gen_random_uuid(),
        TRIM(s.depot_raw),
        true
    FROM public.staging_raw_sales_upload s
    LEFT JOIN public.depots d ON LOWER(TRIM(d.name)) = LOWER(TRIM(s.depot_raw))
    WHERE s.batch_id = p_batch_id
      AND s.depot_raw IS NOT NULL AND TRIM(s.depot_raw) <> ''
      AND d.depot_id IS NULL
    ON CONFLICT (name) DO NOTHING;

    -- Step 1: Detect unmapped dimensions and insert diagnostic errors into upload_validation_errors
    -- 1a. Unmapped Depots
    INSERT INTO public.upload_validation_errors (error_id, batch_id, column_name, error_message, created_at)
    SELECT
        gen_random_uuid(),
        p_batch_id,
        'depot_raw',
        'Unmapped Depot name: ' || quote_literal(COALESCE(s.depot_raw, '')),
        NOW()
    FROM public.staging_raw_sales_upload s
    LEFT JOIN public.depots d ON LOWER(TRIM(d.name)) = LOWER(TRIM(s.depot_raw))
    WHERE s.batch_id = p_batch_id
      AND d.depot_id IS NULL
      AND s.depot_raw IS NOT NULL AND TRIM(s.depot_raw) <> '';

    -- 1b. Unmapped Licensees
    INSERT INTO public.upload_validation_errors (error_id, batch_id, column_name, error_message, created_at)
    SELECT
        gen_random_uuid(),
        p_batch_id,
        'licensee_raw',
        'Unmapped Licensee name: ' || quote_literal(COALESCE(s.licensee_raw, '')),
        NOW()
    FROM public.staging_raw_sales_upload s
    LEFT JOIN public.licensees l ON LOWER(TRIM(l.licensee_name)) = LOWER(TRIM(s.licensee_raw))
    WHERE s.batch_id = p_batch_id
      AND l.licensee_id IS NULL
      AND s.licensee_raw IS NOT NULL AND TRIM(s.licensee_raw) <> '';

    -- 1c. Unmapped Brands
    INSERT INTO public.upload_validation_errors (error_id, batch_id, column_name, error_message, created_at)
    SELECT
        gen_random_uuid(),
        p_batch_id,
        'brand_name_raw',
        'Unmapped Brand name: ' || quote_literal(COALESCE(s.brand_name_raw, '')),
        NOW()
    FROM public.staging_raw_sales_upload s
    LEFT JOIN public.brands b ON LOWER(TRIM(b.brand_name)) = LOWER(TRIM(s.brand_name_raw))
    WHERE s.batch_id = p_batch_id
      AND b.brand_id IS NULL
      AND s.brand_name_raw IS NOT NULL AND TRIM(s.brand_name_raw) <> '';

    -- 1d. Unmapped Packagings
    INSERT INTO public.upload_validation_errors (error_id, batch_id, column_name, error_message, created_at)
    SELECT
        gen_random_uuid(),
        p_batch_id,
        'packing_raw',
        'Unmapped Packaging/Size: ' || quote_literal(COALESCE(s.packing_raw, '')),
        NOW()
    FROM public.staging_raw_sales_upload s
    LEFT JOIN public.packagings p ON LOWER(TRIM(p.packing_raw)) = LOWER(TRIM(s.packing_raw))
    WHERE s.batch_id = p_batch_id
      AND p.packaging_id IS NULL
      AND s.packing_raw IS NOT NULL AND TRIM(s.packing_raw) <> '';

    -- 1e. Unmapped Headquarters
    INSERT INTO public.upload_validation_errors (error_id, batch_id, column_name, error_message, created_at)
    SELECT
        gen_random_uuid(),
        p_batch_id,
        'hq_raw',
        'Unmapped Headquarters: ' || quote_literal(COALESCE(s.hq_raw, '')),
        NOW()
    FROM public.staging_raw_sales_upload s
    LEFT JOIN public.headquarters h ON (
        LOWER(TRIM(h.name)) = LOWER(TRIM(s.hq_raw))
        OR REPLACE(LOWER(TRIM(h.name)), ' ', '') = REPLACE(LOWER(TRIM(s.hq_raw)), ' ', '')
    )
    WHERE s.batch_id = p_batch_id
      AND h.headquarters_id IS NULL
      AND s.hq_raw IS NOT NULL AND TRIM(s.hq_raw) <> '';

    -- Check if any errors were recorded
    SELECT COUNT(*), MIN(error_message) INTO v_unmapped_rows, v_first_error
    FROM public.upload_validation_errors
    WHERE batch_id = p_batch_id;

    -- Step 2: Atomic all-or-nothing rollback on validation failure
    IF v_unmapped_rows > 0 THEN
        DELETE FROM public.staging_raw_sales_upload WHERE batch_id = p_batch_id;

        RETURN jsonb_build_object(
            'status', 'failed',
            'error_message', 'Upload aborted and rolled back to 0: ' || v_unmapped_rows::text || ' rows failed data validation (' || COALESCE(v_first_error, 'Unmapped master records') || ').',
            'imported_rows', 0,
            'failed_rows', v_unmapped_rows
        );
    END IF;

    -- Step 3: Purge existing sales_fact for this specific batch_id to prevent duplication
    DELETE FROM public.sales_fact WHERE batch_id = p_batch_id;

    -- Step 4: Perform set-based resolution and atomic insert into sales_fact
    -- STRICTLY EXCLUDES company "Others" in accordance with BUSINESS_LOGIC_SPEC.md
    WITH resolved_sales AS (
        SELECT
            gen_random_uuid() AS fact_id,
            s.tenant_id,
            CASE
                WHEN s.sale_date_raw ~ '^\d{4}-\d{2}-\d{2}' THEN to_date(s.sale_date_raw, 'YYYY-MM-DD')
                WHEN s.sale_date_raw ~ '^\d{2}-\d{2}-\d{4}' THEN to_date(s.sale_date_raw, 'DD-MM-YYYY')
                WHEN s.sale_date_raw ~ '^\d{2}/\d{2}/\d{4}' THEN to_date(s.sale_date_raw, 'DD/MM/YYYY')
                WHEN s.sale_date_raw ~ '^\d{2}-\d{2}-\d{2}' THEN to_date(s.sale_date_raw, 'DD-MM-YY')
                ELSE to_date(s.sale_date_raw, 'YYYY-MM-DD')
            END AS sale_date,
            b.brand_id,
            p.packaging_id,
            d.depot_id,
            h.headquarters_id,
            ROUND(COALESCE(s.total_case, 0), 2)::NUMERIC AS total_case,
            ROUND(COALESCE(s.total_btl, 0), 2)::NUMERIC AS total_btl,
            ROUND(COALESCE(s.total_bl, 0), 2)::NUMERIC AS total_bl,
            NOW() AS created_at,
            NOW() AS updated_at
        FROM public.staging_raw_sales_upload s
        JOIN public.depots d ON LOWER(TRIM(d.name)) = LOWER(TRIM(s.depot_raw))
        JOIN public.licensees l ON LOWER(TRIM(l.licensee_name)) = LOWER(TRIM(s.licensee_raw))
        JOIN public.brands b ON LOWER(TRIM(b.brand_name)) = LOWER(TRIM(s.brand_name_raw))
        LEFT JOIN public.companies c ON b.company_id = c.company_id
        JOIN public.packagings p ON LOWER(TRIM(p.packing_raw)) = LOWER(TRIM(s.packing_raw))
        JOIN public.headquarters h ON (
            LOWER(TRIM(h.name)) = LOWER(TRIM(s.hq_raw))
            OR REPLACE(LOWER(TRIM(h.name)), ' ', '') = REPLACE(LOWER(TRIM(s.hq_raw)), ' ', '')
        )
        WHERE s.batch_id = p_batch_id
          -- STRICT OTHERS COMPANY EXCLUSION RULE
          AND LOWER(TRIM(COALESCE(s.company_raw, ''))) NOT IN ('others', 'other')
          AND (c.company_name IS NULL OR LOWER(TRIM(c.company_name)) NOT IN ('others', 'other'))
    ),
    inserted AS (
        INSERT INTO public.sales_fact (
            fact_id,
            tenant_id,
            batch_id,
            sale_date,
            licensee_id,
            brand_id,
            packaging_id,
            depot_id,
            headquarters_id,
            total_case,
            total_btl,
            total_bl,
            created_at,
            updated_at
        )
        SELECT
            fact_id,
            tenant_id,
            batch_id,
            sale_date,
            licensee_id,
            brand_id,
            packaging_id,
            depot_id,
            headquarters_id,
            total_case,
            total_btl,
            total_bl,
            created_at,
            updated_at
        FROM resolved_sales
        RETURNING 1
    )
    SELECT COUNT(*) INTO v_inserted_rows FROM inserted;

    -- Step 5: Clean up staging table immediately for this batch
    DELETE FROM public.staging_raw_sales_upload WHERE batch_id = p_batch_id;

    RETURN jsonb_build_object(
        'status', 'success',
        'error_message', NULL,
        'total_rows', v_total_rows,
        'imported_rows', v_inserted_rows,
        'failed_rows', 0
    );
END;
$$;
