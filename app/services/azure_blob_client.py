# app/services/azure_blob_client.py
"""
Azure Blob Storage Client
Handles PDF file storage and retrieval
"""

import os
import logging
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)


class AzureBlobClient:
    def __init__(self):
        self.connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
        self.container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "pdf-documents")
        self.use_managed_identity = os.getenv("USE_MANAGED_IDENTITY", "true").lower() == "true"
        
        if not self.connection_string and not self.account_url:
            logger.warning("Azure Blob Storage not configured, using mock mode")
            self.mock_mode = True
        else:
            self.mock_mode = False
            self._initialize_client()
    
    def _initialize_client(self):
        """Initialize blob service client with authentication"""
        try:
            if self.use_managed_identity and self.account_url:
                # Use Managed Identity (recommended for production)
                credential = DefaultAzureCredential()
                self.blob_service_client = BlobServiceClient(
                    account_url=self.account_url,
                    credential=credential
                )
                logger.info("✓ Using Managed Identity for Blob Storage authentication")
            elif self.connection_string:
                # Use connection string (for development)
                self.blob_service_client = BlobServiceClient.from_connection_string(
                    self.connection_string
                )
                logger.info("✓ Using connection string for Blob Storage authentication")
            
            # Ensure container exists
            self._ensure_container_exists()
        
        except Exception as e:
            logger.error(f"Error initializing blob client: {str(e)}")
            raise
    
    def _ensure_container_exists(self):
        """Create container if it doesn't exist"""
        try:
            container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
            
            if not container_client.exists():
                container_client.create_container()
                logger.info(f"✓ Created container: {self.container_name}")
        
        except Exception as e:
            logger.error(f"Error ensuring container exists: {str(e)}")
            raise
    
    async def upload_blob(self, filename: str, content: bytes) -> str:
        """
        Upload PDF to blob storage
        Validates: Upload successful, returns blob URL
        """
        try:
            if self.mock_mode:
                mock_url = f"https://mockaccount.blob.core.windows.net/{self.container_name}/{filename}"
                logger.info(f"✓ [MOCK] Uploaded blob: {filename}")
                return mock_url
            
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=filename
            )
            
            # Upload with PDF content type
            blob_client.upload_blob(
                content,
                overwrite=True,
                content_settings=ContentSettings(content_type="application/pdf")
            )
            
            blob_url = blob_client.url
            logger.info(f"✓ Uploaded blob: {filename}")
            return blob_url
        
        except Exception as e:
            logger.error(f"Error uploading blob: {str(e)}")
            raise
    
    async def delete_blob(self, filename: str):
        """Delete blob from storage"""
        try:
            if self.mock_mode:
                logger.info(f"✓ [MOCK] Deleted blob: {filename}")
                return
            
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=filename
            )
            
            blob_client.delete_blob()
            logger.info(f"✓ Deleted blob: {filename}")
        
        except Exception as e:
            logger.error(f"Error deleting blob: {str(e)}")
            raise
