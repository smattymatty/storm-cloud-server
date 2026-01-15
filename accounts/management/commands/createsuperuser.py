"""
Custom createsuperuser that also creates Account and Organization.

Wraps Django's built-in createsuperuser to ensure the superuser has
a proper Account and Organization for API key generation.
"""

from django.contrib.auth.management.commands.createsuperuser import (
    Command as BaseCommand,
)

from accounts.models import Account, Organization


class Command(BaseCommand):
    """Extended createsuperuser that creates Account and Organization."""

    help = "Create a superuser with associated Account and Organization."

    def handle(self, *args, **options):
        # Run Django's createsuperuser
        super().handle(*args, **options)

        # Get the created user
        username = options.get(self.UserModel.USERNAME_FIELD)
        if not username:
            # Interactive mode - user was prompted for username
            # We need to find the most recently created superuser
            user = (
                self.UserModel.objects.filter(is_superuser=True)
                .order_by("-date_joined")
                .first()
            )
        else:
            user = self.UserModel.objects.filter(
                **{self.UserModel.USERNAME_FIELD: username}
            ).first()

        if not user:
            return

        # Check if user already has an account
        if hasattr(user, "account"):
            self.stdout.write(
                self.style.WARNING(f"User already has account: {user.account}")
            )
            return

        # Create organization for the superuser
        org_name = f"{user.username}'s Organization"
        org = Organization.objects.create(name=org_name)

        # Create account with owner privileges
        Account.objects.create(
            user=user,
            organization=org,
            email_verified=True,
            is_owner=True,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCreated organization '{org.name}' and account for {user.username}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS("\nNext: Generate API key with 'make api_key'")
        )
