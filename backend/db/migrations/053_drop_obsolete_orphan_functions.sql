-- ==============================================================================
-- Migration: 053_drop_obsolete_orphan_functions.sql
-- Description: Drops 14 obsolete, abandoned, and dead utility stored procedures
-- and their 12 unused dependent expression indexes.
--
-- Target Database: test_db (wgpxmvrbbgpzkomdutlk)
-- ==============================================================================

BEGIN;

-- 1. Drop 12 Unused Dependent Expression Indexes created from norm_text / norm_text_nospace
DROP INDEX IF EXISTS public.idx_brands_norm_name;
DROP INDEX IF EXISTS public.idx_brands_nospace_name;
DROP INDEX IF EXISTS public.idx_companies_norm_name;
DROP INDEX IF EXISTS public.idx_companies_nospace_name;
DROP INDEX IF EXISTS public.idx_depots_norm_name;
DROP INDEX IF EXISTS public.idx_depots_nospace_name;
DROP INDEX IF EXISTS public.idx_headquarters_norm_name;
DROP INDEX IF EXISTS public.idx_headquarters_nospace_name;
DROP INDEX IF EXISTS public.idx_licensees_norm_name;
DROP INDEX IF EXISTS public.idx_licensees_nospace_name;
DROP INDEX IF EXISTS public.idx_packagings_norm_raw;
DROP INDEX IF EXISTS public.idx_packagings_nospace_raw;

-- 2. Drop Legacy Text Normalization & Security Utility Helpers (9 Functions)
DROP FUNCTION IF EXISTS public.norm_text(text) CASCADE;
DROP FUNCTION IF EXISTS public.norm_text() CASCADE;
DROP FUNCTION IF EXISTS public.norm_text_nospace(text) CASCADE;
DROP FUNCTION IF EXISTS public.norm_text_nospace() CASCADE;
DROP FUNCTION IF EXISTS public.is_admin();
DROP FUNCTION IF EXISTS public.get_subordinate_user_ids();
DROP FUNCTION IF EXISTS public.get_user_depot_ids();
DROP FUNCTION IF EXISTS public.get_affected_depots_for_month(date);
DROP FUNCTION IF EXISTS public.get_affected_depots_for_month();
DROP FUNCTION IF EXISTS public.get_reconciliation_audit_json(text, date);
DROP FUNCTION IF EXISTS public.get_reconciliation_audit_json(date, text);
DROP FUNCTION IF EXISTS public.get_reconciliation_audit_json();
DROP FUNCTION IF EXISTS public.populate_dim_calendar_fy();
DROP FUNCTION IF EXISTS public.rls_auto_enable();

-- 3. Drop Abandoned Partitioning Procedures (2 Functions)
DROP FUNCTION IF EXISTS public.create_sales_fact_partition(integer, integer);
DROP FUNCTION IF EXISTS public.create_sales_fact_partition();
DROP FUNCTION IF EXISTS public.ensure_sales_fact_partition(date);
DROP FUNCTION IF EXISTS public.ensure_sales_fact_partition();

-- 4. Drop Legacy Ingestion Procedures & Dangerous Leftover (3 Functions)
DROP FUNCTION IF EXISTS public.resolve_and_insert_sales_facts(uuid, uuid);
DROP FUNCTION IF EXISTS public.resolve_and_insert_sales_facts(uuid);
DROP FUNCTION IF EXISTS public.resolve_and_insert_sales_facts();
DROP FUNCTION IF EXISTS public.sync_user_sales_fact_from_raw();
DROP FUNCTION IF EXISTS public.clear_all_data(boolean);
DROP FUNCTION IF EXISTS public.clear_all_data();

-- 5. Reload PostgREST schema cache
NOTIFY pgrst, 'reload schema';

COMMIT;
