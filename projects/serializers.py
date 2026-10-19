from decimal import Decimal
from django.contrib.auth.models import User
from rest_framework import serializers
from .models import (
    Project,
    ProjectStatus,
    ProjectPriority,
    Task,
    TaskStatus,
    TaskPriority,
    TaskComment,
    TaskActivityLog,
)
from monitoring.models import OperatorMissionRole


class UserSummarySerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    employee_code = serializers.SerializerMethodField()
    mission_role = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()
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
            'employee_code',
            'mission_role',
            'phone_number',
            'can_assign_tasks_to_others',
        ]

    def get_full_name(self, obj) -> str:
        name = f'{obj.first_name} {obj.last_name}'.strip()
        return name if name else obj.username

    def get_roles(self, obj) -> list:
        roles = [group.name for group in obj.groups.all()]
        if obj.is_superuser:
            roles.append("SUPER_ADMIN")
        elif obj.is_staff and not roles:
            roles.append("STAFF_ADMIN")
        return list(set(roles))

    def get_employee_code(self, obj) -> str:
        profile = getattr(obj, 'operator_profile', None)
        return profile.employee_code if profile else ''

    def get_mission_role(self, obj) -> str:
        profile = getattr(obj, 'operator_profile', None)
        return profile.mission_role if profile else ''

    def get_phone_number(self, obj) -> str:
        profile = getattr(obj, 'operator_profile', None)
        return profile.phone_number if profile else ''

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

    def get_employee_code(self, obj) -> str:
        profile = getattr(obj, 'operator_profile', None)
        return profile.employee_code if profile else ''

    def get_mission_role(self, obj) -> str:
        profile = getattr(obj, 'operator_profile', None)
        return profile.mission_role if profile else ''

    def get_phone_number(self, obj) -> str:
        profile = getattr(obj, 'operator_profile', None)
        return profile.phone_number if profile else ''


class CreateStaffMemberSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=True)
    full_name = serializers.CharField(max_length=150, required=True)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(max_length=128, required=True, write_only=True)
    mission_role = serializers.CharField(max_length=50, required=False, default='GAME_OPERATOR')
    mission_roles = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list
    )
    phone_number = serializers.CharField(
        max_length=50,
        required=True,
        allow_blank=False,
        error_messages={
            'required': 'WhatsApp phone number is required to send reminders.',
            'blank': 'WhatsApp phone number cannot be blank.'
        }
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_username(self, value):
        val = value.strip()
        if User.objects.filter(username__iexact=val).exists():
            raise serializers.ValidationError('This username is already taken.')
        return val

    def validate_email(self, value):
        val = value.strip().lower()
        if User.objects.filter(email__iexact=val).exists():
            raise serializers.ValidationError('This email address is already in use.')
        return val


class TaskActivityLogSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)

    class Meta:
        model = TaskActivityLog
        fields = ['id', 'task', 'user', 'action', 'details', 'created_at']


