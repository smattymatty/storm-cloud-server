#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for the custom dotenv parser module.

Run tests with:
    python3 -m pytest deploy/ansible/tests/test_dotenv_parser.py -v

Or from deploy/ansible/tests:
    python3 test_dotenv_parser.py
"""

import sys
import unittest
from pathlib import Path

# Add library directory to path so we can import the module
sys.path.insert(0, str(Path(__file__).parent.parent / "library"))

from read_dotenv import DotenvParser


class TestDotenvParser(unittest.TestCase):
    """Test cases for DotenvParser class."""

    def test_simple_key_value(self):
        """Test basic key=value parsing."""
        content = "KEY1=value1\nKEY2=value2"
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["KEY1"], "value1")
        self.assertEqual(result["KEY2"], "value2")

    def test_empty_lines(self):
        """Test that empty lines are skipped."""
        content = "KEY1=value1\n\n\nKEY2=value2"
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(len(result), 2)
        self.assertEqual(result["KEY1"], "value1")
        self.assertEqual(result["KEY2"], "value2")

    def test_comments(self):
        """Test that comment lines are skipped."""
        content = "# This is a comment\nKEY1=value1\n# Another comment\nKEY2=value2"
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(len(result), 2)
        self.assertEqual(result["KEY1"], "value1")

    def test_inline_comments(self):
        """Test inline comments (only for unquoted values)."""
        content = 'KEY1=value1 # inline comment\nKEY2="value2 # not a comment"'
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["KEY1"], "value1")
        self.assertEqual(result["KEY2"], "value2 # not a comment")

    def test_double_quoted_values(self):
        """Test double-quoted values."""
        content = 'KEY1="value with spaces"\nKEY2="value=with=equals"'
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["KEY1"], "value with spaces")
        self.assertEqual(result["KEY2"], "value=with=equals")

    def test_single_quoted_values(self):
        """Test single-quoted values."""
        content = "KEY1='value with spaces'\nKEY2='value=with=equals'"
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["KEY1"], "value with spaces")
        self.assertEqual(result["KEY2"], "value=with=equals")

    def test_whitespace_handling(self):
        """Test whitespace around keys and values."""
        content = "  KEY1  =  value1  \n\tKEY2\t=\tvalue2\t"
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["KEY1"], "value1")
        self.assertEqual(result["KEY2"], "value2")

    def test_special_characters(self):
        """Test special characters in values."""
        content = 'KEY1="!@#$%^&*()"\nKEY2="value\\nwith\\nnewlines"'
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["KEY1"], "!@#$%^&*()")
        self.assertEqual(result["KEY2"], "value\\nwith\\nnewlines")

    def test_equals_in_value(self):
        """Test equals signs within values."""
        content = 'CONNECTION_STRING="host=localhost;user=admin;pass=secret123"'
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(
            result["CONNECTION_STRING"], "host=localhost;user=admin;pass=secret123"
        )

    def test_multiline_double_quoted(self):
        """Test multiline values with double quotes."""
        content = """KEY1="line1
line2
line3"
KEY2=simple"""
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["KEY1"], "line1\nline2\nline3")
        self.assertEqual(result["KEY2"], "simple")

    def test_multiline_single_quoted(self):
        """Test multiline values with single quotes."""
        content = """KEY1='line1
line2
line3'
KEY2=simple"""
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["KEY1"], "line1\nline2\nline3")
        self.assertEqual(result["KEY2"], "simple")

    def test_empty_value(self):
        """Test empty values."""
        content = "KEY1=\nKEY2=''\nKEY3=\"\""
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["KEY1"], "")
        self.assertEqual(result["KEY2"], "")
        self.assertEqual(result["KEY3"], "")

    def test_key_name_validation(self):
        """Test that only valid key names are parsed."""
        content = "VALID_KEY=value1\n123INVALID=value2\nKEY-INVALID=value3"
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertIn("VALID_KEY", result)
        self.assertNotIn("123INVALID", result)
        self.assertNotIn("KEY-INVALID", result)

    def test_complex_real_world_example(self):
        """Test a complex real-world .env file."""
        content = """# Django settings
SECRET_KEY="django-insecure-abc123!@#$%^&*()"
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
POSTGRES_DB=stormcloud
POSTGRES_USER=stormcloud
POSTGRES_PASSWORD="P@ssw0rd!WithSpecialChars"

# Email (commented out)
# EMAIL_HOST=smtp.gmail.com
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# Multiline example
PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
-----END RSA PRIVATE KEY-----"

# Empty values
OPTIONAL_SETTING=
"""
        parser = DotenvParser(content)
        result = parser.parse()

        self.assertEqual(result["SECRET_KEY"], "django-insecure-abc123!@#$%^&*()")
        self.assertEqual(result["DEBUG"], "False")
        self.assertEqual(result["ALLOWED_HOSTS"], "localhost,127.0.0.1")
        self.assertEqual(result["POSTGRES_DB"], "stormcloud")
        self.assertEqual(result["POSTGRES_USER"], "stormcloud")
        self.assertEqual(result["POSTGRES_PASSWORD"], "P@ssw0rd!WithSpecialChars")
        self.assertNotIn("EMAIL_HOST", result)
        self.assertEqual(
            result["EMAIL_BACKEND"], "django.core.mail.backends.console.EmailBackend"
        )
        self.assertIn("PRIVATE_KEY", result)
        self.assertIn("BEGIN RSA PRIVATE KEY", result["PRIVATE_KEY"])
        self.assertEqual(result["OPTIONAL_SETTING"], "")

    def test_url_values(self):
        """Test URL values with special characters."""
        content = (
            'DATABASE_URL="postgresql://user:p@ss@localhost:5432/db?sslmode=require"'
        )
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(
            result["DATABASE_URL"],
            "postgresql://user:p@ss@localhost:5432/db?sslmode=require",
        )

    def test_json_values(self):
        """Test JSON-like values."""
        content = 'CONFIG={"key":"value","nested":{"foo":"bar"}}'
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["CONFIG"], '{"key":"value","nested":{"foo":"bar"}}')

    def test_export_prefix(self):
        """Test that lines with 'export' prefix are not parsed (shell-specific)."""
        content = "export KEY1=value1\nKEY2=value2"
        parser = DotenvParser(content)
        result = parser.parse()
        # Our parser doesn't support 'export' keyword - it's shell-specific
        self.assertNotIn("KEY1", result)
        self.assertIn("KEY2", result)

    def test_case_sensitivity(self):
        """Test that keys are case-sensitive."""
        content = "key=lowercase\nKEY=uppercase\nKey=mixedcase"
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["key"], "lowercase")
        self.assertEqual(result["KEY"], "uppercase")
        self.assertEqual(result["Key"], "mixedcase")

    def test_duplicate_keys(self):
        """Test that duplicate keys use the last value."""
        content = "KEY1=first\nKEY1=second\nKEY1=third"
        parser = DotenvParser(content)
        result = parser.parse()
        self.assertEqual(result["KEY1"], "third")


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
