-- ==============================================================================
-- Migration 043: Cleanup Redundancies, Duplicate Tables & Obsolete Indexes
-- Database: dev_db_RLL (wgpxmvrbbgpzkomdutlk)
-- Target: Zero-risk cleanup of duplicate tables, dead columns, and unused indexes
-- ==============================================================================

-- 1. Drop duplicate index on public.users
DROP INDEX IF EXISTS public.idx_users_tenant_id;

-- 2. Drop dead indexes on 100% NULL or obsolete columns
DROP INDEX IF EXISTS public.idx_licensees_brand_id;
DROP INDEX IF EXISTS public.idx_licensees_circle_id;
DROP INDEX IF EXISTS public.idx_depots_circle_id;
DROP INDEX IF EXISTS public.idx_ase_tsm_mapping_ase_user_role_id;
DROP INDEX IF EXISTS public.idx_ase_tsm_mapping_tsm_user_role_id;
DROP INDEX IF EXISTS public.idx_ase_tsm_mapping_ase_name;
DROP INDEX IF EXISTS public.idx_dashboard_summary_daily_brand_id;

-- 3. Drop verified dead columns from public.ase_tsm_mapping
ALTER TABLE public.ase_tsm_mapping 
  DROP COLUMN IF EXISTS tsm_user_role_id,
  DROP COLUMN IF EXISTS ase_user_role_id,
  DROP COLUMN IF EXISTS ase_name;

-- 4. Drop verified dead columns from public.licensees
ALTER TABLE public.licensees 
  DROP COLUMN IF EXISTS brand_id,
  DROP COLUMN IF EXISTS total_cases,
  DROP COLUMN IF EXISTS total_bottles;

-- 5. Drop redundant duplicate table: public.tenants
-- Drop foreign keys referencing public.tenants (both tables already point to public.tenant_config)
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS fk_users_tenant;
ALTER TABLE public.upload_batches DROP CONSTRAINT IF EXISTS fk_upload_batches_tenant;
DROP TABLE IF EXISTS public.tenants CASCADE;

-- 6. Drop obsolete stored procedures (RPCs)
DROP FUNCTION IF EXISTS public.refresh_dashboard_daily();
DROP FUNCTION IF EXISTS public.refresh_dashboard_monthly();
DROP FUNCTION IF EXISTS public.refresh_sales_analytics();
DROP FUNCTION IF EXISTS public.refresh_incremental_sales_analytics(DATE);

-- 7. Drop obsolete prototype table (fully decoupled from codebase in Phase 2)
DROP TABLE IF EXISTS public.dashboard_summary_daily CASCADE;

-- 8. Drop duplicate batch tracking columns from public.upload_batches
ALTER TABLE public.upload_batches 
  DROP COLUMN IF EXISTS file_name,
  DROP COLUMN IF EXISTS total_rows,
  DROP COLUMN IF EXISTS upload_status,
  DROP COLUMN IF EXISTS created_by;
