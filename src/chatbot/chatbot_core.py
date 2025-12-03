"""Core chatbot functionality using Kimi AI."""

from typing import Dict, List, Optional
from langchain_openai import ChatOpenAI
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.chains import ConversationalRetrievalChain
from langchain.schema import AIMessage, HumanMessage, SystemMessage


class ChatbotCore:
    """Core chatbot functionality with Kimi AI integration."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str = "kimi-k2-turbo-preview",
        embedding_model_name: Optional[str] = None,
        text_splitter_config: Optional[Dict[str, int]] = None,
    ):
        """Initialize chatbot core.

        Args:
            api_key: API key for Kimi model.
            base_url: Base URL for Kimi API.
            model_name: Name of the Kimi model.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.embedding_model_name = embedding_model_name or "BAAI/bge-small-en-v1.5"
        self.text_splitter_config = text_splitter_config or {}
        self.llm = None
        self.embedding_model = None
        self.vector_store = None
        self.conversation_chain = None

    def initialize_models(self):
        """Initialize LLM and embedding models."""
        self.llm = self._create_llm()
        self.embedding_model = self._create_embedding_model()

    def _create_llm(self) -> ChatOpenAI:
        """Create and configure Kimi LLM.

        Returns:
            Configured ChatOpenAI instance.
        """
        return ChatOpenAI(
            model_name=self.model_name,
            temperature=0,
            streaming=True,
            openai_api_key=self.api_key,
            openai_api_base=self.base_url
        )

    def _create_embedding_model(self) -> FastEmbedEmbeddings:
        """Create and configure embedding model."""

        return FastEmbedEmbeddings(model_name=self.embedding_model_name)

    def create_vector_store(self, documents) -> Optional[FAISS]:
        """Create vector store from documents.

        Args:
            documents: List of document dictionaries.

        Returns:
            FAISS vector store or None if no documents.
        """
        if not documents:
            return None

        chunk_size = int(self.text_splitter_config.get('chunk_size', 1000))
        chunk_overlap = int(self.text_splitter_config.get('chunk_overlap', 200))
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        texts = []
        for doc in documents:
            chunks = text_splitter.split_text(doc['content'])
            for i, chunk in enumerate(chunks):
                texts.append({
                    'content': chunk,
                    'metadata': {'source': doc['name'], 'chunk': i}
                })

        if texts:
            contents = [text['content'] for text in texts]
            metadatas = [text['metadata'] for text in texts]
            embedding_model = self.embedding_model or self._create_embedding_model()
            self.embedding_model = embedding_model
            return FAISS.from_texts(contents, embedding_model, metadatas=metadatas)

        return None

    def create_conversation_chain(self, vector_store: Optional[FAISS] = None, system_prompt: Optional[str] = None):
        """Create conversational chain.

        Args:
            vector_store: Optional FAISS vector store for RAG.

        Returns:
            Conversational chain instance.
        """
        if vector_store:
            chain = ConversationalRetrievalChain.from_llm(
                llm=self.llm,
                retriever=vector_store.as_retriever(),
                verbose=False
            )
            return chain

        return _BasicConversationChain(self.llm, system_prompt=system_prompt)

    def get_llm(self) -> ChatOpenAI:
        """Get the configured LLM instance.

        Returns:
            ChatOpenAI instance.
        """
        if not self.llm:
            self.llm = self._create_llm()
        return self.llm


class _BasicConversationChain:
    """Lightweight replacement for the deprecated ConversationChain."""

    def __init__(self, llm: ChatOpenAI, system_prompt: Optional[str] = None):
        self.llm = llm
        self.history = []
        self.system_prompt = system_prompt

    def invoke(self, inputs, config=None):
        user_input = ""
        if isinstance(inputs, dict):
            user_input = inputs.get("input") or inputs.get("question") or ""
        else:
            user_input = str(inputs)

        if not user_input:
            return {"response": ""}

        messages = []
        if self.system_prompt:
            messages.append(SystemMessage(content=self.system_prompt))
        messages.extend(self.history)
        messages.append(HumanMessage(content=user_input))
        response = self.llm.invoke(messages, config)

        self.history.append(HumanMessage(content=user_input))
        if isinstance(response, AIMessage):
            self.history.append(response)
            content = response.content
        else:
            content = str(response)

        return {"response": content}
