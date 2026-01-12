"""Service layer for storage operations.

These services encapsulate the core file operation logic,
allowing both user and admin views to share the same implementation.
"""

from base64 import b64decode, b64encode
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Optional, Union

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import F, Sum

from core.services.encryption import DecryptionError
from core.storage.local import LocalStorageBackend
from core.utils import PathValidationError, normalize_path

from .models import StoredFile

User = get_user_model()


# =============================================================================
# Data Classes for Results
# =============================================================================


@dataclass
class ServiceResult:
    """Base result from service operations."""

    success: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    data: Optional[dict[str, Any]] = None


@dataclass
class DirectoryListResult(ServiceResult):
    """Result from directory listing."""

    path: str = ""
    entries: list[dict[str, Any]] = None  # type: ignore[assignment]
    count: int = 0
    total: int = 0
    next_cursor: Optional[str] = None

    def __post_init__(self) -> None:
        if self.entries is None:
            self.entries = []


@dataclass
class FileInfoResult(ServiceResult):
    """Result from file info operation."""

    path: str = ""
    name: str = ""
    size: int = 0
    content_type: Optional[str] = None
    is_directory: bool = False
    created_at: Any = None
    modified_at: Any = None
    encryption_method: str = "none"
    etag: Optional[str] = None


@dataclass
class FileContentResult(ServiceResult):
    """Result from file content operations."""

    content: Union[str, bytes, None] = None
    size: int = 0
    content_type: Optional[str] = None


# =============================================================================
# Text File Detection (shared constants and logic)
# =============================================================================


# Text MIME types allowed for content preview
TEXT_PREVIEW_MIME_TYPES: frozenset[str] = frozenset([
    # Plain text
    "text/plain",
    # Markup/Markdown
    "text/markdown",
    "text/x-markdown",
    "text/html",
    "text/xml",
    "text/css",
    # Code files
    "text/x-python",
    "text/x-python-script",
    "application/x-python-code",
    "text/javascript",
    "application/javascript",
    "application/json",
    "text/x-java-source",
    "text/x-c",
    "text/x-c++",
    "text/x-go",
    "text/x-rust",
    "text/x-ruby",
    "text/x-php",
    "text/x-sh",
    "text/x-shellscript",
    "application/x-sh",
    "text/x-yaml",
    "application/x-yaml",
    "text/x-toml",
    "application/xml",
    "application/toml",
    "text/csv",
    "text/tab-separated-values",
])

# File extensions treated as text for preview
TEXT_EXTENSIONS: frozenset[str] = frozenset([
    ".txt", ".md", ".markdown", ".rst", ".asciidoc",
    ".py", ".pyw", ".pyi",
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".json", ".jsonl", ".json5",
    ".html", ".htm", ".xml", ".xhtml", ".svg",
    ".css", ".scss", ".sass", ".less",
    ".java", ".kt", ".kts", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx",
    ".go", ".rs", ".rb", ".php",
    ".sh", ".bash", ".zsh", ".fish",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".csv", ".tsv",
    ".sql", ".graphql", ".gql",
    ".env",
])

# Known filenames without extensions that are text
TEXT_FILENAMES: frozenset[str] = frozenset([
    "makefile", "dockerfile", "gemfile", "rakefile",
    "readme", "license", "changelog", "contributing",
    ".gitignore", ".dockerignore", ".editorconfig",
    ".env", ".env.example", ".env.local",
])


def is_text_file(file_path: str, content_type: Optional[str]) -> bool:
    """
    Determine if a file should be treated as text for preview.

    Uses a whitelist approach:
    1. Check content_type against known text MIME types
    2. Fall back to extension-based detection
    3. Check known text filenames without extensions
    """
    # Check MIME type first
    if content_type:
        ct_lower = content_type.lower().split(";")[0].strip()
        if ct_lower in TEXT_PREVIEW_MIME_TYPES:
            return True
        # Any text/* is allowed
        if ct_lower.startswith("text/"):
            return True

    # Check extension
    ext = Path(file_path).suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return True

    # Check known filenames without extensions
    name = Path(file_path).name.lower()
    if name in TEXT_FILENAMES:
        return True

    return False


