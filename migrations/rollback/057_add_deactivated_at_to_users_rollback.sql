-- Rollback: 057_add_deactivated_at_to_users_rollback.sql
-- Reverts deactivated_at column and restores previous versions of RPCs

ALTER TABLE IF EXISTS public.users
DROP COLUMN IF EXISTS deactivated_at;

NOTIFY pgrst, 'reload schema';

