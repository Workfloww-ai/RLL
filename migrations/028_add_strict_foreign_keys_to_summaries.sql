-- Migration: 028_add_strict_foreign_keys_to_summaries.sql
-- Purpose: Enforce complete, explicit database-level Foreign Key constraints across
-- sales_daily_summary, sales_monthly_summary, sales_fact, user_sales_fact, and offices tables on test_db_RLL.

-- 1. All Foreign Keys on sales_daily_summary
ALTER TABLE IF EXISTS public.sales_daily_summary
  ADD CONSTRAINT fk_sds_headquarters FOREIGN KEY (headquarters_id) REFERENCES public.headquarters(headquarters_id) ON DELETE SET NULL,
  ADD CONSTRAINT fk_sds_depot FOREIGN KEY (depot_id) REFERENCES public.depots(depot_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_sds_company FOREIGN KEY (company_id) REFERENCES public.companies(company_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_sds_brand FOREIGN KEY (brand_id) REFERENCES public.brands(brand_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_sds_group FOREIGN KEY (group_id) REFERENCES public.groups(group_id) ON DELETE SET NULL,
  ADD CONSTRAINT fk_sds_licensee FOREIGN KEY (licensee_id) REFERENCES public.licensees(licensee_id) ON DELETE SET NULL,
  ADD CONSTRAINT fk_sds_tsm_user FOREIGN KEY (tsm_user_id) REFERENCES public.users(user_id) ON DELETE SET NULL,
  ADD CONSTRAINT fk_sds_ase_user FOREIGN KEY (ase_user_id) REFERENCES public.users(user_id) ON DELETE SET NULL;

-- 2. All Foreign Keys on sales_monthly_summary
ALTER TABLE IF EXISTS public.sales_monthly_summary
  ADD CONSTRAINT fk_sms_headquarters FOREIGN KEY (headquarters_id) REFERENCES public.headquarters(headquarters_id) ON DELETE SET NULL,
  ADD CONSTRAINT fk_sms_depot FOREIGN KEY (depot_id) REFERENCES public.depots(depot_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_sms_company FOREIGN KEY (company_id) REFERENCES public.companies(company_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_sms_brand FOREIGN KEY (brand_id) REFERENCES public.brands(brand_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_sms_group FOREIGN KEY (group_id) REFERENCES public.groups(group_id) ON DELETE SET NULL,
  ADD CONSTRAINT fk_sms_licensee FOREIGN KEY (licensee_id) REFERENCES public.licensees(licensee_id) ON DELETE SET NULL,
  ADD CONSTRAINT fk_sms_tsm_user FOREIGN KEY (tsm_user_id) REFERENCES public.users(user_id) ON DELETE SET NULL,
  ADD CONSTRAINT fk_sms_ase_user FOREIGN KEY (ase_user_id) REFERENCES public.users(user_id) ON DELETE SET NULL;

-- 3. All Foreign Keys on sales_fact
ALTER TABLE IF EXISTS public.sales_fact
  ADD CONSTRAINT fk_sf_licensee FOREIGN KEY (licensee_id) REFERENCES public.licensees(licensee_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_sf_brand FOREIGN KEY (brand_id) REFERENCES public.brands(brand_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_sf_packaging FOREIGN KEY (packaging_id) REFERENCES public.packagings(packaging_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_sf_depot FOREIGN KEY (depot_id) REFERENCES public.depots(depot_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_sf_batch FOREIGN KEY (batch_id) REFERENCES public.upload_batches(batch_id) ON DELETE CASCADE;

-- 4. All Foreign Keys on user_sales_fact
ALTER TABLE IF EXISTS public.user_sales_fact
  ADD CONSTRAINT fk_usf_user FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_usf_company FOREIGN KEY (company_id) REFERENCES public.companies(company_id) ON DELETE CASCADE,
  ADD CONSTRAINT fk_usf_brand FOREIGN KEY (brand_id) REFERENCES public.brands(brand_id) ON DELETE CASCADE;

-- 5. Foreign Key on offices
ALTER TABLE IF EXISTS public.offices
  ADD CONSTRAINT fk_offices_headquarters FOREIGN KEY (headquarters_id) REFERENCES public.headquarters(headquarters_id) ON DELETE SET NULL;
