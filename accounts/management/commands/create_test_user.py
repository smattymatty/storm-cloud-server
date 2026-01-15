"""Management command to create a test user for development."""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from accounts.models import Account, Organization

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a test user for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default='testuser',
            help='Username for the test user (default: testuser)'
        )
        parser.add_argument(
            '--email',
            type=str,
            default='test@example.com',
            help='Email for the test user (default: test@example.com)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default='testpass123',
            help='Password for the test user (default: testpass123)'
        )
        parser.add_argument(
            '--staff',
            action='store_true',
            help='Make the user a staff member'
        )
        parser.add_argument(
            '--superuser',
            action='store_true',
            help='Make the user a superuser'
        )
        parser.add_argument(
            '--verified',
            action='store_true',
            help='Mark email as verified'
        )
        parser.add_argument(
            '--org-slug',
            type=str,
            default='test-org',
            dest='org_slug',
            help='Organization slug to create user in (default: test-org, creates if needed)'
        )

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']
        is_staff = options['staff']
        is_superuser = options['superuser']
        is_verified = options['verified']
        org_slug = options['org_slug']

        # Check if user exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.ERROR(f'User "{username}" already exists'))
            return

        # Get or create organization
        org, org_created = Organization.objects.get_or_create(
            slug=org_slug,
            defaults={'name': org_slug.replace('-', ' ').title()}
        )
        if org_created:
            self.stdout.write(f'Created organization: {org.name}')

        # Create user
        if is_superuser:
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=is_staff
            )

        # Create account
        account, created = Account.objects.get_or_create(
            user=user,
            defaults={
                'organization': org,
                'email_verified': is_verified or is_superuser,
            }
        )
        if not created and (is_verified or is_superuser):
            account.email_verified = True
            account.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created test user "{username}" '
                f'(staff={user.is_staff}, superuser={user.is_superuser}, '
                f'verified={account.email_verified}, org={org.slug})'
            )
        )
        self.stdout.write(f'Password: {password}')
