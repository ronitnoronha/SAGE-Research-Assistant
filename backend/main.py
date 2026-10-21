# main.py - FASTAPI BACKEND SERVER FOR SAGE RESEARCH ASSISTANT
import os
import traceback
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

from rag_service import SupabaseRAGService

app = FastAPI(
    title="SAGE Document Research Assistant API",
    description="Supabase & Netlify Cloud Backend for Universal Document RAG",
    version="2.1.0"
)

# Only the SAGE frontend may call this API from a browser.
# Override with a comma-separated ALLOWED_ORIGINS env var (e.g. when the Netlify URL changes).
DEFAULT_ORIGINS = "https://neon-alfajores-a16cfc.netlify.app,http://localhost:8000,http://localhost:5500,http://127.0.0.1:5500"
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # auth uses a Bearer header, not cookies
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))

# Global service instance
rag_service = SupabaseRAGService()

class QueryRequest(BaseModel):
    question: str
    chat_history: Optional[List[Dict[str, str]]] = None

class QueryResponse(BaseModel):
    answer: str
    key_findings: Optional[List[str]] = None
    sources: Optional[List[dict]] = None
    tools_used: Optional[List[str]] = None
    mode: Optional[str] = "agentic_rag"

def require_user(authorization: Optional[str] = Header(None)):
    """Verify the Supabase session token sent by the frontend; reject the request if it's missing or invalid"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please sign in to use SAGE.")
    token = authorization.replace("Bearer ", "", 1).strip()
    try:
        user_res = rag_service.client.auth.get_user(token) if rag_service.client else None
        user = user_res.user if user_res else None
    except Exception as e:
        print(f"⚠️ Auth token verification failed: {e}", flush=True)
        user = None
    if not user:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    return user

@app.get("/")
def root():
    return {
        "system": "SAGE Document Research Assistant API",
        "status": "online",
        "vector_db": "Supabase pgvector"
    }

@app.get("/health")
def health():
    return {"status": "ok", "supabase_configured": bool(rag_service.client)}

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), user=Depends(require_user)):
    """Upload PDF file, extract text, compute embeddings, and insert into the user's library"""
    file_name = os.path.basename(file.filename or "").strip()
    if not file_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"That file is too large. The limit is {MAX_UPLOAD_MB} MB.")
    if not contents.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="That file isn't a valid PDF.")

    try:
        return rag_service.process_and_upload_pdf(file_name, contents, user_id=str(user.id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        print(f"❌ Exception in /upload:\n{traceback.format_exc()}", flush=True)
        raise HTTPException(status_code=500, detail="Indexing failed. Please try again.")

@app.post("/query")
def query_rag(request: QueryRequest, user=Depends(require_user)):
    """Perform Agentic RAG vector query with multi-turn memory against the user's documents"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        return rag_service.query_rag(request.question, user_id=str(user.id), chat_history=request.chat_history)
    except Exception:
        # Full details go to the server log only; the client gets a generic message
        print(f"❌ Exception in /query:\n{traceback.format_exc()}", flush=True)
        return {
            "answer": "Something went wrong while answering. Please try again.",
            "key_findings": [],
            "sources": [],
            "tools_used": [],
            "mode": "error"
        }

@app.get("/documents")
def get_documents(user=Depends(require_user)):
    """List the signed-in user's indexed documents"""
    return {"documents": rag_service.list_documents(user_id=str(user.id))}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
