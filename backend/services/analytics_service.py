import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Set
from backend.db.client import get_supabase
from backend.services.analytics_scope_service import analytics_scope_service

logger = logging.getLogger(__name__)

class AnalyticsService:
    """
    Enterprise Analytics Engine serving Daily, MTD, and YTD performance.
    
    IMPORTANT:
    This service queries ONLY pre-aggregated summary tables:
      - dashboard_summary_daily
      - dashboard_summary_monthly
    It NEVER queries sales_fact directly for dashboard rendering.
    """

    def get_dashboard(
        self,
        period: str = "daily",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        depot_id: Optional[int] = None,
        brand_id: Optional[int] = None,
        current_user: Optional[dict] = None
    ) -> Dict[str, Any]:
        """
        Unified endpoint for Daily, MTD, and YTD analytics with RBAC scoping.
        """
        client = get_supabase()
        period = (period or "daily").lower()

        # Target date (defaults to today if not provided)
        target_date_str = to_date or datetime.today().strftime("%Y-%m-%d")
        try:
            target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            target_dt = datetime.today().date()
            target_date_str = target_dt.strftime("%Y-%m-%d")

        # Resolve User Depot Scope (RBAC)
        allowed_depot_ids: Optional[Set[int]] = None
        if current_user:
            allowed_depot_ids = analytics_scope_service.resolve_allowed_depot_ids(current_user)

        # Validate user-supplied depot_id against allowed scope
        if depot_id is not None:
            if allowed_depot_ids is not None and depot_id not in allowed_depot_ids:
                # Return empty result if requested depot is out of scope
                return self._empty_response(period, from_date or target_date_str, target_date_str)
            query_depot_ids = {depot_id}
        else:
            query_depot_ids = allowed_depot_ids

        if period == "mtd":
            start_date_str = target_dt.replace(day=1).strftime("%Y-%m-%d")
            return self._get_daily_summary_range(
                period="mtd",
                start_date=start_date_str,
                end_date=target_date_str,
                depot_ids=query_depot_ids,
                brand_id=brand_id,
                client=client
            )
        elif period == "ytd":
            return self._get_ytd_summary(
                target_date=target_dt,
                depot_ids=query_depot_ids,
                brand_id=brand_id,
                client=client
            )
        else:
            # Daily period
            start_date_str = from_date or target_date_str
            return self._get_daily_summary_range(
                period="daily",
                start_date=start_date_str,
                end_date=target_date_str,
                depot_ids=query_depot_ids,
                brand_id=brand_id,
                client=client
            )

    def _get_daily_summary_range(
        self,
        period: str,
        start_date: str,
        end_date: str,
        depot_ids: Optional[Set[int]],
        brand_id: Optional[int],
        client: Any
    ) -> Dict[str, Any]:
        """Queries dashboard_summary_daily for a specific date range."""
        if not client:
            return self._empty_response(period, start_date, end_date)

        try:
            query = (
                client.table("dashboard_summary_daily")
                .select("sale_date, depot_id, brand_id, total_case, total_btl, total_bl")
                .gte("sale_date", start_date)
                .lte("sale_date", end_date)
            )

            if depot_ids is not None:
                if not depot_ids:
                    return self._empty_response(period, start_date, end_date)
                query = query.in_("depot_id", list(depot_ids))

            if brand_id is not None:
                query = query.eq("brand_id", brand_id)

            res = query.execute()
            rows = res.data or []

            return self._format_aggregated_response(period, start_date, end_date, rows, client)

        except Exception as e:
            logger.error(f"_get_daily_summary_range error: {e}")
            return self._empty_response(period, start_date, end_date)

    def _get_ytd_summary(
        self,
        target_date: date,
        depot_ids: Optional[Set[int]],
        brand_id: Optional[int],
        client: Any
    ) -> Dict[str, Any]:
        """
        Hybrid YTD Algorithm:
        - Completed Months (dashboard_summary_monthly) from FY Start (April 1) to previous month.
        - Current Partial Month (dashboard_summary_daily) from 1st of current month to target_date.
        """
        # Determine Financial Year Start (April 1)
        if target_date.month >= 4:
            fy_start_year = target_date.year
        else:
            fy_start_year = target_date.year - 1
        
        fy_start_date = date(fy_start_year, 4, 1)
        current_month_start = target_date.replace(day=1)

        ytd_rows = []

        if not client:
            return self._empty_response("ytd", fy_start_date.strftime("%Y-%m-%d"), target_date.strftime("%Y-%m-%d"))

        try:
            # 1. Fetch Completed Months from dashboard_summary_monthly
            if current_month_start > fy_start_date:
                m_query = (
                    client.table("dashboard_summary_monthly")
                    .select("month_start, depot_id, brand_id, total_case, total_btl, total_bl")
                    .gte("month_start", fy_start_date.strftime("%Y-%m-%d"))
                    .lt("month_start", current_month_start.strftime("%Y-%m-%d"))
                )
                if depot_ids is not None:
                    if depot_ids:
                        m_query = m_query.in_("depot_id", list(depot_ids))
                    else:
                        m_query = None
                if brand_id is not None and m_query:
                    m_query = m_query.eq("brand_id", brand_id)
                
                if m_query:
                    m_res = m_query.execute()
                    if m_res.data:
                        ytd_rows.extend(m_res.data)

            # 2. Fetch Current Partial Month from dashboard_summary_daily
            d_query = (
                client.table("dashboard_summary_daily")
                .select("sale_date, depot_id, brand_id, total_case, total_btl, total_bl")
                .gte("sale_date", current_month_start.strftime("%Y-%m-%d"))
                .lte("sale_date", target_date.strftime("%Y-%m-%d"))
            )
            if depot_ids is not None:
                if depot_ids:
                    d_query = d_query.in_("depot_id", list(depot_ids))
                else:
                    d_query = None
            if brand_id is not None and d_query:
                d_query = d_query.eq("brand_id", brand_id)

            if d_query:
                d_res = d_query.execute()
                if d_res.data:
                    ytd_rows.extend(d_res.data)

            return self._format_aggregated_response(
                "ytd", 
                fy_start_date.strftime("%Y-%m-%d"), 
                target_date.strftime("%Y-%m-%d"), 
                ytd_rows, 
                client
            )

        except Exception as e:
            logger.error(f"_get_ytd_summary error: {e}")
            return self._empty_response("ytd", fy_start_date.strftime("%Y-%m-%d"), target_date.strftime("%Y-%m-%d"))

    def _format_aggregated_response(
        self,
        period: str,
        from_date: str,
        to_date: str,
        rows: List[dict],
        client: Any
    ) -> Dict[str, Any]:
        """Aggregates rows by brand and totals for API consumption."""
        total_cases = sum(float(r.get("total_case") or 0) for r in rows)
        total_bottles = sum(float(r.get("total_btl") or 0) for r in rows)
        total_bl = sum(float(r.get("total_bl") or 0) for r in rows)

        # Brand-wise Aggregation
        brand_stats: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            b_id = r.get("brand_id")
            if b_id is None:
                continue
            if b_id not in brand_stats:
                brand_stats[b_id] = {
                    "brand_id": b_id,
                    "total_cases": 0.0,
                    "total_bottles": 0.0,
                    "total_bl": 0.0
                }
            brand_stats[b_id]["total_cases"] += float(r.get("total_case") or 0)
            brand_stats[b_id]["total_bottles"] += float(r.get("total_btl") or 0)
            brand_stats[b_id]["total_bl"] += float(r.get("total_bl") or 0)

        # Fetch Brand Names from Master Table
        brand_lookup = {}
        if brand_stats and client:
            try:
                b_res = client.table("brands").select("brand_id, brand_name").in_("brand_id", list(brand_stats.keys())).execute()
                for b_row in (b_res.data or []):
                    brand_lookup[b_row["brand_id"]] = b_row.get("brand_name", f"Brand {b_row['brand_id']}")
            except Exception as e:
                logger.warning(f"Failed to fetch brand names: {e}")

        brands_list = []
        for b_id, stats in brand_stats.items():
            b_name = brand_lookup.get(b_id, f"Brand {b_id}")
            brands_list.append({
                "brand_id": b_id,
                "brand_name": b_name,
                "total_cases": round(stats["total_cases"], 2),
                "total_bottles": round(stats["total_bottles"], 2),
                "total_bl": round(stats["total_bl"], 2)
            })

        # Sort brands descending by Total Bulk Liters (QTY BL)
        brands_list.sort(key=lambda x: x["total_bl"], reverse=True)

        return {
            "period": period,
            "from_date": from_date,
            "to_date": to_date,
            "totals": {
                "total_cases": round(total_cases, 2),
                "total_bottles": round(total_bottles, 2),
                "total_bl": round(total_bl, 2)
            },
            "brands": brands_list
        }

    def _empty_response(self, period: str, from_date: str, to_date: str) -> Dict[str, Any]:
        return {
            "period": period,
            "from_date": from_date,
            "to_date": to_date,
            "totals": {
                "total_cases": 0.0,
                "total_bottles": 0.0,
                "total_bl": 0.0
            },
            "brands": []
        }

analytics_service = AnalyticsService()