-- Migration: 055_add_company_category.sql
-- Description: Add category column to companies table for distinguishing 'RLL' vs 'Others' portfolio companies.
-- Target DB: test_db (wgpxmvrbbgpzkomdutlk) -> staging verification -> live_db upon explicit confirmation.

-- 1. Add category column if not exists
ALTER TABLE IF EXISTS public.companies 
ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'Others';

-- 2. Create covering index on category
CREATE INDEX IF NOT EXISTS idx_companies_category 
ON public.companies(category);