class TaskCommentSerializer(serializers.ModelSerializer):
    author = UserSummarySerializer(read_only=True)

    class Meta:
        model = TaskComment
        fields = ['id', 'task', 'author', 'content', 'created_at', 'updated_at']
        read_only_fields = ['id', 'author', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        comment = super().create(validated_data)
        TaskActivityLog.objects.create(
            task=comment.task,
            user=self.context['request'].user,
            action='COMMENT_ADDED',
            details={'comment_id': comment.id, 'snippet': comment.content[:60]}
        )
        return comment


class TaskSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(),
        required=False,
        allow_null=True
    )
    project_name = serializers.CharField(source='project.name', read_only=True, default='')
    project_key = serializers.CharField(source='project.key', read_only=True, default='')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    item_type_display = serializers.CharField(source='get_item_type_display', read_only=True)
    
    assignee = UserSummarySerializer(read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='assignee',
        write_only=True,
        required=False,
        allow_null=True
    )
    reporter = UserSummarySerializer(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    comments_count = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id',
            'project',
            'project_name',
            'project_key',
            'task_key',
            'title',
            'description',
            'status',
            'status_display',
            'priority',
            'priority_display',
            'assignee',
            'assignee_id',
            'reporter',
            'due_date',
            'due_time',
            'item_type',
            'item_type_display',
            'whatsapp_phone',
            'whatsapp_sent_at',
            'tags',
            'order',
            'estimated_hours',
            'logged_hours',
            'completed_at',
            'is_overdue',
            'comments_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'task_key', 'reporter', 'completed_at', 'created_at', 'updated_at']

    def get_comments_count(self, obj) -> int:
        return obj.comments.count()

    def validate(self, attrs):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            user = request.user
            assignee = attrs.get('assignee')

            # Check if assignee is provided and differs from the current user
            if assignee and assignee.id != user.id:
                is_admin = (
                    user.is_superuser or
                    user.groups.filter(name__in=['Super Administrator', 'Full Multi-Family Administrator']).exists()
                )
                profile = getattr(user, 'operator_profile', None)
                is_all_families = profile and profile.mission_role == OperatorMissionRole.ALL_FAMILIES
                project = attrs.get('project') or (self.instance.project if self.instance else None)
                is_project_lead = project and project.lead_id == user.id

                # Restricted operators (departmental operators)
                is_restricted_operator = bool(
                    profile and profile.mission_role in [
                        OperatorMissionRole.GAME_OPERATOR,
                        OperatorMissionRole.FACTURE_OPERATOR,
                        OperatorMissionRole.ESIM_OPERATOR,
                        OperatorMissionRole.TREASURY_OFFICER,
                        OperatorMissionRole.AUDITOR,
                    ]
                )

                if is_restricted_operator or not (is_admin or is_all_families or is_project_lead):
                    raise serializers.ValidationError({
                        'assignee_id': f"User '{user.username}' cannot assign tasks to other team members. Operators can only assign tasks to themselves."
                    })

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            user = request.user
            validated_data['reporter'] = user

            # Auto-assign to self if user is a restricted operator and no assignee was given
            profile = getattr(user, 'operator_profile', None)
            is_restricted_operator = bool(
                profile and profile.mission_role in [
                    OperatorMissionRole.GAME_OPERATOR,
                    OperatorMissionRole.FACTURE_OPERATOR,
                    OperatorMissionRole.ESIM_OPERATOR,
                    OperatorMissionRole.TREASURY_OFFICER,
                    OperatorMissionRole.AUDITOR,
                ]
            )
            if is_restricted_operator and 'assignee' not in validated_data:
                validated_data['assignee'] = user

        task = super().create(validated_data)
        TaskActivityLog.objects.create(
            task=task,
            user=request.user if request and request.user.is_authenticated else None,
            action='TASK_CREATED',
            details={'task_key': task.task_key, 'title': task.title}
        )
        return task

    def update(self, instance, validated_data):
        request = self.context.get('request')
        old_status = instance.status
        old_assignee = instance.assignee

        task = super().update(instance, validated_data)

        # Log changes
        if 'status' in validated_data and validated_data['status'] != old_status:
            TaskActivityLog.objects.create(
                task=task,
                user=request.user if request and request.user.is_authenticated else None,
                action='STATUS_CHANGED',
                details={'from': old_status, 'to': task.status}
            )

        if 'assignee' in validated_data and validated_data['assignee'] != old_assignee:
            TaskActivityLog.objects.create(
                task=task,
                user=request.user if request and request.user.is_authenticated else None,
                action='ASSIGNEE_CHANGED',
                details={
                    'from': old_assignee.username if old_assignee else None,
                    'to': task.assignee.username if task.assignee else None
                }
            )

        return task


class ProjectSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    lead = UserSummarySerializer(read_only=True)
    lead_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='lead',
        write_only=True,
        required=False,
        allow_null=True
    )
    created_by = UserSummarySerializer(read_only=True)
    members = UserSummarySerializer(many=True, read_only=True)
    member_ids = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='members',
        many=True,
        write_only=True,
        required=False
    )
    total_tasks_count = serializers.IntegerField(read_only=True)
    completed_tasks_count = serializers.IntegerField(read_only=True)
    in_progress_tasks_count = serializers.IntegerField(read_only=True)
    progress_percentage = serializers.FloatField(read_only=True)

    class Meta:
        model = Project
        fields = [
            'id',
            'name',
            'key',
            'description',
            'status',
            'status_display',
            'priority',
            'priority_display',
            'color',
            'lead',
            'lead_id',
            'created_by',
            'members',
            'member_ids',
            'start_date',
            'target_date',
            'total_tasks_count',
            'completed_tasks_count',
            'in_progress_tasks_count',
            'progress_percentage',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)
