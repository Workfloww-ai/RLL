from typing import Dict, Any, List, Optional
from datetime import datetime, date
from backend.services.import_pipeline import sales_db, dashboard_summary_db
from backend.services.master_service import master_service

class AnalyticsService:

    def get_dashboard_overview(
        self, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None,
        depot_id: Optional[int] = None,
        circle_id: Optional[int] = None
    ) -> Dict[str, Any]:
        
        filtered_sales = sales_db.copy()

        if start_date:
            filtered_sales = [s for s in filtered_sales if s["sales_date"] >= start_date]
        if end_date:
            filtered_sales = [s for s in filtered_sales if s["sales_date"] <= end_date]
        if depot_id:
            filtered_sales = [s for s in filtered_sales if s["depot_id"] == depot_id]

        total_sales_value = sum(s["sale_value"] for s in filtered_sales)
        total_cases_sold = sum(s["total_cases"] for s in filtered_sales)
        total_bottles_sold = sum(s["total_bottles"] for s in filtered_sales)
        total_bulk_liters = sum(s["total_bulk_liters"] for s in filtered_sales)
        active_licensees = len(set(s["licensee_id"] for s in filtered_sales))
        active_brands = len(set(s["brand_id"] for s in filtered_sales))

        kpis = {
            "total_sales_value": round(total_sales_value, 2),
            "total_cases_sold": round(total_cases_sold, 2),
            "total_bottles_sold": round(total_bottles_sold, 2),
            "total_bulk_liters": round(total_bulk_liters, 2),
            "active_licensees_count": active_licensees,
            "active_brands_count": active_brands,
            "growth_percentage": 12.5 # Mock growth metric for dashboard
        }

        # Daily trends
        trends_dict: Dict[str, Dict[str, Any]] = {}
        for s in filtered_sales:
            s_date = s["sales_date"]
            if s_date not in trends_dict:
                trends_dict[s_date] = {
                    "sales_date": s_date,
                    "total_sales": 0.0,
                    "total_cases": 0.0,
                    "total_bottles": 0.0
                }
            trends_dict[s_date]["total_sales"] += s["sale_value"]
            trends_dict[s_date]["total_cases"] += s["total_cases"]
            trends_dict[s_date]["total_bottles"] += s["total_bottles"]

        trends_list = sorted(list(trends_dict.values()), key=lambda x: x["sales_date"])

        # Top Brands
        brand_lookup = {b["brand_id"]: b for b in master_service.get_brands()}
        brand_stats: Dict[int, Dict[str, Any]] = {}
        for s in filtered_sales:
            b_id = s["brand_id"]
            if b_id not in brand_stats:
                b_info = brand_lookup.get(b_id, {"brand_name": f"Brand {b_id}", "brand_code": f"B{b_id}"})
                brand_stats[b_id] = {
                    "brand_id": b_id,
                    "brand_name": b_info["brand_name"],
                    "brand_code": b_info["brand_code"],
                    "total_cases": 0.0,
                    "total_sales_value": 0.0
                }
            brand_stats[b_id]["total_cases"] += s["total_cases"]
            brand_stats[b_id]["total_sales_value"] += s["sale_value"]

        top_brands = sorted(list(brand_stats.values()), key=lambda x: x["total_sales_value"], reverse=True)[:5]
        for tb in top_brands:
            tb["market_share_percentage"] = round((tb["total_sales_value"] / total_sales_value * 100), 2) if total_sales_value > 0 else 0.0

        # Top Depots
        depot_lookup = {d["depot_id"]: d for d in master_service.get_depots()}
        depot_stats: Dict[int, Dict[str, Any]] = {}
        for s in filtered_sales:
            d_id = s["depot_id"]
            if d_id not in depot_stats:
                d_info = depot_lookup.get(d_id, {"depot_name": f"Depot {d_id}", "depot_code": f"D{d_id}"})
                depot_stats[d_id] = {
                    "depot_id": d_id,
                    "depot_name": d_info["depot_name"],
                    "depot_code": d_info["depot_code"],
                    "circle_name": "Jaipur Circle",
                    "total_cases": 0.0,
                    "total_sales_value": 0.0
                }
            depot_stats[d_id]["total_cases"] += s["total_cases"]
            depot_stats[d_id]["total_sales_value"] += s["sale_value"]

        top_depots = sorted(list(depot_stats.values()), key=lambda x: x["total_sales_value"], reverse=True)[:5]

        return {
            "kpis": kpis,
            "trends": trends_list,
            "top_brands": top_brands,
            "top_depots": top_depots
        }

analytics_service = AnalyticsService()
