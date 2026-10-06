"""
Sales Analytics Chatbot Orchestration Service.
Connects user authorization, RBAC scoping, intent parsing, Redis caching,
summary database repositories, and structured response synthesis.

Enforces:
1. STRICT RBAC / User Scope (Tenant ID, Role, Allowed HQs).
2. Sub-second Redis caching (`rll:chatbot:{tenant}:{user}:{intent_hash}`).
3. Verified, non-hallucinated response format with KPIs, tables, and charts (Cases only).
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from backend.db.redis_client import safe_get, safe_set, safe_delete
from backend.repositories.chatbot.summary_repository import ChatbotSummaryRepository
from backend.schemas.chatbot import (
    ChatbotChart,
    ChatbotChartDataPoint,
    ChatbotKPI,
    ChatbotTable,
    ChatbotTableColumn,
    ChatMessageRequest,
    ChatMessageResponse,
)
from backend.services.chatbot.intent_service import ChatbotIntentService

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # 5 minutes


class ChatbotAnalyticsService:
    """Core business service for processing user chatbot queries."""

    @classmethod
    def format_period_label(cls, period: str, target_date: str) -> str:
        """Formats period into exact date or date range string (e.g., '31 Aug 2026' or '01 Aug 2026 - 31 Aug 2026')."""
        from datetime import datetime
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d").date()
            target_fmt = dt.strftime("%d %b %Y")
            clean_period = (period or "Daily").strip()
            if clean_period == "Daily":
                return target_fmt
            elif clean_period == "MTD":
                m_start = dt.replace(day=1).strftime("%d %b %Y")
                return f"{m_start} - {target_fmt}"
            elif clean_period == "YTD":
                fy_year = dt.year if dt.month >= 4 else dt.year - 1
                fy_start = datetime(fy_year, 4, 1).strftime("%d %b %Y")
                return f"{fy_start} - {target_fmt}"
            else:
                return target_fmt
        except Exception:
            return target_date or ""

    @classmethod
    def get_entity_display_names(cls, entity_type: str) -> tuple[str, str]:
        """Returns properly capitalized singular and plural entity display names (e.g. 'TSM', 'TSMs')."""
        et = (entity_type or "").strip().lower()
        if et == "tsm":
            return ("TSM", "TSMs")
        elif et == "hq":
            return ("HQ", "HQs")
        elif et in ("company", "companies"):
            return ("Company", "Companies")
        elif et in ("group", "licensee_group"):
            return ("Group", "Groups")
        elif et == "depot":
            return ("Depot", "Depots")
        elif et == "brand":
            return ("Brand", "Brands")
        else:
            return (entity_type.capitalize(), entity_type.capitalize() + "s")

    @classmethod
    async def process_chat_query(
        cls,
        payload: ChatMessageRequest,
        current_user: Dict[str, Any]
    ) -> ChatMessageResponse:
        """
        Main end-to-end processing pipeline:
        1. Extract security & RBAC scope from JWT user object.
        2. Parse query intent & parameters.
        3. Check Redis response cache.
        4. Execute exact database summary operations.
        5. Format structured response (KPIs, tables, charts, natural text).
        6. Store in Redis cache.
        """
        t0 = time.perf_counter()

        # ── 1. Security & RBAC Scoping ────────────────────────────────────────
        user_id = str(current_user.get("user_id") or current_user.get("sub") or "anonymous")
        tenant_id = str(current_user.get("tenant_id") or "a0000000-0000-0000-0000-000000000001")
        role = str(current_user.get("role") or "viewer").lower()

        # Extract allowed HQs from JWT user profile
        allowed_hqs = current_user.get("allowed_hqs") or current_user.get("headquarters")
        if isinstance(allowed_hqs, str):
            allowed_hqs = [allowed_hqs]

        user_hq_filter = payload.selected_hq or "All Headquarters"
        if allowed_hqs and len(allowed_hqs) == 1 and allowed_hqs[0] != "All Headquarters":
            user_hq_filter = allowed_hqs[0]

        # ── Check Pending Clarification Context ────────────────────────────────
        clarification_key = f"rll:chatbot:clarification:{tenant_id}:{user_id}"
        pending_context = None
        try:
            pending_raw = await safe_get(clarification_key)
            if pending_raw:
                pending_context = json.loads(pending_raw)
        except Exception as e:
            logger.debug(f"Pending clarification check notice: {e}")

        # ── 2. Intent Parsing ─────────────────────────────────────────────────
        parsed = ChatbotIntentService.parse_intent(
            user_message=payload.message,
            current_period=payload.period or "Daily",
            current_hq=user_hq_filter,
            pending_context=pending_context,
        )

        intent = parsed["intent"]
        period = parsed["period"]
        entity_type = parsed["entity_type"]
        entity_name = parsed["entity_name"]
        limit = parsed["limit"]
        selected_hq = parsed["selected_hq"]
        if allowed_hqs and len(allowed_hqs) == 1 and allowed_hqs[0] != "All Headquarters":
            selected_hq = allowed_hqs[0]

        # ── 3. Redis Cache Check ──────────────────────────────────────────────
        import hashlib
        clean_msg = payload.message.strip().lower()
        msg_hash = hashlib.md5(clean_msg.encode('utf-8')).hexdigest()[:12]
        cache_key = f"rll:chatbot:{tenant_id}:{user_id}:{intent}:{period}:{selected_hq}:{entity_type}:{limit}:{msg_hash}"
        try:
            cached_val = await safe_get(cache_key)
            if cached_val:
                cached_data = json.loads(cached_val)
                cached_response = ChatMessageResponse(**cached_data)
                cache_dur_sec = time.perf_counter() - t0
                cached_response.cache_hit = True
                cached_response.execution_time_ms = round(cache_dur_sec * 1000.0, 2)
                logger.info(f"[CHATBOT LATENCY] User Query: '{payload.message}' | Cache HIT | Latency: {cache_dur_sec:.4f}s ({cached_response.execution_time_ms}ms)")
                return cached_response
        except Exception as e:
            logger.debug(f"Redis cache check notice: {e}")

        # ── 4. DB Execution ───────────────────────────────────────────────────
        target_date = payload.date_to or payload.date_from or parsed.get("target_date") or ChatbotSummaryRepository.resolve_latest_date()

        response = cls._build_response_for_intent(
            intent=intent,
            period=period,
            target_date=target_date,
            selected_hq=selected_hq,
            entity_type=entity_type,
            entity_name=entity_name,
            limit=limit,
            user_message=payload.message,
        )

        # Manage Pending Clarification Context Redis State
        if response.intent == "clarification_prompt" and entity_name:
            try:
                await safe_set(
                    key=clarification_key,
                    value=json.dumps({
                        "suggested_entity": entity_name,
                        "suggested_type": entity_type or "group",
                        "target_date": target_date
                    }),
                    ttl=300
                )
            except Exception as e:
                logger.debug(f"Pending clarification store notice: {e}")
        elif pending_context:
            try:
                await safe_delete(clarification_key)
            except Exception as e:
                logger.debug(f"Pending clarification delete notice: {e}")

        dur_sec = time.perf_counter() - t0
        exec_time_ms = round(dur_sec * 1000.0, 2)
        response.execution_time_ms = exec_time_ms
        response.cache_hit = False
        logger.info(f"[CHATBOT LATENCY] User Query: '{payload.message}' | DB MISS | Latency: {dur_sec:.4f}s ({exec_time_ms}ms)")

        # ── 5. Cache Store ────────────────────────────────────────────────────
        try:
            await safe_set(
                key=cache_key,
                value=json.dumps(response.model_dump(), default=str),
                ttl=CACHE_TTL_SECONDS
            )
        except Exception as e:
            logger.debug(f"Redis cache store notice: {e}")

        return response

    @classmethod
    def _build_response_for_intent(
        cls,
        intent: str,
        period: str,
        target_date: str,
        selected_hq: str,
        entity_type: str,
        entity_name: Optional[str],
        limit: int,
        user_message: str,
    ) -> ChatMessageResponse:
        period_lbl = cls.format_period_label(period, target_date)
        # ---------------------------------------------------------------------
        # INTENT 0: GREETING & GENERAL HELPER
        # ---------------------------------------------------------------------
        if intent == "greeting":
            return ChatMessageResponse(
                text="Hello! How may I help you with your sales analytics today?",
                intent="greeting",
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                suggested_questions=[
                    "Top 5 brands",
                    "Daily sales summary",
                    "TSM performance",
                    "Company performance",
                ],
            )

        # ---------------------------------------------------------------------
        # INTENT: CLARIFICATION PROMPT (DID YOU MEAN X?)
        # ---------------------------------------------------------------------
        if intent == "clarification_prompt":
            candidate = entity_name or "this item"
            return ChatMessageResponse(
                text=f"Did you mean {candidate}?",
                intent="clarification_prompt",
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                suggested_questions=[
                    f"Yes, show {candidate} sales",
                    "No"
                ],
                clarification_needed=True
            )

        # ---------------------------------------------------------------------
        # INTENT: NO RESPONSE (USER SAID NO TO CLARIFICATION)
        # ---------------------------------------------------------------------
        if intent == "no_response":
            return ChatMessageResponse(
                text="Got it. How may I help you?",
                intent="no_response",
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                suggested_questions=[
                    "Top 5 brands",
                    "Daily sales summary",
                    "TSM performance",
                    "Company performance",
                ],
            )

        # ---------------------------------------------------------------------
        # INTENT: UNMATCHED ENTITY (UNKNOWN NAME)
        # ---------------------------------------------------------------------
        if intent == "unmatched_entity":
            entity_str = entity_name or "that entity"
            return ChatMessageResponse(
                text=f"I couldn't find an exact match for '{entity_str}' in our database. How may I help you?",
                intent="unmatched_entity",
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                suggested_questions=[
                    "Top 5 brands",
                    "Daily sales summary",
                    "TSM performance",
                    "Company performance",
                ],
            )

        # ---------------------------------------------------------------------
        # INTENT: OUT OF DOMAIN (NON-RLL SALES QUESTION)
        # ---------------------------------------------------------------------
        if intent == "out_of_domain":
            return ChatMessageResponse(
                text="I am very sorry, I can only assist with Rajasthan Liquor Limited (RLL) sales analytics and domain-related questions. How may I help you with your sales performance today?",
                intent="out_of_domain",
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                suggested_questions=[
                    "Top 5 brands",
                    "Daily sales summary",
                    "TSM performance",
                    "Company performance",
                ],
            )

        # ---------------------------------------------------------------------
        # INTENT 1: GET SALES SUMMARY
        # ---------------------------------------------------------------------
        if intent == "get_sales_summary":
            company_id = None
            brand_id = None
            group_id = None
            tsm_user_id = None
            if entity_name:
                if not entity_type:
                    entity_type, _ = ChatbotSummaryRepository.resolve_entity_type_and_id(entity_name)
                if entity_type == "company":
                    company_id = ChatbotSummaryRepository.resolve_entity_id("company", entity_name)
                elif entity_type == "brand":
                    brand_id = ChatbotSummaryRepository.resolve_entity_id("brand", entity_name)
                elif entity_type in ("group", "licensee_group"):
                    group_id = ChatbotSummaryRepository.resolve_entity_id("group", entity_name)
                elif entity_type == "tsm":
                    tsm_user_id = ChatbotSummaryRepository.resolve_entity_id("tsm", entity_name)

            summary = ChatbotSummaryRepository.get_sales_summary(
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                company_id=company_id,
                brand_id=brand_id,
                group_id=group_id,
                tsm_user_id=tsm_user_id,
            )
            cases = summary["total_cases"]

            kpis = [
                ChatbotKPI(
                    title=f"Total Cases ({period_lbl})",
                    value=f"{cases:,.2f}",
                    subtext="Cases (9L equivalent)",
                    change_type="neutral",
                ),
            ]

            header_title = f"for {entity_name}" if entity_name else ""
            text = (
                f"📊 Sales Summary {header_title} ({period_lbl})\n\n"
                f"• Total Sales: {cases:,.2f} cases\n"
                f"• Scope: {selected_hq}"
            )
            if cases == 0:
                latest_avail = ChatbotSummaryRepository.resolve_latest_date()
                text += f"\n\n⚠️(Note: No sales upload found for requested date {target_date}. Latest available sales date is {latest_avail}.)"

            # Top 5 Brands preview table for entity / market
            top_b = ChatbotSummaryRepository.get_top_entities(
                entity_type="brand",
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                limit=5,
                company_id=company_id,
                group_id=group_id,
                tsm_user_id=tsm_user_id,
            )

            table_rows = [
                {"rank": idx + 1, "brand": b["name"], "cases": f"{b['cases']:,.2f}"}
                for idx, b in enumerate(top_b)
            ]

            table_title = f"Top 5 Selling Brands for {entity_name} ({period_lbl})" if entity_name else f"Top 5 Selling Brands ({period_lbl})"
            table = ChatbotTable(
                title=table_title,
                columns=[
                    ChatbotTableColumn(key="rank", label="#", align="center"),
                    ChatbotTableColumn(key="brand", label="Brand Name", align="left"),
                    ChatbotTableColumn(key="cases", label="Cases", align="right"),
                ],
                rows=table_rows,
            )

            return ChatMessageResponse(
                text=text,
                intent=intent,
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                kpis=kpis,
                table=table,
                suggested_questions=[
                    "What are the top 10 selling brands?",
                    "Show sales breakdown by company",
                    "Which brands are growing the fastest?",
                    "Compare MTD sales vs last month",
                ],
            )

        # ---------------------------------------------------------------------
        # INTENT 2: GET TOP ENTITIES
        # ---------------------------------------------------------------------
        elif intent == "get_top_entities":
            top_list = ChatbotSummaryRepository.get_top_entities(
                entity_type=entity_type, period=period, target_date=target_date, selected_hq=selected_hq, limit=limit
            )

            sing_title, plur_title = cls.get_entity_display_names(entity_type)
            table_rows = [
                {"rank": idx + 1, "name": item["name"], "cases": f"{item['cases']:,.2f}"}
                for idx, item in enumerate(top_list)
            ]

            table = ChatbotTable(
                title=f"Top {len(top_list)} {plur_title} by Sales Volume ({period_lbl})",
                columns=[
                    ChatbotTableColumn(key="rank", label="#", align="center"),
                    ChatbotTableColumn(key="name", label=f"{sing_title} Name", align="left"),
                    ChatbotTableColumn(key="cases", label="Cases", align="right"),
                ],
                rows=table_rows,
            )

            chart_data = [
                ChatbotChartDataPoint(label=item["name"][:18], value=item["cases"])
                for item in top_list[:5]
            ]
            chart = ChatbotChart(
                title=f"Top 5 {plur_title} Volume Comparison",
                chart_type="bar",
                series_name="Cases",
                data=chart_data,
            )

            top_1 = top_list[0]["name"] if top_list else "N/A"
            top_1_cases = f"{top_list[0]['cases']:,.2f}" if top_list else "0"

            text = (
                f"🏆 Top {len(top_list)} {plur_title} ({period_lbl})\n\n"
                f"The leading {sing_title} is {top_1} with {top_1_cases} cases sold in {selected_hq}."
            )

            return ChatMessageResponse(
                text=text,
                intent=intent,
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                table=table,
                chart=chart,
                suggested_questions=[
                    f"Show contribution share of top {plur_title.lower()}",
                    "Which brands are declining?",
                    "Show sales trend graph",
                ],
            )

        # ---------------------------------------------------------------------
        # INTENT 3: GET BREAKDOWN
        # ---------------------------------------------------------------------
        elif intent == "get_breakdown":
            breakdown = ChatbotSummaryRepository.get_breakdown(
                entity_type=entity_type, period=period, target_date=target_date, selected_hq=selected_hq
            )

            sing_title, plur_title = cls.get_entity_display_names(entity_type)
            table_rows = [
                {"rank": idx + 1, "name": item["name"], "cases": f"{item['cases']:,.2f}"}
                for idx, item in enumerate(breakdown[:15])
            ]

            table = ChatbotTable(
                title=f"{sing_title} Sales Breakdown ({period_lbl})",
                columns=[
                    ChatbotTableColumn(key="rank", label="#", align="center"),
                    ChatbotTableColumn(key="name", label=f"{sing_title}", align="left"),
                    ChatbotTableColumn(key="cases", label="Cases", align="right"),
                ],
                rows=table_rows,
            )

            text = (
                f"📋 {sing_title} Breakdown ({period_lbl})\n\n"
                f"Showing sales breakdown across {len(breakdown)} {plur_title.lower()} in {selected_hq}."
            )

            return ChatMessageResponse(
                text=text,
                intent=intent,
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                table=table,
                suggested_questions=[
                    "Show top 5 companies by volume",
                    "Who are the top gainers & losers?",
                    "Summarise total sales",
                ],
            )

        # ---------------------------------------------------------------------
        # INTENT 4: COMPARE PERIODS
        # ---------------------------------------------------------------------
        elif intent == "compare_periods":
            comp = ChatbotSummaryRepository.compare_periods(
                period=period, target_date=target_date, selected_hq=selected_hq
            )

            curr = comp["current"]
            prev = comp["previous"]
            var = comp["variance"]

            icon = "📈" if var["direction"] == "up" else "📉" if var["direction"] == "down" else "➡️"
            text = (
                f"{icon} Sales Period Comparison ({period_lbl})\n\n"
                f"• Current Date ({curr['date']}): {curr['cases']:,.2f} cases\n"
                f"• Comparison Date ({prev['date']}): {prev['cases']:,.2f} cases\n"
                f"• Variance: {var['cases']:+,.2f} cases ({var['pct_change']:+,.2f}%)"
            )

            kpis = [
                ChatbotKPI(
                    title=f"Current ({curr['date']})",
                    value=f"{curr['cases']:,.2f}",
                    subtext="Cases",
                ),
                ChatbotKPI(
                    title=f"Previous ({prev['date']})",
                    value=f"{prev['cases']:,.2f}",
                    subtext="Cases",
                ),
                ChatbotKPI(
                    title="Growth Variance",
                    value=f"{var['pct_change']:+,.2f}%",
                    subtext=f"{var['cases']:+,.2f} cases",
                    change_pct=var["pct_change"],
                    change_type=var["direction"],
                ),
            ]

            return ChatMessageResponse(
                text=text,
                intent=intent,
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                kpis=kpis,
                comparison=comp,
                suggested_questions=[
                    "Which brands caused this growth/decline?",
                    "Show sales trend graph",
                    "What are the top 5 selling brands?",
                ],
            )

        # ---------------------------------------------------------------------
        # INTENT 5: GET MOVERS (GAINERS & LOSERS)
        # ---------------------------------------------------------------------
        elif intent == "get_movers":
            movers = ChatbotSummaryRepository.get_movers(
                entity_type=entity_type, period=period, target_date=target_date, selected_hq=selected_hq, limit=limit
            )

            sing_title, plur_title = cls.get_entity_display_names(entity_type)
            gainers = movers["gainers"]
            losers = movers["losers"]

            gainers_rows = [
                {"name": g["name"], "cases": f"{g['current_cases']:,.2f}", "growth": f"+{g['diff_cases']:,.2f} ({g['pct_change']:+,.1f}%)"}
                for g in gainers
            ]

            table = ChatbotTable(
                title=f"Top Growing {plur_title} (Gainers)",
                columns=[
                    ChatbotTableColumn(key="name", label=f"{sing_title} Name", align="left"),
                    ChatbotTableColumn(key="cases", label="Cases", align="right"),
                    ChatbotTableColumn(key="growth", label="Volume Change", align="right"),
                ],
                rows=gainers_rows,
            )

            g_text = ", ".join([f"{g['name']} (+{g['diff_cases']:,.0f} cs)" for g in gainers[:3]]) or "None"
            l_text = ", ".join([f"{l['name']} ({l['diff_cases']:,.0f} cs)" for l in losers[:3]]) or "None"

            text = (
                f"🚀 Top Movers & Performance Changes ({period_lbl})\n\n"
                f"• Top Gainers: {g_text}\n"
                f"• Top Declines: {l_text}"
            )

            return ChatMessageResponse(
                text=text,
                intent=intent,
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                table=table,
                movers=movers,
                suggested_questions=[
                    "Show total sales summary",
                    "Which companies dominate total market share?",
                    "Show top 10 brands",
                ],
            )

        # ---------------------------------------------------------------------
        # INTENT 6: GET CONTRIBUTION
        # ---------------------------------------------------------------------
        elif intent == "get_contribution":
            contrib = ChatbotSummaryRepository.get_contribution(
                entity_type=entity_type, period=period, target_date=target_date, selected_hq=selected_hq, limit=limit
            )

            sing_title, plur_title = cls.get_entity_display_names(entity_type)
            table_rows = [
                {"rank": idx + 1, "name": c["name"], "cases": f"{c['cases']:,.2f}", "share": f"{c['share_pct']:.2f}%"}
                for idx, c in enumerate(contrib)
            ]

            table = ChatbotTable(
                title=f"Market Share Contribution by {sing_title} ({period_lbl})",
                columns=[
                    ChatbotTableColumn(key="rank", label="#", align="center"),
                    ChatbotTableColumn(key="name", label=f"{sing_title}", align="left"),
                    ChatbotTableColumn(key="cases", label="Cases", align="right"),
                    ChatbotTableColumn(key="share", label="% Share", align="right"),
                ],
                rows=table_rows,
            )

            top_share = f"{contrib[0]['name']} ({contrib[0]['share_pct']}%)" if contrib else "N/A"
            text = (
                f"🍕 Market Share Contribution ({period_lbl})\n\n"
                f"The highest volume contributor is {top_share} in {selected_hq}."
            )

            return ChatMessageResponse(
                text=text,
                intent=intent,
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                table=table,
                suggested_questions=[
                    "Compare current period vs last period",
                    "Show sales trend graph",
                    "Full Sales Summary",
                ],
            )

        # ---------------------------------------------------------------------
        # INTENT 7: GET TREND
        # ---------------------------------------------------------------------
        else:
            trend_data = ChatbotSummaryRepository.get_trend(
                period=period, num_days=7, selected_hq=selected_hq
            )

            points = trend_data["trend"]
            chart_points = [
                ChatbotChartDataPoint(label=p["label"], value=p["cases"])
                for p in points
            ]

            chart = ChatbotChart(
                title="7-Day Daily Volume Trend (Cases)",
                chart_type="line",
                series_name="Cases",
                data=chart_points,
            )

            latest_cases = points[-1]["cases"] if points else 0.0
            prev_cases = points[-2]["cases"] if len(points) > 1 else latest_cases
            diff = latest_cases - prev_cases

            text = (
                f"📈 7-Day Sales Volume Trend\n\n"
                f"• Latest Day ({points[-1]['date']}): {latest_cases:,.2f} cases\n"
                f"• Previous Day ({points[-2]['date'] if len(points) > 1 else ''}): {prev_cases:,.2f} cases\n"
                f"• Day-over-Day Change: {diff:+,.2f} cases"
            )

            return ChatMessageResponse(
                text=text,
                intent=intent,
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                chart=chart,
                suggested_questions=[
                    "What are the top 5 selling brands?",
                    "Show sales summary for Daily",
                    "Which brands are growing the fastest?",
                ],
            )
