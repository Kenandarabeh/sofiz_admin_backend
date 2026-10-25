"""
SofizPay Institutional Systems Administration Console.
Organized into 8 dedicated, family-partitioned operations hubs:
1. 🔑 API KEYS & CREDENTIALS VAULT
2. 🔐 STELLAR WALLETS & SECRET KEYS (SK)
3. 💰 ACCOUNT WORKING CAPITALS (BY FAMILY)
4. 🎮 GAME OPERATIONS & MONITORING (Free Fire, PUBG, G2Bulk)
5. 📄 FACTURE OPERATIONS & SETTLEMENT (Sonelgaz, ADE, AT, Sihaam 31)
6. 📶 ESIM OPERATIONS & MONITORING (Telecom & Data)
7. 🏛️ CENTRAL TREASURY, BINANCE & SOLIDARITY AUDIT
8. 🛡️ ACCESS CONTROL & AUDIT LOGS

Strictly complies with Institutional Fintech Standards (100% English).
"""
import logging
from decimal import Decimal
from django import forms
from django.db import models
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    MonitoringGlobalSettings,
    AccountWorkingCapital,
    OperationalFamily,
    StellarWallet,
    WalletFamily,
    WalletRole,
    WalletSweepLog,
    SupplierAccount,
    SupplierProvider,
    BaridiMobAccount,
    BaridiMobTransaction,
    GamingBaridiMobAccount,
    UtilityBaridiMobAccount,
    eSIMBaridiMobAccount,
    SubSystemType,
    BinanceAccount,
    WithdrawalRecord,
    WithdrawalStage,
    WithdrawalPurpose,
    CapitalEntry,
    ExpenseRecord,
    BaridiMobFundingReceipt,
    BalanceAuditLog,
    LoginAuditLog,
    GamingFinancialStatus,
    UtilityFinancialStatus,
    eSIMFinancialStatus,
    GamingWithdrawalRecord,
    UtilityWithdrawalRecord,
    eSIMWithdrawalRecord,
    BinanceP2POperation,
    GamingCapitalEntry,
    UtilityCapitalEntry,
    eSIMCapitalEntry,
    GameProfitRecord,
    UtilityBillRecord,
    StaffOperator,
    OperatorMissionRole,
    OperatorStatus,
    OperatorActionLog,
    G2BulkReplenishmentWindow,
    ReplenishmentWindowStatus,
    BybitAccount,
    AiraloAccount,
    IdoomBatchRefill,
    IdoomRefundRecord,
)
from .services.audit_service import AuditService
from .services.balance_engine import BalanceEngine
from .services.baridimob_service import BaridiMobService
from .services.binance_service import BinanceVerificationService, BinanceApiService
from .services.g2bulk_service import G2BulkService
from .services.rbac_service import RBACService, INSTITUTIONAL_ROLES
from .services.receipt_parser_service import ReceiptParserService
from .services.stellar_service import StellarService

logger = logging.getLogger(__name__)
User = get_user_model()


# ==============================================================================
#  🏛️ CLEAN 8-TIER APP PARTITIONING FOR DJANGO ADMIN SIDEBAR
# ==============================================================================
original_get_app_list = admin.AdminSite.get_app_list


def custom_get_app_list(self, request, app_label=None):
    """
    Partitions Django Admin models into clear, logical, family-partitioned hubs:
    1. 🔑 API KEYS & CREDENTIALS VAULT
    2. 🔐 STELLAR WALLETS & SECRET KEYS (SK)
    3. 💰 ACCOUNT WORKING CAPITALS (BY FAMILY)
    4. 🎮 GAME OPERATIONS & MONITORING (Free Fire, PUBG, G2Bulk)
    5. 📄 FACTURE OPERATIONS & SETTLEMENT (Sonelgaz, ADE, AT, Sihaam 31)
    6. 📶 ESIM OPERATIONS & MONITORING (Telecom & Data)
    7. 🏛️ CENTRAL TREASURY, BINANCE & SOLIDARITY AUDIT
    8. 🛡️ ACCESS CONTROL & AUDIT LOGS
    """
    app_list = original_get_app_list(self, request, app_label)
    auth_app = None
    monitoring_models = {}

    monitoring_app_url = '/admin/monitoring/'
    for app in app_list:
        if app['app_label'] == 'auth':
            auth_app = app
        elif app['app_label'] == 'monitoring':
            monitoring_app_url = app.get('app_url', monitoring_app_url)
            for model in app['models']:
                object_name = model['object_name'].lower()
                monitoring_models[object_name] = model

    if not monitoring_models:
        return app_list

    def get_models(names):
        return [monitoring_models[m] for m in names if m in monitoring_models]

    # 1. 🔑 API Keys & Gateway Credentials
    api_app = {
        'name': '🔑 API KEYS & CREDENTIALS VAULT',
        'app_label': 'api_vault',
        'app_url': monitoring_app_url,
        'has_module_perms': True,
        'models': get_models(['monitoringglobalsettings']),
    }

    # 2. 🔐 All Wallets & Secret Keys (SK) in ONE place
    wallets_app = {
        'name': '🔐 STELLAR WALLETS & SECRET KEYS (SK)',
        'app_label': 'stellar_wallets',
        'app_url': monitoring_app_url,
        'has_module_perms': True,
        'models': get_models(['stellarwallet']),
    }

    # 3. 💰 All Capitals for Each Family in ONE place
    capitals_app = {
        'name': '💰 ACCOUNT WORKING CAPITALS (BY FAMILY)',
        'app_label': 'account_capitals',
        'app_url': monitoring_app_url,
        'has_module_perms': True,
        'models': get_models(['accountworkingcapital']),
    }

    # 4. 🎮 GAME OPERATIONS & MONITORING (Gaming & Top-Ups)
    game_app = {
        'name': '🎮 GAME OPERATIONS & MONITORING (Free Fire, PUBG, G2Bulk)',
        'app_label': 'game_operations',
        'app_url': monitoring_app_url,
        'has_module_perms': True,
        'models': get_models([
            'gamingfinancialstatus',
            'gamingbaridimobaccount',
            'supplieraccount',
            'gamingwithdrawalrecord',
            'gamingcapitalentry',
            'gameprofitrecord',
        ]),
    }

    # 5. 📄 FACTURE OPERATIONS & SETTLEMENT (Sonelgaz, ADE, AT, Sihaam 31)
    facture_app = {
        'name': '📄 FACTURE OPERATIONS & SETTLEMENT (Sonelgaz, ADE, AT, Sihaam 31)',
        'app_label': 'facture_operations',
        'app_url': monitoring_app_url,
        'has_module_perms': True,
        'models': get_models([
            'utilityfinancialstatus',
            'utilitybaridimobaccount',
            'baridimobfundingreceipt',
            'utilitywithdrawalrecord',
            'utilitycapitalentry',
            'utilitybillrecord',
        ]),
    }

    # 6. 📶 ESIM OPERATIONS & MONITORING (Telecom & Data)
    esim_app = {
        'name': '📶 ESIM OPERATIONS & MONITORING (Telecom & Data)',
        'app_label': 'esim_operations',
        'app_url': monitoring_app_url,
        'has_module_perms': True,
        'models': get_models([
            'esimfinancialstatus',
            'esimbaridimobaccount',
            'bybitaccount',
            'airaloaccount',
            'esimwithdrawalrecord',
            'esimcapitalentry',
        ]),
    }

    # 7. 🏛️ CENTRAL TREASURY, BINANCE & SOLIDARITY AUDIT
    treasury_app = {
        'name': '🏛️ CENTRAL TREASURY, BINANCE & SOLIDARITY AUDIT',
        'app_label': 'treasury_operations',
        'app_url': monitoring_app_url,
        'has_module_perms': True,
        'models': get_models([
            'balanceauditlog',
            'binanceaccount',
            'binancep2poperation',
            'baridimobaccount',
            'walletsweeplog',
            'expenserecord',
            'withdrawalrecord',
            'capitalentry',
        ]),
    }

    # 8. 👥 EMPLOYEES & OPERATORS (BY ROLE & PERMISSION)
    staff_app = {
        'name': '👥 EMPLOYEES & OPERATORS (BY ROLE & PERMISSION)',
        'app_label': 'staff_management',
        'app_url': monitoring_app_url,
        'has_module_perms': True,
        'models': get_models(['staffoperator', 'operatoractionlog']),
    }

    # 9. 🛡️ Access Control & Audit Logs
    auth_models = auth_app['models'] if auth_app else []
    security_models = get_models(['loginauditlog', 'operatoractionlog'])
    auth_app_url = auth_app.get('app_url', monitoring_app_url) if auth_app else monitoring_app_url
    rbac_app = {
        'name': '🛡️ ACCESS CONTROL & AUDIT LOGS',
        'app_label': 'rbac_access',
        'app_url': auth_app_url,
        'has_module_perms': True,
        'models': auth_models + security_models,
    }

    partitioned_list = []
    for section in [api_app, wallets_app, capitals_app, game_app, facture_app, esim_app, treasury_app, staff_app]:
        if section['models']:
            partitioned_list.append(section)
    if rbac_app['models']:
        partitioned_list.append(rbac_app)

    return partitioned_list


admin.AdminSite.get_app_list = custom_get_app_list


# ==============================================================================
#  🛡️ INSTITUTIONAL AUDIT TRAIL MIXIN (AUTOMATIC TRACKING FOR ALL MODELS)
# ==============================================================================
class InstitutionalAuditAdminMixin:
    """
    Automatic Institutional Audit Trail Mixin.
    Intercepts and logs every object creation, modification, and deletion executed
    by staff operators, storing exact field diffs, IP addresses, and timestamps.
    """
    def save_model(self, request, obj, form, change):
        diff = AuditService.diff_model_changes(form, obj) if change else "New object created."
        super().save_model(request, obj, form, change)
        AuditService.log_action(
            operator=request.user,
            action_type=OperatorActionLog.ActionType.UPDATE if change else OperatorActionLog.ActionType.CREATE,
            target_model=obj._meta.verbose_name,
            object_id=getattr(obj, 'pk', None),
            object_repr=str(obj),
            changes_summary=f"Changed fields:\n{diff}" if change else f"Initial attributes:\n{diff}",
            request=request
        )

    def delete_model(self, request, obj):
        AuditService.log_action(
            operator=request.user,
            action_type=OperatorActionLog.ActionType.DELETE,
            target_model=obj._meta.verbose_name,
            object_id=getattr(obj, 'pk', None),
            object_repr=str(obj),
            changes_summary=f"Deleted object: {str(obj)}",
            request=request
        )
        super().delete_model(request, obj)


