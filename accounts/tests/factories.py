"""Factory Boy fixtures for accounts app tests."""

import factory
from factory import fuzzy
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from accounts.models import APIKey, UserProfile, EmailVerificationToken

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    """Factory for creating User instances."""

    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        """Set password after user creation."""
        password = extracted or "testpass123"
        self.set_password(password)  # type: ignore[attr-defined]
        if create:
            self.save()  # type: ignore[attr-defined]

    class Params:
        admin = factory.Trait(
            is_staff=True,
            is_superuser=True,
            username=factory.Sequence(lambda n: f"admin{n}"),
        )


class UserProfileFactory(factory.django.DjangoModelFactory):
    """Factory for creating UserProfile instances."""

    class Meta:
        model = UserProfile

    user = factory.SubFactory(UserFactory)
    is_email_verified = False

    class Params:
        verified = factory.Trait(is_email_verified=True)


class UserWithProfileFactory(UserFactory):
    """Creates a user with associated profile in one call."""

    profile = factory.RelatedFactory(
        UserProfileFactory,
        factory_related_name="user",
    )

    class Params:
        verified = factory.Trait(
            profile__is_email_verified=True,
        )
        admin = factory.Trait(
            is_staff=True,
            is_superuser=True,
            username=factory.Sequence(lambda n: f"admin{n}"),
            profile__is_email_verified=True,
        )


class APIKeyFactory(factory.django.DjangoModelFactory):
    """Factory for creating APIKey instances."""

    class Meta:
        model = APIKey

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"key-{n}")
    is_active = True

    class Params:
        revoked = factory.Trait(
            is_active=False,
            revoked_at=factory.LazyFunction(timezone.now),
        )


class EmailVerificationTokenFactory(factory.django.DjangoModelFactory):
    """Factory for creating EmailVerificationToken instances."""

    class Meta:
        model = EmailVerificationToken

    user = factory.SubFactory(UserFactory)
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=24))

    class Params:
        expired = factory.Trait(
            expires_at=factory.LazyFunction(
                lambda: timezone.now() - timedelta(hours=1)
            ),
        )
        used = factory.Trait(
            used_at=factory.LazyFunction(timezone.now),
        )
