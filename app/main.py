# app/main.py
"""
RAG Application - Main Entry Point
Processes PDFs, generates embeddings, and provides query API
"""

import os
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from typing import List, Optional
from pydantic import BaseModel
import uvicorn

from services.pdf_processor import PDFProcessor
from services.embedding_service import EmbeddingService
from services.vector_store import VectorStore
from services.azure_blob_client import AzureBlobClient
from utils.security import mask_sensitive_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG Application",
    description="Retrieval-Augmented Generation service for PDF documents",
    version="1.0.0"
)

# Initialize services
pdf_processor = PDFProcessor()
embedding_service = EmbeddingService()
vector_store = VectorStore()
blob_client = AzureBlobClient()


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class QueryResponse(BaseModel):
    results: List[dict]
    query: str


@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes probes"""
    try:
        # Validate critical services
        vector_store.health_check()
        return {"status": "healthy", "service": "rag-application"}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail="Service unhealthy")


@app.get("/ready")
async def readiness_check():
    """Readiness check for Kubernetes"""
    try:
        vector_store.health_check()
        embedding_service.health_check()
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        raise HTTPException(status_code=503, detail="Service not ready")


@app.post("/upload")
async def upload_pdfs(files: List[UploadFile] = File(...)):
    """
    Upload and process multiple PDF files
    Validates: PDF processing, vectorization, storage
    """
    try:
        logger.info(f"Received {len(files)} files for processing")
        processed_files = []
        
        for file in files:
            if not file.filename.endswith('.pdf'):
                logger.warning(f"Skipping non-PDF file: {file.filename}")
                continue
            
            # Read file content
            content = await file.read()
            logger.info(f"Processing file: {mask_sensitive_data(file.filename)}")
            
            # Upload to Azure Blob Storage
            blob_url = await blob_client.upload_blob(file.filename, content)
            logger.info(f"✓ Uploaded to blob storage: {mask_sensitive_data(blob_url)}")
            
            # Extract text from PDF
            text_chunks = pdf_processor.extract_text(content, file.filename)
            logger.info(f"✓ Extracted {len(text_chunks)} text chunks from {file.filename}")
            
            # Generate embeddings
            embeddings = await embedding_service.generate_embeddings(text_chunks)
            logger.info(f"✓ Generated {len(embeddings)} embeddings")
            
            # Store in vector database
            doc_ids = await vector_store.store_vectors(
                embeddings=embeddings,
                texts=text_chunks,
                metadata={
                    "filename": file.filename,
                    "blob_url": blob_url,
                    "chunk_count": len(text_chunks)
                }
            )
            logger.info(f"✓ Stored vectors in database with {len(doc_ids)} document IDs")
            
            processed_files.append({
                "filename": file.filename,
                "chunks": len(text_chunks),
                "status": "success"
            })
        
        return JSONResponse(
            status_code=200,
            content={
                "message": f"Successfully processed {len(processed_files)} files",
                "files": processed_files
            }
        )
    
    except Exception as e:
        logger.error(f"Error processing PDFs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.post("/query", response_model=QueryResponse)
async def query_documents(request: QueryRequest):
    """
    Query the RAG system with semantic search
    Validates: Query embedding generation, vector search
    """
    try:
        logger.info(f"Processing query: {mask_sensitive_data(request.query)}")
        
        # Generate query embedding
        query_embedding = await embedding_service.generate_embeddings([request.query])
        logger.info("✓ Generated query embedding")
        
        # Search vector database
        results = await vector_store.search(
            query_embedding[0],
            top_k=request.top_k
        )
        logger.info(f"✓ Retrieved {len(results)} results from vector store")
        
        # Format results (mask sensitive data)
        formatted_results = [
            {
                "text": result["text"],
                "score": result["score"],
                "metadata": {
                    "filename": mask_sensitive_data(result["metadata"].get("filename", "")),
                    "chunk_id": result["metadata"].get("chunk_id", "")
                }
            }
            for result in results
        ]
        
        return QueryResponse(
            results=formatted_results,
            query=mask_sensitive_data(request.query)
        )
    
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@app.delete("/documents/{filename}")
async def delete_document(filename: str, confirm: bool = False):
    """
    Delete a document and its vectors (requires confirmation)
    Security: Requires explicit confirmation for destructive operation
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Destructive operation requires explicit confirmation. Set confirm=true"
        )
    
    try:
        logger.warning(f"Deleting document: {mask_sensitive_data(filename)}")
        
        # Delete from vector store
        deleted_count = await vector_store.delete_by_metadata("filename", filename)
        logger.info(f"✓ Deleted {deleted_count} vectors from database")
        
        # Delete from blob storage
        await blob_client.delete_blob(filename)
        logger.info(f"✓ Deleted blob: {mask_sensitive_data(filename)}")
        
        return {
            "message": f"Successfully deleted {filename}",
            "vectors_deleted": deleted_count
        }
    
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
