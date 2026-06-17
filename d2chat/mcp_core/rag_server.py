"""
rag_server.py
RAG 검색 서버 - FAISS 기반 문서 검색
"""
import os
import tempfile

from langchain_openai.embeddings import OpenAIEmbeddings
from langchain_core.prompts import PromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from azure.storage.blob import BlobServiceClient

from backend.app.config import settings
from d2chat.config import DEFAULT_LLM_MODEL

embeddings = OpenAIEmbeddings(model="text-embedding-3-large", api_key=settings.OPENAI_API_KEY)


class RAGServer:
    """FAISS 기반 RAG 검색 서버"""

    PROJECT_MAP = {
        1: "제약",
        3: "법률"
    }

    def __init__(self, llm_model: str = DEFAULT_LLM_MODEL):
        self.llm_model = llm_model
        from utilsPrj.supabase_client import get_service_client
        self.supabase = get_service_client()
        self._faiss_cache = {}  # container_name → FAISS db 캐시

    def _get_dirpath(self, projectid: int) -> str:
        """projectid로 Azure container 이름(dirpath) 조회"""
        response = (
            self.supabase
            .schema('rag')
            .table('projects')
            .select('dirpath')
            .eq('projectid', projectid)
            .execute()
        )
        projects = response.data or []
        if not projects:
            raise ValueError(f"projectid {projectid}에 해당하는 프로젝트가 없습니다.")
        return projects[0]['dirpath']

    def _load_faiss(self, container_name: str) -> FAISS:
        """Azure Blob에서 FAISS 로드 (캐시 적용)"""
        if container_name in self._faiss_cache:
            return self._faiss_cache[container_name]

        blob_service_client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(container_name)

        with tempfile.TemporaryDirectory() as tmpdir:
            blob_list = container_client.list_blobs(name_starts_with="vectordb/")
            for blob in blob_list:
                filename = os.path.basename(blob.name)
                local_path = os.path.join(tmpdir, filename)
                blob_client = container_client.get_blob_client(blob.name)
                with open(local_path, "wb") as f:
                    f.write(blob_client.download_blob().readall())

            db = FAISS.load_local(
                tmpdir,
                embeddings,
                allow_dangerous_deserialization=True
            )

        self._faiss_cache[container_name] = db
        return db

    def search(self, question: str, projectid: int = 1) -> str:
        """
        RAG 검색 후 LLM 답변 반환

        Args:
            question: 사용자 질문
            projectid: 1=제약, 3=법률

        Returns:
            LLM 답변 문자열
        """
        try:
            container_name = self._get_dirpath(projectid)
            db = self._load_faiss(container_name)

            retriever = db.as_retriever(
                search_type="mmr",
                search_kwargs={
                    "k": 10,
                    "fetch_k": 20,
                    "lambda_mult": 0.6,
                }
            )

            template = """
You are an assistant for question-answering tasks.
Use the following pieces of retrieved context to answer the question.
If you don't know the answer, just say that you don't know.
Answer in Korean.

답변은 ##Context에 포함된 내용을 기반으로 작성해주세요.
설명을 요구하는 질문은 이해할 수 있도록 기술해 주세요.
##Context에서 질문에 대한 답을 찾을 수 없는 경우 답을 찾지 못했음을 알려주세요.

##Question:
{question}

##Context:
{context}

##Answer in Korean:
"""
            prompt = PromptTemplate.from_template(template)

            if "claude" in self.llm_model:
                llm = ChatAnthropic(model=self.llm_model, temperature=0, api_key=settings.CLAUDE_API_KEY)
            else:
                llm = ChatOpenAI(model=self.llm_model, temperature=0, api_key=settings.OPENAI_API_KEY)

            chain = (
                {"context": retriever, "question": RunnablePassthrough()}
                | prompt
                | llm
                | StrOutputParser()
            )

            return chain.invoke(question)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"RAG 검색 오류: {str(e)}"
