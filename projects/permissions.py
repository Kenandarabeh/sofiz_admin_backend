from rest_framework import permissions


class IsStaffOrSuperUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and (request.user.is_staff or request.user.is_superuser))


class CanManageProjectPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if user.is_staff or user.is_superuser:
            return True
        return obj.created_by_id == user.id or obj.lead_id == user.id


class CanManageTaskPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if user.is_staff or user.is_superuser:
            return True
        if request.method == 'DELETE':
            return (
                obj.reporter_id == user.id or
                (obj.project and obj.project.lead_id == user.id) or
                (obj.project and obj.project.created_by_id == user.id)
            )
        return True
