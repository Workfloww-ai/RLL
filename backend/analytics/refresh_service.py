import logging
from datetime import date
from typing import List, Set, Union
from backend.db.client import get_supabase

logger = logging.getLogger(__name__)

class AnalyticsRefreshService:
    """
    Service executing idempotent daily & monthly summary updates
    after successful ingestion of sales_fact batches.
    """

    def refresh_sales_analytics_for_dates(self, sale_dates: List[Union[str, date]]) -> bool:
        """
        Refreshes daily summary and monthly summary for all distinct dates affected by a batch.
        """
        if not sale_dates:
            return True

        client = get_supabase()
        if not client:
            logger.info(f"[Mock] refresh_sales_analytics_for_dates count={len(sale_dates)}")
            return True

        # Extract unique dates formatted as YYYY-MM-DD
        unique_dates: Set[str] = {
            str(d).split("T")[0].strip() 
            for d in sale_dates 
            if d and str(d).strip()
        }

        success = True
        for d_str in unique_dates:
            try:
                # Trigger refreshes
                client.rpc("refresh_dashboard_daily", {"p_sale_date": d_str}).execute()
                client.rpc("refresh_dashboard_monthly", {"p_date": d_str}).execute()
                client.rpc("refresh_company_sales_summary", {"p_sale_date": d_str}).execute()
                logger.info(f"Successfully refreshed all analytics & company_sales_summary for date: {d_str}")
            except Exception as e:
                logger.warning(f"RPC refresh failed for date {d_str}: {e}")
                success = False

        return success

analytics_refresh_service = AnalyticsRefreshService()