def generate_etag(path: str, size: int, modified_at: Any) -> str:
    """Generate ETag from file metadata."""
    import hashlib
    ts = modified_at.isoformat() if hasattr(modified_at, "isoformat") else str(modified_at)
    data = f"{path}:{size}:{ts}"
    return hashlib.md5(data.encode()).hexdigest()[:12]


# =============================================================================
# Storage Path Helper
# =============================================================================


def get_user_storage_path(user: User) -> str:
    """Get storage path prefix for user."""
    return f"{user.id}"


# =============================================================================
# Directory Service
# =============================================================================


class DirectoryService:
    """Service for directory operations."""

    def __init__(self, user: User, backend: Optional[LocalStorageBackend] = None):
        self.user = user
        self.backend = backend or LocalStorageBackend()
        self.user_prefix = get_user_storage_path(user)

    def list_directory(
        self,
        dir_path: str = "",
        limit: int = 50,
        cursor: Optional[str] = None,
        search: Optional[str] = None,
    ) -> DirectoryListResult:
        """List directory contents with pagination."""
        # Normalize and validate path
        try:
            dir_path = normalize_path(dir_path) if dir_path else ""
        except PathValidationError as e:
            return DirectoryListResult(
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
                path=dir_path,
            )

        full_path = f"{self.user_prefix}/{dir_path}" if dir_path else self.user_prefix

        try:
            entries = list(self.backend.list(full_path))
        except FileNotFoundError:
            # Auto-create user's root directory if it doesn't exist
            if not dir_path:
                self.backend.mkdir(full_path)
                entries = []
            else:
                return DirectoryListResult(
                    success=False,
                    error_code="DIRECTORY_NOT_FOUND",
                    error_message=f"Directory '{dir_path}' does not exist.",
                    path=dir_path,
                )
        except NotADirectoryError:
            return DirectoryListResult(
                success=False,
                error_code="PATH_IS_FILE",
                error_message=f"Path '{dir_path}' is a file, not a directory.",
                path=dir_path,
            )

        # Fetch metadata from database for entries
        entry_paths = [entry.path.replace(f"{self.user_prefix}/", "") for entry in entries]
        db_files = {
            f.path: {
                "encryption_method": f.encryption_method,
                "sort_position": f.sort_position,
            }
            for f in StoredFile.objects.filter(owner=self.user, path__in=entry_paths)
        }

        # Build entry data
        entry_data = []
        for entry in entries:
            rel_path = entry.path.replace(f"{self.user_prefix}/", "")
            db_info = db_files.get(rel_path, {})
            entry_data.append({
                "name": entry.name,
                "path": rel_path,
                "size": entry.size,
                "is_directory": entry.is_directory,
                "content_type": entry.content_type,
                "modified_at": entry.modified_at,
                "encryption_method": db_info.get("encryption_method", StoredFile.ENCRYPTION_NONE),
                "sort_position": db_info.get("sort_position"),
            })

        # Sort: directories first, then by sort_position (nulls last), then alphabetically
        entry_data = sorted(
            entry_data,
            key=lambda x: (
                not x["is_directory"],
                x["sort_position"] if x["sort_position"] is not None else float("inf"),
                x["name"],
            ),
        )

        # Filter by search term
        if search:
            search_lower = search.lower()
            entry_data = [
                e for e in entry_data
                if search_lower in str(e["name"]).lower()
            ]

        # Pagination
        limit = min(limit, 200)
        start_idx = 0
        if cursor:
            try:
                start_idx = int(b64decode(cursor).decode())
            except (ValueError, UnicodeDecodeError):
                pass

        end_idx = start_idx + limit
        page_entries = entry_data[start_idx:end_idx]

        # Generate next cursor
        next_cursor = None
        if end_idx < len(entry_data):
            next_cursor = b64encode(str(end_idx).encode()).decode()

        return DirectoryListResult(
            success=True,
            path=dir_path,
            entries=page_entries,
            count=len(page_entries),
            total=len(entry_data),
            next_cursor=next_cursor,
        )

    def create_directory(self, dir_path: str) -> ServiceResult:
        """Create a new directory."""
        try:
            dir_path = normalize_path(dir_path)
        except PathValidationError as e:
            return ServiceResult(
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
            )

        full_path = f"{self.user_prefix}/{dir_path}"

        if self.backend.exists(full_path):
            return ServiceResult(
                success=False,
                error_code="ALREADY_EXISTS",
                error_message=f"Directory '{dir_path}' already exists.",
            )

        file_info = self.backend.mkdir(full_path)

        # Create database record
        parent_path = str(Path(dir_path).parent) if "/" in dir_path else ""

        # Shift existing files down to make room at position 0
        StoredFile.objects.filter(
            owner=self.user,
            parent_path=parent_path,
            sort_position__isnull=False,
        ).update(sort_position=F("sort_position") + 1)

        StoredFile.objects.update_or_create(
            owner=self.user,
            path=dir_path,
            defaults={
                "name": file_info.name,
                "size": 0,
                "content_type": "",
                "is_directory": True,
                "parent_path": parent_path,
                "encryption_method": StoredFile.ENCRYPTION_NONE,
                "sort_position": 0,
            },
        )

        return ServiceResult(
            success=True,
            data={
                "path": dir_path,
                "name": file_info.name,
                "size": 0,
                "content_type": None,
                "is_directory": True,
                "created_at": file_info.modified_at,
                "modified_at": file_info.modified_at,
                "encryption_method": StoredFile.ENCRYPTION_NONE,
            },
        )


