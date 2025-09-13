"""
LangChain + Gemini Integration Service

Este módulo integra o LangChain com o Google Gemini para gerenciamento de
conversas inteligentes, memória e geração de respostas contextuais.
"""

import os
import logging
import json
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Global conversation memories
conversation_memories: Dict[str, ConversationBufferWindowMemory] = {}


class AIOrchestrator:
    """AI Orchestrator using LangChain + Gemini for intelligent conversation management."""

    def __init__(self):
        self.llm = None
        self.system_prompt = None
        self.chain = None
        self._initialize_llm()
        self._load_system_prompt()
        self._setup_chain()

    def _initialize_llm(self):
        """Initialize Gemini LLM via LangChain."""
        try:
            # Get API key from environment - try both variable names
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            
            if not api_key:
                raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set")

            self.llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                google_api_key=api_key,
                temperature=0.7,
                max_tokens=1000,
                timeout=30,
            )
            logger.info("✅ LangChain + Gemini LLM initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error initializing LLM: {str(e)}")
            raise

    def _load_system_prompt(self):
        """Load system prompt from .env, JSON file, or use default."""
        try:
            # First try to load from environment variable
            env_prompt = os.getenv("AI_SYSTEM_PROMPT")
            if env_prompt:
                self.system_prompt = env_prompt
                logger.info("✅ System prompt loaded from environment variable")
                return

            # Try to load from ai_schema.json
            schema_file = "ai_schema.json"
            if os.path.exists(schema_file):
                with open(schema_file, "r", encoding="utf-8") as f:
                    schema_data = json.load(f)
                    self.system_prompt = schema_data.get("system_prompt", "")
                    if self.system_prompt:
                        logger.info("✅ System prompt loaded from ai_schema.json")
                        return

            # Use default system prompt
            self.system_prompt = self._get_default_system_prompt()
            logger.info("✅ Using default system prompt")
            
        except Exception as e:
            logger.error(f"❌ Error loading system prompt: {str(e)}")
            self.system_prompt = self._get_default_system_prompt()

    def _get_default_system_prompt(self) -> str:
        """Default system prompt for legal assistant."""
        return """Você é um assistente jurídico especializado de um escritório de advocacia no Brasil.

DIRETRIZES IMPORTANTES:
- Responda SEMPRE em português brasileiro
- Seja empático, profissional e acolhedor
- Aceite variações de respostas (ex: "quero", "sim por favor", "pode ser", "ok", "claro")
- Colete informações de forma natural, não rígida
- Use o contexto da conversa para personalizar respostas
- Guie a conversa naturalmente para agendamento de consulta

INFORMAÇÕES A COLETAR (quando necessário):
- Nome completo do cliente
- Área jurídica de interesse
- Descrição da situação
- Consentimento para contato

ÁREAS DE ESPECIALIZAÇÃO:
- Direito Penal
- Direito Civil  
- Direito Trabalhista
- Direito de Família
- Direito Empresarial

FORMATO DE RESPOSTA:
- Máximo 2-3 parágrafos para WhatsApp
- Linguagem clara e acessível
- Sempre demonstre interesse genuíno em ajudar
- Termine com pergunta ou próximo passo quando apropriado

CONTEXTO ESPECIAL:
- Quando receber informações do LeadPage, use-as para personalizar a conversa
- Adapte seu tom baseado na plataforma (WhatsApp vs Web)
- Mantenha histórico da conversa para continuidade

Você tem acesso ao histórico completo da conversa para fornecer respostas contextualizadas e personalizadas."""

    def _setup_chain(self):
        """Create LangChain conversation chain."""
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.system_prompt),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}"),
            ])

            self.chain = (
                RunnablePassthrough.assign(
                    history=lambda x: self._get_session_history(
                        x.get("session_id", "default")
                    )
                )
                | prompt
                | self.llm
                | StrOutputParser()
            )
            logger.info("✅ LangChain conversation chain setup complete")
        except Exception as e:
            logger.error(f"❌ Error setting up chain: {str(e)}")
            raise

    def _get_session_history(self, session_id: str) -> list:
        """Get session conversation history."""
        if session_id not in conversation_memories:
            conversation_memories[session_id] = ConversationBufferWindowMemory(
                k=10, return_messages=True
            )
        return conversation_memories[session_id].chat_memory.messages

    async def generate_response(
        self, 
        message: str, 
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate AI response using LangChain + Gemini with context."""
        try:
            if session_id not in conversation_memories:
                conversation_memories[session_id] = ConversationBufferWindowMemory(
                    k=10, return_messages=True
                )

            memory = conversation_memories[session_id]
            
            # Add context to message if provided
            contextual_message = message
            if context:
                context_info = []
                if context.get("name"):
                    context_info.append(f"Nome: {context['name']}")
                if context.get("area_of_law"):
                    context_info.append(f"Área jurídica: {context['area_of_law']}")
                if context.get("situation"):
                    context_info.append(f"Situação: {context['situation']}")
                if context.get("platform"):
                    context_info.append(f"Plataforma: {context['platform']}")
                
                if context_info:
                    contextual_message = f"[Contexto: {'; '.join(context_info)}] {message}"

            # Generate response
            response = await self.chain.ainvoke({
                "input": contextual_message, 
                "session_id": session_id
            })

            # Save to memory
            memory.chat_memory.add_user_message(message)
            memory.chat_memory.add_ai_message(response)

            logger.info(f"✅ Generated AI response for session {session_id}")
            return response

        except Exception as e:
            logger.error(f"❌ Error generating response: {str(e)}")
            return self._get_fallback_response()

    def _get_fallback_response(self) -> str:
        """Fallback response when AI fails."""
        return (
            "Peço desculpas, mas estou enfrentando dificuldades técnicas no momento.\n\n"
            "Para garantir que você receba o melhor atendimento jurídico, recomendo "
            "que entre em contato diretamente com nossa equipe pelo telefone "
            "ou agende uma consulta presencial."
        )

    def clear_session_memory(self, session_id: str):
        """Clear memory for a specific session."""
        if session_id in conversation_memories:
            del conversation_memories[session_id]
            logger.info(f"🧹 Cleared memory for session {session_id}")

    def get_conversation_summary(self, session_id: str) -> Dict[str, Any]:
        """Get conversation summary for a session."""
        if session_id not in conversation_memories:
            return {"messages": 0, "summary": "No conversation history"}

        messages = conversation_memories[session_id].chat_memory.messages
        return {
            "messages": len(messages),
            "last_messages": [
                {
                    "type": "human" if isinstance(m, HumanMessage) else "ai",
                    "content": m.content[:100] + ("..." if len(m.content) > 100 else ""),
                }
                for m in messages[-4:]
            ],
        }

    def get_system_prompt(self) -> str:
        """Get current system prompt."""
        return self.system_prompt


# Global AI orchestrator instance
ai_orchestrator = AIOrchestrator()


# Convenience functions for backward compatibility
async def process_chat_message(
    message: str, 
    session_id: str = "default", 
    context: Optional[Dict[str, Any]] = None
) -> str:
    """Process chat message with LangChain + Gemini."""
    return await ai_orchestrator.generate_response(message, session_id, context)


def clear_conversation_memory(session_id: str):
    """Clear conversation memory for session."""
    ai_orchestrator.clear_session_memory(session_id)


def get_conversation_summary(session_id: str) -> Dict[str, Any]:
    """Get conversation summary."""
    return ai_orchestrator.get_conversation_summary(session_id)


async def get_ai_service_status() -> Dict[str, Any]:
    """Get AI service status."""
    try:
        # Test AI response
        test_response = await ai_orchestrator.generate_response(
            "teste", 
            session_id="__status_test__"
        )
        ai_orchestrator.clear_session_memory("__status_test__")

        return {
            "service": "ai_service",
            "status": "active",
            "message": "LangChain + Gemini operational",
            "test_response_length": len(test_response),
            "system_prompt_configured": bool(ai_orchestrator.system_prompt),
            "api_key_configured": bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")),
            "features": [
                "langchain_integration",
                "gemini_api",
                "conversation_memory",
                "session_management",
                "context_awareness",
                "brazilian_portuguese_responses",
            ],
        }
    except Exception as e:
        logger.error(f"❌ Error checking AI service status: {str(e)}")
        return {
            "service": "ai_service",
            "status": "error",
            "error": str(e),
            "configuration_required": True,
        }


# Alias for compatibility
process_with_langchain = process_chat_message