"""Signal handlers for social posting."""
import logging

from django.conf import settings
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from storage.models import ShareLink

from .client import GoToSocialClient
from .middleware import add_social_warning
from .utils import format_share_link_post

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ShareLink)
def post_share_link_to_social(sender, instance, created, **kwargs):
    """
    Post share link to GoToSocial when created.

    Only posts if:
    - Share link was just created (not updated)
    - Social posting is enabled globally
    - Link hasn't already been posted
    - GoToSocial is configured
    """
    # Only run on creation
    if not created:
        return

    # Check if already posted (shouldn't happen, but safety check)
    if instance.posted_to_social:
        return

    # Check global feature flag
    if not getattr(settings, "GOTOSOCIAL_AUTO_POST_ENABLED", False):
        logger.debug("GoToSocial auto-posting disabled globally")
        return

    # Get client
    client = GoToSocialClient.from_settings()
    if not client:
        logger.warning("GoToSocial client not configured, skipping post")
        return

    # Format post content
    try:
        status_text = format_share_link_post(instance)
    except Exception as e:
        logger.error(f"Failed to format share link post: {e}")
        add_social_warning(
            code="SOCIAL_POST_FAILED",
            message="Share link created, but failed to post to Fediverse. Check GoToSocial connection.",
        )
        return

    # Post to GoToSocial
    try:
        response = client.post_status(
            status=status_text,
            visibility=getattr(settings, "GOTOSOCIAL_POST_VISIBILITY", "public"),
        )

        # Update ShareLink with post metadata
        instance.posted_to_social = True
        instance.social_post_id = response.get("id")
        instance.social_post_url = response.get("url")
        instance.save(
            update_fields=["posted_to_social", "social_post_id", "social_post_url"]
        )

        logger.info(
            f"Posted share link {instance.id} to GoToSocial: {response.get('url')}"
        )

    except Exception as e:
        logger.error(f"Failed to post share link to GoToSocial: {e}")
        # Add warning to request context
        add_social_warning(
            code="SOCIAL_POST_FAILED",
            message="Share link created, but failed to post to Fediverse. Check GoToSocial connection.",
        )


@receiver(pre_delete, sender=ShareLink)
def delete_share_link_social_post(sender, instance, **kwargs):
    """
    Delete GoToSocial post when share link is revoked/deleted.

    Only if:
    - Link was posted to social
    - Deletion is enabled in settings
    """
    # Check if this link was posted
    if not instance.posted_to_social or not instance.social_post_id:
        return

    # Check if deletion is enabled
    if not getattr(settings, "GOTOSOCIAL_DELETE_ON_REVOKE", True):
        logger.debug("GoToSocial post deletion disabled")
        return

    # Get client
    client = GoToSocialClient.from_settings()
    if not client:
        return

    # Delete post
    try:
        success = client.delete_status(instance.social_post_id)
        if success:
            logger.info(
                f"Deleted GoToSocial post {instance.social_post_id} for share link {instance.id}"
            )
        else:
            logger.warning(
                f"Failed to delete GoToSocial post {instance.social_post_id}"
            )
    except Exception as e:
        logger.error(f"Error deleting GoToSocial post: {e}")