# =============================================================================
# File Service
# =============================================================================


class FileService:
    """Service for file operations."""

    def __init__(self, user: User, backend: Optional[LocalStorageBackend] = None):
        self.user = user
        self.backend = backend or LocalStorageBackend()
        self.user_prefix = get_user_storage_path(user)

    def get_info(self, file_path: str) -> FileInfoResult:
        """Get file metadata."""
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return FileInfoResult(
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
            )

        full_path = f"{self.user_prefix}/{file_path}"

        try:
            file_info = self.backend.info(full_path)
        except FileNotFoundError:
            return FileInfoResult(
                success=False,
                error_code="FILE_NOT_FOUND",
                error_message=f"File '{file_path}' does not exist.",
            )

        # Get database record for additional info
        try:
            db_file = StoredFile.objects.get(owner=self.user, path=file_path)
            created_at = db_file.created_at
            encryption_method = db_file.encryption_method
        except StoredFile.DoesNotExist:
            created_at = file_info.modified_at
            encryption_method = StoredFile.ENCRYPTION_NONE

        etag = generate_etag(file_path, file_info.size, file_info.modified_at)

        return FileInfoResult(
            success=True,
            path=file_path,
            name=file_info.name,
            size=file_info.size,
            content_type=file_info.content_type,
            is_directory=file_info.is_directory,
            created_at=created_at,
            modified_at=file_info.modified_at,
            encryption_method=encryption_method,
            etag=etag,
        )

    def upload(
        self,
        file_path: str,
        file_obj: BinaryIO,
        file_size: int,
        check_quota: bool = True,
    ) -> ServiceResult:
        """Upload a file."""
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return ServiceResult(
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
            )

        # Check global size limit
        max_size = settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if file_size > max_size:
            return ServiceResult(
                success=False,
                error_code="FILE_TOO_LARGE",
                error_message="File size exceeds maximum allowed size.",
                data={
                    "max_size_mb": settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB,
                    "file_size_mb": round(file_size / (1024 * 1024), 2),
                },
            )

        # Check if overwrite
        is_overwrite = StoredFile.objects.filter(
            owner=self.user, path=file_path
        ).exists()

        # Check quota if requested
        if check_quota:
            quota_result = self._check_quota(file_size, file_path if is_overwrite else None)
            if not quota_result.success:
                return quota_result

        full_path = f"{self.user_prefix}/{file_path}"

        # Ensure parent directory exists
        parent_path = str(Path(full_path).parent)
        if not self.backend.exists(parent_path):
            self.backend.mkdir(parent_path)

        # Save file
        file_info = self.backend.save(full_path, file_obj)

        # Create/update database record
        db_parent_path = str(Path(file_path).parent) if "/" in file_path else ""

        # Shift existing files down to make room at position 0
        StoredFile.objects.filter(
            owner=self.user,
            parent_path=db_parent_path,
            sort_position__isnull=False,
        ).update(sort_position=F("sort_position") + 1)

        stored_file, created = StoredFile.objects.update_or_create(
            owner=self.user,
            path=file_path,
            defaults={
                "name": file_info.name,
                "size": file_info.size,
                "content_type": file_info.content_type or "",
                "is_directory": False,
                "parent_path": db_parent_path,
                # Encryption metadata from backend (ADR 010)
                "encryption_method": file_info.encryption_method,
                "key_id": file_info.encryption_key_id,
                "encrypted_size": file_info.encrypted_size,
                "sort_position": 0,
            },
        )

        return ServiceResult(
            success=True,
            data={
                "path": file_path,
                "name": file_info.name,
                "size": file_info.size,
                "content_type": file_info.content_type,
                "is_directory": False,
                "created_at": stored_file.created_at,
                "modified_at": file_info.modified_at,
                "encryption_method": stored_file.encryption_method,
            },
        )

    def download(self, file_path: str, if_none_match: Optional[str] = None) -> ServiceResult:
        """Get file for download.

        Returns file handle in data['file_handle'] if successful.
        Returns data['not_modified']=True if ETag matches.
        """
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return ServiceResult(
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
            )

        full_path = f"{self.user_prefix}/{file_path}"

        try:
            file_info = self.backend.info(full_path)
        except FileNotFoundError:
            return ServiceResult(
                success=False,
                error_code="FILE_NOT_FOUND",
                error_message=f"File '{file_path}' does not exist.",
            )

        if file_info.is_directory:
            return ServiceResult(
                success=False,
                error_code="PATH_IS_DIRECTORY",
                error_message=f"Path '{file_path}' is a directory.",
            )

        etag = generate_etag(file_path, file_info.size, file_info.modified_at)

        # Check conditional request
        if if_none_match and if_none_match.strip('"') == etag:
            return ServiceResult(
                success=True,
                data={"not_modified": True, "etag": etag},
            )

        # Open file (with decryption)
        try:
            file_handle = self.backend.open(full_path)
        except DecryptionError:
            return ServiceResult(
                success=False,
                error_code="DECRYPTION_FAILED",
                error_message="Unable to decrypt file.",
            )

        return ServiceResult(
            success=True,
            data={
                "file_handle": file_handle,
                "name": file_info.name,
                "size": file_info.size,
                "content_type": file_info.content_type,
                "etag": etag,
            },
        )

    def delete(self, file_path: str) -> ServiceResult:
        """Delete a file or directory."""
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return ServiceResult(
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
            )

        full_path = f"{self.user_prefix}/{file_path}"

        try:
            file_info = self.backend.info(full_path)
        except FileNotFoundError:
            return ServiceResult(
                success=False,
                error_code="FILE_NOT_FOUND",
                error_message=f"File '{file_path}' does not exist.",
            )

        # Delete from filesystem
        self.backend.delete(full_path)

        # Delete from database (CASCADE handles ShareLinks)
        StoredFile.objects.filter(owner=self.user, path=file_path).delete()

        # For directories, also delete child records
        if file_info.is_directory:
            StoredFile.objects.filter(
                owner=self.user, path__startswith=f"{file_path}/"
            ).delete()

        return ServiceResult(success=True, data={"path": file_path})

    def get_content(self, file_path: str) -> FileContentResult:
        """Get text file content for preview."""
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return FileContentResult(
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
            )

        full_path = f"{self.user_prefix}/{file_path}"

        try:
            file_info = self.backend.info(full_path)
        except FileNotFoundError:
            return FileContentResult(
                success=False,
                error_code="FILE_NOT_FOUND",
                error_message=f"File '{file_path}' does not exist.",
            )

        if file_info.is_directory:
            return FileContentResult(
                success=False,
                error_code="PATH_IS_DIRECTORY",
                error_message=f"Path '{file_path}' is a directory.",
            )

        # Check size limit
        max_preview_bytes = settings.STORMCLOUD_MAX_PREVIEW_SIZE_MB * 1024 * 1024
        if file_info.size > max_preview_bytes:
            return FileContentResult(
                success=False,
                error_code="FILE_TOO_LARGE",
                error_message="File exceeds maximum preview size.",
            )

        # Check if text file
        if not is_text_file(file_path, file_info.content_type):
            return FileContentResult(
                success=False,
                error_code="NOT_TEXT_FILE",
                error_message="File is binary and cannot be previewed as text.",
            )

        # Read content (with decryption)
        try:
            file_handle = self.backend.open(full_path)
            content = file_handle.read()
            file_handle.close()
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
        except DecryptionError:
            return FileContentResult(
                success=False,
                error_code="DECRYPTION_FAILED",
                error_message="Unable to decrypt file.",
            )
        except Exception as e:
            return FileContentResult(
                success=False,
                error_code="READ_ERROR",
                error_message=str(e),
            )

        return FileContentResult(
            success=True,
            content=content,
            size=file_info.size,
            content_type=file_info.content_type,
        )

    def update_content(
        self,
        file_path: str,
        content: Union[str, bytes],
        check_quota: bool = True,
    ) -> ServiceResult:
        """Update text file content."""
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return ServiceResult(
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
            )

        full_path = f"{self.user_prefix}/{file_path}"

        # Check file exists
        try:
            old_info = self.backend.info(full_path)
        except FileNotFoundError:
            return ServiceResult(
                success=False,
                error_code="FILE_NOT_FOUND",
                error_message=f"File '{file_path}' does not exist.",
            )

        if old_info.is_directory:
            return ServiceResult(
                success=False,
                error_code="PATH_IS_DIRECTORY",
                error_message="Cannot edit a directory.",
            )

        # Get content bytes
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content
        new_size = len(content_bytes)

        # Check global size limit
        max_size = settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if new_size > max_size:
            return ServiceResult(
                success=False,
                error_code="FILE_TOO_LARGE",
                error_message="Content exceeds maximum allowed size.",
            )

        # Check quota if requested
        if check_quota:
            quota_result = self._check_quota(new_size, file_path)
            if not quota_result.success:
                return quota_result

        # Save content
        content_file = BytesIO(content_bytes)
        file_info = self.backend.save(full_path, content_file)

        # Update database record
        stored_file, _ = StoredFile.objects.update_or_create(
            owner=self.user,
            path=file_path,
            defaults={
                "name": file_info.name,
                "size": file_info.size,
                "content_type": file_info.content_type or "",
                "is_directory": False,
            },
        )

        return ServiceResult(
            success=True,
            data={
                "path": file_path,
                "name": file_info.name,
                "size": file_info.size,
                "content_type": file_info.content_type,
                "created_at": stored_file.created_at,
                "modified_at": file_info.modified_at,
                "encryption_method": stored_file.encryption_method,
            },
        )

    def _check_quota(
        self,
        new_size: int,
        existing_file_path: Optional[str] = None,
    ) -> ServiceResult:
        """Check if operation would exceed user quota."""
        profile = getattr(self.user, "profile", None)
        if not profile:
            return ServiceResult(success=True)

        quota_bytes = profile.storage_quota_bytes
        if quota_bytes <= 0:  # 0 = unlimited
            return ServiceResult(success=True)

        # Calculate current usage
        current_usage = (
            StoredFile.objects.filter(owner=self.user).aggregate(total=Sum("size"))["total"]
            or 0
        )

        # For overwrites, calculate delta
        size_delta = new_size
        if existing_file_path:
            try:
                old_file = StoredFile.objects.get(owner=self.user, path=existing_file_path)
                size_delta = new_size - old_file.size
            except StoredFile.DoesNotExist:
                pass

        if current_usage + size_delta > quota_bytes:
            return ServiceResult(
                success=False,
                error_code="QUOTA_EXCEEDED",
                error_message="Operation would exceed storage quota.",
                data={
                    "quota_mb": round(quota_bytes / (1024 * 1024), 2),
                    "used_mb": round(current_usage / (1024 * 1024), 2),
                    "file_size_mb": round(new_size / (1024 * 1024), 2),
                },
            )

        return ServiceResult(success=True)
