"""
Encryption service for Storm Cloud Server.

AES-256-GCM with authenticated encryption per ADR 010.

Security requirements:
- Generic error messages only (no oracle attacks)
- Authentication tag always verified before output
- Detailed errors logged server-side only
"""

import base64
import logging
import os
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Constants
VERSION_AES_256_GCM = b"\x01"
NONCE_SIZE = 12
TAG_SIZE = 16  # GCM tag is 16 bytes
HEADER_SIZE = 1 + NONCE_SIZE  # version + nonce
OVERHEAD = HEADER_SIZE + TAG_SIZE  # 29 bytes total


class DecryptionError(Exception):
    """
    Generic decryption failure.

    SECURITY: Never expose why decryption failed.
    Details logged server-side only.
    """

    pass


class EncryptionService:
    """Handles all file encryption/decryption operations."""

    def __init__(self, method: Optional[str] = None):
        self.method = method or getattr(settings, "STORAGE_ENCRYPTION_METHOD", "none")
        self._master_key: Optional[bytes] = None

        if self.method != "none":
            self._master_key = self._load_master_key()

    def _load_master_key(self) -> bytes:
        """Load and decode master key from settings."""
        key_b64 = getattr(settings, "STORAGE_ENCRYPTION_KEY", "")
        if not key_b64:
            raise ValueError("STORAGE_ENCRYPTION_KEY not configured")
        # Add padding - token_urlsafe() strips it but b64decode needs it
        return base64.urlsafe_b64decode(key_b64 + "==")

    @property
    def is_enabled(self) -> bool:
        """Check if encryption is enabled."""
        return self.method != "none"

    @property
    def key_id(self) -> Optional[str]:
        """Get current key ID for metadata."""
        if not self.is_enabled:
            return None
        return getattr(settings, "STORAGE_ENCRYPTION_KEY_ID", "1")

    def encrypt_file(self, plaintext: bytes) -> bytes:
        """
        Encrypt file contents.

        Args:
            plaintext: Raw file bytes

        Returns:
            Encrypted blob with header (version + nonce + ciphertext + tag)
        """
        if not self.is_enabled:
            return plaintext

        # Import here to avoid startup errors when cryptography not installed
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(NONCE_SIZE)
        assert self._master_key is not None  # Guaranteed by is_enabled check above
        cipher = AESGCM(self._master_key)

        # GCM encrypt returns ciphertext with tag appended
        ciphertext_with_tag = cipher.encrypt(nonce, plaintext, None)

        return VERSION_AES_256_GCM + nonce + ciphertext_with_tag

    def decrypt_file(self, encrypted: bytes) -> bytes:
        """
        Decrypt file contents.

        Args:
            encrypted: Encrypted blob with header

        Returns:
            Decrypted plaintext bytes

        Raises:
            DecryptionError: On any decryption failure (generic, no details)
        """
        if not self.is_enabled:
            return encrypted

        # Mixed mode: detect plaintext files uploaded before encryption was enabled
        if len(encrypted) < HEADER_SIZE + TAG_SIZE:
            # Too short to be encrypted - return as plaintext
            logger.debug("File too short for encryption header, treating as plaintext")
            return encrypted

        if encrypted[0:1] != VERSION_AES_256_GCM:
            # No version byte = plaintext file in mixed mode
            logger.debug("Plaintext file detected (no version byte), returning as-is")
            return encrypted

        # File is encrypted - decrypt it
        try:
            # Import here to avoid startup errors when cryptography not installed
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = encrypted[1 : 1 + NONCE_SIZE]
            ciphertext_with_tag = encrypted[1 + NONCE_SIZE :]

            assert self._master_key is not None  # Guaranteed by is_enabled check above
            cipher = AESGCM(self._master_key)
            return cipher.decrypt(nonce, ciphertext_with_tag, None)

        except Exception as e:
            # Log detailed error for admin debugging
            logger.error(f"Decryption failed: {type(e).__name__}: {e}")
            # Raise generic error - NEVER expose why it failed
            raise DecryptionError("Decryption failed")

    def calculate_encrypted_size(self, plaintext_size: int) -> int:
        """Calculate size after encryption (for quota checks)."""
        if not self.is_enabled:
            return plaintext_size
        # Overhead: version (1) + nonce (12) + tag (16) = 29 bytes
        return plaintext_size + OVERHEAD

    def detect_encryption(self, data: bytes) -> str:
        """
        Detect encryption method from file header.

        Used by index rebuild to determine file state.

        Args:
            data: File content (at least first byte needed)

        Returns:
            'server' if encrypted with server-side encryption, 'none' if plaintext
        """
        if len(data) >= 1 and data[0:1] == VERSION_AES_256_GCM:
            return "server"
        return "none"
