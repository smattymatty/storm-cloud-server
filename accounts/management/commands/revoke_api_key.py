"""Management command to revoke an API key."""

from django.core.management.base import BaseCommand, CommandError
from accounts.models import APIKey


class Command(BaseCommand):
    help = 'Revoke an API key by ID'

    def add_arguments(self, parser):
        parser.add_argument(
            'key_id',
            type=str,
            help='UUID of the API key to revoke'
        )

    def handle(self, *args, **options):
        key_id = options['key_id']

        # Get API key
        try:
            api_key = APIKey.objects.select_related('organization').get(id=key_id)
        except APIKey.DoesNotExist:
            raise CommandError(f'API key with ID "{key_id}" does not exist')

        if not api_key.is_active:
            self.stdout.write(self.style.WARNING(f'API key "{api_key.name}" is already revoked'))
            return

        # Revoke the key
        api_key.revoke()

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully revoked API key "{api_key.name}" '
                f'for organization "{api_key.organization.name}"'
            )
        )
        self.stdout.write(f'Key ID: {api_key.id}')
        self.stdout.write(f'Revoked at: {api_key.revoked_at}')
