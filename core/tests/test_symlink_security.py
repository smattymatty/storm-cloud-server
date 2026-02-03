"""
Tests for symlink attack prevention in storage operations.

These tests verify that TOCTOU vulnerabilities are mitigated and symlink
attacks are properly rejected. The protection comes from:

1. Fast-reject layer: _resolve_path/_resolve_shared_path check for symlinks
2. FD-based operations: safe_rmtree/safe_move use dir_fd for TOCTOU immunity
3. O_NOFOLLOW: safe_open_nofollow refuses symlinks at syscall level
"""

import os
import shutil
import stat
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock, skipIf

from django.test import TestCase

from core.storage.local import LocalStorageBackend
from core.utils import (
    PathValidationError,
    SymlinkAttackError,
    safe_copy,
    safe_move,
    safe_open_nofollow,
    safe_rmtree,
)


class SymlinkRejectionInPathResolutionTest(TestCase):
    """Test that symlinks are rejected at the path resolution layer."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_root = Path(self.temp_dir) / "storage"
        self.shared_root = Path(self.temp_dir) / "shared"
        self.storage_root.mkdir()
        self.shared_root.mkdir()
        self.backend = LocalStorageBackend(
            storage_root=self.storage_root, shared_root=self.shared_root
        )

        # Create a target outside storage
        self.external_dir = Path(self.temp_dir) / "external"
        self.external_dir.mkdir()
        (self.external_dir / "secret.txt").write_text("sensitive data")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_resolve_path_rejects_symlink_file(self):
        """_resolve_path should reject symlinks to files."""
        # Create symlink inside storage pointing outside
        symlink_path = self.storage_root / "link_to_secret"
        symlink_path.symlink_to(self.external_dir / "secret.txt")

        with self.assertRaises(ValueError) as ctx:
            self.backend._resolve_path("link_to_secret")
        self.assertIn("symlink", str(ctx.exception).lower())

    def test_resolve_path_rejects_symlink_directory(self):
        """_resolve_path should reject symlinks to directories."""
        symlink_path = self.storage_root / "link_to_external"
        symlink_path.symlink_to(self.external_dir)

        with self.assertRaises(ValueError) as ctx:
            self.backend._resolve_path("link_to_external")
        self.assertIn("symlink", str(ctx.exception).lower())

    def test_resolve_path_rejects_symlink_in_path_component(self):
        """_resolve_path should reject symlinks anywhere in path."""
        # Create: storage/realdir/
        real_dir = self.storage_root / "realdir"
        real_dir.mkdir()

        # Create symlink: storage/linkdir -> external/
        link_dir = self.storage_root / "linkdir"
        link_dir.symlink_to(self.external_dir)

        # Try to access: storage/linkdir/secret.txt
        with self.assertRaises(ValueError) as ctx:
            self.backend._resolve_path("linkdir/secret.txt")
        self.assertIn("symlink", str(ctx.exception).lower())

    def test_resolve_path_accepts_regular_paths(self):
        """_resolve_path should accept regular files and directories."""
        # Create regular directory structure
        subdir = self.storage_root / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("content")

        # Should not raise
        resolved = self.backend._resolve_path("subdir/file.txt")
        self.assertEqual(resolved, subdir / "file.txt")

    def test_resolve_shared_path_rejects_symlink(self):
        """_resolve_shared_path should reject symlinks."""
        org_id = "123"
        org_root = self.shared_root / org_id
        org_root.mkdir()

        # Create symlink in shared storage
        symlink_path = org_root / "evil_link"
        symlink_path.symlink_to(self.external_dir)

        with self.assertRaises(ValueError) as ctx:
            self.backend._resolve_shared_path(org_id, "evil_link")
        self.assertIn("symlink", str(ctx.exception).lower())

    def test_resolve_shared_path_accepts_regular_paths(self):
        """_resolve_shared_path should accept regular paths."""
        org_id = "456"
        org_root = self.shared_root / org_id
        org_root.mkdir()
        (org_root / "file.txt").write_text("content")

        resolved = self.backend._resolve_shared_path(org_id, "file.txt")
        self.assertEqual(resolved, org_root / "file.txt")


class SafeRmtreeTest(TestCase):
    """Test safe_rmtree function using fd-based operations."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_root = Path(self.temp_dir) / "storage"
        self.storage_root.mkdir()
        self.external_dir = Path(self.temp_dir) / "external"
        self.external_dir.mkdir()
        (self.external_dir / "secret.txt").write_text("do not delete")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_safe_rmtree_deletes_regular_directory(self):
        """safe_rmtree should delete regular directories."""
        target = self.storage_root / "to_delete"
        target.mkdir()
        (target / "file.txt").write_text("content")
        (target / "subdir").mkdir()
        (target / "subdir" / "nested.txt").write_text("nested")

        safe_rmtree(target, self.storage_root)

        self.assertFalse(target.exists())

    def test_safe_rmtree_deletes_single_file(self):
        """safe_rmtree should handle single file deletion."""
        target = self.storage_root / "single_file.txt"
        target.write_text("content")

        safe_rmtree(target, self.storage_root)

        self.assertFalse(target.exists())

    def test_safe_rmtree_handles_nonexistent_path(self):
        """safe_rmtree should gracefully handle nonexistent paths."""
        target = self.storage_root / "nonexistent"

        # Should not raise
        safe_rmtree(target, self.storage_root)

    def test_safe_rmtree_rejects_symlink_target(self):
        """safe_rmtree should reject if target is a symlink."""
        symlink = self.storage_root / "evil_link"
        symlink.symlink_to(self.external_dir)

        with self.assertRaises(SymlinkAttackError):
            safe_rmtree(symlink, self.storage_root)

        # External directory should still exist
        self.assertTrue(self.external_dir.exists())
        self.assertTrue((self.external_dir / "secret.txt").exists())

    def test_safe_rmtree_rejects_symlink_inside_tree(self):
        """safe_rmtree should reject symlinks inside the tree."""
        target = self.storage_root / "dir_with_symlink"
        target.mkdir()
        (target / "file.txt").write_text("content")
        (target / "evil_link").symlink_to(self.external_dir)

        with self.assertRaises(SymlinkAttackError):
            safe_rmtree(target, self.storage_root)

        # External directory should still exist
        self.assertTrue(self.external_dir.exists())

    def test_safe_rmtree_rejects_path_outside_boundary(self):
        """safe_rmtree should reject paths outside the boundary."""
        with self.assertRaises(ValueError):
            safe_rmtree(self.external_dir, self.storage_root)

        self.assertTrue(self.external_dir.exists())

    def test_platform_support_assertion(self):
        """Verify we fail loudly on unsupported platforms."""
        target = self.storage_root / "test_dir"
        target.mkdir()

        with mock.patch.object(
            shutil.rmtree, "avoids_symlink_attacks", False, create=True
        ):
            with self.assertRaises(RuntimeError) as ctx:
                safe_rmtree(target, self.storage_root)
            self.assertIn("symlink-safe", str(ctx.exception))


