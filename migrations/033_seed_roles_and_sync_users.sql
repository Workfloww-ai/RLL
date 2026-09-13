-- Migration 033: Seed Canonical Roles, Sync Auth Users to Public Users, and Attach Auto-Creation Trigger
-- Target DB: test_db_RLL (kcwowusanrtvccmipjzu)

-- 0. Ensure Default Tenant Exists in public.tenant_config
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
SET is_active = true,
    updated_at = NOW();

-- 1. Seed the 4 Canonical Roles Only
-- RLL defines exactly four operational roles: Admin, Leader, TSM, and ASE.
INSERT INTO public.roles (role_id, role_name, description, is_active)
VALUES
    (gen_random_uuid(), 'Admin', 'System Administrator with full access', true),
    (gen_random_uuid(), 'Leader', 'Leadership / Executive Management Role', true),
    (gen_random_uuid(), 'TSM', 'Territory Sales Manager / Circle Supervisor', true),
    (gen_random_uuid(), 'ASE', 'Area Sales Executive / Depot Field Sales Executive', true)
ON CONFLICT (role_name) DO UPDATE
SET description = EXCLUDED.description,
    is_active = true,
    updated_at = NOW();

-- Deactivate any non-canonical legacy roles
UPDATE public.roles
SET is_active = false
WHERE role_name NOT IN ('Admin', 'Leader', 'TSM', 'ASE');

-- 2. Backfill existing auth.users into public.users
INSERT INTO public.users (user_id, tenant_id, email, first_name, last_name, phone, is_active, created_at, updated_at)
SELECT
    au.id,
    'a0000000-0000-0000-0000-000000000001'::uuid,
    LOWER(TRIM(au.email)),
    COALESCE(
        au.raw_user_meta_data->>'first_name',
        NULLIF(SPLIT_PART(COALESCE(au.raw_user_meta_data->>'full_name', au.email), ' ', 1), ''),
        SPLIT_PART(au.email, '@', 1)
    ) AS first_name,
    COALESCE(
        au.raw_user_meta_data->>'last_name',
        NULLIF(SUBSTRING(COALESCE(au.raw_user_meta_data->>'full_name', '') FROM POSITION(' ' IN COALESCE(au.raw_user_meta_data->>'full_name', '')) + 1), ''),
        ''
    ) AS last_name,
    COALESCE(au.phone, au.raw_user_meta_data->>'phone'),
    true,
    au.created_at,
    NOW()
FROM auth.users au
ON CONFLICT (user_id) DO UPDATE
SET email = EXCLUDED.email,
    first_name = EXCLUDED.first_name,
    last_name = EXCLUDED.last_name,
    phone = COALESCE(EXCLUDED.phone, public.users.phone),
    tenant_id = COALESCE(public.users.tenant_id, EXCLUDED.tenant_id),
    updated_at = NOW();

-- 3. Enhance & Attach Auto-Sync Trigger from auth.users to public.users
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  INSERT INTO public.users (user_id, tenant_id, email, first_name, last_name, phone, is_active)
  VALUES (
    NEW.id,
    'a0000000-0000-0000-0000-000000000001'::uuid,
    LOWER(TRIM(NEW.email)),
    COALESCE(
        NEW.raw_user_meta_data->>'first_name',
        NULLIF(SPLIT_PART(COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email), ' ', 1), ''),
        SPLIT_PART(NEW.email, '@', 1)
    ),
    COALESCE(
        NEW.raw_user_meta_data->>'last_name',
        NULLIF(SUBSTRING(COALESCE(NEW.raw_user_meta_data->>'full_name', '') FROM POSITION(' ' IN COALESCE(NEW.raw_user_meta_data->>'full_name', '')) + 1), ''),
        ''
    ),
    COALESCE(NEW.phone, NEW.raw_user_meta_data->>'phone'),
    true
  )
  ON CONFLICT (user_id) DO UPDATE
  SET email = EXCLUDED.email,
      updated_at = NOW();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 4. Assign Admin & Leader Roles in public.user_roles to System Administrators
WITH admin_role AS (
    SELECT role_id FROM public.roles WHERE LOWER(role_name) = 'admin' AND is_active = true LIMIT 1
)
INSERT INTO public.user_roles (user_role_id, user_id, role_id, is_active, created_at)
SELECT
    gen_random_uuid(),
    u.user_id,
    ar.role_id,
    true,
    NOW()
FROM public.users u
CROSS JOIN admin_role ar
WHERE LOWER(u.email) LIKE '%@workfloww.ai'
   OR LOWER(u.email) IN ('khwaish.gahoi@rll.com', 'suman.@rll.com', 'admin@rll.com')
ON CONFLICT (user_id, role_id) DO NOTHING;

WITH leader_role AS (
    SELECT role_id FROM public.roles WHERE LOWER(role_name) = 'leader' AND is_active = true LIMIT 1
)
INSERT INTO public.user_roles (user_role_id, user_id, role_id, is_active, created_at)
SELECT
    gen_random_uuid(),
    u.user_id,
    lr.role_id,
    true,
    NOW()
FROM public.users u
CROSS JOIN leader_role lr
WHERE LOWER(u.email) LIKE '%@workfloww.ai'
   OR LOWER(u.email) IN ('khwaish.gahoi@rll.com', 'admin@rll.com')
ON CONFLICT (user_id, role_id) DO NOTHING;

-- 5. Assign Field Roles (ASE, TSM) to Specific Role Accounts
WITH ase_role AS (
    SELECT role_id FROM public.roles WHERE LOWER(role_name) = 'ase' AND is_active = true LIMIT 1
)
INSERT INTO public.user_roles (user_role_id, user_id, role_id, is_active, created_at)
SELECT
    gen_random_uuid(),
    u.user_id,
    ar.role_id,
    true,
    NOW()
FROM public.users u
CROSS JOIN ase_role ar
WHERE LOWER(u.email) LIKE '%.ase@rll.com'
ON CONFLICT (user_id, role_id) DO NOTHING;

WITH tsm_role AS (
    SELECT role_id FROM public.roles WHERE LOWER(role_name) = 'tsm' AND is_active = true LIMIT 1
)
INSERT INTO public.user_roles (user_role_id, user_id, role_id, is_active, created_at)
SELECT
    gen_random_uuid(),
    u.user_id,
    tr.role_id,
    true,
    NOW()
FROM public.users u
CROSS JOIN tsm_role tr
WHERE LOWER(u.email) LIKE 'tsm.%@rll.com'
ON CONFLICT (user_id, role_id) DO NOTHING;
