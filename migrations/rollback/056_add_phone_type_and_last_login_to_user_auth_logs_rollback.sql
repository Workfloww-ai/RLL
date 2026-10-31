-- Rollback Migration: 056_add_phone_type_and_last_login_to_user_auth_logs_rollback.sql
-- Description: Drops user_auth view, added indexes, and added columns from user_auth_logs.

DROP VIEW IF EXISTS public.user_auth;
DROP INDEX IF EXISTS public.idx_user_auth_logs_last_login;
DROP INDEX IF EXISTS public.idx_user_auth_logs_phone_type;
DROP INDEX IF EXISTS public.idx_user_auth_logs_user_id_unique;

ALTER TABLE IF EXISTS public.user_auth_logs
DROP COLUMN IF EXISTS phone_type,
DROP COLUMN IF EXISTS last_login,
DROP COLUMN IF EXISTS email,
DROP COLUMN IF EXISTS status;