# ==============================================================================
#  🔑 1. API KEYS & CREDENTIALS VAULT (ZERO HTML)
# ==============================================================================
class MonitoringGlobalSettingsForm(forms.ModelForm):
    bybit_api_key = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'style': 'font-family: monospace; width: 450px;', 'placeholder': 'Bybit V5 API Key'}),
        required=False,
        label="Bybit API Key"
    )
    bybit_api_secret = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'style': 'font-family: monospace; width: 450px;', 'placeholder': 'Bybit V5 API Secret'}),
        required=False,
        label="Bybit API Secret"
    )
    airalo_client_id = forms.CharField(
        widget=forms.TextInput(attrs={'style': 'font-family: monospace; width: 450px;', 'placeholder': 'Airalo Client ID'}),
        required=False,
        label="Airalo Client ID"
    )
    airalo_client_secret = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'style': 'font-family: monospace; width: 450px;', 'placeholder': 'Airalo Client Secret'}),
        required=False,
        label="Airalo Client Secret"
    )
    epay_api_key = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'style': 'font-family: monospace; width: 450px;'}),
        required=False,
        label="Epay API Key"
    )
    binance_api_key = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'style': 'font-family: monospace; width: 450px;'}),
        required=False,
        label="Binance API Key"
    )
    binance_api_secret = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'style': 'font-family: monospace; width: 450px;'}),
        required=False,
        label="Binance API Secret"
    )
    g2bulk_api_key = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'style': 'font-family: monospace; width: 450px;'}),
        required=False,
        label="G2Bulk API Key"
    )
    baridimob_secret_token = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'style': 'font-family: monospace; width: 450px;'}),
        required=False,
        label="BaridiMob Bearer Secret Token"
    )
    master_admin_api_key = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'style': 'font-family: monospace; width: 450px;'}),
        required=False,
        label="Master Admin Secret Key"
    )

    class Meta:
        model = MonitoringGlobalSettings
        fields = '__all__'


@admin.register(MonitoringGlobalSettings)
class MonitoringGlobalSettingsAdmin(admin.ModelAdmin):
    form = MonitoringGlobalSettingsForm
    list_display = (
        '__str__',
        'mode_badge',
        'epay_exchange_rate_display',
        'total_live_profits_dzd',
        'is_auto_sync_enabled',
        'last_global_sync',
    )
    readonly_fields = ('last_global_sync', 'mode_quick_toggle_panel')
    fieldsets = (
        ('🚨 Master Operational Mode: REAL vs MOCK', {
            'fields': ('data_source_mode', 'mode_quick_toggle_panel'),
            'description': 'ONE-CLICK SWITCH BETWEEN MOCK SIMULATION AND REAL LIVE PRODUCTION DATA. When set to REAL, all services strictly fetch live balances & data from real APIs and real DB records without simulated overrides.'
        }),
        ('Bybit V5 API & eSIM Visa Card Gateway', {
            'fields': ('bybit_api_key', 'bybit_api_secret', 'bybit_user_id'),
            'description': 'Institutional credentials for Bybit V5 API live USDT funding balances, trading accounts, and corporate Visa card funding.'
        }),
        ('Airalo Wholesale eSIM Telecom API', {
            'fields': ('airalo_base_url', 'airalo_client_id', 'airalo_client_secret', 'airalo_min_threshold_usd'),
            'description': 'Official Airalo partner credentials for live eSIM inventory balance monitoring and refill alerts.'
        }),
        ('Epay Gateway API Credentials', {
            'fields': ('epay_api_url', 'epay_api_key')
        }),
        ('Binance P2P & Crypto Gateway', {
            'fields': ('binance_api_key', 'binance_api_secret', 'binance_merchant_id')
        }),
        ('G2Bulk Wholesale Supplier API & Safety Threshold', {
            'fields': ('g2bulk_base_url', 'g2bulk_api_key', 'g2bulk_min_threshold_usd')
        }),
        ('BaridiMob API Credentials', {
            'fields': ('baridimob_secret_token', 'baridimob_device_id')
        }),
        ('BaridiMob Operational Accounts Refill Thresholds', {
            'fields': ('gaming_baridimob_min_threshold_dzd', 'utility_baridimob_min_threshold_dzd'),
            'description': 'Configure the minimum DZD balance threshold below which an alert is triggered in the admin dashboard requiring working capital replenishment.'
        }),
        ('Valuation, Automated Routing & Blockchain Keys', {
            'fields': (
                'usd_to_dzd_exchange_rate',
                'master_admin_api_key',
                'stellar_horizon_url',
                'dzt_asset_code',
                'dzt_asset_issuer',
                'games_collection_wallet',
                'central_treasury_wallet',
                'is_auto_sync_enabled',
                'last_global_sync',
            )
        }),
    )

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('quick-toggle-mode/', self.admin_site.admin_view(self.quick_toggle_mode_view), name='monitoring_toggle_mode'),
        ]
        return custom_urls + urls

    def quick_toggle_mode_view(self, request):
        from django.shortcuts import redirect
        from django.contrib import messages
        sync_report = MonitoringGlobalSettings.apply_data_mode(mode=MonitoringGlobalSettings.DataSourceMode.REAL)
        messages.success(request, "🟢 Successfully synchronized REAL LIVE PRODUCTION DATA! All accounts and services queried live endpoints.")
        return redirect(request.META.get('HTTP_REFERER') or '../1/change/')

    @admin.display(description="Mode & Global Sync")
    def mode_quick_toggle_panel(self, obj):
        if not obj or not obj.id:
            return "-"
        real_btn_style = (
            "background:#059669; color:#fff; font-weight:bold; padding:8px 16px; border-radius:6px; text-decoration:none; display:inline-block; box-shadow:0 2px 4px rgba(0,0,0,0.2);"
        )
        status_text = '<strong style="color:#059669; font-size:14px;">🟢 CURRENTLY ACTIVE: REAL LIVE PRODUCTION DATA</strong>'
        return format_html(
            '<div style="padding:14px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; margin-top:4px;">'
            '<div style="margin-bottom:12px;">{}</div>'
            '<div>'
            '<a href="../quick-toggle-mode/?mode=REAL" style="{}">🔄 Force Live Synchronize All Services (Direct APIs)</a>'
            '</div>'
            '<p style="margin-top:10px; margin-bottom:0; font-size:12px; color:#64748b;">'
            'Queries live Bybit, Airalo, Binance, G2Bulk, Epay, BaridiMob, ECCP, and Stellar Horizon.'
            '</p>'
            '</div>',
            format_html(status_text),
            real_btn_style
        )

    @admin.display(description="Operational Mode")
    def mode_badge(self, obj):
        return format_html('<span style="background-color: #059669; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 11px;">🟢 REAL LIVE DATA</span>')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and 'data_source_mode' in form.changed_data:
            MonitoringGlobalSettings.apply_data_mode(mode=obj.data_source_mode)
        if obj.g2bulk_min_threshold_usd:
            SupplierAccount.objects.filter(provider=SupplierProvider.G2BULK).update(
                min_balance_threshold_usd=obj.g2bulk_min_threshold_usd
            )
        if obj.gaming_baridimob_min_threshold_dzd:
            BaridiMobAccount.objects.filter(system_type=SubSystemType.GAMING).update(
                min_balance_threshold_dzd=obj.gaming_baridimob_min_threshold_dzd
            )
        if obj.utility_baridimob_min_threshold_dzd:
            BaridiMobAccount.objects.filter(system_type=SubSystemType.UTILITY).update(
                min_balance_threshold_dzd=obj.utility_baridimob_min_threshold_dzd
            )

    @admin.display(description="Epay Exchange Rate (1 USD = X DZT)")
    def epay_exchange_rate_display(self, obj):
        return f"{obj.usd_to_dzd_exchange_rate:,.2f} DZT (Auto-synced from Epay)"

    def has_add_permission(self, request):
        return not MonitoringGlobalSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# ==============================================================================
#  🔐 2. STELLAR WALLETS & SECRET KEYS (SK) IN ONE PLACE
# ==============================================================================
class StellarWalletForm(forms.ModelForm):
    secret_seed = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={
            'placeholder': 'S... (56-character Ed25519 Secret Seed)',
            'style': 'font-family: monospace; width: 450px;',
            'autocomplete': 'new-password'
        }),
        required=False,
        label="Secret Key (SK)"
    )

    class Meta:
        model = StellarWallet
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        public_addr = (cleaned_data.get('public_address') or '').strip()
        secret_seed = (cleaned_data.get('secret_seed') or '').strip()
        family = cleaned_data.get('family')
        role = cleaned_data.get('role')

        # Institutional Rule 1: Central Treasury Singularity
        if family == WalletFamily.TREASURY or role == WalletRole.VAULT:
            if family == WalletFamily.TREASURY and role != WalletRole.VAULT:
                self.add_error('role', f"Treasury Family wallets must strictly have role '{WalletRole.VAULT.label}'.")
            if role == WalletRole.VAULT and family != WalletFamily.TREASURY:
                self.add_error('family', f"Central Treasury Master Vault must strictly belong to '{WalletFamily.TREASURY.label}'.")

            existing_vault = StellarWallet.objects.filter(
                models.Q(family=WalletFamily.TREASURY) | models.Q(role=WalletRole.VAULT)
            )
            if self.instance and self.instance.pk:
                existing_vault = existing_vault.exclude(pk=self.instance.pk)
            first_v = existing_vault.first()
            if first_v:
                raise ValidationError(
                    f"Strict Institutional Rule: Only ONE Central Treasury Master Vault is permitted in the entire system. "
                    f"Active vault already configured: '{first_v.name}' ({first_v.public_address})."
                )

        # Institutional Rule 2: Single Dedicated Profit Wallet per Operational Family
        if role == WalletRole.PROFIT:
            if family == WalletFamily.TREASURY:
                self.add_error('role', "Central Treasury does not have a Profit account. Profit accounts belong to operational families (Game, Facture, eSIM).")
            existing_profit = StellarWallet.objects.filter(
                family=family,
                role=WalletRole.PROFIT
            )
            if self.instance and self.instance.pk:
                existing_profit = existing_profit.exclude(pk=self.instance.pk)
            first_p = existing_profit.first()
            if first_p:
                self.add_error('role', f"Family '{family}' already has a dedicated Profit Wallet: '{first_p.name}'. Only ONE profit wallet is allowed per operational family.")

        if public_addr:
            if not public_addr.startswith('G') or len(public_addr) != 56:
                raise ValidationError("Invalid Stellar Public Key. Must start with 'G' and be exactly 56 characters.")

        if secret_seed:
            if not secret_seed.startswith('S') or len(secret_seed) != 56:
                raise ValidationError("Invalid Stellar Secret Key (SK). Must start with 'S' and be exactly 56 characters.")

            try:
                from stellar_sdk import Keypair
                kp = Keypair.from_secret(secret_seed)
                if public_addr and kp.public_key != public_addr:
                    raise ValidationError(
                        f"Cryptographic Mismatch: The Secret Key (SK) derives address '{kp.public_key}', which does NOT match the Public Address '{public_addr}'."
                    )
            except Exception as e:
                if isinstance(e, ValidationError):
                    raise
                raise ValidationError(f"Invalid Stellar cryptographic key: {e}")

        return cleaned_data


