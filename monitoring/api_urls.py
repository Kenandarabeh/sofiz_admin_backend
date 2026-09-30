"""
REST API URL Routing for SofizAdmin Monitoring Backend
Designed for the React + Vite frontend single-page application.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    DashboardOverviewAPIView,
    StellarWalletViewSet,
    WalletSweepLogViewSet,
    FundingCycleViewSet,
    BinanceLiveAPIView,
    SupplierAccountViewSet,
    BaridiMobAccountViewSet,
    ExpenseRecordViewSet,
    GameProfitRecordViewSet,
    UtilityBillRecordViewSet,
    CapitalEntryViewSet,
    WithdrawalRecordViewSet,
    BalanceAuditLogViewSet,
    GlobalSettingsAPIView,
    GamingMonitoringAPIView,
    UtilityMonitoringAPIView,
    SalahGamingAccountAPIView,
    SalahGamingAccountSyncAPIView,
)
from .auth_views import (
    LoginAPIView,
    CustomTokenRefreshView,
    UserProfileAPIView,
    LogoutAPIView,
    ChangePasswordAPIView,
    LoginAuditLogListView,
)

router = DefaultRouter()
router.register(r'wallets', StellarWalletViewSet, basename='stellar-wallets')
router.register(r'sweeps', WalletSweepLogViewSet, basename='wallet-sweeps')
router.register(r'funding-cycles', FundingCycleViewSet, basename='funding-cycles')
router.register(r'suppliers', SupplierAccountViewSet, basename='suppliers')
router.register(r'baridimob-accounts', BaridiMobAccountViewSet, basename='baridimob-accounts')
router.register(r'expenses', ExpenseRecordViewSet, basename='expenses')
router.register(r'game-profits', GameProfitRecordViewSet, basename='game-profits')
router.register(r'utility-bills', UtilityBillRecordViewSet, basename='utility-bills')
router.register(r'capital-entries', CapitalEntryViewSet, basename='capital-entries')
router.register(r'withdrawals', WithdrawalRecordViewSet, basename='withdrawals')
router.register(r'audit-logs', BalanceAuditLogViewSet, basename='audit-logs')

urlpatterns = [
    # Institutional Authentication & Profile Suite
    path('auth/login/', LoginAPIView.as_view(), name='api-auth-login'),
    path('auth/refresh/', CustomTokenRefreshView.as_view(), name='api-auth-refresh'),
    path('auth/me/', UserProfileAPIView.as_view(), name='api-auth-me'),
    path('auth/logout/', LogoutAPIView.as_view(), name='api-auth-logout'),
    path('auth/change-password/', ChangePasswordAPIView.as_view(), name='api-auth-change-password'),
    path('auth/audit-logs/', LoginAuditLogListView.as_view(), name='api-auth-audit-logs'),

    # Dashboard Analytics
    path('dashboard/overview/', DashboardOverviewAPIView.as_view(), name='api-dashboard-overview'),
    path('monitoring/gaming/', GamingMonitoringAPIView.as_view(), name='api-gaming-monitoring'),
    path('monitoring/gaming/salah-account/', SalahGamingAccountAPIView.as_view(), name='api-salah-gaming-account'),
    path('monitoring/gaming/salah-account/sync/', SalahGamingAccountSyncAPIView.as_view(), name='api-salah-gaming-account-sync'),
    path('monitoring/utility/', UtilityMonitoringAPIView.as_view(), name='api-utility-monitoring'),

    # Binance Live Integration
    path('binance/<str:action_name>/', BinanceLiveAPIView.as_view(), name='api-binance-live'),

    # Global Settings
    path('settings/', GlobalSettingsAPIView.as_view(), name='api-settings'),

    # Router endpoints
    path('', include(router.urls)),
]
