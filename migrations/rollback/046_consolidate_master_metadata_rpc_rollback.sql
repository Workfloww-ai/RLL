-- Rollback: 046_consolidate_master_metadata_rpc_rollback.sql
DROP FUNCTION IF EXISTS public.get_master_metadata_bundle();
DROP FUNCTION IF EXISTS public.get_latest_sale_date();
