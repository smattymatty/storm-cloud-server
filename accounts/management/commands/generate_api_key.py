"""Management command to generate an API key for a user."""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from accounts.models import APIKey

User = get_user_model()


class Command(BaseCommand):
    help = 'Generate an API key for a user'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            type=str,
            help='Username of the user to generate a key for'
        )
        parser.add_argument(
            '--name',
            type=str,
            default='CLI Key',
            help='Name for the API key (default: CLI Key)'
        )

    def handle(self, *args, **options):
        username = options['username']
        key_name = options['name']

        # Get user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist')

        # Get user's account and organization
        if not hasattr(user, 'account') or not user.account:
            raise CommandError(f'User "{username}" has no account')
        account = user.account
        organization = account.organization

        # Create API key
        api_key = APIKey.objects.create(
            organization=organization,
            created_by=account,
            name=key_name,
        )

        self.stdout.write(self.style.SUCCESS(f'Successfully generated API key for "{username}"'))
        self.stdout.write(f'Key Name: {api_key.name}')
        self.stdout.write(f'Key ID: {api_key.id}')
        self.stdout.write(self.style.WARNING(f'API Key: {api_key.key}'))
        self.stdout.write(self.style.WARNING('Save this key - it will not be shown again!'))
