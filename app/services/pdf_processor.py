# app/services/pdf_processor.py
"""
PDF Processing Service
Extracts and chunks text from PDF files
"""

import io
import logging
from typing import List
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)


class PDFProcessor:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def extract_text(self, pdf_content: bytes, filename: str) -> List[str]:
        """
        Extract text from PDF and split into chunks
        Validates: Text extraction successful, chunks created
        """
        try:
            pdf_file = io.BytesIO(pdf_content)
            reader = PdfReader(pdf_file)
            
            # Extract text from all pages
            full_text = ""
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                full_text += text + "\n"
            
            if not full_text.strip():
                logger.warning(f"No text extracted from {filename}")
                return []
            
            logger.info(f"✓ Extracted {len(full_text)} characters from {filename}")
            
            # Split into chunks
            chunks = self._create_chunks(full_text)
            logger.info(f"✓ Created {len(chunks)} chunks")
            
            return chunks
        
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {str(e)}")
            raise
    
    def _create_chunks(self, text: str) -> List[str]:
        """Split text into overlapping chunks"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            
            if chunk.strip():
                chunks.append(chunk)
            
            start += self.chunk_size - self.chunk_overlap
        
        return chunks
