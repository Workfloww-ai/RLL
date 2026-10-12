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
    "greeting",
    "clarification_prompt",
    "disambiguation_prompt",
    "no_response",
    "unmatched_entity",
    "out_of_domain",
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
    def classify_match_confidence(cls, entity_type: str, raw_name: str) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Evaluates match confidence for a target entity name against master catalog.
        Returns (confidence_level, entity_id, resolved_display_name).
        Confidence Levels:
        - "HIGH": Direct exact match or exact multi-word token match.
        - "LOW_TYPO": Typo / fuzzy match (difflib score 0.40 <= score < 0.85 or partial token overlap).
        - "NONE": Unrecognized entity.
        """
        if not raw_name or not raw_name.strip():
            return "NONE", None, None

        import difflib
        from backend.repositories.chatbot.summary_repository import ChatbotSummaryRepository
        master = ChatbotSummaryRepository._load_master_lookups()

        clean_q = raw_name.lower().strip()
        clean_q = re.sub(r"^(sale of|sales of|total sales|summary of|performance of)\s+", "", clean_q)
        clean_q = re.sub(r"\s+(group|brand|company|depot|tsm|hq|licensee|ase)$", "", clean_q).strip()

        dict_rev = (
            master.get("companies_rev", {}) if entity_type == "company"
            else master.get("brands_rev", {}) if entity_type == "brand"
            else master.get("depots_rev", {}) if entity_type == "depot"
            else master.get("hq_rev", {}) if entity_type == "hq"
            else master.get("licensees_rev", {}) if entity_type == "licensee"
            else master.get("ases_rev", {}) if entity_type in ("ase", "tsm_ase")
            else master.get("tsms_rev", {}) if entity_type == "tsm"
            else master.get("groups_rev", {})
        )
        dict_main = (
            master.get("companies", {}) if entity_type == "company"
            else master.get("brands", {}) if entity_type == "brand"
            else master.get("depots", {}) if entity_type == "depot"
            else master.get("hq", {}) if entity_type == "hq"
            else master.get("licensees", {}) if entity_type == "licensee"
            else master.get("ases", {}) if entity_type in ("ase", "tsm_ase")
            else master.get("tsms", {}) if entity_type == "tsm"
            else master.get("groups", {})
        )

        def get_name(eid: str, default_str: str) -> str:
            val = dict_main.get(eid)
            if isinstance(val, str):
                return val
            elif isinstance(val, dict):
                return val.get("name") or default_str
            return default_str.title()

        # 1. Exact lookup
        if clean_q in dict_rev:
            eid = dict_rev[clean_q]
            return "HIGH", eid, get_name(eid, clean_q)

        # 2. Token Set Match
        q_tokens = [w for w in clean_q.split() if len(w) >= 2]
        best_id = None
        best_name = None
        best_score = 0.0

        for key, eid in dict_rev.items():
            k_clean = key.replace(" group", "").strip()
            k_tokens = set(k_clean.split())
            matched = set(q_tokens).intersection(k_tokens)

            # Exact token match for multi-word or single word (e.g. "abhishek" in "abhishek ji")
            if len(matched) == len(q_tokens) and (len(q_tokens) > 1 or any(len(t) >= 4 for t in q_tokens)):
                return "HIGH", eid, get_name(eid, key)

            if matched:
                ratio = difflib.SequenceMatcher(None, clean_q, k_clean).ratio()
                if ratio > best_score:
                    best_score = ratio
                    best_id = eid
                    best_name = get_name(eid, key)

        # 3. Difflib close match
        close_keys = difflib.get_close_matches(clean_q, list(dict_rev.keys()), n=1, cutoff=0.45)
        if close_keys:
            matched_key = close_keys[0]
            eid = dict_rev[matched_key]
            name = get_name(eid, matched_key)
            ratio = difflib.SequenceMatcher(None, clean_q, matched_key).ratio()
            if ratio >= 0.85:
                return "HIGH", eid, name
            elif ratio > best_score:
                best_score = ratio
                best_id = eid
                best_name = name

        if best_id:
            if best_score >= 0.85:
                return "HIGH", best_id, best_name
            elif best_score >= 0.35:
                return "LOW_TYPO", best_id, best_name

        return "NONE", None, None

    @classmethod
    def parse_intent(
        cls,
        user_message: str,
        current_period: str = "Daily",
        current_hq: str = "All Headquarters",
        pending_context: Optional[Dict[str, Any]] = None,
        explicit_entity_type: Optional[str] = None,
        explicit_entity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parses user prompt into target intent name and parameters.
        Supports explicit clicked entity resolution and NLP search with fuzzy disambiguation.
        """
        msg_lower = user_message.lower().strip()

        # Handle explicit clicked quick-reply entity (e.g. from Zomato-style chip click)
        if explicit_entity_type and explicit_entity_id:
            from backend.repositories.chatbot.summary_repository import ChatbotSummaryRepository
            master = ChatbotSummaryRepository._load_master_lookups()
            resolved_name = None
            if explicit_entity_type == "licensee":
                lic = master.get("licensees", {}).get(str(explicit_entity_id))
                resolved_name = lic["name"] if lic else "Licensee"
            elif explicit_entity_type in ("ase", "tsm_ase"):
                ase = master.get("ases", {}).get(str(explicit_entity_id))
                resolved_name = ase["name"] if ase else "ASE"
            elif explicit_entity_type == "company":
                resolved_name = master.get("companies", {}).get(str(explicit_entity_id), "Company")
            elif explicit_entity_type == "brand":
                b = master.get("brands", {}).get(str(explicit_entity_id))
                resolved_name = b["name"] if b else "Brand"
            elif explicit_entity_type in ("group", "licensee_group"):
                resolved_name = master.get("groups", {}).get(str(explicit_entity_id), "Group")
            elif explicit_entity_type == "tsm":
                tsm_obj = next((t for t in master.get("tsms_list", []) if str(t.get("id")) == str(explicit_entity_id)), None)
                resolved_name = tsm_obj["name"] if tsm_obj else "TSM"
            elif explicit_entity_type == "multi_licensee":
                resolved_name = user_message.title() if user_message else "All Matching Shops"

            extracted_target_date = cls.extract_date_from_text(user_message)
            return {
                "intent": "get_sales_summary",
                "period": current_period,
                "target_date": extracted_target_date,
                "entity_type": explicit_entity_type,
                "entity_id": explicit_entity_id,
                "entity_name": resolved_name or user_message,
                "limit": 10,
                "selected_hq": current_hq,
            }

        # 0a. Check for Negative / Rejection Response ("no", "nope", "no thanks")
        if msg_lower in ("no", "nope", "no thanks", "no, thank you", "no thank you", "cancel"):
            return {
                "intent": "no_response",
                "period": current_period,
                "target_date": None,
                "entity_type": None,
                "entity_name": None,
                "limit": 10,
                "selected_hq": current_hq,
            }

        # 0b. Check for Affirmative Confirmation ("Yes", "Yes, show X sales")
        m_yes = re.search(r"^(yes|yeah|sure)\b(?:,\s*show\s+([a-zA-Z0-9\s]+?)\s+sales)?", msg_lower)
        if m_yes:
            confirmed_entity = (m_yes.group(2) or "").strip().title()
            confirmed_type = None
            confirmed_date = None

            if not confirmed_entity and pending_context and pending_context.get("suggested_entity"):
                confirmed_entity = pending_context["suggested_entity"]
                confirmed_type = pending_context.get("suggested_type") or "group"
                confirmed_date = pending_context.get("target_date")

            if confirmed_entity:
                if not confirmed_date and pending_context:
                    confirmed_date = pending_context.get("target_date")
                return {
                    "intent": "get_sales_summary",
                    "period": current_period,
                    "target_date": confirmed_date,
                    "entity_type": confirmed_type,
                    "entity_name": confirmed_entity,
                    "limit": 10,
                    "selected_hq": current_hq,
                }

        # 0c. Greeting & Conversational Intent Detection
        GREETING_WORDS = {
            "hello", "helloo", "hellooo", "hi", "hie", "hey", "helo", "how are you",
            "how r u", "good morning", "good afternoon", "good evening", "namaste",
            "who are you", "what can you do", "help", "hi there", "hello there"
        }
        clean_msg = re.sub(r"[^\w\s]", "", msg_lower).strip()
        sales_keywords = {"sale", "sales", "brand", "company", "depot", "tsm", "group", "case", "cases", "top", "summary", "perform", "trend", "compare", "mtd", "ytd"}

        if clean_msg in GREETING_WORDS or (any(clean_msg.startswith(g) for g in GREETING_WORDS) and not any(k in clean_msg for k in sales_keywords)):
            return {
                "intent": "greeting",
                "period": current_period,
                "target_date": None,
                "entity_type": None,
                "entity_name": None,
                "limit": 10,
                "selected_hq": current_hq,
            }

        # 0d. Explicit Non-Domain Query Check
        NON_DOMAIN_INDICATORS = {
            "weather", "climate", "temperature", "recipe", "cook", "cooking", "ipl", "cricket", "football",
            "soccer", "movie", "film", "song", "joke", "politics", "minister", "president",
            "prime minister", "capital", "math", "code", "python", "programming", "news",
            "who is", "who won", "how to make", "tell me a", "what is the weather"
        }
        if any(nd in msg_lower for nd in NON_DOMAIN_INDICATORS) and not any(k in msg_lower for k in sales_keywords):
            return {
                "intent": "out_of_domain",
                "period": current_period,
                "target_date": None,
                "entity_type": None,
                "entity_name": None,
                "limit": 10,
                "selected_hq": current_hq,
            }

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

        # If user specified explicit day date
        if extracted_target_date and "mtd" not in msg_lower and "month to date" not in msg_lower:
            period = "Daily"
        elif any(m in msg_lower for m in ["august", "aug", "july", "jul", "june", "jun"]):
            if "mtd" in msg_lower or not extracted_target_date:
                period = "MTD"
                if not extracted_target_date:
                    from backend.repositories.chatbot.summary_repository import ChatbotSummaryRepository
                    extracted_target_date = ChatbotSummaryRepository.resolve_latest_date()

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
        raw_candidate = None

        # 4a. Company Detection
        for c_key, c_val in COMPANIES_MAP.items():
            if re.search(rf"\b{c_key}\b", msg_lower):
                entity_name = c_val
                entity_type = "company"
                raw_candidate = c_key
                break

        # 4b. Explicit Group Detection (if user mentioned 'group' or 'syndicate')
        if not entity_name and any(k in msg_lower for k in ["group", "groups", "syndicate"]):
            from backend.repositories.chatbot.summary_repository import ChatbotSummaryRepository
            master = ChatbotSummaryRepository._load_master_lookups()
            master_groups = master.get("groups_rev", {})

            # Check 1: Direct lookup against master catalog group names
            best_group_match = None
            best_match_len = 0
            for g_key, g_id in master_groups.items():
                g_core = g_key.replace(" group", "").strip()
                if len(g_core) >= 3 and (g_core in msg_lower or g_key in msg_lower):
                    if len(g_core) > best_match_len:
                        best_match_len = len(g_core)
                        best_group_match = master.get("groups", {}).get(g_id) or g_core.title()

            if best_group_match:
                entity_type = "group"
                entity_name = best_group_match
            else:
                m_before = re.search(r"(?:sale\s+of\s+|of\s+|for\s+)?((?:[a-zA-Z0-9-]+\s+){1,4})group\b", msg_lower)
                m_after = re.search(r"\bgroup\s+((?:[a-zA-Z0-9-]+\s*){1,4})", msg_lower)

                stop_words = {"sale", "sales", "of", "on", "for", "in", "the", "a", "an", "group", "groups", "total", "daily", "mtd", "ytd", "summary"}

                captured_name = None
                if m_before:
                    raw_str = m_before.group(1).strip()
                    words = [w for w in raw_str.split() if w not in stop_words and not w.isdigit()]
                    if words:
                        captured_name = " ".join(words)
                elif m_after:
                    raw_str = m_after.group(1).strip()
                    words = [w for w in raw_str.split() if w not in stop_words and not w.isdigit()]
                    if words:
                        captured_name = " ".join(words)

                if captured_name:
                    entity_type = "group"
                    raw_candidate = captured_name

        # 4c. TSM Detection (only if 'tsm' is explicitly mentioned)
        has_tsm_keyword = any(k in msg_lower for k in ("tsm", "tsms", "territory sales manager"))
        if has_tsm_keyword and not entity_name and not raw_candidate and entity_type not in ("group", "company"):
            from backend.repositories.chatbot.summary_repository import ChatbotSummaryRepository
            import difflib
            master = ChatbotSummaryRepository._load_master_lookups()
            master_tsms = master.get("tsms_rev", {})

            for t_key, t_id in master_tsms.items():
                t_parts = [part for part in t_key.split() if len(part) >= 3]
                if t_key in msg_lower or (len(t_parts) > 1 and all(part in msg_lower for part in t_parts)):
                    entity_type = "tsm"
                    entity_name = master["tsms"].get(t_id)
                    break

            if not entity_name:
                m_tsm = re.search(r"(?:sale\s+of\s+|sales\s+of\s+|performance\s+of\s+)?((?:[a-zA-Z0-9-]+\s+){1,4})tsm\b", msg_lower)
                if m_tsm:
                    raw_phrase = m_tsm.group(1).strip()
                    stop_words = {"sale", "sales", "of", "on", "for", "in", "the", "a", "an", "tsm", "tsms", "total", "daily", "mtd", "ytd", "summary"}
                    words = [w for w in raw_phrase.split() if w not in stop_words and not w.isdigit()]
                    if words:
                        raw_candidate = " ".join(words)
                        entity_type = "tsm"

        # Evaluate Match Confidence for raw_candidate
        if raw_candidate and not entity_name:
            conf, eid, resolved_name = cls.classify_match_confidence(entity_type, raw_candidate)
            if conf == "HIGH" and resolved_name:
                entity_name = resolved_name
            elif conf == "LOW_TYPO" and resolved_name:
                return {
                    "intent": "clarification_prompt",
                    "period": period,
                    "target_date": extracted_target_date,
                    "entity_type": entity_type,
                    "entity_name": resolved_name,
                    "limit": limit,
                    "selected_hq": selected_hq,
                }
            elif conf == "NONE" and any(prefix in msg_lower for prefix in ["sale of", "sales of", "performance of", "summary of"]):
                return {
                    "intent": "unmatched_entity",
                    "period": period,
                    "target_date": extracted_target_date,
                    "entity_type": entity_type,
                    "entity_name": raw_candidate.title(),
                    "limit": limit,
                    "selected_hq": selected_hq,
                }

        # 4d-pre. Category Dimension Overview Detection
        # Prevents generic queries like "TSM performance", "Company performance", "Depot performance", "Top 5 brands"
        # from mistakenly executing fuzzy substring matching on licensee/outlet names!
        if not entity_name and not raw_candidate:
            if re.search(r"\b(tsm\s+performance|tsms\s+performance|tsm\s+sales|tsms\s+sales|top\s+tsms?|all\s+tsms?|tsm|tsms)\b", msg_lower):
                return {
                    "intent": "get_top_entities",
                    "period": period,
                    "target_date": extracted_target_date,
                    "entity_type": "tsm",
                    "entity_name": None,
                    "limit": limit,
                    "selected_hq": selected_hq,
                }
            elif re.search(r"\b(company\s+performance|companies\s+performance|company\s+sales|companies\s+sales|top\s+companies|all\s+companies|companies|company)\b", msg_lower):
                return {
                    "intent": "get_top_entities",
                    "period": period,
                    "target_date": extracted_target_date,
                    "entity_type": "company",
                    "entity_name": None,
                    "limit": limit,
                    "selected_hq": selected_hq,
                }
            elif re.search(r"\b(depot\s+performance|depots\s+performance|depot\s+sales|depots\s+sales|top\s+depots|all\s+depots|depots|depot)\b", msg_lower):
                return {
                    "intent": "get_top_entities",
                    "period": period,
                    "target_date": extracted_target_date,
                    "entity_type": "depot",
                    "entity_name": None,
                    "limit": limit,
                    "selected_hq": selected_hq,
                }
            elif re.search(r"\b(ase\s+performance|ases\s+performance|ase\s+sales|ases\s+sales|top\s+ases|all\s+ases|ases|ase)\b", msg_lower):
                return {
                    "intent": "get_top_entities",
                    "period": period,
                    "target_date": extracted_target_date,
                    "entity_type": "ase",
                    "entity_name": None,
                    "limit": limit,
                    "selected_hq": selected_hq,
                }
            elif re.search(r"\b(top\s*\d*\s*brands?|best\s+brands?|leading\s+brands?|brand\s+performance|brands?\s+sales)\b", msg_lower):
                return {
                    "intent": "get_top_entities",
                    "period": period,
                    "target_date": extracted_target_date,
                    "entity_type": "brand",
                    "entity_name": None,
                    "limit": limit,
                    "selected_hq": selected_hq,
                }
            elif re.search(r"\b(daily\s+sales\s+summary|sales\s+summary|total\s+sales|overall\s+sales|daily\s+summary|today\s+sales|sales\s+overview)\b", msg_lower):
                return {
                    "intent": "get_sales_summary",
                    "period": period,
                    "target_date": extracted_target_date,
                    "entity_type": "brand",
                    "entity_name": None,
                    "limit": limit,
                    "selected_hq": selected_hq,
                }

        # 4d. Licensee & ASE Detection (with typo and multi-match disambiguation)
        if not entity_name and not raw_candidate:
            from backend.repositories.chatbot.summary_repository import ChatbotSummaryRepository
            clean_search = re.sub(
                r"\b(sales|sale|sel|sail|total|performance|summary|of|for|on|in|at|the|daily|mtd|ytd|today|show|me|tell|view|data|give|please|pls|ka|ki|ke|ko|se|me|mein|par|pe|aur|kya|tha|thi|hai|batao|dikhao|dekho|karo|kitna|kitni|chahiye|bhejo|bataiye|dikhaye|shop|shops|theka|theke|dukan|dukaan|licensee|licensees|licencee|licencees|license|licence|outlet|outlets|group|groups|syndicate|tsm|tsms|company|companies|depot|depots|brand|brands|ase|ases|executive|executives|overall|with|to|from|by|all)\b",
                " ",
                msg_lower
            )
            if extracted_target_date:
                clean_search = re.sub(r"\b(\d{1,2}(?:st|nd|rd|th)?|\d{4}|january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b", " ", clean_search)
            for h_k in ["jaipur", "sikar", "alwar", "sri ganganagar", "ganganagar", "kota", "udaipur", "ajmer", "jodhpur", "hq"]:
                clean_search = re.sub(rf"\b{h_k}\b", " ", clean_search)

            search_phrase = " ".join(clean_search.split()).strip()
            if search_phrase.lower() in ("tsm", "tsms", "company", "companies", "depot", "depots", "brand", "brands", "ase", "ases", "outlet", "outlets", "shop", "shops", "licensee", "licensees", "group", "groups"):
                search_phrase = ""
            target_types = ["licensee", "group", "ase", "tsm"]
            if any(k in msg_lower for k in ["licensee", "licencee", "theka", "theke", "shop", "dukan", "dukaan"]):
                target_types = ["licensee"]
            elif any(k in msg_lower for k in ["group", "groups", "syndicate"]):
                target_types = ["group"]
            elif "ase" in msg_lower or "executive" in msg_lower:
                target_types = ["ase"]
            elif "tsm" in msg_lower or "territory" in msg_lower:
                target_types = ["tsm"]

            if search_phrase and len(search_phrase) >= 2 and not search_phrase.isdigit():
                candidate_matches = ChatbotSummaryRepository.find_matching_entities(search_phrase, target_types=target_types, limit=30)
                if candidate_matches:
                    top_m = candidate_matches[0]
                    second_score = candidate_matches[1]["score"] if len(candidate_matches) > 1 else 0.0

                    entity_types_in_candidates = {c.get("entity_type") for c in candidate_matches if c.get("entity_type")}
                    has_competing_types = len(entity_types_in_candidates) > 1

                    # 1. Single dominant high-confidence match (e.g. Bija Ram with >=0.92 vs runner up <0.85) - only if no competing entity types
                    if top_m["score"] >= 0.92 and second_score < 0.85 and not has_competing_types:
                        entity_name = top_m["name"]
                        entity_type = top_m["entity_type"]
                        return {
                            "intent": "get_sales_summary",
                            "period": period,
                            "target_date": extracted_target_date,
                            "entity_type": entity_type,
                            "entity_id": top_m["id"],
                            "entity_name": entity_name,
                            "limit": limit,
                            "selected_hq": selected_hq,
                        }
                    # 2. Multiple competing matches or mixed entity types
                    elif len(candidate_matches) > 1 or has_competing_types:
                        target_dt = extracted_target_date or ChatbotSummaryRepository.resolve_latest_date()
                        active_matches = ChatbotSummaryRepository.enrich_candidates_with_period_sales(
                            candidate_matches,
                            period=period,
                            target_date=target_dt,
                            selected_hq=selected_hq,
                        )
                        # Valid matches: keep group, ASE, and TSM candidates, and keep licensees strictly with sales > 0.00
                        valid_matches = [
                            m for m in active_matches
                            if m.get("entity_type") in ("group", "ase", "tsm_ase", "tsm") or float(m.get("cases") or 0.0) > 0.0
                        ]

                        types_in_valid = {m.get("entity_type") for m in valid_matches if m.get("entity_type")}
                        has_multiple_types = len(types_in_valid) > 1

                        # If exactly 1 entity had sales (and no competing entity types), directly resolve without asking!
                        if len(valid_matches) == 1 and not has_multiple_types:
                            single_m = valid_matches[0]
                            return {
                                "intent": "get_sales_summary",
                                "period": period,
                                "target_date": extracted_target_date,
                                "entity_type": single_m.get("entity_type", "licensee"),
                                "entity_id": single_m["id"],
                                "entity_name": single_m["name"],
                                "limit": limit,
                                "selected_hq": selected_hq,
                            }
                        # If multiple entities or competing types exist, prompt disambiguation!
                        elif len(valid_matches) > 1 or has_multiple_types:
                            return {
                                "intent": "disambiguation_prompt",
                                "period": period,
                                "target_date": extracted_target_date,
                                "entity_type": "mixed" if has_multiple_types else valid_matches[0]["entity_type"],
                                "entity_name": search_phrase,
                                "candidate_matches": valid_matches,
                                "limit": limit,
                                "selected_hq": selected_hq,
                            }
                        else:
                            # None had sales in this specific period
                            return {
                                "intent": "no_sales_for_candidates",
                                "period": period,
                                "target_date": extracted_target_date,
                                "entity_type": candidate_matches[0]["entity_type"],
                                "entity_name": search_phrase,
                                "candidate_matches": candidate_matches[:5],
                                "limit": limit,
                                "selected_hq": selected_hq,
                            }
                    # 3. Single moderate match (e.g. typo with score >= 0.70)
                    elif top_m["score"] >= 0.70:
                        return {
                            "intent": "disambiguation_prompt",
                            "period": period,
                            "target_date": extracted_target_date,
                            "entity_type": top_m["entity_type"],
                            "entity_name": search_phrase,
                            "candidate_matches": [top_m],
                            "limit": limit,
                            "selected_hq": selected_hq,
                        }

        # 4e. Fallback Entity Type Keyword Detection
        if not entity_name:
            if "company" in msg_lower or "companies" in msg_lower or "manufacturer" in msg_lower:
                entity_type = "company"
            elif "group" in msg_lower or "groups" in msg_lower:
                entity_type = "group"
            elif "licensee" in msg_lower or "licensees" in msg_lower:
                entity_type = "licensee"
            elif "ase" in msg_lower or "ases" in msg_lower:
                entity_type = "ase"
            elif "depot" in msg_lower or "depots" in msg_lower or "warehouse" in msg_lower:
                entity_type = "depot"
            elif "tsm" in msg_lower or "tsms" in msg_lower or "executive" in msg_lower or "salesperson" in msg_lower:
                entity_type = "tsm"
            elif "brand" in msg_lower or "brands" in msg_lower or "product" in msg_lower or "liquor" in msg_lower:
                entity_type = "brand"

        # 5. Intent Routing Rules
        DOMAIN_KEYWORDS = {
            "sale", "sales", "case", "cases", "volume", "bottle", "bottles", "bl",
            "brand", "brands", "company", "companies", "depot", "depots", "warehouse",
            "tsm", "tsms", "executive", "salesperson", "group", "groups", "licensee",
            "licensees", "ase", "ases",
            "hq", "hqs", "headquarters", "jaipur", "sikar", "alwar", "ganganagar", "kota",
            "udaipur", "ajmer", "jodhpur", "rll", "diageo", "pernod", "radico", "bacardi",
            "khoday", "amrut", "sgs", "campari", "ardent", "beyond water",
            "top", "leading", "best", "highest", "biggest", "rank", "ranking",
            "summary", "summarise", "summarize", "total", "overview", "perform", "performance",
            "trend", "history", "chart", "over time", "graph", "days",
            "gainer", "gainers", "loser", "losers", "mover", "movers", "declining", "growing",
            "drop", "growth", "fall", "compare", "versus", "vs", "comparison", "last month", "yesterday",
            "contribution", "share", "percent", "market share", "mtd", "ytd", "daily", "today",
            "august", "aug", "july", "jul", "june", "jun", "january", "jan", "february", "feb",
            "march", "mar", "april", "apr", "may", "september", "sep", "october", "oct",
            "november", "nov", "december", "dec"
        }

        intent = None
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
            if any(prefix in msg_lower for prefix in ["sale of", "sales of", "performance of", "sales for", "summary for"]):
                intent = "get_sales_summary"
            else:
                intent = "get_top_entities"
        elif any(w in msg_lower for w in ["breakdown", "list", "all companies", "all brands", "all depots"]):
            intent = "get_breakdown"
        elif entity_name:
            intent = "get_sales_summary"
        elif any(w in msg_lower for w in ["summary", "summarise", "summarize", "total", "sales", "overview", "perform"]):
            intent = "get_sales_summary"
        elif any(w in msg_lower.split() for w in DOMAIN_KEYWORDS):
            intent = "get_sales_summary"
        else:
            intent = "out_of_domain"

        # LLM fallback if message is complex & Gemini API Key is configured
        if getattr(settings, "GEMINI_API_KEY", None) and len(user_message.split()) > 6:
            try:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(cls._llm_intent_fallback, user_message)
                    llm_parsed = future.result(timeout=1.5)
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
