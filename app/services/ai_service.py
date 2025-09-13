"""
AI Service Layer

Este módulo fornece funções de alto nível para interação com a camada de IA.
Ele atua como uma ponte entre os endpoints da API e a orquestração
LangChain + Gemini definida em `ai_chain.py`.
"""

import logging
from app.services.ai_chain import (
    process_chat_message,
    process_with_langchain,
    clear_conversation_memory,
    get_conversation_summary,
    ai_orchestrator,
)

# Configure logging
logger = logging.getLogger(__name__)


# -----------------------------
# Funções principais de serviço
# -----------------------------

async def process_chat_message_service(
    message: str, session_id: str = "default"
) -> str:
    """
    Processa a mensagem do usuário usando LangChain + Gemini.
    """
    try:
        logger.info(f"📨 Processando mensagem: {message[:50]}... (sessão={session_id})")

        # Sempre processa via LangChain
        response = await process_with_langchain(message, session_id=session_id)

        logger.info(f"✅ Resposta gerada: {response[:50]}...")
        return response

    except Exception as e:
        logger.error(f"❌ Erro no processamento da mensagem: {str(e)}")
        return (
            "Desculpe, ocorreu um erro ao processar sua mensagem. "
            "Por favor, tente novamente mais tarde."
        )


async def get_ai_service_status() -> dict:
    """
    Retorna o status atual do serviço de IA.
    """
    try:
        # Testa rapidamente se a IA responde
        test_response = await process_with_langchain("teste", session_id="__status__")
        ai_orchestrator.clear_session_memory("__status__")

        return {
            "service": "ai_service",
            "status": "active",
            "message": "LangChain + Gemini está operacional",
            "test_response": test_response[:50],
            "system_prompt_configured": bool(ai_orchestrator.system_prompt),
            "active_sessions": len(ai_orchestrator.get_conversation_summary("default")),
            "features": [
                "langchain_integration",
                "gemini_api",
                "conversation_memory",
                "session_management",
                "brazilian_portuguese_responses",
            ],
        }

    except Exception as e:
        logger.error(f"❌ Erro ao verificar status da IA: {str(e)}")
        return {
            "service": "ai_service",
            "status": "error",
            "error": str(e),
            "configuration_required": True,
        }


# -----------------------------
# Aliases para compatibilidade
# -----------------------------

# Alias para manter compatibilidade com `chat.py`
process_chat_message = process_chat_message_service

# Processamento de mensagens (compatível com versões antigas)
process_ai_message = process_chat_message_service

# Memória da conversa
clear_memory = clear_conversation_memory
get_summary = get_conversation_summary