class SafeMoveTest(TestCase):
    """Test safe_move function with fd-pinned rename."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_root = Path(self.temp_dir) / "storage"
        self.storage_root.mkdir()
        self.external_dir = Path(self.temp_dir) / "external"
        self.external_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_safe_move_moves_regular_file(self):
        """safe_move should move regular files."""
        source = self.storage_root / "source.txt"
        source.write_text("content")
        dest = self.storage_root / "dest.txt"

        safe_move(source, dest, self.storage_root)

        self.assertFalse(source.exists())
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(), "content")

    def test_safe_move_moves_directory(self):
        """safe_move should move directories."""
        source = self.storage_root / "source_dir"
        source.mkdir()
        (source / "file.txt").write_text("content")
        dest = self.storage_root / "dest_dir"

        safe_move(source, dest, self.storage_root)

        self.assertFalse(source.exists())
        self.assertTrue(dest.exists())
        self.assertTrue((dest / "file.txt").exists())

    def test_safe_move_rejects_symlink_source_parent(self):
        """safe_move should reject symlink in source parent path."""
        # Create symlink as parent directory
        (self.external_dir / "file.txt").write_text("content")
        link_dir = self.storage_root / "link_parent"
        link_dir.symlink_to(self.external_dir)

        dest = self.storage_root / "dest.txt"

        # Opening link_parent with O_NOFOLLOW | O_DIRECTORY should fail
        with self.assertRaises(SymlinkAttackError):
            safe_move(link_dir / "file.txt", dest, self.storage_root)

    def test_safe_move_rejects_path_outside_boundary(self):
        """safe_move should reject paths outside boundary."""
        source = self.storage_root / "source.txt"
        source.write_text("content")

        with self.assertRaises(ValueError):
            safe_move(source, self.external_dir / "dest.txt", self.storage_root)


class SafeCopyTest(TestCase):
    """Test safe_copy function with O_NOFOLLOW validation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_root = Path(self.temp_dir) / "storage"
        self.storage_root.mkdir()
        self.external_dir = Path(self.temp_dir) / "external"
        self.external_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_safe_copy_copies_regular_file(self):
        """safe_copy should copy regular files."""
        source = self.storage_root / "source.txt"
        source.write_text("content")
        dest = self.storage_root / "dest.txt"

        safe_copy(source, dest, self.storage_root)

        self.assertTrue(source.exists())
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(), "content")

    def test_safe_copy_copies_directory(self):
        """safe_copy should copy directories."""
        source = self.storage_root / "source_dir"
        source.mkdir()
        (source / "file.txt").write_text("content")
        dest = self.storage_root / "dest_dir"

        safe_copy(source, dest, self.storage_root)

        self.assertTrue(source.exists())
        self.assertTrue(dest.exists())
        self.assertTrue((dest / "file.txt").exists())

    def test_safe_copy_rejects_symlink_source(self):
        """safe_copy should reject symlink sources."""
        (self.external_dir / "secret.txt").write_text("secret")
        source = self.storage_root / "link"
        source.symlink_to(self.external_dir / "secret.txt")
        dest = self.storage_root / "dest.txt"

        with self.assertRaises(SymlinkAttackError):
            safe_copy(source, dest, self.storage_root)

    def test_safe_copy_rejects_symlink_in_source_tree(self):
        """safe_copy should reject symlinks inside source directory."""
        source = self.storage_root / "source_dir"
        source.mkdir()
        (source / "file.txt").write_text("content")
        (source / "evil_link").symlink_to(self.external_dir)
        dest = self.storage_root / "dest_dir"

        with self.assertRaises(SymlinkAttackError):
            safe_copy(source, dest, self.storage_root)


