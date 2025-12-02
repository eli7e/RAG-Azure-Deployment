# app/utils/security.py
"""
Security utilities for data masking and privacy
"""

import re
import hashlib


def mask_sensitive_data(text: str, mask_char: str = "*") -> str:
    """
    Mask sensitive information in text
    - Email addresses
    - File paths
    - URLs (partial)
    """
    if not text:
        return text
    
    # Mask email addresses
    text = re.sub(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        lambda m: m.group(0)[:3] + mask_char * 5 + m.group(0)[-4:],
        text
    )
    
    # Mask file paths (keep first and last 10 chars)
    if len(text) > 30 and ('/' in text or '\\' in text):
        text = text[:10] + mask_char * 10 + text[-10:]
    
    return text


def hash_identifier(identifier: str) -> str:
    """Create a hash for identifiers (for logging)"""
    return hashlib.sha256(identifier.encode()).hexdigest()[:16]
