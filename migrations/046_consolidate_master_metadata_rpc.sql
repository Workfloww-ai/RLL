-- Migration: 046_consolidate_master_metadata_rpc.sql
-- Description: Consolidates 13 separate master metadata HTTP queries into a single high-performance RPC
-- and bundles MAX(sale_date) to reduce cold-start network roundtrips from 14 to 1 (< 100ms).

-- 1. Create dedicated standalone helper function for latest sale date
CREATE OR REPLACE FUNCTION public.get_latest_sale_date()
RETURNS DATE
LANGUAGE sql
STABLE
AS $$
    SELECT MAX(sale_date) FROM public.sales_daily_summary;
$$;

GRANT EXECUTE ON FUNCTION public.get_latest_sale_date() TO authenticated, service_role, anon;

-- 2. Create high-performance master metadata bundle RPC
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
                'company_name', c.company_name
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
            WHERE ur.is_active IS TRUE
        ), '[]'::jsonb),
        
        'users', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'user_id', u.user_id,
                'first_name', u.first_name,
                'last_name', u.last_name,
                'email', u.email,
                'is_active', u.is_active
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
            WHERE uhm.is_active IS TRUE
        ), '[]'::jsonb),
        
        'ase_tsm_mapping', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'tsm_user_id', atm.tsm_user_id,
                'ase_user_id', atm.ase_user_id
            ))
            FROM public.ase_tsm_mapping atm
        ), '[]'::jsonb)
    ) INTO v_result;

    RETURN v_result;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_master_metadata_bundle() TO authenticated, service_role, anon;
