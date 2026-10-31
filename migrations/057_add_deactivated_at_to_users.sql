-- Migration: 057_add_deactivated_at_to_users.sql
-- Description:
-- 1. Adds deactivated_at TIMESTAMPTZ column to public.users to accurately preserve employee deactivation timestamp.
-- 2. Backfills deactivated_at from updated_at for existing inactive users.
-- 3. Updates get_master_metadata_bundle() RPC to include deactivated_at and return complete role/HQ history.
-- 4. Updates get_mobile_tsm_sales_summary_json() RPC to credit inactive users only for sales prior to deactivation date.

-- ── 1. Schema Alteration: Add deactivated_at column ─────────────────────────
ALTER TABLE IF EXISTS public.users
ADD COLUMN IF NOT EXISTS deactivated_at TIMESTAMPTZ;

-- Backfill existing inactive users with their updated_at timestamp
UPDATE public.users
SET deactivated_at = updated_at
WHERE is_active = false
  AND deactivated_at IS NULL;

-- ── 2. Update get_master_metadata_bundle() RPC ──────────────────────────────
CREATE OR REPLACE FUNCTION public.get_master_metadata_bundle()
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SET work_mem = '64MB'
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'latest_sale_date', (SELECT MAX(sale_date)::TEXT FROM public.sales_daily_summary),
        
        'companies', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'company_id', c.company_id,
                'company_name', c.company_name,
                'category', c.category
            ))
            FROM public.companies c
        ), '[]'::jsonb),
        
        'brands', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'brand_id', b.brand_id,
                'brand_name', b.brand_name,
                'company_id', b.company_id
            ))
            FROM public.brands b
        ), '[]'::jsonb),
        
        'headquarters', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'headquarters_id', h.headquarters_id,
                'name', h.name
            ))
            FROM public.headquarters h
            WHERE h.is_active IS NOT FALSE
        ), '[]'::jsonb),
        
        'depots', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'depot_id', d.depot_id,
                'name', d.name,
                'headquarters_id', d.headquarters_id
            ))
            FROM public.depots d
        ), '[]'::jsonb),
        
        'roles', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'role_id', r.role_id,
                'role_name', r.role_name
            ))
            FROM public.roles r
        ), '[]'::jsonb),
        
        'user_roles', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'user_id', ur.user_id,
                'role_id', ur.role_id,
                'is_active', ur.is_active
            ))
            FROM public.user_roles ur
        ), '[]'::jsonb),
        
        'users', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'user_id', u.user_id,
                'first_name', u.first_name,
                'last_name', u.last_name,
                'email', u.email,
                'is_active', u.is_active,
                'deactivated_at', u.deactivated_at
            ))
            FROM public.users u
        ), '[]'::jsonb),
        
        'user_depot', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'user_id', ud.user_id,
                'depot_id', ud.depot_id
            ))
            FROM public.user_depot ud
        ), '[]'::jsonb),
        
        'user_headquarters_mapping', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'user_id', uhm.user_id,
                'headquarters_id', uhm.headquarters_id,
                'is_active', uhm.is_active
            ))
            FROM public.user_headquarters_mapping uhm
        ), '[]'::jsonb),
        
        'ase_tsm_mapping', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'tsm_user_id', atm.tsm_user_id,
                'ase_user_id', atm.ase_user_id,
                'is_active', atm.is_active
            ))
            FROM public.ase_tsm_mapping atm
        ), '[]'::jsonb)
    ) INTO v_result;

    RETURN v_result;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_master_metadata_bundle() TO authenticated, service_role, anon;

-- ── 3. Update get_mobile_tsm_sales_summary_json() RPC ───────────────────────
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
    IF COALESCE(current_setting('request.jwt.claim.role', true), '') != 'service_role' 
       AND current_user NOT IN ('postgres', 'service_role') THEN
        IF auth.uid() IS NULL THEN
            RETURN '[]'::jsonb;
        END IF;

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
          AND uhm.tenant_id = p_tenant_id;

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
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS daily_bl,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS mtd_bl,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS ytd_cases,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS ytd_bottles,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS ytd_bl
                FROM public.user_sales_fact usf
                LEFT JOIN public.users u ON u.user_id = usf.user_id
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
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS daily_bl,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS mtd_bl,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS ytd_cases,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS ytd_bottles,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS ytd_bl
                FROM public.user_sales_fact usf
                LEFT JOIN public.users u ON u.user_id = usf.user_id
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
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS daily_bl,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS mtd_bl,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS ytd_cases,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS ytd_bottles,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS ytd_bl
                FROM public.user_sales_fact usf
                LEFT JOIN public.users u ON u.user_id = usf.user_id
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
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS daily_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS daily_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date = p_target_date AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS daily_bl,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS mtd_cases,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS mtd_bottles,
                    ROUND(SUM(CASE WHEN usf.sale_date >= p_mtd_start  AND (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS mtd_bl,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.cases   ELSE 0 END), 2)::NUMERIC AS ytd_cases,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bottles ELSE 0 END), 2)::NUMERIC AS ytd_bottles,
                    ROUND(SUM(CASE WHEN (u.deactivated_at IS NULL OR usf.sale_date < u.deactivated_at::date) THEN usf.bl      ELSE 0 END), 2)::NUMERIC AS ytd_bl
                FROM public.user_sales_fact usf
                LEFT JOIN public.users u ON u.user_id = usf.user_id
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

REVOKE ALL ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[], UUID, UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[], UUID, UUID) FROM anon;
REVOKE ALL ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[], UUID, UUID) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE, UUID[], UUID, UUID) TO service_role;

NOTIFY pgrst, 'reload schema';

