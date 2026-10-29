-- Migration: 051_optimize_tsm_sales_rpc_and_indexing.sql
-- Description: Canonicalizes and optimizes get_mobile_tsm_sales_summary_json by:
-- 1. Dropping obsolete 3-arg, 4-arg, and 5-arg overloads to eliminate PGRST203 ambiguity.
-- 2. Providing a single canonical 6-parameter RPC supporting p_hq_id and mandatory p_tenant_id scoping.
-- 3. Short-circuiting empty user list (p_user_ids = []) to immediately return [] in 0ms.
-- 4. Enforcing strict multi-tenant isolation across user_sales_fact, companies, and HQ mappings.
--    FAIL-CLOSED: If p_tenant_id IS NULL, immediately returns [] in 0ms. Never executes cross-tenant queries.
-- 5. Hardening caller authentication: Only service_role is trusted to supply arbitrary p_tenant_id.
--    All other callers (anon, missing role claim, or authenticated) fail closed unless verified against auth.uid().
-- 6. Least privilege: Revoking execute permissions from PUBLIC, anon, and authenticated; granting exclusively to service_role.
-- 7. High-performance covering B-Tree indexes on public.user_sales_fact:
--    a) idx_usf_tenant_user_date_covering: accelerates user/HQ-scoped lookups (TSM, ASE, specific HQ).
--    b) idx_usf_tenant_date_user_covering: accelerates statewide All-HQ lookups (Index-Only Scan).
-- 8. Refreshing PostgREST schema cache via NOTIFY pgrst.

-- ── 1. Create Covering Composite Indexes on user_sales_fact ───────────────────────────
-- Index A: User-scoped queries (TSM / ASE / Selected HQ) seeking directly to (tenant_id, user_id)
CREATE INDEX IF NOT EXISTS idx_usf_tenant_user_date_covering
ON public.user_sales_fact (tenant_id, user_id, sale_date DESC)
INCLUDE (company_id, brand_id, cases, bottles, bl);

-- Index B: Statewide All-HQ queries scanning contiguous date ranges within tenant (Index-Only Scan)
CREATE INDEX IF NOT EXISTS idx_usf_tenant_date_user_covering
ON public.user_sales_fact (tenant_id, sale_date DESC, user_id)
INCLUDE (company_id, brand_id, cases, bottles, bl);

-- ── 2. Drop Obsolete Overloads to Prevent PostgREST Schema Ambiguity (PGRST203) ─────────
DROP FUNCTION IF EXISTS public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE);
DROP FUNCTION IF EXISTS public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[]);
DROP FUNCTION IF EXISTS public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[], UUID);
DROP FUNCTION IF EXISTS public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[], UUID, UUID);

-- ── 3. Canonical get_mobile_tsm_sales_summary_json Function ───────────────────────────
CREATE OR REPLACE FUNCTION public.get_mobile_tsm_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE,
    p_user_ids    UUID[] DEFAULT NULL,
    p_hq_id       UUID   DEFAULT NULL,
    p_tenant_id   UUID   DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
SET work_mem = '64MB'
SET enable_incremental_sort = off
AS $$
DECLARE
    v_include_others BOOLEAN;
    v_valid_company_ids UUID[];
    v_target_user_ids UUID[];
    v_result JSONB;
