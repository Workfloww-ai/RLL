-- Migration: 019_tenant_config.sql
-- Purpose: Create multi-tenant white-label configuration table and retrieval stored procedure.

-- 1. Create tenant_config table
CREATE TABLE IF NOT EXISTS public.tenant_config (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_slug TEXT UNIQUE NOT NULL,
    app_name TEXT NOT NULL DEFAULT 'LucidX360',
    logo_url TEXT,
    favicon_url TEXT,
    splash_screen_url TEXT,
    pinned_company_name TEXT,
    excluded_companies TEXT[] DEFAULT ARRAY['Others'],
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Index on tenant_slug for sub-millisecond retrieval
CREATE INDEX IF NOT EXISTS idx_tenant_config_slug 
ON public.tenant_config (tenant_slug) 
WHERE is_active = true;

-- 3. Seed default tenant row (Rajasthan Liquor Limited default tenant)
INSERT INTO public.tenant_config (
    tenant_slug,
    app_name,
    logo_url,
    favicon_url,
    splash_screen_url,
    pinned_company_name,
    excluded_companies
) VALUES (
    'rll',
    'LucidX360',
    NULL, -- Will fall back to client local crest asset if null
    NULL,
    NULL,
    'Rajasthan Liquor Limited',
    ARRAY['Others']
) ON CONFLICT (tenant_slug) DO NOTHING;

-- 4. Stored Procedure: get_tenant_config
CREATE OR REPLACE FUNCTION public.get_tenant_config(p_tenant_slug TEXT DEFAULT 'rll')
RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT row_to_json(tc)::jsonb INTO v_result
    FROM (
        SELECT
            tenant_id,
            tenant_slug,
            app_name,
            COALESCE(logo_url, '')          AS logo_url,
            COALESCE(favicon_url, '')       AS favicon_url,
            COALESCE(splash_screen_url, '') AS splash_screen_url,
            COALESCE(pinned_company_name, '') AS pinned_company_name,
            excluded_companies,
            is_active
        FROM public.tenant_config
        WHERE (p_tenant_slug IS NULL OR LOWER(TRIM(tenant_slug)) = LOWER(TRIM(p_tenant_slug)))
          AND is_active = true
        ORDER BY created_at ASC
        LIMIT 1
    ) tc;

    RETURN COALESCE(v_result, jsonb_build_object(
        'tenant_slug', 'rll',
        'app_name', 'LucidX360',
        'logo_url', '',
        'favicon_url', '',
        'splash_screen_url', '',
        'pinned_company_name', '',
        'excluded_companies', ARRAY['Others']
    ));
END;
$$;

GRANT SELECT ON public.tenant_config TO authenticated, service_role, anon;
GRANT EXECUTE ON FUNCTION public.get_tenant_config(TEXT) TO authenticated, service_role, anon;
