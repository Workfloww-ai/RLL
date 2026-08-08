-- Migration 002: Change role & hierarchy IDs to UUID and seed roles

-- Enable pgcrypto extension if not enabled
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. Modify roles table
ALTER TABLE public.roles ALTER COLUMN role_id DROP DEFAULT;
ALTER TABLE public.roles ALTER COLUMN role_id TYPE uuid USING gen_random_uuid();
ALTER TABLE public.roles ALTER COLUMN role_id SET DEFAULT gen_random_uuid();

-- 2. Modify user_roles table
ALTER TABLE public.user_roles ALTER COLUMN user_role_id DROP DEFAULT;
ALTER TABLE public.user_roles ALTER COLUMN user_role_id TYPE uuid USING gen_random_uuid();
ALTER TABLE public.user_roles ALTER COLUMN user_role_id SET DEFAULT gen_random_uuid();

ALTER TABLE public.user_roles ALTER COLUMN role_id TYPE uuid USING gen_random_uuid();

-- 3. Modify ase_tsm_mapping table
ALTER TABLE public.ase_tsm_mapping ALTER COLUMN hierarchy_id DROP DEFAULT;
ALTER TABLE public.ase_tsm_mapping ALTER COLUMN hierarchy_id TYPE uuid USING gen_random_uuid();
ALTER TABLE public.ase_tsm_mapping ALTER COLUMN hierarchy_id SET DEFAULT gen_random_uuid();

ALTER TABLE public.ase_tsm_mapping ALTER COLUMN tsm_user_role_id TYPE uuid USING gen_random_uuid();
ALTER TABLE public.ase_tsm_mapping ALTER COLUMN ase_user_role_id TYPE uuid USING gen_random_uuid();

-- 4. Seed standard roles (Leader, TSM, ASE, Admin)
INSERT INTO public.roles (role_id, role_name, description, is_active)
VALUES
    (gen_random_uuid(), 'Leader', 'Leadership / Management Role', true),
    (gen_random_uuid(), 'TSM', 'Territory Sales Manager', true),
    (gen_random_uuid(), 'ASE', 'Area Sales Executive', true),
    (gen_random_uuid(), 'Admin', 'System Administrator', true)
ON CONFLICT (role_name) DO NOTHING;
