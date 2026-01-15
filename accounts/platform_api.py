"""
Platform-level API endpoints for client enrollment.

Two-step enrollment flow:
1. Admin creates a platform invite for a potential client
2. Client validates the invite token
3. Step 1: Client enrolls (POST /platform/enroll/) - creates User only, logs in
4. Step 2: Client sets up org (POST /platform/setup-org/) - creates Org + Account
"""

from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Account, Organization, PlatformInvite
from .platform_serializers import (
    PlatformEnrollResponseSerializer,
    PlatformEnrollSerializer,
    PlatformInviteCreateSerializer,
    PlatformInviteResponseSerializer,
    PlatformInviteValidateResponseSerializer,
    PlatformInviteValidateSerializer,
    PlatformSetupOrgResponseSerializer,
    PlatformSetupOrgSerializer,
)


User = get_user_model()


class PlatformInviteCreateView(APIView):
    """
    Create a platform invite for a new client.

    POST /api/v1/platform/invite/create/
    Admin only - creates an invite that allows a client to sign up
    and create their own organization.
    """

    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = PlatformInviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # Calculate expiration
        expires_at = timezone.now() + timedelta(days=data.get('expires_in_days', 7))

        # Convert GB to bytes
        quota_bytes = data['quota_gb'] * 1024 * 1024 * 1024

        # Get creating account (if authenticated via account, not just admin user)
        created_by = None
        if hasattr(request.user, 'account'):
            created_by = request.user.account

        invite = PlatformInvite.objects.create(
            email=data['email'].lower(),
            name=data['name'],
            quota_bytes=quota_bytes,
            expires_at=expires_at,
            created_by=created_by,
        )

        response_serializer = PlatformInviteResponseSerializer(invite)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class PlatformInviteListView(APIView):
    """
    List all platform invites.

    GET /api/v1/platform/invites/
    Admin only.
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        invites = PlatformInvite.objects.all().order_by('-created_at')

        # Optional filters
        if request.query_params.get('active') == 'true':
            invites = invites.filter(is_active=True, is_used=False)
        elif request.query_params.get('used') == 'true':
            invites = invites.filter(is_used=True)

        serializer = PlatformInviteResponseSerializer(invites, many=True)
        return Response(serializer.data)


class PlatformInviteDetailView(APIView):
    """
    Get, update, or delete a platform invite.

    GET/DELETE /api/v1/platform/invites/{id}/
    Admin only.
    """

    permission_classes = [IsAdminUser]

    def get(self, request, invite_id):
        try:
            invite = PlatformInvite.objects.get(id=invite_id)
        except PlatformInvite.DoesNotExist:
            return Response(
                {'error': {'code': 'NOT_FOUND', 'message': 'Invite not found'}},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = PlatformInviteResponseSerializer(invite)
        return Response(serializer.data)

    def delete(self, request, invite_id):
        try:
            invite = PlatformInvite.objects.get(id=invite_id)
        except PlatformInvite.DoesNotExist:
            return Response(
                {'error': {'code': 'NOT_FOUND', 'message': 'Invite not found'}},
                status=status.HTTP_404_NOT_FOUND
            )

        if invite.is_used:
            return Response(
                {'error': {'code': 'ALREADY_USED', 'message': 'Cannot delete used invite'}},
                status=status.HTTP_400_BAD_REQUEST
            )

        invite.is_active = False
        invite.save(update_fields=['is_active', 'updated_at'])

        return Response({'message': 'Invite deactivated'})


class PlatformInviteValidateView(APIView):
    """
    Validate a platform invite token.

    POST /api/v1/platform/invite/validate/
    Public endpoint - allows clients to check if their invite is valid
    before starting the enrollment form.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PlatformInviteValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['token']

        try:
            invite = PlatformInvite.objects.get(key=token)
        except PlatformInvite.DoesNotExist:
            return Response(
                {'error': {'code': 'INVALID_TOKEN', 'message': 'Invalid invite token'}},
                status=status.HTTP_404_NOT_FOUND
            )

        response_data = {
            'email': invite.email,
            'name': invite.name,
            'is_valid': invite.is_valid(),
            'expires_at': invite.expires_at,
        }

        if not invite.is_valid():
            if invite.is_used:
                response_data['invalid_reason'] = 'already_used'
            elif not invite.is_active:
                response_data['invalid_reason'] = 'deactivated'
            elif invite.expires_at and timezone.now() > invite.expires_at:
                response_data['invalid_reason'] = 'expired'

        response_serializer = PlatformInviteValidateResponseSerializer(data=response_data)
        response_serializer.is_valid()
        return Response(response_data)


