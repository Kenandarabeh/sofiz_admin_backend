from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProjectViewSet,
    TaskViewSet,
    ProjectAnalyticsAPIView,
    TeamMembersAPIView,
    AvailableRolesAPIView,
)

router = DefaultRouter()
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'', ProjectViewSet, basename='project')

urlpatterns = [
    path('analytics/', ProjectAnalyticsAPIView.as_view(), name='projects-analytics'),
    path('team-members/', TeamMembersAPIView.as_view(), name='team-members'),
    path('roles/', AvailableRolesAPIView.as_view(), name='available-roles'),
    path('', include(router.urls)),
]
