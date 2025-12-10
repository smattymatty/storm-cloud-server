"""Utility functions for accounts app."""

from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailVerificationToken


def get_client_ip(request) -> str:
    """Extract client IP from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def send_verification_email(user, request):
    """Send verification email to user."""
    # Create token
    token = EmailVerificationToken.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(hours=settings.STORMCLOUD_EMAIL_VERIFICATION_EXPIRY_HOURS)
    )

    # Build verification link
    if settings.STORMCLOUD_EMAIL_VERIFICATION_LINK:
        verification_link = settings.STORMCLOUD_EMAIL_VERIFICATION_LINK.format(token=token.token)
    else:
        # Default to API endpoint
        verification_link = f"{request.build_absolute_uri('/api/v1/auth/verify-email/')}?token={token.token}"

    # Send email
    email_body = settings.STORMCLOUD_EMAIL_VERIFICATION_BODY.format(
        username=user.username,
        verification_link=verification_link,
        expiry_hours=settings.STORMCLOUD_EMAIL_VERIFICATION_EXPIRY_HOURS
    )

    send_mail(
        subject=settings.STORMCLOUD_EMAIL_VERIFICATION_SUBJECT,
        message=email_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
