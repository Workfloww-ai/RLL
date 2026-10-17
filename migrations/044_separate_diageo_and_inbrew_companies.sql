-- ==============================================================================
-- Migration: 044_separate_diageo_and_inbrew_companies.sql
-- Description: Uncombines Diageo and Inbrew into two distinct standalone companies.
-- Date: 2026-10-16
-- ==============================================================================

DO $$
DECLARE
    v_diageo_id UUID;
    v_inbrew_id UUID;
    v_tenant_id UUID := 'a0000000-0000-0000-0000-000000000001'::uuid;
BEGIN
    -- 1. Ensure Diageo company exists and is properly named
    SELECT company_id INTO v_diageo_id
    FROM public.companies
    WHERE company_name ILIKE '%diageo%'
    ORDER BY created_at ASC
    LIMIT 1;

    IF v_diageo_id IS NOT NULL THEN
        UPDATE public.companies
        SET company_name = 'Diageo'
        WHERE company_id = v_diageo_id;
    ELSE
        INSERT INTO public.companies (company_name, is_active, tenant_id)
        VALUES ('Diageo', true, v_tenant_id)
        RETURNING company_id INTO v_diageo_id;
    END IF;

    -- 2. Ensure Inbrew company exists
    SELECT company_id INTO v_inbrew_id
    FROM public.companies
    WHERE company_name ILIKE '%inbrew%'
    LIMIT 1;

    IF v_inbrew_id IS NULL THEN
        INSERT INTO public.companies (company_name, is_active, tenant_id)
        VALUES ('Inbrew', true, v_tenant_id)
        RETURNING company_id INTO v_inbrew_id;
    ELSE
        UPDATE public.companies
        SET company_name = 'Inbrew'
        WHERE company_id = v_inbrew_id;
    END IF;

    -- 3. Clean up and insert normalized company aliases
    DELETE FROM public.company_aliases
    WHERE norm_key IN ('diageoinbrew', 'diageo-inbrew', 'diageo/inbrew');

    INSERT INTO public.company_aliases (norm_key, company_id, raw_name, source)
    VALUES
        ('diageo', v_diageo_id, 'Diageo', 'migration_044'),
        ('unitedspirits', v_diageo_id, 'United Spirits', 'migration_044'),
        ('inbrew', v_inbrew_id, 'Inbrew', 'migration_044'),
        ('inbrewbeverages', v_inbrew_id, 'Inbrew Beverages', 'migration_044')
    ON CONFLICT (norm_key) DO UPDATE
    SET company_id = EXCLUDED.company_id,
        raw_name = EXCLUDED.raw_name;

    -- 4. Reassign Inbrew brands (acquired from USL/Diageo portfolio)
    UPDATE public.brands
    SET company_id = v_inbrew_id
    WHERE brand_name ILIKE '%green label%'
       OR brand_name ILIKE '%blue riband%'
       OR brand_name ILIKE '%romanov%'
       OR brand_name ILIKE '%bagpiper%';

    -- 5. Reassign core Diageo brands (McDowell's, Royal Challenge, Smirnoff, Black Dog, Signature, Antiquity)
    UPDATE public.brands
    SET company_id = v_diageo_id
    WHERE (brand_name ILIKE '%mcdowell%'
       OR brand_name ILIKE '%royal challenge%'
       OR brand_name ILIKE '%smirnoff%'
       OR brand_name ILIKE '%black dog%'
       OR (brand_name ILIKE '%signature%' AND brand_name NOT ILIKE '%spier%')
       OR brand_name ILIKE '%antiquity%');

    RAISE NOTICE 'Diageo (ID: %) and Inbrew (ID: %) successfully uncombined into distinct companies.', v_diageo_id, v_inbrew_id;
END $$;
