"""Factory Boy factories for storage app tests."""

import factory
from storage.models import StoredFile, ShareLink
from accounts.tests.factories import UserFactory


class StoredFileFactory(factory.django.DjangoModelFactory):
    """Factory for StoredFile model."""

    class Meta:
        model = StoredFile

    owner = factory.SubFactory(UserFactory)
    path = factory.Sequence(lambda n: f'file{n}.txt')
    name = factory.LazyAttribute(lambda o: o.path.split('/')[-1])
    size = 1024
    content_type = 'text/plain'
    is_directory = False
    parent_path = ''

    class Params:
        directory = factory.Trait(
            is_directory=True,
            content_type='',
            size=0,
            path=factory.Sequence(lambda n: f'folder{n}'),
        )


class ShareLinkFactory(factory.django.DjangoModelFactory):
    """Factory for ShareLink model."""

    class Meta:
        model = ShareLink

    owner = factory.SubFactory(UserFactory)
    stored_file = factory.SubFactory(StoredFileFactory, owner=factory.SelfAttribute('..owner'))
    file_path = factory.LazyAttribute(lambda o: o.stored_file.path if o.stored_file else 'test-file.txt')
    expiry_days = 7
    is_active = True

    class Params:
        with_password = factory.Trait(
            password_hash=factory.LazyFunction(
                lambda: ShareLink().set_password('test123') or ShareLink.objects.none().first().password_hash
            )
        )
        with_custom_slug = factory.Trait(
            custom_slug=factory.Sequence(lambda n: f'custom-slug-{n}')
        )
        expired = factory.Trait(
            expiry_days=1,
            expires_at=factory.LazyFunction(
                lambda: __import__('django.utils.timezone', fromlist=['timezone']).timezone.now() - __import__('datetime').timedelta(days=2)
            )
        )
        unlimited = factory.Trait(
            expiry_days=0,
            expires_at=None
        )
