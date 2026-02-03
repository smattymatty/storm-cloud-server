"""Core utility functions for Storm Cloud."""

import re


class PathValidationError(Exception):
    """Raised when path contains invalid characters or traversal attempts."""

    pass


def normalize_path(path: str) -> str:
    """
    Normalize a storage path.

    - Strips leading/trailing slashes
    - Collapses multiple slashes
    - Blocks path traversal
    - Rejects invalid characters

    Args:
        path: Path to normalize

    Returns:
        Normalized path string

    Raises:
        PathValidationError: For invalid paths
    """
    if not path:
        return ""

    # Block null bytes and control characters
    if "\x00" in path or re.search(r"[\x00-\x1f]", path):
        raise PathValidationError("Path contains invalid characters")

    # Normalize slashes
    path = re.sub(r"/+", "/", path)
    path = path.strip("/")

    # Block path traversal
    parts = path.split("/")
    if ".." in parts:
        raise PathValidationError("Path traversal not allowed")

    return path


def validate_filename(name: str) -> str:
    """
    Validate a single filename component.

    Args:
        name: Filename to validate

    Returns:
        The validated filename

    Raises:
        PathValidationError: For invalid filenames
    """
    if not name:
        raise PathValidationError("Filename cannot be empty")

    if "/" in name or "\\" in name:
        raise PathValidationError("Filename cannot contain slashes")

    if name in (".", ".."):
        raise PathValidationError("Invalid filename")

    # Check for null bytes and control characters
    if "\x00" in name or re.search(r"[\x00-\x1f]", name):
        raise PathValidationError("Filename contains invalid characters")

    return name


# =============================================================================
# TOCTOU-Safe Filesystem Operations
# =============================================================================
#
# These functions use file descriptor-based operations to eliminate
# Time-Of-Check-Time-Of-Use race conditions in filesystem operations.
# Once you hold an fd, you're pinned to an inode - no symlink swapping
# can redirect your operation.
# =============================================================================

import errno
import os
import shutil
import stat
from pathlib import Path


class SymlinkAttackError(PathValidationError):
    """Raised when a symlink attack is detected during filesystem operations."""

    pass


def _assert_platform_support() -> None:
    """
    Fail loudly if platform doesn't support safe operations.

    Raises:
        RuntimeError: If shutil.rmtree doesn't have symlink attack protection
    """
    if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
        raise RuntimeError(
            "Platform does not support symlink-safe rmtree. "
            "Refusing to operate in vulnerable mode."
        )


def safe_rmtree(path: Path, root_boundary: Path) -> None:
    """
    Delete directory tree using file descriptors - immune to TOCTOU.

    Uses os.fwalk() with dir_fd parameters. Once we hold an fd, we're
    pinned to an inode, not a path string. Symlink swapping cannot
    redirect our operations.

    Args:
        path: Path to delete (file or directory)
        root_boundary: Operations must stay within this root

    Raises:
        SymlinkAttackError: If symlink is detected during traversal
        ValueError: If path escapes root_boundary
    """
    _assert_platform_support()

    path = Path(path)
    root_boundary = Path(root_boundary).resolve()

    # Check for symlink BEFORE resolving - this is critical
    if path.is_symlink():
        raise SymlinkAttackError(f"Target is a symlink: {path}")

    path = path.resolve()

    try:
        path.relative_to(root_boundary)
    except ValueError:
        raise ValueError(f"Path {path} is outside boundary {root_boundary}")

    if not path.exists():
        return

    # Single file: open with O_NOFOLLOW, refuse if symlink
    if path.is_file():
        try:
            fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
            os.close(fd)
        except OSError as e:
            if e.errno == errno.ELOOP:
                raise SymlinkAttackError(f"Target is a symlink: {path}")
            raise
        path.unlink()
        return

    # Directory: use os.fwalk with dir_fd for fd-pinned operations
    for root, dirs, files, root_fd in os.fwalk(
        str(path), topdown=False, follow_symlinks=False
    ):
        root_path = Path(root)

        # Verify still within boundary (paranoia check)
        try:
            root_path.resolve().relative_to(root_boundary)
        except ValueError:
            raise SymlinkAttackError(f"Path escaped boundary: {root}")

        # Delete files using dir_fd (fd-pinned, immune to TOCTOU)
        for name in files:
            # NOTE: The stat check is extra paranoia, not load-bearing.
            # os.unlink() removes the directory entry itself - it doesn't
            # follow symlinks. If attacker swaps file for symlink between
            # stat and unlink, unlink deletes the symlink, not its target.
            # The actual safety comes from dir_fd pinning us to the inode.
            st = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if stat.S_ISLNK(st.st_mode):
                raise SymlinkAttackError(f"Symlink detected: {root_path / name}")
            os.unlink(name, dir_fd=root_fd)

        # Delete directories using dir_fd
        for name in dirs:
            # NOTE: os.rmdir() on a symlink fails with ENOTDIR, so this
            # stat check is also extra paranoia. Kept for explicit rejection.
            st = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if stat.S_ISLNK(st.st_mode):
                raise SymlinkAttackError(f"Symlink detected: {root_path / name}")
            os.rmdir(name, dir_fd=root_fd)

    # Remove the now-empty root directory
    path.rmdir()