@admin.register(StellarWallet)
class StellarWalletAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    form = StellarWalletForm
    list_display = (
        'name',
        'family_badge',
        'role_badge',
        'public_address',
        'secret_key_status',
        'formatted_dzt_balance',
        'is_active',
        'last_synced_at',
    )
    list_filter = ('family', 'role', 'is_active', 'last_synced_at')
    search_fields = ('name', 'public_address', 'notes')
    fieldsets = (
        ('Wallet Family & Operational Role', {
            'fields': ('name', 'family', 'role', 'is_active')
        }),
        ('Cryptographic Keys (Public Key & Secret Key)', {
            'fields': ('public_address', 'secret_seed')
        }),
        ('Live Balance', {
            'fields': ('dzt_balance', 'last_synced_at', 'last_error')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )
    readonly_fields = ('dzt_balance', 'last_synced_at', 'last_error')
    actions = [
        'sync_live_balance_action',
        'toggle_active_status_action',
    ]

    def family_badge(self, obj):
        colors = {
            'GAME': '#7c3aed',
            'FACTURE': '#0284c7',
            'ESIM': '#059669',
            'TREASURY': '#b45309',
        }
        bg = colors.get(obj.family, '#475569')
        return format_html('<span style="background: {}; color: white; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 11px;">{}</span>', bg, obj.get_family_display())
    family_badge.short_description = "Family"

    def role_badge(self, obj):
        colors = {
            'COLLECTION': '#16a34a',
            'WITHDRAWAL': '#2563eb',
            'PROFIT': '#9333ea',
            'VAULT': '#d97706',
        }
        bg = colors.get(obj.role, '#475569')
        return format_html('<span style="background: {}; color: white; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 11px;">{}</span>', bg, obj.get_role_display())
    role_badge.short_description = "Role"

    def formatted_dzt_balance(self, obj):
        if obj.family == WalletFamily.TREASURY or obj.role == WalletRole.VAULT or (obj.name and 'treasury' in obj.name.lower()):
            return format_html('<span style="color: #64748b; font-weight: 600; font-style: italic;">— Master Issuer Vault —</span>')
        val = obj.dzt_balance or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; font-size: 13px; color: #0284c7;">{} DZT</span>', f"{val:,.2f}")
    formatted_dzt_balance.short_description = "Live DZT Balance"

    def secret_key_status(self, obj):
        if obj.secret_seed and str(obj.secret_seed).strip().startswith('S') and len(str(obj.secret_seed).strip()) == 56:
            return format_html('<span style="color: #16a34a; font-weight: bold;">Configured (S...56)</span>')
        return format_html('<span style="color: #dc2626; font-weight: bold;">Missing SK (Read-Only)</span>')
    secret_key_status.short_description = "Secret Key (SK)"

    @admin.action(description="🔄 Sync Live On-Chain Balance from Horizon")
    def sync_live_balance_action(self, request, queryset):
        success_count = 0
        for w in queryset:
            res = StellarService.sync_wallet(w)
            if res.get('success'):
                success_count += 1
        self.message_user(request, f"Successfully synced live Horizon balance for {success_count}/{queryset.count()} wallets.")

    @admin.action(description="⚡ Toggle Active / Inactive Status")
    def toggle_active_status_action(self, request, queryset):
        for w in queryset:
            w.is_active = not w.is_active
            w.save(update_fields=['is_active'])
        self.message_user(request, f"Toggled active status for {queryset.count()} wallet(s).")


# ==============================================================================
#  💰 3. ALL CAPITALS FOR EACH FAMILY IN ONE PLACE
# ==============================================================================
@admin.register(AccountWorkingCapital)
class AccountWorkingCapitalAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        'family_badge',
        'account_name',
        'formatted_capital',
        'description',
        'last_updated_at',
    )
    list_editable = ()
    list_filter = ('family',)
    search_fields = ('account_name', 'description')
    ordering = ['family']

    def family_badge(self, obj):
        colors = {
            'GAME': '#7c3aed',
            'FACTURE': '#0284c7',
            'ESIM': '#059669',
        }
        bg = colors.get(obj.family, '#475569')
        return format_html('<span style="background: {}; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 12px;">{}</span>', bg, obj.get_family_display())
    family_badge.short_description = "Operational Family"

    def formatted_capital(self, obj):
        val = obj.capital_amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; font-size: 14px; color: #16a34a;">{} DZD</span>', f"{val:,.2f}")
    formatted_capital.short_description = "Working Capital (DZD)"

    def has_add_permission(self, request):
        return AccountWorkingCapital.objects.count() < 3

    def has_delete_permission(self, request, obj=None):
        return False


# ==============================================================================
#  🎮 4. GAME OPERATIONS & MONITORING (Free Fire, PUBG, G2Bulk)
# ==============================================================================
@admin.register(GamingFinancialStatus)
class GamingFinancialStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'role_badge', 'public_address', 'formatted_dzt_balance', 'secret_key_status', 'last_synced_at')
    readonly_fields = [f.name for f in StellarWallet._meta.fields]
    actions = ['sync_live_balance_action']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(family=WalletFamily.GAME)

    def role_badge(self, obj):
        return format_html('<span style="background: #7c3aed; color: white; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 11px;">{}</span>', obj.get_role_display())
    role_badge.short_description = "Role"

    def formatted_dzt_balance(self, obj):
        val = obj.dzt_balance or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7; font-size: 13px;">{} DZT</span>', f"{val:,.2f}")
    formatted_dzt_balance.short_description = "Live Balance"

    def secret_key_status(self, obj):
        if obj.secret_seed:
            return format_html('<span style="color: #16a34a; font-weight: bold;">Configured (S...56)</span>')
        return format_html('<span style="color: #dc2626; font-weight: bold;">Missing SK</span>')
    secret_key_status.short_description = "SK Status"

    @admin.action(description="🔄 Sync Horizon Balance")
    def sync_live_balance_action(self, request, queryset):
        for w in queryset:
            StellarService.sync_wallet(w)
        self.message_user(request, f"Synced {queryset.count()} gaming wallet(s).")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SupplierAccount)
class SupplierAccountAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        'name',
        'formatted_balance_usd',
        'formatted_balance_dzd',
        'min_balance_threshold_usd',
        'threshold_status_badge',
        'account_uid',
        'account_username',
        'is_active',
        'last_synced_at',
    )
    list_editable = ('min_balance_threshold_usd',)
    search_fields = ('name', 'account_username', 'account_uid')
    list_filter = ('is_active', 'provider')
    actions = ['sync_g2bulk_balance_action']
    fields = (
        'provider',
        'name',
        'min_balance_threshold_usd',
        'balance_usd',
        'balance_dzd_equivalent',
        'account_username',
        'account_uid',
        'api_key',
        'is_active',
        'last_synced_at',
        'last_error',
    )
    readonly_fields = ('balance_dzd_equivalent', 'last_synced_at', 'last_error')

    def formatted_balance_usd(self, obj):
        val = obj.balance_usd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #059669; font-size: 13px;">${} USD</span>', f"{val:,.2f}")
    formatted_balance_usd.short_description = "Live Balance (USD $)"

    def formatted_balance_dzd(self, obj):
        val = obj.balance_dzd_equivalent or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7; font-size: 13px;">{} DZT</span>', f"{val:,.2f}")
    formatted_balance_dzd.short_description = "Equivalent in DZD"

    def threshold_status_badge(self, obj):
        threshold = obj.min_balance_threshold_usd or Decimal("500.00")
        bal = obj.balance_usd or Decimal("0.00")
        if bal < threshold:
            deficit = threshold - bal
            return format_html(
                '<span style="background: #991b1b; color: #fca5a5; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">Refill Needed (-${:,.2f})</span>',
                deficit
            )
        return format_html(
            '<span style="background: #166534; color: #86efac; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">Healthy Buffer</span>'
        )
    threshold_status_badge.short_description = "Buffer Status"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.provider == SupplierProvider.G2BULK and obj.min_balance_threshold_usd:
            settings = MonitoringGlobalSettings.get_settings()
            settings.g2bulk_min_threshold_usd = obj.min_balance_threshold_usd
            settings.save(update_fields=['g2bulk_min_threshold_usd'])

    @admin.action(description="Sync Live G2Bulk Balance via Official API")
    def sync_g2bulk_balance_action(self, request, queryset):
        res = G2BulkService.sync_supplier()
        if res.get('success'):
            self.message_user(request, f"G2Bulk Live Balance Synced: ${res.get('balance_usd'):,.2f} USD ({res.get('balance_dzd'):,.2f} DZT)")
        else:
            self.message_user(request, f"G2Bulk Sync Error: {res.get('error')}", level='ERROR')


