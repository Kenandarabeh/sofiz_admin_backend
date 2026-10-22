"""
Institutional Authentication & Authorization API Views for SofizAdmin
Provides secure JWT token lifecycle, rate-limiting, audit logging, and profile management
specifically crafted for the React + Vite single-page frontend.
"""
import logging
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from .models import LoginAuditLog
from .auth_serializers import (
    LoginSerializer,
    UserDetailSerializer,
    ChangePasswordSerializer,
    LoginAuditLogSerializer,
)

logger = logging.getLogger(__name__)


def get_client_ip(request) -> str:
    """Safely extracts real client IP address from request headers"""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or '127.0.0.1'


class LoginRateThrottle(AnonRateThrottle):
    """Protects authentication endpoint against brute-force attacks"""
    rate = '15/minute'


class LoginAPIView(APIView):
    """
    POST /api/auth/login/
    Accepts: { "username": "admin" or "email@example.com", "password": "..." }
    Returns: JWT Access token (60m), Refresh token (7d), and full user profile metadata.
    Enforces brute-force rate-limiting and logs every attempt for compliance.
    """
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        client_ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        identifier = str(request.data.get('username', '')).strip()

        serializer = LoginSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            # Extract failure reason
            errors = serializer.errors
            detail = "Invalid credentials."
            if 'detail' in errors:
                d = errors['detail']
                detail = str(d[0]) if isinstance(d, list) else str(d)
            elif 'non_field_errors' in errors:
                d = errors['non_field_errors']
                detail = str(d[0]) if isinstance(d, list) else str(d)
            elif errors:
                first_k = next(iter(errors))
                val = errors[first_k]
                detail = str(val[0]) if isinstance(val, list) else str(val)

            # Record security audit log
            LoginAuditLog.objects.create(
                username=identifier or 'unknown',
                ip_address=client_ip,
                user_agent=user_agent,
                is_success=False,
                failure_reason=detail
            )
            logger.warning(f"Failed login attempt for '{identifier}' from {client_ip}: {detail}")
            return Response({'success': False, 'error': detail}, status=status.HTTP_401_UNAUTHORIZED)

        user = serializer.validated_data['user']

        # Generate JWT Tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        # Update last login timestamp
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        # Record successful audit log
        LoginAuditLog.objects.create(
            username=user.username,
            user=user,
            ip_address=client_ip,
            user_agent=user_agent,
            is_success=True,
            failure_reason=None
        )
        logger.info(f"Successful login for user '{user.username}' from {client_ip}")

        user_data = UserDetailSerializer(user).data
        jwt_lifetime = settings.SIMPLE_JWT.get('ACCESS_TOKEN_LIFETIME', timedelta(days=1))
        expires_seconds = int(jwt_lifetime.total_seconds()) if hasattr(jwt_lifetime, 'total_seconds') else 86400

        return Response({
            'success': True,
            'access': access_token,
            'refresh': str(refresh),
            'token_type': 'Bearer',
            'expires_in': expires_seconds,
            'user': user_data,
        }, status=status.HTTP_200_OK)


class CustomTokenRefreshView(TokenRefreshView):
    """
    POST /api/auth/refresh/
    Accepts: { "refresh": "<refresh_token>" }
    Refreshes access token with token rotation and old token blacklisting.
    """
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, InvalidToken, User.DoesNotExist):
            return Response({
                'detail': 'Token is invalid or user no longer exists.',
                'code': 'token_not_valid'
            }, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.error(f"Unexpected server error during token refresh: {e}")
            return Response({
                'detail': 'Server error during token refresh. Please retry.',
                'code': 'server_error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        data = serializer.validated_data
        jwt_lifetime = settings.SIMPLE_JWT.get('ACCESS_TOKEN_LIFETIME', timedelta(days=1))
        expires_seconds = int(jwt_lifetime.total_seconds()) if hasattr(jwt_lifetime, 'total_seconds') else 86400

        return Response({
            'success': True,
            'access': data.get('access'),
            'refresh': data.get('refresh', request.data.get('refresh')),
            'token_type': 'Bearer',
            'expires_in': expires_seconds,
        })


class UserProfileAPIView(APIView):
    """
    GET /api/auth/me/
    Returns the authenticated user profile, permissions, roles, and administrative flags.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserDetailSerializer(request.user)
        return Response({
            'success': True,
            'user': serializer.data
        })


class LogoutAPIView(APIView):
    """
    POST /api/auth/logout/
    Accepts: { "refresh": "<refresh_token>" }
    Permanently revokes and blacklists the refresh token.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({
                'success': True,
                'message': "Logged out."
            }, status=status.HTTP_200_OK)

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            # Token already blacklisted, expired, or invalid - treat logout as successful
            pass

        return Response({
            'success': True,
            'message': "Successfully logged out."
        }, status=status.HTTP_200_OK)


class ChangePasswordAPIView(APIView):
    """
    POST /api/auth/change-password/
    Accepts: { "current_password": "...", "new_password": "...", "confirm_new_password": "..." }
    Validates current password, enforces institutional password strength, and updates credentials.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()

        # Generate fresh JWT tokens
        refresh = RefreshToken.for_user(request.user)
        return Response({
            'success': True,
            'message': "Password changed successfully.",
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_200_OK)


class LoginAuditLogListView(generics.ListAPIView):
    """
    GET /api/auth/audit-logs/
    Institutional audit log of authentication activity (restricted to staff & superusers).
    """
    permission_classes = [IsAdminUser]
    serializer_class = LoginAuditLogSerializer
    queryset = LoginAuditLog.objects.all().order_by('-timestamp')
