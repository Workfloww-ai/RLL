# from typing import Dict, Any, List, Optional
# from datetime import datetime, date
# from backend.services.import_pipeline import sales_db, dashboard_summary_db
# from backend.services.master_service import master_service

# class AnalyticsService:

#     def get_dashboard_overview(
#         self, 
#         start_date: Optional[str] = None, 
#         end_date: Optional[str] = None,
#         depot_id: Optional[int] = None,
#         circle_id: Optional[int] = None
#     ) -> Dict[str, Any]:
        
#         filtered_sales = sales_db.copy()

#         if start_date:
#             filtered_sales = [s for s in filtered_sales if s["sales_date"] >= start_date]
#         if end_date:
#             filtered_sales = [s for s in filtered_sales if s["sales_date"] <= end_date]
#         if depot_id:
#             filtered_sales = [s for s in filtered_sales if s["depot_id"] == depot_id]

#         total_sales_value = sum(s["sale_value"] for s in filtered_sales)
#         total_cases_sold = sum(s["total_cases"] for s in filtered_sales)
#         total_bottles_sold = sum(s["total_bottles"] for s in filtered_sales)
#         total_bulk_liters = sum(s["total_bulk_liters"] for s in filtered_sales)
#         active_licensees = len(set(s["licensee_id"] for s in filtered_sales))
#         active_brands = len(set(s["brand_id"] for s in filtered_sales))

#         kpis = {
#             "total_sales_value": round(total_sales_value, 2),
#             "total_cases_sold": round(total_cases_sold, 2),
#             "total_bottles_sold": round(total_bottles_sold, 2),
#             "total_bulk_liters": round(total_bulk_liters, 2),
#             "active_licensees_count": active_licensees,
#             "active_brands_count": active_brands,
#             "growth_percentage": 12.5 # Mock growth metric for dashboard
#         }

#         # Daily trends
#         trends_dict: Dict[str, Dict[str, Any]] = {}
#         for s in filtered_sales:
#             s_date = s["sales_date"]
#             if s_date not in trends_dict:
#                 trends_dict[s_date] = {
#                     "sales_date": s_date,
#                     "total_sales": 0.0,
#                     "total_cases": 0.0,
#                     "total_bottles": 0.0
#                 }
#             trends_dict[s_date]["total_sales"] += s["sale_value"]
#             trends_dict[s_date]["total_cases"] += s["total_cases"]
#             trends_dict[s_date]["total_bottles"] += s["total_bottles"]

#         trends_list = sorted(list(trends_dict.values()), key=lambda x: x["sales_date"])

#         # Top Brands
#         brand_lookup = {b["brand_id"]: b for b in master_service.get_brands()}
#         brand_stats: Dict[int, Dict[str, Any]] = {}
#         for s in filtered_sales:
#             b_id = s["brand_id"]
#             if b_id not in brand_stats:
#                 b_info = brand_lookup.get(b_id, {"brand_name": f"Brand {b_id}", "brand_code": f"B{b_id}"})
#                 brand_stats[b_id] = {
#                     "brand_id": b_id,
#                     "brand_name": b_info["brand_name"],
#                     "brand_code": b_info["brand_code"],
#                     "total_cases": 0.0,
#                     "total_sales_value": 0.0
#                 }
#             brand_stats[b_id]["total_cases"] += s["total_cases"]
#             brand_stats[b_id]["total_sales_value"] += s["sale_value"]

#         top_brands = sorted(list(brand_stats.values()), key=lambda x: x["total_sales_value"], reverse=True)[:5]
#         for tb in top_brands:
#             tb["market_share_percentage"] = round((tb["total_sales_value"] / total_sales_value * 100), 2) if total_sales_value > 0 else 0.0

#         # Top Depots
#         depot_lookup = {d["depot_id"]: d for d in master_service.get_depots()}
#         depot_stats: Dict[int, Dict[str, Any]] = {}
#         for s in filtered_sales:
#             d_id = s["depot_id"]
#             if d_id not in depot_stats:
#                 d_info = depot_lookup.get(d_id, {"depot_name": f"Depot {d_id}", "depot_code": f"D{d_id}"})
#                 depot_stats[d_id] = {
#                     "depot_id": d_id,
#                     "depot_name": d_info["depot_name"],
#                     "depot_code": d_info["depot_code"],
#                     "circle_name": "Jaipur Circle",
#                     "total_cases": 0.0,
#                     "total_sales_value": 0.0
#                 }
#             depot_stats[d_id]["total_cases"] += s["total_cases"]
#             depot_stats[d_id]["total_sales_value"] += s["sale_value"]

