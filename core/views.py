"""Base views for Storm Cloud API."""

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated


class StormCloudBaseAPIView(APIView):
    """
    Base API view for all Storm Cloud endpoints.

    Provides:
    - Authentication required by default
    - Common serializer context
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        """Return context dict for serializers."""
        return {"request": self.request}
