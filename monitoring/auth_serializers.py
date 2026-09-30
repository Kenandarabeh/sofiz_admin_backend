"""
Authentication & Authorization Serializers for SofizAdmin
Provides institutional-grade authentication, password management, and user serialization
for the React + Vite single-page frontend.
"""
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import LoginAuditLog


class LoginSerializer(serializers.Serializer):
    """
    Dual-identifier login serializer: accepts either username OR email, along with password.
    Enforces active account checks and timing-safe authentication.
    """
    username = serializers.CharField(required=True, trim_whitespace=True)
    password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        identifier = attrs.get('username')
        password = attrs.get('password')

        if not identifier or not password:
            raise serializers.ValidationError("Both username/email and password are required.")

        # Attempt resolution by email or username
        user = None
        if '@' in identifier:
            matched = User.objects.filter(email__iexact=identifier).first()
            if matched:
                user = authenticate(username=matched.username, password=password)
        else:
            user = authenticate(username=identifier, password=password)

        if not user:
            raise serializers.ValidationError({
                "detail": "Invalid credentials. Please verify your username/email and password."
            })

        if not user.is_active:
            raise serializers.ValidationError({
                "detail": "This account is disabled. Please contact the system administrator."
            })

        attrs['user'] = user
        return attrs


class UserDetailSerializer(serializers.ModelSerializer):
    """
    Comprehensive user profile serializer providing role and permission metadata
    for role-based UI rendering in React Vite frontend.
    """
    full_name = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'is_staff',
            'is_superuser',
            'roles',
            'permissions',
            'last_login',
            'date_joined',
        ]
        read_only_fields = fields

    def get_full_name(self, obj) -> str:
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name if name else obj.username

    def get_roles(self, obj) -> list:
        roles = [group.name for group in obj.groups.all()]
        if obj.is_superuser:
            roles.append("SUPER_ADMIN")
        elif obj.is_staff:
            roles.append("STAFF_ADMIN")
        return list(set(roles))

    def get_permissions(self, obj) -> list:
        return list(obj.get_all_permissions())


class ChangePasswordSerializer(serializers.Serializer):
    """
    Enforces rigorous password validation via Django standard password validators
    (length, common passwords, numeric similarity, user attribute similarity).
    """
    current_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_new_password = serializers.CharField(required=True, write_only=True)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password does not match.")
        return value

    def validate(self, attrs):
        new_password = attrs.get('new_password')
        confirm_password = attrs.get('confirm_new_password')
        user = self.context['request'].user

        if new_password != confirm_password:
            raise serializers.ValidationError({"confirm_new_password": "New passwords do not match."})

        # Run Django configured password validators
        errors = []
        try:
            validate_password(new_password, user=user)
        except Exception as e:
            errors.extend(list(e.messages))

        if errors:
            raise serializers.ValidationError({"new_password": errors})

        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class LoginAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAuditLog
        fields = [
            'id',
            'username',
            'user',
            'ip_address',
            'user_agent',
            'is_success',
            'failure_reason',
            'timestamp',
        ]
        read_only_fields = fields
