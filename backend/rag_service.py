# rag_service.py - SUPABASE POWERED VECTOR RAG SERVICE FOR SAGE
import os
import io
import json
from typing import List, Dict, Any, Optional
from pypdf import PdfReader
from supabase import create_client, Client
import google.generativeai as genai

class SupabaseRAGService:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_key = os.getenv("SUPABASE_KEY", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")

        self.client: Optional[Client] = None
        if self.supabase_url and self.supabase_key:
            self.client = create_client(self.supabase_url, self.supabase_key)

        self._encoder = None

        # Initialize Gemini if key exists
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            self.llm = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.llm = None

    def get_encoder(self):
        """Lazy load lightweight ONNX embedding model (fastembed) using <50MB RAM"""
        if self._encoder is None:
            print("⚡ Loading ultra-lightweight ONNX embedding model (fastembed BAAI/bge-small-en-v1.5)...")
            from fastembed import TextEmbedding
            self._encoder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        return self._encoder

    def encode_text(self, text: str) -> List[float]:
        """Generate 384-dimensional vector embedding using fastembed"""
        encoder = self.get_encoder()
        embeddings = list(encoder.embed([text]))
        return [float(x) for x in embeddings[0]]

    def chunk_text(self, text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
        """Split document text into overlapping chunks"""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start += chunk_size - overlap
        return chunks

    def process_and_upload_pdf(self, file_name: str, file_bytes: bytes) -> Dict[str, Any]:
        """Process PDF bytes, extract chunks, compute embeddings & insert into Supabase"""
        if not self.client:
            raise RuntimeError("Supabase client not configured. Set SUPABASE_URL and SUPABASE_KEY.")

        # 1. Upload PDF to Supabase Storage Bucket ('research_papers')
        try:
            storage_path = f"papers/{file_name}"
            self.client.storage.from_("research_papers").upload(
                path=storage_path,
                file=file_bytes,
                file_options={"upsert": "true"}
            )
        except Exception as e:
            print(f"⚠️ Storage upload warning: {e}")

        # 2. Extract text from PDF using PyPDF
        reader = PdfReader(io.BytesIO(file_bytes))
        total_pages = len(reader.pages)
        inserted_chunks = 0

        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                continue

            chunks = self.chunk_text(text)
            for chunk in chunks:
                # Generate embedding vector (384 float dimensions)
                embedding = self.encode_text(chunk)

                # Insert chunk into Supabase Postgres documents table
                record = {
                    "content": chunk,
                    "metadata": {
                        "source": file_name,
                        "page": page_num,
                        "total_pages": total_pages
                    },
                    "embedding": embedding
                }

                self.client.table("documents").insert(record).execute()
                inserted_chunks += 1

        return {
            "status": "success",
            "file_name": file_name,
            "pages_processed": total_pages,
            "chunks_inserted": inserted_chunks
        }

    def query_rag(self, question: str, match_count: int = 5) -> Dict[str, Any]:
        """Perform Vector similarity search on Supabase & generate answer"""
        if not self.client:
            raise RuntimeError("Supabase client not configured.")

        # 1. Compute embedding for question
        query_embedding = self.encode_text(question)

        # 2. RPC call to match_documents in Supabase
        rpc_res = self.client.rpc(
            "match_documents",
            {
                "query_embedding": query_embedding,
                "match_threshold": 0.2,
                "match_count": match_count
            }
        ).execute()

        matches = rpc_res.data or []

        if not matches:
            return {
                "answer": "No relevant evidence found in the research papers stored on Supabase.",
                "sources": [],
                "mode": "extractive_fallback"
            }

        # 3. Build context & source list
        context_blocks = []
        sources = []

        for item in matches:
            content = item.get("content", "")
            meta = item.get("metadata", {})
            context_blocks.append(content)
            sources.append({
                "source": meta.get("source", "Research Paper"),
                "page": meta.get("page", 1),
                "content": content[:300] + "..." if len(content) > 300 else content
            })

        context_str = "\n\n".join(context_blocks)

        # 4. Generate answer via Cloud LLM API or Extractive Fallback
        if self.llm:
            prompt = f"""You are SAGE, a medical research assistant. Analyze the medical evidence context and answer the user question accurately with clinical clarity.

MEDICAL CONTEXT:
{context_str}

USER QUESTION:
{question}

ANSWER:"""
            try:
                response = self.llm.generate_content(prompt)
                answer = response.text
                mode = "gemini_cloud"
            except Exception as e:
                print(f"⚠️ Cloud LLM generation failed: {e}")
                answer = self._extractive_synthesis(question, matches)
                mode = "extractive_fallback"
        else:
            answer = self._extractive_synthesis(question, matches)
            mode = "extractive_fallback"

        return {
            "answer": answer,
            "sources": sources,
            "mode": mode
        }

    def _extractive_synthesis(self, question: str, matches: List[Dict[str, Any]]) -> str:
        """Fallback synthesis directly from retrieved Supabase vector passages"""
        lines = [
            f"**Medical Document Synthesis for:** *{question}*\n",
            "Extracted clinical passages retrieved from Supabase Vector index:\n"
        ]
        for idx, item in enumerate(matches[:4], 1):
            meta = item.get("metadata", {})
            source_file = meta.get("source", "Medical Document")
            page = meta.get("page", 1)
            content = item.get("content", "").strip().replace("\n", " ")
            lines.append(f"📌 **Excerpt {idx}** (*{source_file}*, Page {page}):")
            lines.append(f"> \"{content}\"\n")

        lines.append("ℹ️ *Extractive Mode active via Supabase `pgvector`. Add `GEMINI_API_KEY` for generative answers.*")
        return "\n".join(lines)

    def list_documents(self) -> List[Dict[str, Any]]:
        """List distinct documents stored in Supabase"""
        if not self.client:
            return []
        try:
            res = self.client.table("documents").select("metadata").execute()
            docs = {}
            for item in (res.data or []):
                meta = item.get("metadata", {})
                source = meta.get("source")
                if source:
                    docs[source] = docs.get(source, 0) + 1
            return [{"source": k, "chunk_count": v} for k, v in docs.items()]
        except Exception as e:
            print(f"Error fetching documents: {e}")
            return []
