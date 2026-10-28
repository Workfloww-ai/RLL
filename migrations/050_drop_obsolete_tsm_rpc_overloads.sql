-- Migration: 050_drop_obsolete_tsm_rpc_overloads.sql
-- Description: Explicitly drops the legacy 3-parameter get_mobile_tsm_sales_summary_json(DATE, DATE, DATE)
-- function overload from PostgreSQL so PostgREST schema cache only recognizes the unified 4-parameter
-- function from Migration 049 that dynamically respects the include_others toggle.

DROP FUNCTION IF EXISTS public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE);
