"""
Encryption utilities for storing sensitive data
"""
import base64
import hashlib
from cryptography.fernet import Fernet
from config import config


class Encryption:
    """Handle encryption/decryption of sensitive data"""
    
    def __init__(self):
        # Derive a valid Fernet key from the encryption key
        key = config.ENCRYPTION_KEY.encode()
        # Use SHA256 to get 32 bytes, then base64 encode for Fernet
        key_hash = hashlib.sha256(key).digest()
        self.fernet = Fernet(base64.urlsafe_b64encode(key_hash))
    
    def encrypt(self, data: str) -> str:
        """Encrypt a string"""
        if not data:
            return ''
        encrypted = self.fernet.encrypt(data.encode())
        return encrypted.decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt a string"""
        if not encrypted_data:
            return ''
        try:
            decrypted = self.fernet.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except Exception:
            return ''
    
    def mask_token(self, token: str, visible_chars: int = 8) -> str:
        """Mask a token for display"""
        if not token or len(token) <= visible_chars * 2:
            return '***'
        return f"{token[:visible_chars]}...{token[-visible_chars:]}"


encryption = Encryption()
