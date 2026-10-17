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
    ChatbotQuickReply,
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
        elif et in ("ase", "tsm_ase"):
            return ("ASE", "ASEs")
        elif et == "licensee":
            return ("Outlet", "Outlets")
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
        2. Parse query intent & parameters (supports explicit quick replies & fuzzy entity resolution).
        3. Check Redis response cache.
        4. Execute exact database summary operations.
        5. Format structured response (KPIs, tables, charts, natural text, quick-reply chips).
        6. Store in Redis cache.
        """
        t0 = time.perf_counter()

        # ── 1. Security & RBAC Scoping ────────────────────────────────────────
        user_id = str(current_user.get("user_id") or current_user.get("sub") or "anonymous")
        tenant_id = str(current_user.get("tenant_id") or "")
        if not tenant_id and user_id and user_id != "anonymous":
            client = get_supabase_client()
            if client:
                try:
                    u_res = client.table("users").select("tenant_id").eq("user_id", user_id).limit(1).execute()
                    if u_res.data and u_res.data[0].get("tenant_id"):
                        tenant_id = str(u_res.data[0]["tenant_id"])
                except Exception:
                    pass
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
            explicit_entity_type=payload.entity_type,
            explicit_entity_id=payload.entity_id,
        )

        intent = parsed["intent"]
        period = parsed["period"]
        entity_type = parsed["entity_type"]
        entity_name = parsed["entity_name"]
        entity_id = parsed.get("entity_id")
        candidate_matches = parsed.get("candidate_matches")
        limit = parsed["limit"]
        selected_hq = parsed["selected_hq"]
        if allowed_hqs and len(allowed_hqs) == 1 and allowed_hqs[0] != "All Headquarters":
            selected_hq = allowed_hqs[0]

        # ── 3. Redis Cache Check ──────────────────────────────────────────────
        import hashlib
        clean_msg = payload.message.strip().lower()
        msg_hash = hashlib.md5(f"{clean_msg}:{payload.entity_type}:{payload.entity_id}".encode('utf-8')).hexdigest()[:12]
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
            entity_id=entity_id,
            candidate_matches=candidate_matches,
            limit=limit,
            user_message=payload.message,
        )

        # Manage Pending Clarification Context Redis State
        if response.intent in ("clarification_prompt", "disambiguation_prompt") and entity_name:
            try:
                await safe_set(
                    key=clarification_key,
                    value=json.dumps({
                        "suggested_entity": entity_name,
                        "suggested_type": entity_type or "licensee",
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
        entity_id: Optional[str] = None,
        candidate_matches: Optional[List[Dict[str, Any]]] = None,
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
        # INTENT: DISAMBIGUATION PROMPT (ZOMATO-STYLE QUICK CLICK OPTIONS)
        # ---------------------------------------------------------------------
        if intent == "disambiguation_prompt":
            matches = candidate_matches or []
            entity_label = "options"
            if matches:
                first_type = matches[0].get("entity_type")
                entity_label = "outlets" if first_type == "licensee" else "sales executives (ASE)" if first_type == "ase" else "records"

            clean_q = entity_name or "your query"
            target_date_label = cls.format_period_label(period, target_date)
            date_suffix = f" on {target_date_label}" if target_date_label else ""

            # Ensure every candidate is checked against actual sales in this period
            if matches and any("cases" not in m for m in matches):
                matches = ChatbotSummaryRepository.enrich_candidates_with_period_sales(
                    matches,
                    period=period,
                    target_date=target_date,
                    selected_hq=selected_hq,
                )

            candidate_groups = [m for m in matches if m.get("entity_type") == "group"]
            candidate_licensees = [m for m in matches if m.get("entity_type") == "licensee"]
            candidate_ases = [m for m in matches if m.get("entity_type") in ("ase", "tsm_ase")]
            candidate_tsms = [m for m in matches if m.get("entity_type") == "tsm"]

            # STRICT NON-ZERO FILTER FOR LICENSEES:
            # 0.00 cases licensees are NEVER shown as options under any circumstances!
            active_licensees = [lic for lic in candidate_licensees if float(lic.get("cases") or 0.0) > 0.0]

            total_valid_candidates = len(candidate_tsms) + len(candidate_ases) + len(candidate_groups) + len(active_licensees)

            # -----------------------------------------------------------------
            # Case 1: Exactly 1 single matching entity across all types!
            # -----------------------------------------------------------------
            if total_valid_candidates == 1:
                if candidate_tsms:
                    single = candidate_tsms[0]
                    return cls._build_response_for_intent(
                        intent="get_sales_summary",
                        period=period,
                        target_date=target_date,
                        selected_hq=selected_hq,
                        entity_type="tsm",
                        entity_name=single["name"],
                        limit=limit,
                        user_message=user_message,
                        entity_id=single["id"],
                    )
                elif candidate_ases:
                    single = candidate_ases[0]
                    return cls._build_response_for_intent(
                        intent="get_sales_summary",
                        period=period,
                        target_date=target_date,
                        selected_hq=selected_hq,
                        entity_type="ase",
                        entity_name=single["name"],
                        limit=limit,
                        user_message=user_message,
                        entity_id=single["id"],
                    )
                elif candidate_groups:
                    single = candidate_groups[0]
                    return cls._build_response_for_intent(
                        intent="get_sales_summary",
                        period=period,
                        target_date=target_date,
                        selected_hq=selected_hq,
                        entity_type="group",
                        entity_name=single["name"],
                        limit=limit,
                        user_message=user_message,
                        entity_id=single["id"],
                    )
                elif active_licensees:
                    single = active_licensees[0]
                    return cls._build_response_for_intent(
                        intent="get_sales_summary",
                        period=period,
                        target_date=target_date,
                        selected_hq=selected_hq,
                        entity_type="licensee",
                        entity_name=single["name"],
                        limit=limit,
                        user_message=user_message,
                        entity_id=single["id"],
                    )

            # -----------------------------------------------------------------
            # Case 2: Multiple matching entities (mixed or same type)
            # -----------------------------------------------------------------
            if total_valid_candidates > 1:
                quick_replies: List[ChatbotQuickReply] = []

                # 1. TSM options (up to 3)
                for t in candidate_tsms[:3]:
                    quick_replies.append(
                        ChatbotQuickReply(
                            label=t['name'],
                            value=f"{t['name']} sales{date_suffix}".strip(),
                            entity_type="tsm",
                            entity_id=t.get("id"),
                            subtext=t.get("subtext") or "Territory Sales Manager",
                        )
                    )

                # 2. ASE options (up to 3)
                for a in candidate_ases[:3]:
                    quick_replies.append(
                        ChatbotQuickReply(
                            label=a['name'],
                            value=f"{a['name']} sales{date_suffix}".strip(),
                            entity_type="ase",
                            entity_id=a.get("id"),
                            subtext=a.get("subtext") or "Area Sales Executive",
                        )
                    )

                # 3. Group options (up to 3)
                for g in candidate_groups[:3]:
                    quick_replies.append(
                        ChatbotQuickReply(
                            label=g['name'],
                            value=f"{g['name']} group sales{date_suffix}".strip(),
                            entity_type="group",
                            entity_id=g.get("id"),
                            subtext="Group",
                        )
                    )

                # 4. Combined Outlets option (if multiple active outlets)
                if len(active_licensees) > 1:
                    all_lic_ids = ",".join(str(m["id"]) for m in active_licensees)
                    quick_replies.append(
                        ChatbotQuickReply(
                            label=f"All {clean_q.title()} Outlets ({len(active_licensees)} Outlets)",
                            value=f"All {clean_q} outlets sales{date_suffix}".strip(),
                            entity_type="multi_licensee",
                            entity_id=all_lic_ids,
                            subtext=f"View combined sales across all {len(active_licensees)} active outlets",
                        )
                    )

                # 5. Individual Outlets (up to 5 if mixed, up to 7 if only outlets)
                lic_limit = 5 if (candidate_tsms or candidate_ases or candidate_groups) else 7
                for lic in active_licensees[:lic_limit]:
                    quick_replies.append(
                        ChatbotQuickReply(
                            label=lic['name'],
                            value=f"{lic['name']} sales{date_suffix}".strip(),
                            entity_type="licensee",
                            entity_id=lic.get("id"),
                            subtext=lic.get("subtext") or "Outlet",
                        )
                    )

                # Build dynamic header message
                types_found = []
                if candidate_tsms:
                    types_found.append("TSMs")
                if candidate_ases:
                    types_found.append("ASEs")
                if candidate_groups:
                    types_found.append("Groups")
                if active_licensees:
                    types_found.append("Outlets")

                if len(types_found) > 1:
                    if len(types_found) == 2:
                        types_text = f"{types_found[0]} and {types_found[1]}"
                    else:
                        types_text = f"{', '.join(types_found[:-1])}, and {types_found[-1]}"
                    text = (
                        f"🔍 I found {types_text} matching '{clean_q.title()}'{date_suffix}.\n\n"
                        f"Please select which one you would like to view:"
                    )
                elif candidate_tsms:
                    text = (
                        f"🔍 I found {len(candidate_tsms)} Territory Sales Managers (TSM) matching '{clean_q.title()}'{date_suffix}.\n\n"
                        f"Please select a TSM below to view sales:"
                    )
                elif candidate_ases:
                    text = (
                        f"🔍 I found {len(candidate_ases)} Area Sales Executives (ASE) matching '{clean_q.title()}'{date_suffix}.\n\n"
                        f"Please select an ASE below to view sales:"
                    )
                elif candidate_groups:
                    text = (
                        f"🔍 I found {len(candidate_groups)} groups matching '{clean_q.title()}'{date_suffix}.\n\n"
                        f"Please select a group below to view sales:"
                    )
                else:
                    text = (
                        f"🔍 I found {len(active_licensees)} outlets with recorded sales matching '{clean_q}'.\n\n"
                        f"Please select an outlet below to view sales{date_suffix}:"
                    )

                return ChatMessageResponse(
                    text=text,
                    intent="disambiguation_prompt",
                    period=period,
                    target_date=target_date,
                    selected_hq=selected_hq,
                    quick_replies=quick_replies,
                    suggested_questions=[qr.label for qr in quick_replies[:4]],
                    clarification_needed=True,
                )

            # -----------------------------------------------------------------
            # Case 3: No entities with sales in this period
            # -----------------------------------------------------------------
            return cls._build_response_for_intent(
                intent="no_sales_for_candidates",
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                entity_type=entity_type,
                entity_name=clean_q,
                limit=limit,
                user_message=user_message,
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
        # INTENT: NO SALES FOR MATCHING CANDIDATES IN REQUESTED PERIOD
        # ---------------------------------------------------------------------
        if intent == "no_sales_for_candidates":
            clean_q = (entity_name or "matching outlets").title()
            latest_avail = ChatbotSummaryRepository.resolve_latest_date()
            text = (
                f"⚠️ None of the outlets matching '{clean_q}' recorded sales for {period_lbl}.\n\n"
                f"Would you like to check their total sales for MTD (Month to Date) or on the latest available date ({latest_avail})?"
            )
            quick_replies = [
                ChatbotQuickReply(
                    label=f"Show {clean_q} MTD Sales",
                    value=f"{clean_q} MTD sales",
                ),
                ChatbotQuickReply(
                    label=f"Show {clean_q} Latest Sales ({latest_avail})",
                    value=f"{clean_q} sales on {latest_avail}",
                ),
            ]
            return ChatMessageResponse(
                text=text,
                intent=intent,
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                quick_replies=quick_replies,
                suggested_questions=[qr.label for qr in quick_replies],
                clarification_needed=True,
            )

        # ---------------------------------------------------------------------
        # INTENT 1: GET SALES SUMMARY
        # ---------------------------------------------------------------------
        if intent == "get_sales_summary":
            # 1. Multi-licensee combined aggregation (e.g. from "All Wine Shops Combined" chip)
            if entity_type == "multi_licensee" and entity_id:
                lic_ids = [i.strip() for i in str(entity_id).split(",") if i.strip()]
                multi_summary = ChatbotSummaryRepository.get_multi_licensee_summary(
                    licensee_ids=lic_ids,
                    period=period,
                    target_date=target_date,
                    selected_hq=selected_hq,
                )
                cases = multi_summary["total_cases"]
                kpis = [
                    ChatbotKPI(
                        title=f"Total Cases ({period_lbl})",
                        value=f"{cases:,.2f}",
                        subtext="Combined Cases (9L equivalent)",
                        change_type="neutral",
                    ),
                ]
                import re
                raw_name = (entity_name or "Matching").replace("sales", "").replace("Sales", "").replace("All", "").replace("all", "").strip()
                # Remove date references and existing outlet keywords from raw_name if present
                raw_name = re.sub(r"\b(\d{1,2}(?:st|nd|rd|th)?|\d{4}|august|aug|july|jul|june|jun|on|outlets?|shops?)\b", "", raw_name, flags=re.IGNORECASE).strip()
                clean_title = f"{raw_name.title()} Outlets" if raw_name else "Matching Outlets"
                text = (
                    f"📊 Combined Sales Summary for {clean_title} ({period_lbl})\n\n"
                    f"• Total Cases: {cases:,.2f} cases\n"
                    f"• Active Outlets: {multi_summary.get('record_count', 0)}\n"
                    f"• Scope: {selected_hq}"
                )
                tbl_cols = [
                    ChatbotTableColumn(key="rank", label="#", align="center"),
                    ChatbotTableColumn(key="name", label="Outlet Name", align="left"),
                    ChatbotTableColumn(key="hq", label="Headquarters", align="left"),
                    ChatbotTableColumn(key="cases", label="Cases", align="right"),
                ]
                tbl = ChatbotTable(
                    title=f"Active Outlets Breakdown ({period_lbl})",
                    columns=tbl_cols,
                    rows=multi_summary["rows"],
                )
                drilldown_chips: List[ChatbotQuickReply] = []
                for r in multi_summary["rows"][:4]:
                    drilldown_chips.append(
                        ChatbotQuickReply(
                            label=r["name"],
                            value=f"{r['name']} sales on {period_lbl}".strip(),
                            entity_type="licensee",
                            subtext=f"{r['cases']} cases • {r['hq']}",
                        )
                    )
                return ChatMessageResponse(
                    text=text,
                    intent=intent,
                    period=period,
                    target_date=target_date,
                    selected_hq=selected_hq,
                    kpis=kpis,
                    table=tbl,
                    quick_replies=drilldown_chips,
                    suggested_questions=[c.label for c in drilldown_chips],
                )

            company_id = None
            brand_id = None
            group_id = None
            tsm_user_id = None
            licensee_id = None
            ase_user_id = None
            if entity_name or entity_id:
                if not entity_type and entity_name:
                    entity_type, _ = ChatbotSummaryRepository.resolve_entity_type_and_id(entity_name)
                if entity_type == "licensee":
                    licensee_id = entity_id or ChatbotSummaryRepository.resolve_entity_id("licensee", entity_name)
                elif entity_type in ("ase", "tsm_ase"):
                    ase_user_id = entity_id or ChatbotSummaryRepository.resolve_entity_id("ase", entity_name)
                elif entity_type == "company":
                    company_id = entity_id or ChatbotSummaryRepository.resolve_entity_id("company", entity_name)
                elif entity_type == "brand":
                    brand_id = entity_id or ChatbotSummaryRepository.resolve_entity_id("brand", entity_name)
                elif entity_type in ("group", "licensee_group"):
                    group_id = entity_id or ChatbotSummaryRepository.resolve_entity_id("group", entity_name)
                elif entity_type == "tsm":
                    tsm_user_id = entity_id or ChatbotSummaryRepository.resolve_entity_id("tsm", entity_name)

            summary = ChatbotSummaryRepository.get_sales_summary(
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                company_id=company_id,
                brand_id=brand_id,
                group_id=group_id,
                tsm_user_id=tsm_user_id,
                licensee_id=licensee_id,
                ase_user_id=ase_user_id,
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
            sing_type, _ = cls.get_entity_display_names(entity_type) if entity_type else ("", "")
            type_badge = f" ({sing_type})" if sing_type and sing_type not in ("Brand", "") else ""
            text = (
                f"📊 Sales Summary {header_title}{type_badge} ({period_lbl})\n\n"
                f"• Total Cases: {cases:,.2f} cases\n"
                f"• Scope: {selected_hq}"
            )
            if cases == 0:
                latest_avail = ChatbotSummaryRepository.resolve_latest_date()
                clean_ent = entity_name or "this entity"
                return ChatMessageResponse(
                    text=(
                        f"⚠️ No sales recorded for {clean_ent} on {period_lbl} (excluding company Others).\n\n"
                        f"Would you like to check sales on the latest available date ({latest_avail}) or MTD?"
                    ),
                    intent="no_sales_for_candidates",
                    period=period,
                    target_date=target_date,
                    selected_hq=selected_hq,
                    quick_replies=[
                        ChatbotQuickReply(
                            label=f"Show {clean_ent} Latest Sales ({latest_avail})",
                            value=f"{clean_ent} sales on {latest_avail}",
                            entity_type=entity_type,
                            entity_id=licensee_id or ase_user_id or group_id or brand_id,
                        ),
                        ChatbotQuickReply(
                            label=f"Show {clean_ent} MTD Sales",
                            value=f"{clean_ent} MTD sales",
                            entity_type=entity_type,
                            entity_id=licensee_id or ase_user_id or group_id or brand_id,
                        ),
                    ],
                    clarification_needed=True,
                )

            # Brand breakdown: if licensee, ASE, or TSM, use get_entity_brand_breakdown
            if licensee_id or ase_user_id or tsm_user_id:
                etype = "licensee" if licensee_id else ("ase" if ase_user_id else "tsm")
                eid = licensee_id or ase_user_id or tsm_user_id
                top_b = ChatbotSummaryRepository.get_entity_brand_breakdown(
                    entity_type=etype,
                    entity_id=eid,
                    period=period,
                    target_date=target_date,
                    selected_hq=selected_hq,
                    limit=10,
                )
            else:
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
                {
                    "rank": idx + 1,
                    "brand": b["name"],
                    "cases": f"{b['cases']:,.2f}",
                }
                for idx, b in enumerate(top_b)
            ]

            table_title = f"Top Brands Sold for {entity_name} ({period_lbl})" if entity_name else f"Top Selling Brands ({period_lbl})"
            table = ChatbotTable(
                title=table_title,
                columns=[
                    ChatbotTableColumn(key="rank", label="#", align="center"),
                    ChatbotTableColumn(key="brand", label="Brand Name", align="left"),
                    ChatbotTableColumn(key="cases", label="Cases", align="right"),
                ],
                rows=table_rows,
            )

            # Chart for visual delight
            chart_data = [
                ChatbotChartDataPoint(label=item["name"][:18], value=item["cases"])
                for item in top_b[:5]
            ]
            chart = ChatbotChart(
                title=f"Top Brands Volume for {entity_name}" if entity_name else "Top Brands Volume",
                chart_type="bar",
                series_name="Cases",
                data=chart_data,
            ) if chart_data else None

            suggested_q = [
                "What are the top 10 selling brands?",
                "Show sales breakdown by company",
                "Which brands are growing the fastest?",
                "Compare MTD sales vs last month",
            ]
            if entity_type == "licensee":
                suggested_q = [
                    f"Top brands for {entity_name}",
                    f"{entity_name} MTD sales",
                    f"{entity_name} YTD sales",
                    "Top 5 outlets",
                ]
            elif entity_type in ("ase", "tsm_ase"):
                suggested_q = [
                    f"Top brands for {entity_name}",
                    f"{entity_name} MTD sales",
                    f"{entity_name} YTD sales",
                    "Top 5 ASEs",
                ]

            return ChatMessageResponse(
                text=text,
                intent=intent,
                period=period,
                target_date=target_date,
                selected_hq=selected_hq,
                kpis=kpis,
                table=table,
                chart=chart,
                suggested_questions=suggested_q,
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