BEGIN
    -- Mandatory Tenant Scope: Fail-closed if p_tenant_id is NULL, missing, or unresolved
    IF p_tenant_id IS NULL THEN
        RETURN '[]'::jsonb;
    END IF;

    -- Authoritative Caller Validation:
    -- Only service_role (or postgres superuser during maintenance) is trusted to supply arbitrary p_tenant_id.
    -- All other callers (anon, missing role claim, or authenticated) MUST be verified against auth.uid().
    IF COALESCE(current_setting('request.jwt.claim.role', true), '') != 'service_role' 
       AND current_user NOT IN ('postgres', 'service_role') THEN
        -- If caller has no authenticated identity, fail closed immediately
        IF auth.uid() IS NULL THEN
            RETURN '[]'::jsonb;
        END IF;

        -- Enforce that authenticated user authoritatively belongs to p_tenant_id in public.users
        IF NOT EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.user_id = auth.uid()
              AND u.tenant_id = p_tenant_id
              AND (u.is_active IS NULL OR u.is_active = true)
        ) THEN
            RETURN '[]'::jsonb;
        END IF;
    END IF;

    -- Empty user list fast-path: return [] immediately in 0ms without hitting sales table
    IF p_user_ids IS NOT NULL AND cardinality(p_user_ids) = 0 THEN
        RETURN '[]'::jsonb;
    END IF;

    v_include_others := public.get_include_others_in_sales();

    -- Resolve user IDs: explicit user_ids take precedence; otherwise resolve from p_hq_id
    IF p_user_ids IS NOT NULL AND cardinality(p_user_ids) > 0 THEN
        v_target_user_ids := p_user_ids;
    ELSIF p_hq_id IS NOT NULL THEN
        SELECT COALESCE(ARRAY_AGG(uhm.user_id), '{}'::UUID[])
        INTO v_target_user_ids
        FROM public.user_headquarters_mapping uhm
        WHERE uhm.headquarters_id = p_hq_id
          AND (uhm.is_active IS NULL OR uhm.is_active = true)
          AND uhm.tenant_id = p_tenant_id;

        -- If the target HQ has 0 mapped users for this tenant, return empty JSON array in 0ms
        IF cardinality(v_target_user_ids) = 0 THEN
            RETURN '[]'::jsonb;
        END IF;
    ELSE
        v_target_user_ids := NULL;
    END IF;

    IF v_include_others THEN
        -- When Others toggle is ON: Include ALL companies in TSM sales
        IF v_target_user_ids IS NOT NULL AND cardinality(v_target_user_ids) > 0 THEN
            SELECT COALESCE(to_jsonb(json_agg(tsm_row)), '[]'::jsonb)
            INTO v_result
            FROM (
                SELECT
                    usf.user_id,
                    usf.company_id,
                    usf.brand_id,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS daily_bl,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS mtd_bl,
                    ROUND(SUM(usf.cases), 2)::NUMERIC                                                             AS ytd_cases,
                    ROUND(SUM(usf.bottles), 2)::NUMERIC                                                           AS ytd_bottles,
                    ROUND(SUM(usf.bl), 2)::NUMERIC                                                              AS ytd_bl
                FROM public.user_sales_fact usf
                WHERE usf.user_id = ANY(v_target_user_ids)
                  AND usf.sale_date >= p_ytd_start
                  AND usf.sale_date <= p_target_date
                  AND usf.tenant_id = p_tenant_id
                GROUP BY usf.user_id, usf.company_id, usf.brand_id
            ) tsm_row;
        ELSE
            SELECT COALESCE(to_jsonb(json_agg(tsm_row)), '[]'::jsonb)
            INTO v_result
            FROM (
                SELECT
                    usf.user_id,
                    usf.company_id,
                    usf.brand_id,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS daily_bl,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS mtd_bl,
                    ROUND(SUM(usf.cases), 2)::NUMERIC                                                             AS ytd_cases,
                    ROUND(SUM(usf.bottles), 2)::NUMERIC                                                           AS ytd_bottles,
                    ROUND(SUM(usf.bl), 2)::NUMERIC                                                              AS ytd_bl
                FROM public.user_sales_fact usf
                WHERE usf.sale_date >= p_ytd_start
                  AND usf.sale_date <= p_target_date
                  AND usf.tenant_id = p_tenant_id
                GROUP BY usf.user_id, usf.company_id, usf.brand_id
            ) tsm_row;
        END IF;
    ELSE
        -- When Others toggle is OFF: Exclude Company 'Others'
        SELECT ARRAY_AGG(c.company_id) INTO v_valid_company_ids
        FROM public.companies c
        WHERE LOWER(TRIM(c.company_name)) NOT IN ('others', 'other')
          AND c.tenant_id = p_tenant_id;

        IF v_target_user_ids IS NOT NULL AND cardinality(v_target_user_ids) > 0 THEN
            SELECT COALESCE(to_jsonb(json_agg(tsm_row)), '[]'::jsonb)
            INTO v_result
            FROM (
                SELECT
                    usf.user_id,
                    usf.company_id,
                    usf.brand_id,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS daily_bl,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS mtd_bl,
                    ROUND(SUM(usf.cases), 2)::NUMERIC                                                             AS ytd_cases,
                    ROUND(SUM(usf.bottles), 2)::NUMERIC                                                           AS ytd_bottles,
                    ROUND(SUM(usf.bl), 2)::NUMERIC                                                              AS ytd_bl
                FROM public.user_sales_fact usf
                WHERE usf.user_id = ANY(v_target_user_ids)
                  AND usf.company_id = ANY(v_valid_company_ids)
                  AND usf.sale_date >= p_ytd_start
                  AND usf.sale_date <= p_target_date
                  AND usf.tenant_id = p_tenant_id
                GROUP BY usf.user_id, usf.company_id, usf.brand_id
            ) tsm_row;
        ELSE
            SELECT COALESCE(to_jsonb(json_agg(tsm_row)), '[]'::jsonb)
            INTO v_result
            FROM (
                SELECT
                    usf.user_id,
                    usf.company_id,
                    usf.brand_id,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date  THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS daily_bl,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start   THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  THEN usf.bl ELSE 0 END), 2)::NUMERIC     AS mtd_bl,
                    ROUND(SUM(usf.cases), 2)::NUMERIC                                                             AS ytd_cases,
                    ROUND(SUM(usf.bottles), 2)::NUMERIC                                                           AS ytd_bottles,
                    ROUND(SUM(usf.bl), 2)::NUMERIC                                                              AS ytd_bl
                FROM public.user_sales_fact usf
                WHERE usf.company_id = ANY(v_valid_company_ids)
                  AND usf.sale_date >= p_ytd_start
                  AND usf.sale_date <= p_target_date
                  AND usf.tenant_id = p_tenant_id
                GROUP BY usf.user_id, usf.company_id, usf.brand_id
            ) tsm_row;
        END IF;
    END IF;

    RETURN COALESCE(v_result, '[]'::jsonb);
END;
$$;

-- ── 4. Grant Permissions (Least Privilege: Service Role Only) ─────────────────────────
-- Revoke all direct client execution from PUBLIC, anon, and authenticated roles.
-- The RPC is intended exclusively for trusted backend calls via SUPABASE_SERVICE_ROLE_KEY.
REVOKE ALL ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[], UUID, UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[], UUID, UUID) FROM anon;
REVOKE ALL ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[], UUID, UUID) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[], UUID, UUID) TO service_role;

-- ── 5. Reload PostgREST Schema Cache ──────────────────────────────────────────────────
NOTIFY pgrst, 'reload schema';
