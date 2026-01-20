"""Async tasks for accounts app."""

from django.core.mail import send_mail, EmailMultiAlternatives
from django.tasks import task


@task
def send_simple_email_async(
    subject: str,
    message: str,
    from_email: str,
    recipient_list: list[str],
):
    """Send simple text email in background."""
    return send_mail(
        subject=subject,
        message=message,
        from_email=from_email,
        recipient_list=recipient_list,
        fail_silently=False,
    )


@task
def send_html_email_async(
    subject: str,
    text_content: str,
    html_content: str,
    from_email: str,
    recipient_list: list[str],
):
    """Send HTML email with text fallback in background."""
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email,
        to=recipient_list,
    )
    msg.attach_alternative(html_content, "text/html")
    return msg.send()
