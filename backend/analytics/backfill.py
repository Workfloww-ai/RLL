import logging
import time
from typing import List, Optional
from datetime import datetime
from backend.db.client import get_supabase

logger = logging.getLogger("analytics_backfill")

def backfill_summary_tables(start_date: Optional[str] = None, end_date: Optional[str] = None) -> bool:
    """
    Safely backfills historical sales_fact records into sales_daily_summary and sales_monthly_summary.
    Processes data date-by-date to prevent memory or transaction lock issues.
    Restartable & idempotent.
    """
    client = get_supabase()
    if not client:
        logger.warning("[ANALYTICS BACKFILL] Supabase client unavailable. Skipping backfill.")
        return False

    t_start = time.time()
    logger.info("[ANALYTICS BACKFILL] Initiating historical summary backfill process...")

    try:
        # Fetch distinct sale_dates using get_distinct_sale_dates RPC function
        res = client.rpc("get_distinct_sale_dates").execute()
        rows = res.data or []
        distinct_dates = set()
        for r in rows:
            if r.get("sale_date"):
                d_str = str(r["sale_date"]).split("T")[0]
                if start_date and d_str < start_date:
                    continue
                if end_date and d_str > end_date:
                    continue
                distinct_dates.add(d_str)

        sorted_dates = sorted(list(distinct_dates))
        total_dates = len(sorted_dates)
        logger.info(f"[ANALYTICS BACKFILL] Found {total_dates} distinct sale dates to process.")

        if total_dates == 0:
            logger.info("[ANALYTICS BACKFILL] No sales records found to backfill.")
            return True

        processed_count = 0
        affected_months = set()

        for idx, s_date in enumerate(sorted_dates, 1):
            t_date_start = time.time()
            try:
                # 1. Refresh Daily Summary
                client.rpc("refresh_sales_daily_summary_for_date", {"p_sale_date": s_date}).execute()
                
                # Track month start for batch monthly refresh
                dt = datetime.strptime(s_date, "%Y-%m-%d")
                month_start = f"{dt.year:04d}-{dt.month:02d}-01"
                affected_months.add(month_start)

                processed_count += 1
                duration_ms = round((time.time() - t_date_start) * 1000, 2)
                logger.info(f"[ANALYTICS BACKFILL] Progress: {idx}/{total_dates} dates processed ({s_date} completed in {duration_ms}ms)")
            except Exception as e_date:
                logger.error(f"[ANALYTICS BACKFILL] Error backfilling date {s_date}: {e_date}")

        # 2. Refresh Monthly Summaries for affected months (depot-by-depot to prevent timeouts)
        logger.info(f"[ANALYTICS BACKFILL] Refreshing {len(affected_months)} affected monthly summaries...")
        for m_start in sorted(list(affected_months)):
            try:
                dt = datetime.strptime(m_start, "%Y-%m-%d")
                if dt.month == 12:
                    next_year = dt.year + 1
                    next_month = 1
                else:
                    next_year = dt.year
                    next_month = dt.month + 1
                m_end = f"{next_year:04d}-{next_month:02d}-01"

                # Find affected depots in daily summary and existing depots in monthly summary
                res_daily = client.table("sales_daily_summary").select("depot_id").gte("sale_date", m_start).lt("sale_date", m_end).execute()
                depots_daily = {r["depot_id"] for r in (res_daily.data or []) if r.get("depot_id")}

                res_monthly = client.table("sales_monthly_summary").select("depot_id").eq("month_start", m_start).execute()
                depots_monthly = {r["depot_id"] for r in (res_monthly.data or []) if r.get("depot_id")}

                all_depots = depots_daily.union(depots_monthly)
                logger.info(f"[ANALYTICS BACKFILL] Refreshing {len(all_depots)} depots for month {m_start}...")

                for d_id in sorted(list(all_depots)):
                    client.rpc("refresh_sales_monthly_summary_for_month", {
                        "p_month_start": m_start,
                        "p_depot_id": d_id
                    }).execute()

                logger.info(f"[ANALYTICS BACKFILL] Refreshed monthly summary for month_start={m_start}")
            except Exception as e_month:
                logger.error(f"[ANALYTICS BACKFILL] Error refreshing month {m_start}: {e_month}")

        t_total = round(time.time() - t_start, 2)
        logger.info(f"[ANALYTICS BACKFILL] Completed backfill for {processed_count}/{total_dates} dates across {len(affected_months)} months in {t_total}s.")
        return True

    except Exception as e:
        logger.error(f"[ANALYTICS BACKFILL] Critical backfill failure: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    backfill_summary_tables()
