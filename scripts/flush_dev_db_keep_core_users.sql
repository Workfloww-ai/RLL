-- ==============================================================================
-- Complete Data Wipe / Reset Script for dev_db_RLL (wgpxmvrbbgpzkomdutlk)
--
-- TARGET: dev_db_RLL (wgpxmvrbbgpzkomdutlk)
-- (NEVER run on live_db kcwowusanrtvccmipjzu!)
--
-- KEEPS DATA IN EXACTLY 6 CORE TABLES:
--   1. public.users
--   2. public.user_roles
--   3. public.roles
--   4. public.tenant_config
--   5. public.ase_tsm_mapping
--   6. public.system_settings
--
-- WIPES ALL OTHER TABLES (Sales facts, daily/monthly summaries, batches,
-- logs, and master data entities like brands, depots, licensees, etc.)
-- ==============================================================================

TRUNCATE TABLE 
  -- 1. Transactional Sales Facts & Staging
  public.sales_fact,
  public.user_sales_fact,
  public.raw_sales_upload,
  
  -- 2. Pre-aggregated Sales Summaries
  public.sales_daily_summary,
  public.sales_monthly_summary,
  
  -- 3. Ingestion Batches, Chunks & Pipeline Logs
  public.upload_batches,
  public.batch_chunks,
  public.upload_pipeline_logs,
  public.upload_validation_errors,
  public.error_logs,
  
  -- 4. Auth & System Logs
  public.user_auth_logs,
  public.chatbot_query_logs,
  public.chatbot_popular_queries,
  public.otp_codes,
  public.system_settings_audit_log,
  
  -- 5. Secondary User Mappings
  public.user_depot,
  public.user_headquarters_mapping,
  
  -- 6. Master Data Entities
  public.licensees,
  public.groups,
  public.brands,
  public.company_aliases,
  public.companies,
  public.depots,
  public.offices,
  public.headquarters,
  public.circles,
  public.packagings
CASCADE;

-- Optional cleanup for legacy tables if they still exist
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'dashboard_summary_daily' AND table_schema = 'public') THEN
        EXECUTE 'TRUNCATE TABLE public.dashboard_summary_daily CASCADE;';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tenants' AND table_schema = 'public') THEN
        EXECUTE 'TRUNCATE TABLE public.tenants CASCADE;';
    END IF;
END $$;
