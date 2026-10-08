import logging
import re
import uuid
from typing import List, Dict, Any, Optional
from backend.db.supabase_client import get_supabase_client

logger = logging.getLogger("popular_queries_repository")

FALLBACK_PROMPTS = [
    "Summarise total sales for Daily",
    "What are the top 5 selling brands?",
    "Show company market share breakdown",
    "Compare MTD sales vs last month",
    "Which brands are growing the fastest?",
    "Show daily sales trend over last 7 days",
    "Who are the top 5 TSMs by sales volume?",
]


def _is_valid_uuid(val: Any) -> bool:
    """Checks if a string value is a valid UUID format."""
    if not val:
        return False
    try:
        uuid.UUID(str(val))
        return True
    except Exception:
        return False


class PopularQueriesRepository:
    """Repository layer for chatbot query logging and popular prompts."""

    @staticmethod
    def normalize_query(query: str) -> str:
        """Normalizes raw user query string for grouping and frequency tracking."""
        if not query:
            return ""
        # Lowercase, strip punctuation and extra whitespace
        cleaned = re.sub(r'[^\w\s]', '', query.lower())
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    @classmethod
    def get_popular_prompts(cls, limit: int = 8) -> List[str]:
        """
        Fetches mostly asked / popular prompts sorted by pinning status,
        display order, and frequency count.
        """
        client = get_supabase_client()
        if not client:
            return FALLBACK_PROMPTS

        prompts = []
        seen = set()

        try:
            res = client.table("chatbot_popular_queries") \
                .select("display_text, is_pinned, display_order, ask_count") \
                .eq("is_active", True) \
                .order("is_pinned", desc=True) \
                .order("display_order", desc=False) \
                .order("ask_count", desc=True) \
                .limit(limit) \
                .execute()

            if res.data:
                for row in res.data:
                    txt = (row.get("display_text") or "").strip()
                    norm = cls.normalize_query(txt)
                    is_pinned = bool(row.get("is_pinned"))
                    ask_count = int(row.get("ask_count") or 0)

                    # Strictly include queries asked >= 5 times OR explicitly pinned by Admin
                    if txt and norm not in seen and (is_pinned or ask_count >= 5):
                        seen.add(norm)
                        prompts.append(txt)

            # Fill up to limit with fallback prompts if needed
            if len(prompts) < limit:
                for fallback in FALLBACK_PROMPTS:
                    norm = cls.normalize_query(fallback)
                    if norm not in seen:
                        seen.add(norm)
                        prompts.append(fallback)
                    if len(prompts) >= limit:
                        break

            if prompts:
                return prompts[:limit]
        except Exception as e:
            logger.warning(f"Error fetching popular queries from DB (using fallback): {e}")

        return FALLBACK_PROMPTS

    @classmethod
    def log_query_and_update_stats(
        cls,
        raw_query: str,
        normalized_query: str,
        intent: str,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        execution_time_ms: float = 0.0,
        is_successful: bool = True
    ) -> None:
        """
        Logs raw query event into chatbot_query_logs table and increments frequency
        counter in chatbot_popular_queries table asynchronously.
        """
        client = get_supabase_client()
        if not client or not raw_query or not raw_query.strip():
            return

        norm_query = normalized_query or cls.normalize_query(raw_query)
        if len(norm_query) < 3:
            return  # Skip logging extremely short/vague messages like "hi"

        # 1. Log query execution event (isolated try block)
        try:
            log_payload = {
                "raw_query": raw_query.strip(),
                "normalized_query": norm_query,
                "intent": intent or "UNKNOWN",
                "execution_time_ms": execution_time_ms,
                "is_successful": is_successful
            }
            if user_id and _is_valid_uuid(user_id):
                log_payload["user_id"] = str(user_id)
            if tenant_id and _is_valid_uuid(tenant_id):
                log_payload["tenant_id"] = str(tenant_id)

            client.table("chatbot_query_logs").insert(log_payload).execute()
        except Exception as e_log:
            logger.error(f"Error inserting into chatbot_query_logs: {e_log}")

        # 2. Update frequency in popular queries table (isolated try block)
        try:
            existing_res = client.table("chatbot_popular_queries") \
                .select("id, ask_count") \
                .eq("normalized_query", norm_query) \
                .limit(1) \
                .execute()

            if existing_res.data and len(existing_res.data) > 0:
                existing_row = existing_res.data[0]
                new_count = (existing_row.get("ask_count") or 0) + 1
                client.table("chatbot_popular_queries") \
                    .update({"ask_count": new_count}) \
                    .eq("id", existing_row["id"]) \
                    .execute()
            else:
                pop_payload = {
                    "display_text": raw_query.strip(),
                    "normalized_query": norm_query,
                    "intent": intent or "UNKNOWN",
                    "ask_count": 1,
                    "is_active": True
                }
                if tenant_id and _is_valid_uuid(tenant_id):
                    pop_payload["tenant_id"] = str(tenant_id)

                client.table("chatbot_popular_queries").insert(pop_payload).execute()
        except Exception as e_pop:
            logger.error(f"Error updating chatbot_popular_queries: {e_pop}")

