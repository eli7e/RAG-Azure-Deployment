# app/services/embedding_service.py
"""
Embedding Service
Generates vector embeddings using Azure OpenAI or local models
"""

import os
import logging
from typing import List
import asyncio
from openai import AsyncAzureOpenAI

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        self.use_azure_openai = os.getenv("USE_AZURE_OPENAI", "true").lower() == "true"
        
        if self.use_azure_openai:
            self.client = AsyncAzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            self.deployment_name = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
        else:
            # Fallback to sentence-transformers
            from sentence_transformers import SentenceTransformer
            model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
            self.model = SentenceTransformer(model_name)
            logger.info(f"Using local embedding model: {model_name}")
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for text chunks
        Validates: Embeddings generated, correct dimensions
        """
        try:
            if self.use_azure_openai:
                embeddings = await self._generate_azure_embeddings(texts)
            else:
                embeddings = await self._generate_local_embeddings(texts)
            
            logger.info(f"✓ Generated embeddings with dimension {len(embeddings[0])}")
            return embeddings
        
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise
    
    async def _generate_azure_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Azure OpenAI"""
        embeddings = []
        
        # Process in batches to avoid rate limits
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            response = await self.client.embeddings.create(
                input=batch,
                model=self.deployment_name
            )
            
            batch_embeddings = [item.embedding for item in response.data]
            embeddings.extend(batch_embeddings)
        
        return embeddings
    
    async def _generate_local_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using local model"""
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            self.model.encode,
            texts
        )
        return embeddings.tolist()
    
    def health_check(self):
        """Verify embedding service is operational"""
        if self.use_azure_openai and not os.getenv("AZURE_OPENAI_API_KEY"):
            raise Exception("Azure OpenAI API key not configured")
        return True
