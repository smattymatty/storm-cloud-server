#!/usr/bin/python
# -*- coding: utf-8 -*-

# =============================================================================
# Storm Cloud Server - Dotenv Parser Module
# =============================================================================
# Custom Ansible module for parsing .env files with extended format support.
#
# Handles:
#   - Quoted values (single and double quotes)
#   - Multiline values
#   - Comments (inline and full-line)
#   - Special characters
#   - Equals signs in values
#   - Whitespace around keys/values
#
# Usage:
#   - name: Read secrets from .env
#     read_dotenv:
#       path: /path/to/.env
#       keys:
#         - SECRET_KEY
#         - POSTGRES_PASSWORD
#     register: dotenv_result
#
#   - name: Use parsed values
#     debug:
#       msg: "Secret key is {{ dotenv_result.values.SECRET_KEY }}"
# =============================================================================

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: read_dotenv
short_description: Parse .env files and extract specific keys
description:
    - Parses .env files with support for quotes, multiline values, and comments
    - Extracts specified keys and returns their values
    - Validates that all requested keys exist
version_added: "1.0.0"
options:
    path:
        description:
            - Path to the .env file to parse
        required: true
        type: str
    keys:
        description:
            - List of keys to extract from the .env file
        required: true
        type: list
        elements: str
    required:
        description:
            - Whether all keys must exist (fail if any missing)
        required: false
        type: bool
        default: true
author:
    - Storm Cloud Server Contributors
"""

EXAMPLES = r"""
- name: Read database credentials
  read_dotenv:
    path: /app/.env
    keys:
      - POSTGRES_PASSWORD
      - SECRET_KEY
  register: env_vars

- name: Use extracted values
  debug:
    msg: "DB password is {{ env_vars.values.POSTGRES_PASSWORD }}"
"""

RETURN = r"""
values:
    description: Dictionary of extracted key-value pairs
    type: dict
    returned: always
    sample: {"SECRET_KEY": "django-secret", "POSTGRES_PASSWORD": "db-pass"}
missing_keys:
    description: List of keys that were not found in the .env file
    type: list
    returned: when required=false
    sample: ["MISSING_KEY"]
"""

import os
import re

try:
    from ansible.module_utils.basic import AnsibleModule

    HAS_ANSIBLE = True
except ImportError:
    HAS_ANSIBLE = False
    # Mock for testing
    AnsibleModule = None


class DotenvParser:
    """
    Extended .env file parser supporting various formats and edge cases.
    """

    def __init__(self, content):
        self.content = content
        self.values = {}

    def parse(self):
        """
        Parse the .env file content and extract all key-value pairs.
        """
        lines = self.content.split("\n")
        multiline_key = None
        multiline_value = []
        multiline_quote = None

        for line_num, line in enumerate(lines, start=1):
            # Handle multiline continuation
            if multiline_key is not None:
                stripped = line.rstrip()

                # Check if multiline ends
                if multiline_quote == '"' and stripped.endswith('"'):
                    # End of double-quoted multiline
                    multiline_value.append(stripped[:-1])
                    self.values[multiline_key] = "\n".join(multiline_value)
                    multiline_key = None
                    multiline_value = []
                    multiline_quote = None
                elif multiline_quote == "'" and stripped.endswith("'"):
                    # End of single-quoted multiline
                    multiline_value.append(stripped[:-1])
                    self.values[multiline_key] = "\n".join(multiline_value)
                    multiline_key = None
                    multiline_value = []
                    multiline_quote = None
                else:
                    # Continue collecting multiline value
                    multiline_value.append(line.rstrip())
                continue

            # Strip whitespace
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            # Match key=value pattern
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", stripped)
            if not match:
                # Invalid line format, skip
                continue

            key = match.group(1)
            value = match.group(2)

            # Remove inline comments (unless inside quotes)
            if not (value.startswith('"') or value.startswith("'")):
                # Not quoted, check for inline comment
                comment_pos = value.find("#")
                if comment_pos != -1:
                    value = value[:comment_pos].rstrip()

            # Handle quoted values
            if value.startswith('"') and value.endswith('"') and len(value) > 1:
                # Double-quoted, complete on one line
                self.values[key] = value[1:-1]
            elif value.startswith("'") and value.endswith("'") and len(value) > 1:
                # Single-quoted, complete on one line
                self.values[key] = value[1:-1]
            elif value.startswith('"') and not value.endswith('"'):
                # Start of multiline double-quoted value
                multiline_key = key
                multiline_value = [value[1:]]
                multiline_quote = '"'
            elif value.startswith("'") and not value.endswith("'"):
                # Start of multiline single-quoted value
                multiline_key = key
                multiline_value = [value[1:]]
                multiline_quote = "'"
            else:
                # Unquoted value
                self.values[key] = value

        return self.values


def run_module():
    """
    Main module execution.
    """
    module_args = dict(
        path=dict(type="str", required=True),
        keys=dict(type="list", elements="str", required=True),
        required=dict(type="bool", required=False, default=True),
    )

    result = dict(changed=False, values={}, missing_keys=[])

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    path = module.params["path"]
    requested_keys = module.params["keys"]
    required = module.params["required"]

    # Check if file exists
    if not os.path.exists(path):
        module.fail_json(msg=f"File not found: {path}", **result)

    # Read file content
    content = ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        module.fail_json(msg=f"Failed to read file: {str(e)}", **result)

    # Parse .env file
    parser = DotenvParser(content)
    all_values = {}
    try:
        all_values = parser.parse()
    except Exception as e:
        module.fail_json(msg=f"Failed to parse .env file: {str(e)}", **result)

    # Extract requested keys
    missing_keys = []
    for key in requested_keys:
        if key in all_values:
            result["values"][key] = all_values[key]
        else:
            missing_keys.append(key)

    result["missing_keys"] = missing_keys

    # Fail if required keys are missing
    if required and missing_keys:
        module.fail_json(
            msg=f"Missing required keys in {path}: {', '.join(missing_keys)}", **result
        )

    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