@admin.register(G2BulkReplenishmentWindow)
class G2BulkReplenishmentWindowAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'supplier',
        'status_badge',
        'started_at',
        'duration_display',
        'expires_at',
        'countdown_badge',
        'initial_balance_usd',
        'target_replenish_amount_usd',
        'final_balance_usd',
        'suppressed_alerts_count',
        'alert_dispatched_badge',
    )
    list_filter = ('status', 'alert_dispatched', 'started_at')
    search_fields = ('initiated_by', 'notes', 'supplier__name')
    readonly_fields = ('started_at', 'expires_at', 'completed_at', 'created_at', 'updated_at', 'suppressed_alerts_count')
    actions = ['complete_window_action', 'cancel_window_action', 'evaluate_windows_action']

    def status_badge(self, obj):
        if obj.status == ReplenishmentWindowStatus.ACTIVE:
            return format_html(
                '<span style="background: #1e3a8a; color: #93c5fd; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🛡️ Active (Notifications Blocked)</span>'
            )
        elif obj.status == ReplenishmentWindowStatus.COMPLETED:
            return format_html(
                '<span style="background: #166534; color: #86efac; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">✅ Completed (Recharge Confirmed)</span>'
            )
        elif obj.status == ReplenishmentWindowStatus.EXPIRED_BALANCED:
            return format_html(
                '<span style="background: #065f46; color: #a7f3d0; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">Expired (100% Balanced)</span>'
            )
        elif obj.status == ReplenishmentWindowStatus.EXPIRED_DISCREPANCY:
            return format_html(
                '<span style="background: #991b1b; color: #fca5a5; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🚨 Expired (Discrepancy Alerted)</span>'
            )
        return format_html(
            '<span style="background: #475569; color: #cbd5e1; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">Cancelled</span>'
        )
    status_badge.short_description = "Window Status"

    def duration_display(self, obj):
        return f"{obj.duration_hours} Hours"
    duration_display.short_description = "Max Duration"

    def countdown_badge(self, obj):
        if obj.status != ReplenishmentWindowStatus.ACTIVE:
            return format_html('<span style="color: #64748b; font-size: 11px;">Closed</span>')
        sec = obj.remaining_seconds
        if sec <= 0:
            return format_html('<span style="color: #f59e0b; font-weight: bold; font-size: 11px;">Expired (Evaluating...)</span>')
        hrs = sec // 3600
        mins = (sec % 3600) // 60
        return format_html(
            '<span style="font-family: monospace; font-weight: bold; color: #3b82f6;">{}h {}m remaining</span>',
            hrs, mins
        )
    countdown_badge.short_description = "Grace Countdown"

    def alert_dispatched_badge(self, obj):
        if obj.alert_dispatched:
            return format_html('<span style="color: #ef4444; font-weight: bold;">🚨 Dispatched</span>')
        return format_html('<span style="color: #10b981;">No Discrepancy</span>')
    alert_dispatched_badge.short_description = "Delayed Alert"

    @admin.action(description="Complete Selected Windows (Recharge Confirmed)")
    def complete_window_action(self, request, queryset):
        for win in queryset.filter(status=ReplenishmentWindowStatus.ACTIVE):
            G2BulkReplenishmentWindow.complete_window(win.id, notes="Manually completed from Django Admin.")
        self.message_user(request, "Selected replenishment windows completed successfully.")

    @admin.action(description="Cancel Selected Windows (Restore Instant Alerting)")
    def cancel_window_action(self, request, queryset):
        queryset.filter(status=ReplenishmentWindowStatus.ACTIVE).update(
            status=ReplenishmentWindowStatus.CANCELLED,
            completed_at=timezone.now()
        )
        self.message_user(request, "Selected replenishment windows cancelled.")

    @admin.action(description="Evaluate Expired Windows & Check Discrepancies")
    def evaluate_windows_action(self, request, queryset):
        G2BulkReplenishmentWindow.evaluate_and_expire_windows()
        self.message_user(request, "Replenishment windows evaluated against live audit engine.")


@admin.register(GamingWithdrawalRecord)
class GamingWithdrawalRecordAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'stage_badge',
        'formatted_amount_dzd',
        'formatted_usd',
        'destination_supplier',
        'binance_status_badge',
        'withdrawal_date',
    )
    list_filter = ('stage', 'withdrawal_date')
    search_fields = ('title', 'p2p_order_id', 'binance_txid')
    actions = ['advance_to_p2p_action', 'advance_to_completed_action', 'verify_binance_action']

    def stage_badge(self, obj):
        if obj.stage == WithdrawalStage.COMPLETED:
            return format_html('<span style="background: #166534; color: #86efac; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">Stage 3: Completed</span>')
        elif obj.stage == WithdrawalStage.BINANCE_P2P:
            return format_html('<span style="background: #1e3a8a; color: #93c5fd; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">Stage 2: Binance P2P</span>')
        elif obj.stage == WithdrawalStage.CANCELLED:
            return format_html('<span style="background: #991b1b; color: #fca5a5; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">Cancelled</span>')
        return format_html('<span style="background: #854d0e; color: #fef08a; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">Stage 1: Allocated</span>')
    stage_badge.short_description = "Workflow Stage"

    def formatted_amount_dzd(self, obj):
        val = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #dc2626;">-{} DZT</span>', f"{val:,.2f}")
    formatted_amount_dzd.short_description = "Amount (DZT)"

    def formatted_usd(self, obj):
        val = obj.amount_usd_equivalent or Decimal("0.00")
        return format_html('<span style="font-family: monospace; color: #059669;">${}</span>', f"{val:,.2f}")
    formatted_usd.short_description = "USD ($)"

    def binance_status_badge(self, obj):
        if obj.binance_verification_status == 'VERIFIED_MATCH':
            return format_html('<span style="color: #16a34a; font-weight: bold;">🟢 Verified</span>')
        elif obj.binance_txid or obj.p2p_order_id:
            return format_html('<span style="color: #2563eb; font-weight: bold;">🔵 Recorded</span>')
        return format_html('<span style="color: #64748b;">⚪ Pending</span>')
    binance_status_badge.short_description = "Binance"

    @admin.action(description="⏩ Advance Stage to 2: Binance P2P Acquired")
    def advance_to_p2p_action(self, request, queryset):
        updated = queryset.filter(stage=WithdrawalStage.ALLOCATED).update(stage=WithdrawalStage.BINANCE_P2P, updated_at=timezone.now())
        self.message_user(request, f"Advanced {updated} withdrawal(s) to Stage 2: Binance P2P Acquired.")

    @admin.action(description="✅ Advance Stage to 3: G2Bulk Confirmed & Closed")
    def advance_to_completed_action(self, request, queryset):
        updated = queryset.exclude(stage=WithdrawalStage.COMPLETED).update(stage=WithdrawalStage.COMPLETED, updated_at=timezone.now())
        self.message_user(request, f"Advanced {updated} withdrawal(s) to Stage 3: Completed & Closed.")

    @admin.action(description="🔍 Run Binance Verification Check")
    def verify_binance_action(self, request, queryset):
        for w in queryset:
            if w.binance_txid:
                BinanceVerificationService.verify_transaction_hash(w)
        self.message_user(request, f"Ran Binance verification checks for {queryset.count()} record(s).")


@admin.register(GamingCapitalEntry)
class GamingCapitalEntryAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'formatted_amount_dzd', 'deposit_date', 'source_account', 'destination_supplier', 'created_at')
    list_filter = ('deposit_date',)
    search_fields = ('title', 'source_account')

    def formatted_amount_dzd(self, obj):
        val = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #16a34a;">+{} DZT</span>', f"{val:,.2f}")
    formatted_amount_dzd.short_description = "Amount (DZT)"


@admin.register(GameProfitRecord)
class GameProfitRecordAdmin(admin.ModelAdmin):
    list_display = ('order_reference', 'game_code', 'package_name', 'player_id', 'formatted_sale', 'formatted_cost', 'formatted_profit', 'is_delivered', 'order_date')
    list_filter = ('game_code', 'is_delivered', 'order_date')
    search_fields = ('order_reference', 'player_id', 'package_name')
    readonly_fields = [f.name for f in GameProfitRecord._meta.fields]

    def formatted_sale(self, obj):
        val = obj.sale_price_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace;">{} DZT</span>', f"{val:,.2f}")
    formatted_sale.short_description = "Customer Sale"

    def formatted_cost(self, obj):
        val = obj.cost_price_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; color: #dc2626;">{} DZT</span>', f"{val:,.2f}")
    formatted_cost.short_description = "Wholesale Cost"

    def formatted_profit(self, obj):
        val = obj.net_profit_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #16a34a;">+{} DZT</span>', f"{val:,.2f}")
    formatted_profit.short_description = "Net Profit"

    def has_add_permission(self, request):
        return False


# ==============================================================================
#  📄 5. FACTURE OPERATIONS & SETTLEMENT (Sonelgaz, ADE, AT, Sihaam 31)
# ==============================================================================
@admin.register(UtilityFinancialStatus)
class UtilityFinancialStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'role_badge', 'public_address', 'formatted_dzt_balance', 'secret_key_status', 'last_synced_at')
    readonly_fields = [f.name for f in StellarWallet._meta.fields]
    actions = ['sync_live_balance_action']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(family=WalletFamily.FACTURE)

    def role_badge(self, obj):
        return format_html('<span style="background: #0284c7; color: white; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 11px;">{}</span>', obj.get_role_display())
    role_badge.short_description = "Role"

    def formatted_dzt_balance(self, obj):
        val = obj.dzt_balance or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7; font-size: 13px;">{} DZT</span>', f"{val:,.2f}")
    formatted_dzt_balance.short_description = "Live Balance"

    def secret_key_status(self, obj):
        if obj.secret_seed:
            return format_html('<span style="color: #16a34a; font-weight: bold;">Configured (S...56)</span>')
        return format_html('<span style="color: #dc2626; font-weight: bold;">Missing SK</span>')
    secret_key_status.short_description = "SK Status"

    @admin.action(description="🔄 Sync Horizon Balance")
    def sync_live_balance_action(self, request, queryset):
        for w in queryset:
            StellarService.sync_wallet(w)
        self.message_user(request, f"Synced {queryset.count()} facture wallet(s).")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GamingBaridiMobAccount)
class GamingBaridiMobAccountAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('account_name', 'formatted_balance_dzd', 'min_balance_threshold_dzd', 'rip_number', 'system_type', 'is_active', 'notes', 'created_at')
    list_filter = ('is_active', 'system_type')
    search_fields = ('account_name', 'rip_number', 'notes')
    fields = ('account_name', 'rip_number', 'system_type', 'min_balance_threshold_dzd', 'is_active', 'notes')

    def formatted_balance_dzd(self, obj):
        val = obj.balance_dzd or Decimal("0.00")
        color = "#16a34a" if val >= obj.min_balance_threshold_dzd else "#dc2626"
        return format_html('<span style="font-family: monospace; font-weight: bold; color: {}; font-size: 14px;">{} DZD</span>', color, f"{val:,.2f}")
    formatted_balance_dzd.short_description = "Live Balance (DZD)"

    def get_changeform_initial_data(self, request):
        return {'system_type': SubSystemType.GAMING, 'is_active': True}

    def save_model(self, request, obj, form, change):
        if not obj.system_type:
            obj.system_type = SubSystemType.GAMING
        super().save_model(request, obj, form, change)


