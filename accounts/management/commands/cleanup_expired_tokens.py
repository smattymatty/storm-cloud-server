"""Management command to cleanup expired verification tokens."""

from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import EmailVerificationToken


class Command(BaseCommand):
    help = 'Delete expired email verification tokens'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Find expired tokens
        now = timezone.now()
        expired_tokens = EmailVerificationToken.objects.filter(
            expires_at__lt=now
        )

        count = expired_tokens.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'DRY RUN: Would delete {count} expired tokens')
            )
            if count > 0:
                self.stdout.write('\nExpired tokens:')
                for token in expired_tokens[:10]:  # Show first 10
                    self.stdout.write(
                        f'  - {token.user.username}: expired at {token.expires_at}'
                    )
                if count > 10:
                    self.stdout.write(f'  ... and {count - 10} more')
        else:
            # Delete expired tokens
            expired_tokens.delete()
            self.stdout.write(
                self.style.SUCCESS(f'Successfully deleted {count} expired tokens')
            )
