import logging
from backend.db.client import get_supabase

logger = logging.getLogger(__name__)

def backfill_historical_summaries() -> bool:
    """
    Backfills dashboard_summary_daily and dashboard_summary_monthly
    by fetching distinct sale_dates from sales_fact and running refresh_sales_analytics.
    """
    client = get_supabase()
    if not client:
        logger.info("[Mock] Historical backfill skipped: Supabase client unavailable.")
        return True

    try:
        logger.info("Fetching distinct sale_dates from sales_fact for backfill...")
        res = client.table("sales_fact").select("sale_date").execute()
        
        if not res.data:
            logger.info("No existing records in sales_fact to backfill.")
            return True

        distinct_dates = sorted(list({
            str(row["sale_date"]).split("T")[0] 
            for row in res.data 
            if row.get("sale_date")
        }))

        logger.info(f"Found {len(distinct_dates)} distinct dates in sales_fact. Starting refresh...")

        for d_str in distinct_dates:
            try:
                client.rpc("refresh_sales_analytics", {"p_sale_date": d_str}).execute()
                logger.info(f"Backfilled analytics summary for date: {d_str}")
            except Exception as e:
                logger.warning(f"RPC refresh_sales_analytics failed for date {d_str}: {e}")

        logger.info("Completed historical summary backfill successfully!")
        return True

    except Exception as e:
        logger.error(f"Historical backfill failed: {e}")
        return False

if __name__ == "__main__":
    backfill_historical_summaries()
