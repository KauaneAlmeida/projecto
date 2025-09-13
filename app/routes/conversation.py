"""
Conversation Flow Routes

Handles the hybrid conversation flow for client intake:
- Step-by-step guided questions (Firebase)
- Fallback to AI-powered responses (LangChain + Gemini)
- Phone number collection & WhatsApp trigger
- Context preservation across web and WhatsApp
"""

import uuid
import logging
import json
import os
from fastapi import APIRouter, HTTPException, status

from app.models.request import ConversationRequest
from app.models.response import ConversationResponse
from app.services.orchestration_service import hybrid_orchestrator
from app.services.firebase_service import get_firebase_service_status

# Logging
logger = logging.getLogger(__name__)

# FastAPI router
router = APIRouter()


@router.post("/conversation/start", response_model=ConversationResponse)
async def start_conversation():
    """
    Start a new conversation session.
    Initializes with hybrid orchestration (Firebase + AI).
    """
    try:
        session_id = str(uuid.uuid4())
        logger.info(f"🚀 Starting new conversation | session={session_id}")

        result = await hybrid_orchestrator.process_message("", session_id, platform="web")
        return ConversationResponse(**result)

    except Exception as e:
        logger.error(f"❌ Error starting conversation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start conversation"
        )


@router.post("/conversation/respond", response_model=ConversationResponse)
async def respond_to_conversation(request: ConversationRequest):
    """
    Process user response with hybrid orchestration.

    Flow:
    1. Continue Firebase guided flow if active
    2. Use AI fallback via LangChain + Gemini
    3. Handle phone collection & WhatsApp trigger
    """
    try:
        if not request.session_id:
            request.session_id = str(uuid.uuid4())
            logger.info(f"🆕 New session generated: {request.session_id}")

        logger.info(f"📝 Processing response | session={request.session_id} | msg={request.message[:50]}...")

        result = await hybrid_orchestrator.process_message(
            request.message,
            request.session_id,
            platform="web"
        )
        return ConversationResponse(**result)

    except Exception as e:
        logger.error(f"❌ Error processing response: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process conversation response"
        )


@router.post("/conversation/submit-phone")
async def submit_phone_number(request: dict):
    """
    Submit phone number and trigger WhatsApp flow.
    """
    try:
        phone_number = request.get("phone_number")
        session_id = request.get("session_id")
        
        if not phone_number or not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing phone_number or session_id"
            )
        
        logger.info(f"📱 Phone submitted | session={session_id} | number={phone_number}")

        result = await hybrid_orchestrator.handle_phone_number_submission(phone_number, session_id)
        return result

    except Exception as e:
        logger.error(f"❌ Error submitting phone number: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process phone number submission"
        )


@router.get("/conversation/status/{session_id}")
async def get_conversation_status(session_id: str):
    """
    Get current conversation state for a session.
    """
    try:
        logger.info(f"📊 Fetching status | session={session_id}")
        status_info = await hybrid_orchestrator.get_session_context(session_id)
        return status_info

    except Exception as e:
        logger.error(f"❌ Error getting status for {session_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get conversation status"
        )


@router.get("/conversation/ai-config")
async def get_ai_config():
    """
    Get AI system prompt + configuration (debug/admin use).
    """
    try:
        from app.services.ai_chain import ai_orchestrator

        config = {}
        if os.path.exists("ai_schema.json"):
            with open("ai_schema.json", "r", encoding="utf-8") as f:
                config = json.load(f)

        return {
            "current_system_prompt": ai_orchestrator.get_system_prompt(),
            "full_config": config,
            "config_source": "ai_schema.json" if config else "default",
            "editable_location": "ai_schema.json in project root"
        }

    except Exception as e:
        logger.error(f"❌ Error getting AI config: {str(e)}")
        return {"error": str(e)}


@router.get("/conversation/flow")
async def get_conversation_flow():
    """
    Get current Firebase conversation flow config.
    Lawyers can edit it directly in Firebase Console.
    """
    try:
        from app.services.conversation_service import conversation_manager

        flow = await conversation_manager.get_flow()
        return {
            "flow": flow,
            "total_steps": len(flow.get("steps", [])),
            "editable_in": "Firebase Console > conversation_flows > law_firm_intake",
            "note": "Lawyers can update questions without code changes",
            "features": [
                "Firebase-guided sequence",
                "Hybrid orchestration with AI fallback",
                "LangChain + Gemini integration",
                "Phone collection",
                "WhatsApp trigger",
                "Cross-platform context"
            ]
        }

    except Exception as e:
        logger.error(f"❌ Error retrieving conversation flow: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversation flow"
        )


@router.get("/conversation/service-status")
async def conversation_service_status():
    """
    Check overall service health: Firebase + AI + flow accessibility.
    """
    try:
        # Firebase
        firebase_status = await get_firebase_service_status()

        # Flow check
        try:
            from app.services.conversation_service import conversation_manager
            flow = await conversation_manager.get_flow()
            flow_accessible = True
            total_steps = len(flow.get("steps", []))
        except Exception as e:
            flow_accessible = False
            total_steps = 0
            logger.error(f"❌ Flow access test failed: {str(e)}")

        # AI service
        try:
            from app.services.ai_chain import get_ai_service_status
            ai_status = await get_ai_service_status()
        except Exception as e:
            ai_status = {"status": "error", "error": str(e)}

        return {
            "service": "hybrid_orchestration_service",
            "status": (
                "active" if firebase_status["status"] == "active"
                and flow_accessible
                and ai_status["status"] == "active" else "degraded"
            ),
            "firebase_status": firebase_status,
            "ai_status": ai_status,
            "conversation_flow": {
                "accessible": flow_accessible,
                "total_steps": total_steps,
                "editable_location": "Firebase Console > conversation_flows > law_firm_intake"
            },
            "endpoints": {
                "start": "/api/v1/conversation/start",
                "respond": "/api/v1/conversation/respond",
                "submit_phone": "/api/v1/conversation/submit-phone",
                "status": "/api/v1/conversation/status/{session_id}",
                "flow": "/api/v1/conversation/flow",
                "ai_config": "/api/v1/conversation/ai-config"
            }
        }

    except Exception as e:
        logger.error(f"❌ Error getting service status: {str(e)}")
        return {"service": "conversation_service", "status": "error", "error": str(e)}
