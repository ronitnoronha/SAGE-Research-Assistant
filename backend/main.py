# main.py - FASTAPI BACKEND SERVER FOR SAGE RESEARCH ASSISTANT
import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

from rag_service import SupabaseRAGService

app = FastAPI(
    title="SAGE Research Assistant API",
    description="Supabase & Netlify Cloud Backend for Medical RAG",
    version="2.0.0"
)

# Enable CORS for Netlify frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global service instance
rag_service = SupabaseRAGService()

class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    answer: str
    sources: Optional[List[dict]] = None
    mode: Optional[str] = "supabase_pgvector"

@app.get("/")
def root():
    return {
        "system": "SAGE Medical Research Assistant API",
        "status": "online",
        "vector_db": "Supabase pgvector"
    }

@app.get("/health")
def health():
    return {"status": "ok", "supabase_configured": bool(rag_service.client)}

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload PDF file, extract text, compute embeddings, and insert into Supabase Vector DB"""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    try:
        contents = await file.read()
        result = rag_service.process_and_upload_pdf(file.filename, contents)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query", response_model=QueryResponse)
def query_medical_rag(request: QueryRequest):
    """Perform RAG vector query against Supabase"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    
    try:
        result = rag_service.query_rag(request.question)
        return result
    except Exception as e:
        import traceback
        err_detail = f"⚠️ Server Error processing query: {str(e)}\n\n{traceback.format_exc()}"
        print(f"❌ Exception in /query: {err_detail}", flush=True)
        return {
            "answer": err_detail,
            "sources": [],
            "mode": "error"
        }

@app.get("/documents")
def get_documents():
    """List indexed research documents stored in Supabase"""
    return {"documents": rag_service.list_documents()}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
