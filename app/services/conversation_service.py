"""
Conversation Flow Service

This module manages the guided conversation flow for law firm client intake.
It handles step-by-step questions, user responses, and transitions to AI chat.

The conversation flow is stored in Firebase and can be updated by lawyers
without modifying the code.
"""

import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from app.services.firebase_service import (
    get_conversation_flow,
    save_lead_data,
    get_user_session,
    save_user_session
)
from app.services.ai_service import process_chat_message
from app.services.baileys_service import baileys_service

# Configure logging
logger = logging.getLogger(__name__)

class ConversationManager:
    """
    Manages conversation flow state and progression for users.
    
    This class handles:
    - Step-by-step guided questions
    - User response collection and validation
    - Redirection for irrelevant responses
    - Lead data compilation
    - Transition to AI chat mode
    - Phone number collection and WhatsApp trigger
    """
    
    def __init__(self):
        self.flow_cache = None
        self.cache_timestamp = None
    
    async def get_flow(self) -> Dict[str, Any]:
        """Get conversation flow, with caching for performance."""
        # Cache flow for 5 minutes to reduce Firebase calls
        if (self.flow_cache is None or 
            (datetime.now() - self.cache_timestamp).seconds > 300):
            self.flow_cache = await get_conversation_flow()
            self.cache_timestamp = datetime.now()
        
        return self.flow_cache
    
    async def start_conversation(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Start a new conversation flow.
        
        Args:
            session_id (Optional[str]): Session ID, generates new if None
            
        Returns:
            Dict[str, Any]: Initial conversation state with first question
        """
        try:
            if not session_id:
                session_id = str(uuid.uuid4())
            
            flow = await self.get_flow()
            
            # Initialize session data
            session_data = {
                "session_id": session_id,
                "current_step": 1,
                "responses": {},
                "flow_completed": False,
                "ai_mode": False,
                "phone_collected": False,
                "started_at": datetime.now(),
                "last_updated": datetime.now()
            }
            
            await save_user_session(session_id, session_data)
            
            # Get first question
            first_step = next((step for step in flow["steps"] if step["id"] == 1), None)
            
            if not first_step:
                raise ValueError("No first step found in conversation flow")
            
            logger.info(f"✅ Started conversation for session: {session_id}")
            
            return {
                "session_id": session_id,
                "question": first_step["question"],
                "step_id": first_step["id"],
                "is_final_step": len(flow["steps"]) == 1,
                "flow_completed": False,
                "ai_mode": False,
                "phone_collected": False
            }
            
        except Exception as e:
            logger.error(f"❌ Error starting conversation: {str(e)}")
            raise
    
    async def process_response(self, session_id: str, user_response: str) -> Dict[str, Any]:
        """
        Process user response and return next question or AI response.
        
        Args:
            session_id (str): The session identifier
            user_response (str): User's response to current question
            
        Returns:
            Dict[str, Any]: Next question or AI response with conversation state
        """
        try:
            # Get current session
            session_data = await get_user_session(session_id)
            if not session_data:
                # Session not found, start new conversation
                logger.info(f"🔄 Session {session_id} not found, starting new conversation")
                return await self.start_conversation(session_id)
            
            # If in phone collection mode
            if session_data.get("flow_completed", False) and not session_data.get("phone_collected", False):
                return await self._handle_phone_collection(session_id, session_data, user_response)
            
            # If already in AI mode, use Gemini
            if session_data.get("ai_mode", False):
                ai_response = await process_chat_message(user_response, session_id=session_id)
                return {
                    "session_id": session_id,
                    "response": ai_response,
                    "ai_mode": True,
                    "flow_completed": True,
                    "phone_collected": session_data.get("phone_collected", False)
                }
            
            flow = await self.get_flow()
            current_step = session_data.get("current_step", 1)
            
            # Find current step in flow
            current_step_data = next(
                (step for step in flow["steps"] if step["id"] == current_step), 
                None
            )
            
            if not current_step_data:
                logger.error(f"❌ Step {current_step} not found in flow")
                return await self._switch_to_ai_mode(session_id, user_response)
            
            # Validate response relevance (basic check)
            if not self._is_response_relevant(user_response, current_step_data):
                logger.info(f"🔄 Irrelevant response detected for step {current_step}")
                return {
                    "session_id": session_id,
                    "question": f"Por favor, responda à pergunta atual: {current_step_data['question']}",
                    "step_id": current_step_data["id"],
                    "is_final_step": False,
                    "flow_completed": False,
                    "ai_mode": False,
                    "redirect_message": True
                }
            
            # Save user response
            field_name = current_step_data.get("field", f"step_{current_step}")
            session_data["responses"][field_name] = user_response.strip()
            session_data["last_updated"] = datetime.now()
            
            # Check if this was the last step
            next_step = current_step + 1
            next_step_data = next(
                (step for step in flow["steps"] if step["id"] == next_step), 
                None
            )
            
            if next_step_data:
                # Move to next step
                session_data["current_step"] = next_step
                await save_user_session(session_id, session_data)
                
                is_final_step = next_step == len(flow["steps"])
                
                logger.info(f"📝 Moving to step {next_step} for session {session_id}")
                
                return {
                    "session_id": session_id,
                    "question": next_step_data["question"],
                    "step_id": next_step_data["id"],
                    "is_final_step": is_final_step,
                    "flow_completed": False,
                    "ai_mode": False,
                    "phone_collected": False
                }
            else:
                # Flow completed, save lead and ask for phone
                return await self._complete_flow(session_id, session_data, flow)
                
        except Exception as e:
            logger.error(f"❌ Error processing response for session {session_id}: {str(e)}")
            # Fallback to AI mode on error
            return await self._switch_to_ai_mode(session_id, user_response)
    
    def _is_response_relevant(self, response: str, step_data: Dict[str, Any]) -> bool:
        """
        Basic relevance check for user responses.
        
        Args:
            response (str): User's response
            step_data (Dict[str, Any]): Current step data
            
        Returns:
            bool: True if response seems relevant
        """
        response_lower = response.lower().strip()
        
        # Very short responses are likely irrelevant
        if len(response_lower) < 2:
            return False
        
        # Common irrelevant responses
        irrelevant_patterns = [
            "oi", "olá", "hello", "hi", "tchau", "bye", "obrigado", "thanks",
            "ok", "tá", "sim", "não", "yes", "no", "???", "???"
        ]
        
        # If response is just a greeting or very generic, it's likely irrelevant
        if response_lower in irrelevant_patterns:
            return False
        
        # For name field, check if it looks like a name
        if step_data.get("field") == "name":
            # Names should have at least 2 characters and not be numbers
            if len(response_lower) < 2 or response_lower.isdigit():
                return False
        
        # For area of law, check if it contains legal-related terms or numbers
        if step_data.get("field") == "area_of_law":
            legal_terms = ["penal", "civil", "trabalhista", "criminal", "família", "empresarial", "1", "2", "3", "4"]
            if not any(term in response_lower for term in legal_terms):
                return False
        
        return True
    
    async def _complete_flow(self, session_id: str, session_data: Dict[str, Any], flow: Dict[str, Any]) -> Dict[str, Any]:
        """
        Complete the guided flow and save lead data, then ask for phone.
        
        Args:
            session_id (str): Session identifier
            session_data (Dict[str, Any]): Current session data
            flow (Dict[str, Any]): Conversation flow configuration
            
        Returns:
            Dict[str, Any]: Phone collection message
        """
        try:
            # Prepare lead data
            responses = session_data.get("responses", {})
            lead_data = {
                "name": responses.get("name", "Unknown"),
                "area_of_law": responses.get("area_of_law", "Not specified"),
                "situation": responses.get("situation", "Not provided"),
                "wants_meeting": responses.get("wants_meeting", "Not specified"),
                "session_id": session_id,
                "completed_at": datetime.now(),
                "status": "intake_completed"
            }
            
            # Save lead to Firebase
            lead_id = await save_lead_data(lead_data)
            
            # Update session - flow completed, now collecting phone
            session_data.update({
                "flow_completed": True,
                "ai_mode": False,  # Not in AI mode yet
                "phone_collected": False,  # Now collecting phone
                "lead_id": lead_id,
                "completed_at": datetime.now(),
                "last_updated": datetime.now()
            })
            
            await save_user_session(session_id, session_data)
            
            # Phone collection message
            phone_message = """Obrigado por fornecer essas informações! 

Para finalizar seu atendimento e conectá-lo diretamente com nossa equipe jurídica, preciso do seu número de WhatsApp.

Por favor, digite seu número completo com DDD (exemplo: 11999999999):"""
            
            logger.info(f"✅ Completed flow for session {session_id}, created lead {lead_id}, now collecting phone")
            
            return {
                "session_id": session_id,
                "question": phone_message,
                "flow_completed": True,
                "ai_mode": False,
                "phone_collected": False,
                "lead_saved": True,
                "lead_id": lead_id,
                "collecting_phone": True
            }
            
        except Exception as e:
            logger.error(f"❌ Error completing flow: {str(e)}")
            return await self._switch_to_ai_mode(session_id, "Thank you for your information.")
    
    async def _handle_phone_collection(self, session_id: str, session_data: Dict[str, Any], user_response: str) -> Dict[str, Any]:
        """
        Handle phone number collection and WhatsApp trigger.
        
        Args:
            session_id (str): Session identifier
            session_data (Dict[str, Any]): Current session data
            user_response (str): User's phone number response
            
        Returns:
            Dict[str, Any]: Confirmation and AI mode activation
        """
        try:
            # Basic phone validation
            phone_clean = ''.join(filter(str.isdigit, user_response))
            
            if len(phone_clean) < 10 or len(phone_clean) > 11:
                return {
                    "session_id": session_id,
                    "question": "Por favor, digite um número válido com DDD (exemplo: 11999999999):",
                    "flow_completed": True,
                    "ai_mode": False,
                    "phone_collected": False,
                    "collecting_phone": True,
                    "validation_error": True
                }
            
            # Format phone number for WhatsApp
            if len(phone_clean) == 10:
                # Add 9 for mobile numbers without it
                phone_formatted = f"55{phone_clean[:2]}9{phone_clean[2:]}"
            else:
                phone_formatted = f"55{phone_clean}"
            
            # Save phone number
            session_data.update({
                "phone_collected": True,
                "ai_mode": True,
                "phone_number": phone_clean,
                "phone_formatted": phone_formatted,
                "last_updated": datetime.now()
            })
            
            await save_user_session(session_id, session_data)
            
            # Update lead with phone number
            responses = session_data.get("responses", {})
            lead_data = {
                "phone_number": phone_clean,
                "phone_formatted": phone_formatted,
                "status": "phone_collected",
                "updated_at": datetime.now()
            }
            
            # Trigger WhatsApp message
            user_name = responses.get("name", "Cliente")
            whatsapp_message = f"""Olá {user_name}! 👋

Recebemos suas informações através do nosso chatbot e nossa equipe jurídica está pronta para ajudá-lo.

📋 *Resumo do seu caso:*
• Área: {responses.get("area_of_law", "Não especificada")}
• Situação: {responses.get("situation", "Não informada")[:100]}...

Em breve entraremos em contato para agendar uma consulta personalizada.

Atenciosamente,
Equipe Jurídica"""
            
            # Send WhatsApp message
            whatsapp_success = False
            try:
                whatsapp_success = await baileys_service.send_whatsapp_message(
                    f"{phone_formatted}@s.whatsapp.net", 
                    whatsapp_message
                )
                logger.info(f"📱 WhatsApp message sent to {phone_formatted}: {whatsapp_success}")
            except Exception as whatsapp_error:
                logger.error(f"❌ Failed to send WhatsApp message: {str(whatsapp_error)}")
            
            # Confirmation message
            confirmation_message = f"""Perfeito! Confirmamos seu número: {phone_clean}

✅ Suas informações foram registradas com sucesso
📱 Enviamos uma mensagem para seu WhatsApp
👨‍💼 Nossa equipe entrará em contato em breve

Agora posso responder outras dúvidas que você tenha sobre nossos serviços jurídicos. Como posso ajudá-lo?"""
            
            logger.info(f"✅ Phone collected for session {session_id}: {phone_clean}, WhatsApp sent: {whatsapp_success}")
            
            return {
                "session_id": session_id,
                "response": confirmation_message,
                "flow_completed": True,
                "ai_mode": True,
                "phone_collected": True,
                "whatsapp_sent": whatsapp_success,
                "phone_number": phone_clean
            }
            
        except Exception as e:
            logger.error(f"❌ Error handling phone collection: {str(e)}")
            return {
                "session_id": session_id,
                "response": "Ocorreu um erro ao processar seu número. Vamos prosseguir - como posso ajudá-lo com questões jurídicas?",
                "flow_completed": True,
                "ai_mode": True,
                "phone_collected": True,
                "error": str(e)
            }
    
    async def _switch_to_ai_mode(self, session_id: str, user_message: str) -> Dict[str, Any]:
        """
        Switch to AI mode and process user message.
        
        Args:
            session_id (str): Session identifier
            user_message (str): User's message
            
        Returns:
            Dict[str, Any]: AI response
        """
        try:
            # Update session to AI mode
            session_data = await get_user_session(session_id) or {}
            session_data.update({
                "ai_mode": True,
                "flow_completed": True,
                "phone_collected": True,  # Skip phone collection in error cases
                "switched_to_ai_at": datetime.now(),
                "last_updated": datetime.now()
            })
            await save_user_session(session_id, session_data)
            
            # Get AI response
            ai_response = await process_chat_message(user_message, session_id=session_id)
            
            logger.info(f"🤖 Switched to AI mode for session {session_id}")
            
            return {
                "session_id": session_id,
                "response": ai_response,
                "ai_mode": True,
                "flow_completed": True,
                "phone_collected": True
            }
            
        except Exception as e:
            logger.error(f"❌ Error switching to AI mode: {str(e)}")
            return {
                "session_id": session_id,
                "response": "Estou aqui para ajudá-lo com questões jurídicas. Como posso auxiliá-lo?",
                "ai_mode": True,
                "flow_completed": True,
                "phone_collected": True
            }
    
    async def get_conversation_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get current conversation status for a session.
        
        Args:
            session_id (str): Session identifier
            
        Returns:
            Dict[str, Any]: Current conversation state
        """
        try:
            session_data = await get_user_session(session_id)
            if not session_data:
                return {"exists": False}
            
            flow = await self.get_flow()
            current_step = session_data.get("current_step", 1)
            
            return {
                "exists": True,
                "session_id": session_id,
                "current_step": current_step,
                "total_steps": len(flow["steps"]),
                "flow_completed": session_data.get("flow_completed", False),
                "ai_mode": session_data.get("ai_mode", False),
                "phone_collected": session_data.get("phone_collected", False),
                "responses_collected": len(session_data.get("responses", {})),
                "started_at": session_data.get("started_at"),
                "last_updated": session_data.get("last_updated")
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting conversation status: {str(e)}")
            return {"exists": False, "error": str(e)}

# Global conversation manager instance
conversation_manager = ConversationManager()