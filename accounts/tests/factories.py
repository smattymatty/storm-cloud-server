"""Factory Boy fixtures for accounts app tests."""

import secrets
import factory
from factory import fuzzy
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from accounts.models import (
    APIKey,
    Account,
    Organization,
    EmailVerificationToken,
    EnrollmentKey,
    PlatformInvite,
)

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


class OrganizationFactory(factory.django.DjangoModelFactory):
    """Factory for creating Organization instances."""

    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Test Org {n}")
    slug = factory.Sequence(lambda n: f"test-org-{n}")
    is_active = True


class AccountFactory(factory.django.DjangoModelFactory):
    """Factory for creating Account instances (replaces UserProfileFactory)."""

    class Meta:
        model = Account

    user = factory.SubFactory(UserFactory)
    organization = factory.SubFactory(OrganizationFactory)
    email_verified = False

    class Params:
        verified = factory.Trait(email_verified=True)


# Backward compatibility alias
UserProfileFactory = AccountFactory


class UserWithAccountFactory(UserFactory):
    """Creates a user with associated account in one call."""

    account = factory.RelatedFactory(
        AccountFactory,
        factory_related_name="user",
    )

    class Params:
        verified = factory.Trait(
            account__email_verified=True,
        )
        admin = factory.Trait(
            is_staff=True,
            is_superuser=True,
            username=factory.Sequence(lambda n: f"admin{n}"),
            account__email_verified=True,
        )


# Backward compatibility alias
UserWithProfileFactory = UserWithAccountFactory


class APIKeyFactory(factory.django.DjangoModelFactory):
    """Factory for creating APIKey instances."""

    class Meta:
        model = APIKey

    organization = factory.SubFactory(OrganizationFactory)
    created_by = None
    name = factory.Sequence(lambda n: f"key-{n}")
    key = factory.LazyFunction(lambda: f"sk_{secrets.token_urlsafe(32)}")
    is_active = True

    class Params:
        revoked = factory.Trait(
            is_active=False,
            revoked_at=factory.LazyFunction(timezone.now),
        )

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Handle backward-compat user= parameter."""
        user = kwargs.pop("user", None)
        if user and hasattr(user, "account") and user.account:
            # If user has an account, use their organization and set created_by
            if "organization" not in kwargs:
                kwargs["organization"] = user.account.organization
            if "created_by" not in kwargs:
                kwargs["created_by"] = user.account
        return super()._create(model_class, *args, **kwargs)


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


class EnrollmentKeyFactory(factory.django.DjangoModelFactory):
    """Factory for creating EnrollmentKey instances."""

    class Meta:
        model = EnrollmentKey

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Invite {n}")
    single_use = True
    is_active = True
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))

    class Params:
        expired = factory.Trait(
            expires_at=factory.LazyFunction(
                lambda: timezone.now() - timedelta(hours=1)
            ),
        )
        multi_use = factory.Trait(
            single_use=False,
        )
        with_email = factory.Trait(
            required_email=factory.LazyAttribute(
                lambda o: f"invite{secrets.token_hex(4)}@example.com"
            ),
        )


class PlatformInviteFactory(factory.django.DjangoModelFactory):
    """Factory for creating PlatformInvite instances."""

    class Meta:
        model = PlatformInvite

    email = factory.Sequence(lambda n: f"platforminvite{n}@example.com")
    name = factory.Sequence(lambda n: f"Platform Invite {n}")
    created_by = factory.SubFactory(AccountFactory)
    is_active = True
    is_used = False
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))

    class Params:
        expired = factory.Trait(
            expires_at=factory.LazyFunction(
                lambda: timezone.now() - timedelta(hours=1)
            ),
        )
        used = factory.Trait(
            is_used=True,
            used_at=factory.LazyFunction(timezone.now),
        )
