"""
Metadata validation for content flags.

Each flag type has a schema defining required and optional fields.
Validation ensures data consistency and provides clear error messages.
"""

from typing import Any

FLAG_METADATA_SCHEMAS: dict[str, dict[str, list[str]]] = {
    "ai_generated": {
        "required": ["model"],
        "optional": ["prompt_context", "notes"],
    },
    "user_approved": {
        "required": [],
        "optional": ["notes"],
    },
}


def validate_flag_metadata(
    flag_type: str, metadata: dict[str, Any]
) -> tuple[bool, str]:
    """
    Validate metadata against schema for flag type.

    Args:
        flag_type: The type of flag (e.g., 'ai_generated', 'user_approved')
        metadata: Dictionary of metadata to validate

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty string.
    """
    schema = FLAG_METADATA_SCHEMAS.get(flag_type)
    if not schema:
        return False, f"Unknown flag type: {flag_type}"

    # Check required fields
    for field in schema["required"]:
        if field not in metadata or not metadata[field]:
            return False, f"Missing required field: {field}"

    # Check for unknown fields
    allowed = set(schema["required"]) | set(schema["optional"])
    for field in metadata:
        if field not in allowed:
            return False, f"Unknown field for {flag_type}: {field}"

    return True, ""
