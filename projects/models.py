import re
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class ProjectStatus(models.TextChoices):
    PLANNING = 'PLANNING', 'Planning'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    ON_HOLD = 'ON_HOLD', 'On Hold'
    ARCHIVED = 'ARCHIVED', 'Archived'


class ProjectPriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    MEDIUM = 'MEDIUM', 'Medium'
    HIGH = 'HIGH', 'High'
    URGENT = 'URGENT', 'Urgent'


class TaskStatus(models.TextChoices):
    TODO = 'TODO', 'To Do'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    IN_REVIEW = 'IN_REVIEW', 'In Review'
    DONE = 'DONE', 'Done'


class TaskPriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    MEDIUM = 'MEDIUM', 'Medium'
    HIGH = 'HIGH', 'High'
    URGENT = 'URGENT', 'Urgent'


class Project(models.Model):
    name = models.CharField(max_length=200, help_text='Project name')
    key = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        help_text='Short project key identifier (e.g. SOF, FIN, OPS)'
    )
    description = models.TextField(blank=True, help_text='Project description and objectives')
    status = models.CharField(
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.PLANNING,
        db_index=True
    )
    priority = models.CharField(
        max_length=20,
        choices=ProjectPriority.choices,
        default=ProjectPriority.MEDIUM
    )
    color = models.CharField(max_length=30, default='#3B82F6', help_text='Project theme color (HEX)')
    lead = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='led_projects',
        help_text='Project manager or lead'
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_projects'
    )
    members = models.ManyToManyField(
        User,
        blank=True,
        related_name='assigned_projects',
        help_text='Team members collaborating on the project'
    )
    start_date = models.DateField(null=True, blank=True)
    target_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'

    def __str__(self):
        return f'[{self.key}] {self.name}'

    def clean(self):
        if self.key:
            self.key = re.sub(r'[^A-Z0-9]', '', self.key.upper())

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def total_tasks_count(self) -> int:
        return self.tasks.count()

    @property
    def completed_tasks_count(self) -> int:
        return self.tasks.filter(status=TaskStatus.DONE).count()

    @property
    def in_progress_tasks_count(self) -> int:
        return self.tasks.filter(status=TaskStatus.IN_PROGRESS).count()

    @property
    def progress_percentage(self) -> float:
        total = self.total_tasks_count
        if total == 0:
            return 100.0 if self.status == ProjectStatus.COMPLETED else 0.0
        done = self.completed_tasks_count
        return round((done / total) * 100, 1)


class Task(models.Model):
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='tasks',
        help_text='Associated project (optional for events and meetings)'
    )
    task_key = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        blank=True,
        help_text='Automatic task key (e.g. SOF-1)'
    )
    title = models.CharField(max_length=255, help_text='Task title')
    description = models.TextField(blank=True, help_text='Task details and specifications')
    status = models.CharField(
        max_length=20,
        choices=TaskStatus.choices,
        default=TaskStatus.TODO,
        db_index=True
    )
    priority = models.CharField(
        max_length=20,
        choices=TaskPriority.choices,
        default=TaskPriority.MEDIUM,
        db_index=True
    )
    assignee = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_tasks',
        help_text='Assigned operator/staff'
    )
    reporter = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reported_tasks',
        help_text='Task reporter/creator'
    )
    due_date = models.DateField(null=True, blank=True, help_text='Due date or deadline')
    due_time = models.TimeField(null=True, blank=True, help_text='Time of event or meeting')
    item_type = models.CharField(
        max_length=20,
        default='TASK',
        choices=[
            ('TASK', 'Task'),
            ('EVENT', 'Event'),
            ('MEETING', 'Meeting'),
        ],
        db_index=True,
        help_text='Item category (Task, Event, or Meeting)'
    )
    whatsapp_phone = models.CharField(max_length=40, blank=True, default='', help_text='WhatsApp phone number for reminders')
    whatsapp_sent_at = models.DateTimeField(null=True, blank=True, help_text='Timestamp of sent WhatsApp reminder')
    tags = models.JSONField(default=list, blank=True, help_text='Sub-tags and categories')
    order = models.PositiveIntegerField(default=0, help_text='Task ordering index inside column')
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    logged_hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = 'Task'
        verbose_name_plural = 'Tasks'

    def __str__(self):
        return f'{self.task_key}: {self.title}'

    @property
    def is_overdue(self) -> bool:
        if self.status != TaskStatus.DONE and self.due_date:
            return self.due_date < timezone.localdate()
        return False

    def save(self, *args, **kwargs):
        # Auto-generate task_key if not set
        if not self.task_key:
            if self.project_id and self.project:
                prefix = self.project.key
            elif self.item_type == 'EVENT':
                prefix = 'EVT'
            elif self.item_type == 'MEETING':
                prefix = 'MTG'
            else:
                prefix = 'TSK'

            last_task = Task.objects.filter(task_key__startswith=f'{prefix}-').order_by('-id').first()
            next_num = 1
            if last_task and last_task.task_key:
                try:
                    num_part = int(last_task.task_key.split('-')[-1])
                    next_num = num_part + 1
                except (ValueError, IndexError):
                    next_num = Task.objects.filter(task_key__startswith=f'{prefix}-').count() + 1
            
            candidate = f'{prefix}-{next_num}'
            while Task.objects.filter(task_key=candidate).exists():
                next_num += 1
                candidate = f'{prefix}-{next_num}'
            self.task_key = candidate

        # Handle completion date
        if self.status == TaskStatus.DONE and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status != TaskStatus.DONE and self.completed_at:
            self.completed_at = None

        super().save(*args, **kwargs)


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_comments')
    content = models.TextField(help_text='Comment text content')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Task Comment'
        verbose_name_plural = 'Task Comments'

    def __str__(self):
        return f'Comment by {self.author.username} on {self.task.task_key}'


class TaskActivityLog(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='activity_logs')
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60, help_text='Action type (e.g. STATUS_CHANGE, ASSIGNMENT)')
    details = models.JSONField(default=dict, blank=True, help_text='Activity details payload')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Task Activity Log'
        verbose_name_plural = 'Task Activity Logs'

    def __str__(self):
        return f'[{self.action}] on {self.task.task_key} at {self.created_at}'

