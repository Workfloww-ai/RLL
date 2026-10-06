"""
Sales Analytics Chatbot API Router.
Dedicated HTTP endpoint handlers for Sales AI Chatbot requests.
"""

import time
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from backend.core.security import get_current_user
from backend.schemas.chatbot import ChatMessageRequest, ChatMessageResponse
from backend.services.chatbot.analytics_service import ChatbotAnalyticsService

from backend.services.tenant_service import get_chatbot_enabled_setting_async

router = APIRouter(prefix="/chatbot", tags=["Sales Chatbot"])

@router.post("/query", response_model=ChatMessageResponse)
async def query_sales_chatbot(
    payload: ChatMessageRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> ChatMessageResponse:
    """
    Main Chatbot Query API Endpoint.
    Validates user JWT token, extracts security scope, executes analytics intent,
    and returns structured response with KPIs, tables, and charts.
    """
    is_chatbot_enabled = await get_chatbot_enabled_setting_async()
    if not is_chatbot_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sales AI Chatbot feature is currently disabled by system administrator."
        )

    if not payload.message or not payload.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User message query cannot be empty."
        )

    t_start = time.perf_counter()
    try:
        response = await ChatbotAnalyticsService.process_chat_query(
            payload=payload,
            current_user=current_user
        )
        latency_sec = time.perf_counter() - t_start
        latency_ms = round(latency_sec * 1000.0, 2)
        response.execution_time_ms = latency_ms

        cache_status_str = "HIT (Served from Redis RAM)" if response.cache_hit else "MISS (Fetched from PostgreSQL DB)"
        print(
            f"\n{'='*70}\n"
            f"⏱️  [CHATBOT RESPONSE LATENCY]\n"
            f"   User Question : \"{payload.message}\"\n"
            f"   Latency       : {latency_sec:.4f} seconds ({latency_ms:.2f} ms)\n"
            f"   Cache Status  : {cache_status_str}\n"
            f"   Intent        : {response.intent} | Period: {response.period}\n"
            f"{'='*70}\n",
            flush=True
        )
        return response
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chatbot execution error: {str(e)}"
        )

@router.get("/suggested-prompts")
async def get_suggested_prompts(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, List[str]]:
    """Returns curated starter prompt pills for Chatbot UI."""
    is_chatbot_enabled = await get_chatbot_enabled_setting_async()
    if not is_chatbot_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sales AI Chatbot feature is currently disabled by system administrator."
        )
    return {
        "prompts": [
            "Summarise total sales for Daily",
            "What are the top 5 selling brands?",
            "Show company market share breakdown",
            "Compare MTD sales vs last month",
            "Which brands are growing the fastest?",
            "Show daily sales trend over last 7 days",
            "Who are the top 5 TSMs by sales volume?",
        ]
    }
