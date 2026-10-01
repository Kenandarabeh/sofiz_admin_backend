from django.contrib import admin
from .models import Project, Task, TaskComment, TaskActivityLog


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    fields = ['task_key', 'title', 'status', 'priority', 'assignee', 'due_date']
    readonly_fields = ['task_key']
    show_change_link = True


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['key', 'name', 'status', 'priority', 'lead', 'total_tasks_count', 'progress_percentage', 'created_at']
    list_filter = ['status', 'priority', 'created_at']
    search_fields = ['name', 'key', 'description']
    inlines = [TaskInline]
    filter_horizontal = ['members']


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    extra = 0
    readonly_fields = ['author', 'created_at']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['task_key', 'title', 'project', 'status', 'priority', 'assignee', 'due_date', 'created_at']
    list_filter = ['status', 'priority', 'project', 'due_date', 'created_at']
    search_fields = ['task_key', 'title', 'description']
    readonly_fields = ['task_key', 'completed_at', 'created_at', 'updated_at']
    inlines = [TaskCommentInline]


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ['task', 'author', 'created_at']
    search_fields = ['content', 'task__task_key', 'author__username']


@admin.register(TaskActivityLog)
class TaskActivityLogAdmin(admin.ModelAdmin):
    list_display = ['task', 'action', 'user', 'created_at']
    list_filter = ['action', 'created_at']
    readonly_fields = ['task', 'user', 'action', 'details', 'created_at']
