"""
Firebase Service (Simplified)

This module handles Firebase Admin SDK integration for Firestore operations.
It initializes Firebase using a single service account JSON file instead of
multiple environment variables.
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import HTTPException, status

# Configure logging
logger = logging.getLogger(__name__)

# Global Firebase app instance
_firebase_app = None
_firestore_client = None


def initialize_firebase():
    """
    Initialize Firebase Admin SDK with credentials.json.
    Only initializes once to avoid duplicate app errors.
    """
    global _firebase_app, _firestore_client

    if _firebase_app is not None:
        logger.info("✅ Firebase already initialized")
        return

    try:
        cred_path = os.getenv("FIREBASE_CREDENTIALS", "firebase-key.json")

        if not os.path.exists(cred_path):
            raise ValueError(
                f"Firebase credentials file not found: {cred_path}. "
                "Make sure FIREBASE_CREDENTIALS is set correctly in your .env."
            )

        logger.info(f"🔥 Initializing Firebase using {cred_path}")

        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)

        # Initialize Firestore client
        _firestore_client = firestore.client()
        logger.info("✅ Firebase initialized successfully")

    except Exception as e:
        logger.error(f"❌ Failed to initialize Firebase: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Firebase initialization failed: {str(e)}",
        )


def get_firestore_client():
    """
    Get the Firestore client instance.
    """
    if _firestore_client is None:
        initialize_firebase()

    if _firestore_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firestore client not available",
        )

    return _firestore_client


# --------------------------------------------------------------------------
# Conversation Flow
# --------------------------------------------------------------------------
async def get_conversation_flow() -> Dict[str, Any]:
    try:
        db = get_firestore_client()
        flow_ref = db.collection("conversation_flows").document("law_firm_intake")
        flow_doc = flow_ref.get()

        if not flow_doc.exists:
            logger.info("📝 Creating default conversation flow")
            default_flow = {
                "steps": [
                    {
                        "id": 1,
                        "question": "Olá! Bem-vindo ao nosso escritório de advocacia. Para começar, qual é o seu nome completo?",
                        "field": "name",
                        "required": True,
                        "type": "text",
                    },
                    {
                        "id": 2,
                        "question": "Em qual área do direito você precisa de ajuda?\n\n1️⃣ Direito Penal\n2️⃣ Direito Civil\n3️⃣ Direito Trabalhista\n4️⃣ Direito de Família\n5️⃣ Outro\n\nPor favor, digite o número ou o nome da área:",
                        "field": "area_of_law",
                        "required": True,
                        "type": "choice",
                    },
                    {
                        "id": 3,
                        "question": "Descreva brevemente sua situação jurídica. Isso nos ajudará a entender como podemos auxiliá-lo:",
                        "field": "situation",
                        "required": True,
                        "type": "text",
                    },
                    {
                        "id": 4,
                        "question": "Obrigado pelas informações. Mesmo que o orçamento seja uma preocupação, podemos trabalhar juntos para encontrar um plano de pagamento adequado. Gostaria que eu agendasse uma consulta com um de nossos advogados?\n\nPor favor, responda: Sim ou Não",
                        "field": "wants_meeting",
                        "required": True,
                        "type": "boolean",
                    },
                ],
                "completion_message": "Obrigado! Suas informações foram registradas e um de nossos advogados entrará em contato em breve.",
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "version": "2.0",
                "description": "Fluxo de captação de leads para escritório de advocacia",
            }

            flow_ref.set(default_flow)
            logger.info("✅ Default conversation flow created")
            return default_flow

        return flow_doc.to_dict()

    except Exception as e:
        logger.error(f"❌ Error retrieving conversation flow: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversation flow",
        )


# --------------------------------------------------------------------------
# Lead Management
# --------------------------------------------------------------------------
async def save_lead_data(lead_data: Dict[str, Any]) -> str:
    try:
        db = get_firestore_client()

        lead_data.update(
            {
                "timestamp": datetime.now(),
                "status": "new",
                "source": "chatbot_intake",
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
        )

        leads_ref = db.collection("leads")
        doc_ref = leads_ref.add(lead_data)
        return doc_ref[1].id

    except Exception as e:
        logger.error(f"❌ Error saving lead data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save lead information",
        )


async def update_lead_data(lead_id: str, update_data: Dict[str, Any]) -> bool:
    try:
        db = get_firestore_client()
        update_data["updated_at"] = datetime.now()
        db.collection("leads").document(lead_id).update(update_data)
        return True
    except Exception as e:
        logger.error(f"❌ Error updating lead data: {str(e)}")
        return False


# --------------------------------------------------------------------------
# Session Management
# --------------------------------------------------------------------------
async def get_user_session(session_id: str) -> Optional[Dict[str, Any]]:
    try:
        db = get_firestore_client()
        doc = db.collection("user_sessions").document(session_id).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        logger.error(f"❌ Error retrieving session {session_id}: {str(e)}")
        return None


async def save_user_session(session_id: str, session_data: Dict[str, Any]) -> bool:
    try:
        db = get_firestore_client()
        session_data["last_updated"] = datetime.now()
        if "created_at" not in session_data:
            session_data["created_at"] = datetime.now()
        db.collection("user_sessions").document(session_id).set(session_data, merge=True)
        return True
    except Exception as e:
        logger.error(f"❌ Error saving session {session_id}: {str(e)}")
        return False


# --------------------------------------------------------------------------
# Health Check
# --------------------------------------------------------------------------
async def get_firebase_service_status() -> Dict[str, Any]:
    try:
        db = get_firestore_client()
        test_ref = db.collection("_health_check").document("test")
        test_ref.set({"timestamp": datetime.now(), "status": "healthy"})

        return {
            "service": "firebase_service",
            "status": "active",
            "firestore_connected": True,
            "credentials_file": os.getenv("FIREBASE_CREDENTIALS", "firebase-key.json"),
            "collections": ["conversation_flows", "leads", "user_sessions", "_health_check"],
        }
    except Exception as e:
        return {
            "service": "firebase_service",
            "status": "error",
            "firestore_connected": False,
            "error": str(e),
            "configuration_required": True,
        }


# Initialize on import
try:
    initialize_firebase()
    logger.info("🔥 Firebase service module loaded successfully")
except Exception as e:
    logger.warning(f"⚠️ Firebase initialization deferred: {str(e)}")
