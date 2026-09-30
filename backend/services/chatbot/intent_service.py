"""
Sales Analytics Chatbot Intent Service.
Parses natural language user prompts into validated analytics tool intents and parameters.

Architecture:
1. High-speed, deterministic regex & rule-based parser for sub-millisecond intent extraction.
2. Optional Gemini LLM fallback for ambiguous natural language queries.
3. STRICT Security: The intent parser ONLY selects approved tool names and parameter models.
   It CANNOT execute SQL, modify permissions, or invent sales metrics.
"""

import logging
import re
from typing import Any, Dict, Optional, Tuple

from backend.core.config import settings

logger = logging.getLogger(__name__)

VALID_INTENTS = {
    "get_sales_summary",
    "get_top_entities",
    "get_breakdown",
    "compare_periods",
    "get_movers",
    "get_contribution",
    "get_trend",
}

class ChatbotIntentService:
    """Parses user questions into structured analytics tool calls."""

    @classmethod
    def parse_intent(
        cls,
        user_message: str,
        current_period: str = "Daily",
        current_hq: str = "All Headquarters"
    ) -> Dict[str, Any]:
        """
        Parses user prompt into target intent name and parameters.
        Returns dictionary containing:
        - intent: str
        - period: str ("Daily", "MTD", "YTD")
        - entity_type: str ("brand", "company", "depot", "tsm", "hq")
        - entity_name: Optional[str]
        - limit: int
        - selected_hq: str
        """
        msg_lower = user_message.lower().strip()

        # 1. Period & Explicit Date extraction
        period = current_period
        if "mtd" in msg_lower or "month to date" in msg_lower or "this month" in msg_lower:
            period = "MTD"
        elif "ytd" in msg_lower or "year to date" in msg_lower or "this year" in msg_lower or "annual" in msg_lower:
            period = "YTD"
        elif "daily" in msg_lower or "today" in msg_lower or "date" in msg_lower:
            period = "Daily"

        extracted_target_date = cls.extract_date_from_text(user_message)

        # 2. HQ Extraction
        selected_hq = current_hq
        HQS_MAP = {
            "jaipur": "Jaipur",
            "sikar": "SIKAR",
            "alwar": "ALWAR",
            "sri ganganagar": "SRI GANGANAGAR",
            "ganganagar": "SRI GANGANAGAR",
            "kota": "Kota",
            "udaipur": "UDAIPUR",
            "ajmer": "Ajmer",
            "jodhpur": "JODHPUR",
        }
        for h_key, h_val in HQS_MAP.items():
            if h_key in msg_lower:
                selected_hq = h_val
                break

        hq_matches = re.search(r"hq\s*:\s*([a-zA-Z\s]+)|in\s+([a-zA-Z\s]+)\s+hq", msg_lower)
        if hq_matches and selected_hq == current_hq:
            found_hq = (hq_matches.group(1) or hq_matches.group(2) or "").strip().title()
            if found_hq:
                selected_hq = found_hq

        # If user specified explicit day date (e.g. '10th august' or '10-08-2026'), use Daily period unless 'mtd' explicitly mentioned
        if extracted_target_date and "mtd" not in msg_lower and "month to date" not in msg_lower:
            period = "Daily"
        elif any(m in msg_lower for m in ["august", "aug", "july", "jul", "june", "jun"]):
            if "mtd" in msg_lower or not extracted_target_date:
                period = "MTD"
                if not extracted_target_date:
                    extracted_target_date = "2026-08-31"

        # 3. Limit Extraction
        limit = 10
        limit_match = re.search(r"\b(top|first|best)\s*(\d+)\b", msg_lower)
        if limit_match:
            try:
                limit = int(limit_match.group(2))
                if limit < 1:
                    limit = 5
                elif limit > 50:
                    limit = 50
            except ValueError:
                limit = 10

        # 4. Entity Type & Company Detection
        COMPANIES_MAP = {
            "rll": "RLL",
            "rajasthan liquors": "RLL",
            "rajasthan liquor": "RLL",
            "diageo": "Diageo/In brew",
            "united spirits": "Diageo/In brew",
            "pernod": "Pernod Ricard India",
            "sgs": "SGS",
            "khoday": "Khoday",
            "amrut": "Amrut",
            "radico": "Radico Khaitan",
            "bacardi": "Bacardi India",
            "campari": "Campari",
            "ardent": "Ardent",
            "beyond water": "Beyond Water",
        }

        entity_type = "brand"
        entity_name = None

        # 4a. Company Detection
        for c_key, c_val in COMPANIES_MAP.items():
            if re.search(rf"\b{c_key}\b", msg_lower):
                entity_name = c_val
                entity_type = "company"
                break

        # 4b. Group Detection
        if not entity_name:
            group_match = re.search(r"(\b[\w\d-]+\b)\s+group|group\s+(\b[\w\d-]+\b)", msg_lower)
            if group_match:
                g_name = (group_match.group(1) or group_match.group(2) or "").strip()
                if g_name and g_name not in ("the", "a", "all", "of", "in", "for", "sales", "total"):
                    entity_type = "group"
                    entity_name = f"{g_name} group"

        # 4c. TSM Detection
        if not entity_name:
            from backend.repositories.chatbot.summary_repository import ChatbotSummaryRepository
            master = ChatbotSummaryRepository._load_master_lookups()
            master_tsms = master.get("tsms_rev", {})
            for t_key, t_id in master_tsms.items():
                if t_key in msg_lower or any(part in msg_lower for part in t_key.split() if len(part) >= 4):
                    entity_type = "tsm"
                    entity_name = master["tsms"].get(t_id)
                    break

        # 4d. Fallback Entity Type Keyword Detection
        if not entity_name:
            if "company" in msg_lower or "companies" in msg_lower or "manufacturer" in msg_lower:
                entity_type = "company"
            elif "group" in msg_lower or "groups" in msg_lower:
                entity_type = "group"
            elif "depot" in msg_lower or "depots" in msg_lower or "warehouse" in msg_lower:
                entity_type = "depot"
            elif "tsm" in msg_lower or "tsms" in msg_lower or "executive" in msg_lower or "salesperson" in msg_lower:
                entity_type = "tsm"
            elif "brand" in msg_lower or "brands" in msg_lower or "product" in msg_lower or "liquor" in msg_lower:
                entity_type = "brand"

        # 5. Intent Routing Rules
        intent = "get_sales_summary"

        if any(w in msg_lower for w in ["gainer", "loser", "mover", "declining", "growing", "drop", "growth", "fall"]):
            intent = "get_movers"
        elif any(w in msg_lower for w in ["compare", "versus", "vs", "comparison", "last month", "yesterday"]):
            intent = "compare_periods"
        elif any(w in msg_lower for w in ["contribution", "share", "%", "percent", "market share", "dominat"]):
            intent = "get_contribution"
        elif any(w in msg_lower for w in ["trend", "history", "chart", "over time", "graph", "days"]):
            intent = "get_trend"
        elif any(w in msg_lower for w in ["top", "leading", "best", "highest", "biggest", "rank", "ranking"]):
            intent = "get_top_entities"
        elif not entity_name and ("company" in msg_lower or "companies" in msg_lower or "tsm" in msg_lower or "tsms" in msg_lower or "depot" in msg_lower or "depots" in msg_lower):
            intent = "get_top_entities"
        elif any(w in msg_lower for w in ["breakdown", "list", "all companies", "all brands", "all depots"]):
            intent = "get_breakdown"
        elif entity_name:
            intent = "get_sales_summary"
        elif any(w in msg_lower for w in ["summary", "summarise", "summarize", "total", "sales", "overview", "perform"]):
            intent = "get_sales_summary"

        # LLM fallback if message is complex & Gemini API Key is configured
        if getattr(settings, "GEMINI_API_KEY", None) and len(user_message.split()) > 6:
            try:
                llm_parsed = cls._llm_intent_fallback(user_message)
                if llm_parsed and llm_parsed.get("intent") in VALID_INTENTS:
                    return {
                        "intent": llm_parsed["intent"],
                        "period": llm_parsed.get("period") or period,
                        "entity_type": llm_parsed.get("entity_type") or entity_type,
                        "entity_name": llm_parsed.get("entity_name") or entity_name,
                        "limit": llm_parsed.get("limit") or limit,
                        "selected_hq": llm_parsed.get("selected_hq") or selected_hq,
                    }
            except Exception as e:
                logger.debug(f"LLM intent fallback notice: {e}")

        return {
            "intent": intent,
            "period": period,
            "target_date": extracted_target_date,
            "entity_type": entity_type,
            "entity_name": entity_name,
            "limit": limit,
            "selected_hq": selected_hq,
        }

    @classmethod
    def extract_date_from_text(cls, text: str, default_year: int = 2026) -> Optional[str]:
        """Extracts natural language date expressions (e.g., '15th august', '15/08/2026') into YYYY-MM-DD."""
        msg = text.lower().strip()
        months_map = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
            'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
            'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
            'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12
        }

        # 1. Day + Month: '15th august', '15th of august', '15 august 2026'
        m1 = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)(?:\s+(\d{4}))?\b', msg)
        if m1:
            day = int(m1.group(1))
            month_str = m1.group(2)
            year = int(m1.group(3)) if m1.group(3) else default_year
            month = months_map.get(month_str)
            if month and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"

        # 2. Month + Day: 'august 15th', 'august 15', 'aug 15 2026'
        m2 = re.search(r'\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?\b', msg)
        if m2:
            month_str = m2.group(1)
            day = int(m2.group(2))
            year = int(m2.group(3)) if m2.group(3) else default_year
            month = months_map.get(month_str)
            if month and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"

        # 3. YYYY-MM-DD
        m3 = re.search(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', msg)
        if m3:
            y, m, d = int(m3.group(1)), int(m3.group(2)), int(m3.group(3))
            return f"{y:04d}-{m:02d}-{d:02d}"

        # 4. DD/MM/YYYY or DD-MM-YYYY
        m4 = re.search(r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b', msg)
        if m4:
            d, m, y = int(m4.group(1)), int(m4.group(2)), int(m4.group(3))
            return f"{y:04d}-{m:02d}-{d:02d}"

        return None

    @classmethod
    def _llm_intent_fallback(cls, prompt: str) -> Optional[Dict[str, Any]]:
        """Optional Gemini LLM intent extractor. Returns intent & parameters dict."""
        import json
        import urllib.request

        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not api_key:
            return None

        sys_prompt = (
            "You are an intent parser for a sales analytics application. "
            "Given a user prompt, return a valid JSON object with keys: "
            "intent (one of: get_sales_summary, get_top_entities, get_breakdown, compare_periods, get_movers, get_contribution, get_trend), "
            "period ('Daily', 'MTD', 'YTD'), entity_type ('brand', 'company', 'depot', 'tsm'), "
            "entity_name (string or null), limit (integer)."
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [
                    {"text": sys_prompt},
                    {"text": f"User query: {prompt}"}
                ]
            }],
            "generationConfig": {"response_mime_type": "application/json"}
        }

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
