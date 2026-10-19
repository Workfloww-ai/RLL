-- ==============================================================================
-- Rollback Migration 043: Restore Redundant Columns and Indexes if needed
-- Database: dev_db_RLL (wgpxmvrbbgpzkomdutlk)
-- ==============================================================================

-- 1. Restore upload_batches columns
ALTER TABLE public.upload_batches 
  ADD COLUMN IF NOT EXISTS file_name TEXT,
  ADD COLUMN IF NOT EXISTS total_rows INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS upload_status VARCHAR(50) DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS created_by UUID;

-- 2. Restore duplicate index on public.users
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON public.users(tenant_id);

-- 3. Restore ase_tsm_mapping columns
ALTER TABLE public.ase_tsm_mapping 
  ADD COLUMN IF NOT EXISTS tsm_user_role_id INTEGER,
  ADD COLUMN IF NOT EXISTS ase_user_role_id INTEGER,
  ADD COLUMN IF NOT EXISTS ase_name VARCHAR(255);

-- 4. Restore licensees columns
ALTER TABLE public.licensees 
  ADD COLUMN IF NOT EXISTS brand_id BIGINT,
  ADD COLUMN IF NOT EXISTS total_cases NUMERIC(12, 2) DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS total_bottles NUMERIC(12, 2) DEFAULT 0.0;
