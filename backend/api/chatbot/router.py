"""
Sales Analytics Chatbot API Router.
Dedicated HTTP endpoint handlers for Sales AI Chatbot requests.
"""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from backend.core.security import get_current_user
from backend.schemas.chatbot import ChatMessageRequest, ChatMessageResponse
from backend.services.chatbot.analytics_service import ChatbotAnalyticsService

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
    if not payload.message or not payload.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User message query cannot be empty."
        )

    try:
        response = await ChatbotAnalyticsService.process_chat_query(
            payload=payload,
            current_user=current_user
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chatbot execution error: {str(e)}"
        )

@router.get("/suggested-prompts")
async def get_suggested_prompts(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, List[str]]:
    """Returns curated starter prompt pills for Chatbot UI."""
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
