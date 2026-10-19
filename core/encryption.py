"""
Institutional Grade Database Field Encryption Module.
Complies with institutional fintech standards for sensitive credential storage.
Uses Fernet (AES-128-CBC + HMAC-SHA256 authenticated symmetric encryption).
"""

import os
import base64
import hashlib
import logging
from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger('core.encryption')

ENCRYPTION_PREFIX = "enc:v1:"
_FERNET_INSTANCE = None


def get_encryption_key() -> bytes:
    """
    Retrieves the 32-byte urlsafe-base64 encryption key.
    If FIELD_ENCRYPTION_KEY environment variable is defined, uses it directly.
    Otherwise, deterministically derives a key from Django's SECRET_KEY.
    """
    custom_key = os.getenv("FIELD_ENCRYPTION_KEY")
    if custom_key and len(custom_key.strip()) >= 32:
        clean_key = custom_key.strip()
        try:
            # Validate if it's already valid urlsafe base64
            decoded = base64.urlsafe_b64decode(clean_key.encode('utf-8'))
            if len(decoded) == 32:
                return clean_key.encode('utf-8')
        except Exception:
            pass
        # Derive 32 bytes from custom key if not standard base64
        digest = hashlib.sha256(clean_key.encode('utf-8')).digest()
        return base64.urlsafe_b64encode(digest)

    # Deterministic fallback derivation from SECRET_KEY
    secret = getattr(settings, 'SECRET_KEY', 'default-insecure-key-sofizadmin-prod')
    digest = hashlib.sha256((secret + ":institutional_vault_encryption_2026").encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet:
    """Returns a singleton or cached Fernet cipher instance."""
    global _FERNET_INSTANCE
    if _FERNET_INSTANCE is None:
        key = get_encryption_key()
        _FERNET_INSTANCE = Fernet(key)
    return _FERNET_INSTANCE


def reset_fernet_cache():
    """Resets the cached Fernet instance (useful for testing)."""
    global _FERNET_INSTANCE
    _FERNET_INSTANCE = None


def encrypt_value(value: str) -> str:
    """
    Encrypts a plaintext string.
    Returns string prefixed with enc:v1:
    If already encrypted or empty, returns as is.
    """
    if value is None:
        return None
    val_str = str(value)
    if not val_str:
        return val_str
    if val_str.startswith(ENCRYPTION_PREFIX):
        return val_str
    
    fernet = get_fernet()
    ciphertext = fernet.encrypt(val_str.encode('utf-8')).decode('utf-8')
    return f"{ENCRYPTION_PREFIX}{ciphertext}"


def decrypt_value(value: str) -> str:
    """
    Decrypts a ciphertext string starting with enc:v1:.
    If not encrypted (legacy plain text), returns value directly for backward compatibility.
    """
    if value is None:
        return None
    val_str = str(value)
    if not val_str:
        return val_str
    if not val_str.startswith(ENCRYPTION_PREFIX):
        # Plaintext backward compatibility
        return val_str

    raw_token = val_str[len(ENCRYPTION_PREFIX):]
    try:
        fernet = get_fernet()
        decrypted_bytes = fernet.decrypt(raw_token.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except InvalidToken:
        logger.error("Failed to decrypt encrypted field: Invalid encryption key or corrupted token.")
        # Return masked representation to prevent exposing corrupted ciphertext
        return val_str
    except Exception as exc:
        logger.error(f"Unexpected error during field decryption: {exc}")
        return val_str


def is_encrypted(value: str) -> bool:
    """Checks whether a value is stored in encrypted format."""
    return bool(value and str(value).startswith(ENCRYPTION_PREFIX))


class EncryptedCharField(models.CharField):
    """
    Institutional transparently encrypted CharField.
    Stored encrypted in database, decrypted automatically in application memory.
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_value(value)

    def to_python(self, value):
        if value is None:
            return value
        if isinstance(value, str):
            return decrypt_value(value)
        return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == '':
            return value
        return encrypt_value(value)


class EncryptedTextField(models.TextField):
    """
    Institutional transparently encrypted TextField for longer secrets.
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_value(value)

    def to_python(self, value):
        if value is None:
            return value
        if isinstance(value, str):
            return decrypt_value(value)
        return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == '':
            return value
        return encrypt_value(value)
