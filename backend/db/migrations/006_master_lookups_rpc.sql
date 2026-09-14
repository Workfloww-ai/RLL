-- 006_master_lookups_rpc.sql
-- Migration: Add RPC function for single-query master lookups (companies, brands, depots, headquarters)

CREATE OR REPLACE FUNCTION public.get_master_lookups_json()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
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
        ), '[]'::jsonb),

        'depots', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'depot_id', d.depot_id,
                'name', d.name,
                'headquarters_id', d.headquarters_id
            ))
            FROM public.depots d
        ), '[]'::jsonb)
    ) INTO v_result;

    RETURN v_result;
END;
$$;
