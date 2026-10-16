-- Migration: 041_add_chatbot_enabled_system_setting.sql
-- Purpose: Seed default 'chatbot_enabled' setting in public.system_settings and create helper getter function.

INSERT INTO public.system_settings (setting_key, setting_value, description)
VALUES (
    'chatbot_enabled',
    'true',
    'When true, the Sales AI Chatbot assistant is enabled and visible across mobile and web platforms. When false, the chatbot is disabled.'
)
ON CONFLICT (setting_key) DO UPDATE
SET description = EXCLUDED.description,
    updated_at = NOW();

-- Central PostgreSQL Helper Function for Chatbot Feature Gate
CREATE OR REPLACE FUNCTION public.get_chatbot_enabled()
RETURNS boolean
LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_val TEXT;
BEGIN
    SELECT setting_value INTO v_val
    FROM public.system_settings
    WHERE setting_key = 'chatbot_enabled';

    RETURN COALESCE(LOWER(TRIM(v_val)) = 'true', true);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_chatbot_enabled() TO authenticated, service_role, anon;