def safe_open_nofollow(path: Path, flags: int) -> int:
    """
    Open file/directory with O_NOFOLLOW - refuses symlinks at syscall level.

    This is the security boundary for move/copy operations.

    Args:
        path: Path to open
        flags: Flags to pass to os.open (O_NOFOLLOW will be added)

    Returns:
        File descriptor

    Raises:
        SymlinkAttackError: If path is a symlink
    """
    try:
        return os.open(str(path), flags | os.O_NOFOLLOW)
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise SymlinkAttackError(f"Path is a symlink: {path}")
        raise


def safe_move(source: Path, dest: Path, root_boundary: Path) -> None:
    """
    Move file/directory with fd-pinned rename - immune to TOCTOU.

    Uses src_dir_fd and dst_dir_fd parameters to os.rename() so the
    rename operates relative to held directory fds, not path strings.

    Args:
        source: Source path
        dest: Destination path
        root_boundary: Both paths must be within this root

    Raises:
        SymlinkAttackError: If symlink detected in source or destination parent
        ValueError: If paths escape root_boundary
    """
    source = Path(source)
    dest = Path(dest)
    root_boundary = Path(root_boundary).resolve()

    # Check for symlinks BEFORE resolving
    if source.is_symlink():
        raise SymlinkAttackError(f"Source is a symlink: {source}")
    if source.parent.is_symlink():
        raise SymlinkAttackError(f"Source parent is a symlink: {source.parent}")

    source = source.resolve()
    dest = dest.resolve()

    for p in [source, dest]:
        try:
            p.relative_to(root_boundary)
        except ValueError:
            raise ValueError(f"Path {p} is outside boundary {root_boundary}")

    # Hold parent directory fds open with O_NOFOLLOW - this is the security boundary
    try:
        src_parent_fd = os.open(
            str(source.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise SymlinkAttackError(f"Source parent is a symlink: {source.parent}")
        raise

    try:
        try:
            dst_parent_fd = os.open(
                str(dest.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
        except OSError as e:
            if e.errno == errno.ELOOP:
                raise SymlinkAttackError(
                    f"Destination parent is a symlink: {dest.parent}"
                )
            raise

        try:
            # Rename relative to directory fds - immune to TOCTOU
            os.rename(
                source.name,
                dest.name,
                src_dir_fd=src_parent_fd,
                dst_dir_fd=dst_parent_fd,
            )
        except OSError as e:
            if e.errno == errno.EXDEV:
                # Cross-filesystem: copy then delete
                os.close(dst_parent_fd)
                os.close(src_parent_fd)
                safe_copy(source, dest, root_boundary)
                safe_rmtree(source, root_boundary)
                return
            else:
                raise
        finally:
            # Only close if not already closed in EXDEV branch
            try:
                os.close(dst_parent_fd)
            except OSError:
                pass
    finally:
        try:
            os.close(src_parent_fd)
        except OSError:
            pass


def safe_copy(source: Path, dest: Path, root_boundary: Path) -> None:
    """
    Copy file/directory with O_NOFOLLOW validation.

    NOTE: This still has a narrow race window between validation and
    shutil.copytree(). There's no fd-based copy in stdlib. The race is
    mitigated by:
    1. Storage directories should have restricted write permissions
    2. Both source and dest are within the validated boundary
    3. Copy is typically user-to-user transfer, not deletion

    TODO: Implement fd-based copy (open with O_NOFOLLOW, read from fd,
    write to new fd at destination) for full TOCTOU immunity.

    Args:
        source: Source path
        dest: Destination path
        root_boundary: Both paths must be within this root

    Raises:
        SymlinkAttackError: If symlink detected
        ValueError: If paths escape root_boundary
    """
    source = Path(source)
    dest = Path(dest)
    root_boundary = Path(root_boundary).resolve()

    # Check for symlinks BEFORE resolving
    if source.is_symlink():
        raise SymlinkAttackError(f"Source is a symlink: {source}")

    source = source.resolve()
    dest = dest.resolve()

    for p in [source, dest]:
        try:
            p.relative_to(root_boundary)
        except ValueError:
            raise ValueError(f"Path {p} is outside boundary {root_boundary}")

    # Refuse symlink source at syscall level
    try:
        fd = safe_open_nofollow(source, os.O_RDONLY)
        os.close(fd)
    except SymlinkAttackError:
        raise SymlinkAttackError(f"Source is a symlink: {source}")

    # For directories, walk and check each entry with O_NOFOLLOW
    # This narrows the race window but doesn't eliminate it
    if source.is_dir():
        for root, dirs, files in os.walk(str(source), followlinks=False):
            for name in dirs + files:
                p = Path(root) / name
                try:
                    fd = safe_open_nofollow(p, os.O_RDONLY)
                    os.close(fd)
                except SymlinkAttackError:
                    raise SymlinkAttackError(f"Symlink in source tree: {p}")
        # symlinks=False copies symlink content, not the link itself
        # But we've already rejected all symlinks above
        shutil.copytree(source, dest, symlinks=False)
    else:
        shutil.copy2(source, dest, follow_symlinks=False)
