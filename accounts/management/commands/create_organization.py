"""
Management command to create a new organization with bootstrap enrollment key.

Usage:
    python manage.py create_organization "Acme Corp" --bootstrap-email ceo@acme.com

This creates:
1. A new Organization with the given name
2. A single-use EnrollmentKey restricted to the bootstrap email
3. The first account created with this key becomes the org owner

The output includes the enrollment key which should be shared with the
organization owner to complete their registration.
"""

from django.core.management.base import BaseCommand, CommandError

from accounts.models import Organization, EnrollmentKey


class Command(BaseCommand):
    help = "Create a new organization with a bootstrap enrollment key"

    def add_arguments(self, parser):
        parser.add_argument(
            "name", type=str, help='Organization name (e.g., "Acme Corp")'
        )
        parser.add_argument(
            "--slug",
            type=str,
            default=None,
            help="Custom URL slug (auto-generated from name if not provided)",
        )
        parser.add_argument(
            "--bootstrap-email",
            type=str,
            required=True,
            dest="bootstrap_email",
            help="Email address for the bootstrap enrollment key (required)",
        )
        parser.add_argument(
            "--quota-gb",
            type=int,
            default=0,
            dest="quota_gb",
            help="Storage quota in GB (0 = unlimited, default: 0)",
        )
        parser.add_argument(
            "--key-name",
            type=str,
            default="Bootstrap Key",
            dest="key_name",
            help='Name for the enrollment key (default: "Bootstrap Key")',
        )

    def handle(self, *args, **options):
        name = options["name"]
        slug = options["slug"]
        bootstrap_email = options["bootstrap_email"].lower().strip()
        quota_gb = options["quota_gb"]
        key_name = options["key_name"]

        # Validate email
        if "@" not in bootstrap_email:
            raise CommandError(f"Invalid email address: {bootstrap_email}")

        # Check if org with same name/slug already exists
        if slug and Organization.objects.filter(slug=slug).exists():
            raise CommandError(f"Organization with slug '{slug}' already exists")

        # Create organization
        org = Organization(
            name=name,
            storage_quota_bytes=quota_gb * 1024 * 1024 * 1024 if quota_gb > 0 else 0,
        )
        if slug:
            org.slug = slug
        org.save()

        self.stdout.write(f"Created organization: {org.name} (slug: {org.slug})")

        # Create bootstrap enrollment key
        enrollment_key = EnrollmentKey.objects.create(
            organization=org,
            name=key_name,
            required_email=bootstrap_email,
            single_use=True,
            preset_permissions={
                # First user gets all admin permissions
                "can_invite": True,
                "can_manage_members": True,
                "can_manage_api_keys": True,
                "is_owner": True,
            },
        )

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("ORGANIZATION CREATED SUCCESSFULLY"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"\nOrganization: {org.name}")
        self.stdout.write(f"Slug:         {org.slug}")
        self.stdout.write(
            f"Quota:        {'Unlimited' if quota_gb == 0 else f'{quota_gb} GB'}"
        )
        self.stdout.write(f"\nBootstrap Enrollment Key:")
        self.stdout.write(self.style.WARNING(f"  {enrollment_key.key}"))
        self.stdout.write(f"\nRequired Email: {bootstrap_email}")
        self.stdout.write("\n" + "-" * 60)
        self.stdout.write("Share this key with the organization owner.")
        self.stdout.write("They must register with the exact email address above.")
        self.stdout.write("This key can only be used once.")
        self.stdout.write("-" * 60 + "\n")

        return enrollment_key.key