class PlatformEnrollView(APIView):
    """
    Step 1: Create user account using a platform invite.

    POST /api/v1/platform/enroll/
    Public endpoint - creates User only, sets session cookie.
    User must then call /platform/setup-org/ to complete enrollment.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PlatformEnrollSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # Validate token
        try:
            invite = PlatformInvite.objects.get(key=data['token'])
        except PlatformInvite.DoesNotExist:
            return Response(
                {'error': {'code': 'INVALID_TOKEN', 'message': 'Invalid invite token'}},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if someone already started enrollment with this invite
        if invite.enrolled_user is not None:
            return Response(
                {'error': {
                    'code': 'ALREADY_ENROLLED',
                    'message': 'User already created. Please log in and complete org setup.'
                }},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if invite is still valid
        if not invite.is_valid():
            if invite.is_used:
                reason = 'This invite has already been used.'
            elif not invite.is_active:
                reason = 'This invite has been deactivated.'
            else:
                reason = 'This invite has expired.'
            return Response(
                {'error': {'code': 'INVALID_INVITE', 'message': reason}},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify email matches
        if data['email'].lower() != invite.email.lower():
            return Response(
                {'error': {
                    'code': 'EMAIL_MISMATCH',
                    'message': 'Email does not match the invite.'
                }},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create user and link to invite
        with transaction.atomic():
            user = User.objects.create_user(
                username=data['username'],
                email=data['email'].lower(),
                password=data['password'],
            )

            # Link user to invite (for step 2)
            invite.enrolled_user = user
            invite.save(update_fields=['enrolled_user', 'updated_at'])

        # Log user in (set session cookie)
        login(request, user)

        # Calculate quota in GB for response
        quota_gb = invite.quota_bytes // (1024 * 1024 * 1024) if invite.quota_bytes else 0

        response_data = {
            'user_id': user.id,
            'username': user.username,
            'needs_org_setup': True,
            'invite_name': invite.name,
            'quota_gb': quota_gb,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)


class PlatformSetupOrgView(APIView):
    """
    Step 2: Create organization and account.

    POST /api/v1/platform/setup-org/
    Authenticated endpoint - user must have a pending platform invite.
    Creates Organization and Account, completes enrollment.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Check user has pending invite
        try:
            invite = request.user.pending_platform_invite
        except PlatformInvite.DoesNotExist:
            return Response(
                {'error': {
                    'code': 'NO_PENDING_INVITE',
                    'message': 'No pending enrollment found. Please start from invite link.'
                }},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check user doesn't already have an account
        if hasattr(request.user, 'account'):
            return Response(
                {'error': {
                    'code': 'ALREADY_HAS_ACCOUNT',
                    'message': 'User already has an account.'
                }},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = PlatformSetupOrgSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # Create org and account in transaction
        with transaction.atomic():
            # Create organization
            org = Organization.objects.create(
                name=data['organization_name'],
                slug=data.get('organization_slug') or None,  # Let model auto-generate
                storage_quota_bytes=invite.quota_bytes,
            )

            # Create account (org owner)
            account = Account.objects.create(
                user=request.user,
                organization=org,
                email_verified=False,  # Will need email verification
                is_owner=True,
                can_invite=True,
                can_manage_members=True,
                can_manage_api_keys=True,
            )

            # Mark invite as fully used
            invite.is_used = True
            invite.used_by = account
            invite.used_at = timezone.now()
            invite.enrolled_user = None  # Clear pending state
            invite.save(update_fields=[
                'is_used', 'used_by', 'used_at', 'enrolled_user', 'updated_at'
            ])

        response_data = {
            'organization_id': org.id,
            'organization_name': org.name,
            'organization_slug': org.slug,
            'account_id': account.id,
            'message': 'Organization created successfully.',
        }

        return Response(response_data, status=status.HTTP_201_CREATED)
