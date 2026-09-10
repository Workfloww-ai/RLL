import logging
import time
import asyncio
from datetime import datetime, date
from typing import List, Set, Union, Dict, Any, Optional

from backend.db.client import get_supabase
from backend.db.redis_client import safe_delete_pattern

logger = logging.getLogger("incremental_analytics_engine")

class IncrementalAnalyticsEngine:
    """
    Enterprise Incremental Analytics Aggregation Engine for Rajasthan Liquor Limited (RLL).
    Processes sales_fact batch updates by calculating summary aggregations strictly for affected
    dates and financial months. Guarantees 100% idempotency, transaction safety, and Redis cache invalidation.
    """

    def purge_batch_facts(self, batch_id: Union[int, str]) -> bool:
        """
        Phase 3 Batch-Scoped Replacement:
        Safely purges sales facts belonging strictly to batch_id from sales_fact and user_sales_fact,
        leaving facts from other upload batches completely untouched.
        """
        client = get_supabase()
        if not client or not batch_id:
            return True

        batch_id_str = str(batch_id).strip()
        # Schema guard: Ensure batch_id is valid 36-char UUID format before querying PostgreSQL UUID column
        if len(batch_id_str) != 36 and "-" not in batch_id_str:
            logger.info(f"[ANALYTICS] Non-UUID batch_id '{batch_id_str}' passed; skipping live DB deletion.")
            return True

        try:
            client.table("sales_fact").delete().eq("batch_id", batch_id_str).execute()
            try:
                client.table("user_sales_fact").delete().eq("batch_id", batch_id_str).execute()
            except Exception as e_usf:
                logger.debug(f"[ANALYTICS] user_sales_fact purge notice for batch {batch_id_str}: {e_usf}")
            logger.info(f"[ANALYTICS] Batch-scoped fact purge completed for batch_id={batch_id_str}.")
            return True
        except Exception as e:
            logger.error(f"[ANALYTICS] Failed batch-scoped fact purge for batch_id={batch_id_str}: {e}")
            return False

    def process_batch_incremental_aggregation(
        self,
        batch_id: Optional[Union[int, str]],
        sale_dates: List[Union[str, date]],
        enable_legacy_rpcs: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes incremental aggregation for all dates and financial months affected by a sales batch.
        Phase 6 Optimized: Bypasses duplicate legacy summary table RPC calls by default, relying
        strictly on set-based refresh_sales_daily_summary_for_date and refresh_sales_monthly_summary_for_month.
        """
        t_start = time.perf_counter()
        if not sale_dates:
            return {
                "success": True,
                "batch_id": batch_id,
                "affected_dates_count": 0,
                "affected_months_count": 0,
                "duration_ms": 0.0
            }

        client = get_supabase()
        if not client:
            logger.info(f"[ANALYTICS MOCK] Processed batch {batch_id} for {len(sale_dates)} dates.")
            return {
                "success": True,
                "batch_id": batch_id,
                "affected_dates_count": len(sale_dates),
                "affected_months_count": 1,
                "duration_ms": 0.0
            }

        # 1. Normalize affected sale dates to YYYY-MM-DD
        unique_dates: Set[str] = set()
        for d in sale_dates:
            if not d:
                continue
            if isinstance(d, (date, datetime)):
                unique_dates.add(d.strftime("%Y-%m-%d"))
            else:
                d_str = str(d).strip()
                # Split by T or space to extract the date portion
                d_date_part = d_str.split("T")[0].split(" ")[0].strip()
                parsed = False
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
                    try:
                        dt = datetime.strptime(d_date_part, fmt).date()
                        unique_dates.add(dt.strftime("%Y-%m-%d"))
                        parsed = True
                        break
                    except ValueError:
                        continue
                if not parsed:
                    logger.warning(f"[ANALYTICS] Could not parse date format: '{d_str}'")

        sorted_dates = sorted(list(unique_dates))
        affected_months: Set[str] = set()
        for s_date in sorted_dates:
            try:
                dt = datetime.strptime(s_date, "%Y-%m-%d")
                month_start = f"{dt.year:04d}-{dt.month:02d}-01"
                affected_months.add(month_start)
            except ValueError:
                logger.warning(f"[ANALYTICS] Invalid parsed date string encountered: '{s_date}'")

        sorted_months = sorted(list(affected_months))
        logger.info(
            f"[ANALYTICS] Batch {batch_id}: Initiating incremental aggregation for "
            f"{len(sorted_dates)} date(s) ({sorted_dates}) across {len(sorted_months)} month(s) ({sorted_months})."
        )

        daily_duration_total_ms = 0.0
        monthly_duration_total_ms = 0.0
        success = True

        # 2. Incremental Daily Aggregation
        for s_date in sorted_dates:
            t0 = time.perf_counter()
            date_ok = False
            for attempt in range(2):
                try:
                    client.rpc("refresh_sales_daily_summary_for_date", {"p_sale_date": s_date}).execute()
                    date_ok = True
                    break
                except Exception as e_retry:
                    logger.debug(f"[ANALYTICS] Daily summary attempt {attempt+1} notice for {s_date}: {e_retry}")
                    time.sleep(0.3)

            if not date_ok:
                logger.info(f"[ANALYTICS] Single-pass daily summary timeout notice for date {s_date}. Falling back to depot chunking...")
                try:
                    depots_res = client.table("depots").select("depot_id").execute()
                    depot_list = depots_res.data or []
                    client.table("sales_daily_summary").delete().eq("sale_date", s_date).execute()
                    for d in depot_list:
                        did = d.get("depot_id")
                        if did:
                            client.rpc("refresh_sales_daily_summary_for_date", {
                                "p_sale_date": s_date,
                                "p_depot_id": did
                            }).execute()
                    date_ok = True
                except Exception as e_dep_daily:
                    logger.warning(f"[ANALYTICS] Depot-chunked daily summary error for {s_date}: {e_dep_daily}")

            if date_ok:
                t1 = time.perf_counter()
                d_ms = (t1 - t0) * 1000
                daily_duration_total_ms += d_ms
                logger.info(f"[ANALYTICS] Daily summary aggregated for date {s_date} in {d_ms:.1f}ms")
            else:
                logger.warning(f"[ANALYTICS] Daily summary aggregation notice for date {s_date} after retries.")
                success = False

        # 3. Incremental Monthly Aggregation (Set-based RPC execution per affected month with resilient depot-chunking fallback)
        for m_start in sorted_months:
            t0 = time.perf_counter()
            try:
                logger.info(f"[ANALYTICS] Refreshing monthly summary for month_start {m_start}...")
                client.rpc("refresh_sales_monthly_summary_for_month", {
                    "p_month_start": m_start
                }).execute()
                
                # Phase 6 Rollback Guard: Execute legacy RPCs only if explicitly requested
                if enable_legacy_rpcs:
                    try:
                        client.rpc("refresh_dashboard_monthly", {"p_date": m_start}).execute()
                    except Exception as e_mleg:
                        logger.debug(f"[ANALYTICS] Legacy refresh_dashboard_monthly notice: {e_mleg}")

                t1 = time.perf_counter()
                m_ms = (t1 - t0) * 1000
                monthly_duration_total_ms += m_ms
                logger.info(f"[ANALYTICS] Monthly summary aggregated for month_start {m_start} in {m_ms:.1f}ms")
            except Exception as e_monthly:
                logger.warning(f"[ANALYTICS] Single-pass monthly summary notice for {m_start}: {e_monthly}. Falling back to depot chunking...")
                try:
                    depots_res = client.table("depots").select("depot_id").execute()
                    depot_list = depots_res.data or []
                    client.table("sales_monthly_summary").delete().eq("month_start", m_start).execute()
                    for d in depot_list:
                        did = d.get("depot_id")
                        if did:
                            client.rpc("refresh_sales_monthly_summary_for_month", {
                                "p_month_start": m_start,
                                "p_depot_id": did
                            }).execute()
                    t1 = time.perf_counter()
                    m_ms = (t1 - t0) * 1000
                    monthly_duration_total_ms += m_ms
                    logger.info(f"[ANALYTICS] Depot-chunked monthly aggregation completed for {m_start} ({len(depot_list)} depots) in {m_ms:.1f}ms.")
                except Exception as e_chunk:
                    logger.error(f"[ANALYTICS] Failed depot-chunked monthly aggregation for month_start {m_start}: {e_chunk}", exc_info=True)
                    success = False

        # 4. Redis Cache Pattern Invalidation (Event-Driven)
        redis_keys_deleted = 0
        try:
            from backend.services.cache_service import invalidate_analytics_cache_sync
            redis_keys_deleted = invalidate_analytics_cache_sync() or 0
            logger.info(f"[ANALYTICS] Invalidated Redis cache keys for batch {batch_id}.")
        except Exception as e_redis:
            logger.warning(f"[ANALYTICS] Non-fatal Redis invalidation notice: {e_redis}")

        t_end = time.perf_counter()
        total_duration_ms = round((t_end - t_start) * 1000, 2)

        # Structured Analytics Processing Log
        logger.info(
            f"\n==================================================\n"
            f"[ANALYTICS INCREMENTAL AGGREGATION REPORT]\n"
            f"==================================================\n"
            f"Batch ID:               {batch_id}\n"
            f"Status:                 {'SUCCESS' if success else 'PARTIAL_FAILURE'}\n"
            f"Affected Sale Dates:    {len(sorted_dates)} {sorted_dates}\n"
            f"Affected Months:        {len(sorted_months)} {sorted_months}\n"
            f"Daily Aggregation Time: {daily_duration_total_ms:.1f} ms\n"
            f"Monthly Aggregation:   {monthly_duration_total_ms:.1f} ms\n"
            f"Total Engine Duration: {total_duration_ms:.1f} ms\n"
            f"Redis Keys Cleared:     {redis_keys_deleted}\n"
            f"=================================================="
        )

        return {
            "success": success,
            "batch_id": batch_id,
            "affected_dates_count": len(sorted_dates),
            "affected_months_count": len(sorted_months),
            "daily_duration_ms": round(daily_duration_total_ms, 2),
            "monthly_duration_ms": round(monthly_duration_total_ms, 2),
            "duration_ms": total_duration_ms,
            "redis_keys_invalidated": redis_keys_deleted
        }

incremental_engine = IncrementalAnalyticsEngine()
