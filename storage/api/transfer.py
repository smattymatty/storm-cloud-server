"""Cross-storage transfer API for moving/copying files between user and org storage."""

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.views import StormCloudBaseAPIView
from core.storage.local import LocalStorageBackend
from core.utils import PathValidationError, normalize_path
from storage.models import StoredFile, FileAuditLog
from storage.api.utils import emit_user_file_action


class StorageTransferRequestSerializer(serializers.Serializer):
    """Serializer for cross-storage transfer request."""

    operation = serializers.ChoiceField(choices=["move", "copy"])
    source_type = serializers.ChoiceField(choices=["user", "org"])
    source_path = serializers.CharField(max_length=1024)
    destination_type = serializers.ChoiceField(choices=["user", "org"])
    destination_path = serializers.CharField(max_length=1024)


class StorageTransferResponseSerializer(serializers.Serializer):
    """Serializer for cross-storage transfer response."""

    success = serializers.BooleanField()
    source = serializers.DictField()
    destination = serializers.DictField()
    file_size = serializers.IntegerField()


class StorageTransferView(StormCloudBaseAPIView):
    """Transfer files between user storage and organization storage."""

    @extend_schema(
        operation_id="v1_storage_transfer",
        summary="Transfer file between storage types",
        description=(
            "Move or copy a file between user (private) and organization (shared) storage. "
            "Quota is checked for copy operations. Move operations don't change total quota "
            "usage since user files count toward org total anyway."
        ),
        request=StorageTransferRequestSerializer,
        responses={
            200: StorageTransferResponseSerializer,
            400: OpenApiResponse(description="Validation error"),
            404: OpenApiResponse(description="Source file not found"),
        },
        tags=["Files"],
    )
    def post(self, request: Request) -> Response:
        """Execute cross-storage transfer."""
        serializer = StorageTransferRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid request data",
                        "details": serializer.errors,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        operation = serializer.validated_data["operation"]
        source_type = serializer.validated_data["source_type"]
        source_path = serializer.validated_data["source_path"]
        destination_type = serializer.validated_data["destination_type"]
        destination_path = serializer.validated_data["destination_path"]

        # Normalize paths
        try:
            source_path = normalize_path(source_path)
            destination_path = normalize_path(destination_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get account and org
        account = request.user.account
        org = account.organization

        if not org:
            return Response(
                {
                    "error": {
                        "code": "NO_ORGANIZATION",
                        "message": "User is not part of an organization",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check permissions
        if operation == "move":
            if not account.can_move:
                return Response(
                    {
                        "error": {
                            "code": "PERMISSION_DENIED",
                            "message": "You do not have permission to move files",
                            "permission": "can_move",
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        elif operation == "copy":
            if not account.can_upload:
                return Response(
                    {
                        "error": {
                            "code": "PERMISSION_DENIED",
                            "message": "You do not have permission to copy files",
                            "permission": "can_upload",
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        backend = LocalStorageBackend()

        # Find source file
        if source_type == "user":
            try:
                source_file = StoredFile.objects.get(owner=account, path=source_path)
            except StoredFile.DoesNotExist:
                return Response(
                    {
                        "error": {
                            "code": "NOT_FOUND",
                            "message": f"Source file not found: {source_path}",
                        }
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:  # source_type == "org"
            try:
                source_file = StoredFile.objects.get(organization=org, path=source_path)
            except StoredFile.DoesNotExist:
                return Response(
                    {
                        "error": {
                            "code": "NOT_FOUND",
                            "message": f"Source file not found in organization storage: {source_path}",
                        }
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        file_size = source_file.size

        # For copy operations, check quota at destination
        if operation == "copy":
            if destination_type == "user":
                # Check user quota
                if account.storage_quota_bytes > 0:
                    if (
                        account.storage_used_bytes + file_size
                        > account.storage_quota_bytes
                    ):
                        return Response(
                            {
                                "error": {
                                    "code": "QUOTA_EXCEEDED",
                                    "message": "Copy would exceed your storage quota",
                                    "quota_type": "user",
                                    "quota_bytes": account.storage_quota_bytes,
                                    "used_bytes": account.storage_used_bytes,
                                    "requested_bytes": file_size,
                                }
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
            # Also check org quota for any copy (user files count toward org total)
            if org.storage_quota_bytes > 0:
                if org.storage_used_bytes + file_size > org.storage_quota_bytes:
                    return Response(
                        {
                            "error": {
                                "code": "QUOTA_EXCEEDED",
                                "message": "Copy would exceed organization storage quota",
                                "quota_type": "organization",
                                "quota_bytes": org.storage_quota_bytes,
                                "used_bytes": org.storage_used_bytes,
                                "requested_bytes": file_size,
                            }
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # Check destination doesn't already exist
        if destination_type == "user":
            if StoredFile.objects.filter(owner=account, path=destination_path).exists():
                return Response(
                    {
                        "error": {
                            "code": "ALREADY_EXISTS",
                            "message": f"File already exists at destination: {destination_path}",
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:  # destination_type == "org"
            if StoredFile.objects.filter(
                organization=org, path=destination_path
            ).exists():
                return Response(
                    {
                        "error": {
                            "code": "ALREADY_EXISTS",
                            "message": f"File already exists in organization storage: {destination_path}",
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Execute the transfer
        try:
            # Get source physical path
            if source_type == "user":
                source_physical = backend._resolve_path(str(account.id), source_path)
            else:
                source_physical = backend._resolve_shared_path(str(org.id), source_path)

            # Get destination physical path
            if destination_type == "user":
                dest_physical = backend._resolve_path(str(account.id), destination_path)
            else:
                dest_physical = backend._resolve_shared_path(
                    str(org.id), destination_path
                )

            # Ensure destination parent exists
            dest_physical.parent.mkdir(parents=True, exist_ok=True)

            if operation == "move":
                # Move file
                import shutil

                shutil.move(str(source_physical), str(dest_physical))

                # Update database: delete old record, create new one
                # Get file attributes before deletion
                file_attrs = {
                    "name": source_file.name,
                    "size": source_file.size,
                    "content_type": source_file.content_type,
                    "is_directory": source_file.is_directory,
                    "encryption_method": source_file.encryption_method,
                    "key_id": source_file.key_id,
                    "encrypted_size": source_file.encrypted_size,
                }
                source_file.delete()

                # Create new record at destination
                dest_name = (
                    destination_path.split("/")[-1]
                    if "/" in destination_path
                    else destination_path
                )
                parent_path = (
                    "/".join(destination_path.split("/")[:-1])
                    if "/" in destination_path
                    else ""
                )

                StoredFile.objects.create(
                    owner=account if destination_type == "user" else None,
                    organization=org if destination_type == "org" else None,
                    path=destination_path,
                    name=dest_name,
                    parent_path=parent_path,
                    **file_attrs,
                )

            else:  # copy
                import shutil

                shutil.copy2(str(source_physical), str(dest_physical))

                # Create new database record
                dest_name = (
                    destination_path.split("/")[-1]
                    if "/" in destination_path
                    else destination_path
                )
                parent_path = (
                    "/".join(destination_path.split("/")[:-1])
                    if "/" in destination_path
                    else ""
                )

                StoredFile.objects.create(
                    owner=account if destination_type == "user" else None,
                    organization=org if destination_type == "org" else None,
                    path=destination_path,
                    name=dest_name,
                    parent_path=parent_path,
                    size=source_file.size,
                    content_type=source_file.content_type,
                    is_directory=source_file.is_directory,
                    encryption_method=source_file.encryption_method,
                    key_id=source_file.key_id,
                    encrypted_size=source_file.encrypted_size,
                )

                # Update quota for copy
                if destination_type == "user":
                    account.update_storage_usage(file_size)
                else:
                    # Org file - update org quota directly
                    org.update_storage_usage(file_size)

            # Log the action
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=(
                    FileAuditLog.ACTION_MOVE
                    if operation == "move"
                    else FileAuditLog.ACTION_COPY
                ),
                path=source_path,
                destination_path=destination_path,
            )

            return Response(
                {
                    "success": True,
                    "source": {"type": source_type, "path": source_path},
                    "destination": {"type": destination_type, "path": destination_path},
                    "file_size": file_size,
                }
            )

        except Exception as e:
            # Log the actual error for debugging, but don't expose to client
            import logging

            logger = logging.getLogger(__name__)
            logger.exception(f"Transfer failed: {e}")
            return Response(
                {
                    "error": {
                        "code": "TRANSFER_FAILED",
                        "message": "Transfer failed. Please try again.",
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
