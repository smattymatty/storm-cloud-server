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


def send_enrollment_invite_email(email: str, org_name: str, token: str, inviter_name: str = None, server_url: str = None) -> None:
    """Send enrollment invitation email.
    
    Args:
        email: Recipient email address
        org_name: Organization name for the invite
        token: Enrollment token
        inviter_name: Optional name of person who created the invite
        server_url: Backend server URL for the server param
    """
    from urllib.parse import urlencode
    from django.core.mail import EmailMultiAlternatives
    
    # Get frontend URL from settings
    frontend_url = getattr(settings, 'STORMCLOUD_FRONTEND_URL', None)
    
    if frontend_url:
        params = {'token': token}
        if server_url:
            params['server'] = server_url
        invite_link = f"{frontend_url}/cloud/enroll?{urlencode(params)}"
    else:
        invite_link = None
    
    inviter_text = f" by {inviter_name}" if inviter_name else ""
    
    subject = f"You've been invited to join {org_name}"
    
    # Plain text version
    text_content = f"""You've been invited{inviter_text} to join {org_name} on Storm Cloud.

{"Click here to complete your enrollment: " + invite_link if invite_link else "Use enrollment token: " + token}

If you did not expect this invitation, you can safely ignore this email.

- Storm Cloud
"""
    
    # HTML version
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f4f4f5;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 600px; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); padding: 32px 40px; border-radius: 8px 8px 0 0;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">Storm Cloud</h1>
                        </td>
                    </tr>
                    
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 16px 0; color: #1a1a1a; font-size: 20px; font-weight: 600;">You're Invited!</h2>
                            
                            <p style="margin: 0 0 24px 0; color: #4a4a4a; font-size: 16px; line-height: 1.6;">
                                {f"{inviter_name} has" if inviter_name else "You've been"} invited you to join <strong>{org_name}</strong> on Storm Cloud.
                            </p>
                            
                            {f'''<table role="presentation" cellspacing="0" cellpadding="0" style="margin: 32px 0;">
                                <tr>
                                    <td style="background-color: #2d5a87; border-radius: 6px;">
                                        <a href="{invite_link}" style="display: inline-block; padding: 14px 32px; color: #ffffff; text-decoration: none; font-size: 16px; font-weight: 600;">Accept Invitation</a>
                                    </td>
                                </tr>
                            </table>
                            
                            <p style="margin: 0 0 8px 0; color: #6a6a6a; font-size: 14px;">Or copy this link:</p>
                            <p style="margin: 0; padding: 12px; background-color: #f4f4f5; border-radius: 4px; font-size: 13px; color: #4a4a4a; word-break: break-all;">{invite_link}</p>''' if invite_link else f'''
                            <p style="margin: 0; padding: 16px; background-color: #f4f4f5; border-radius: 4px;">
                                <strong style="color: #1a1a1a;">Your enrollment token:</strong><br>
                                <code style="font-size: 14px; color: #2d5a87;">{token}</code>
                            </p>'''}
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 24px 40px; background-color: #f9fafb; border-top: 1px solid #e5e7eb; border-radius: 0 0 8px 8px;">
                            <p style="margin: 0; color: #6b7280; font-size: 13px; line-height: 1.5;">
                                If you didn't expect this invitation, you can safely ignore this email.
                            </p>
                        </td>
                    </tr>
                </table>
                
                <p style="margin: 24px 0 0 0; color: #9ca3af; font-size: 12px;">
                    Sent by Storm Cloud
                </p>
            </td>
        </tr>
    </table>
</body>
</html>"""
    
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)


def send_platform_invite_email(email: str, invite_name: str, token: str, inviter_name: str = None, server_url: str = None) -> None:
    """Send platform invitation email.

    Args:
        email: Recipient email address
        invite_name: Name/description of the invite
        token: Platform invite token
        inviter_name: Optional name of person who created the invite
        server_url: Backend server URL for the server param
    """
    from urllib.parse import urlencode
    from django.core.mail import EmailMultiAlternatives

    # Get frontend URL from settings
    frontend_url = getattr(settings, 'STORMCLOUD_FRONTEND_URL', None)

    if frontend_url:
        params = {'token': token}
        if server_url:
            params['server'] = server_url
        invite_link = f"{frontend_url}/cloud/platform-enroll?{urlencode(params)}"
    else:
        invite_link = None

    inviter_text = f" by {inviter_name}" if inviter_name else ""

    subject = "You've been invited to Storm Cloud"

    # Plain text version
    text_content = f"""You've been invited{inviter_text} to join Storm Cloud.

{invite_name}

{"Click here to complete your enrollment: " + invite_link if invite_link else "Use enrollment token: " + token}

If you did not expect this invitation, you can safely ignore this email.

- Storm Cloud
"""

    # HTML version
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f4f4f5;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 600px; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); padding: 32px 40px; border-radius: 8px 8px 0 0;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">Storm Cloud</h1>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 16px 0; color: #1a1a1a; font-size: 20px; font-weight: 600;">You're Invited!</h2>

                            <p style="margin: 0 0 24px 0; color: #4a4a4a; font-size: 16px; line-height: 1.6;">
                                {f"{inviter_name} has" if inviter_name else "You've been"} invited you to join Storm Cloud.
                            </p>

                            <p style="margin: 0 0 24px 0; color: #6a6a6a; font-size: 14px; line-height: 1.6;">
                                <strong>{invite_name}</strong>
                            </p>

                            {f'''<table role="presentation" cellspacing="0" cellpadding="0" style="margin: 32px 0;">
                                <tr>
                                    <td style="background-color: #2d5a87; border-radius: 6px;">
                                        <a href="{invite_link}" style="display: inline-block; padding: 14px 32px; color: #ffffff; text-decoration: none; font-size: 16px; font-weight: 600;">Accept Invitation</a>
                                    </td>
                                </tr>
                            </table>

                            <p style="margin: 0 0 8px 0; color: #6a6a6a; font-size: 14px;">Or copy this link:</p>
                            <p style="margin: 0; padding: 12px; background-color: #f4f4f5; border-radius: 4px; font-size: 13px; color: #4a4a4a; word-break: break-all;">{invite_link}</p>''' if invite_link else f'''
                            <p style="margin: 0; padding: 16px; background-color: #f4f4f5; border-radius: 4px;">
                                <strong style="color: #1a1a1a;">Your enrollment token:</strong><br>
                                <code style="font-size: 14px; color: #2d5a87;">{token}</code>
                            </p>'''}
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 24px 40px; background-color: #f9fafb; border-top: 1px solid #e5e7eb; border-radius: 0 0 8px 8px;">
                            <p style="margin: 0; color: #6b7280; font-size: 13px; line-height: 1.5;">
                                If you didn't expect this invitation, you can safely ignore this email.
                            </p>
                        </td>
                    </tr>
                </table>

                <p style="margin: 24px 0 0 0; color: #9ca3af; font-size: 12px;">
                    Sent by Storm Cloud
                </p>
            </td>
        </tr>
    </table>
</body>
</html>"""

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)
