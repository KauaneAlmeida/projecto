"""
Hybrid Flow Orchestration Service

This service orchestrates between Firebase predefined flows and AI-powered responses.
It determines whether to use a Firebase flow response or fallback to LangChain + Gemini.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from app.services.firebase_service import get_conversation_flow, get_user_session, save_user_session
from app.services.ai_chain import ai_orchestrator
from app.services.conversation_service import conversation_manager

# Configure logging
logger = logging.getLogger(__name__)

class HybridOrchestrator:
    """
    Hybrid orchestrator that manages the flow between Firebase predefined flows
    and AI-powered responses using LangChain + Gemini.
    """
    
    def __init__(self):
        self.flow_cache = None
        self.cache_timestamp = None
    
    async def process_message(
        self, 
        message: str, 
        session_id: str, 
        phone_number: Optional[str] = None,
        platform: str = "web"
    ) -> Dict[str, Any]:
        """
        Process incoming message with hybrid orchestration.
        
        Args:
            message (str): User's message
            session_id (str): Session identifier
            phone_number (Optional[str]): User's phone number if available
            platform (str): Platform origin ("web", "whatsapp")
            
        Returns:
            Dict[str, Any]: Response with type indicator and content
        """
        try:
            logger.info(f"🎯 Processing message via hybrid orchestration - Session: {session_id}, Platform: {platform}")
            
            # First, check if we're in a Firebase flow
            flow_response = await self._check_firebase_flow(message, session_id, phone_number)
            
            if flow_response:
                logger.info(f"📋 Using Firebase flow response for session: {session_id}")
                return {
                    "response_type": "firebase_flow",
                    "platform": platform,
                    "session_id": session_id,
                    **flow_response
                }
            
            # If no Firebase flow match, use AI
            logger.info(f"🤖 Using AI response for session: {session_id}")
            ai_response = await self._get_ai_response(message, session_id, platform)
            
            return {
                "response_type": "ai_generated",
                "platform": platform,
                "session_id": session_id,
                "response": ai_response,
                "ai_mode": True
            }
            
        except Exception as e:
            logger.error(f"❌ Error in hybrid orchestration: {str(e)}")
            return {
                "response_type": "error",
                "platform": platform,
                "session_id": session_id,
                "response": "Desculpe, ocorreu um erro interno. Nossa equipe foi notificada e entrará em contato em breve.",
                "error": str(e)
            }
    
    async def _check_firebase_flow(
        self, 
        message: str, 
        session_id: str, 
        phone_number: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Check if message should be handled by Firebase flow.
        
        Args:
            message (str): User's message
            session_id (str): Session identifier
            phone_number (Optional[str]): User's phone number
            
        Returns:
            Optional[Dict[str, Any]]: Firebase flow response or None
        """
        try:
            # Get current session state
            session_data = await get_user_session(session_id)
            
            # If no session exists, start new conversation flow
            if not session_data:
                logger.info(f"🆕 No session found, starting new Firebase flow for: {session_id}")
                return await conversation_manager.start_conversation(session_id)
            
            # If session exists but flow is not completed, continue with flow
            if not session_data.get("flow_completed", False):
                logger.info(f"📝 Continuing Firebase flow for session: {session_id}")
                return await conversation_manager.process_response(session_id, message)
            
            # If flow is completed but phone not collected, handle phone collection
            if session_data.get("flow_completed", False) and not session_data.get("phone_collected", False):
                logger.info(f"📱 Handling phone collection for session: {session_id}")
                return await conversation_manager.process_response(session_id, message)
            
            # If everything is completed, return None to use AI
            logger.info(f"✅ Firebase flow completed for session {session_id}, switching to AI mode")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error checking Firebase flow: {str(e)}")
            return None
    
    async def _get_ai_response(self, message: str, session_id: str, platform: str) -> str:
        """
        Get AI response using LangChain + Gemini.
        
        Args:
            message (str): User's message
            session_id (str): Session identifier
            platform (str): Platform origin
            
        Returns:
            str: AI-generated response
        """
        try:
            # Add platform context to the message for better AI understanding
            contextual_message = message
            if platform == "whatsapp":
                contextual_message = f"[WhatsApp] {message}"
            elif platform == "web":
                contextual_message = f"[Website] {message}"
            
            # Generate AI response
            ai_response = await ai_orchestrator.generate_response(contextual_message, session_id)
            
            # Update session to indicate AI mode
            session_data = await get_user_session(session_id) or {}
            session_data.update({
                "ai_mode": True,
                "flow_completed": True,
                "phone_collected": True,  # Assume collected if in AI mode
                "platform": platform,
                "last_ai_interaction": message
            })
            await save_user_session(session_id, session_data)
            
            return ai_response
            
        except Exception as e:
            logger.error(f"❌ Error getting AI response: {str(e)}")
            return "Desculpe, estou enfrentando dificuldades técnicas. Nossa equipe entrará em contato em breve para ajudá-lo."
    
    async def handle_phone_number_submission(
        self, 
        phone_number: str, 
        session_id: str
    ) -> Dict[str, Any]:
        """
        Handle phone number submission from web platform.
        
        Args:
            phone_number (str): User's phone number
            session_id (str): Session identifier
            
        Returns:
            Dict[str, Any]: Response with WhatsApp trigger status
        """
        try:
            logger.info(f"📱 Handling phone number submission: {phone_number} for session: {session_id}")
            
            # Get current session data
            session_data = await get_user_session(session_id) or {}
            
            # Save phone number to session
            session_data.update({
                "phone_number": phone_number,
                "phone_submitted": True,
                "platform_transition": "web_to_whatsapp"
            })
            await save_user_session(session_id, session_data)
            
            # Import here to avoid circular imports
            from app.services.baileys_service import baileys_service
            
            # Format phone number for WhatsApp
            # Clean and format phone number
            phone_clean = ''.join(filter(str.isdigit, phone_number))
            
            # Add country code if missing
            if len(phone_clean) == 10:
                # Add 9 for mobile numbers without it (Brazilian format)
                phone_formatted = f"55{phone_clean[:2]}9{phone_clean[2:]}"
            elif len(phone_clean) == 11:
                phone_formatted = f"55{phone_clean}"
            else:
                phone_formatted = phone_clean
            
            # Add WhatsApp suffix
            whatsapp_number = f"{phone_formatted}@s.whatsapp.net"
            
            # Prepare initial WhatsApp message
            user_name = session_data.get("responses", {}).get("name", "Cliente")
            responses = session_data.get("responses", {})
            
            initial_message = f"""Olá {user_name}! 👋

Recebemos sua solicitação através do nosso site e estamos aqui para ajudá-lo com questões jurídicas.

📋 *Resumo das suas informações:*
• Nome: {responses.get("name", "Não informado")}
• Área jurídica: {responses.get("area_of_law", "Não especificada")}
• Situação: {responses.get("situation", "Não informada")[:100]}{"..." if len(responses.get("situation", "")) > 100 else ""}

Nossa equipe jurídica especializada está pronta para analisar seu caso. Vamos continuar nossa conversa aqui no WhatsApp para maior comodidade.

Como posso ajudá-lo hoje? 🤝"""
            
            # Send WhatsApp message
            whatsapp_success = False
            try:
                whatsapp_success = await baileys_service.send_whatsapp_message(
                    whatsapp_number, 
                    initial_message
                )
                logger.info(f"📱 WhatsApp message sent to {whatsapp_number}: {whatsapp_success}")
            except Exception as whatsapp_error:
                logger.error(f"❌ Failed to send WhatsApp message: {str(whatsapp_error)}")
            
            return {
                "response_type": "phone_submitted",
                "session_id": session_id,
                "phone_number": phone_number,
                "phone_formatted": phone_formatted,
                "whatsapp_sent": whatsapp_success,
                "message": f"✅ Perfeito! {'Enviamos uma mensagem para seu WhatsApp ' + phone_clean + '. Continue a conversa por lá!' if whatsapp_success else 'Registramos seu número ' + phone_clean + '. Nossa equipe entrará em contato em breve.'}"
            }
            
        except Exception as e:
            logger.error(f"❌ Error handling phone number submission: {str(e)}")
            return {
                "response_type": "error",
                "session_id": session_id,
                "message": "Ocorreu um erro ao processar seu número. Nossa equipe entrará em contato em breve.",
                "error": str(e)
            }
    
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """
        Get comprehensive session context for debugging/admin purposes.
        
        Args:
            session_id (str): Session identifier
            
        Returns:
            Dict[str, Any]: Session context information
        """
        try:
            # Get Firebase session data
            session_data = await get_user_session(session_id) or {}
            
            # Get AI conversation summary
            ai_summary = ai_orchestrator.get_conversation_summary(session_id)
            
            return {
                "session_id": session_id,
                "firebase_session": session_data,
                "ai_conversation": ai_summary,
                "flow_completed": session_data.get("flow_completed", False),
                "ai_mode": session_data.get("ai_mode", False),
                "phone_collected": session_data.get("phone_collected", False),
                "platform": session_data.get("platform", "unknown")
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting session context: {str(e)}")
            return {"error": str(e)}

# Global hybrid orchestrator instance
hybrid_orchestrator = HybridOrchestrator()