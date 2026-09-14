-- Migration: 019_security_rls_and_access_toggle.sql
-- Purpose: System settings table for TSM/ASE Data Access Mode toggle, security RLS policies, and RPC configuration management.

-- 1. Create System Settings Table
CREATE TABLE IF NOT EXISTS public.system_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Insert Default Setting for TSM/ASE Data Restriction Mode
INSERT INTO public.system_settings (setting_key, setting_value, description)
VALUES (
    'tsm_ase_data_restriction_enabled',
    'true',
    'When set to true, TSM and ASE users see data restricted to their assigned areas/depots. When false, TSM and ASE see full Leader view.'
)
ON CONFLICT (setting_key) DO NOTHING;

-- 3. System Settings Helper Functions
CREATE OR REPLACE FUNCTION public.get_system_setting(p_key TEXT)
RETURNS TEXT
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_val TEXT;
BEGIN
    SELECT setting_value INTO v_val
    FROM public.system_settings
    WHERE setting_key = p_key;

    RETURN COALESCE(v_val, 'true');
END;
$$;

CREATE OR REPLACE FUNCTION public.set_system_setting(p_key TEXT, p_val TEXT)
RETURNS VOID
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO public.system_settings (setting_key, setting_value, updated_at)
    VALUES (p_key, p_val, NOW())
    ON CONFLICT (setting_key) DO UPDATE
    SET setting_value = EXCLUDED.setting_value,
        updated_at = NOW();
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_system_setting(TEXT) TO authenticated, service_role, anon;
GRANT EXECUTE ON FUNCTION public.set_system_setting(TEXT, TEXT) TO authenticated, service_role;

-- 4. Enable RLS and Configure Policies for system_settings
ALTER TABLE IF EXISTS public.system_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow authenticated read on system_settings" ON public.system_settings;
CREATE POLICY "Allow authenticated read on system_settings" ON public.system_settings
    FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow admin update on system_settings" ON public.system_settings;
CREATE POLICY "Allow admin update on system_settings" ON public.system_settings
    FOR ALL USING (auth.role() = 'service_role' OR EXISTS (
        SELECT 1 FROM public.user_roles ur
        JOIN public.roles r ON ur.role_id = r.role_id
        WHERE ur.user_id = auth.uid()
          AND LOWER(r.role_name) IN ('admin', 'super_admin', 'super admin')
          AND ur.is_active = true
    ));

-- 5. Updated RLS Policies on Sales and User Data
ALTER TABLE IF EXISTS public.user_sales_fact ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow users to read assigned user sales facts" ON public.user_sales_fact;
CREATE POLICY "Allow users to read assigned user sales facts" ON public.user_sales_fact
    FOR SELECT USING (
        auth.role() = 'service_role'
        OR public.get_system_setting('tsm_ase_data_restriction_enabled') = 'false'
        OR user_id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM public.user_roles ur
            JOIN public.roles r ON ur.role_id = r.role_id
            WHERE ur.user_id = auth.uid()
              AND LOWER(r.role_name) IN ('admin', 'super_admin', 'super admin', 'leader')
              AND ur.is_active = true
        )
    );

-- 6. Trigger for updated_at on system_settings
CREATE OR REPLACE FUNCTION public.update_system_settings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_system_settings_updated_at ON public.system_settings;
CREATE TRIGGER trg_system_settings_updated_at
    BEFORE UPDATE ON public.system_settings
    FOR EACH ROW
    EXECUTE FUNCTION public.update_system_settings_updated_at();

