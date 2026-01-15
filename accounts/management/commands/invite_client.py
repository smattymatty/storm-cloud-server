"""
Management command to create a platform invite for client onboarding.

Usage:
    python manage.py invite_client ceo@acme.com --name "Acme Onboarding"
    python manage.py invite_client ceo@acme.com --name "Acme" --quota-gb 100 --expires-days 30
"""

from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import PlatformInvite


class Command(BaseCommand):
    """Create a platform invite for a new client."""

    help = "Create a platform invite for client-first enrollment."

    def add_arguments(self, parser):
        parser.add_argument(
            "email",
            type=str,
            help="Email address that must be used to claim this invite."
        )
        parser.add_argument(
            "--name",
            "-n",
            type=str,
            required=True,
            help="Descriptive name for this invite (e.g., 'Acme Corp Onboarding')."
        )
        parser.add_argument(
            "--quota-gb",
            type=int,
            default=0,
            help="Storage quota for the new org in GB. 0 = unlimited. Default: 0"
        )
        parser.add_argument(
            "--expires-days",
            type=int,
            default=7,
            help="Days until invite expires. Default: 7"
        )

    def handle(self, *args, **options):
        email = options["email"].lower()
        name = options["name"]
        quota_gb = options["quota_gb"]
        expires_days = options["expires_days"]

        # Check for existing active invite for this email
        existing = PlatformInvite.objects.filter(
            email=email,
            is_active=True,
            is_used=False
        ).first()

        if existing:
            if existing.is_valid():
                self.stdout.write(
                    self.style.WARNING(
                        f"Active invite already exists for {email}"
                    )
                )
                self.stdout.write(f"Token: {existing.key}")
                self.stdout.write(f"Expires: {existing.expires_at}")
                return
            else:
                # Deactivate expired invite
                existing.is_active = False
                existing.save(update_fields=['is_active', 'updated_at'])

        # Calculate expiration
        expires_at = timezone.now() + timedelta(days=expires_days)

        # Convert GB to bytes
        quota_bytes = quota_gb * 1024 * 1024 * 1024

        # Create invite
        invite = PlatformInvite.objects.create(
            email=email,
            name=name,
            quota_bytes=quota_bytes,
            expires_at=expires_at,
        )

        self.stdout.write(self.style.SUCCESS(f"\nPlatform invite created!"))
        self.stdout.write(f"  Email: {email}")
        self.stdout.write(f"  Name: {name}")
        self.stdout.write(f"  Token: {invite.key}")
        self.stdout.write(f"  Expires: {expires_at.strftime('%Y-%m-%d %H:%M %Z')}")
        if quota_gb:
            self.stdout.write(f"  Org Quota: {quota_gb} GB")
        else:
            self.stdout.write(f"  Org Quota: Unlimited")

        self.stdout.write(self.style.SUCCESS(
            f"\nShare this enrollment URL with the client:"
        ))
        self.stdout.write(f"  /enroll?token={invite.key}")
