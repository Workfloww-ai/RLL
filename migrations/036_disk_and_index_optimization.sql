-- Migration 036: Database Storage, FK Indexing, Duplicate Cleanup & UNLOGGED Staging
-- Targeted Database: test_db (wgpxmvrbbgpzkomdutlk)

BEGIN;

--------------------------------------------------------------------------------
-- 1. Create Indexes for 29 Unindexed Foreign Keys
--------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ase_tsm_mapping_ase_user_role_id ON public.ase_tsm_mapping(ase_user_role_id);
CREATE INDEX IF NOT EXISTS idx_ase_tsm_mapping_tsm_user_role_id ON public.ase_tsm_mapping(tsm_user_role_id);
CREATE INDEX IF NOT EXISTS idx_brands_tenant_id ON public.brands(tenant_id);
CREATE INDEX IF NOT EXISTS idx_companies_tenant_id ON public.companies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_dashboard_summary_daily_brand_id ON public.dashboard_summary_daily(brand_id);
CREATE INDEX IF NOT EXISTS idx_dashboard_summary_daily_headquarters_id ON public.dashboard_summary_daily(headquarters_id);
CREATE INDEX IF NOT EXISTS idx_depots_circle_id ON public.depots(circle_id);
CREATE INDEX IF NOT EXISTS idx_depots_tenant_id ON public.depots(tenant_id);
CREATE INDEX IF NOT EXISTS idx_headquarters_tenant_id ON public.headquarters(tenant_id);
CREATE INDEX IF NOT EXISTS idx_licensees_brand_id ON public.licensees(brand_id);
CREATE INDEX IF NOT EXISTS idx_licensees_circle_id ON public.licensees(circle_id);
CREATE INDEX IF NOT EXISTS idx_licensees_tenant_id ON public.licensees(tenant_id);
CREATE INDEX IF NOT EXISTS idx_raw_sales_upload_tenant_id ON public.raw_sales_upload(tenant_id);
CREATE INDEX IF NOT EXISTS idx_roles_created_by ON public.roles(created_by);
CREATE INDEX IF NOT EXISTS idx_roles_updated_by ON public.roles(updated_by);
CREATE INDEX IF NOT EXISTS idx_sales_daily_summary_ase_user_id ON public.sales_daily_summary(ase_user_id);
CREATE INDEX IF NOT EXISTS idx_sales_daily_summary_office_id ON public.sales_daily_summary(office_id);
CREATE INDEX IF NOT EXISTS idx_sales_monthly_summary_ase_user_id ON public.sales_monthly_summary(ase_user_id);
CREATE INDEX IF NOT EXISTS idx_sales_monthly_summary_licensee_id ON public.sales_monthly_summary(licensee_id);
CREATE INDEX IF NOT EXISTS idx_sales_monthly_summary_office_id ON public.sales_monthly_summary(office_id);
CREATE INDEX IF NOT EXISTS idx_upload_batches_created_by ON public.upload_batches(created_by);
CREATE INDEX IF NOT EXISTS idx_upload_batches_tenant_id ON public.upload_batches(tenant_id);
CREATE INDEX IF NOT EXISTS idx_upload_batches_updated_by ON public.upload_batches(updated_by);
CREATE INDEX IF NOT EXISTS idx_upload_batches_uploaded_by ON public.upload_batches(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_upload_pipeline_logs_batch_id ON public.upload_pipeline_logs(batch_id);
CREATE INDEX IF NOT EXISTS idx_upload_validation_errors_raw_id ON public.upload_validation_errors(raw_id);
CREATE INDEX IF NOT EXISTS idx_user_auth_logs_user_id ON public.user_auth_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sales_fact_brand_id ON public.user_sales_fact(brand_id);
CREATE INDEX IF NOT EXISTS idx_user_sales_fact_tenant_id ON public.user_sales_fact(tenant_id);

--------------------------------------------------------------------------------
-- 2. Drop 5 Duplicate Expression Indexes
--------------------------------------------------------------------------------
DROP INDEX IF EXISTS public.idx_brands_lower_name;
DROP INDEX IF EXISTS public.idx_depots_lower_name;
DROP INDEX IF EXISTS public.idx_headquarters_lower_name;
DROP INDEX IF EXISTS public.idx_licensees_lower_name;
DROP INDEX IF EXISTS public.idx_packagings_lower_name;

--------------------------------------------------------------------------------
-- 3. Set Staging Tables to UNLOGGED (Reclaims WAL log writes during bulk upload)
--------------------------------------------------------------------------------
ALTER TABLE IF EXISTS public.upload_validation_errors SET UNLOGGED;
ALTER TABLE IF EXISTS public.raw_sales_upload SET UNLOGGED;

COMMIT;
