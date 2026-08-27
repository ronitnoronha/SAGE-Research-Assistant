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
        all_records = []

        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                continue

            chunks = self.chunk_text(text)
            for chunk in chunks:
                # Generate embedding vector (384 float dimensions)
                embedding = self.encode_text(chunk)

                all_records.append({
                    "content": chunk,
                    "metadata": {
                        "source": file_name,
                        "page": page_num,
                        "total_pages": total_pages
                    },
                    "embedding": embedding
                })

        # 3. Batch insert records into Supabase in chunks of 50 (50x faster)
        batch_size = 50
        for i in range(0, len(all_records), batch_size):
            batch = all_records[i:i + batch_size]
            self.client.table("documents").insert(batch).execute()

        return {
            "status": "success",
            "file_name": file_name,
            "pages_processed": total_pages,
            "chunks_inserted": len(all_records)
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

        # Filter out boilerplate metadata (disclosures, acknowledgments, references)
        filtered_matches = []
        for item in matches:
            content_lower = item.get("content", "").lower()
            if any(skip_word in content_lower for skip_word in ["disclosures j.r.", "funding this work", "conflict of interest statement"]):
                continue
            filtered_matches.append(item)

        matches_to_use = filtered_matches if filtered_matches else matches

        # 3. Build context & source list
        context_blocks = []
        sources = []

        for item in matches_to_use[:4]:
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
        active_key = (os.getenv("GEMINI_API_KEY") or self.gemini_api_key or "").strip()
        is_valid_key = (
            active_key != ""
            and "your-google-gemini-api-key" not in active_key
        )

        if is_valid_key:
            prompt = f"""You are SAGE, an expert medical research assistant. Synthesize a clear, accurate, and comprehensive medical answer to the user's question based on the provided research paper context.

RESEARCH CONTEXT:
{context_str}

USER QUESTION:
{question}

ANSWER:"""
            answer = None
            
            # Method 1: Direct HTTP REST API (fastest, most reliable, no SDK version issues)
            import requests
            for model_name in ['gemini-3.6-flash', 'gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-pro']:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={active_key}"
                    headers = {"Content-Type": "application/json"}
                    payload = {"contents": [{"parts": [{"text": prompt}]}]}
                    
                    res = requests.post(url, headers=headers, json=payload, timeout=12)
                    if res.status_code == 200:
                        res_data = res.json()
                        candidates = res_data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts and "text" in parts[0]:
                                answer = parts[0]["text"]
                                mode = f"gemini_{model_name}_api"
                                print(f"✅ Gemini REST response generated with {model_name}", flush=True)
                                break
                    else:
                        print(f"⚠️ Gemini REST model {model_name} HTTP {res.status_code}: {res.text[:100]}", flush=True)
                except Exception as e:
                    print(f"⚠️ Gemini REST call failed for {model_name}: {e}", flush=True)
                    continue

            # Method 2: SDK Fallback if REST didn't return text
            if not answer:
                for model_name in ['gemini-3.6-flash', 'gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-pro']:
                    try:
                        llm = genai.GenerativeModel(model_name)
                        response = llm.generate_content(prompt)
                        if response and hasattr(response, 'text') and response.text:
                            answer = response.text
                            mode = f"gemini_{model_name}_sdk"
                            break
                    except Exception as e:
                        print(f"⚠️ SDK model {model_name} failed: {e}", flush=True)
                        continue

            if not answer:
                answer = self._extractive_synthesis(question, matches_to_use)
                mode = "extractive_fallback"
        else:
            answer = self._extractive_synthesis(question, matches_to_use)
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
