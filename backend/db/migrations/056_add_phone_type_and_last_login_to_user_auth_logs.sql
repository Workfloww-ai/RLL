-- Migration: 056_add_phone_type_and_last_login_to_user_auth_logs.sql
-- Description: Adds phone_type, last_login, email, and status columns to user_auth_logs.
-- Creates user_auth alias view and vacuums/clears prior records.
-- Target DB: test_db (wgpxmvrbbgpzkomdutlk)

-- 1. Add columns to public.user_auth_logs
ALTER TABLE IF EXISTS public.user_auth_logs
ADD COLUMN IF NOT EXISTS phone_type TEXT,
ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS email TEXT,
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'SUCCESS';

-- 2. Create index on last_login and phone_type
CREATE INDEX IF NOT EXISTS idx_user_auth_logs_last_login ON public.user_auth_logs(last_login DESC);
CREATE INDEX IF NOT EXISTS idx_user_auth_logs_phone_type ON public.user_auth_logs(phone_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_auth_logs_user_id_unique ON public.user_auth_logs(user_id);

-- 3. Create public.user_auth view as a convenient synonym for user_auth_logs
CREATE OR REPLACE VIEW public.user_auth AS
SELECT
    auth_log_id,
    user_id,
    email,
    phone_type,
    last_login,
    action,
    status,
    ip_address,
    user_agent,
    created_at
FROM public.user_auth_logs;

-- Grant permissions on view
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_auth TO authenticated, service_role, anon;

-- 4. Vacuum/clear all existing records from user_auth_logs
DELETE FROM public.user_auth_logs;
