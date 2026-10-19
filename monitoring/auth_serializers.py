"""
Authentication & Authorization Serializers for SofizAdmin
Provides institutional-grade authentication, password management, and user serialization
for the React + Vite single-page frontend.
"""
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import LoginAuditLog, OperatorMissionRole


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

        # Strict Frontend Access Gate:
        # 1. Master Django Admin Vault account (vault_ops_769cd6ec) is restricted to the Django admin portal.
        if user.username == 'vault_ops_769cd6ec':
            raise serializers.ValidationError({
                "detail": "Master Django Admin Vault credentials cannot be used to log into the frontend application. Please access the system via the dedicated Admin Vault portal."
            })

        # 2. Designated operational officers and Full Operations Administrators may access the frontend based on role
        profile = getattr(user, 'operator_profile', None)
        is_operational_officer = (
            user.is_superuser
            or user.is_staff
            or (profile is not None)
            or user.groups.filter(name__in=[
                'Full Multi-Family Administrator',
                'Super Administrator',
                'Withdrawal Operations Officer',
                'Game Family Operator',
                'Facture Family Operator',
                'eSIM Family Operator',
                'Treasury & P2P Officer'
            ]).exists()
        )

        if not is_operational_officer:
            raise serializers.ValidationError({
                "detail": "Access restricted: Only authorized operations officers are permitted to log into this workspace."
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
    mission_role = serializers.SerializerMethodField()
    can_assign_tasks_to_others = serializers.SerializerMethodField()

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
            'mission_role',
            'can_assign_tasks_to_others',
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
            roles.append("ADMIN")
        elif obj.is_staff:
            roles.append("STAFF_ADMIN")
            roles.append("ADMIN")
        return list(set(roles))

    def get_permissions(self, obj) -> list:
        return list(obj.get_all_permissions())

    def get_mission_role(self, obj) -> str:
        profile = getattr(obj, 'operator_profile', None)
        return profile.mission_role if profile else ''

    def get_can_assign_tasks_to_others(self, obj) -> bool:
        if obj.is_superuser:
            return True
        if obj.groups.filter(name__in=['Super Administrator', 'Full Multi-Family Administrator']).exists():
            return True
        profile = getattr(obj, 'operator_profile', None)
        if profile and profile.mission_role == OperatorMissionRole.ALL_FAMILIES:
            return True

        if profile and profile.mission_role in [
            OperatorMissionRole.GAME_OPERATOR,
            OperatorMissionRole.FACTURE_OPERATOR,
            OperatorMissionRole.ESIM_OPERATOR,
            OperatorMissionRole.TREASURY_OFFICER,
            OperatorMissionRole.AUDITOR,
        ]:
            return False

        return False


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