@admin.register(UtilityBaridiMobAccount)
class UtilityBaridiMobAccountAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('account_name', 'formatted_balance_dzd', 'min_balance_threshold_dzd', 'rip_number', 'system_type', 'is_active', 'last_synced_at')
    list_filter = ('is_active', 'system_type')
    search_fields = ('account_name', 'rip_number', 'account_email', 'notes')
    fields = ('account_name', 'rip_number', 'system_type', 'min_balance_threshold_dzd', 'is_active', 'account_email', 'notes')
    actions = ['sync_baridi_balance_action']

    def formatted_balance_dzd(self, obj):
        val = obj.balance_dzd or Decimal("0.00")
        color = "#16a34a" if val >= obj.min_balance_threshold_dzd else "#dc2626"
        return format_html('<span style="font-family: monospace; font-weight: bold; color: {}; font-size: 14px;">{} DZD</span>', color, f"{val:,.2f}")
    formatted_balance_dzd.short_description = "Live Balance (DZD)"

    @admin.action(description="🔄 Sync Live BaridiMob (Sihaam 31) Balance")
    def sync_baridi_balance_action(self, request, queryset):
        res = BaridiMobService.sync_baridi_balance()
        if res.get('success'):
            self.message_user(request, f"BaridiMob balance synced successfully: {res.get('balance_dzd'):,.2f} DZD")
        else:
            self.message_user(request, f"BaridiMob Sync Error: {res.get('error')}", level='ERROR')

    def get_changeform_initial_data(self, request):
        return {'system_type': SubSystemType.UTILITY, 'is_active': True}

    def save_model(self, request, obj, form, change):
        if not obj.system_type:
            obj.system_type = SubSystemType.UTILITY
        super().save_model(request, obj, form, change)


@admin.register(eSIMBaridiMobAccount)
class eSIMBaridiMobAccountAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('account_name', 'rip_number', 'system_type', 'is_active', 'notes', 'created_at')
    list_filter = ('is_active', 'system_type')
    search_fields = ('account_name', 'rip_number', 'notes')
    fields = ('account_name', 'rip_number', 'system_type', 'is_active', 'notes')

    def get_changeform_initial_data(self, request):
        return {'system_type': SubSystemType.ESIM, 'is_active': True}

    def save_model(self, request, obj, form, change):
        if not obj.system_type:
            obj.system_type = SubSystemType.ESIM
        super().save_model(request, obj, form, change)


@admin.register(BaridiMobAccount)
class BaridiMobAccountAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('account_name', 'system_type', 'formatted_balance_dzd', 'min_balance_threshold_dzd', 'rip_number', 'account_email', 'is_active', 'last_synced_at')
    list_filter = ('system_type', 'is_active')
    search_fields = ('account_name', 'rip_number', 'account_email', 'notes')
    fields = ('account_name', 'rip_number', 'system_type', 'min_balance_threshold_dzd', 'is_active', 'account_email', 'notes')
    actions = ['sync_baridi_balance_action']

    def formatted_balance_dzd(self, obj):
        val = obj.balance_dzd or Decimal("0.00")
        color = "#16a34a" if val >= obj.min_balance_threshold_dzd else "#dc2626"
        return format_html('<span style="font-family: monospace; font-weight: bold; color: {}; font-size: 14px;">{} DZD</span>', color, f"{val:,.2f}")
    formatted_balance_dzd.short_description = "Live Balance (DZD)"

    @admin.action(description="🔄 Sync Live BaridiMob (Sihaam 31) Balance")
    def sync_baridi_balance_action(self, request, queryset):
        res = BaridiMobService.sync_baridi_balance()
        if res.get('success'):
            self.message_user(request, f"BaridiMob balance synced successfully: {res.get('balance_dzd'):,.2f} DZD")

@admin.register(BaridiMobTransaction)
class BaridiMobTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'tid',
        'account',
        'formatted_amount',
        'transaction_type',
        'formatted_balance',
        'transaction_date',
        'ref_num',
        'created_at',
    )
    list_filter = ('account', 'transaction_type', 'transaction_date')
    search_fields = ('tid', 'ref_num', 'description', 'account__account_name')
    date_hierarchy = 'transaction_date'
    ordering = ('-transaction_date', '-created_at')
    readonly_fields = [f.name for f in BaridiMobTransaction._meta.fields]

    def formatted_amount(self, obj):
        val = obj.amount or Decimal("0.00")
        if val > 0:
            return format_html('<span style="font-family: monospace; font-weight: bold; color: #16a34a;">+{} DZD</span>', f"{val:,.2f}")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #dc2626;">{} DZD</span>', f"{val:,.2f}")
    formatted_amount.short_description = "Amount (DZD)"

    def formatted_balance(self, obj):
        if obj.available_balance is not None:
            return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7;">{} DZD</span>', f"{obj.available_balance:,.2f}")
        return "—"
    formatted_balance.short_description = "Balance After Tx"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BaridiMobFundingReceipt)
class BaridiMobFundingReceiptAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        'reference',
        'receipt_preview_link',
        'formatted_amount_dzd',
        'formatted_fee',
        'status_badge',
        'recipient_rip',
        'responsible_person',
        'receipt_date',
    )
    list_filter = ('status', 'receipt_date', 'created_at')
    search_fields = ('reference', 'recipient_rip', 'responsible_person')
    readonly_fields = ('file_hash', 'raw_text', 'created_at')
    actions = ['reparse_receipt_action']

    def receipt_preview_link(self, obj):
        if obj.receipt_file and hasattr(obj.receipt_file, 'url'):
            return format_html('<a href="{}" target="_blank" style="background: #0284c7; color: white; padding: 3px 8px; border-radius: 4px; text-decoration: none; font-size: 11px; font-weight: bold;">📄 View Receipt</a>', obj.receipt_file.url)
        return format_html('<span style="color: #94a3b8; font-size: 11px;">No File</span>')
    receipt_preview_link.short_description = "Receipt Document"

    def formatted_amount_dzd(self, obj):
        amt = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7;">{} DZD</span>', f"{amt:,.2f}")
    formatted_amount_dzd.short_description = "Receipt Amount"

    def formatted_fee(self, obj):
        val = obj.fee_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; color: #dc2626;">{} DZD</span>', f"{val:,.2f}")
    formatted_fee.short_description = "Fee"

    def status_badge(self, obj):
        colors = {
            'PENDING_P2P': ('#854d0e', '#fef08a', '1. Pending P2P'),
            'USDT_ACQUIRED': ('#1e3a8a', '#93c5fd', '2. USDT Acquired'),
            'G2BULK_CONFIRMED': ('#166534', '#86efac', '3. G2Bulk Confirmed'),
        }
        bg, text, label = colors.get(obj.status, ('#475569', '#ffffff', obj.status))
        return format_html('<span style="background: {}; color: {}; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 11px;">{}</span>', bg, text, label)
    status_badge.short_description = "Status"

    @admin.action(description="🔍 Re-parse Selected Receipts with OCR")
    def reparse_receipt_action(self, request, queryset):
        success_count = 0
        for r in queryset:
            if r.receipt_file:
                res = ReceiptParserService.parse_receipt(r.receipt_file)
                if res.get('success'):
                    success_count += 1
        self.message_user(request, f"Re-parsed {success_count}/{queryset.count()} receipt(s).")


@admin.register(UtilityWithdrawalRecord)
class UtilityWithdrawalRecordAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'title', 'stage_badge', 'formatted_amount_dzd', 'source_baridimob', 'destination_recipient', 'withdrawal_date')
    list_filter = ('stage', 'withdrawal_date')
    search_fields = ('title', 'reference', 'destination_recipient')

    def stage_badge(self, obj):
        if obj.stage == WithdrawalStage.COMPLETED:
            return format_html('<span style="background: #166534; color: #86efac; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🟢 Completed</span>')
        return format_html('<span style="background: #854d0e; color: #fef08a; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🟡 Allocated</span>')
    stage_badge.short_description = "Status"

    def formatted_amount_dzd(self, obj):
        val = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #dc2626;">-{} DZT</span>', f"{val:,.2f}")
    formatted_amount_dzd.short_description = "Amount (DZT)"


@admin.register(UtilityCapitalEntry)
class UtilityCapitalEntryAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'formatted_amount_dzd', 'deposit_date', 'source_account', 'destination_baridimob', 'created_at')
    list_filter = ('deposit_date',)
    search_fields = ('title', 'source_account')

    def formatted_amount_dzd(self, obj):
        val = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #16a34a;">+{} DZT</span>', f"{val:,.2f}")
    formatted_amount_dzd.short_description = "Amount (DZT)"


@admin.register(UtilityBillRecord)
class UtilityBillRecordAdmin(admin.ModelAdmin):
    list_display = ('bill_reference', 'service_badge', 'customer_account', 'formatted_bill_amount', 'formatted_commission', 'is_settled', 'payment_date')
    list_filter = ('service', 'is_settled', 'payment_date')
    search_fields = ('bill_reference', 'customer_account')

    def service_badge(self, obj):
        return format_html('<span style="background: #0284c7; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>', obj.get_service_display())
    service_badge.short_description = "Service"

    def formatted_bill_amount(self, obj):
        val = obj.bill_amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace;">{} DZD</span>', f"{val:,.2f}")
    formatted_bill_amount.short_description = "Bill Face Amount"

    def formatted_commission(self, obj):
        val = obj.commission_earned_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #16a34a;">+{} DZD</span>', f"{val:,.2f}")
    formatted_commission.short_description = "Commission"

    def has_add_permission(self, request):
        return False


# ==============================================================================
#  📶 6. ESIM OPERATIONS & MONITORING (Telecom & Data)
# ==============================================================================
@admin.register(eSIMFinancialStatus)
class eSIMFinancialStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'role_badge', 'public_address', 'formatted_dzt_balance', 'secret_key_status', 'last_synced_at')
    readonly_fields = [f.name for f in StellarWallet._meta.fields]
    actions = ['sync_live_balance_action']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(family=WalletFamily.ESIM)

    def role_badge(self, obj):
        return format_html('<span style="background: #059669; color: white; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 11px;">{}</span>', obj.get_role_display())
    role_badge.short_description = "Role"

    def formatted_dzt_balance(self, obj):
        val = obj.dzt_balance or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7; font-size: 13px;">{} DZT</span>', f"{val:,.2f}")
    formatted_dzt_balance.short_description = "Live Balance"

    def secret_key_status(self, obj):
        if obj.secret_seed:
            return format_html('<span style="color: #16a34a; font-weight: bold;">Configured (S...56)</span>')
        return format_html('<span style="color: #dc2626; font-weight: bold;">Missing SK</span>')
    secret_key_status.short_description = "SK Status"

    @admin.action(description="🔄 Sync Horizon Balance")
    def sync_live_balance_action(self, request, queryset):
        for w in queryset:
            StellarService.sync_wallet(w)
        self.message_user(request, f"Synced {queryset.count()} eSIM wallet(s).")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(eSIMWithdrawalRecord)
class eSIMWithdrawalRecordAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'title', 'stage_badge', 'formatted_amount_dzd', 'destination_recipient', 'withdrawal_date')
    list_filter = ('stage', 'withdrawal_date')
    search_fields = ('title', 'reference', 'destination_recipient')

    def stage_badge(self, obj):
        if obj.stage == WithdrawalStage.COMPLETED:
            return format_html('<span style="background: #166534; color: #86efac; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🟢 Completed</span>')
        return format_html('<span style="background: #854d0e; color: #fef08a; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🟡 Allocated</span>')
    stage_badge.short_description = "Status"

    def formatted_amount_dzd(self, obj):
        val = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #dc2626;">-{} DZT</span>', f"{val:,.2f}")
    formatted_amount_dzd.short_description = "Amount (DZT)"


@admin.register(eSIMCapitalEntry)
class eSIMCapitalEntryAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'formatted_amount_dzd', 'deposit_date', 'source_account', 'created_at')
    list_filter = ('deposit_date',)
    search_fields = ('title', 'source_account')

    def formatted_amount_dzd(self, obj):
        val = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #16a34a;">+{} DZT</span>', f"{val:,.2f}")
    formatted_amount_dzd.short_description = "Amount (DZT)"


@admin.register(BybitAccount)
class BybitAccountAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('account_name', 'user_id', 'formatted_funding_usdt', 'formatted_unified_usdt', 'formatted_dzd', 'is_active', 'last_synced_at')
    list_filter = ('is_active', 'last_synced_at')
    search_fields = ('account_name', 'user_id')
    readonly_fields = ('balance_dzd_equivalent', 'last_synced_at', 'last_error', 'created_at', 'updated_at')

    def formatted_funding_usdt(self, obj):
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7;">{} USDT</span>', f"{obj.funding_balance_usdt:,.2f}")
    formatted_funding_usdt.short_description = "Funding Wallet"

    def formatted_unified_usdt(self, obj):
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #475569;">{} USDT</span>', f"{obj.unified_balance_usdt:,.2f}")
    formatted_unified_usdt.short_description = "Unified Wallet"

    def formatted_dzd(self, obj):
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #16a34a;">{} DZT</span>', f"{obj.balance_dzd_equivalent:,.2f}")
    formatted_dzd.short_description = "DZD Equivalent"


@admin.register(AiraloAccount)
class AiraloAccountAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('account_name', 'formatted_balance_usd', 'is_active', 'last_synced_at')
    list_filter = ('is_active', 'last_synced_at')
    search_fields = ('account_name',)
    readonly_fields = ('last_synced_at', 'last_error', 'created_at', 'updated_at')

    def formatted_balance_usd(self, obj):
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7;">${} USD</span>', f"{obj.available_balance_usd:,.2f}")
    formatted_balance_usd.short_description = "Available Balance"



# ==============================================================================
#  🏛️ 7. CENTRAL TREASURY, BINANCE & SOLIDARITY AUDIT
# ==============================================================================
@admin.register(BalanceAuditLog)
class BalanceAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'checked_at',
        'status_badge',
        'formatted_discrepancy',
        'formatted_assets',
        'formatted_in_transit',
        'formatted_expenses',
        'formatted_capital',
        'formatted_profits',
    )
    list_filter = ('status', 'checked_at')
    readonly_fields = [f.name for f in BalanceAuditLog._meta.fields]
    actions = ['run_live_audit_action']

    def status_badge(self, obj):
        if obj.status == 'BALANCED':
            return format_html('<span style="background: #166534; color: #86efac; font-weight: bold; padding: 4px 10px; border-radius: 6px; font-size: 11px;">🟢 100% Balanced</span>')
        return format_html('<span style="background: #991b1b; color: #fca5a5; font-weight: bold; padding: 4px 10px; border-radius: 6px; font-size: 11px;">🔴 Discrepancy</span>')
    status_badge.short_description = "Audit Status"

    def formatted_discrepancy(self, obj):
        val = obj.discrepancy_dzd or Decimal("0.00")
        color = "#16a34a" if abs(val) <= Decimal("0.05") else "#dc2626"
        return format_html('<span style="font-family: monospace; font-weight: bold; color: {}; font-size: 13px;">{} DZT</span>', color, f"{val:,.2f}")
    formatted_discrepancy.short_description = "Discrepancy (DZT)"

    def formatted_assets(self, obj):
        val = obj.total_assets_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; color: #0284c7;">{} DZT</span>', f"{val:,.2f}")
    formatted_assets.short_description = "Assets Total"

    def formatted_in_transit(self, obj):
        val = getattr(obj, 'total_in_transit_dzd', Decimal("0.00")) or Decimal("0.00")
        color = "#eab308" if val > 0 else "#64748b"
        return format_html('<span style="font-family: monospace; font-weight: bold; color: {};">{} DZT</span>', color, f"{val:,.2f}")
    formatted_in_transit.short_description = "In-Transit Funds"

    def formatted_expenses(self, obj):
        val = obj.total_expenses_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; color: #dc2626;">{} DZT</span>', f"{val:,.2f}")
    formatted_expenses.short_description = "Expenses Total"

    def formatted_capital(self, obj):
        val = obj.total_capital_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; color: #16a34a;">{} DZT</span>', f"{val:,.2f}")
    formatted_capital.short_description = "Capital Total"

    def formatted_profits(self, obj):
        val = obj.total_profits_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; color: #9333ea;">{} DZT</span>', f"{val:,.2f}")
    formatted_profits.short_description = "Profits Total"

    @admin.action(description="⚡ Run Live Golden Balance Audit Snapshot Now")
    def run_live_audit_action(self, request, queryset):
        res = BalanceEngine.run_audit(sync_live=True, send_alerts=False)
        self.message_user(
            request,
            f"Audit Complete: Status = {res.get('status')}, Assets = {res.get('total_assets'):,.2f} DZT, "
            f"Capital = {res.get('total_capital'):,.2f} DZT, Discrepancy = {res.get('discrepancy'):,.2f} DZT."
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BinanceAccount)
class BinanceAccountAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        'account_name',
        'formatted_balance_usdt',
        'formatted_balance_dzd',
        'merchant_id',
        'is_active',
        'last_synced_at',
    )
    search_fields = ('account_name', 'merchant_id')
    list_filter = ('is_active',)
    actions = ['sync_binance_balance_action']

    def formatted_balance_usdt(self, obj):
        val = obj.balance_usdt or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7; font-size: 14px;">{} USDT</span>', f"{val:,.2f}")
    formatted_balance_usdt.short_description = "Live USDT Balance"

    def formatted_balance_dzd(self, obj):
        val = obj.balance_dzd_equivalent or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #16a34a; font-size: 14px;">{} DZT</span>', f"{val:,.2f}")
    formatted_balance_dzd.short_description = "Equivalent in DZD"

    @admin.action(description="🔄 Sync Live Binance USDT Balance from Binance API")
    def sync_binance_balance_action(self, request, queryset):
        res = BinanceApiService.get_account_balances()
        if res.get('success'):
            for acc in queryset:
                acc.last_synced_at = timezone.now()
                acc.save(update_fields=['last_synced_at'])
            self.message_user(request, f"Binance balance verified successfully.")
        else:
            self.message_user(request, f"Binance API Sync Notice: {res.get('error')}", level='WARNING')


@admin.register(BinanceP2POperation)
class BinanceP2POperationAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'p2p_order_id',
        'binance_txid',
        'formatted_amount_dzd',
        'formatted_usd',
        'binance_status_badge',
        'stage_badge',
        'withdrawal_date',
    )
    list_filter = ('binance_verification_status', 'stage', 'withdrawal_date')
    search_fields = ('title', 'p2p_order_id', 'binance_txid')
    actions = ['verify_binance_txid_action']

    def stage_badge(self, obj):
        if obj.stage == WithdrawalStage.COMPLETED:
            return format_html('<span style="background: #166534; color: #86efac; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🟢 3. Completed</span>')
        elif obj.stage == WithdrawalStage.BINANCE_P2P:
            return format_html('<span style="background: #1e3a8a; color: #93c5fd; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🔵 2. Binance P2P</span>')
        return format_html('<span style="background: #854d0e; color: #fef08a; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🟡 1. Allocated</span>')
    stage_badge.short_description = "Stage"

    def formatted_amount_dzd(self, obj):
        val = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #dc2626;">-{} DZT</span>', f"{val:,.2f}")
    formatted_amount_dzd.short_description = "Amount (DZT)"

    def formatted_usd(self, obj):
        val = obj.binance_verified_amount_usd or obj.amount_usd_equivalent or Decimal("0.00")
        return format_html('<span style="font-family: monospace; color: #059669;">${}</span>', f"{val:,.2f}")
    formatted_usd.short_description = "USD ($)"

    def binance_status_badge(self, obj):
        if obj.binance_verification_status == 'VERIFIED_MATCH':
            return format_html('<span style="color: #16a34a; font-weight: bold;">🟢 Verified</span>')
        elif obj.binance_verification_status == 'AMOUNT_MISMATCH':
            return format_html('<span style="color: #dc2626; font-weight: bold;">🔴 Mismatch</span>')
        elif obj.binance_txid or obj.p2p_order_id:
            return format_html('<span style="color: #2563eb; font-weight: bold;">🔵 Recorded</span>')
        return format_html('<span style="color: #64748b;">⚪ None</span>')
    binance_status_badge.short_description = "Verification"

    @admin.action(description="🔍 Run Binance Hash Verification Check")
    def verify_binance_txid_action(self, request, queryset):
        for w in queryset:
            if w.binance_txid:
                BinanceVerificationService.verify_transaction_hash(w)
        self.message_user(request, f"Executed verification for {queryset.count()} operation(s).")

    def has_add_permission(self, request):
        return False