class SafeOpenNoFollowTest(TestCase):
    """Test safe_open_nofollow function."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_root = Path(self.temp_dir) / "storage"
        self.storage_root.mkdir()
        self.external_dir = Path(self.temp_dir) / "external"
        self.external_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_opens_regular_file(self):
        """safe_open_nofollow should open regular files."""
        target = self.storage_root / "file.txt"
        target.write_text("content")

        fd = safe_open_nofollow(target, os.O_RDONLY)
        try:
            self.assertIsInstance(fd, int)
            self.assertGreater(fd, 0)
        finally:
            os.close(fd)

    def test_opens_directory(self):
        """safe_open_nofollow should open directories."""
        target = self.storage_root / "dir"
        target.mkdir()

        fd = safe_open_nofollow(target, os.O_RDONLY | os.O_DIRECTORY)
        try:
            self.assertIsInstance(fd, int)
        finally:
            os.close(fd)

    def test_rejects_symlink(self):
        """safe_open_nofollow should reject symlinks with SymlinkAttackError."""
        target = self.storage_root / "link"
        target.symlink_to(self.external_dir)

        with self.assertRaises(SymlinkAttackError):
            safe_open_nofollow(target, os.O_RDONLY)


@skipIf(os.name == "nt", "Symlink race tests not reliable on Windows")
class RacingTOCTOUTest(TestCase):
    """
    Actually race a thread to swap symlinks during deletion.

    This is the critical test - we spawn a thread that continuously
    tries to replace directories with symlinks while deletion is
    in progress. The fd-based approach should be immune.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_root = Path(self.temp_dir) / "storage"
        self.storage_root.mkdir()
        self.external_dir = Path(self.temp_dir) / "external"
        self.external_dir.mkdir()
        (self.external_dir / "critical.txt").write_text("DO NOT DELETE")
        # Staging area for pre-prepared symlinks (atomic swap attack)
        self.symlink_staging = Path(self.temp_dir) / "staging"
        self.symlink_staging.mkdir()
        self.stop_racing = threading.Event()

    def tearDown(self):
        self.stop_racing.set()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_racing_symlink_swap_during_deletion(self):
        """
        Spawn thread that races to swap symlinks during deletion.
        Run many iterations to exercise the race window.
        """

        def attacker_thread(
            target_dir: Path, external: Path, symlink_staging: Path, stop_event
        ):
            """
            Continuously try to atomically swap target with a pre-prepared symlink.
            Uses os.rename() for atomic swap - this is what a real attacker would do.
            """
            counter = 0
            while not stop_event.is_set():
                try:
                    # Prepare symlink in staging area
                    staged_symlink = symlink_staging / f"attack_{os.getpid()}_{counter}"
                    counter += 1
                    if staged_symlink.exists() or staged_symlink.is_symlink():
                        staged_symlink.unlink()
                    staged_symlink.symlink_to(external)

                    # Atomic swap: rename staged symlink over target
                    # This is a single syscall with no gap
                    os.rename(staged_symlink, target_dir)
                except (OSError, FileNotFoundError):
                    pass
                time.sleep(0.0001)  # Tight loop

        # Run 50 iterations (reduced for test speed)
        for i in range(50):
            # Create target directory with nested structure
            target = self.storage_root / f"victim_{i}"
            target.mkdir()
            for j in range(3):
                subdir = target / f"subdir_{j}"
                subdir.mkdir()
                (subdir / "file.txt").write_text("content")

            # Start attacker thread with atomic swap attack
            self.stop_racing.clear()
            attacker = threading.Thread(
                target=attacker_thread,
                args=(
                    target,
                    self.external_dir,
                    self.symlink_staging,
                    self.stop_racing,
                ),
            )
            attacker.start()

            try:
                # Attempt deletion - should either succeed or raise SymlinkAttackError
                # Should NEVER delete external_dir contents
                safe_rmtree(target, self.storage_root)
            except (SymlinkAttackError, FileNotFoundError, OSError):
                pass  # Expected when race is detected
            finally:
                self.stop_racing.set()
                attacker.join(timeout=1)

            # CRITICAL ASSERTION: external dir must be intact
            self.assertTrue(
                self.external_dir.exists(),
                f"External directory was deleted on iteration {i}!",
            )
            self.assertTrue(
                (self.external_dir / "critical.txt").exists(),
                f"External file was deleted on iteration {i}!",
            )

        # If we get here without deleting external_dir, the protection works


