from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

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
from monitoring.models import OperatorMissionRole, OperatorStatus, StaffOperator
from monitoring.services.rbac_service import INSTITUTIONAL_ROLES, RBACService
from .serializers import (
    ProjectSerializer,
    TaskSerializer,
    TaskCommentSerializer,
    TaskActivityLogSerializer,
    UserSummarySerializer,
    CreateStaffMemberSerializer,
)
from .permissions import CanManageProjectPermission, CanManageTaskPermission
from .whatsapp import send_task_whatsapp_reminder_async, send_task_whatsapp_reminder_sync
from .notifications import (
    notify_task_assigned_async,
    notify_task_status_changed_async,
    notify_task_comment_added_async,
)



class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().select_related('lead', 'created_by').prefetch_related('members', 'tasks')
    serializer_class = ProjectSerializer
    permission_classes = [CanManageProjectPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        priority_param = self.request.query_params.get('priority')
        search_param = self.request.query_params.get('search')

        if status_param:
            qs = qs.filter(status=status_param)
        if priority_param:
            qs = qs.filter(priority=priority_param)
        if search_param:
            qs = qs.filter(Q(name__icontains=search_param) | Q(key__icontains=search_param) | Q(description__icontains=search_param))
        return qs

    @action(detail=True, methods=['get'])
    def tasks(self, request, pk=None):
        project = self.get_object()
        tasks = project.tasks.all().select_related('assignee', 'reporter').prefetch_related('comments')
        user = request.user
        can_view_all = (
            user.is_superuser or
            user.groups.filter(name__in=['Super Administrator', 'Full Multi-Family Administrator']).exists() or
            (project.lead_id == user.id) or
            (project.created_by_id == user.id)
        )
        if user and user.is_authenticated and not can_view_all:
            tasks = tasks.filter(Q(assignee=user) | Q(reporter=user))

        status_filter = request.query_params.get('status')
        if status_filter:
            tasks = tasks.filter(status=status_filter)
        serializer = TaskSerializer(tasks, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        project = self.get_object()
        today = timezone.localdate()
        tasks = project.tasks.all()

        total = tasks.count()
        todo = tasks.filter(status=TaskStatus.TODO).count()
        in_progress = tasks.filter(status=TaskStatus.IN_PROGRESS).count()
        in_review = tasks.filter(status=TaskStatus.IN_REVIEW).count()
        done = tasks.filter(status=TaskStatus.DONE).count()
        overdue = tasks.filter(~Q(status=TaskStatus.DONE), due_date__lt=today).count()

        completion_rate = round((done / total * 100), 1) if total > 0 else 0.0

        # Workload for this project
        members_data = []
        project_users = set(list(project.members.all()) + ([project.lead] if project.lead else []))
        for user in project_users:
            u_tasks = tasks.filter(assignee=user)
            members_data.append({
                'user_id': user.id,
                'username': user.username,
                'full_name': f'{user.first_name} {user.last_name}'.strip() or user.username,
                'total_assigned': u_tasks.count(),
                'todo': u_tasks.filter(status=TaskStatus.TODO).count(),
                'in_progress': u_tasks.filter(status=TaskStatus.IN_PROGRESS).count(),
                'in_review': u_tasks.filter(status=TaskStatus.IN_REVIEW).count(),
                'done': u_tasks.filter(status=TaskStatus.DONE).count(),
                'overdue': u_tasks.filter(~Q(status=TaskStatus.DONE), due_date__lt=today).count(),
            })

        return Response({
            'project_id': project.id,
            'project_name': project.name,
            'project_key': project.key,
            'total_tasks': total,
            'todo_tasks': todo,
            'in_progress_tasks': in_progress,
            'in_review_tasks': in_review,
            'done_tasks': done,
            'overdue_tasks': overdue,
            'completion_rate': completion_rate,
            'members_workload': members_data,
        })


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all().select_related('project', 'assignee', 'reporter').prefetch_related('comments')
    serializer_class = TaskSerializer
    permission_classes = [CanManageTaskPermission]

    def perform_create(self, serializer):
        reporter = self.request.user if (self.request.user and self.request.user.is_authenticated) else None
        task = serializer.save(reporter=reporter)
        TaskActivityLog.objects.create(
            task=task,
            user=reporter,
            action='CREATED',
            details={'title': task.title, 'assignee': task.assignee.username if task.assignee else None}
        )
        if task.assignee and task.assignee.email:
            notify_task_assigned_async(task, assigned_by=reporter)

        # Auto-fill whatsapp_phone from assignee operator_profile if not set
        if not task.whatsapp_phone and task.assignee:
            profile = getattr(task.assignee, 'operator_profile', None)
            if profile and profile.phone_number:
                task.whatsapp_phone = profile.phone_number
                task.save(update_fields=['whatsapp_phone'])

        # Auto-send WhatsApp reminder for events/meetings or when phone exists
        send_wa = self.request.data.get('send_whatsapp', True)
        if task.whatsapp_phone and send_wa:
            send_task_whatsapp_reminder_async(task)

    def perform_update(self, serializer):
        old_task = self.get_object()
        old_assignee = old_task.assignee
        old_status = old_task.status

        task = serializer.save()
        user = self.request.user if (self.request.user and self.request.user.is_authenticated) else None

        if task.assignee and (not old_assignee or old_assignee.id != task.assignee.id):
            TaskActivityLog.objects.create(
                task=task,
                user=user,
                action='ASSIGNEE_CHANGED',
                details={
                    'from': old_assignee.username if old_assignee else None,
                    'to': task.assignee.username
                }
            )
            notify_task_assigned_async(task, assigned_by=user)

        if task.status != old_status:
            TaskActivityLog.objects.create(
                task=task,
                user=user,
                action='STATUS_CHANGED',
                details={'from': old_status, 'to': task.status}
            )
            notify_task_status_changed_async(task, old_status=old_status, new_status=task.status, changed_by=user)

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # Normal users can only see tasks assigned to them or reported by them
        can_view_all = False
        if user and user.is_authenticated:
            if user.is_superuser:
                can_view_all = True
            elif user.groups.filter(name__in=['Super Administrator', 'Full Multi-Family Administrator']).exists():
                can_view_all = True
            elif user.has_perm('projects.view_all_tasks'):
                can_view_all = True

        if user and user.is_authenticated and not can_view_all:
            qs = qs.filter(Q(assignee=user) | Q(reporter=user))

        project_param = self.request.query_params.get('project')
        status_param = self.request.query_params.get('status')
        priority_param = self.request.query_params.get('priority')
        assignee_param = self.request.query_params.get('assignee')
        overdue_param = self.request.query_params.get('is_overdue')
        search_param = self.request.query_params.get('search')

        if project_param:
            if project_param.isdigit():
                qs = qs.filter(project_id=project_param)
            else:
                qs = qs.filter(project__key__iexact=project_param)

        if status_param:
            qs = qs.filter(status=status_param)
        if priority_param:
            qs = qs.filter(priority=priority_param)
        if assignee_param:
            if assignee_param == 'unassigned':
                qs = qs.filter(assignee__isnull=True)
            elif assignee_param.isdigit():
                qs = qs.filter(assignee_id=assignee_param)
            else:
                qs = qs.filter(assignee__username=assignee_param)

        if overdue_param == 'true':
            qs = qs.filter(~Q(status=TaskStatus.DONE), due_date__lt=timezone.localdate())

        if search_param:
            qs = qs.filter(
                Q(title__icontains=search_param) |
                Q(task_key__icontains=search_param) |
                Q(description__icontains=search_param)
            )

        return qs

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        task = self.get_object()
        new_status = request.data.get('status')
        new_order = request.data.get('order')

        if not new_status or new_status not in TaskStatus.values:
            return Response(
                {'error': f'Valid status required. Choices: {TaskStatus.values}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = task.status
        task.status = new_status
        if new_order is not None:
            try:
                task.order = int(new_order)
            except (ValueError, TypeError):
                pass

        task.save()

        user = request.user if request.user.is_authenticated else None
        TaskActivityLog.objects.create(
            task=task,
            user=user,
            action='STATUS_CHANGED',
            details={'from': old_status, 'to': new_status}
        )

        if old_status != new_status:
            notify_task_status_changed_async(task, old_status=old_status, new_status=new_status, changed_by=user)

        serializer = self.get_serializer(task)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def assign(self, request, pk=None):
        task = self.get_object()
        assignee_id = request.data.get('assignee_id')

        old_assignee = task.assignee
        if assignee_id is None or assignee_id == '':
            task.assignee = None
        else:
            try:
                task.assignee = User.objects.get(id=assignee_id)
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        task.save(update_fields=['assignee'])

        user = request.user if request.user.is_authenticated else None
        TaskActivityLog.objects.create(
            task=task,
            user=user,
            action='ASSIGNEE_CHANGED',
            details={
                'from': old_assignee.username if old_assignee else None,
                'to': task.assignee.username if task.assignee else None
            }
        )

        if task.assignee and (not old_assignee or old_assignee.id != task.assignee.id):
            notify_task_assigned_async(task, assigned_by=user)

        serializer = self.get_serializer(task)
        return Response(serializer.data)

    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        task = self.get_object()
        if request.method == 'GET':
            comments = task.comments.all().select_related('author')
            serializer = TaskCommentSerializer(comments, many=True)
            return Response(serializer.data)

        content = request.data.get('content', '').strip()
        if not content:
            return Response({'error': 'Comment content cannot be empty'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = TaskCommentSerializer(data={'task': task.id, 'content': content}, context={'request': request})
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()
        author = request.user if request.user.is_authenticated else None
        notify_task_comment_added_async(task, comment=comment, author=author)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def send_whatsapp(self, request, pk=None):
        task = self.get_object()
        phone = request.data.get('phone') or task.whatsapp_phone
        if not phone and task.assignee:
            profile = getattr(task.assignee, 'operator_profile', None)
            phone = profile.phone_number if profile else ''

        if not phone:
            return Response({'error': 'لم يتم العثور على رقم هاتف واتساب للتذكير'}, status=status.HTTP_400_BAD_REQUEST)

        custom_message = request.data.get('message')
        result = send_task_whatsapp_reminder_sync(task, target_phone=phone, custom_message=custom_message, user=request.user)
        if result.get('success'):
            return Response(result)
        return Response(result, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def activities(self, request, pk=None):
        task = self.get_object()
        logs = task.activity_logs.all().select_related('user')
        serializer = TaskActivityLogSerializer(logs, many=True)
        return Response(serializer.data)


class ProjectAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        user = request.user
        can_view_all = False
        if user and user.is_authenticated:
            if user.is_superuser or user.groups.filter(name__in=['Super Administrator', 'Full Multi-Family Administrator']).exists():
                can_view_all = True

        projects = Project.objects.all()
        tasks = Task.objects.all()

        if user and user.is_authenticated and not can_view_all:
            tasks = tasks.filter(Q(assignee=user) | Q(reporter=user))
            projects = projects.filter(Q(members=user) | Q(lead=user) | Q(created_by=user) | Q(tasks__assignee=user)).distinct()

        total_projects = projects.count()
        active_projects = projects.filter(status__in=[ProjectStatus.PLANNING, ProjectStatus.IN_PROGRESS]).count()
        completed_projects = projects.filter(status=ProjectStatus.COMPLETED).count()

        total_tasks = tasks.count()
        done_tasks = tasks.filter(status=TaskStatus.DONE).count()
        in_progress_tasks = tasks.filter(status=TaskStatus.IN_PROGRESS).count()
        in_review_tasks = tasks.filter(status=TaskStatus.IN_REVIEW).count()
        todo_tasks = tasks.filter(status=TaskStatus.TODO).count()
        overdue_tasks = tasks.filter(~Q(status=TaskStatus.DONE), due_date__lt=today).count()

        completion_rate = round((done_tasks / total_tasks * 100), 1) if total_tasks > 0 else 0.0

        # Priority breakdown
        priority_breakdown = {
            'URGENT': tasks.filter(priority=TaskPriority.URGENT).count(),
            'HIGH': tasks.filter(priority=TaskPriority.HIGH).count(),
            'MEDIUM': tasks.filter(priority=TaskPriority.MEDIUM).count(),
            'LOW': tasks.filter(priority=TaskPriority.LOW).count(),
        }

        # Status breakdown
        status_breakdown = {
            'TODO': todo_tasks,
            'IN_PROGRESS': in_progress_tasks,
            'IN_REVIEW': in_review_tasks,
            'DONE': done_tasks,
        }

        # Team Workload Analytics
        team_members = User.objects.filter(is_active=True).order_by('username')
        team_workload = []
        for user in team_members:
            u_tasks = tasks.filter(assignee=user)
            u_total = u_tasks.count()
            u_done = u_tasks.filter(status=TaskStatus.DONE).count()
            u_in_progress = u_tasks.filter(status=TaskStatus.IN_PROGRESS).count()
            u_todo = u_tasks.filter(status=TaskStatus.TODO).count()
            u_in_review = u_tasks.filter(status=TaskStatus.IN_REVIEW).count()
            u_overdue = u_tasks.filter(~Q(status=TaskStatus.DONE), due_date__lt=today).count()

            # We include users who have assigned tasks or are staff
            if u_total > 0 or user.is_staff:
                team_workload.append({
                    'user_id': user.id,
                    'username': user.username,
                    'full_name': f'{user.first_name} {user.last_name}'.strip() or user.username,
                    'total_assigned': u_total,
                    'todo': u_todo,
                    'in_progress': u_in_progress,
                    'in_review': u_in_review,
                    'done': u_done,
                    'overdue': u_overdue,
                    'completion_rate': round((u_done / u_total * 100), 1) if u_total > 0 else 0.0,
                })

        # Recent activities
        recent_logs = TaskActivityLog.objects.select_related('task', 'user', 'task__project').order_by('-created_at')[:12]
        recent_activities = []
        for log in recent_logs:
            recent_activities.append({
                'id': log.id,
                'task_key': log.task.task_key,
                'task_title': log.task.title,
                'project_key': log.task.project.key if (log.task and log.task.project) else 'GEN',
                'user': log.user.username if log.user else 'System',
                'action': log.action,
                'details': log.details,
                'created_at': log.created_at,
            })

        return Response({
            'total_projects': total_projects,
            'active_projects': active_projects,
            'completed_projects': completed_projects,
            'total_tasks': total_tasks,
            'done_tasks': done_tasks,
            'in_progress_tasks': in_progress_tasks,
            'in_review_tasks': in_review_tasks,
            'todo_tasks': todo_tasks,
            'overdue_tasks': overdue_tasks,
            'completion_rate': completion_rate,
            'priority_breakdown': priority_breakdown,
            'status_breakdown': status_breakdown,
            'team_workload': team_workload,
            'recent_activities': recent_activities,
        })


class TeamMembersAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        users = User.objects.filter(is_active=True).select_related('operator_profile').prefetch_related('groups').order_by('username')
        serializer = UserSummarySerializer(users, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {'error': 'عذراً، يجب أن تمتلك صلاحيات إدارية (Admin) لإنشاء موظفين جدد.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CreateStaffMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        full_name = data['full_name'].strip()
        name_parts = full_name.split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        user = User.objects.create_user(
            username=data['username'].strip(),
            email=data['email'].strip().lower(),
            password=data['password'],
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
            is_active=True
        )

        mission_roles = data.get('mission_roles') or []
        if not mission_roles:
            single = data.get('mission_role', 'GAME_OPERATOR')
            mission_roles = [single] if single else ['GAME_OPERATOR']
        elif isinstance(mission_roles, str):
            mission_roles = [r.strip() for r in mission_roles.split(',') if r.strip()]

        assigned_groups = RBACService.assign_multiple_mission_roles(user, mission_roles)
        primary_role = mission_roles[0] if mission_roles else 'GAME_OPERATOR'

        staff = StaffOperator.objects.create(
            full_name=full_name,
            username=user.username,
            email=user.email,
            mission_role=primary_role,
            status=OperatorStatus.ACTIVE,
            phone_number=data.get('phone_number', ''),
            notes=data.get('notes', ''),
            linked_user=user,
            is_active=True
        )

        return Response(
            {
                'success': True,
                'message': f'تم إنشاء الموظف {full_name} بنجاح وتعيين الصلاحيات.',
                'user': UserSummarySerializer(user).data,
                'employee_code': staff.employee_code,
                'assigned_groups': assigned_groups,
            },
            status=status.HTTP_201_CREATED
        )


class AvailableRolesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        roles_data = []
        for code, label in OperatorMissionRole.choices:
            group_name = RBACService.ROLE_MAPPING.get(code, 'Compliance & Financial Auditor')
            role_info = INSTITUTIONAL_ROLES.get(group_name, {})
            roles_data.append({
                'code': code,
                'label': label,
                'group_name': group_name,
                'description': role_info.get('description', ''),
                'color': role_info.get('color', '#3B82F6'),
                'is_super': role_info.get('is_super', False),
            })
        return Response(roles_data)
