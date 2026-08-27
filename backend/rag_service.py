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

    def get_enhanced_matches(self, question: str) -> List[Dict[str, Any]]:
        """Multi-strategy search matching original rag_system.py precision"""
        search_queries = [
            question,
            question + " treatment medication criteria",
            question + " diagnosis findings recommendations"
        ]

        all_matches = []
        seen_snippets = set()

        for q in search_queries:
            try:
                emb = self.encode_text(q)
                rpc_res = self.client.rpc(
                    "match_documents",
                    {
                        "query_embedding": emb,
                        "match_threshold": 0.15,
                        "match_count": 4
                    }
                ).execute()

                matches = rpc_res.data or []
                for item in matches:
                    content_text = item.get("content") or ""
                    snippet = content_text[:100]
                    content_lower = content_text.lower()
                    if snippet and snippet not in seen_snippets and not any(skip in content_lower for skip in ["disclosures j.r.", "funding this work", "conflict of interest statement"]):
                        seen_snippets.add(snippet)
                        all_matches.append(item)
            except Exception as e:
                print(f"⚠️ Search strategy warning for '{q}': {e}", flush=True)

        return all_matches[:6]

    def query_rag(self, question: str, match_count: int = 5) -> Dict[str, Any]:
        """Perform Vector similarity search on Supabase & generate structured medical answer"""
        if not self.client:
            raise RuntimeError("Supabase client not configured.")

        # 1. Multi-strategy search (exact match to original rag_system.py)
        matches_to_use = self.get_enhanced_matches(question)

        if not matches_to_use:
            return {
                "answer": "No relevant evidence found in the research papers stored on Supabase.",
                "sources": [],
                "mode": "extractive_fallback"
            }

        # 2. Build context & source list
        context_blocks = []
        sources = []

        for item in matches_to_use:
            content = str(item.get("content") or "")
            meta = item.get("metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            context_blocks.append(content)
            sources.append({
                "source": str(meta.get("source") or "Research Paper"),
                "page": int(meta.get("page") or 1),
                "content": content[:300] + "..." if len(content) > 300 else content
            })

        context_str = "\n\n".join(context_blocks)

        # 3. Restored exact original Prompt Template from rag_system.py
        prompt = f"""You are a medical research expert. Analyze the following research papers and provide a comprehensive answer.

RESEARCH CONTEXT:
{context_str}

QUESTION: {question}

INSTRUCTIONS:
1. Extract ALL relevant information from the research context
2. Include specific numbers, criteria, and recommendations
3. If information is missing, say what you found and what's missing
4. Be precise and cite details from the papers

ANSWER:"""
        answer = None
        mode = "extractive_fallback"
        import requests

        # Provider 1: Groq API (LLaMA 3.3 70B - 14,400 requests/day free!)
        groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
        if groq_key and "your-groq-api-key" not in groq_key:
            for g_model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]:
                try:
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {
                        "Authorization": f"Bearer {groq_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": g_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "max_tokens": 2048
                    }
                    res = requests.post(url, headers=headers, json=payload, timeout=15)
                    if res.status_code == 200:
                        res_data = res.json()
                        choices = res_data.get("choices", [])
                        if choices:
                            text_out = choices[0].get("message", {}).get("content", "").strip()
                            if text_out:
                                answer = text_out
                                mode = f"groq_{g_model}"
                                print(f"✅ Groq response generated with {g_model}", flush=True)
                                break
                    else:
                        print(f"⚠️ Groq model {g_model} HTTP {res.status_code}: {res.text[:100]}", flush=True)
                except Exception as e:
                    print(f"⚠️ Groq call failed for {g_model}: {e}", flush=True)
                    continue

        # Provider 2: Google Gemini API (if Groq did not answer)
        if not answer:
            active_key = (os.getenv("GEMINI_API_KEY") or self.gemini_api_key or "").strip()
            is_valid_key = (
                active_key != ""
                and "your-google-gemini-api-key" not in active_key
            )
            if is_valid_key:
                model_candidates = ['gemini-3.5-flash', 'gemini-flash-latest', 'gemini-3.6-flash']
                for model_name in model_candidates:
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={active_key}"
                        headers = {"Content-Type": "application/json"}
                        payload = {
                            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048}
                        }
                        res = requests.post(url, headers=headers, json=payload, timeout=12)
                        if res.status_code == 200:
                            res_data = res.json()
                            candidates = res_data.get("candidates", [])
                            if candidates:
                                first_cand = candidates[0]
                                parts = first_cand.get("content", {}).get("parts", [])
                                if parts and "text" in parts[0] and parts[0]["text"].strip():
                                    answer = parts[0]["text"]
                                    mode = f"gemini_{model_name}_api"
                                    print(f"✅ Gemini response generated with {model_name}", flush=True)
                                    break
                    except Exception as e:
                        print(f"⚠️ Gemini call failed for {model_name}: {e}", flush=True)
                        continue

        # Provider 3: Extractive Fallback
        if not answer:
            answer = self._extractive_synthesis(question, matches_to_use)
            mode = "extractive_quota_fallback"

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
