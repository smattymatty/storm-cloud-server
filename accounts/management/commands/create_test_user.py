"""Management command to create a test user for development."""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from accounts.models import UserProfile

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

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']
        is_staff = options['staff']
        is_superuser = options['superuser']
        is_verified = options['verified']

        # Check if user exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.ERROR(f'User "{username}" already exists'))
            return

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

        # Create/update profile
        profile, created = UserProfile.objects.get_or_create(user=user)
        if is_verified or is_superuser:
            profile.is_email_verified = True
            profile.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created test user "{username}" '
                f'(staff={user.is_staff}, superuser={user.is_superuser}, verified={profile.is_email_verified})'
            )
        )
        self.stdout.write(f'Password: {password}')
