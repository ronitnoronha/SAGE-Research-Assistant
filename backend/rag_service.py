# rag_service.py - AGENTIC RAG SERVICE POWERED BY LANGCHAIN, SUPABASE & GROQ
import os
import io
import json
import re
import math
from typing import List, Dict, Any, Optional
from pypdf import PdfReader
from supabase import create_client, Client
import google.generativeai as genai

# LangChain Core Schemas & Tools
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field


# ==========================================
# 1. Pydantic Structured Output Models
# ==========================================

class SourceCitation(BaseModel):
    source: str = Field(description="Document source name or file path")
    page: int = Field(default=1, description="Page number of the citation")
    content: str = Field(description="Excerpt snippet supporting the answer")


class DocumentResponse(BaseModel):
    answer: str = Field(description="Detailed, accurate answer grounded in the document context")
    key_findings: List[str] = Field(default_factory=list, description="Key takeaways, metrics, or bullet points")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="List of source citations with page numbers")
    tools_used: List[str] = Field(default_factory=list, description="List of tools invoked during query execution")
    mode: str = Field(default="agentic_rag", description="Execution mode (groq_react, gemini_rag, extractive_fallback)")


# ==========================================
# 2. Main Autonomous RAG Service
# ==========================================

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
            self.client.storage.from_("research_papers").upload(
                file_name,
                file_bytes,
                file_options={"content-type": "application/pdf", "upsert": "true"}
            )
            print(f"✅ Uploaded {file_name} to Supabase Storage Bucket 'research_papers'", flush=True)
        except Exception as e:
            print(f"ℹ️ Storage bucket note for {file_name}: {e}", flush=True)

        # 2. Extract Text from PDF Pages using pypdf
        reader = PdfReader(io.BytesIO(file_bytes))
        total_pages = len(reader.pages)
        print(f"📖 Parsing {file_name} ({total_pages} pages)...", flush=True)

        all_records = []
        for page_idx, page in enumerate(reader.pages):
            page_num = page_idx + 1
            page_text = page.extract_text() or ""
            if not page_text.strip():
                continue

            chunks = self.chunk_text(page_text)
            for chunk_idx, chunk in enumerate(chunks):
                emb = self.encode_text(chunk)
                record = {
                    "content": chunk,
                    "metadata": {
                        "source": file_name,
                        "page": page_num,
                        "chunk_index": chunk_idx,
                        "total_pages": total_pages
                    },
                    "embedding": emb
                }
                all_records.append(record)

        # 3. Batch Insert into Supabase table 'documents'
        batch_size = 50
        for i in range(0, len(all_records), batch_size):
            batch = all_records[i:i + batch_size]
            self.client.table("documents").insert(batch).execute()

        print(f"🎉 Successfully inserted {len(all_records)} chunks into Supabase pgvector!", flush=True)

        return {
            "status": "success",
            "file_name": file_name,
            "pages_processed": total_pages,
            "chunks_inserted": len(all_records)
        }

    # ==========================================
    # 3. LangChain Tools Definitions
    # ==========================================

    def search_documents(self, query: str, match_count: int = 5) -> List[Dict[str, Any]]:
        """Vector similarity retrieval over Supabase pgvector"""
        if not self.client:
            return []

        search_queries = [
            query,
            query + " details findings summary"
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
                        "match_count": match_count
                    }
                ).execute()

                matches = rpc_res.data or []
                for item in matches:
                    content_text = item.get("content") or ""
                    snippet = content_text[:100]
                    content_lower = content_text.lower()
                    if snippet and snippet not in seen_snippets and not any(skip in content_lower for skip in ["disclosures j.r.", "funding this work", "conflict of interest"]):
                        seen_snippets.add(snippet)
                        all_matches.append(item)
            except Exception as e:
                print(f"⚠️ Vector search warning for '{q}': {e}", flush=True)

        return all_matches[:6]

    def calculate(self, expression: str) -> str:
        """Evaluate mathematical and statistical expressions safely"""
        try:
            # Sanitize expression: allow digits, operators, parens, decimal points, math functions
            clean_expr = re.sub(r"[^0-9\+\-\*\/\(\)\.\%\,\s]", "", expression)
            # Safe evaluation
            result = eval(clean_expr, {"__builtins__": None}, {"math": math})
            return f"Calculation Result: {clean_expr} = {result}"
        except Exception as e:
            return f"Calculation Error on '{expression}': {str(e)}"

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

    # ==========================================
    # 4. Multi-Turn Coreference Query Rewriter
    # ==========================================

    def contextualize_query(self, question: str, chat_history: Optional[List[Dict[str, str]]] = None) -> str:
        """Resolve pronouns & contextualize follow-up questions using recent chat history"""
        if not chat_history or len(chat_history) == 0:
            return question

        # Check if question has pronouns or is a follow-up
        pronoun_triggers = ["he", "she", "it", "they", "his", "her", "their", "this", "that", "these", "those", "previous", "earlier", "who", "whom"]
        words = question.lower().split()
        has_pronoun = any(p in words for p in pronoun_triggers) or len(words) < 5

        if not has_pronoun:
            return question

        # Format recent dialog
        history_snippet = []
        for msg in chat_history[-4:]:
            role = msg.get("role", "user")
            content = msg.get("content", "").strip()
            if content:
                history_snippet.append(f"{role.capitalize()}: {content}")

        history_text = "\n".join(history_snippet)

        groq_key = (os.getenv("GROQ_API_KEY") or "").strip().replace("GROQ_API_KEY=", "").replace('"', '').replace("'", "")
        if groq_key and "your-groq-api-key" not in groq_key:
            try:
                import requests
                rewriter_prompt = f"""Given the following conversation history and a follow-up question, rephrase the follow-up question into a standalone, complete search query.
DO NOT answer the question. Only return the rephrased search query. If the question is already complete, return it unchanged.

CONVERSATION HISTORY:
{history_text}

FOLLOW-UP QUESTION: {question}

STANDALONE SEARCH QUERY:"""

                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "allam-2-7b",
                    "messages": [{"role": "user", "content": rewriter_prompt}],
                    "temperature": 0.0,
                    "max_tokens": 100
                }
                res = requests.post(url, headers=headers, json=payload, timeout=6)
                if res.status_code == 200:
                    rewritten = res.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    # Clean tags if any
                    if "<think>" in rewritten:
                        if "</think>" in rewritten:
                            rewritten = rewritten.split("</think>")[-1].strip()
                        else:
                            rewritten = rewritten.split("<think>")[-1].strip()
                    if "thinking process" in rewritten.lower()[:300]:
                        for marker in ["Standalone", "Rephrased", "Query", "\n\n", ":"]:
                            if marker.lower() in rewritten.lower():
                                rewritten = rewritten.split(marker, 1)[-1].strip()
                                break
                    # Extract cleanest standalone string
                    rewritten = rewritten.strip('"`\' \n')
                    if "\n" in rewritten:
                        lines = [l.strip('"`\' ') for l in rewritten.split("\n") if l.strip() and not l.strip().startswith("#") and not l.strip().startswith("*") and not l.strip().startswith("-")]
                        if lines:
                            rewritten = lines[-1].strip('"`\' ')
                    if rewritten and len(rewritten) > 2 and len(rewritten) < 150:
                        print(f"🔄 Rephrased Query: '{question}' -> '{rewritten}'", flush=True)
                        return rewritten
            except Exception as e:
                print(f"⚠️ Contextualize query note: {e}", flush=True)

        return question

    # ==========================================
    # 5. Autonomous Query RAG Engine
    # ==========================================

    def query_rag(self, question: str, chat_history: Optional[List[Dict[str, str]]] = None, match_count: int = 5) -> Dict[str, Any]:
        """Execute Agentic RAG with multi-turn memory, vector search, and structured output"""
        if not self.client:
            raise RuntimeError("Supabase client not configured.")

        tools_used = []

        # Step 1: Resolve pronouns using chat history (LangChain Memory)
        standalone_query = self.contextualize_query(question, chat_history)
        if standalone_query != question:
            tools_used.append(f"query_rephrased: '{standalone_query}'")

        # Step 2: Retrieve relevant vector chunks (Retrieval)
        matches_to_use = self.search_documents(standalone_query, match_count=match_count)
        tools_used.append("supabase_vector_search")

        if not matches_to_use:
            return {
                "answer": f"No relevant information found in the indexed documents for query: '{standalone_query}'.",
                "key_findings": [],
                "sources": [],
                "tools_used": tools_used,
                "mode": "extractive_fallback"
            }

        # Step 3: Format Context & Citations
        context_blocks = []
        sources = []

        for item in matches_to_use:
            content = str(item.get("content") or "")
            meta = item.get("metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            context_blocks.append(content)
            sources.append({
                "source": str(meta.get("source") or "Document"),
                "page": int(meta.get("page") or 1),
                "content": content[:300] + "..." if len(content) > 300 else content
            })

        context_str = "\n\n".join(context_blocks)

        # Step 4: Build Dialog Messages & Prompt (LangChain Messages)
        dialog_context = ""
        if chat_history and len(chat_history) > 0:
            history_lines = [f"{m.get('role', 'user').capitalize()}: {m.get('content', '')}" for m in chat_history[-3:]]
            dialog_context = "RECENT CONVERSATION HISTORY:\n" + "\n".join(history_lines) + "\n\n"

        prompt = f"""You are SAGE, an intelligent document analysis and research assistant. Analyze the provided context from the uploaded documents and provide an accurate, clear, and comprehensive answer to the user's question.

{dialog_context}DOCUMENT CONTEXT:
{context_str}

USER QUESTION: {question}

INSTRUCTIONS:
1. Base your answer directly and thoroughly on the provided document context.
2. Extract all relevant facts, figures, key metrics, findings, and details.
3. If the context does not contain enough information to fully answer the question, clearly state what information is available and what is missing.
4. Structure the response clearly with logical sections or bullet points when appropriate.
5. Provide ONLY the final answer. DO NOT include any self-checks, verification steps, instruction checklists, thinking process, or meta-notes in your response.

ANSWER:"""

        answer = None
        key_findings = []
        mode = "extractive_fallback"
        import requests

        # Provider 1: Groq API (Qwen 3.6 27B / GPT-OSS 120B on LPU)
        groq_key = (os.getenv("GROQ_API_KEY") or "").strip().replace("GROQ_API_KEY=", "").replace('"', '').replace("'", "")
        if groq_key and "your-groq-api-key" not in groq_key:
            groq_models = ["qwen/qwen3.6-27b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "groq/compound-mini"]
            for g_model in groq_models:
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

                            # Strip thinking tags
                            if "<think>" in text_out:
                                if "</think>" in text_out:
                                    text_out = text_out.split("</think>")[-1].strip()
                                else:
                                    text_out = text_out.split("<think>")[-1].strip()

                            # Strip leading thinking process header
                            if "thinking process" in text_out.lower()[:300]:
                                for marker in ["###", "Based on", "Definition &", "1. ", "According to"]:
                                    if marker in text_out and text_out.find(marker) > 10:
                                        text_out = marker + text_out.split(marker, 1)[-1]
                                        break

                            # Strip trailing self-checks / verification blocks
                            for cut_marker in [
                                "Check Against Instructions",
                                "Self-Correction",
                                "Self-Verification",
                                "Verification during thought",
                                "All constraints met",
                                "Proceed. Output generation",
                                "Output matches",
                                "Structure in output:"
                            ]:
                                idx = text_out.lower().find(cut_marker.lower())
                                if idx != -1:
                                    text_out = text_out[:idx].strip()

                            if text_out:
                                answer = text_out
                                mode = f"groq_{g_model}"
                                print(f"✅ Groq Agentic answer generated with {g_model}", flush=True)
                                break
                    else:
                        print(f"⚠️ Groq model {g_model} HTTP {res.status_code}: {res.text[:100]}", flush=True)
                except Exception as e:
                    print(f"⚠️ Groq call failed for {g_model}: {e}", flush=True)
                    continue

        # Provider 2: Google Gemini API (if Groq was rate-limited or unavailable)
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

        # Structured Response Object
        response_obj = DocumentResponse(
            answer=answer,
            key_findings=key_findings,
            sources=sources,
            tools_used=tools_used,
            mode=mode
        )

        return response_obj.model_dump()

    def _extractive_synthesis(self, question: str, matches: List[Dict[str, Any]]) -> str:
        """Fallback synthesis directly from retrieved Supabase vector passages"""
        lines = [
            f"**Document Synthesis for:** *{question}*\n",
            "Extracted passages retrieved from Supabase Vector index:\n"
        ]
        for idx, item in enumerate(matches[:4], 1):
            meta = item.get("metadata", {})
            source_file = meta.get("source", "Document")
            page = meta.get("page", 1)
            content = item.get("content", "").strip().replace("\n", " ")
            lines.append(f"📌 **Excerpt {idx}** (*{source_file}*, Page {page}):")
            lines.append(f"> \"{content}\"\n")

        lines.append("ℹ️ *Extractive Mode active via Supabase `pgvector`.*")
        return "\n".join(lines)
