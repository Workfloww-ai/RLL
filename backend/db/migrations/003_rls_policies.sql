-- Migration 003: Row Level Security (RLS) Policies Setup

-- 1. Enable RLS on all Public Schema Tables
ALTER TABLE IF EXISTS public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.ase_tsm_mapping ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.offices ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.headquarters ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.circles ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.depots ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.user_depot ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.licensees ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.brands ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.packagings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.upload_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.batch_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.raw_sales_upload ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.upload_pipeline_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.upload_validation_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.sales_fact ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.dashboard_summary_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.dashboard_summary_monthly ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.user_auth_logs ENABLE ROW LEVEL SECURITY;

-- 2. Master Data Read Policies (Allow Authenticated & Service Roles to Read Master Reference Tables)
DROP POLICY IF EXISTS "Allow authenticated read on master tables" ON public.companies;
CREATE POLICY "Allow authenticated read on master tables" ON public.companies FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow authenticated read on master tables" ON public.brands;
CREATE POLICY "Allow authenticated read on master tables" ON public.brands FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow authenticated read on master tables" ON public.packagings;
CREATE POLICY "Allow authenticated read on master tables" ON public.packagings FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow authenticated read on master tables" ON public.depots;
CREATE POLICY "Allow authenticated read on master tables" ON public.depots FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow authenticated read on master tables" ON public.offices;
CREATE POLICY "Allow authenticated read on master tables" ON public.offices FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow authenticated read on master tables" ON public.headquarters;
CREATE POLICY "Allow authenticated read on master tables" ON public.headquarters FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow authenticated read on master tables" ON public.circles;
CREATE POLICY "Allow authenticated read on master tables" ON public.circles FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow authenticated read on master tables" ON public.roles;
CREATE POLICY "Allow authenticated read on master tables" ON public.roles FOR SELECT USING (true);

-- 3. User & Auth Policies
DROP POLICY IF EXISTS "Allow users to read own profile" ON public.users;
CREATE POLICY "Allow users to read own profile" ON public.users FOR SELECT USING (auth.uid() = user_id OR auth.role() = 'service_role');

-- 4. Transactional & Dashboard Summary Policies
DROP POLICY IF EXISTS "Allow authenticated access to daily sales summaries" ON public.dashboard_summary_daily;
CREATE POLICY "Allow authenticated access to daily sales summaries" ON public.dashboard_summary_daily FOR ALL USING (true);

DROP POLICY IF EXISTS "Allow authenticated access to monthly sales summaries" ON public.dashboard_summary_monthly;
CREATE POLICY "Allow authenticated access to monthly sales summaries" ON public.dashboard_summary_monthly FOR ALL USING (true);

DROP POLICY IF EXISTS "Allow authenticated access to sales facts" ON public.sales_fact;
CREATE POLICY "Allow authenticated access to sales facts" ON public.sales_fact FOR ALL USING (true);

DROP POLICY IF EXISTS "Allow authenticated access to upload batches" ON public.upload_batches;
CREATE POLICY "Allow authenticated access to upload batches" ON public.upload_batches FOR ALL USING (true);
