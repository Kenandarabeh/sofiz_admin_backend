from django.urls import path
from . import views

app_name = 'monitoring'

urlpatterns = [
    path('api/sync/', views.sync_financials_api, name='api_sync'),
    path('api/status/', views.status_api, name='api_status'),
    path('api/financial/summary/', views.financial_summary_api, name='api_financial_summary'),
    path('api/operations/financial/summary/', views.financial_summary_api, name='api_epay_financial_summary'),
]
