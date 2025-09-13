"""
LangChain + Gemini Integration Service

Este módulo integra o LangChain com o Google Gemini para gerenciamento de
conversas inteligentes, memória e geração de respostas contextuais.
"""

import os
import logging
import json
from typing import Dict, Any
from dotenv import load_dotenv
from langchain.memory import ConversationBufferWindowMemory  # type: ignore
from langchain.schema import HumanMessage, AIMessage  # type: ignore
from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder  # type: ignore
from langchain.schema.runnable import RunnablePassthrough  # type: ignore
from langchain.schema.output_parser import StrOutputParser  # type: ignore

# 🔑 Carregar variáveis de ambiente
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

# Configuração de logging
logger = logging.getLogger(__name__)

# Memórias globais de conversas
conversation_memories: Dict[str, ConversationBufferWindowMemory] = {}


class AIOrchestrator:
    """AI Orchestrator usando LangChain + Gemini."""

    def __init__(self):
        self.llm = None
        self.system_prompt = None
        self.chain = None
        self._initialize_llm()
        self._load_system_prompt()
        self._setup_chain()

    def _initialize_llm(self):
        """Inicializa o LLM Gemini via LangChain."""
        try:
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                google_api_key=api_key,
                temperature=0.7,
                max_tokens=1000,
                timeout=30,
            )
            logger.info("✅ LangChain + Gemini LLM inicializado com sucesso")
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar LLM: {str(e)}")
            raise

    def _load_system_prompt(self):
        """Carrega o system prompt do .env, JSON ou usa o padrão."""
        try:
            env_prompt = os.getenv("AI_SYSTEM_PROMPT")
            if env_prompt:
                self.system_prompt = env_prompt
                return

            schema_file = "ai_schema.json"
            if os.path.exists(schema_file):
                with open(schema_file, "r", encoding="utf-8") as f:
                    schema_data = json.load(f)
                    self.system_prompt = schema_data.get("system_prompt", "")
                    return

            self.system_prompt = self._get_default_system_prompt()
        except Exception as e:
            logger.error(f"❌ Erro ao carregar system prompt: {str(e)}")
            self.system_prompt = self._get_default_system_prompt()

    def _get_default_system_prompt(self) -> str:
        """Prompt padrão caso não exista outro."""
        return """Você é um assistente jurídico especializado de um escritório de advocacia no Brasil.

DIRETRIZES IMPORTANTES:
- Responda SEMPRE em português brasileiro
- Mantenha respostas profissionais, concisas e focadas em questões jurídicas
- NÃO forneça aconselhamento jurídico específico ou definitivo
- Sempre recomende consulta presencial para casos específicos
- Use linguagem acessível, mas técnica quando necessário
- Demonstre empatia e compreensão
- Foque em orientações gerais e procedimentos legais
- Mencione a importância de documentação e prazos quando relevante

ÁREAS DE ESPECIALIZAÇÃO:
- Direito Penal
- Direito Civil  
- Direito Trabalhista
- Direito de Família
- Direito Empresarial

FORMATO DE RESPOSTA:
- Máximo 3 parágrafos
- Linguagem clara e objetiva
- Sempre termine sugerindo agendamento de consulta para análise detalhada

Você tem acesso ao histórico da conversa para fornecer respostas contextualizadas."""

    def _setup_chain(self):
        """Cria a LangChain conversation chain."""
        prompt = ChatPromptTemplate.from_messages(
            [
                ("human", self.system_prompt),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}"),
            ]
        )

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

    def _get_session_history(self, session_id: str) -> list:
        """Obtém histórico da sessão."""
        if session_id not in conversation_memories:
            conversation_memories[session_id] = ConversationBufferWindowMemory(
                k=10, return_messages=True
            )
        return conversation_memories[session_id].chat_memory.messages

    async def generate_response(self, message: str, session_id: str = "default") -> str:
        """Gera resposta usando LangChain + Gemini."""
        try:
            if session_id not in conversation_memories:
                conversation_memories[session_id] = ConversationBufferWindowMemory(
                    k=10, return_messages=True
                )

            memory = conversation_memories[session_id]
            response = await self.chain.ainvoke(
                {"input": message, "session_id": session_id}
            )

            memory.chat_memory.add_user_message(message)
            memory.chat_memory.add_ai_message(response)

            return response
        except Exception as e:
            logger.error(f"❌ Erro ao gerar resposta: {str(e)}")
            return (
                "Peço desculpas, mas estou enfrentando dificuldades técnicas no momento.\n\n"
                "Para garantir que você receba o melhor atendimento jurídico, recomendo "
                "que entre em contato diretamente com nossa equipe pelo WhatsApp "
                "ou agende uma consulta presencial."
            )

    def clear_session_memory(self, session_id: str):
        """Limpa memória de uma sessão."""
        if session_id in conversation_memories:
            del conversation_memories[session_id]

    def get_conversation_summary(self, session_id: str) -> Dict[str, Any]:
        """Resumo da conversa da sessão."""
        if session_id not in conversation_memories:
            return {"messages": 0, "summary": "Nenhum histórico"}

        messages = conversation_memories[session_id].chat_memory.messages
        return {
            "messages": len(messages),
            "last_messages": [
                {
                    "type": "human" if isinstance(m, HumanMessage) else "ai",
                    "content": m.content[:100]
                    + ("..." if len(m.content) > 100 else ""),
                }
                for m in messages[-4:]
            ],
        }


# ------------------------------
# Funções globais de conveniência
# ------------------------------

ai_orchestrator = AIOrchestrator()


async def process_chat_message(
    message: str, session_id: str = "default", use_langchain: bool = False
) -> str:
    """Processa mensagem com LangChain + Gemini."""
    return await ai_orchestrator.generate_response(message, session_id)


def clear_conversation_memory(session_id: str):
    ai_orchestrator.clear_session_memory(session_id)


def get_conversation_summary(session_id: str) -> Dict[str, Any]:
    return ai_orchestrator.get_conversation_summary(session_id)


# 🔄 Alias para compatibilidade com ai_service.py
async def process_with_langchain(message: str, session_id: str = "default") -> str:
    return await process_chat_message(message, session_id=session_id, use_langchain=True)