#         top_depots = sorted(list(depot_stats.values()), key=lambda x: x["total_sales_value"], reverse=True)[:5]

#         return {
#             "kpis": kpis,
#             "trends": trends_list,
#             "top_brands": top_brands,
#             "top_depots": top_depots
#         }

# analytics_service = AnalyticsService()

















































from typing import Dict, Any, Optional
from backend.db.client import get_supabase


class AnalyticsService:

    def get_dashboard_overview(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        depot_id: Optional[int] = None,
        circle_id: Optional[int] = None,
    ) -> Dict[str, Any]:

        client = get_supabase()

        if not client:
            raise RuntimeError(
                "Supabase connection is unavailable."
            )

        # =====================================================
        # SALES FACT QUERY
        # =====================================================

        query = (
            client
            .table("sales_fact")
            .select(
                "sale_id,"
                "sale_date,"
                "licensee_id,"
                "brand_id,"
                "packaging_id,"
                "depot_id,"
                "total_case,"
                "total_btl,"
                "total_bl,"
                "batch_id"
            )
        )

        if start_date:
            query = query.gte(
                "sale_date",
                start_date
            )

        if end_date:
            query = query.lte(
                "sale_date",
                end_date
            )

        if depot_id:
            query = query.eq(
                "depot_id",
                depot_id
            )

        response = query.execute()

        sales = response.data or []

        # =====================================================
        # CIRCLE FILTER
        #
        # sales_fact contains depot_id, not circle_id.
        # Therefore find depots belonging to the circle first.
        # =====================================================

        if circle_id:

            depot_response = (
                client
                .table("depots")
                .select("depot_id")
                .eq(
                    "circle_id",
                    circle_id
                )
                .execute()
            )

            circle_depot_ids = {
                row["depot_id"]
                for row in (
                    depot_response.data or []
                )
            }

            sales = [
                sale
                for sale in sales
                if sale.get("depot_id")
                in circle_depot_ids
            ]

        # =====================================================
        # KPI CALCULATIONS
        # =====================================================

        total_cases = sum(
            float(
                sale.get("total_case") or 0
            )
            for sale in sales
        )

        total_bottles = sum(
            float(
                sale.get("total_btl") or 0
            )
            for sale in sales
        )

        total_bulk_liters = sum(
            float(
                sale.get("total_bl") or 0
            )
            for sale in sales
        )

        active_licensees = len({
            sale["licensee_id"]
            for sale in sales
            if sale.get("licensee_id")
            is not None
        })

        active_brands = len({
            sale["brand_id"]
            for sale in sales
            if sale.get("brand_id")
            is not None
        })

        # IMPORTANT:
        #
        # Your current sales_fact table has no monetary
        # sales/revenue column.
        #
        # TOTAL_BL is volume, NOT sales value.
        #
        # Therefore we do not invent a revenue number.
        # =====================================================

        kpis = {
            "total_sales_value": 0.0,

            "total_cases_sold":
                round(total_cases, 2),

            "total_bottles_sold":
                round(total_bottles, 2),

            "total_bulk_liters":
                round(total_bulk_liters, 2),

            "active_licensees_count":
                active_licensees,

            "active_brands_count":
                active_brands,

            # Proper growth calculation can be added
            # once previous-period comparison is defined.
            "growth_percentage": 0.0,
        }

        # =====================================================
        # DAILY TRENDS
        # =====================================================

        trends_dict: Dict[
            str,
            Dict[str, Any]
        ] = {}

        for sale in sales:

            sale_date = sale.get(
                "sale_date"
            )

            if not sale_date:
                continue

            if sale_date not in trends_dict:

                trends_dict[sale_date] = {
                    "sales_date":
                        sale_date,

                    # Kept for compatibility with your
                    # existing response schema.
                    "total_sales":
                        0.0,

                    "total_cases":
                        0.0,

                    "total_bottles":
                        0.0,

                    "total_bulk_liters":
                        0.0,
                }

            trends_dict[
                sale_date
            ][
                "total_cases"
            ] += float(
                sale.get(
                    "total_case"
                ) or 0
            )

            trends_dict[
                sale_date
            ][
                "total_bottles"
            ] += float(
                sale.get(
                    "total_btl"
                ) or 0
            )

            trends_dict[
                sale_date
            ][
                "total_bulk_liters"
            ] += float(
                sale.get(
                    "total_bl"
                ) or 0
            )

        trends_list = sorted(
            trends_dict.values(),
            key=lambda item:
                item["sales_date"]
        )

        # =====================================================
        # LOAD BRANDS
        # =====================================================

        brand_response = (
            client
            .table("brands")
            .select(
                "brand_id,"
                "brand_name"
            )
            .execute()
        )

        brand_lookup = {
            row["brand_id"]: row
            for row in (
                brand_response.data or []
            )
        }

        # =====================================================
        # TOP BRANDS
        #
        # Since there is no sale_value/revenue, ranking is
        # based on TOTAL_BL (bulk litres).
        # =====================================================

        brand_stats: Dict[
            int,
            Dict[str, Any]
        ] = {}

        for sale in sales:

            brand_id = sale.get(
                "brand_id"
            )

            if brand_id is None:
                continue

            if brand_id not in brand_stats:

                brand = brand_lookup.get(
                    brand_id,
                    {}
                )

                brand_stats[
                    brand_id
                ] = {
                    "brand_id":
                        brand_id,

                    "brand_name":
                        brand.get(
                            "brand_name",
                            f"Brand {brand_id}"
                        ),

                    # Old API expected brand_code,
                    # but current DB does not have it.
                    "brand_code":
                        str(brand_id),

                    "total_cases":
                        0.0,

                    "total_sales_value":
                        0.0,

                    "total_bulk_liters":
                        0.0,
                }

            brand_stats[
                brand_id
            ][
                "total_cases"
            ] += float(
                sale.get(
                    "total_case"
                ) or 0
            )

            brand_stats[
                brand_id
            ][
                "total_bulk_liters"
            ] += float(
                sale.get(
                    "total_bl"
                ) or 0
            )

        top_brands = sorted(
            brand_stats.values(),
            key=lambda item:
                item[
                    "total_bulk_liters"
                ],
            reverse=True
        )[:5]

        # =====================================================
        # BRAND MARKET SHARE
        #
        # Here market share means BL volume share.
        # =====================================================

        for brand in top_brands:

            if total_bulk_liters > 0:

                brand[
                    "market_share_percentage"
                ] = round(
                    (
                        brand[
                            "total_bulk_liters"
                        ]
                        / total_bulk_liters
                    )
                    * 100,
                    2
                )

            else:

                brand[
                    "market_share_percentage"
                ] = 0.0

        # =====================================================
        # LOAD DEPOTS + CIRCLES
        # =====================================================

        depot_response = (
            client
            .table("depots")
            .select(
                "depot_id,"
                "name,"
                "circle_id"
            )
            .execute()
        )

        depot_lookup = {
            row["depot_id"]: row
            for row in (
                depot_response.data or []
            )
        }

        circle_response = (
            client
            .table("circles")
            .select(
                "circle_id,"
                "name"
            )
            .execute()
        )

        circle_lookup = {
            row["circle_id"]: row
            for row in (
                circle_response.data or []
            )
        }

        # =====================================================
        # TOP DEPOTS
        # =====================================================

        depot_stats: Dict[
            int,
            Dict[str, Any]
        ] = {}

        for sale in sales:

            sale_depot_id = sale.get(
                "depot_id"
            )

            if sale_depot_id is None:
                continue

            if (
                sale_depot_id
                not in depot_stats
            ):

                depot = depot_lookup.get(
                    sale_depot_id,
                    {}
                )

                depot_circle_id = (
                    depot.get(
                        "circle_id"
                    )
                )

                circle = (
                    circle_lookup.get(
                        depot_circle_id,
                        {}
                    )
                )

                depot_stats[
                    sale_depot_id
                ] = {
                    "depot_id":
                        sale_depot_id,

                    "depot_name":
                        depot.get(
                            "name",
                            f"Depot {sale_depot_id}"
                        ),

                    # Current schema has no depot_code.
                    "depot_code":
                        str(sale_depot_id),

                    "circle_name":
                        circle.get(
                            "name",
                            ""
                        ),

                    "total_cases":
                        0.0,

                    "total_sales_value":
                        0.0,

                    "total_bulk_liters":
                        0.0,
                }

            depot_stats[
                sale_depot_id
            ][
                "total_cases"
            ] += float(
                sale.get(
                    "total_case"
                ) or 0
            )

            depot_stats[
                sale_depot_id
            ][
                "total_bulk_liters"
            ] += float(
                sale.get(
                    "total_bl"
                ) or 0
            )

        top_depots = sorted(
            depot_stats.values(),
            key=lambda item:
                item[
                    "total_bulk_liters"
                ],
            reverse=True
        )[:5]

        # =====================================================
        # FINAL RESPONSE
        # =====================================================

        return {
            "kpis": kpis,
            "trends": trends_list,
            "top_brands": top_brands,
            "top_depots": top_depots,
        }


analytics_service = AnalyticsService()