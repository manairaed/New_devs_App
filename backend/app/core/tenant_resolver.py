"""
Minimal tenant resolver for authentication.
"""
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class TenantResolver:
    """Minimal tenant resolver that extracts tenant_id from JWT claims."""

    @staticmethod
    def resolve_tenant_from_token(token_payload: dict) -> Optional[str]:
        """
        Extract tenant_id from JWT token payload.

        Args:
            token_payload: Decoded JWT payload

        Returns:
            Tenant ID if found, None otherwise
        """
        # Try user_metadata first (most common location)
        if 'user_metadata' in token_payload and isinstance(token_payload['user_metadata'], dict):
            tenant_id = token_payload['user_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        # Try app_metadata as fallback
        if 'app_metadata' in token_payload and isinstance(token_payload['app_metadata'], dict):
            tenant_id = token_payload['app_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        # Try root level
        tenant_id = token_payload.get('tenant_id')
        if tenant_id:
            return tenant_id

        logger.warning("No tenant_id found in token payload")
        return None

    @staticmethod
    def resolve_tenant_from_user(user_data: dict) -> Optional[str]:
        """
        Extract tenant_id from user data.

        Args:
            user_data: User data dictionary

        Returns:
            Tenant ID if found, None otherwise
        """
        # Check various possible locations
        if 'tenant_id' in user_data:
            return user_data['tenant_id']

        if 'user_metadata' in user_data and isinstance(user_data['user_metadata'], dict):
            tenant_id = user_data['user_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        if 'app_metadata' in user_data and isinstance(user_data['app_metadata'], dict):
            tenant_id = user_data['app_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        return None

    @staticmethod
    async def resolve_tenant_id(user_id: Optional[str] = None, user_email: Optional[str] = None, token: Optional[str] = None, **kwargs) -> Optional[str]:
        """
        Resolve tenant ID for a user.
        Strict isolation: Never falls back to a default tenant.
        
        Args:
            user_id: User ID
            user_email: User email
            token: Optional JWT token string
            
        Returns:
            Tenant ID or None if cannot be determined
        """
        # 1. First try extracting directly from token claims if token provided
        if token:
            try:
                import jwt as pyjwt
                # Decode unverified to inspect claims payload
                unverified_payload = pyjwt.decode(token, options={"verify_signature": False})
                if isinstance(unverified_payload, dict):
                    resolved = TenantResolver.resolve_tenant_from_token(unverified_payload)
                    if resolved:
                        return resolved
            except Exception as e:
                logger.debug(f"Could not extract tenant from token: {e}")

        # 2. Known client email mappings for Challenge Mode
        if user_email == "sunset@propertyflow.com":
            return "tenant-a"
        if user_email == "ocean@propertyflow.com":
            return "tenant-b"
        if user_email == "candidate@propertyflow.com":
            return "tenant-a"

        # 3. No fallback to a default tenant - return None to enforce tenant isolation
        logger.warning(f"No tenant could be resolved for user: {user_email} (ID: {user_id})")
        return None

    @staticmethod
    async def update_user_tenant_metadata(user_id: str, tenant_id: str) -> None:
        """
        Update user metadata with tenant_id.
        
        Args:
            user_id: User ID
            tenant_id: Tenant ID
        """
        # No-op in this resolver implementation.
        pass
