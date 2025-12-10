"""Factory Boy factories for storage app tests."""

import factory
from storage.models import StoredFile
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