@admin.register(WalletSweepLog)
class WalletSweepLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'timestamp', 'source_wallet', 'destination_wallet', 'formatted_amount_dzt', 'sweep_type', 'status_badge', 'formatted_epay_profit')
    list_filter = ('sweep_type', 'status', 'timestamp')
    readonly_fields = [f.name for f in WalletSweepLog._meta.fields]
    actions = ['action_run_sweep_now', 'action_run_dry_run']

    def formatted_amount_dzt(self, obj):
        val = obj.amount_dzt or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7;">{} DZT</span>', f"{val:,.2f}")
    formatted_amount_dzt.short_description = "Amount (DZT)"

    def formatted_epay_profit(self, obj):
        val = obj.epay_reported_profit or Decimal("0.00")
        return format_html('<span style="font-family: monospace; color: #16a34a;">{} DZD</span>', f"{val:,.2f}")
    formatted_epay_profit.short_description = "Epay Profit (DZD)"

    def status_badge(self, obj):
        if obj.status == 'SUCCESS':
            return format_html('<span style="color: #16a34a; font-weight: bold;">🟢 Success</span>')
        elif obj.status == 'FAILED':
            return format_html('<span style="color: #dc2626; font-weight: bold;">🔴 Failed</span>')
        elif obj.status == 'ABORTED_DISCREPANCY':
            return format_html('<span style="color: #ea580c; font-weight: bold;">🟠 Aborted (Discrepancy)</span>')
        return format_html('<span style="color: #64748b; font-weight: bold;">{}</span>', obj.status)
    status_badge.short_description = "Status"

    @admin.action(description="🚀 Run Daily Stellar Sweep NOW (Live Transfer)")
    def action_run_sweep_now(self, request, queryset):
        from monitoring.services.stellar_sweep_service import StellarSweepService
        result = StellarSweepService.execute_daily_sweep(dry_run=False, force=False)
        if result.get("aborted"):
            self.message_user(
                request,
                f"⚠️ Sweep ABORTED due to pre-flight audit errors: {'; '.join(result.get('errors', []))}",
                level='ERROR'
            )
        elif result.get("success"):
            transfers = result.get("transfers", [])
            success_count = sum(1 for t in transfers if t.get("success"))
            total_sent = sum(t["amount"] for t in transfers if t.get("success"))
            self.message_user(
                request,
                f"🟢 Daily Sweep executed successfully! {success_count} transfer(s) — Total: {total_sent:,.2f} DZT sent.",
                level='SUCCESS'
            )
        else:
            self.message_user(request, "❌ Sweep failed unexpectedly.", level='ERROR')

    @admin.action(description="🔍 Run Sweep DRY-RUN (Simulation Only — No Real Transfers)")
    def action_run_dry_run(self, request, queryset):
        from monitoring.services.stellar_sweep_service import StellarSweepService
        result = StellarSweepService.execute_daily_sweep(dry_run=True, force=False)
        audit = result.get("audit", {})
        if result.get("success"):
            self.message_user(
                request,
                f"✅ DRY-RUN Passed! Epay Profit: {audit.get('today_profit', 0):,.2f} DZD | "
                f"Collection Wallets: {audit.get('total_collection_dzt', 0):,.2f} DZT | "
                f"No real transactions were sent.",
                level='SUCCESS'
            )
        else:
            errors = audit.get("errors", [])
            self.message_user(
                request,
                f"⚠️ DRY-RUN: Audit found issues: {'; '.join(errors)}",
                level='WARNING'
            )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExpenseRecord)
class ExpenseRecordAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'system_type', 'category', 'formatted_amount_dzd', 'expense_date', 'reference', 'created_at')
    list_filter = ('system_type', 'category', 'expense_date')
    search_fields = ('title', 'reference', 'notes')

    def formatted_amount_dzd(self, obj):
        val = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #dc2626;">-{} DZT</span>', f"{val:,.2f}")
    formatted_amount_dzd.short_description = "Amount (DZT)"


@admin.register(WithdrawalRecord)
class WithdrawalRecordAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'system_type',
        'stage_badge',
        'formatted_amount_dzd',
        'destination_recipient',
        'withdrawal_date',
    )
    list_filter = ('stage', 'system_type', 'withdrawal_type', 'withdrawal_date')
    search_fields = ('title', 'reference', 'destination_recipient', 'notes')

    def stage_badge(self, obj):
        if obj.stage == WithdrawalStage.COMPLETED:
            return format_html('<span style="background: #166534; color: #86efac; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🟢 Completed</span>')
        elif obj.stage == WithdrawalStage.BINANCE_P2P:
            return format_html('<span style="background: #1e3a8a; color: #93c5fd; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🔵 Binance P2P</span>')
        return format_html('<span style="background: #854d0e; color: #fef08a; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🟡 Allocated</span>')
    stage_badge.short_description = "Stage"

    def formatted_amount_dzd(self, obj):
        val = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #dc2626;">-{} DZT</span>', f"{val:,.2f}")
    formatted_amount_dzd.short_description = "Amount (DZT)"


@admin.register(CapitalEntry)
class CapitalEntryAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = ('title', 'category', 'formatted_amount_dzd', 'deposit_date', 'source_account', 'created_at')
    list_filter = ('category', 'deposit_date')
    search_fields = ('title', 'source_account', 'notes')

    def formatted_amount_dzd(self, obj):
        val = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #16a34a;">+{} DZT</span>', f"{val:,.2f}")
    formatted_amount_dzd.short_description = "Amount (DZT)"


# ==============================================================================
#  👥 8. EMPLOYEES & OPERATORS (BY MISSION & ROLE)
# ==============================================================================
class StaffOperatorForm(forms.ModelForm):
    login_password = forms.CharField(
        widget=forms.PasswordInput(render_value=False),
        required=False,
        label="Set / Reset Login Password",
        help_text="Enter a secure password to set or update this operator's login password. Leave blank when editing to keep existing password."
    )

    class Meta:
        model = StaffOperator
        fields = '__all__'


@admin.register(StaffOperator)
class StaffOperatorAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    form = StaffOperatorForm
    list_display = (
        'employee_code',
        'full_name',
        'username',
        'mission_badge',
        'status_badge',
        'email',
        'phone_number',
        'login_account_status',
        'view_audit_trail_link',
        'created_at',
    )
    list_filter = ('mission_role', 'status', 'is_active', 'created_at')
    search_fields = ('full_name', 'username', 'employee_code', 'email', 'phone_number')
    readonly_fields = ('employee_code', 'last_activity_at', 'created_at', 'updated_at')
    fieldsets = (
        ('Staff Identity & Credentials', {
            'fields': ('full_name', 'username', 'email', 'login_password', 'phone_number', 'employee_code')
        }),
        ('Mission Role & Access Permission', {
            'fields': ('mission_role', 'status', 'is_active', 'linked_user')
        }),
        ('Employment Details & Notes', {
            'fields': ('notes', 'last_activity_at', 'created_at', 'updated_at')
        }),
    )
    actions = ['activate_operators_action', 'suspend_operators_action', 'reset_password_action', 'resync_permissions_action']

    def mission_badge(self, obj):
        colors = {
            'GAME_OPERATOR': ('#7c3aed', '🎮 Game Family Operator'),
            'FACTURE_OPERATOR': ('#0284c7', '📄 Facture Family Operator'),
            'ESIM_OPERATOR': ('#059669', '📶 eSIM Family Operator'),
            'TREASURY_OFFICER': ('#b45309', '🏛️ Treasury & P2P Officer'),
            'AUDITOR': ('#475569', '📊 Compliance & Auditor'),
            'ALL_FAMILIES': ('#9333ea', '👑 Full Administrator'),
        }
        color, label = colors.get(obj.mission_role, ('#475569', obj.get_mission_role_display()))
        return format_html('<span style="background: {}; color: white; padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 11px;">{}</span>', color, label)
    mission_badge.short_description = "Mission Role"

    def status_badge(self, obj):
        if obj.status == OperatorStatus.ACTIVE and obj.is_active:
            return format_html('<span style="background: #166534; color: #86efac; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🟢 Active</span>')
        elif obj.status == OperatorStatus.SUSPENDED or not obj.is_active:
            return format_html('<span style="background: #991b1b; color: #fca5a5; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🔴 Suspended</span>')
        return format_html('<span style="background: #854d0e; color: #fef08a; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">🟡 On Leave</span>')
    status_badge.short_description = "Status"

    def login_account_status(self, obj):
        if obj.linked_user:
            state = "🟢 Enabled" if obj.linked_user.is_active else "🔴 Locked"
            return format_html('<span style="font-size: 12px; font-weight: bold;">User: @{} ({})</span>', obj.linked_user.username, state)
        return format_html('<span style="color: #dc2626; font-size: 12px;">⚠️ No User Account</span>')
    login_account_status.short_description = "Auth Account"

    def view_audit_trail_link(self, obj):
        try:
            from django.urls import reverse
            url = reverse('admin:monitoring_operatoractionlog_changelist') + f'?q={obj.username}'
        except Exception:
            url = f'/{getattr(settings, "ADMIN_URL_PATH", "portal-vault-8f2a9c37/")}monitoring/operatoractionlog/?q={obj.username}'
        return format_html(
            '<a href="{}" style="background: #0284c7; color: white; padding: 3px 7px; border-radius: 4px; text-decoration: none; font-size: 11px; font-weight: bold;">🔍 View Changes</a>',
            url
        )
    view_audit_trail_link.short_description = "Audit Trail"

    def save_model(self, request, obj, form, change):
        user = obj.linked_user
        if not user:
            user = User.objects.filter(username=obj.username).first()
            if not user:
                user = User(username=obj.username)

        user.email = obj.email
        user.first_name = obj.full_name
        user.is_staff = True
        user.is_active = (obj.status == OperatorStatus.ACTIVE and obj.is_active)

        raw_pass = form.cleaned_data.get('login_password')
        if raw_pass:
            user.set_password(raw_pass)
        elif not user.password:
            default_p = "SofizStaff2026!#"
            user.set_password(default_p)
            self.message_user(request, f"Generated initial login password '{default_p}' for @{obj.username}.", level='INFO')

        user.save()

        RBACService.assign_mission_role(user, obj.mission_role)
        obj.linked_user = user

        super().save_model(request, obj, form, change)

    @admin.action(description="🟢 Activate Operators (Enable Login Access)")
    def activate_operators_action(self, request, queryset):
        for op in queryset:
            op.status = OperatorStatus.ACTIVE
            op.is_active = True
            op.save(update_fields=['status', 'is_active'])
            if op.linked_user:
                op.linked_user.is_active = True
                op.linked_user.save(update_fields=['is_active'])
        self.message_user(request, f"Activated {queryset.count()} operator(s) and restored system login.")

    @admin.action(description="🔴 Suspend Operators (Revoke Login Access)")
    def suspend_operators_action(self, request, queryset):
        for op in queryset:
            op.status = OperatorStatus.SUSPENDED
            op.is_active = False
            op.save(update_fields=['status', 'is_active'])
            if op.linked_user:
                op.linked_user.is_active = False
                op.linked_user.save(update_fields=['is_active'])
        self.message_user(request, f"Suspended {queryset.count()} operator(s) and immediately revoked system login.")

    @admin.action(description="🔑 Reset Password to Temporary Password")
    def reset_password_action(self, request, queryset):
        import secrets
        for op in queryset:
            new_pass = f"Pass-{secrets.token_hex(4).upper()}!#"
            if op.linked_user:
                op.linked_user.set_password(new_pass)
                op.linked_user.save()
                self.message_user(request, f"Password for @{op.username} reset to: {new_pass}")
            else:
                self.message_user(request, f"Cannot reset password for {op.full_name}: No linked user.", level='ERROR')

    @admin.action(description="🛡️ Re-sync Role Permissions & Groups")
    def resync_permissions_action(self, request, queryset):
        for op in queryset:
            if op.linked_user:
                RBACService.assign_mission_role(op.linked_user, op.mission_role)
        self.message_user(request, f"Re-synced groups and permissions for {queryset.count()} operator(s).")


