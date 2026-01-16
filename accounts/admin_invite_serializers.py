"""Serializers for admin invite management."""

from rest_framework import serializers


class InviteCreatedBySerializer(serializers.Serializer):
    """Serializer for the user who created an invite."""

    id = serializers.IntegerField()
    username = serializers.CharField()


class InviteAcceptedBySerializer(serializers.Serializer):
    """Serializer for the user who accepted an invite."""

    id = serializers.IntegerField()
    username = serializers.CharField()


class InviteOrganizationSerializer(serializers.Serializer):
    """Serializer for invite organization info."""

    id = serializers.UUIDField()
    name = serializers.CharField()


class AdminInviteSerializer(serializers.Serializer):
    """Serializer for a unified invite (EnrollmentKey or PlatformInvite)."""

    id = serializers.UUIDField()
    token = serializers.CharField()
    type = serializers.ChoiceField(choices=['org', 'platform'])
    email = serializers.EmailField(allow_null=True)
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=['pending', 'accepted', 'expired', 'revoked'])
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField(allow_null=True)
    accepted_at = serializers.DateTimeField(allow_null=True)
    accepted_by = InviteAcceptedBySerializer(allow_null=True)
    revoked_at = serializers.DateTimeField(allow_null=True)
    created_by = InviteCreatedBySerializer(allow_null=True)
    organization = InviteOrganizationSerializer(allow_null=True)


class AdminInviteListResponseSerializer(serializers.Serializer):
    """Response serializer for paginated invite list."""

    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = AdminInviteSerializer(many=True)


class AdminInviteRevokeResponseSerializer(serializers.Serializer):
    """Response serializer for revoke action."""

    id = serializers.UUIDField()
    status = serializers.CharField()
    revoked_at = serializers.DateTimeField()


class AdminInviteResendResponseSerializer(serializers.Serializer):
    """Response serializer for resend action."""

    id = serializers.UUIDField()
    email = serializers.EmailField()
    message = serializers.CharField()
