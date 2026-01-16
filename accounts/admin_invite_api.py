"""Admin API views for invite management."""

from django.conf import settings
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from core.views import StormCloudBaseAPIView

from .models import EnrollmentKey, PlatformInvite
from .admin_invite_serializers import (
    AdminInviteSerializer,
    AdminInviteListResponseSerializer,
    AdminInviteRevokeResponseSerializer,
    AdminInviteResendResponseSerializer,
)


class CanManageInvites(BasePermission):
    """Permission class for invite management.

    Platform admins (is_staff) can manage all invites.
    Org admins (can_invite) can manage their org's invites only.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        # Check can_invite permission
        account = getattr(request.user, 'account', None)
        if account and account.can_invite:
            return True
        return False


def get_invite_status(invite) -> str:
    """Derive status from model fields.

    Priority: accepted > revoked > expired > pending
    """
    # Check accepted (used)
    if hasattr(invite, 'is_used'):  # PlatformInvite
        if invite.is_used:
            return 'accepted'
    else:  # EnrollmentKey
        if invite.used_by is not None:
            return 'accepted'

    # Check revoked
    if invite.revoked_at is not None or not invite.is_active:
        return 'revoked'

    # Check expired
    if invite.expires_at and timezone.now() > invite.expires_at:
        return 'expired'

    return 'pending'


def serialize_invite(invite, invite_type: str) -> dict:
    """Convert an invite model to a serializable dict."""
    # Get accepted_by info
    accepted_by = None
    accepted_at = None

    if invite_type == 'platform':
        if invite.used_by:
            accepted_by = {
                'id': invite.used_by.user.id,
                'username': invite.used_by.user.username,
            }
            accepted_at = invite.used_at
    else:  # org (EnrollmentKey)
        if invite.used_by:
            accepted_by = {
                'id': invite.used_by.user.id,
                'username': invite.used_by.user.username,
            }
            accepted_at = invite.used_at

    # Get created_by info
    created_by = None
    if invite.created_by:
        created_by = {
            'id': invite.created_by.user.id,
            'username': invite.created_by.user.username,
        }

    # Get organization info
    organization = None
    if invite_type == 'org':
        organization = {
            'id': invite.organization.id,
            'name': invite.organization.name,
        }

    # Get email
    email = invite.email if invite_type == 'platform' else invite.required_email

    return {
        'id': invite.id,
        'token': invite.key,
        'type': invite_type,
        'email': email,
        'name': invite.name,
        'status': get_invite_status(invite),
        'created_at': invite.created_at,
        'expires_at': invite.expires_at,
        'accepted_at': accepted_at,
        'accepted_by': accepted_by,
        'revoked_at': invite.revoked_at,
        'created_by': created_by,
        'organization': organization,
    }


class AdminInviteListView(StormCloudBaseAPIView):
    """List all invites with filtering and pagination."""

    permission_classes = [CanManageInvites]

    @extend_schema(
        operation_id="v1_admin_invites_list",
        summary="Admin: List invitations",
        description="Get list of all invitations with filtering options.",
        parameters=[
            OpenApiParameter(
                name='status',
                description='Filter by status: pending, accepted, expired, revoked',
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name='type',
                description='Filter by type: org, platform',
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name='page',
                description='Page number (default: 1)',
                required=False,
                type=int,
            ),
            OpenApiParameter(
                name='page_size',
                description='Items per page (default: 25, max: 100)',
                required=False,
                type=int,
            ),
        ],
        responses={
            200: AdminInviteListResponseSerializer,
        },
        tags=["Administration"],
    )
    def get(self, request: Request) -> Response:
        """List all invites."""
        # Parse query params
        status_filter = request.query_params.get('status')
        type_filter = request.query_params.get('type')
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 25)), 100)

        # Determine what the user can see
        is_platform_admin = request.user.is_staff
        user_org = None
        if not is_platform_admin:
            account = getattr(request.user, 'account', None)
            if account:
                user_org = account.organization

        # Collect all invites
        all_invites = []

        # Get EnrollmentKeys (org invites)
        if type_filter in (None, 'org'):
            ek_qs = EnrollmentKey.objects.select_related(
                'organization', 'created_by__user', 'used_by__user'
            )
            if not is_platform_admin and user_org:
                ek_qs = ek_qs.filter(organization=user_org)

            for ek in ek_qs:
                invite_data = serialize_invite(ek, 'org')
                if status_filter is None or invite_data['status'] == status_filter:
                    all_invites.append(invite_data)

        # Get PlatformInvites (only for platform admins)
        if is_platform_admin and type_filter in (None, 'platform'):
            pi_qs = PlatformInvite.objects.select_related(
                'created_by__user', 'used_by__user'
            )

            for pi in pi_qs:
                invite_data = serialize_invite(pi, 'platform')
                if status_filter is None or invite_data['status'] == status_filter:
                    all_invites.append(invite_data)

        # Sort by created_at descending
        all_invites.sort(key=lambda x: x['created_at'], reverse=True)

        # Pagination
        total_count = len(all_invites)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_invites = all_invites[start_idx:end_idx]

        # Build next/previous URLs
        base_url = request.build_absolute_uri(request.path)
        next_url = None
        prev_url = None

        if end_idx < total_count:
            next_url = f"{base_url}?page={page + 1}&page_size={page_size}"
            if status_filter:
                next_url += f"&status={status_filter}"
            if type_filter:
                next_url += f"&type={type_filter}"

        if page > 1:
            prev_url = f"{base_url}?page={page - 1}&page_size={page_size}"
            if status_filter:
                prev_url += f"&status={status_filter}"
            if type_filter:
                prev_url += f"&type={type_filter}"

        return Response({
            'count': total_count,
            'next': next_url,
            'previous': prev_url,
            'results': paginated_invites,
        })


def find_invite_by_id(invite_id: str, user, require_pending: bool = False):
    """Find an invite by ID, checking permissions.

    Returns (invite, invite_type, error_response) tuple.
    """
    is_platform_admin = user.is_staff
    user_org = None
    if not is_platform_admin:
        account = getattr(user, 'account', None)
        if account:
            user_org = account.organization

    # Try EnrollmentKey first
    try:
        ek = EnrollmentKey.objects.select_related(
            'organization', 'created_by__user', 'used_by__user'
        ).get(id=invite_id)

        # Check permission
        if not is_platform_admin and user_org and ek.organization != user_org:
            return None, None, Response(
                {'error': {'code': 'NOT_FOUND', 'message': 'Invite not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        invite_status = get_invite_status(ek)
        if require_pending and invite_status != 'pending':
            if invite_status == 'accepted':
                return None, None, Response(
                    {'error': {'code': 'ALREADY_ACCEPTED', 'message': 'Cannot modify an accepted invite.'}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            elif invite_status == 'revoked':
                return None, None, Response(
                    {'error': {'code': 'ALREADY_REVOKED', 'message': 'Invite is already revoked.'}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            else:  # expired
                return None, None, Response(
                    {'error': {'code': 'EXPIRED', 'message': 'Cannot modify an expired invite.'}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return ek, 'org', None
    except EnrollmentKey.DoesNotExist:
        pass

    # Try PlatformInvite (only for platform admins)
    if is_platform_admin:
        try:
            pi = PlatformInvite.objects.select_related(
                'created_by__user', 'used_by__user'
            ).get(id=invite_id)

            invite_status = get_invite_status(pi)
            if require_pending and invite_status != 'pending':
                if invite_status == 'accepted':
                    return None, None, Response(
                        {'error': {'code': 'ALREADY_ACCEPTED', 'message': 'Cannot modify an accepted invite.'}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                elif invite_status == 'revoked':
                    return None, None, Response(
                        {'error': {'code': 'ALREADY_REVOKED', 'message': 'Invite is already revoked.'}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:  # expired
                    return None, None, Response(
                        {'error': {'code': 'EXPIRED', 'message': 'Cannot modify an expired invite.'}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            return pi, 'platform', None
        except PlatformInvite.DoesNotExist:
            pass

    return None, None, Response(
        {'error': {'code': 'NOT_FOUND', 'message': 'Invite not found.'}},
        status=status.HTTP_404_NOT_FOUND,
    )


class AdminInviteRevokeView(StormCloudBaseAPIView):
    """Revoke an invitation."""

    permission_classes = [CanManageInvites]

    @extend_schema(
        operation_id="v1_admin_invites_revoke",
        summary="Admin: Revoke invitation",
        description="Revoke a pending invitation. Cannot revoke accepted invites.",
        responses={
            200: AdminInviteRevokeResponseSerializer,
            400: OpenApiResponse(description="Invite already accepted or revoked"),
            404: OpenApiResponse(description="Invite not found"),
        },
        tags=["Administration"],
    )
    def post(self, request: Request, invite_id: str) -> Response:
        """Revoke an invite."""
        invite, invite_type, error = find_invite_by_id(invite_id, request.user, require_pending=True)
        if error:
            return error

        # Revoke the invite
        invite.is_active = False
        invite.revoked_at = timezone.now()
        invite.save(update_fields=['is_active', 'revoked_at', 'updated_at'])

        return Response({
            'id': invite.id,
            'status': 'revoked',
            'revoked_at': invite.revoked_at,
        })


class AdminInviteResendView(StormCloudBaseAPIView):
    """Resend invitation email."""

    permission_classes = [CanManageInvites]

    @extend_schema(
        operation_id="v1_admin_invites_resend",
        summary="Admin: Resend invitation email",
        description="Resend the invitation email for a pending invite.",
        responses={
            200: AdminInviteResendResponseSerializer,
            400: OpenApiResponse(description="Cannot resend - not pending, no email, or email not configured"),
            404: OpenApiResponse(description="Invite not found"),
        },
        tags=["Administration"],
    )
    def post(self, request: Request, invite_id: str) -> Response:
        """Resend invite email."""
        invite, invite_type, error = find_invite_by_id(invite_id, request.user, require_pending=True)
        if error:
            return error

        # Get email address
        email = invite.email if invite_type == 'platform' else invite.required_email
        if not email:
            return Response(
                {'error': {'code': 'NO_EMAIL', 'message': 'Invite has no email address.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check email is configured
        email_configured = bool(
            settings.EMAIL_HOST and
            settings.EMAIL_BACKEND != 'django.core.mail.backends.console.EmailBackend'
        )
        if not email_configured:
            return Response(
                {'error': {'code': 'EMAIL_NOT_CONFIGURED', 'message': 'Email is not configured on this server.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Send the email
        try:
            if invite_type == 'org':
                from .utils import send_enrollment_invite_email

                # Get inviter name
                inviter_name = None
                if invite.created_by and invite.created_by.user:
                    inviter_name = invite.created_by.user.get_full_name() or invite.created_by.user.username

                # Get server URL
                server_url = request.build_absolute_uri('/').rstrip('/')

                send_enrollment_invite_email(
                    email=email,
                    org_name=invite.organization.name,
                    token=invite.key,
                    inviter_name=inviter_name,
                    server_url=server_url,
                )
            else:  # platform
                from .utils import send_platform_invite_email

                # Get inviter name
                inviter_name = None
                if invite.created_by and invite.created_by.user:
                    inviter_name = invite.created_by.user.get_full_name() or invite.created_by.user.username

                # Get server URL
                server_url = request.build_absolute_uri('/').rstrip('/')

                send_platform_invite_email(
                    email=email,
                    invite_name=invite.name,
                    token=invite.key,
                    inviter_name=inviter_name,
                    server_url=server_url,
                )
        except Exception as e:
            return Response(
                {'error': {'code': 'EMAIL_FAILED', 'message': f'Failed to send email: {str(e)}'}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            'id': invite.id,
            'email': email,
            'message': 'Invitation email resent successfully.',
        })
