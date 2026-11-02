-- Rollback Migration: 055_add_company_category_rollback.sql
-- Description: Drop category column and its index from companies table.

DROP INDEX IF EXISTS public.idx_companies_category;
ALTER TABLE IF EXISTS public.companies DROP COLUMN IF EXISTS category;

