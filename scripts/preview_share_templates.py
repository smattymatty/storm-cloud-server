#!/usr/bin/env python
"""
Preview share page templates by rendering them to HTML files.

Usage:
    python scripts/preview_share_templates.py

This will create HTML files in /tmp/share_preview/ that you can open in a browser.
"""

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "_core" / "templates" / "public"
OUTPUT_DIR = Path("/tmp/share_preview")


def render_simple(template_path: Path, context: dict) -> str:
    """Simple template rendering - just replace {{ var }} with values."""
    content = template_path.read_text()

    # Handle extends - inline the base template
    if "{% extends" in content:
        base_path = TEMPLATE_DIR / "base.html"
        base_content = base_path.read_text()

        # Extract blocks from child template
        import re
        blocks = {}
        for match in re.finditer(r'{%\s*block\s+(\w+)\s*%}(.*?){%\s*endblock\s*%}', content, re.DOTALL):
            blocks[match.group(1)] = match.group(2).strip()

        # Replace blocks in base
        for block_name, block_content in blocks.items():
            # Replace the block in base template
            pattern = r'{%\s*block\s+' + block_name + r'\s*%}.*?{%\s*endblock\s*%}'
            base_content = re.sub(pattern, block_content, base_content, flags=re.DOTALL)

        # Remove any remaining empty blocks
        base_content = re.sub(r'{%\s*block\s+\w+\s*%}\s*{%\s*endblock\s*%}', '', base_content)

        content = base_content

    # Replace {{ variable }} with context values
    for key, value in context.items():
        content = content.replace("{{ " + key + " }}", str(value))
        content = content.replace("{{" + key + "}}", str(value))

    # Handle conditionals (simple version)
    import re

    # Handle {% if var %} ... {% endif %}
    for key, value in context.items():
        if value:
            # Remove the if/endif tags but keep content
            content = re.sub(r'{%\s*if\s+' + key + r'\s*%}(.*?){%\s*endif\s*%}', r'\1', content, flags=re.DOTALL)
        else:
            # Remove the entire block
            content = re.sub(r'{%\s*if\s+' + key + r'\s*%}.*?{%\s*endif\s*%}', '', content, flags=re.DOTALL)

    # Clean up remaining template tags
    content = re.sub(r'{%\s*csrf_token\s*%}', '<input type="hidden" name="csrftoken" value="fake-csrf">', content)
    content = re.sub(r'{%.*?%}', '', content)
    content = re.sub(r'{{.*?}}', '', content)

    return content


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Sample contexts
    templates_to_render = [
        (
            "share_pdf.html",
            TEMPLATE_DIR / "share.html",
            {
                "token": "abc123-sample-token",
                "file_name": "important-document.pdf",
                "file_size_display": "2.4 MB",
                "content_type": "application/pdf",
                "is_pdf": True,
                "download_url": "/share/abc123-sample-token/file/",
                "allow_download": True,
                "shared_by": "alice",
                "created_at": "Jan 13, 2025 at 14:30",
                "expires_at": "Jan 20, 2025 at 14:30",
                "has_password": False,
            }
        ),
        (
            "share_protected.html",
            TEMPLATE_DIR / "share.html",
            {
                "token": "protected-token",
                "file_name": "confidential-report.pdf",
                "file_size_display": "1.8 MB",
                "content_type": "application/pdf",
                "is_pdf": True,
                "download_url": "/share/protected-token/file/",
                "allow_download": True,
                "shared_by": "bob",
                "created_at": "Jan 10, 2025 at 09:15",
                "expires_at": "",
                "has_password": True,
            }
        ),
        (
            "share_other.html",
            TEMPLATE_DIR / "share.html",
            {
                "token": "xyz789-sample-token",
                "file_name": "photo.jpg",
                "file_size_display": "856 KB",
                "content_type": "image/jpeg",
                "is_pdf": False,
                "download_url": "/share/xyz789-sample-token/file/",
                "allow_download": True,
                "shared_by": "carol",
                "created_at": "Jan 12, 2025 at 16:45",
                "expires_at": "Feb 12, 2025 at 16:45",
                "has_password": False,
            }
        ),
        (
            "password.html",
            TEMPLATE_DIR / "password.html",
            {"token": "protected-token", "error": ""}
        ),
        (
            "password_error.html",
            TEMPLATE_DIR / "password.html",
            {"token": "protected-token", "error": "Incorrect password"}
        ),
        (
            "error_not_found.html",
            TEMPLATE_DIR / "error.html",
            {
                "error_code": "not_found",
                "error_title": "Link Not Found",
                "error_message": "This share link doesn't exist.",
            }
        ),
        (
            "error_expired.html",
            TEMPLATE_DIR / "error.html",
            {
                "error_code": "expired",
                "error_title": "Link Expired",
                "error_message": "This share link has expired.",
            }
        ),
    ]

    for output_name, template_path, context in templates_to_render:
        html = render_simple(template_path, context)
        output_path = OUTPUT_DIR / output_name
        output_path.write_text(html)
        print(f"Created: {output_path}")

    print(f"\nOpen in browser (copy/paste these commands):")
    print(f"  xdg-open {OUTPUT_DIR}/share_pdf.html")
    print(f"  xdg-open {OUTPUT_DIR}/share_protected.html")
    print(f"  xdg-open {OUTPUT_DIR}/share_other.html")
    print(f"  xdg-open {OUTPUT_DIR}/password.html")
    print(f"  xdg-open {OUTPUT_DIR}/password_error.html")
    print(f"  xdg-open {OUTPUT_DIR}/error_not_found.html")
    print(f"  xdg-open {OUTPUT_DIR}/error_expired.html")


if __name__ == "__main__":
    main()
