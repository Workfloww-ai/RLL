-- Migration: 021_tenant_config.sql
-- Purpose: Create multi-tenant white-label configuration table, seed canonical tenant with stable UUID, and retrieval stored procedure.

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

-- 2. Index on tenant_slug and tenant_id for sub-millisecond retrieval
CREATE INDEX IF NOT EXISTS idx_tenant_config_slug 
ON public.tenant_config (tenant_slug) 
WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_tenant_config_id 
ON public.tenant_config (tenant_id) 
WHERE is_active = true;

-- 3. Seed canonical tenant row with stable UUID
INSERT INTO public.tenant_config (
    tenant_id,
    tenant_slug,
    app_name,
    logo_url,
    favicon_url,
    splash_screen_url,
    pinned_company_name,
    excluded_companies,
    is_active
) VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'rll',
    'LucidX360',
    '/images/rll logo.svg',
    NULL,
    NULL,
    'Rajasthan Liquor Limited',
    ARRAY['Others'],
    true
) ON CONFLICT (tenant_slug) DO UPDATE
SET app_name = EXCLUDED.app_name,
    logo_url = COALESCE(EXCLUDED.logo_url, public.tenant_config.logo_url),
    pinned_company_name = EXCLUDED.pinned_company_name,
    excluded_companies = EXCLUDED.excluded_companies,
    is_active = true,
    updated_at = NOW();

-- 4. Stored Procedure: get_tenant_config
DROP FUNCTION IF EXISTS public.get_tenant_config(TEXT);
CREATE OR REPLACE FUNCTION public.get_tenant_config(
    p_tenant_slug TEXT DEFAULT NULL,
    p_tenant_id UUID DEFAULT NULL
)
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
        WHERE (p_tenant_id IS NOT NULL AND tenant_id = p_tenant_id)
           OR (p_tenant_id IS NULL AND p_tenant_slug IS NOT NULL AND LOWER(TRIM(tenant_slug)) = LOWER(TRIM(p_tenant_slug)))
           OR (p_tenant_id IS NULL AND p_tenant_slug IS NULL AND is_active = true)
        ORDER BY 
            CASE WHEN p_tenant_id IS NOT NULL AND tenant_id = p_tenant_id THEN 0
                 WHEN p_tenant_slug IS NOT NULL AND LOWER(TRIM(tenant_slug)) = LOWER(TRIM(p_tenant_slug)) THEN 1
                 ELSE 2 END,
            created_at ASC
        LIMIT 1
    ) tc;

    RETURN COALESCE(v_result, jsonb_build_object(
        'tenant_id', 'a0000000-0000-0000-0000-000000000001'::uuid,
        'tenant_slug', 'rll',
        'app_name', 'LucidX360',
        'logo_url', '/images/rll logo.svg',
        'favicon_url', '',
        'splash_screen_url', '',
        'pinned_company_name', 'Rajasthan Liquor Limited',
        'excluded_companies', ARRAY['Others']
    ));
END;
$$;

GRANT SELECT ON public.tenant_config TO authenticated, service_role, anon;
GRANT EXECUTE ON FUNCTION public.get_tenant_config(TEXT, UUID) TO authenticated, service_role, anon;
