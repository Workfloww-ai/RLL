-- Rollback: 050_drop_obsolete_tsm_rpc_overloads_rollback.sql
-- Description: Recreates the 3-parameter get_mobile_tsm_sales_summary_json function overload as a wrapper if needed.

CREATE OR REPLACE FUNCTION public.get_mobile_tsm_sales_summary_json(
    p_target_date DATE,
    p_mtd_start   DATE,
    p_ytd_start   DATE
)
RETURNS JSONB
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN public.get_mobile_tsm_sales_summary_json(p_target_date, p_mtd_start, p_ytd_start, NULL);
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_mobile_tsm_sales_summary_json(DATE, DATE, DATE) TO authenticated, service_role, anon;