@admin.register(OperatorActionLog)
class OperatorActionLogAdmin(admin.ModelAdmin):
    list_display = (
        'timestamp',
        'operator_badge',
        'action_badge',
        'target_model',
        'object_repr',
        'changes_summary_preview',
        'ip_address',
    )
    list_filter = ('action_type', 'operator_family', 'target_model', 'timestamp')
    search_fields = ('operator_username', 'object_repr', 'changes_summary', 'ip_address')
    readonly_fields = [f.name for f in OperatorActionLog._meta.fields]
    ordering = ['-timestamp']

    def operator_badge(self, obj):
        colors = {
            'GAME_OPERATOR': '#7c3aed',
            'FACTURE_OPERATOR': '#0284c7',
            'ESIM_OPERATOR': '#059669',
            'TREASURY_OFFICER': '#b45309',
            'AUDITOR': '#475569',
            'ALL_FAMILIES': '#9333ea',
        }
        bg = colors.get(obj.operator_family, '#334155')
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 11px;">@{}</span>',
            bg, obj.operator_username
        )
    operator_badge.short_description = "Staff Operator"

    def action_badge(self, obj):
        colors = {
            'CREATE': ('#166534', '#86efac', '🟢 CREATE'),
            'UPDATE': ('#1e3a8a', '#93c5fd', '🔵 UPDATE'),
            'DELETE': ('#991b1b', '#fca5a5', '🔴 DELETE'),
            'ACTION_EXECUTE': ('#78350f', '#fde047', '⚡ EXECUTE'),
        }
        bg, text, label = colors.get(obj.action_type, ('#334155', '#ffffff', obj.action_type))
        return format_html(
            '<span style="background: {}; color: {}; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">{}</span>',
            bg, text, label
        )
    action_badge.short_description = "Action"

    def changes_summary_preview(self, obj):
        summary = (obj.changes_summary or '').strip()
        first_line = summary.split('\n')[0]
        if len(first_line) > 80:
            first_line = first_line[:77] + '...'
        return format_html('<span style="font-family: monospace; font-size: 12px;">{}</span>', first_line)
    changes_summary_preview.short_description = "Changes Diff"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ==============================================================================
#  🛡️ 9. ACCESS CONTROL & AUDIT LOGS
# ==============================================================================
@admin.register(LoginAuditLog)
class LoginAuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'username', 'ip_address', 'status_badge', 'user_agent_short')
    list_filter = ('is_success', 'timestamp')
    search_fields = ('username', 'ip_address')
    readonly_fields = [f.name for f in LoginAuditLog._meta.fields]

    def status_badge(self, obj):
        if obj.is_success:
            return format_html('<span style="color: #16a34a; font-weight: bold;">🟢 Success</span>')
        return format_html('<span style="color: #dc2626; font-weight: bold;">🔴 Failed ({})</span>', obj.failure_reason or 'Auth Error')
    status_badge.short_description = "Status"

    def user_agent_short(self, obj):
        ua = obj.user_agent or ''
        return ua[:40] + '...' if len(ua) > 40 else ua
    user_agent_short.short_description = "User Agent"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Re-register User with Institutional Group Badges
admin.site.unregister(User)


@admin.register(User)
class InstitutionalUserAdmin(BaseUserAdmin):
    list_display = (
        'username',
        'email',
        'first_name',
        'is_staff',
        'is_superuser',
        'assigned_role_name',
        'is_active',
    )
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    actions = [
        'assign_treasury_role',
        'assign_p2p_role',
        'assign_utility_role',
        'assign_auditor_role',
    ]

    def assigned_role_name(self, obj):
        group = obj.groups.first()
        return group.name if group else "Default Staff"
    assigned_role_name.short_description = "Role / Group"

    @admin.action(description="🛡️ Assign Role: Treasury Officer")
    def assign_treasury_role(self, request, queryset):
        g, _ = Group.objects.get_or_create(name='Fintech Treasury Officer')
        for u in queryset:
            u.groups.clear()
            u.groups.add(g)
        self.message_user(request, f"Assigned Fintech Treasury Officer role to {queryset.count()} user(s).")

    @admin.action(description="🛒 Assign Role: P2P & Procurement Officer")
    def assign_p2p_role(self, request, queryset):
        g, _ = Group.objects.get_or_create(name='P2P & Procurement Officer')
        for u in queryset:
            u.groups.clear()
            u.groups.add(g)
        self.message_user(request, f"Assigned P2P & Procurement Officer role to {queryset.count()} user(s).")

    @admin.action(description="⚡ Assign Role: Utility Operations Agent")
    def assign_utility_role(self, request, queryset):
        g, _ = Group.objects.get_or_create(name='Utility Operations Agent')
        for u in queryset:
            u.groups.clear()
            u.groups.add(g)
        self.message_user(request, f"Assigned Utility Operations Agent role to {queryset.count()} user(s).")

    @admin.action(description="📊 Assign Role: Compliance & Financial Auditor")
    def assign_auditor_role(self, request, queryset):
        g, _ = Group.objects.get_or_create(name='Compliance & Financial Auditor')
        for u in queryset:
            u.groups.clear()
            u.groups.add(g)
        self.message_user(request, f"Assigned Compliance & Financial Auditor role to {queryset.count()} user(s).")


# ==============================================================================
#  IDOOM (ALGÉRIE TÉLÉCOM) OPERATIONS & AUDIT ADMIN
# ==============================================================================

@admin.register(IdoomBatchRefill)
class IdoomBatchRefillAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        'batch_reference',
        'total_cards_count',
        'formatted_face_value',
        'formatted_cost',
        'formatted_profit',
        'executed_by',
        'created_at',
    )
    search_fields = ('batch_reference', 'uploaded_file_name')
    list_filter = ('created_at',)
    readonly_fields = ('created_at',)

    def formatted_face_value(self, obj):
        val = obj.total_face_value_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7;">{:,.2f} DZD</span>', val)
    formatted_face_value.short_description = "Face Value"

    def formatted_cost(self, obj):
        val = obj.total_cost_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #dc2626;">{:,.2f} DZD</span>', val)
    formatted_cost.short_description = "Procurement Cost"

    def formatted_profit(self, obj):
        val = obj.expected_profit_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #16a34a;">{:,.2f} DZD</span>', val)
    formatted_profit.short_description = "Segregated Profit"


@admin.register(IdoomRefundRecord)
class IdoomRefundRecordAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        'refund_reference',
        'epay_transaction_id',
        'client_phone_or_account',
        'formatted_amount',
        'formatted_reversed_profit',
        'reason',
        'executed_by',
        'created_at',
    )
    search_fields = ('refund_reference', 'epay_transaction_id', 'client_phone_or_account')
    list_filter = ('reason', 'created_at')
    readonly_fields = ('created_at',)

    def formatted_amount(self, obj):
        val = obj.denomination_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #dc2626;">{:,.2f} DZD</span>', val)
    formatted_amount.short_description = "Refunded Face Value"

    def formatted_reversed_profit(self, obj):
        val = obj.reversed_profit_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #e11d48;">-{:,.2f} DZD</span>', val)
    formatted_reversed_profit.short_description = "Reversed Profit"


from .models import XLMLiquidityFundingRecord

@admin.register(XLMLiquidityFundingRecord)
class XLMLiquidityFundingRecordAdmin(InstitutionalAuditAdminMixin, admin.ModelAdmin):
    list_display = (
        'cycle_reference',
        'stage_badge',
        'formatted_amount',
        'receipt_reference',
        'usdt_acquired',
        'xlm_acquired',
        'on_chain_badge',
        'created_at',
    )
    list_filter = ('stage', 'on_chain_verified', 'created_at')
    search_fields = ('cycle_reference', 'receipt_reference', 'p2p_order_id', 'stellar_tx_hash')
    readonly_fields = ('created_at', 'updated_at', 'on_chain_verified_at')

    def stage_badge(self, obj):
        colors = {
            'STAGE_1_BARIDIMOB': ('#1e3a8a', '#93c5fd', '1. P2P Order'),
            'STAGE_2_CONVERT': ('#78350f', '#fde047', '2. USDT->XLM'),
            'STAGE_3_WITHDRAW': ('#4c1d95', '#c4b5fd', '3. Withdrawing'),
            'STAGE_4_COMPLETED': ('#14532d', '#86efac', '4. Completed'),
            'CANCELLED': ('#7f1d1d', '#fca5a5', 'Cancelled'),
        }
        bg, text, label = colors.get(obj.stage, ('#334155', '#ffffff', obj.stage))
        return format_html(
            '<span style="background: {}; color: {}; font-weight: bold; padding: 3px 8px; border-radius: 6px; font-size: 11px;">{}</span>',
            bg, text, label
        )
    stage_badge.short_description = "Stage"

    def on_chain_badge(self, obj):
        if obj.on_chain_verified:
            return format_html('<span style="color: #16a34a; font-weight: bold;">✓ Confirmed Ledger #{}</span>', obj.stellar_ledger_sequence or 'Live')
        return format_html('<span style="color: #94a3b8;">Pending Blockchain</span>')
    on_chain_badge.short_description = "Horizon Consensus"

    def formatted_amount(self, obj):
        val = obj.amount_dzd or Decimal("0.00")
        return format_html('<span style="font-family: monospace; font-weight: bold; color: #0284c7;">{:,.2f} DZD</span>', val)
    formatted_amount.short_description = "DZD Outflow"


