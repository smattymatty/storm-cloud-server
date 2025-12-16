"""Delete GoToSocial posts for expired share links."""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from social.client import GoToSocialClient
from storage.models import ShareLink


class Command(BaseCommand):
    help = "Delete GoToSocial posts for expired share links"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Check if deletion is enabled
        if not getattr(settings, "GOTOSOCIAL_DELETE_ON_REVOKE", True):
            self.stdout.write(
                self.style.WARNING(
                    "GoToSocial post deletion disabled (GOTOSOCIAL_DELETE_ON_REVOKE=false)"
                )
            )
            return

        # Get client
        client = GoToSocialClient.from_settings()
        if not client:
            self.stdout.write(self.style.ERROR("GoToSocial not configured"))
            return

        # Find expired share links with social posts
        now = timezone.now()
        expired_links = ShareLink.objects.filter(
            posted_to_social=True,
            social_post_id__isnull=False,
            expires_at__isnull=False,
            expires_at__lt=now,
        )

        count = expired_links.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("No expired posts to clean up"))
            return

        self.stdout.write(f"Found {count} expired share link(s) with social posts")

        deleted = 0
        for link in expired_links:
            if dry_run:
                self.stdout.write(
                    f"  [DRY RUN] Would delete post: {link.social_post_url}"
                )
            else:
                try:
                    success = client.delete_status(link.social_post_id)
                    if success:
                        self.stdout.write(
                            self.style.SUCCESS(f"  ✓ Deleted post for: {link.file_path}")
                        )
                        deleted += 1
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  ✗ Failed to delete post for: {link.file_path}"
                            )
                        )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ✗ Error deleting post for {link.file_path}: {e}"
                        )
                    )

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"\n[DRY RUN] Would delete {count} post(s)")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\n✓ Deleted {deleted}/{count} post(s)")
            )
