"""Management command to clean up stale CMS page mappings."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from cms.models import PageFileMapping

User = get_user_model()


class Command(BaseCommand):
    """Clean up stale CMS page-file mappings."""

    help = "Clean up stale CMS page mappings (not seen in X hours)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=168,
            help="Delete mappings not seen in X hours (default: 168 = 7 days)",
        )
        parser.add_argument(
            "--user",
            type=str,
            help="Only clean up for specific username",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        username = options.get("user")
        dry_run = options["dry_run"]

        if hours < 24:
            self.stderr.write(self.style.ERROR("Minimum threshold is 24 hours"))
            return

        if username:
            try:
                users = [User.objects.get(username=username)]
            except User.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"User not found: {username}"))
                return
        else:
            # All users with mappings
            user_ids = PageFileMapping.objects.values_list(
                "owner_id", flat=True
            ).distinct()
            users = list(User.objects.filter(id__in=user_ids))

        if not users:
            self.stdout.write("No users with mappings found.")
            return

        total_deleted = 0

        for user in users:
            stale = PageFileMapping.get_stale_mappings(user, hours=hours)
            count = stale.count()

            if count > 0:
                if dry_run:
                    self.stdout.write(
                        f"{user.username}: would delete {count} stale mapping(s)"
                    )
                    # Show some examples
                    for mapping in stale[:5]:
                        self.stdout.write(
                            f"  - {mapping.page_path} → {mapping.file_path}"
                        )
                    if count > 5:
                        self.stdout.write(f"  ... and {count - 5} more")
                else:
                    deleted = PageFileMapping.cleanup_stale(user, hours=hours)
                    total_deleted += deleted
                    self.stdout.write(
                        f"{user.username}: deleted {deleted} stale mapping(s)"
                    )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run - nothing deleted"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nTotal deleted: {total_deleted}"))
