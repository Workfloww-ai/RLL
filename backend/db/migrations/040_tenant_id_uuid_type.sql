-- ============================================================================
-- Migration 040: Standardize tenant_id to PostgreSQL UUID Data Type
-- Target DB: Execute on test_db (wgpxmvrbbgpzkomdutlk) first for verification.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Ensure tenants master table exists with UUID primary key
CREATE TABLE IF NOT EXISTS public.tenants (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_slug VARCHAR(64) UNIQUE NOT NULL,
    app_name VARCHAR(128) NOT NULL,
    logo_url TEXT,
    favicon_url TEXT,
    splash_screen_url TEXT,
    pinned_company_name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed default canonical tenant UUID if missing
INSERT INTO public.tenants (tenant_id, tenant_slug, app_name, pinned_company_name)
VALUES ('a0000000-0000-0000-0000-000000000001'::uuid, 'rll', 'LucidX360', 'Rajasthan Liquor Limited')
ON CONFLICT (tenant_id) DO NOTHING;

-- 2. Convert string/varchar tenant_id columns to native PostgreSQL UUID type
DO $$
BEGIN
    -- users table
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='tenant_id' AND data_type!='uuid') THEN
        ALTER TABLE public.users ALTER COLUMN tenant_id TYPE UUID USING tenant_id::uuid;
    END IF;

    -- upload_batches table
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='upload_batches' AND column_name='tenant_id' AND data_type!='uuid') THEN
        ALTER TABLE public.upload_batches ALTER COLUMN tenant_id TYPE UUID USING tenant_id::uuid;
    END IF;

    -- companies table
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='tenant_id' AND data_type!='uuid') THEN
        ALTER TABLE public.companies ALTER COLUMN tenant_id TYPE UUID USING tenant_id::uuid;
    END IF;

    -- brands table
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='brands' AND column_name='tenant_id' AND data_type!='uuid') THEN
        ALTER TABLE public.brands ALTER COLUMN tenant_id TYPE UUID USING tenant_id::uuid;
    END IF;

    -- depots table
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='depots' AND column_name='tenant_id' AND data_type!='uuid') THEN
        ALTER TABLE public.depots ALTER COLUMN tenant_id TYPE UUID USING tenant_id::uuid;
    END IF;

    -- headquarters table
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='headquarters' AND column_name='tenant_id' AND data_type!='uuid') THEN
        ALTER TABLE public.headquarters ALTER COLUMN tenant_id TYPE UUID USING tenant_id::uuid;
    END IF;

    -- licensees table
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='licensees' AND column_name='tenant_id' AND data_type!='uuid') THEN
        ALTER TABLE public.licensees ALTER COLUMN tenant_id TYPE UUID USING tenant_id::uuid;
    END IF;

    -- raw_sales_upload table
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='raw_sales_upload' AND column_name='tenant_id' AND data_type!='uuid') THEN
        ALTER TABLE public.raw_sales_upload ALTER COLUMN tenant_id TYPE UUID USING tenant_id::uuid;
    END IF;

    -- user_sales_fact table
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='user_sales_fact' AND column_name='tenant_id' AND data_type!='uuid') THEN
        ALTER TABLE public.user_sales_fact ALTER COLUMN tenant_id TYPE UUID USING tenant_id::uuid;
    END IF;
END $$;

-- 3. Add Foreign Key constraints if not present
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='fk_users_tenant') THEN
        ALTER TABLE public.users ADD CONSTRAINT fk_users_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='fk_upload_batches_tenant') THEN
        ALTER TABLE public.upload_batches ADD CONSTRAINT fk_upload_batches_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;
    END IF;
END $$;

-- 4. Ensure UUID Indexes
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON public.users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_upload_batches_tenant_id ON public.upload_batches(tenant_id);
CREATE INDEX IF NOT EXISTS idx_companies_tenant_id ON public.companies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_brands_tenant_id ON public.brands(tenant_id);
CREATE INDEX IF NOT EXISTS idx_depots_tenant_id ON public.depots(tenant_id);
CREATE INDEX IF NOT EXISTS idx_headquarters_tenant_id ON public.headquarters(tenant_id);
CREATE INDEX IF NOT EXISTS idx_licensees_tenant_id ON public.licensees(tenant_id);
