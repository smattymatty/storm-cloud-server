"""HTML views for storage app (non-API views)."""

from django.http import FileResponse, Http404
from django.shortcuts import render, redirect
from django.views import View
from django.db.models import F
from django.utils import timezone

from .models import ShareLink
from .services import get_user_storage_path
from .utils import get_share_link_by_token


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def format_datetime(dt) -> str:
    """Format datetime for display."""
    if dt is None:
        return ""
    return dt.strftime("%b %d, %Y at %H:%M")


class PublicSharePageView(View):
    """HTML page for viewing/downloading shared files."""

    def get_share_link(self, token: str):
        """Look up and validate share link."""
        link = get_share_link_by_token(token)
        if not link:
            return None, "not_found"
        if not link.is_valid():
            if link.is_expired():
                return None, "expired"
            return None, "revoked"
        return link, None

    def is_password_verified(self, request, link) -> bool:
        """Check if password is already verified in session."""
        if not link.password_hash:
            return True  # No password required
        session_key = f"share_password_{link.id}"
        return request.session.get(session_key) is True

    def set_password_verified(self, request, link):
        """Store password verification in session."""
        session_key = f"share_password_{link.id}"
        request.session[session_key] = True

    def get(self, request, token: str):
        """Show share page or password form."""
        link, error = self.get_share_link(token)

        if error:
            context = {}
            if error == "expired":
                context = {
                    "error_code": "expired",
                    "error_title": "Link Expired",
                    "error_message": "This share link has expired.",
                }
            elif error == "revoked":
                context = {
                    "error_code": "revoked",
                    "error_title": "Link Revoked",
                    "error_message": "This share link has been revoked.",
                }
            else:
                context = {
                    "error_code": "not_found",
                    "error_title": "Link Not Found",
                    "error_message": "This share link doesn't exist.",
                }
            return render(request, "public/error.html", context, status=404)

        # Check if password is required and not yet verified
        if link.password_hash and not self.is_password_verified(request, link):
            return render(request, "public/password.html", {"token": token})

        # Increment view count
        ShareLink.objects.filter(id=link.id).update(
            view_count=F("view_count") + 1, last_accessed_at=timezone.now()
        )

        # Get file info
        stored_file = link.stored_file
        content_type = stored_file.content_type or "application/octet-stream"
        is_pdf = content_type == "application/pdf"

        context = {
            "token": token,
            "file_name": stored_file.name,
            "file_size_display": format_file_size(stored_file.size),
            "content_type": content_type,
            "is_pdf": is_pdf,
            "download_url": f"/share/{token}/file/",
            "allow_download": link.allow_download,
            # Header metadata
            "shared_by": link.owner.username,
            "created_at": format_datetime(link.created_at),
            "expires_at": format_datetime(link.expires_at) if link.expires_at else None,
            "has_password": bool(link.password_hash),
        }
        return render(request, "public/share.html", context)

    def post(self, request, token: str):
        """Handle password submission."""
        link, error = self.get_share_link(token)

        if error:
            return redirect("public_share_page", token=token)

        password = request.POST.get("password", "")

        if link.check_password(password):
            self.set_password_verified(request, link)
            return redirect("public_share_page", token=token)

        # Wrong password
        return render(
            request,
            "public/password.html",
            {"token": token, "error": "Incorrect password"},
        )


class PublicShareFileView(View):
    """Serve shared file (session-based auth for password-protected shares)."""

    def get(self, request, token: str):
        """Stream the shared file."""
        # Lazy imports to avoid circular import
        from core.storage.local import LocalStorageBackend
        from core.services.encryption import DecryptionError

        link = get_share_link_by_token(token)

        if not link or not link.is_valid():
            raise Http404("Share link not found")

        # Check password via session
        if link.password_hash:
            session_key = f"share_password_{link.id}"
            if not request.session.get(session_key):
                raise Http404("Password verification required")

        # Check if downloads are allowed
        if not link.allow_download:
            raise Http404("Downloads disabled for this link")

        # Get file from storage
        stored_file = link.stored_file
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(link.owner)
        full_path = f"{user_prefix}/{stored_file.path}"

        try:
            file_handle = backend.open(full_path)
        except FileNotFoundError:
            raise Http404("File no longer exists")
        except DecryptionError:
            raise Http404("Unable to access file")

        # Increment download count
        ShareLink.objects.filter(id=link.id).update(
            download_count=F("download_count") + 1, last_accessed_at=timezone.now()
        )

        # Return file response
        content_type = stored_file.content_type or "application/octet-stream"
        filename = stored_file.name

        # For PDFs viewed inline, don't force download
        is_pdf = content_type == "application/pdf"

        response = FileResponse(file_handle, content_type=content_type)

        if is_pdf:
            # Inline display for PDFs in embed
            response["Content-Disposition"] = f'inline; filename="{filename}"'
        else:
            # Force download for other files
            response["Content-Disposition"] = f'attachment; filename="{filename}"'

        response["Cache-Control"] = "private, max-age=3600"
        return response
