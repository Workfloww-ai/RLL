-- Migration: 042_add_user_headquarters_mapping.sql
-- Purpose: Unified employee-to-headquarters assignment bridge table (Option B)
--          Supporting many-to-many (M:N) headquarters assignments for TSMs, ASEs, and all user roles.
-- Target DB: test_db (wgpxmvrbbgpzkomdutlk) -> staging verification -> live_db upon approval
-- Audit: Corrects RLS policies, tightens PostgreSQL role grants, and adds DB-level tenant-integrity triggers.

-- 1. Create user_headquarters_mapping table
CREATE TABLE IF NOT EXISTS public.user_headquarters_mapping (
    mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenant_config(tenant_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    headquarters_id UUID NOT NULL REFERENCES public.headquarters(headquarters_id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    updated_by UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    CONSTRAINT uq_user_headquarters_tenant UNIQUE (tenant_id, user_id, headquarters_id)
);

-- 2. Performance & Coverage Indexes
CREATE INDEX IF NOT EXISTS idx_user_hq_mapping_user_active 
    ON public.user_headquarters_mapping(user_id, is_active);

CREATE INDEX IF NOT EXISTS idx_user_hq_mapping_hq_active 
    ON public.user_headquarters_mapping(headquarters_id, is_active);

CREATE INDEX IF NOT EXISTS idx_user_hq_mapping_tenant 
    ON public.user_headquarters_mapping(tenant_id);

-- 3. Database-Level Tenant Integrity Safeguard Trigger
-- Prevents cross-tenant assignments: verifies user.tenant_id == headquarters.tenant_id == mapping.tenant_id
CREATE OR REPLACE FUNCTION public.check_user_hq_tenant_integrity()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_user_tenant UUID;
    v_hq_tenant UUID;
BEGIN
    SELECT tenant_id INTO v_user_tenant 
    FROM public.users 
    WHERE user_id = NEW.user_id;

    IF v_user_tenant IS NULL THEN
        RAISE EXCEPTION 'Target user % does not exist', NEW.user_id;
    END IF;

    SELECT tenant_id INTO v_hq_tenant 
    FROM public.headquarters 
    WHERE headquarters_id = NEW.headquarters_id;

    IF v_hq_tenant IS NULL THEN
        RAISE EXCEPTION 'Target headquarters % does not exist', NEW.headquarters_id;
    END IF;

    IF NEW.tenant_id IS DISTINCT FROM v_user_tenant THEN
        RAISE EXCEPTION 'Tenant mismatch: Mapping tenant_id (%) does not match user tenant_id (%)', NEW.tenant_id, v_user_tenant;
    END IF;

    IF NEW.tenant_id IS DISTINCT FROM v_hq_tenant THEN
        RAISE EXCEPTION 'Tenant mismatch: Mapping tenant_id (%) does not match headquarters tenant_id (%)', NEW.tenant_id, v_hq_tenant;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_check_user_hq_tenant_integrity ON public.user_headquarters_mapping;
CREATE TRIGGER trg_check_user_hq_tenant_integrity
    BEFORE INSERT OR UPDATE ON public.user_headquarters_mapping
    FOR EACH ROW
    EXECUTE FUNCTION public.check_user_hq_tenant_integrity();

-- 4. Automated updated_at Timestamp Trigger
CREATE OR REPLACE FUNCTION public.set_user_hq_mapping_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_user_hq_mapping_updated_at ON public.user_headquarters_mapping;
CREATE TRIGGER trg_user_hq_mapping_updated_at
    BEFORE UPDATE ON public.user_headquarters_mapping
    FOR EACH ROW
    EXECUTE FUNCTION public.set_user_hq_mapping_updated_at();

-- 5. Enable Row Level Security (RLS)
ALTER TABLE IF EXISTS public.user_headquarters_mapping ENABLE ROW LEVEL SECURITY;

-- 6. Clean Old / Insecure Policies
DROP POLICY IF EXISTS "Allow authenticated read on user_headquarters_mapping" ON public.user_headquarters_mapping;
DROP POLICY IF EXISTS "Allow service role and authenticated write on user_headquarters_mapping" ON public.user_headquarters_mapping;
DROP POLICY IF EXISTS "Allow tenant-scoped read on user_headquarters_mapping" ON public.user_headquarters_mapping;
DROP POLICY IF EXISTS "Allow admin and service-role write on user_headquarters_mapping" ON public.user_headquarters_mapping;

-- 7. Scoped RLS Security Policies
-- (a) Tenant-Scoped Read Policy:
-- Service role has full access; authenticated users can only view assignments within their own tenant
CREATE POLICY "Allow tenant-scoped read on user_headquarters_mapping" ON public.user_headquarters_mapping
    FOR SELECT USING (
        auth.role() = 'service_role'
        OR user_id = auth.uid()
        OR tenant_id = (SELECT u.tenant_id FROM public.users u WHERE u.user_id = auth.uid())
    );

-- (b) Administrative Write Policy (INSERT, UPDATE, DELETE):
-- Service role has full access; authenticated users must hold an administrative role in the same tenant
CREATE POLICY "Allow admin and service-role write on user_headquarters_mapping" ON public.user_headquarters_mapping
    FOR ALL USING (
        auth.role() = 'service_role'
        OR (
            tenant_id = (SELECT u.tenant_id FROM public.users u WHERE u.user_id = auth.uid())
            AND EXISTS (
                SELECT 1 FROM public.user_roles ur
                JOIN public.roles r ON ur.role_id = r.role_id
                WHERE ur.user_id = auth.uid()
                  AND LOWER(r.role_name) IN ('admin', 'super_admin', 'super admin', 'developer')
                  AND ur.is_active = true
            )
        )
    )
    WITH CHECK (
        auth.role() = 'service_role'
        OR (
            tenant_id = (SELECT u.tenant_id FROM public.users u WHERE u.user_id = auth.uid())
            AND EXISTS (
                SELECT 1 FROM public.user_roles ur
                JOIN public.roles r ON ur.role_id = r.role_id
                WHERE ur.user_id = auth.uid()
                  AND LOWER(r.role_name) IN ('admin', 'super_admin', 'super admin', 'developer')
                  AND ur.is_active = true
            )
        )
    );

-- 8. Explicit Permissions / Grants
-- Revoke all access from anon and public (no unauthenticated access permitted)
REVOKE ALL ON TABLE public.user_headquarters_mapping FROM anon, public;

-- Grant required permissions to service_role, postgres, and authenticated
GRANT ALL ON TABLE public.user_headquarters_mapping TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.user_headquarters_mapping TO authenticated;
