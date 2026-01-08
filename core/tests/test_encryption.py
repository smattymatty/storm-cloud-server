"""Tests for encryption service (ADR 010)."""

import base64
import secrets

from django.test import TestCase, override_settings

from core.services.encryption import (
    HEADER_SIZE,
    NONCE_SIZE,
    OVERHEAD,
    TAG_SIZE,
    VERSION_AES_256_GCM,
    DecryptionError,
    EncryptionService,
)


def generate_test_key() -> str:
    """Generate a valid encryption key for testing."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


TEST_KEY = generate_test_key()


class EncryptionServiceDisabledTest(TestCase):
    """Tests when encryption is disabled (default)."""

    @override_settings(STORAGE_ENCRYPTION_METHOD="none")
    def test_is_enabled_returns_false(self):
        """is_enabled should return False when method is 'none'."""
        service = EncryptionService()
        self.assertFalse(service.is_enabled)

    @override_settings(STORAGE_ENCRYPTION_METHOD="none")
    def test_encrypt_returns_plaintext(self):
        """encrypt_file should return plaintext unchanged when disabled."""
        service = EncryptionService()
        plaintext = b"hello world"
        result = service.encrypt_file(plaintext)
        self.assertEqual(result, plaintext)

    @override_settings(STORAGE_ENCRYPTION_METHOD="none")
    def test_decrypt_returns_plaintext(self):
        """decrypt_file should return data unchanged when disabled."""
        service = EncryptionService()
        data = b"hello world"
        result = service.decrypt_file(data)
        self.assertEqual(result, data)

    @override_settings(STORAGE_ENCRYPTION_METHOD="none")
    def test_key_id_returns_none(self):
        """key_id should return None when disabled."""
        service = EncryptionService()
        self.assertIsNone(service.key_id)

    @override_settings(STORAGE_ENCRYPTION_METHOD="none")
    def test_calculate_encrypted_size_returns_original(self):
        """calculate_encrypted_size should return original size when disabled."""
        service = EncryptionService()
        self.assertEqual(service.calculate_encrypted_size(100), 100)


@override_settings(
    STORAGE_ENCRYPTION_METHOD="server",
    STORAGE_ENCRYPTION_KEY=TEST_KEY,
    STORAGE_ENCRYPTION_KEY_ID="test-key-1",
)
class EncryptionServiceEnabledTest(TestCase):
    """Tests when encryption is enabled."""

    def test_is_enabled_returns_true(self):
        """is_enabled should return True when method is 'server'."""
        service = EncryptionService()
        self.assertTrue(service.is_enabled)

    def test_key_id_returns_configured_value(self):
        """key_id should return configured value."""
        service = EncryptionService()
        self.assertEqual(service.key_id, "test-key-1")

    def test_encrypt_adds_header(self):
        """encrypt_file should add version byte and nonce header."""
        service = EncryptionService()
        plaintext = b"hello world"
        encrypted = service.encrypt_file(plaintext)

        # Check version byte
        self.assertEqual(encrypted[0:1], VERSION_AES_256_GCM)

        # Check overall size (plaintext + overhead)
        expected_size = len(plaintext) + OVERHEAD
        self.assertEqual(len(encrypted), expected_size)

    def test_encrypt_decrypt_roundtrip(self):
        """encrypt then decrypt should return original plaintext."""
        service = EncryptionService()
        plaintext = b"hello world, this is a test message"
        encrypted = service.encrypt_file(plaintext)
        decrypted = service.decrypt_file(encrypted)
        self.assertEqual(decrypted, plaintext)

    def test_encrypt_different_nonces(self):
        """encrypt_file should use different nonce each time."""
        service = EncryptionService()
        plaintext = b"same content"
        encrypted1 = service.encrypt_file(plaintext)
        encrypted2 = service.encrypt_file(plaintext)

        # Different nonces mean different ciphertext
        self.assertNotEqual(encrypted1, encrypted2)

        # But both decrypt to same plaintext
        self.assertEqual(service.decrypt_file(encrypted1), plaintext)
        self.assertEqual(service.decrypt_file(encrypted2), plaintext)

    def test_encrypt_empty_content(self):
        """encrypt_file should handle empty content."""
        service = EncryptionService()
        plaintext = b""
        encrypted = service.encrypt_file(plaintext)
        decrypted = service.decrypt_file(encrypted)
        self.assertEqual(decrypted, plaintext)

    def test_encrypt_large_content(self):
        """encrypt_file should handle large content."""
        service = EncryptionService()
        plaintext = b"x" * (1024 * 1024)  # 1 MB
        encrypted = service.encrypt_file(plaintext)
        decrypted = service.decrypt_file(encrypted)
        self.assertEqual(decrypted, plaintext)

    def test_calculate_encrypted_size(self):
        """calculate_encrypted_size should add overhead."""
        service = EncryptionService()
        self.assertEqual(service.calculate_encrypted_size(100), 100 + OVERHEAD)
        self.assertEqual(service.calculate_encrypted_size(0), OVERHEAD)


@override_settings(
    STORAGE_ENCRYPTION_METHOD="server",
    STORAGE_ENCRYPTION_KEY=TEST_KEY,
    STORAGE_ENCRYPTION_KEY_ID="1",
)
class EncryptionServiceMixedModeTest(TestCase):
    """Tests for mixed mode (plaintext files when encryption enabled)."""

    def test_decrypt_plaintext_file_short(self):
        """decrypt_file should return plaintext for short files (< header size)."""
        service = EncryptionService()
        plaintext = b"hi"  # Shorter than header
        result = service.decrypt_file(plaintext)
        self.assertEqual(result, plaintext)

    def test_decrypt_plaintext_file_no_version_byte(self):
        """decrypt_file should return plaintext when no version byte present."""
        service = EncryptionService()
        # Start with a different byte than VERSION_AES_256_GCM
        plaintext = b"This is plain text without encryption header"
        result = service.decrypt_file(plaintext)
        self.assertEqual(result, plaintext)

    def test_decrypt_corrupted_raises_error(self):
        """decrypt_file should raise DecryptionError for corrupted encrypted data."""
        service = EncryptionService()
        # Valid header but corrupted ciphertext
        corrupted = VERSION_AES_256_GCM + (b"\x00" * NONCE_SIZE) + (b"\xff" * 32)
        with self.assertRaises(DecryptionError):
            service.decrypt_file(corrupted)

    def test_decrypt_tampered_raises_error(self):
        """decrypt_file should raise DecryptionError for tampered data."""
        service = EncryptionService()
        plaintext = b"original content"
        encrypted = service.encrypt_file(plaintext)

        # Tamper with the ciphertext (not the header)
        tampered = bytearray(encrypted)
        tampered[-1] ^= 0xFF  # Flip bits in last byte
        tampered = bytes(tampered)

        with self.assertRaises(DecryptionError):
            service.decrypt_file(tampered)


@override_settings(
    STORAGE_ENCRYPTION_METHOD="server",
    STORAGE_ENCRYPTION_KEY=TEST_KEY,
)
class EncryptionServiceDetectionTest(TestCase):
    """Tests for encryption detection."""

    def test_detect_encrypted_file(self):
        """detect_encryption should return 'server' for encrypted files."""
        service = EncryptionService()
        plaintext = b"test content"
        encrypted = service.encrypt_file(plaintext)
        self.assertEqual(service.detect_encryption(encrypted), "server")

    def test_detect_plaintext_file(self):
        """detect_encryption should return 'none' for plaintext files."""
        service = EncryptionService()
        plaintext = b"this is plain text"
        self.assertEqual(service.detect_encryption(plaintext), "none")

    def test_detect_empty_file(self):
        """detect_encryption should return 'none' for empty files."""
        service = EncryptionService()
        self.assertEqual(service.detect_encryption(b""), "none")


class EncryptionConstantsTest(TestCase):
    """Tests for encryption constants."""

    def test_header_size(self):
        """HEADER_SIZE should be version + nonce."""
        self.assertEqual(HEADER_SIZE, 1 + NONCE_SIZE)

    def test_overhead(self):
        """OVERHEAD should be header + tag."""
        self.assertEqual(OVERHEAD, HEADER_SIZE + TAG_SIZE)

    def test_nonce_size(self):
        """NONCE_SIZE should be 12 bytes (AES-GCM standard)."""
        self.assertEqual(NONCE_SIZE, 12)

    def test_tag_size(self):
        """TAG_SIZE should be 16 bytes (AES-GCM standard)."""
        self.assertEqual(TAG_SIZE, 16)
