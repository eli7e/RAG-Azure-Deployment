# app/services/vector_store.py
"""
Vector Store Service
Manages vector storage and retrieval using Azure Cognitive Search
"""

import os
import logging
from typing import List, Dict, Any
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
)
from azure.core.credentials import AzureKeyCredential
import uuid

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self):
        self.service_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
        self.api_key = os.getenv("AZURE_SEARCH_API_KEY")
        self.index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "rag-documents")
        self.vector_dimensions = int(os.getenv("VECTOR_DIMENSIONS", "1536"))
        
        if not self.service_endpoint or not self.api_key:
            logger.warning("Azure Search credentials not configured, using mock mode")
            self.mock_mode = True
            self.mock_storage = []
        else:
            self.mock_mode = False
            self.credential = AzureKeyCredential(self.api_key)
            self.search_client = SearchClient(
                endpoint=self.service_endpoint,
                index_name=self.index_name,
                credential=self.credential
            )
            self._ensure_index_exists()
    
    def _ensure_index_exists(self):
        """Create search index if it doesn't exist"""
        try:
            index_client = SearchIndexClient(
                endpoint=self.service_endpoint,
                credential=self.credential
            )
            
            # Define index schema
            fields = [
                SearchField(
                    name="id",
                    type=SearchFieldDataType.String,
                    key=True,
                    filterable=True
                ),
                SearchField(
                    name="content",
                    type=SearchFieldDataType.String,
                    searchable=True
                ),
                SearchField(
                    name="embedding",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=self.vector_dimensions,
                    vector_search_profile_name="default-profile"
                ),
                SearchField(
                    name="filename",
                    type=SearchFieldDataType.String,
                    filterable=True,
                    facetable=True
                ),
                SearchField(
                    name="chunk_id",
                    type=SearchFieldDataType.Int32,
                    filterable=True
                ),
            ]
            
            # Configure vector search
            vector_search = VectorSearch(
                profiles=[
                    VectorSearchProfile(
                        name="default-profile",
                        algorithm_configuration_name="hnsw-config"
                    )
                ],
                algorithms=[
                    HnswAlgorithmConfiguration(name="hnsw-config")
                ]
            )
            
            index = SearchIndex(
                name=self.index_name,
                fields=fields,
                vector_search=vector_search
            )
            
            index_client.create_or_update_index(index)
            logger.info(f"✓ Search index '{self.index_name}' ready")
        
        except Exception as e:
            logger.error(f"Error creating search index: {str(e)}")
            raise
    
    async def store_vectors(
        self,
        embeddings: List[List[float]],
        texts: List[str],
        metadata: Dict[str, Any]
    ) -> List[str]:
        """
        Store vectors in Azure Cognitive Search
        Validates: Vectors stored successfully, returns document IDs
        """
        try:
            documents = []
            doc_ids = []
            
            for idx, (embedding, text) in enumerate(zip(embeddings, texts)):
                doc_id = str(uuid.uuid4())
                doc_ids.append(doc_id)
                
                document = {
                    "id": doc_id,
                    "content": text,
                    "embedding": embedding,
                    "filename": metadata.get("filename", ""),
                    "chunk_id": idx,
                }
                documents.append(document)
            
            if self.mock_mode:
                self.mock_storage.extend(documents)
                logger.info(f"✓ [MOCK] Stored {len(documents)} vectors")
            else:
                result = self.search_client.upload_documents(documents=documents)
                logger.info(f"✓ Stored {len(result)} vectors in Azure Search")
            
            return doc_ids
        
        except Exception as e:
            logger.error(f"Error storing vectors: {str(e)}")
            raise
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors
        Validates: Search completed, results returned
        """
        try:
            if self.mock_mode:
                # Simple mock search
                results = self.mock_storage[:top_k]
                logger.info(f"✓ [MOCK] Retrieved {len(results)} results")
                return [
                    {
                        "text": doc["content"],
                        "score": 0.95,
                        "metadata": {
                            "filename": doc["filename"],
                            "chunk_id": doc["chunk_id"]
                        }
                    }
                    for doc in results
                ]
            
            # Perform vector search
            search_results = self.search_client.search(
                search_text=None,
                vector_queries=[{
                    "vector": query_embedding,
                    "k_nearest_neighbors": top_k,
                    "fields": "embedding"
                }],
                select=["content", "filename", "chunk_id"]
            )
            
            results = []
            for result in search_results:
                results.append({
                    "text": result["content"],
                    "score": result["@search.score"],
                    "metadata": {
                        "filename": result["filename"],
                        "chunk_id": result["chunk_id"]
                    }
                })
            
            logger.info(f"✓ Retrieved {len(results)} results from Azure Search")
            return results
        
        except Exception as e:
            logger.error(f"Error searching vectors: {str(e)}")
            raise
    
    async def delete_by_metadata(self, field: str, value: str) -> int:
        """Delete documents by metadata field"""
        try:
            if self.mock_mode:
                initial_count = len(self.mock_storage)
                self.mock_storage = [
                    doc for doc in self.mock_storage
                    if doc.get(field) != value
                ]
                deleted = initial_count - len(self.mock_storage)
                logger.info(f"✓ [MOCK] Deleted {deleted} documents")
                return deleted
            
            # Search for documents to delete
            results = self.search_client.search(
                search_text="*",
                filter=f"{field} eq '{value}'",
                select=["id"]
            )
            
            doc_ids = [{"id": result["id"]} for result in results]
            
            if doc_ids:
                self.search_client.delete_documents(documents=doc_ids)
                logger.info(f"✓ Deleted {len(doc_ids)} documents")
            
            return len(doc_ids)
        
        except Exception as e:
            logger.error(f"Error deleting documents: {str(e)}")
            raise
    
    def health_check(self):
        """Verify vector store is operational"""
        if self.mock_mode:
            return True
        
        try:
            # Simple connectivity check
            self.search_client.get_document_count()
            return True
        except Exception as e:
            raise Exception(f"Vector store health check failed: {str(e)}")
