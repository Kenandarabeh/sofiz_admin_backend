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
    BaridiMobTransactionViewSet,
    ExpenseRecordViewSet,
    GameProfitRecordViewSet,
    UtilityBillRecordViewSet,
    CapitalEntryViewSet,
    WithdrawalRecordViewSet,
    BalanceAuditLogViewSet,
    GlobalSettingsAPIView,
    MasterDataModeToggleAPIView,
    GamingMonitoringAPIView,
    UtilityMonitoringAPIView,
    SihaamUtilityAccountSyncAPIView,
    SalahGamingAccountAPIView,
    SalahGamingAccountSyncAPIView,
    eSIMMonitoringAPIView,
    eSIMSyncBybitAPIView,
    eSIMSyncAiraloAPIView,
    BybitAccountViewSet,
    AiraloAccountViewSet,
    eSIMFundingRecordViewSet,
    eSIMOrderRecordViewSet,
    ECCPBalanceSyncAPIView,
    MasterLiquiditySummaryAPIView,
    UnifiedAccountsMonitoringAPIView,
    G2BulkReplenishmentWindowViewSet,
    DailyOperationsProfitsAPIView,
    IdoomMonitoringAPIView,
    IdoomWithdrawalsRefillAPIView,
    IdoomRefundRollbackAPIView,
    IPTVMonitoringAPIView,
    IPTVWithdrawalsRefillAPIView,
    IPTVRefundRollbackAPIView,
    FlexyOperationsMonitoringAPIView,
    FlexyWithdrawalsRefillAPIView,
    XLMLiquidityStatusAPIView,
    XLMCycleStageAdvanceAPIView,
    XLMCycleVerifyOnChainAPIView,
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
router.register(r'baridimob-transactions', BaridiMobTransactionViewSet, basename='baridimob-transactions')
router.register(r'expenses', ExpenseRecordViewSet, basename='expenses')
router.register(r'game-profits', GameProfitRecordViewSet, basename='game-profits')
router.register(r'utility-bills', UtilityBillRecordViewSet, basename='utility-bills')
router.register(r'capital-entries', CapitalEntryViewSet, basename='capital-entries')
router.register(r'withdrawals', WithdrawalRecordViewSet, basename='withdrawals')
router.register(r'audit-logs', BalanceAuditLogViewSet, basename='audit-logs')
router.register(r'bybit-accounts', BybitAccountViewSet, basename='bybit-accounts')
router.register(r'airalo-accounts', AiraloAccountViewSet, basename='airalo-accounts')
router.register(r'esim-fundings', eSIMFundingRecordViewSet, basename='esim-fundings')
router.register(r'esim-orders', eSIMOrderRecordViewSet, basename='esim-orders')
router.register(r'g2bulk-replenishment-windows', G2BulkReplenishmentWindowViewSet, basename='g2bulk-replenishment-windows')

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
    path('monitoring/utility/sihaam-account/sync/', SihaamUtilityAccountSyncAPIView.as_view(), name='api-sihaam-utility-account-sync'),
    path('monitoring/eccp/sync/', ECCPBalanceSyncAPIView.as_view(), name='api-eccp-sync'),
    path('monitoring/master-liquidity-summary/', MasterLiquiditySummaryAPIView.as_view(), name='api-master-liquidity-summary'),
    path('monitoring/unified-accounts/', UnifiedAccountsMonitoringAPIView.as_view(), name='api-unified-accounts-monitoring'),
    path('monitoring/daily-operations-profits/', DailyOperationsProfitsAPIView.as_view(), name='api-daily-operations-profits'),

    # Dedicated eSIM Monitoring & Live Sync
    path('monitoring/esim/', eSIMMonitoringAPIView.as_view(), name='api-esim-monitoring'),
    path('monitoring/esim/sync-bybit/', eSIMSyncBybitAPIView.as_view(), name='api-esim-sync-bybit'),
    path('monitoring/esim/sync-airalo/', eSIMSyncAiraloAPIView.as_view(), name='api-esim-sync-airalo'),

    # Dedicated Idoom (Algérie Télécom) Monitoring, Refill & Refund
    path('monitoring/idoom/', IdoomMonitoringAPIView.as_view(), name='api-idoom-monitoring'),
    path('idoom/refill/', IdoomWithdrawalsRefillAPIView.as_view(), name='api-idoom-refill'),
    path('idoom/refund/', IdoomRefundRollbackAPIView.as_view(), name='api-idoom-refund'),

    # Dedicated IPTV (Subscriptions & Vouchers) Monitoring, Refill & Refund
    path('monitoring/iptv/', IPTVMonitoringAPIView.as_view(), name='api-iptv-monitoring'),
    path('iptv/refill/', IPTVWithdrawalsRefillAPIView.as_view(), name='api-iptv-refill'),
    path('iptv/refund/', IPTVRefundRollbackAPIView.as_view(), name='api-iptv-refund'),

    # Dedicated Flexy (Mobilis, Djezzy, Ooredoo) Monitoring & Refill/Sweep
    path('monitoring/flexy/', FlexyOperationsMonitoringAPIView.as_view(), name='api-flexy-monitoring'),
    path('flexy/refill/', FlexyWithdrawalsRefillAPIView.as_view(), name='api-flexy-refill'),

    # Dedicated XLM Liquidity Procurement & On-Chain Horizon Verification
    path('xlm/status/', XLMLiquidityStatusAPIView.as_view(), name='api-xlm-status'),
    path('xlm/advance-stage/', XLMCycleStageAdvanceAPIView.as_view(), name='api-xlm-advance-stage'),
    path('xlm/verify-on-chain/', XLMCycleVerifyOnChainAPIView.as_view(), name='api-xlm-verify-on-chain'),

    # Binance Live Integration
    path('binance/<str:action_name>/', BinanceLiveAPIView.as_view(), name='api-binance-live'),

    # Global Settings & Master Data Source Mode (REAL vs MOCK)
    path('settings/', GlobalSettingsAPIView.as_view(), name='api-settings'),
    path('monitoring/data-mode/', MasterDataModeToggleAPIView.as_view(), name='api-data-mode'),
    path('monitoring/toggle-data-mode/', MasterDataModeToggleAPIView.as_view(), name='api-toggle-data-mode'),

    # Router endpoints
    path('', include(router.urls)),
]
