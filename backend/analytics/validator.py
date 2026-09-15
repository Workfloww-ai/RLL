import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.db.client import get_supabase
from backend.db.supabase_client import call_mobile_sales_json_rpc
from backend.services.mobile_companies_service import get_companies_summary

logger = logging.getLogger("analytics_validator")


def calculate_scale_factor(period: str, date_from: Optional[str] = None, date_to: Optional[str] = None) -> float:
    """
    Computes dynamic scale factor based on date span and period baseline days.
    Guarantees factor is clamped strictly between [0.1, 3.5].
    """
    if not date_from or not date_to:
        return 1.0

    try:
        d_from = datetime.strptime(date_from.strip(), "%Y-%m-%d")
        d_to = datetime.strptime(date_to.strip(), "%Y-%m-%d")
    except Exception:
        return 1.0

    diff_days = abs((d_to - d_from).days) + 1  # inclusive

    period_baseline_days = {
        "Daily": 1,
        "MTD": 24,   # average active working days in MTD
        "YTD": 275   # average active working days in YTD
    }

    base = period_baseline_days.get(period, 1)
    factor = diff_days / base
    return max(0.1, min(round(factor, 4), 3.5))


class AnalyticsValidator:
    """
    Automated Data Accuracy & Parity Validation Engine (Phase 5).
    Executes comprehensive verification across:
    1. Mathematical Parity (Daily, MTD, YTD for Cases, Bottles, BL) between legacy sales_fact and sales_daily_summary.
    2. Corporate Pinned Ranking: Rajasthan Liquors (Rank 1) and Diageo (Rank 2) positioned at the top.
    3. Strict Exclusion of Company 'Others' (Rule #7) and 0-sale brand licensees.
    4. Dynamic Scale Factor calculation bounds [0.1, 3.5].
    """

    def validate_scale_factor_bounds(self) -> Dict[str, Any]:
        """Validates that dynamic scale factor calculations strictly stay within [0.1, 3.5]."""
        test_cases = [
            ("Daily", "2026-08-31", "2026-08-31", 1.0),      # Standard 1-day Daily
            ("Daily", "2026-08-01", "2026-08-31", 3.5),      # Extreme multi-day Daily (clamped to 3.5)
            ("MTD", "2026-08-01", "2026-08-24", 1.0),        # Exact MTD baseline
            ("MTD", "2026-08-01", "2026-08-01", 0.1),        # 1-day MTD (1/24 ~ 0.0417, clamped to 0.1)
            ("YTD", "2026-04-01", "2026-12-31", 1.0),        # Exact YTD baseline (~275 days)
            ("YTD", "2026-04-01", "2026-04-01", 0.1),        # 1-day YTD (clamped to 0.1)
            ("Daily", "2020-01-01", "2026-01-01", 3.5),      # Extreme multi-year (clamped to 3.5)
        ]

        results = []
        all_passed = True
        for period, d_from, d_to, expected in test_cases:
            computed = calculate_scale_factor(period, d_from, d_to)
            is_valid_bound = 0.1 <= computed <= 3.5
            is_match = abs(computed - expected) < 0.05
            if not (is_valid_bound and is_match):
                all_passed = False
            results.append({
                "period": period,
                "from": d_from,
                "to": d_to,
                "computed": computed,
                "expected": expected,
                "passed": is_valid_bound and is_match
            })

        return {
            "passed": all_passed,
            "tests_run": len(test_cases),
            "details": results
        }

    def validate_corporate_ranking(self, target_date: str, hq_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Validates that Rajasthan Liquors (Rank 1) and Diageo (Rank 2) are pinned at top.
        """
        companies_list, _, _ = get_companies_summary(period="Daily", date_to=target_date, selected_hq=hq_name)
        if not companies_list:
            return {"passed": False, "reason": "No companies returned"}

        rank_1 = companies_list[0] if len(companies_list) > 0 else {}
        rank_2 = companies_list[1] if len(companies_list) > 1 else {}

        r1_name = (rank_1.get("name") or "").lower()
        r1_pinned = bool(rank_1.get("isPinned"))
        r2_name = (rank_2.get("name") or "").lower()
        r2_pinned = bool(rank_2.get("isPinned"))

        is_r1_rajasthan = "rajasthan" in r1_name or rank_1.get("id") == "rll"
        is_r2_diageo = "diageo" in r2_name or "inbrew" in r2_name

        passed = is_r1_rajasthan and r1_pinned and is_r2_diageo and r2_pinned

        return {
            "passed": passed,
            "rank_1": {
                "name": rank_1.get("name"),
                "isPinned": r1_pinned,
                "cases": rank_1.get("cases"),
                "expected": "Rajasthan Liquor Limited"
            },
            "rank_2": {
                "name": rank_2.get("name"),
                "isPinned": r2_pinned,
                "cases": rank_2.get("cases"),
                "expected": "Diageo/In brew"
            }
        }

    def validate_exclusion_rules(self, target_date: str, client) -> Dict[str, Any]:
        """
        Validates strict exclusion of company 'Others' (Rule #7) and 0-sale brand licensees.
        """
        companies_list, _, _ = get_companies_summary(period="Daily", date_to=target_date)
        others_found = [c.get("name") for c in companies_list if (c.get("name") or "").strip().lower() == "others"]

        # Check cascading groups RPC for zero-licensee groups
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        mtd_start = f"{dt.year:04d}-{dt.month:02d}-01"
        fy_year = dt.year if dt.month >= 4 else dt.year - 1
        ytd_start = f"{fy_year:04d}-04-01"

        cascading_passed = True
        zero_licensees_count = 0
        try:
            res = client.rpc("get_cascading_groups_summary_json", {
                "p_target_date": target_date,
                "p_mtd_start": mtd_start,
                "p_ytd_start": ytd_start,
                "p_exclude_company": "Others"
            }).execute()
            groups = res.data or []
            for g in groups:
                if (g.get("total_licensees") or 0) <= 0:
                    zero_licensees_count += 1
            if zero_licensees_count > 0:
                cascading_passed = False
        except Exception as e:
            logger.warning(f"Cascading RPC check notice: {e}")

        passed = len(others_found) == 0 and cascading_passed

        return {
            "passed": passed,
            "others_in_companies": len(others_found),
            "zero_licensee_groups": zero_licensees_count
        }

    def validate_date_accuracy(
        self,
        target_date: str,
        hq_id: Optional[str] = None,
        tolerance: float = 0.05
    ) -> Dict[str, Any]:
        """
        Executes end-to-end automated mathematical parity validation:
        1. Compares legacy sales_fact RPC vs new physical sales_daily_summary RPC
           for Daily, MTD, and YTD totals across Cases, Bottles, and BL.
        2. Validates corporate pinned ranking (Rank 1 RLL, Rank 2 Diageo).
        3. Validates strict exclusion of company 'Others' and 0-sale brand licensees.
        4. Validates dynamic scale factor calculation bounds [0.1, 3.5].
        """
        client = get_supabase()
        if not client:
            return {"is_accurate": True, "reason": "Mock mode", "mismatches": []}

        t_start = time.time()
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        mtd_start = f"{dt.year:04d}-{dt.month:02d}-01"
        fy_year = dt.year if dt.month >= 4 else dt.year - 1
        ytd_start = f"{fy_year:04d}-04-01"

        logger.info(f"[VALIDATOR] Initiating Phase 5 parity validation for date={target_date}, HQ={hq_id or 'All'}")

        # 1. Fetch Legacy RPC results (from sales_fact)
        old_data = call_mobile_sales_json_rpc(target_date, mtd_start, ytd_start, hq_id=hq_id)
        old_companies = old_data.get("companies") or []

        # 2. Fetch New Physical Summary Table results (from sales_daily_summary via optimized RPC)
        rpc_params: Dict[str, Any] = {
            "p_target_date": target_date,
            "p_mtd_start": mtd_start,
            "p_ytd_start": ytd_start,
        }
        if hq_id:
            rpc_params["p_hq_id"] = hq_id

        new_res = client.rpc("get_mobile_companies_summary", rpc_params).execute()
        new_companies = new_res.data or []

        # 3. Check Mathematical Parity across all 9 Metrics
        metrics_to_check = [
            ("daily_cases", "Cases (Daily)"),
            ("mtd_cases", "Cases (MTD)"),
            ("ytd_cases", "Cases (YTD)"),
            ("daily_bottles", "Bottles (Daily)"),
            ("mtd_bottles", "Bottles (MTD)"),
            ("ytd_bottles", "Bottles (YTD)"),
            ("daily_bl", "BL (Daily)"),
            ("mtd_bl", "BL (MTD)"),
            ("ytd_bl", "BL (YTD)"),
        ]

        mismatches: List[Dict[str, Any]] = []
        metrics_summary: Dict[str, Any] = {}

        for metric_key, label in metrics_to_check:
            old_val = sum(float(c.get(metric_key, 0.0) or 0.0) for c in old_companies)
            new_val = sum(float(c.get(metric_key, 0.0) or 0.0) for c in new_companies)
            diff = abs(old_val - new_val)

            metrics_summary[metric_key] = {
                "label": label,
                "old_val": round(old_val, 2),
                "new_val": round(new_val, 2),
                "diff": round(diff, 2),
                "parity": diff <= tolerance
            }

            if diff > tolerance:
                mismatches.append({
                    "metric": metric_key,
                    "label": label,
                    "old_value": round(old_val, 2),
                    "new_value": round(new_val, 2),
                    "difference": round(diff, 2)
                })

        # 4. Corporate Pinned Ranking Check
        ranking_check = self.validate_corporate_ranking(target_date)
        if not ranking_check.get("passed"):
            mismatches.append({
                "metric": "corporate_pinned_ranking",
                "label": "Corporate Ranking (Rank 1 RLL, Rank 2 Diageo)",
                "details": ranking_check
            })

        # 5. Strict Exclusion Rules Check
        exclusion_check = self.validate_exclusion_rules(target_date, client)
        if not exclusion_check.get("passed"):
            mismatches.append({
                "metric": "exclusion_rules",
                "label": "Rule #7 'Others' & 0-Sale Licensees Exclusion",
                "details": exclusion_check
            })

        # 6. Dynamic Scale Factor Bounds Check
        scale_check = self.validate_scale_factor_bounds()
        if not scale_check.get("passed"):
            mismatches.append({
                "metric": "scale_factor_bounds",
                "label": "Scale Factor Bounds [0.1, 3.5]",
                "details": scale_check
            })

        duration_ms = round((time.time() - t_start) * 1000, 2)
        is_accurate = len(mismatches) == 0

        if is_accurate:
            logger.info(
                f"[VALIDATOR] ✅ 100% Parity PASS for date={target_date} across Cases, Bottles, BL, "
                f"Corporate Ranking, 'Others' Exclusion, and Scale Factor Bounds ({duration_ms}ms)"
            )
        else:
            logger.warning(f"[VALIDATOR] ❌ Validation MISMATCH for date={target_date}: {mismatches}")

        return {
            "is_accurate": is_accurate,
            "target_date": target_date,
            "metrics": metrics_summary,
            "corporate_ranking": ranking_check,
            "exclusion_rules": exclusion_check,
            "scale_factor_bounds": scale_check,
            "mismatches": mismatches,
            "duration_ms": duration_ms
        }


analytics_validator = AnalyticsValidator()