class LocalStorageBackendSecurityTest(TestCase):
    """Test that LocalStorageBackend methods are protected against symlink attacks."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_root = Path(self.temp_dir) / "storage"
        self.shared_root = Path(self.temp_dir) / "shared"
        self.storage_root.mkdir()
        self.shared_root.mkdir()
        self.backend = LocalStorageBackend(
            storage_root=self.storage_root, shared_root=self.shared_root
        )

        self.external_dir = Path(self.temp_dir) / "external"
        self.external_dir.mkdir()
        (self.external_dir / "secret.txt").write_text("sensitive")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_move_rejects_symlink_source(self):
        """Backend move should reject symlink sources."""
        # Create source directory in storage
        (self.storage_root / "source").mkdir()
        (self.storage_root / "source" / "file.txt").write_text("content")

        # Create destination directory
        (self.storage_root / "dest").mkdir()

        # Create symlink as source
        symlink = self.storage_root / "evil_source"
        symlink.symlink_to(self.external_dir)

        # Trying to move the symlink should fail at path resolution
        with self.assertRaises(ValueError):
            self.backend.move("evil_source", "dest")

    def test_copy_rejects_symlink_source(self):
        """Backend copy should reject symlink sources."""
        # Create destination directory
        (self.storage_root / "dest").mkdir()

        # Create symlink as source
        symlink = self.storage_root / "evil_source"
        symlink.symlink_to(self.external_dir)

        # Trying to copy the symlink should fail at path resolution
        with self.assertRaises(ValueError):
            self.backend.copy("evil_source", "dest")

    def test_move_shared_rejects_symlink(self):
        """Backend move_shared should reject symlinks."""
        org_id = "org1"
        org_root = self.shared_root / org_id
        org_root.mkdir()

        # Create legitimate directory
        (org_root / "source").mkdir()
        (org_root / "source" / "file.txt").write_text("content")
        (org_root / "dest").mkdir()

        # Create symlink
        symlink = org_root / "evil"
        symlink.symlink_to(self.external_dir)

        with self.assertRaises(ValueError):
            self.backend.move_shared(org_id, "evil", "dest")

    def test_copy_shared_rejects_symlink(self):
        """Backend copy_shared should reject symlinks."""
        org_id = "org2"
        org_root = self.shared_root / org_id
        org_root.mkdir()

        (org_root / "dest").mkdir()

        symlink = org_root / "evil"
        symlink.symlink_to(self.external_dir)

        with self.assertRaises(ValueError):
            self.backend.copy_shared(org_id, "evil", "dest")
