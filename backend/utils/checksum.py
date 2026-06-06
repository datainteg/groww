"""
Groww API Checksum Generation
"""
import hashlib
import time


def generate_checksum(secret: str, timestamp: str = None) -> tuple:
    """
    Generate SHA-256 checksum for Groww API authentication.
    
    Args:
        secret: The API secret from Groww
        timestamp: Optional timestamp in epoch seconds (auto-generated if not provided)
    
    Returns:
        Tuple of (checksum, timestamp)
    """
    if timestamp is None:
        timestamp = str(int(time.time()))
    
    input_str = secret + timestamp
    sha256 = hashlib.sha256()
    sha256.update(input_str.encode('utf-8'))
    checksum = sha256.hexdigest()
    
    return checksum, timestamp


def get_current_timestamp() -> str:
    """Get current timestamp in epoch seconds"""
    return str(int(time.time()))
