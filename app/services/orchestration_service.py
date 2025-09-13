"""
Intelligent Conversation Orchestration Service

This service manages intelligent conversation flow using AI (LangChain + Gemini)
instead of rigid Firebase flows. It handles context, memory, and natural dialogue.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from app.services.firebase_service import get_user_session, save_user_session, save_lead_data
from app.services.ai_chain import ai_orchestrator
from app.services.baileys_service import baileys_service

# Configure logging
logger = logging.getLogger(__name__)


class IntelligentOrchestrator:
    """
    Intelligent orchestrator that uses AI to manage conversation flow
    instead of rigid predefined steps.
    """
    
    def __init__(self):
        self.lead_fields = ["name", "area_of_law", "situation", "consent"]
    
    async def process_message(
        self, 
        message: str, 
        session_id: str, 
        phone_number: Optional[str] = None,
        platform: str = "web"
    ) -> Dict[str, Any]:
        """
        Process incoming message with intelligent AI orchestration.
        
        Args:
            message (str): User's message
            session_id (str): Session identifier
            phone_number (Optional[str]): User's phone number if available
            platform (str): Platform origin ("web", "whatsapp")
            
        Returns:
            Dict[str, Any]: AI response with context
        """
        try:
            logger.info(f"🎯 Processing message via AI orchestration - Session: {session_id}, Platform: {platform}")
            
            # Get or create session
            session_data = await self._get_or_create_session(session_id, platform, phone_number)
            
            # Extract any lead information from the message
            extracted_info = self._extract_lead_info(message, session_data)
            if extracted_info:
                session_data["lead_data"].update(extracted_info)
                await save_user_session(session_id, session_data)
                logger.info(f"📝 Updated lead data: {extracted_info}")
            
            # Prepare context for AI
            context = self._prepare_ai_context(session_data, platform)
            
            # Generate AI response
            ai_response = await ai_orchestrator.generate_response(
                message, 
                session_id, 
                context=context
            )
            
            # Check if we have enough information to save as lead
            if self._should_save_lead(session_data):
                await self._save_lead_if_ready(session_data)
            
            # Update session with last interaction
            session_data["last_message"] = message
            session_data["last_response"] = ai_response
            session_data["last_updated"] = datetime.now()
            session_data["message_count"] = session_data.get("message_count", 0) + 1
            await save_user_session(session_id, session_data)
            
            return {
                "response_type": "ai_intelligent",
                "platform": platform,
                "session_id": session_id,
                "response": ai_response,
                "ai_mode": True,
                "lead_data": session_data.get("lead_data", {}),
                "message_count": session_data.get("message_count", 1)
            }
            
        except Exception as e:
            logger.error(f"❌ Error in intelligent orchestration: {str(e)}")
            return {
                "response_type": "error",
                "platform": platform,
                "session_id": session_id,
                "response": "Desculpe, ocorreu um erro interno. Nossa equipe foi notificada e entrará em contato em breve.",
                "error": str(e)
            }
    
    async def _get_or_create_session(
        self, 
        session_id: str, 
        platform: str, 
        phone_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get existing session or create new one."""
        session_data = await get_user_session(session_id)
        
        if not session_data:
            session_data = {
                "session_id": session_id,
                "platform": platform,
                "phone_number": phone_number,
                "created_at": datetime.now(),
                "last_updated": datetime.now(),
                "lead_data": {},
                "message_count": 0,
                "lead_saved": False
            }
            await save_user_session(session_id, session_data)
            logger.info(f"🆕 Created new session: {session_id}")
        
        return session_data
    
    def _extract_lead_info(self, message: str, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract lead information from user message using simple heuristics.
        This could be enhanced with NLP in the future.
        """
        extracted = {}
        message_lower = message.lower()
        current_lead_data = session_data.get("lead_data", {})
        
        # Extract name (if not already collected)
        if not current_lead_data.get("name"):
            # Look for patterns that might indicate a name
            words = message.split()
            if len(words) >= 2 and not any(word in message_lower for word in [
                "direito", "advogado", "processo", "problema", "situação", "preciso", "quero"
            ]):
                # Might be a name if it's 2+ words and doesn't contain legal terms
                if all(word.isalpha() or word.replace(".", "").isalpha() for word in words[:2]):
                    extracted["name"] = " ".join(words[:2]).title()
        
        # Extract area of law
        legal_areas = {
            "penal": "Direito Penal",
            "criminal": "Direito Penal", 
            "civil": "Direito Civil",
            "trabalhista": "Direito Trabalhista",
            "trabalho": "Direito Trabalhista",
            "família": "Direito de Família",
            "divórcio": "Direito de Família",
            "empresarial": "Direito Empresarial",
            "empresa": "Direito Empresarial"
        }
        
        if not current_lead_data.get("area_of_law"):
            for keyword, area in legal_areas.items():
                if keyword in message_lower:
                    extracted["area_of_law"] = area
                    break
        
        # Extract situation (if message is descriptive)
        if not current_lead_data.get("situation") and len(message) > 20:
            situation_indicators = [
                "problema", "situação", "preciso", "aconteceu", "estou", 
                "tenho", "sofri", "fui", "recebi", "processo"
            ]
            if any(indicator in message_lower for indicator in situation_indicators):
                extracted["situation"] = message[:200]  # Limit to 200 chars
        
        # Extract consent (if user agrees to something)
        consent_indicators = [
            "sim", "quero", "aceito", "concordo", "pode", "ok", "claro", 
            "sim por favor", "pode ser", "tudo bem"
        ]
        if not current_lead_data.get("consent"):
            if any(indicator in message_lower for indicator in consent_indicators):
                extracted["consent"] = True
        
        return extracted
    
    def _prepare_ai_context(self, session_data: Dict[str, Any], platform: str) -> Dict[str, Any]:
        """Prepare context information for AI."""
        lead_data = session_data.get("lead_data", {})
        
        context = {
            "platform": platform,
            "message_count": session_data.get("message_count", 0),
            "session_age_minutes": (
                (datetime.now() - session_data.get("created_at", datetime.now())).seconds // 60
            )
        }
        
        # Add lead data to context
        if lead_data.get("name"):
            context["name"] = lead_data["name"]
        if lead_data.get("area_of_law"):
            context["area_of_law"] = lead_data["area_of_law"]
        if lead_data.get("situation"):
            context["situation"] = lead_data["situation"][:100]  # Truncate for context
        
        return context
    
    def _should_save_lead(self, session_data: Dict[str, Any]) -> bool:
        """Check if we have enough information to save as a lead."""
        lead_data = session_data.get("lead_data", {})
        
        # Save if we have at least name and one other piece of info
        has_name = bool(lead_data.get("name"))
        has_other_info = any([
            lead_data.get("area_of_law"),
            lead_data.get("situation"),
            lead_data.get("consent")
        ])
        
        return has_name and has_other_info and not session_data.get("lead_saved", False)
    
    async def _save_lead_if_ready(self, session_data: Dict[str, Any]):
        """Save lead data if we have enough information."""
        try:
            lead_data = session_data.get("lead_data", {})
            
            # Prepare lead data for saving
            lead_record = {
                "name": lead_data.get("name", "Unknown"),
                "area_of_law": lead_data.get("area_of_law", "Not specified"),
                "situation": lead_data.get("situation", "Not provided"),
                "consent": lead_data.get("consent", False),
                "phone_number": session_data.get("phone_number", ""),
                "platform": session_data.get("platform", "unknown"),
                "session_id": session_data["session_id"],
                "message_count": session_data.get("message_count", 0),
                "created_at": session_data.get("created_at", datetime.now()),
                "status": "ai_collected"
            }
            
            # Save to Firebase
            lead_id = await save_lead_data(lead_record)
            
            # Update session
            session_data["lead_saved"] = True
            session_data["lead_id"] = lead_id
            await save_user_session(session_data["session_id"], session_data)
            
            logger.info(f"💾 Saved lead data: {lead_id} for session {session_data['session_id']}")
            
        except Exception as e:
            logger.error(f"❌ Error saving lead data: {str(e)}")
    
    async def handle_phone_number_submission(
        self, 
        phone_number: str, 
        session_id: str
    ) -> Dict[str, Any]:
        """Handle phone number submission and trigger WhatsApp."""
        try:
            logger.info(f"📱 Handling phone submission: {phone_number} for session: {session_id}")
            
            # Get session data
            session_data = await get_user_session(session_id) or {}
            
            # Clean and format phone number
            phone_clean = ''.join(filter(str.isdigit, phone_number))
            
            # Add country code if missing (Brazilian format)
            if len(phone_clean) == 10:
                phone_formatted = f"55{phone_clean[:2]}9{phone_clean[2:]}"
            elif len(phone_clean) == 11:
                phone_formatted = f"55{phone_clean}"
            else:
                phone_formatted = phone_clean
            
            # Update session
            session_data.update({
                "phone_number": phone_clean,
                "phone_formatted": phone_formatted,
                "phone_submitted": True,
                "platform_transition": "web_to_whatsapp"
            })
            await save_user_session(session_id, session_data)
            
            # Prepare WhatsApp message
            lead_data = session_data.get("lead_data", {})
            user_name = lead_data.get("name", "Cliente")
            
            whatsapp_message = f"""Olá {user_name}! 👋

Recebemos sua solicitação através do nosso site e estou aqui para ajudá-lo com questões jurídicas.

Nossa equipe especializada está pronta para analisar seu caso. Vamos continuar nossa conversa aqui no WhatsApp para maior comodidade.

Como posso ajudá-lo hoje? 🤝"""
            
            # Send WhatsApp message
            whatsapp_success = False
            try:
                whatsapp_number = f"{phone_formatted}@s.whatsapp.net"
                whatsapp_success = await baileys_service.send_whatsapp_message(
                    whatsapp_number, 
                    whatsapp_message
                )
                logger.info(f"📱 WhatsApp message sent: {whatsapp_success}")
            except Exception as e:
                logger.error(f"❌ Failed to send WhatsApp: {str(e)}")
            
            return {
                "response_type": "phone_submitted",
                "session_id": session_id,
                "phone_number": phone_clean,
                "whatsapp_sent": whatsapp_success,
                "message": f"✅ Perfeito! {'Enviamos uma mensagem para seu WhatsApp. Continue a conversa por lá!' if whatsapp_success else 'Registramos seu número. Nossa equipe entrará em contato em breve.'}"
            }
            
        except Exception as e:
            logger.error(f"❌ Error handling phone submission: {str(e)}")
            return {
                "response_type": "error",
                "session_id": session_id,
                "message": "Ocorreu um erro ao processar seu número. Nossa equipe entrará em contato em breve.",
                "error": str(e)
            }
    
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """Get comprehensive session context."""
        try:
            session_data = await get_user_session(session_id) or {}
            ai_summary = ai_orchestrator.get_conversation_summary(session_id)
            
            return {
                "session_id": session_id,
                "session_data": session_data,
                "ai_conversation": ai_summary,
                "lead_data": session_data.get("lead_data", {}),
                "lead_saved": session_data.get("lead_saved", False),
                "platform": session_data.get("platform", "unknown"),
                "message_count": session_data.get("message_count", 0)
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting session context: {str(e)}")
            return {"error": str(e)}


# Global intelligent orchestrator instance
intelligent_orchestrator = IntelligentOrchestrator()

# Alias for backward compatibility
hybrid_orchestrator = intelligent_orchestrator