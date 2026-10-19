import os
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User
from core.encryption import EncryptedCharField, EncryptedTextField


# ==============================================================================
# ENUM CHOICES (Django 4+ TextChoices for Enterprise Type Safety)
# ==============================================================================

class WalletCategory(models.TextChoices):
    GAMING = 'GAMING', 'Gaming Collection (Free Fire, PUBG, Games, Apps)'
    UTILITY = 'UTILITY', 'Utility Bills & Telecom (Sonelgaz, ADE, AT, eSIM)'
    TREASURY = 'TREASURY', 'Central Treasury & Gas'
    SWEEP_VAULT = 'SWEEP_VAULT', 'Daily Sweep Vault'
    PROFIT_VAULT = 'PROFIT_VAULT', 'Profit Reserve Vault'


class OperationalFamily(models.TextChoices):
    GAME = 'GAME', 'Game Family (Gaming & Top-Ups)'
    FACTURE = 'FACTURE', 'Facture Family (Bills & Utilities)'
    ESIM = 'ESIM', 'eSIM Family (eSIM & Telecom)'
    IDOOM = 'IDOOM', 'Idoom Family (Algérie Télécom)'


class WalletFamily(models.TextChoices):
    GAME = 'GAME', 'Game Family (Gaming & Top-Ups)'
    FACTURE = 'FACTURE', 'Facture Family (Bills & Utilities)'
    ESIM = 'ESIM', 'eSIM Family (eSIM & Telecom)'
    IDOOM = 'IDOOM', 'Idoom Family (Algérie Télécom)'
    TREASURY = 'TREASURY', 'Treasury Family (Central Vaults)'


class WalletRole(models.TextChoices):
    COLLECTION = 'COLLECTION', 'Collection / Normal (Receiving)'
    WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal / Settlement (Outflow)'
    PROFIT = 'PROFIT', 'Profit Reserve (Segregated Net Profit)'
    VAULT = 'VAULT', 'Central Treasury Master Vault'


class SweepType(models.TextChoices):
    PROFIT_TRANSFER = 'PROFIT_TRANSFER', 'Profit Allocation Transfer'
    SWEEP_TRANSFER = 'SWEEP_TRANSFER', 'Daily Sweep Balance Transfer'
    MANUAL_SWEEP = 'MANUAL_SWEEP', 'Manual Sweep Transfer'
    WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal Outflow (Direct Deduction)'


class SweepStatus(models.TextChoices):
    SUCCESS = 'SUCCESS', 'Success'
    FAILED = 'FAILED', 'Failed'
    ABORTED_DISCREPANCY = 'ABORTED_DISCREPANCY', 'Aborted (Discrepancy Detected)'


class SupplierProvider(models.TextChoices):
    G2BULK = 'G2BULK', 'G2Bulk (Official Gaming Provider)'


class SubSystemType(models.TextChoices):
    GAMING = 'GAMING', 'Gaming Working Capital (G2Bulk Supplier)'
    UTILITY = 'UTILITY', 'Utility Bills Working Capital (BaridiMob)'
    ESIM = 'ESIM', 'eSIM & Telecom Working Capital'
    IDOOM = 'IDOOM', 'Idoom Working Capital & Vouchers'
    TREASURY = 'TREASURY', 'Central Treasury Reserve (Stellar DZT)'
    ALL = 'ALL', 'All Sub-Systems (Universal Authorized)'


class BinanceVerificationStatus(models.TextChoices):
    UNVERIFIED = 'UNVERIFIED', 'Unverified'
    VERIFIED_MATCH = 'VERIFIED_MATCH', 'Verified (Amount Matches)'
    AMOUNT_MISMATCH = 'AMOUNT_MISMATCH', 'Mismatch (Wrong Amount)'
    NOT_FOUND = 'NOT_FOUND', 'Not Found / Invalid Hash'


class WithdrawalType(models.TextChoices):
    SUPPLIER_FUNDING = 'SUPPLIER_FUNDING', 'Supplier Account Funding (Purchasing G2Bulk Balance)'
    LIQUIDITY_REFILL = 'LIQUIDITY_REFILL', 'Operational Liquidity Refill (eSIM / Gaming Procurement)'
    PROFIT_WITHDRAWAL = 'PROFIT_WITHDRAWAL', 'Profit / Capital Withdrawal (Owner Payout)'
    LIQUIDITY_TRANSFER = 'LIQUIDITY_TRANSFER', 'Internal Liquidity Transfer'
    OTHER = 'OTHER', 'Other Outflow / Withdrawal'


class WithdrawalPurpose(models.TextChoices):
    """
    Confined institutional purpose choices for fund outflows & supplier funding.
    Includes standardized audit notes for zero-discrepancy financial tracking.
    """
    G2BULK_P2P = 'G2BULK_P2P', 'G2Bulk Wholesale Balance Funding (Binance P2P)'
    G2BULK_DIRECT = 'G2BULK_DIRECT', 'G2Bulk Wholesale Direct Balance Top-Up'
    G2BULK_EMERGENCY = 'G2BULK_EMERGENCY', 'G2Bulk Emergency Liquidity Injection'
    GAMING_PROFIT_PAYOUT = 'GAMING_PROFIT_PAYOUT', 'Gaming Net Profit Distribution (Owner Payout)'
    BARIDIMOB_UTILITY_RECHARGE = 'BARIDIMOB_UTILITY_RECHARGE', 'BaridiMob Utility Account Liquidity Injection (Sihaam31)'
    SONELGAZ_SETTLEMENT = 'SONELGAZ_SETTLEMENT', 'Sonelgaz Settlement Balance Allocation'
    ADE_SETTLEMENT = 'ADE_SETTLEMENT', 'ADE Water Settlement Balance Allocation'
    AT_SETTLEMENT = 'AT_SETTLEMENT', 'Algérie Télécom Settlement Balance Allocation'
    ESIM_REFILL = 'ESIM_REFILL', 'eSIM & Telecom Balance Refill (Airalo / Telecom Partner)'
    IDOOM_STOCK_REFILL = 'IDOOM_STOCK_REFILL', 'Idoom Vouchers & Inventory Procurement Refill'
    TREASURY_ALLOCATION = 'TREASURY_ALLOCATION', 'Internal Treasury Liquidity Allocation'
    OWNER_DIVIDEND = 'OWNER_DIVIDEND', 'Owner Capital & Profit Dividend'
    OTHER = 'OTHER', 'Other Confined Outflow'

    @classmethod
    def get_default_notes(cls, code: str) -> str:
        """Standardized institutional audit notes and accounting descriptions for each purpose"""
        notes_mapping = {
            cls.G2BULK_P2P: "Acquiring USDT via BaridiMob P2P on Binance to fund official G2Bulk wholesale balance for gaming top-ups.",
            cls.G2BULK_DIRECT: "Direct institutional crypto/wire transfer to G2Bulk supplier account to replenish wholesale gaming inventory.",
            cls.G2BULK_EMERGENCY: "Immediate rapid-fill liquidity injection to G2Bulk supplier balance to prevent customer gamer order disruptions.",
            cls.GAMING_PROFIT_PAYOUT: "Audited distribution of accrued net profits generated from gamer top-up sales (owner capital withdrawal).",
            cls.BARIDIMOB_UTILITY_RECHARGE: "Recharging BaridiMob postal card (Sihaam31) to settle customer Sonelgaz, ADE, and Algérie Télécom bills.",
            cls.SONELGAZ_SETTLEMENT: "Batch settlement allocation for customer electricity and gas invoices on Sonelgaz ELIT electronic gateway.",
            cls.ADE_SETTLEMENT: "Batch settlement allocation for water utility bills via Algérienne Des Eaux payment portal.",
            cls.AT_SETTLEMENT: "Batch settlement allocation for Internet ADSL/Fibre and fixed telephone bills via Algérie Télécom portal.",
            cls.ESIM_REFILL: "Replenishing operational funds for Airalo eSIM data packages procurement and international roaming distribution.",
            cls.IDOOM_STOCK_REFILL: "Procurement replenishment of Idoom ADSL/Fibre/4G LTE vouchers and allocation to Big Wallet with profit segregation.",
            cls.TREASURY_ALLOCATION: "Internal treasury capital transfer to replenish operational gaming vaults and collection pools.",
            cls.OWNER_DIVIDEND: "Audited distribution of verified business profits and dividends to institutional owner bank accounts.",
            cls.OTHER: "Documented institutional fund outflow with verified audit rationale.",
        }
        return notes_mapping.get(code, "Institutional financial outflow record.")


class WithdrawalStage(models.TextChoices):
    ALLOCATED = 'ALLOCATED', '1. BaridiMob Dispatched'
    BINANCE_P2P = 'BINANCE_P2P', '2. Binance P2P Acquired'
    COMPLETED = 'COMPLETED', '3. G2Bulk Confirmed & Closed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class FundingCycleStatus(models.TextChoices):
    PENDING_P2P = 'PENDING_P2P', 'In Custody / Pending P2P Purchase'
    P2P_COMPLETED = 'P2P_COMPLETED', 'P2P Purchased (Pending G2Bulk Transfer)'
    G2BULK_FUNDED = 'G2BULK_FUNDED', 'Fully Completed & Verified'
    REJECTED = 'REJECTED', 'Rejected / Invalid'


class ExpenseCategory(models.TextChoices):
    BLOCKCHAIN_FEE = 'BLOCKCHAIN_FEE', 'Stellar Network Fees'
    BARIDIMOB_FEE = 'BARIDIMOB_FEE', 'BaridiMob Transaction & Transfer Fees'
    SERVER_PROXY = 'SERVER_PROXY', 'Server, Hosting & Proxy Infrastructure'
    EXCHANGE_LOSS = 'EXCHANGE_LOSS', 'Currency Exchange & Conversion Loss'
    REVERSAL_REFUND = 'REVERSAL_REFUND', 'Customer Refunds & Reversals'
    OPERATIONAL = 'OPERATIONAL', 'General Operational Expenses'


class UtilityServiceType(models.TextChoices):
    SONELGAZ = 'SONELGAZ', 'Sonelgaz Electricity & Gas (ELIT)'
    ADE = 'ADE', 'Algérienne Des Eaux (Water)'
    ALGERIE_TELECOM = 'ALGERIE_TELECOM', 'Algérie Télécom (Idoom ADSL / Fibre)'


class AuditStatus(models.TextChoices):
    BALANCED = 'BALANCED', '100% Balanced (No Discrepancy)'
    DISCREPANCY_DETECTED = 'DISCREPANCY_DETECTED', 'Discrepancy Detected'


# ==============================================================================
# 1. GLOBAL SYSTEM SETTINGS & ROUTING
# ==============================================================================

class MonitoringGlobalSettings(models.Model):
    """Central configuration for financial monitoring, integrations, and automated wallet routing"""

    class DataSourceMode(models.TextChoices):
        REAL = "REAL", "Real Live Data (Direct External APIs)"
        MOCK = "MOCK", "Mock Simulation Data (Sandbox Practice)"

    data_source_mode = models.CharField(
        max_length=10,
        choices=DataSourceMode.choices,
        default=DataSourceMode.REAL,
        verbose_name="Data Source Operating Mode",
        help_text="Operating mode: Real Live Data strictly enforced."
    )

    g2bulk_api_key = EncryptedCharField(max_length=500, blank=True, null=True, verbose_name="G2Bulk API Key")
    g2bulk_base_url = models.CharField(max_length=255, default="https://api.g2bulk.com/v1", verbose_name="G2Bulk Base URL")
    stellar_horizon_url = models.CharField(max_length=255, default="https://horizon.stellar.org", verbose_name="Stellar Horizon URL")
    dzt_asset_code = models.CharField(max_length=20, default="DZT", verbose_name="DZT Asset Code")
    dzt_asset_issuer = models.CharField(
        max_length=100,
        default="GCAZI7YBLIDJWIVEL7ETNAZGPP3LC24NO6KAOBWZHUERXQ7M5BC52DLV",
        verbose_name="DZT Asset Issuer Address"
    )
    usd_to_dzd_exchange_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("240.00"),
        verbose_name="Exchange Rate (1 USD = X DZT/DZD)"
    )
    epay_api_url = models.CharField(max_length=255, default="https://epay.sofizpay.com/api/operations", verbose_name="Epay API URL")
    epay_api_key = EncryptedCharField(max_length=500, default="sk_sofizadmin_live_52041594509c51cd5cda405b244d9b703e684225473e63164ab614c681de7779", verbose_name="Epay API Key (X-API-KEY)")
    binance_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="Binance API Key")
    binance_api_secret = EncryptedCharField(max_length=500, blank=True, null=True, verbose_name="Binance API Secret")
    binance_merchant_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Binance Merchant ID / Pay ID")
    
    # Bybit Crypto Exchange (eSIM Visa Card Funding)
    bybit_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="Bybit API Key")
    bybit_api_secret = EncryptedCharField(max_length=500, blank=True, null=True, verbose_name="Bybit API Secret")
    bybit_user_id = models.CharField(max_length=100, default="477447830", verbose_name="Bybit User ID")
    
    # Airalo eSIM Provider
    airalo_client_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Airalo Client ID")
    airalo_client_secret = EncryptedCharField(max_length=500, blank=True, null=True, verbose_name="Airalo Client Secret")
    airalo_base_url = models.CharField(max_length=255, default="https://partners-api.airalo.com/v2", verbose_name="Airalo Base URL")
    airalo_min_threshold_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("100.00"),
        verbose_name="Airalo Minimum Balance Threshold (USD $)",
        help_text="Triggers replenishment alert when Airalo available credit balance drops below this amount."
    )
    
    total_live_profits_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Live API Profits (DZT / DZD)")
    total_live_sales_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Live API Sales (DZT / DZD)")
    total_live_orders_count = models.IntegerField(default=0, verbose_name="Live API Completed Orders")
    g2bulk_min_threshold_usd = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        default=Decimal("500.0000"),
        verbose_name="G2Bulk Minimum Balance Threshold (USD $)",
        help_text="Configured by Super Administrator. Triggers replenishment alert if live balance drops below this amount."
    )
    gaming_baridimob_min_threshold_dzd = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("10000.00"),
        verbose_name="Gaming Account Refill Alert Threshold (DZD)",
        help_text="Configured in Django Admin. Triggers replenishment alert when Gaming operational BaridiMob account balance drops below this amount."
    )
    utility_baridimob_min_threshold_dzd = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("10000.00"),
        verbose_name="Factures Account Refill Alert Threshold (DZD)",
        help_text="Configured in Django Admin. Triggers replenishment alert when Factures operational BaridiMob account balance drops below this amount."
    )
    is_auto_sync_enabled = models.BooleanField(default=True, verbose_name="Auto Sync Enabled")
    last_global_sync = models.DateTimeField(null=True, blank=True, verbose_name="Last Global Sync")

    # Automated Funding Wallet Routing
    games_collection_wallet = models.ForeignKey(
        'StellarWallet',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='games_collection_settings',
        verbose_name="Games Collection / Withdrawal Wallet (Source)"
    )
    central_treasury_wallet = models.ForeignKey(
        'StellarWallet',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='central_treasury_settings',
        verbose_name="Central Treasury / Vault Wallet (Destination)"
    )
    # BaridiMob Gateway API Credentials
    baridimob_secret_token = EncryptedCharField(
        max_length=500,
        blank=True,
        null=True,
        default="37dff1b2b1244a4ea3dcbc6b1c0d078e3830fce0f3474ccdaffd5a1d56c729f1",
        verbose_name="BaridiMob Bearer Secret Token"
    )
    baridimob_device_id = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        default="11bf5b37-e0b8-42e0-8dcf-dc8c4aefc000",
        verbose_name="BaridiMob Device ID / UUID"
    )

    # Master Admin API Secret Key
    master_admin_api_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Master Admin Secret API Key"
    )

    # Institutional Working Capital Direct Admin Overrides
    gaming_capital_override = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Gaming Working Capital Override (DZD)",
        help_text="Direct Django Admin control. If set, this amount is used across all gaming equations. If blank, calculated from Gaming Capital entries."
    )
    utility_capital_override = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Utility Working Capital Override (DZD)",
        help_text="Direct Django Admin control. If set, this amount is used across all utility equations. If blank, calculated from Utility Capital entries."
    )

    updated_at = models.DateTimeField(auto_now=True)

    @property
    def effective_gaming_capital(self) -> Decimal:
        from django.apps import apps
        AccountWorkingCapital = apps.get_model('monitoring', 'AccountWorkingCapital')
        acc = AccountWorkingCapital.objects.filter(
            models.Q(family='GAME') | models.Q(account_name__icontains='Game') | models.Q(account_name__icontains='Gaming')
        ).first()
        if acc and acc.capital_amount_dzd > 0:
            return acc.capital_amount_dzd
        if self.gaming_capital_override is not None:
            return self.gaming_capital_override
        CapitalEntry = apps.get_model('monitoring', 'CapitalEntry')
        return (CapitalEntry.objects.filter(category='GAMING').aggregate(total=models.Sum('amount_dzd'))['total'] or Decimal("0.00")).quantize(Decimal("0.01"))

    @property
    def effective_utility_capital(self) -> Decimal:
        from django.apps import apps
        AccountWorkingCapital = apps.get_model('monitoring', 'AccountWorkingCapital')
        acc = AccountWorkingCapital.objects.filter(
            models.Q(family='FACTURE') | models.Q(account_name__icontains='Facture') | models.Q(account_name__icontains='Utility')
        ).first()
        if acc and acc.capital_amount_dzd > 0:
            return acc.capital_amount_dzd
        if self.utility_capital_override is not None:
            return self.utility_capital_override
        CapitalEntry = apps.get_model('monitoring', 'CapitalEntry')
        return (CapitalEntry.objects.filter(category='UTILITY').aggregate(total=models.Sum('amount_dzd'))['total'] or Decimal("0.00")).quantize(Decimal("0.01"))

    @property
    def effective_esim_capital(self) -> Decimal:
        from django.apps import apps
        AccountWorkingCapital = apps.get_model('monitoring', 'AccountWorkingCapital')
        acc = AccountWorkingCapital.objects.filter(
            models.Q(family='ESIM') | models.Q(account_name__icontains='eSIM')
        ).first()
        if acc and acc.capital_amount_dzd > 0:
            return acc.capital_amount_dzd
        return Decimal("0.00")

    @property
    def effective_total_capital(self) -> Decimal:
        return (self.effective_gaming_capital + self.effective_utility_capital + self.effective_esim_capital).quantize(Decimal("0.01"))

    @classmethod
    def get_settings(cls):
        settings, _ = cls.objects.get_or_create(id=1)
        active_key = os.getenv('MASTER_ADMIN_API_KEY') or os.getenv('SOFIZPAY_ADMIN_API_KEY')
        if not active_key:
            from django.conf import settings as dj_settings
            kfile = os.path.join(dj_settings.BASE_DIR, 'MASTER_ADMIN_KEY.txt')
            if os.path.isfile(kfile):
                try:
                    with open(kfile, 'r', encoding='utf-8') as f:
                        active_key = f.read().strip()
                except Exception:
                    pass
        if active_key and settings.epay_api_key != active_key:
            settings.epay_api_key = active_key
            settings.save(update_fields=['epay_api_key'])
        return settings

    @classmethod
    def is_real_mode(cls) -> bool:
        """Returns True if the system is explicitly operating in Real Live Production Data mode"""
        return True

    @classmethod
    def is_mock_mode(cls) -> bool:
        """Mock simulation mode is completely prohibited across the system"""
        return False

    @classmethod
    def apply_data_mode(cls, mode: str = None) -> dict:
        """
        Master Switch: Toggles or sets the system-wide operational mode between REAL and MOCK.
        Triggers immediate synchronization across all institutional services:
        - Bybit V5 API & eSIM Visa Card balances
        - Airalo Partner Wholesale balances
        - G2Bulk Wholesale Supplier balances
        - BaridiMob & ECCP Postal balances
        - Epay Unified Financial Summary & Profits
        - Stellar Horizon Wallets & Liquidity Pools
        - Account Monitoring live time-series snapshots
        """
        settings = cls.get_settings()
        settings.data_source_mode = cls.DataSourceMode.REAL
        settings.last_global_sync = timezone.now()
        settings.save(update_fields=['data_source_mode', 'last_global_sync'])

        is_real = True
        sync_report = {
            "mode": cls.DataSourceMode.REAL,
            "is_real": True,
            "is_mock": False,
            "timestamp": timezone.now().isoformat(),
            "services": {}
        }

        # 1. Bybit V5 Service
        try:
            from .services.bybit_service import BybitService
            bybit_acc = BybitService.sync_account()
            sync_report["services"]["bybit"] = {
                "funding_usdt": float(bybit_acc.funding_balance_usdt),
                "unified_usdt": float(bybit_acc.unified_balance_usdt),
                "total_dzd": float(bybit_acc.balance_dzd_equivalent)
            }
        except Exception as e:
            sync_report["services"]["bybit"] = {"error": str(e)}

        # 2. Airalo Service
        try:
            from .services.airalo_service import AiraloService
            airalo_acc = AiraloService.sync_account()
            sync_report["services"]["airalo"] = {
                "balance_usd": float(airalo_acc.available_balance_usd),
                "balance_dzd": float(airalo_acc.balance_dzd_equivalent)
            }
        except Exception as e:
            sync_report["services"]["airalo"] = {"error": str(e)}

        # 3. G2Bulk Supplier Service
        try:
            from .services.g2bulk_service import G2BulkService
            g2_res = G2BulkService.sync_supplier()
            sync_report["services"]["g2bulk"] = {
                "success": g2_res.get("success", False),
            }
        except Exception as e:
            sync_report["services"]["g2bulk"] = {"error": str(e)}

        # 4. BaridiMob & ECCP Postal Services
        try:
            from .services.baridimob_service import BaridiMobService
            bm_res = BaridiMobService.sync_baridi_balance(account_key='all')
            eccp_g = BaridiMobService.sync_eccp_balance(account_key='game')
            eccp_f = BaridiMobService.sync_eccp_balance(account_key='facture')
            sync_report["services"]["baridimob"] = {
                "success": bool(bm_res.get("success", False)),
                "is_simulation": bool(bm_res.get("is_simulation", False)),
                "game_balance": float(bm_res.get("game", {}).get("balance_dzd", 0) or 0),
                "facture_balance": float(bm_res.get("facture", {}).get("balance_dzd", 0) or 0)
            }
            sync_report["services"]["eccp"] = {
                "game_balance": float(eccp_g.get("eccp_balance_dzd", 0) or 0),
                "facture_balance": float(eccp_f.get("eccp_balance_dzd", 0) or 0)
            }
        except Exception as e:
            sync_report["services"]["baridimob"] = {"error": str(e)}

        # 5. Epay Unified Financial Summary & Profits
        try:
            from .services.epay_service import EpaySyncService
            epay_res = EpaySyncService.sync_financial_summary()
            sync_report["services"]["epay"] = {
                "dollar_rate": float(epay_res.get("dollar_rate", 250.0)),
                "total_profit_dzd": float(epay_res.get("total_profit_dzd", 0.0)),
                "total_sales_dzd": float(epay_res.get("total_sales_dzd", 0.0))
            }
        except Exception as e:
            sync_report["services"]["epay"] = {"error": str(e)}

        # 6. Stellar Horizon & Wallets
        try:
            from .services.stellar_service import StellarService
            StellarService.set_simulation_mode(not is_real)
            stellar_res = StellarService.sync_all_wallets(simulate=(not is_real))
            sync_report["services"]["stellar"] = {"synced_wallets": len(stellar_res)}
        except Exception as e:
            sync_report["services"]["stellar"] = {"error": str(e)}

        # 7. Live Snapshots
        try:
            from .services.account_monitoring_service import AccountMonitoringService
            trigger_name = "MODE_SWITCH_REAL" if is_real else "MODE_SWITCH_MOCK"
            AccountMonitoringService.capture_live_snapshots(trigger=trigger_name)
            sync_report["services"]["snapshots"] = "captured"
        except Exception as e:
            sync_report["services"]["snapshots"] = {"error": str(e)}

        return sync_report

    class Meta:
        verbose_name = "API Keys & Gateway Credentials"
        verbose_name_plural = "API Keys & Gateway Credentials"

    def __str__(self):
        return "Master API Keys & Credentials Vault"


class AccountWorkingCapital(models.Model):
    """
    Dedicated Institutional Working Capital per Operational Family (Game, Facture, eSIM).
    Centrally managed exclusively within Django Admin.
    Central Treasury is a reserve vault and strictly holds zero working capital.
    """
    family = models.CharField(
        max_length=30,
        choices=OperationalFamily.choices,
        default=OperationalFamily.GAME,
        unique=True,
        db_index=True,
        verbose_name="Operational Family"
    )
    account_name = models.CharField(max_length=150, unique=True, verbose_name="Account / Family Label")
    capital_amount_dzd = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Working Capital Amount (DZD)"
    )
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Description / Purpose")
    last_updated_at = models.DateTimeField(auto_now=True, verbose_name="Last Updated")

    class Meta:
        verbose_name = "Account Working Capital"
        verbose_name_plural = "Account Working Capitals"
        ordering = ['family']

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        if str(self.family).upper() == 'TREASURY':
            raise ValidationError("Institutional Rule Violation: Central Treasury does not hold working capital. Only operational families (Game, Facture, eSIM) are permitted.")

    @property
    def subsystem(self):
        mapping = {'GAME': 'GAMING', 'FACTURE': 'UTILITY', 'ESIM': 'ESIM'}
        return mapping.get(self.family, self.family)

    def __str__(self):
        return f"[{self.get_family_display()}] {self.account_name} — {self.capital_amount_dzd:,.2f} DZD"


# ==============================================================================
# 2. STELLAR BLOCKCHAIN WALLETS & SWEEPS
# ==============================================================================

class StellarWallet(models.Model):
    """Institutional Stellar Blockchain Wallets organized by Families and Account Roles"""
    name = models.CharField(max_length=150, verbose_name="Wallet Name / Label")
    family = models.CharField(
        max_length=30,
        choices=WalletFamily.choices,
        default=WalletFamily.GAME,
        db_index=True,
        verbose_name="Wallet Family"
    )
    role = models.CharField(
        max_length=30,
        choices=WalletRole.choices,
        default=WalletRole.COLLECTION,
        db_index=True,
        verbose_name="Wallet Role / Account Type"
    )
    category = models.CharField(
        max_length=30,
        choices=WalletCategory.choices,
        default=WalletCategory.GAMING,
        db_index=True,
        verbose_name="Legacy Category"
    )
    public_address = models.CharField(max_length=100, unique=True, db_index=True, verbose_name="Stellar Public Address (G...)")
    secret_seed = EncryptedCharField(max_length=500, blank=True, null=True, verbose_name="Stellar Secret Seed (S...)")
    dzt_balance = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"), verbose_name="Live DZT Balance")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Is Active")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Last Synced At")
    last_error = models.TextField(null=True, blank=True, verbose_name="Last Sync Error")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stellar Wallet (DZT)"
        verbose_name_plural = "Stellar DZT Wallets"
        ordering = ['family', 'role', '-dzt_balance']
        indexes = [
            models.Index(fields=['family', 'role', 'is_active'], name='idx_wallet_fam_role_active'),
            models.Index(fields=['category', 'is_active'], name='idx_wallet_cat_active'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['family'],
                condition=models.Q(family='TREASURY'),
                name='unique_single_treasury_family'
            ),
            models.UniqueConstraint(
                fields=['role'],
                condition=models.Q(role='VAULT'),
                name='unique_single_master_vault'
            ),
            models.UniqueConstraint(
                fields=['family', 'role'],
                condition=models.Q(role='PROFIT'),
                name='unique_single_family_profit_wallet'
            ),
        ]

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError

        # Strict Institutional Rule 1: Central Treasury Singularity
        if self.family == WalletFamily.TREASURY or self.role == WalletRole.VAULT:
            if self.family == WalletFamily.TREASURY and self.role != WalletRole.VAULT:
                raise ValidationError({
                    'role': f"Wallets belonging to '{WalletFamily.TREASURY.label}' must strictly have role '{WalletRole.VAULT.label}'."
                })
            if self.role == WalletRole.VAULT and self.family != WalletFamily.TREASURY:
                raise ValidationError({
                    'family': f"Wallets with role '{WalletRole.VAULT.label}' must strictly belong to family '{WalletFamily.TREASURY.label}'."
                })

            existing_vault = StellarWallet.objects.filter(
                models.Q(family=WalletFamily.TREASURY) | models.Q(role=WalletRole.VAULT)
            ).exclude(pk=self.pk).first()

            if existing_vault:
                raise ValidationError(
                    f"Strict Institutional Rule: Only ONE Central Treasury Master Vault is permitted in the entire system. "
                    f"Active vault already configured: '{existing_vault.name}' ({existing_vault.public_address})."
                )

        # Strict Institutional Rule 2: Single Dedicated Profit Wallet per Operational Family
        if self.role == WalletRole.PROFIT:
            if self.family == WalletFamily.TREASURY:
                raise ValidationError({
                    'role': "Central Treasury does not take a Profit Wallet role. Profits belong to operational families (Game, Facture, eSIM)."
                })

            existing_profit = StellarWallet.objects.filter(
                family=self.family,
                role=WalletRole.PROFIT
            ).exclude(pk=self.pk).first()
            if existing_profit:
                raise ValidationError({
                    'role': f"Institutional Rule: Family '{self.get_family_display()}' already has a dedicated Profit Wallet ('{existing_profit.name}'). Only ONE Profit Wallet is allowed per family."
                })

    def save(self, *args, **kwargs):
        # Enforce clean validation unless explicitly updating purely live telemetry fields
        update_fields = kwargs.get('update_fields')
        telemetry_fields = {'dzt_balance', 'last_synced_at', 'last_error', 'updated_at'}
        if update_fields is None or not set(update_fields).issubset(telemetry_fields):
            self.clean()

        # Auto-synchronize legacy category to protect all existing queries
        if self.family == WalletFamily.GAME:
            self.category = WalletCategory.GAMING
        elif self.family in [WalletFamily.FACTURE, WalletFamily.ESIM]:
            self.category = WalletCategory.UTILITY
        elif self.family == WalletFamily.TREASURY:
            self.category = WalletCategory.TREASURY
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.get_family_display()} - {self.get_role_display()}] {self.name} | {self.dzt_balance:,.2f} DZT"


class GamingWalletManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(family=WalletFamily.GAME) | models.Q(category=WalletCategory.GAMING)
        )


class GamingWallet(StellarWallet):
    """Proxy model for Gaming Top-up Wallets (Free Fire, PUBG)"""
    objects = GamingWalletManager()

    class Meta:
        proxy = True
        verbose_name = "Gaming Top-Up Wallet"
        verbose_name_plural = "Gaming Collection Wallets (Free Fire, PUBG)"


class SweepVaultWalletManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(category=WalletCategory.SWEEP_VAULT)


class SweepVaultWallet(StellarWallet):
    """Proxy model for Central Daily Sweep Vault Wallet"""
    objects = SweepVaultWalletManager()

    class Meta:
        proxy = True
        verbose_name = "Daily Sweep Vault Wallet"
        verbose_name_plural = "Daily Sweep Vault Wallets"


class ProfitVaultWalletManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(category=WalletCategory.PROFIT_VAULT)


class ProfitVaultWallet(StellarWallet):
    """Proxy model for Profit Reserve Vault Wallet"""
    objects = ProfitVaultWalletManager()

    class Meta:
        proxy = True
        verbose_name = "Profit Reserve Vault Wallet"
        verbose_name_plural = "Profit Reserve Vault Wallets"


class UtilityWalletManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(family=WalletFamily.FACTURE) |
            (models.Q(category=WalletCategory.UTILITY) & ~models.Q(family=WalletFamily.ESIM))
        )


class UtilityWallet(StellarWallet):
    """Proxy model for Utility Bills & Telecom Wallets (Sonelgaz, ADE, AT, eSIM)"""
    objects = UtilityWalletManager()

    class Meta:
        proxy = True
        verbose_name = "Utility & Telecom Wallet"
        verbose_name_plural = "Utility Bills & Telecom Wallets (Sonelgaz, ADE, AT)"


class GamingFinancialStatus(StellarWallet):
    """Proxy model for Gaming Live Balance & Audit Dashboard"""
    objects = GamingWalletManager()

    class Meta:
        proxy = True
        verbose_name = "Gaming Financial Balance & Status"
        verbose_name_plural = "Gaming Live Balance & Status (Audit & Discrepancy)"


class UtilityFinancialStatus(StellarWallet):
    """Proxy model for Factures Live Balance & Audit Dashboard"""
    objects = UtilityWalletManager()

    class Meta:
        proxy = True
        verbose_name = "Factures Financial Balance & Status"
        verbose_name_plural = "Factures Live Balance & Status (Audit & Discrepancy)"


class eSIMWalletManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(family=WalletFamily.ESIM)


class eSIMFinancialStatus(StellarWallet):
    """Proxy model for eSIM Live Balance & Status"""
    objects = eSIMWalletManager()

    class Meta:
        proxy = True
        verbose_name = "eSIM Financial Balance & Status"
        verbose_name_plural = "eSIM Live Balance & Status"


class TreasuryWalletManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(family=WalletFamily.TREASURY) | models.Q(category=WalletCategory.TREASURY)
        )


class TreasuryWallet(StellarWallet):
    """Proxy model for Central Treasury Wallets"""
    objects = TreasuryWalletManager()

    class Meta:
        proxy = True
        verbose_name = "Central Treasury Wallet"
        verbose_name_plural = "Central Treasury Wallets"


class WalletSweepLog(models.Model):
    """Immutable audit log of automated and manual daily sweeps and profit allocations across Stellar wallets"""
    timestamp = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Sweep Timestamp")
    source_wallet = models.ForeignKey(
        StellarWallet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='outgoing_sweeps',
        verbose_name="Source Collection Wallet"
    )
    destination_wallet = models.ForeignKey(
        StellarWallet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incoming_sweeps',
        verbose_name="Destination Vault Wallet"
    )
    amount_dzt = models.DecimalField(max_digits=18, decimal_places=4, verbose_name="Amount (DZT)")
    sweep_type = models.CharField(
        max_length=30,
        choices=SweepType.choices,
        default=SweepType.SWEEP_TRANSFER,
        db_index=True,
        verbose_name="Sweep Type"
    )
    epay_reported_profit = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Epay Daily Profit (DZD)")
    epay_reported_sales = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Epay Daily Sales (DZD)")
    stellar_tx_hash = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Stellar TX Hash")
    status = models.CharField(
        max_length=30,
        choices=SweepStatus.choices,
        default=SweepStatus.SUCCESS,
        db_index=True,
        verbose_name="Status"
    )
    error_details = models.TextField(blank=True, null=True, verbose_name="Error / Audit Details")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Wallet Sweep & Profit Log"
        verbose_name_plural = "Wallet Sweep & Profit Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['status', 'timestamp'], name='idx_sweep_status_time'),
            models.Index(fields=['sweep_type', 'status'], name='idx_sweep_type_status'),
        ]

    def __str__(self):
        src = self.source_wallet.name if self.source_wallet else "Unknown"
        dst = self.destination_wallet.name if self.destination_wallet else "Unknown"
        return f"[{self.get_sweep_type_display()}] {src} -> {dst} | {self.amount_dzt:,.2f} DZT ({self.status})"


# ==============================================================================
# 3. EXTERNAL SUPPLIERS & SETTLEMENT ACCOUNTS
# ==============================================================================

class SupplierAccount(models.Model):
    """External gaming top-up supplier account (G2Bulk)"""
    provider = models.CharField(
        max_length=50,
        choices=SupplierProvider.choices,
        default=SupplierProvider.G2BULK,
        unique=True,
        verbose_name="Provider"
    )
    name = models.CharField(max_length=100, default="Official G2Bulk Account", verbose_name="Account Name")
    api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="API Key")
    balance_usd = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal("0.0000"), verbose_name="Live Balance (USD $)")
    balance_dzd_equivalent = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Equivalent in DZT / DZD")
    min_balance_threshold_usd = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        default=Decimal("500.0000"),
        verbose_name="Minimum Balance Threshold (USD $)",
        help_text="Configured by Super Administrator. If live balance drops below this amount, alerts operator to fund."
    )
    account_username = models.CharField(max_length=150, blank=True, null=True, verbose_name="Account Username")
    account_uid = models.CharField(max_length=100, blank=True, null=True, verbose_name="Account User ID (user_id)")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Is Active")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Last Synced At")
    last_error = models.TextField(null=True, blank=True, verbose_name="Last Sync Error")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Supplier Account"
        verbose_name_plural = "Gaming Supplier Accounts (G2Bulk)"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} | ${self.balance_usd:,.2f} USD ({self.balance_dzd_equivalent:,.2f} DZT)"

    def update_dzd_equivalent(self, rate=None):
        if rate is None:
            try:
                from .services.p2p_rate_service import P2PRateService
                rate = P2PRateService.get_effective_p2p_rate('GAMING')['rate']
            except Exception:
                settings = MonitoringGlobalSettings.get_settings()
                rate = settings.usd_to_dzd_exchange_rate
        self.balance_dzd_equivalent = (self.balance_usd * Decimal(str(rate))).quantize(Decimal("0.01"))


class ReplenishmentWindowStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active Grace Window (Notifications Suppressed)'
    COMPLETED = 'COMPLETED', 'Completed Successfully (Recharge Confirmed)'
    EXPIRED_BALANCED = 'EXPIRED_BALANCED', 'Expired Balanced (No Action Required)'
    EXPIRED_DISCREPANCY = 'EXPIRED_DISCREPANCY', 'Expired with Discrepancy (Alert Dispatched)'
    CANCELLED = 'CANCELLED', 'Manually Cancelled by Operator'


class G2BulkReplenishmentWindow(models.Model):
    """
    Operational Grace Window for G2Bulk Wholesale Replenishment.
    Suppresses automated discrepancy and low-balance alerts for up to 30 hours
    while wholesale funds are in transit across P2P / bank wire / supplier processing.
    Upon window expiration, verifies golden balance and dispatches alerts only if
    a financial defect or discrepancy persists.
    """
    supplier = models.ForeignKey(
        SupplierAccount,
        on_delete=models.CASCADE,
        related_name='replenishment_windows',
        verbose_name="Supplier Account"
    )
    status = models.CharField(
        max_length=30,
        choices=ReplenishmentWindowStatus.choices,
        default=ReplenishmentWindowStatus.ACTIVE,
        db_index=True,
        verbose_name="Status"
    )
    started_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Started At")
    duration_hours = models.PositiveIntegerField(default=30, verbose_name="Max Grace Duration (Hours)")
    expires_at = models.DateTimeField(db_index=True, verbose_name="Grace Expiration Timestamp")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Completed At")
    initiated_by = models.CharField(max_length=150, default="Admin Operator", verbose_name="Initiated By")

    # Financial metrics for audit trail
    initial_balance_usd = models.DecimalField(
        max_digits=15, decimal_places=4, default=Decimal("0.0000"), verbose_name="Initial G2Bulk Balance ($ USD)"
    )
    target_replenish_amount_usd = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, verbose_name="Target Replenishment ($ USD)"
    )
    final_balance_usd = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, verbose_name="Final G2Bulk Balance ($ USD)"
    )

    # Audit outcome after expiration or completion
    final_discrepancy_dzd = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Final Discrepancy (DZD)"
    )
    alert_dispatched = models.BooleanField(default=False, db_index=True, verbose_name="Discrepancy Alert Dispatched")
    alert_dispatched_at = models.DateTimeField(null=True, blank=True, verbose_name="Alert Dispatched At")

    suppressed_alerts_count = models.PositiveIntegerField(default=0, verbose_name="Suppressed Alerts Count")
    notes = models.TextField(blank=True, null=True, verbose_name="Operator Notes")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "G2Bulk Replenishment Grace Window"
        verbose_name_plural = "G2Bulk Replenishment Grace Windows"
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status', 'expires_at'], name='idx_g2b_win_status_exp'),
        ]

    def __str__(self):
        return f"G2Bulk Grace Window #{self.id} [{self.status}] Started: {self.started_at.strftime('%Y-%m-%d %H:%M')}"

    def is_currently_active(self) -> bool:
        if self.status != ReplenishmentWindowStatus.ACTIVE:
            return False
        return timezone.now() < self.expires_at

    @property
    def remaining_seconds(self) -> int:
        if self.status != ReplenishmentWindowStatus.ACTIVE:
            return 0
        now = timezone.now()
        if now >= self.expires_at:
            return 0
        return int((self.expires_at - now).total_seconds())

    @property
    def elapsed_seconds(self) -> int:
        now = timezone.now()
        total = int((now - self.started_at).total_seconds())
        return max(0, total)

    @property
    def progress_pct(self) -> float:
        total = self.duration_hours * 3600
        if total <= 0:
            return 100.0
        pct = (self.elapsed_seconds / total) * 100.0
        return min(100.0, max(0.0, round(pct, 1)))

    @classmethod
    def get_active_window(cls):
        """Returns the currently active G2Bulk replenishment grace window, if any."""
        now = timezone.now()
        return cls.objects.filter(
            status=ReplenishmentWindowStatus.ACTIVE,
            expires_at__gt=now
        ).order_by('-started_at').first()

    @classmethod
    def is_replenishment_active(cls) -> bool:
        """Returns True if a G2Bulk replenishment grace window is actively suppressing alerts."""
        return cls.get_active_window() is not None

    @classmethod
    def record_suppressed_alert(cls, alert_type: str = "DISCREPANCY", amount: Decimal = None):
        """Increments suppression counter and appends audit note to active window."""
        active = cls.get_active_window()
        if active:
            active.suppressed_alerts_count += 1
            now_str = timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')
            amt_str = f" ({amount:,.2f})" if amount is not None else ""
            active.notes = (active.notes or "").strip() + f"\n• [{now_str}] Blocked {alert_type} notification{amt_str} to preserve system continuity."
            active.save(update_fields=['suppressed_alerts_count', 'notes', 'updated_at'])

    @classmethod
    def start_window(cls, supplier=None, duration_hours: int = 30, target_amount_usd: Decimal = None, initiated_by: str = "Admin Operator", notes: str = ""):
        """Starts a new G2Bulk replenishment grace period (capped at 30 hours max)."""
        duration = min(30, max(1, int(duration_hours or 30)))
        now = timezone.now()
        expires_at = now + timezone.timedelta(hours=duration)

        if not supplier:
            supplier = SupplierAccount.objects.filter(provider=SupplierProvider.G2BULK).first()
            if not supplier:
                supplier = SupplierAccount.objects.first()

        # Close any previous active windows cleanly
        cls.objects.filter(status=ReplenishmentWindowStatus.ACTIVE).update(
            status=ReplenishmentWindowStatus.CANCELLED,
            completed_at=now
        )

        initial_bal = supplier.balance_usd if supplier else Decimal("0.0000")

        window = cls.objects.create(
            supplier=supplier,
            status=ReplenishmentWindowStatus.ACTIVE,
            started_at=now,
            duration_hours=duration,
            expires_at=expires_at,
            initiated_by=initiated_by or "Admin Operator",
            initial_balance_usd=initial_bal,
            target_replenish_amount_usd=target_amount_usd,
            notes=notes or f"Started G2Bulk replenishment grace shield for {duration} hours max."
        )
        return window

    @classmethod
    def complete_window(cls, window_id: int = None, final_balance_usd: Decimal = None, notes: str = ""):
        """Completes an active window early when wholesale balance is confirmed."""
        window = cls.objects.filter(id=window_id).first() if window_id else cls.get_active_window()
        if not window:
            return None

        now = timezone.now()
        window.status = ReplenishmentWindowStatus.COMPLETED
        window.completed_at = now
        if final_balance_usd is not None:
            window.final_balance_usd = final_balance_usd
        elif window.supplier:
            window.supplier.refresh_from_db()
            window.final_balance_usd = window.supplier.balance_usd

        if notes:
            window.notes = (window.notes or "").strip() + f"\n• [{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] {notes}"
        window.save()
        return window

    @classmethod
    def evaluate_and_expire_windows(cls):
        """
        Evaluates expired windows. If 30h has elapsed, performs financial audit:
        - If discrepancy or defect remains: dispatches delayed notification!
        - If balanced: marks EXPIRED_BALANCED with zero alarms.
        """
        now = timezone.now()
        expired_qs = cls.objects.filter(
            status=ReplenishmentWindowStatus.ACTIVE,
            expires_at__lte=now
        )

        for win in expired_qs:
            try:
                from monitoring.services.balance_engine import BalanceEngine
                audit_result = BalanceEngine.run_audit(sync_live=True, send_alerts=False)
                discrepancy = audit_result.get('discrepancy', Decimal("0.00"))
                is_balanced = audit_result.get('is_balanced', False)

                win.completed_at = now
                win.final_discrepancy_dzd = discrepancy
                if win.supplier:
                    win.supplier.refresh_from_db()
                    win.final_balance_usd = win.supplier.balance_usd

                if not is_balanced:
                    # An unresolved defect / discrepancy remains after 30h grace period!
                    win.status = ReplenishmentWindowStatus.EXPIRED_DISCREPANCY
                    win.alert_dispatched = True
                    win.alert_dispatched_at = now
                    win.notes = (win.notes or "").strip() + f"\n• [{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] Grace period of {win.duration_hours}h expired with active discrepancy of {discrepancy:,.2f} DZT. Urgent alert dispatched."
                    win.save()

                    # Dispatch delayed critical alert!
                    from monitoring.services.email_alerts import EmailAlertService
                    EmailAlertService.send_discrepancy_alert(discrepancy)
                else:
                    win.status = ReplenishmentWindowStatus.EXPIRED_BALANCED
                    win.notes = (win.notes or "").strip() + f"\n• [{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] Grace period of {win.duration_hours}h expired. Balance is 100% verified and healthy."
                    win.save()

            except Exception as e:
                import logging
                logging.getLogger(__name__).exception(f"Error evaluating expired G2Bulk window #{win.id}: {e}")


class BaridiMobAccount(models.Model):
    """BaridiMob Authorized Settlement Accounts whitelisted for fund transfers & receipts"""
    account_name = models.CharField(max_length=150, default="BaridiMob Main Settlement Account (Sihaam31)", verbose_name="Account Label / Owner")
    rip_number = models.CharField(max_length=50, default="00799999003300065433", db_index=True, verbose_name="Account RIP Number")
    system_type = models.CharField(
        max_length=30,
        choices=SubSystemType.choices,
        default=SubSystemType.GAMING,
        db_index=True,
        verbose_name="Authorized Sub-System"
    )
    account_email = models.CharField(max_length=150, default="Sihaam31", blank=True, verbose_name="Username / Email")
    balance_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Live Balance (DZD)")
    eccp_balance_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="ECCP Postal Balance (DZD)")
    eccp_last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="ECCP Last Synced At")
    min_balance_threshold_dzd = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("10000.00"),
        verbose_name="Minimum Balance Alert Threshold (DZD)",
        help_text="Configured in Django Admin. When balance drops below this amount, a refill warning is raised."
    )
    last_stable_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Last Verified Stable Balance (DZD)")
    is_glitch_quarantined = models.BooleanField(default=False, db_index=True, verbose_name="Algérie Poste Glitch Quarantined")
    quarantined_glitch_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Reported Glitch Balance (DZD)")
    glitch_detected_at = models.DateTimeField(null=True, blank=True, verbose_name="Glitch Detected At")
    glitch_resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="Glitch Resolved At")
    secret_token = models.CharField(max_length=255, default="37dff1b2b1244a4ea3dcbc6b1c0d078e3830fce0f3474ccdaffd5a1d56c729f1", blank=True, verbose_name="Bearer Secret Token")
    devid = models.CharField(max_length=100, default="4d4a7cdb-3f11-4dcf-96ed-ca64f50c4b45", blank=True, verbose_name="Device ID")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Is Active")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Last Synced At")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Authorized Settlement Account"
        verbose_name_plural = "All Authorized Settlement Accounts"
        ordering = ['-balance_dzd']

    def __str__(self):
        return f"[{self.get_system_type_display()}] {self.account_name} (RIP: {self.rip_number})"


class BaridiMobTransaction(models.Model):
    """Permanent archival ledger for BaridiMob account transactions (Inflows, Outflows, Bill Payments)"""
    account = models.ForeignKey(
        BaridiMobAccount,
        on_delete=models.CASCADE,
        related_name='transactions',
        verbose_name="BaridiMob Account"
    )
    tid = models.CharField(max_length=100, db_index=True, verbose_name="Transaction ID (tid)")
    ref_num = models.CharField(max_length=100, db_index=True, blank=True, null=True, verbose_name="Reference Number (refNum)")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Amount (DZD)")
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Postal / Bank Fee Surcharge (DZD)")
    transaction_type = models.CharField(max_length=150, default="GENERIC", db_index=True, verbose_name="Transaction Type / Operation")
    operation_code = models.CharField(max_length=50, blank=True, null=True, db_index=True, verbose_name="Operation Code (Algérie Poste)")
    is_bank_fee = models.BooleanField(default=False, db_index=True, verbose_name="Is Postal / Bank Deduction (Not Client Bill)")
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Description / Statement")
    available_balance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Available Balance (DZD)")
    transaction_date = models.DateTimeField(db_index=True, verbose_name="Transaction Timestamp")
    raw_data = models.JSONField(default=dict, blank=True, verbose_name="Full Epay / BaridiMob Raw Payload")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "BaridiMob Transaction Record"
        verbose_name_plural = "BaridiMob Transaction Records"
        ordering = ['-transaction_date', '-id']
        constraints = [
            models.UniqueConstraint(fields=['account', 'tid'], name='unique_baridimob_account_tid')
        ]

    def __str__(self):
        return f"[{self.account.account_name}] #{self.tid} | {self.amount:+,.2f} DZD ({self.transaction_date.strftime('%Y-%m-%d %H:%M')})"


class GamingBaridiMobManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(models.Q(system_type=SubSystemType.GAMING) | models.Q(system_type=SubSystemType.ALL))


class GamingBaridiMobAccount(BaridiMobAccount):
    """Proxy model for Authorized BaridiMob Accounts accepted for Gaming (G2Bulk P2P)"""
    objects = GamingBaridiMobManager()

    class Meta:
        proxy = True
        verbose_name = "Gaming Accepted Account"
        verbose_name_plural = "Gaming Accepted Accounts (Whitelisted)"


class UtilityBaridiMobManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(models.Q(system_type=SubSystemType.UTILITY) | models.Q(system_type=SubSystemType.ALL))


class UtilityBaridiMobAccount(BaridiMobAccount):
    """Proxy model for Authorized BaridiMob Accounts accepted for Utility Bills & Settlement"""
    objects = UtilityBaridiMobManager()

    class Meta:
        proxy = True
        verbose_name = "Utility Accepted Account"
        verbose_name_plural = "Utility Accepted Accounts (Whitelisted)"


class eSIMBaridiMobManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(models.Q(system_type=SubSystemType.ESIM) | models.Q(system_type=SubSystemType.ALL))


class eSIMBaridiMobAccount(BaridiMobAccount):
    """Proxy model for Authorized BaridiMob Accounts accepted for eSIM & Telecom Operations"""
    objects = eSIMBaridiMobManager()

    class Meta:
        proxy = True
        verbose_name = "eSIM Accepted Account"
        verbose_name_plural = "eSIM Accepted Accounts (Whitelisted)"


class BinanceAccount(models.Model):
    """Binance P2P & Crypto Settlement Account for P2P Purchases & USDT Reserves"""
    account_name = models.CharField(max_length=150, default="Official Binance Corporate Account", verbose_name="Account Label")
    merchant_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Binance Pay ID / Merchant ID")
    balance_usdt = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"), verbose_name="Live Balance (USDT)")
    balance_dzd_equivalent = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Equivalent in DZT / DZD")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Is Active")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Last Synced At")
    last_error = models.TextField(null=True, blank=True, verbose_name="Last Sync Error")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Binance Crypto Account"
        verbose_name_plural = "Binance Crypto Accounts (P2P & USDT)"
        ordering = ['-balance_usdt']

    def __str__(self):
        return f"{self.account_name} | {self.balance_usdt:,.2f} USDT ({self.balance_dzd_equivalent:,.2f} DZT)"

    def update_dzd_equivalent(self, rate=None):
        if rate is None:
            try:
                from .services.p2p_rate_service import P2PRateService
                rate = P2PRateService.get_effective_p2p_rate('GAMING')['rate']
            except Exception:
                settings = MonitoringGlobalSettings.get_settings()
                rate = settings.usd_to_dzd_exchange_rate
        self.balance_dzd_equivalent = (self.balance_usdt * Decimal(str(rate))).quantize(Decimal("0.01"))


# ==============================================================================
# 4. CAPITAL ENTRIES & WITHDRAWALS
# ==============================================================================

class CapitalEntry(models.Model):
    """Capital Inflows and Seed Capital deposits partitioned by Sub-System"""
    title = models.CharField(max_length=200, verbose_name="Capital Deposit Description")
    category = models.CharField(
        max_length=30,
        choices=SubSystemType.choices,
        default=SubSystemType.GAMING,
        db_index=True,
        verbose_name="Sub-System / Purpose"
    )
    amount_dzd = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Deposit Amount (DZD / DZT)")
    deposit_date = models.DateField(default=timezone.localdate, db_index=True, verbose_name="Deposit Date")
    source_account = models.CharField(max_length=150, blank=True, null=True, verbose_name="Source Account (Bank / Cash / Partner)")
    destination_wallet = models.ForeignKey(StellarWallet, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Destination Stellar Wallet")
    destination_supplier = models.ForeignKey(SupplierAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Destination G2Bulk Account")
    destination_baridimob = models.ForeignKey(BaridiMobAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Destination BaridiMob Account")
    binance_txid = models.CharField(max_length=255, blank=True, null=True, db_index=True, verbose_name="Binance TXID / Order ID / Hash")
    binance_verified_amount_usd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Binance Verified Amount ($ USD)")
    binance_verification_status = models.CharField(
        max_length=50,
        default=BinanceVerificationStatus.UNVERIFIED,
        choices=BinanceVerificationStatus.choices,
        db_index=True,
        verbose_name="Binance Verification Status"
    )
    binance_verification_notes = models.TextField(blank=True, null=True, verbose_name="Binance Verification Notes")
    binance_verified_at = models.DateTimeField(null=True, blank=True, verbose_name="Binance Verified At")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes & Details")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Capital Inflow Entry"
        verbose_name_plural = "Capital Inflow Deposits (All)"
        ordering = ['-deposit_date', '-created_at']
        indexes = [
            models.Index(fields=['category', 'deposit_date'], name='idx_capital_cat_date'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount_dzd__gte=Decimal("0.00")),
                name='check_capital_amount_positive'
            )
        ]

    def __str__(self):
        return f"[{self.get_category_display()}] {self.title} | +{self.amount_dzd:,.2f} DZT ({self.deposit_date})"


class GamingCapitalManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(category=SubSystemType.GAMING)


class GamingCapitalEntry(CapitalEntry):
    """Proxy model for Gaming Working Capital Deposits"""
    objects = GamingCapitalManager()

    class Meta:
        proxy = True
        verbose_name = "Gaming Working Capital Deposit"
        verbose_name_plural = "Gaming Working Capital Deposits"


class UtilityCapitalManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(category=SubSystemType.UTILITY)


class UtilityCapitalEntry(CapitalEntry):
    """Proxy model for Utility Bills Working Capital Deposits (BaridiMob)"""
    objects = UtilityCapitalManager()

    class Meta:
        proxy = True
        verbose_name = "Utility Working Capital Deposit"
        verbose_name_plural = "Utility Bills Working Capital Deposits (BaridiMob)"


class eSIMCapitalManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(category=SubSystemType.ESIM)


class eSIMCapitalEntry(CapitalEntry):
    """Proxy model for eSIM & Telecom Working Capital Deposits"""
    objects = eSIMCapitalManager()

    class Meta:
        proxy = True
        verbose_name = "eSIM Working Capital Deposit"
        verbose_name_plural = "eSIM Working Capital Deposits"


class WithdrawalRecord(models.Model):
    """Withdrawal and Fund Outflows (e.g. funding G2Bulk supplier, partner withdrawals, liquidity transfers)"""
    title = models.CharField(max_length=200, verbose_name="Withdrawal Description / Purpose")
    purpose_code = models.CharField(
        max_length=50,
        choices=WithdrawalPurpose.choices,
        default=WithdrawalPurpose.G2BULK_P2P,
        db_index=True,
        verbose_name="Confined Purpose Code"
    )
    system_type = models.CharField(
        max_length=30,
        choices=SubSystemType.choices,
        default=SubSystemType.GAMING,
        db_index=True,
        verbose_name="Sub-System"
    )
    withdrawal_type = models.CharField(
        max_length=30,
        choices=WithdrawalType.choices,
        default=WithdrawalType.SUPPLIER_FUNDING,
        db_index=True,
        verbose_name="Withdrawal Type"
    )
    amount_dzd = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Withdrawn Amount (DZD / DZT)")
    amount_usd_equivalent = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Equivalent in USD ($)")
    withdrawal_date = models.DateField(default=timezone.localdate, db_index=True, verbose_name="Withdrawal Date")
    source_wallet = models.ForeignKey(StellarWallet, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Source Stellar Wallet")
    source_baridimob = models.ForeignKey(BaridiMobAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Source BaridiMob Account")
    destination_supplier = models.ForeignKey(SupplierAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Destination Supplier (G2Bulk)")
    destination_recipient = models.CharField(max_length=150, blank=True, null=True, verbose_name="Recipient / Destination Account")
    binance_txid = models.CharField(max_length=255, blank=True, null=True, db_index=True, verbose_name="Binance TXID / Order ID / Hash")
    binance_verified_amount_usd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Binance Verified Amount ($ USD)")
    binance_verification_status = models.CharField(
        max_length=50,
        default=BinanceVerificationStatus.UNVERIFIED,
        choices=BinanceVerificationStatus.choices,
        db_index=True,
        verbose_name="Binance Verification Status"
    )
    binance_verification_notes = models.TextField(blank=True, null=True, verbose_name="Binance Verification Notes")
    binance_verified_at = models.DateTimeField(null=True, blank=True, verbose_name="Binance Verified At")
    stage = models.CharField(
        max_length=30,
        choices=WithdrawalStage.choices,
        default=WithdrawalStage.ALLOCATED,
        db_index=True,
        verbose_name="Workflow Stage"
    )
    p2p_order_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Binance P2P Order ID")
    p2p_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="P2P Unit Rate (DZD/USDT)")
    binance_pay_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Binance Pay Transaction ID")
    g2bulk_transaction_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="G2Bulk Deposit Transaction ID")
    supplier_pay_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Binance Pay ID / G2Bulk Reference")
    g2bulk_confirmed_increase_usd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="G2Bulk Confirmed Increase ($ USD)")
    binance_fee_usd = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.0000"), verbose_name="Binance Transfer / Network Fee ($ USD)")
    binance_fee_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Binance Transfer Fee Equivalent (DZD)")
    reference = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Transaction Reference / Hash")
    stellar_tx_hash = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Stellar Internal Transfer TX Hash")
    file_hash = models.CharField(max_length=64, null=True, blank=True, db_index=True, verbose_name="SHA256 Receipt Hash")
    receipt_file = models.FileField(upload_to='withdrawal_receipts/%Y/%m/', null=True, blank=True, verbose_name="BaridiMob Receipt PDF")
    funding_receipt = models.ForeignKey(                                                                                                                                                                                                                                                                                                                                                         
        'BaridiMobFundingReceipt',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='linked_withdrawal_records',
        verbose_name="Linked Funding Receipt"
    )
    recipient_rip = models.CharField(max_length=50, blank=True, null=True, verbose_name="Recipient RIP")
    receipt_amount_dzd = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Receipt Verified Amount (DZD)")
    receipt_verified = models.BooleanField(default=False, verbose_name="Receipt Account Verified")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes & Details")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Withdrawal Record"
        verbose_name_plural = "Withdrawals & Fund Outflows"
        ordering = ['-withdrawal_date', '-created_at']
        indexes = [
            models.Index(fields=['system_type', 'withdrawal_type'], name='idx_withdr_sys_type'),
            models.Index(fields=['purpose_code'], name='idx_withdr_purpose'),
            models.Index(fields=['stage'], name='idx_withdr_stage'),
            models.Index(fields=['withdrawal_date'], name='idx_withdr_date'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount_dzd__gte=Decimal("0.00")),
                name='check_withdr_amount_positive'
            )
        ]

    def save(self, *args, **kwargs):
        # Enforce institutional binding to G2Bulk supplier for Gaming or G2Bulk funding
        if not self.destination_supplier:
            if self.system_type == SubSystemType.GAMING or (self.purpose_code and str(self.purpose_code).startswith('G2BULK')):
                g2bulk = SupplierAccount.objects.filter(provider='G2BULK').first()
                if g2bulk:
                    self.destination_supplier = g2bulk

        # Enforce that source_wallet is strictly the subsystem's designated withdrawal wallet
        if not self.source_wallet or self.source_wallet.category in [WalletCategory.TREASURY, WalletCategory.SWEEP_VAULT, WalletCategory.PROFIT_VAULT]:
            settings = MonitoringGlobalSettings.get_settings()
            if self.system_type == SubSystemType.UTILITY:
                self.source_wallet = (
                    StellarWallet.objects.filter(role=WalletRole.WITHDRAWAL, family=WalletFamily.FACTURE, is_active=True).first()
                    or StellarWallet.objects.filter(role=WalletRole.WITHDRAWAL, category=WalletCategory.UTILITY, is_active=True).first()
                    or StellarWallet.objects.filter(category=WalletCategory.UTILITY, is_active=True).first()
                )
            elif self.system_type == SubSystemType.ESIM:
                self.source_wallet = (
                    StellarWallet.objects.filter(role=WalletRole.WITHDRAWAL, family=WalletFamily.ESIM, is_active=True).first()
                )
            else:  # GAMING
                self.source_wallet = (
                    settings.games_collection_wallet
                    or StellarWallet.objects.filter(role=WalletRole.WITHDRAWAL, family=WalletFamily.GAME, is_active=True).first()
                    or StellarWallet.objects.filter(role=WalletRole.WITHDRAWAL, category=WalletCategory.GAMING, is_active=True).first()
                    or StellarWallet.objects.filter(category=WalletCategory.GAMING, is_active=True).first()
                )

        if not self.title and self.purpose_code:
            self.title = self.get_purpose_code_display()
        super().save(*args, **kwargs)

    @property
    def purpose_default_notes(self):
        return WithdrawalPurpose.get_default_notes(self.purpose_code)

    @property
    def receipt_file_url(self):
        if self.receipt_file and hasattr(self.receipt_file, 'url'):
            try:
                return self.receipt_file.url
            except Exception:
                pass
        if self.funding_receipt and self.funding_receipt.receipt_file and hasattr(self.funding_receipt.receipt_file, 'url'):
            try:
                return self.funding_receipt.receipt_file.url
            except Exception:
                pass
        return None

    @property
    def stage_number(self):
        mapping = {
            WithdrawalStage.ALLOCATED: 1,
            WithdrawalStage.BINANCE_P2P: 2,
            WithdrawalStage.COMPLETED: 3,
            WithdrawalStage.CANCELLED: 0,
        }
        return mapping.get(self.stage, 1)

    @property
    def next_action(self):
        if self.stage == WithdrawalStage.ALLOCATED:
            return {
                'key': 'BUY_BINANCE_P2P',
                'title': 'Advance to Stage 2: Binance P2P Purchase',
                'instruction': 'Acquire USDT on Binance P2P with the transferred DZD funds and attach the Binance Order ID & Rate.',
                'target_stage': WithdrawalStage.BINANCE_P2P,
                'target_stage_label': '2. Binance P2P Acquired',
            }
        elif self.stage == WithdrawalStage.BINANCE_P2P:
            return {
                'key': 'CONFIRM_G2BULK_CREDIT',
                'title': 'Advance to Stage 3: G2Bulk Wholesale Credit & Close',
                'instruction': 'Transfer acquired USDT to G2Bulk via Binance Pay and verify supplier credit to finalize & close.',
                'target_stage': WithdrawalStage.COMPLETED,
                'target_stage_label': '3. G2Bulk Confirmed & Closed',
            }
        elif self.stage == WithdrawalStage.COMPLETED:
            return {
                'key': 'DONE',
                'title': 'Workflow Completed',
                'instruction': 'Withdrawal has been fully settled, verified, and audited with zero discrepancy across all 3 stages.',
                'target_stage': None,
                'target_stage_label': '3. G2Bulk Confirmed & Closed',
            }
        return {
            'key': 'NONE',
            'title': 'No Action Required',
            'instruction': '',
            'target_stage': None,
            'target_stage_label': '',
        }

    def __str__(self):
        return f"[{self.get_stage_display()}] {self.title} | -{self.amount_dzd:,.2f} DZT ({self.withdrawal_date})"


class GamingWithdrawalManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(system_type=SubSystemType.GAMING)


class GamingWithdrawalRecord(WithdrawalRecord):
    """Proxy model for Gaming Withdrawals & Supplier Funding (G2Bulk)"""
    objects = GamingWithdrawalManager()

    class Meta:
        proxy = True
        verbose_name = "Gaming Withdrawal / Supplier Funding"
        verbose_name_plural = "Gaming Withdrawals & Supplier Funding (G2Bulk)"


class UtilityWithdrawalManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(system_type=SubSystemType.UTILITY)


class UtilityWithdrawalRecord(WithdrawalRecord):
    """Proxy model for Utility Bills Withdrawals & Fund Outflows"""
    objects = UtilityWithdrawalManager()

    class Meta:
        proxy = True
        verbose_name = "Utility Withdrawal"
        verbose_name_plural = "Utility Withdrawals & Fund Outflows"


class eSIMWithdrawalManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(system_type=SubSystemType.ESIM)


class eSIMWithdrawalRecord(WithdrawalRecord):
    """Proxy model for eSIM & Telecom Withdrawals & Fund Outflows"""
    objects = eSIMWithdrawalManager()

    class Meta:
        proxy = True
        verbose_name = "eSIM Withdrawal"
        verbose_name_plural = "eSIM Withdrawals & Fund Outflows"


class BinanceP2PRecordManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(binance_txid__isnull=False) |
            models.Q(p2p_order_id__isnull=False) |
            models.Q(stage__in=[WithdrawalStage.BINANCE_P2P, WithdrawalStage.COMPLETED])
        )


class BinanceP2POperation(WithdrawalRecord):
    """Proxy model for Binance P2P Purchases & Crypto Operations"""
    objects = BinanceP2PRecordManager()

    class Meta:
        proxy = True
        verbose_name = "Binance P2P Operation"
        verbose_name_plural = "Binance P2P & Crypto Operations"


# ==============================================================================
# 5. AUTOMATED 4-STAGE FUNDING CYCLE (BARIDIMOB -> P2P -> G2BULK)
# ==============================================================================

class BaridiMobFundingReceipt(models.Model):
    """
    Automated BaridiMob Transfer Receipts for G2Bulk Funding.
    Uploaded via PDF or Image, automatically parsed, verified against duplicates,
    executes the internal Stellar transfer from Games Collection to Central Treasury,
    records the 50 DZD BaridiMob fee expense, and tracks Binance P2P and G2Bulk funding.
    """
    receipt_file = models.FileField(upload_to='receipts/%Y/%m/', null=True, blank=True, verbose_name="BaridiMob Receipt File (PDF or Image) (Deprecated - No Files Stored)")
    reference = models.CharField(max_length=100, unique=True, null=True, blank=True, db_index=True, verbose_name="Transaction Reference / N° Transaction")
    file_hash = models.CharField(max_length=64, unique=True, null=True, blank=True, db_index=True, verbose_name="SHA256 File Hash")
    amount_dzd = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True, verbose_name="Receipt Amount (DZD / DZT)")
    fee_dzd = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("50.00"), blank=True, verbose_name="BaridiMob Fee (DZD)")
    recipient_rip = models.CharField(max_length=50, blank=True, null=True, db_index=True, verbose_name="Recipient RIP")
    responsible_person = models.CharField(max_length=150, default="P2P Purchasing Officer", verbose_name="Responsible Person / Agent Name")

    # Internal Stellar Transfer (Stage 1)
    source_wallet = models.ForeignKey(
        StellarWallet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipt_funding_sources',
        verbose_name="Games Source Wallet"
    )
    destination_wallet = models.ForeignKey(
        StellarWallet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipt_funding_destinations',
        verbose_name="Central Treasury / Vault"
    )
    stellar_tx_hash = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Stellar Internal Transfer TX Hash")

    # Linked Operational Fee, Supplier & Withdrawal Records
    expense_record = models.ForeignKey(
        'ExpenseRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='funding_receipts',
        verbose_name="Fee Expense Record (50 DZD)"
    )
    supplier_account = models.ForeignKey(
        SupplierAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='funding_cycles',
        verbose_name="Target Supplier Account (G2Bulk)"
    )
    withdrawal_record = models.ForeignKey(
        WithdrawalRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='funding_receipts',
        verbose_name="Linked Withdrawal Outflow Record"
    )

    # Binance P2P and G2Bulk Tracking (Stages 2, 3, 4)
    binance_order_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Binance P2P / Pay Order ID")
    usdt_acquired = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True, verbose_name="USDT Acquired")
    p2p_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="P2P Exchange Rate")
    usdt_sent_to_g2bulk = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True, verbose_name="USDT Sent to G2Bulk")
    binance_fee_usd = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.0000"), verbose_name="Binance Transfer Fee ($ USD)")
    g2bulk_increase_usd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="G2Bulk Confirmed Increase ($ USD)")

    status = models.CharField(
        max_length=30,
        choices=FundingCycleStatus.choices,
        default=FundingCycleStatus.PENDING_P2P,
        blank=True,
        db_index=True,
        verbose_name="Workflow Status"
    )
    raw_text = models.TextField(blank=True, null=True, verbose_name="Extracted Raw Receipt Text")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes & Audit Details")
    receipt_date = models.DateField(default=timezone.localdate, blank=True, db_index=True, verbose_name="Receipt Date")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "BaridiMob Funding Receipt"
        verbose_name_plural = "BaridiMob Funding Receipts"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'receipt_date'], name='idx_receipt_status_date'),
            models.Index(fields=['created_at'], name='idx_receipt_created'),
            models.Index(fields=['reference'], name='idx_receipt_reference'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount_dzd__isnull=True) | models.Q(amount_dzd__gte=Decimal("0.00")),
                name='check_funding_amount_positive'
            )
        ]

    def __str__(self):
        ref = self.reference or "NO-REF"
        amt = self.amount_dzd or Decimal("0.00")
        return f"Receipt #{ref} | {amt:,.2f} DZD -> {self.responsible_person} ({self.get_status_display()})"


# ==============================================================================
# 6. OPERATIONAL EXPENSES & FEES
# ==============================================================================

class ExpenseRecord(models.Model):
    """Operational expenses, blockchain transaction gas, and BaridiMob fee records"""
    title = models.CharField(max_length=200, verbose_name="Expense Title")
    system_type = models.CharField(
        max_length=30,
        choices=SubSystemType.choices,
        default=SubSystemType.TREASURY,
        db_index=True,
        verbose_name="Sub-System"
    )
    category = models.CharField(
        max_length=50,
        choices=ExpenseCategory.choices,
        default=ExpenseCategory.BLOCKCHAIN_FEE,
        db_index=True,
        verbose_name="Expense Category"
    )
    amount_dzd = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Expense Amount (DZD / DZT)")
    expense_date = models.DateField(default=timezone.localdate, db_index=True, verbose_name="Expense Date")
    related_wallet = models.ForeignKey(StellarWallet, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Related Stellar Wallet")
    related_supplier = models.ForeignKey(SupplierAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Related Supplier Account (G2Bulk)")
    related_baridimob = models.ForeignKey(BaridiMobAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Related BaridiMob Account")
    reference = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Reference / Transaction Hash")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Expense Record"
        verbose_name_plural = "Operational Expenses & Fees"
        ordering = ['-expense_date', '-created_at']
        indexes = [
            models.Index(fields=['system_type', 'category'], name='idx_expense_sys_cat'),
            models.Index(fields=['expense_date'], name='idx_expense_date'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount_dzd__gte=Decimal("0.00")),
                name='check_expense_amount_positive'
            )
        ]

    def __str__(self):
        return f"[{self.get_system_type_display()}] {self.title} | -{self.amount_dzd:,.2f} DZT"


class GamingExpenseManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(system_type=SubSystemType.GAMING)


class GamingExpenseRecord(ExpenseRecord):
    """Proxy model for Gaming Top-Up Operational Expenses & Supplier Fees"""
    objects = GamingExpenseManager()

    class Meta:
        proxy = True
        verbose_name = "Gaming Expense & Fee"
        verbose_name_plural = "Gaming Operational Expenses & Fees"


class UtilityExpenseManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(system_type=SubSystemType.UTILITY)


class UtilityExpenseRecord(ExpenseRecord):
    """Proxy model for Utility Bills & BaridiMob Operational Expenses & Fees"""
    objects = UtilityExpenseManager()

    class Meta:
        proxy = True
        verbose_name = "Utility Bill Expense"
        verbose_name_plural = "Utility Bills Operational Expenses & Fees"


# ==============================================================================
# 7. SALES PROFITS & UTILITY BILL COMMISSIONS
# ==============================================================================

class GameProfitRecord(models.Model):
    """Gaming Top-up sales profits from G2Bulk & Cha7n orders"""
    order_reference = models.CharField(max_length=100, unique=True, db_index=True, verbose_name="Order Reference (UID)")
    game_code = models.CharField(max_length=50, default="freefire", db_index=True, verbose_name="Game Code (freefire, pubgm, mlbb...)")
    game_title = models.CharField(max_length=100, blank=True, null=True, verbose_name="Game Title")
    package_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="Package / Diamond Count")
    player_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Player ID")
    cost_price_usd = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.0000"), verbose_name="Wholesale Cost Price (USD $)")
    cost_price_dzd = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"), verbose_name="Cost Price (DZT / DZD)")
    sale_price_dzd = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"), verbose_name="Customer Sale Price (DZT / DZD)")
    net_profit_dzd = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"), verbose_name="Net Profit (DZT / DZD)")
    is_delivered = models.BooleanField(default=True, db_index=True, verbose_name="Is Delivered")
    order_date = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Order Date")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Gaming Order Profit"
        verbose_name_plural = "Gaming Order Profits (Free Fire, PUBG)"
        ordering = ['-order_date']
        indexes = [
            models.Index(fields=['game_code', 'order_date'], name='idx_profit_game_date'),
            models.Index(fields=['is_delivered'], name='idx_profit_delivered'),
        ]

    def save(self, *args, **kwargs):
        if self.net_profit_dzd == Decimal("0.00") and self.sale_price_dzd > 0:
            self.net_profit_dzd = self.sale_price_dzd - self.cost_price_dzd
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.game_code} - {self.order_reference} | Profit: +{self.net_profit_dzd:,.2f} DZT"


class UtilityBillRecord(models.Model):
    """Utility bill payments and commission records (Sonelgaz, ADE, Algérie Télécom)"""
    service = models.CharField(
        max_length=30,
        choices=UtilityServiceType.choices,
        default=UtilityServiceType.SONELGAZ,
        db_index=True,
        verbose_name="Utility Service"
    )
    bill_reference = models.CharField(max_length=100, unique=True, db_index=True, verbose_name="Bill / Facture Number")
    customer_account = models.CharField(max_length=100, blank=True, null=True, verbose_name="Customer Account / Phone")
    bill_amount_dzd = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Bill Face Amount (DZD)")
    commission_earned_dzd = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"), verbose_name="Commission Earned (DZD)")
    is_settled = models.BooleanField(default=True, db_index=True, verbose_name="Settled & Paid via BaridiMob")
    baridimob_account = models.ForeignKey(BaridiMobAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Settled From BaridiMob")
    payment_date = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Payment Date")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Utility Bill Record"
        verbose_name_plural = "Utility Bills & Telecom Records (Sonelgaz, ADE, AT)"
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['service', 'payment_date'], name='idx_bill_service_date'),
            models.Index(fields=['is_settled'], name='idx_bill_settled'),
        ]

    def __str__(self):
        return f"[{self.get_service_display()}] {self.bill_reference} | {self.bill_amount_dzd:,.2f} DZD"


# ==============================================================================
# 8. FINANCIAL RECONCILIATION & GOLDEN BALANCE AUDIT
# ==============================================================================

class BalanceAuditLog(models.Model):
    """
    Real-time financial audit snapshots and Golden Balance Equation verification:
    Total Current Assets (Stellar + G2Bulk + BaridiMob) + Total Expenses = Total Capital + Total Profits
    """
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Audit Timestamp")
    total_dzt_wallets = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Stellar DZT Wallets Total (DZD)")
    total_g2bulk_dzd = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="G2Bulk Total Equivalent (DZD)")
    total_baridimob_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="BaridiMob Total Working Capital (DZD)")
    total_in_transit_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="In-Transit Funding Refills (DZD)")
    total_assets_dzd = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Total Current Assets (DZT + G2Bulk + BaridiMob + In-Transit)")
    total_expenses_dzd = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Total Expenses & Fees (DZD)")
    
    # Left side = Assets + Expenses
    left_side_total = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Left Side Total (Assets + Expenses)")
    
    total_capital_dzd = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Total Capital Inflow (DZD)")
    total_profits_dzd = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Total Sales Profit (DZD)")
    
    # Right side = Capital + Profits
    right_side_total = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Right Side Total (Capital + Profits)")
    
    # Discrepancy = Left - Right
    discrepancy_dzd = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Discrepancy Amount (DZD)")
    status = models.CharField(
        max_length=30,
        choices=AuditStatus.choices,
        default=AuditStatus.BALANCED,
        db_index=True,
        verbose_name="Audit Status"
    )
    notes = models.TextField(blank=True, null=True, verbose_name="Audit Notes")

    class Meta:
        verbose_name = "Balance Audit Log"
        verbose_name_plural = "Golden Balance Audit Logs"
        ordering = ['-checked_at']
        indexes = [
            models.Index(fields=['status', 'checked_at'], name='idx_audit_status_time'),
        ]

    def __str__(self):
        return f"Audit {self.checked_at.strftime('%Y-%m-%d %H:%M')} | {self.status} (Discrepancy: {self.discrepancy_dzd:,.2f} DZT)"


# ==============================================================================
# 9. AUTHENTICATION & ACCESS AUDIT TRAIL
# ==============================================================================

class LoginAuditLog(models.Model):
    """Institutional audit log of authentication attempts, IP addresses, and security outcomes"""
    username = models.CharField(max_length=150, db_index=True, verbose_name="Username or Email")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Matched User Account")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="Client IP Address")
    user_agent = models.TextField(blank=True, null=True, verbose_name="Client User Agent / Device")
    is_success = models.BooleanField(default=False, db_index=True, verbose_name="Authentication Succeeded")
    failure_reason = models.CharField(max_length=255, blank=True, null=True, verbose_name="Failure Reason")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Attempt Timestamp")

    class Meta:
        verbose_name = "Login Audit Log"
        verbose_name_plural = "Login Audit Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['is_success', 'timestamp'], name='idx_login_status_time'),
            models.Index(fields=['username', 'timestamp'], name='idx_login_user_time'),
        ]

    def __str__(self):
        status_label = "SUCCESS" if self.is_success else f"FAILED ({self.failure_reason})"
        return f"Login [{status_label}] - {self.username} from {self.ip_address} at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"


# ==============================================================================
# 10. EMPLOYEES & OPERATORS (BY MISSION & ROLE)
# ==============================================================================

class OperatorMissionRole(models.TextChoices):
    GAME_OPERATOR = 'GAME_OPERATOR', '🎮 Game Family Operator (Free Fire, PUBG, G2Bulk)'
    FACTURE_OPERATOR = 'FACTURE_OPERATOR', '📄 Facture Family Operator (Sonelgaz, ADE, AT, Sihaam 31)'
    ESIM_OPERATOR = 'ESIM_OPERATOR', '📶 eSIM Family Operator (Telecom & Mobile Data)'
    TREASURY_OFFICER = 'TREASURY_OFFICER', '🏛️ Treasury & P2P Officer (Binance & Vaults)'
    AUDITOR = 'AUDITOR', '📊 Compliance & Financial Auditor (Read-Only)'
    ALL_FAMILIES = 'ALL_FAMILIES', '👑 Full Multi-Family Administrator'


class OperatorStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active (Login Enabled)'
    SUSPENDED = 'SUSPENDED', 'Suspended (Login Revoked)'
    ON_LEAVE = 'ON_LEAVE', 'On Leave (Temporary Inactive)'


class StaffOperator(models.Model):
    """
    Institutional Staff Employees & Operators partitioned by Mission & Department.
    Directly provisioned with a secure login account (User, Username, Password, Role-Based Groups).
    """
    employee_code = models.CharField(max_length=50, unique=True, db_index=True, verbose_name="Employee Code (e.g. EMP-GAM-001)")
    full_name = models.CharField(max_length=150, verbose_name="Employee Full Name")
    username = models.CharField(max_length=150, unique=True, db_index=True, verbose_name="Login Username")
    email = models.EmailField(unique=True, verbose_name="Login Email Address")
    mission_role = models.CharField(
        max_length=50,
        choices=OperatorMissionRole.choices,
        default=OperatorMissionRole.GAME_OPERATOR,
        db_index=True,
        verbose_name="Assigned Mission / Department"
    )
    status = models.CharField(
        max_length=30,
        choices=OperatorStatus.choices,
        default=OperatorStatus.ACTIVE,
        db_index=True,
        verbose_name="Employment Status"
    )
    phone_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="Phone / WhatsApp Contact")
    linked_user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='operator_profile',
        verbose_name="Linked User Account"
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Login Access Allowed")
    last_activity_at = models.DateTimeField(null=True, blank=True, verbose_name="Last System Activity")
    notes = models.TextField(blank=True, null=True, verbose_name="Job Role & Responsibilities")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Staff Employee & Operator"
        verbose_name_plural = "Employees & Operators (By Role)"
        ordering = ['mission_role', 'full_name']

    def __str__(self):
        return f"[{self.get_mission_role_display()}] {self.full_name} (@{self.username})"

    def save(self, *args, **kwargs):
        if not self.employee_code:
            import uuid
            prefix = "EMP-" + (self.mission_role or 'OP')[:3].upper()
            self.employee_code = f"{prefix}-{uuid.uuid4().hex[:5].upper()}"
        super().save(*args, **kwargs)


class OperatorActionLog(models.Model):
    """
    High-fidelity Institutional Audit Trail tracking every change, addition,
    deletion, and critical action executed by staff operators across all modules.
    """
    class ActionType(models.TextChoices):
        CREATE = 'CREATE', '🟢 Create / Addition'
        UPDATE = 'UPDATE', '🔵 Update / Modification'
        DELETE = 'DELETE', '🔴 Delete / Removal'
        ACTION_EXECUTE = 'ACTION_EXECUTE', '⚡ Critical Action Executed'

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Action Timestamp")
    operator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_action_logs',
        verbose_name="Operator User"
    )
    operator_username = models.CharField(max_length=150, db_index=True, verbose_name="Operator Username")
    operator_family = models.CharField(max_length=50, blank=True, null=True, db_index=True, verbose_name="Mission Family")
    action_type = models.CharField(
        max_length=30,
        choices=ActionType.choices,
        default=ActionType.UPDATE,
        db_index=True,
        verbose_name="Action Type"
    )
    target_model = models.CharField(max_length=100, db_index=True, verbose_name="Target Module / Section")
    object_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Object ID")
    object_repr = models.CharField(max_length=255, verbose_name="Target Object")
    changes_summary = models.TextField(verbose_name="Changes Summary & Diff")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="Operator IP Address")
    user_agent = models.TextField(blank=True, null=True, verbose_name="Device / Browser Agent")

    class Meta:
        verbose_name = "Operator Activity & Change Log"
        verbose_name_plural = "Operator Activity & Change Audit Trail"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp', 'operator_username'], name='idx_audit_time_op'),
            models.Index(fields=['action_type', 'target_model'], name='idx_audit_type_mod'),
        ]

    def __str__(self):
        return f"[{self.action_type}] {self.operator_username} on {self.target_model} ({self.object_repr})"


# ==============================================================================
# 11. DEDICATED eSIM MULTI-TENANT ISOLATED INFRASTRUCTURE (Bybit & Airalo)
# ==============================================================================

class BybitAccount(models.Model):
    """Dedicated Bybit Crypto Funding Account for eSIM Visa Card Allocation"""
    account_name = models.CharField(max_length=150, default="Official Bybit Corporate Account", verbose_name="Account Label")
    user_id = models.CharField(max_length=100, default="477447830", verbose_name="Bybit User ID")
    funding_balance_usdt = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"), verbose_name="Funding Wallet Balance (USDT)")
    unified_balance_usdt = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"), verbose_name="Unified Wallet Balance (USDT)")
    balance_dzd_equivalent = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Equivalent in DZT / DZD")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Is Active")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Last Synced At")
    last_error = models.TextField(null=True, blank=True, verbose_name="Last Sync Error")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bybit Crypto Account"
        verbose_name_plural = "Bybit Crypto Accounts (USDT & Visa Card)"
        ordering = ['-funding_balance_usdt']

    def __str__(self):
        return f"{self.account_name} (UID: {self.user_id}) | {self.funding_balance_usdt:,.2f} USDT ({self.balance_dzd_equivalent:,.2f} DZT)"

    def update_dzd_equivalent(self, rate=None):
        if rate is None:
            try:
                from .services.p2p_rate_service import P2PRateService
                rate = P2PRateService.get_effective_p2p_rate('ESIM')['rate']
            except Exception:
                settings = MonitoringGlobalSettings.get_settings()
                rate = settings.usd_to_dzd_exchange_rate
        total_usdt = self.funding_balance_usdt + self.unified_balance_usdt
        self.balance_dzd_equivalent = (total_usdt * Decimal(str(rate))).quantize(Decimal("0.01"))


class AiraloAccount(models.Model):
    """Dedicated Airalo eSIM Wholesale Provider Account for Data Packages"""
    account_name = models.CharField(max_length=150, default="Official Airalo Partner Account", verbose_name="Account Label")
    available_balance_usd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Available Credit Balance ($ USD)")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Is Active")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Last Synced At")
    last_error = models.TextField(null=True, blank=True, verbose_name="Last Sync Error")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Airalo eSIM Account"
        verbose_name_plural = "Airalo eSIM Accounts (Wholesale)"
        ordering = ['-available_balance_usd']

    def __str__(self):
        return f"{self.account_name} | ${self.available_balance_usd:,.2f} USD"

    @property
    def balance_dzd_equivalent(self):
        """Dynamic calculation using actual Binance P2P purchase price"""
        try:
            from .services.p2p_rate_service import P2PRateService
            rate = P2PRateService.get_effective_p2p_rate('ESIM')['rate']
        except Exception:
            settings = MonitoringGlobalSettings.get_settings()
            rate = settings.usd_to_dzd_exchange_rate
        return (self.available_balance_usd * Decimal(str(rate))).quantize(Decimal("0.01"))


class eSIMFundingStage(models.TextChoices):
    BARIDIMOB_DISPATCHED = 'BARIDIMOB_DISPATCHED', '1. BaridiMob Dispatched'
    BINANCE_P2P = 'BINANCE_P2P', '2. Binance P2P Acquired'
    BYBIT_FUNDED = 'BYBIT_FUNDED', '3. Bybit Funded & Visa Card Allocated'
    AIRALO_COMPLETED = 'AIRALO_COMPLETED', '4. Airalo Confirmed & Closed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class eSIMFundingRecord(models.Model):
    """
    Dedicated 4-Stage Replenishment Pipeline for eSIM & Telecom Operations:
    Stage 1: BaridiMob Dispatched (Salah Account)
    Stage 2: Binance P2P Acquired (USDT)
    Stage 3: Bybit Funded & Visa Card Allocated (USDT -> Visa Card)
    Stage 4: Airalo Confirmed & Closed (eSIM Packages Acquired)
    """
    amount_dzd = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Replenishment Amount (DZD)")
    amount_usd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Amount ($ USD)")
    stage = models.CharField(
        max_length=30,
        choices=eSIMFundingStage.choices,
        default=eSIMFundingStage.BARIDIMOB_DISPATCHED,
        db_index=True,
        verbose_name="Workflow Stage"
    )
    # Stage 1: BaridiMob
    source_baridimob = models.ForeignKey(
        BaridiMobAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Source BaridiMob Account (Salah)"
    )
    receipt_file = models.FileField(upload_to='esim_receipts/%Y/%m/', null=True, blank=True, verbose_name="BaridiMob Receipt PDF")
    receipt_reference = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="BaridiMob Receipt Reference")
    receipt_verified = models.BooleanField(default=False, verbose_name="Receipt Verified")

    # Stage 2: Binance P2P
    binance_p2p_order_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Binance P2P Order ID")
    binance_txid = models.CharField(max_length=255, blank=True, null=True, db_index=True, verbose_name="Binance TXID")
    p2p_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="P2P Exchange Rate (DZD/USDT)")
    binance_verified_amount_usdt = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Acquired USDT on Binance")
    binance_verified = models.BooleanField(default=False, verbose_name="Binance P2P Verified")

    # Stage 3: Bybit & Visa Card
    bybit_txid = models.CharField(max_length=255, blank=True, null=True, db_index=True, verbose_name="Bybit TXID / Transfer ID")
    bybit_transfer_amount_usdt = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Transferred USDT to Bybit")
    bybit_verified = models.BooleanField(default=False, verbose_name="Bybit Transfer Verified")
    bybit_verified_at = models.DateTimeField(null=True, blank=True, verbose_name="Bybit Verified At")
    visa_card_last4 = models.CharField(max_length=10, blank=True, null=True, default="Bybit Visa", verbose_name="Visa Card Identifier")

    # Stage 4: Airalo Supplier
    airalo_order_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Airalo Order ID")
    airalo_package_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Airalo Package Code")
    airalo_confirmed_amount_usd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Airalo Confirmed Increase ($ USD)")
    airalo_verified = models.BooleanField(default=False, verbose_name="Airalo Order Verified")

    notes = models.TextField(blank=True, null=True, verbose_name="Notes & Audit Trail")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "eSIM Replenishment Cycle"
        verbose_name_plural = "eSIM Replenishment Cycles (4-Stage)"
        ordering = ['-created_at']

    def __str__(self):
        return f"eSIM #{self.id} | {self.amount_dzd:,.2f} DZD ({self.get_stage_display()})"


class eSIMOrderRecord(models.Model):
    """eSIM package orders and commission / profit records"""
    order_id = models.CharField(max_length=100, unique=True, db_index=True, verbose_name="Order ID / Airalo Order")
    package_id = models.CharField(max_length=100, db_index=True, verbose_name="Package Code")
    package_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="Package Description")
    customer_phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="Customer Phone / User")
    cost_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Cost ($ USD)")
    cost_dzd = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"), verbose_name="Cost (DZD)")
    sale_price_dzd = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"), verbose_name="Sale Price (DZD)")
    net_profit_dzd = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"), verbose_name="Net Profit (DZD)")
    status = models.CharField(max_length=50, default="COMPLETED", db_index=True, verbose_name="Order Status")
    created_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Order Timestamp")

    class Meta:
        verbose_name = "eSIM Order Record"
        verbose_name_plural = "eSIM Order Records"
        ordering = ['-created_at']

    def __str__(self):
        return f"eSIM #{self.order_id} ({self.package_id}) | +{self.net_profit_dzd:,.2f} DZD"


class AccountMonitoringChannel(models.TextChoices):
    G2BULK = "g2bulk", "G2Bulk Wholesale Inventory"
    AIRALO = "airalo", "Airalo eSIM Telecom Wholesale"
    BARIDIMOB_ESIM_QUOTA = "baridimob_esim_quota", "BaridiMob (eSIM Quota)"
    ECCP_ESIM_QUOTA = "eccp_esim_quota", "ECCP (eSIM Quota)"
    BARIDIMOB_GAME_QUOTA = "baridimob_game_quota", "BaridiMob (Gaming Quota)"
    ECCP_GAME_QUOTA = "eccp_game_quota", "ECCP (Gaming Quota)"
    BARIDIMOB_FACTURE = "baridimob_facture", "BaridiMob (Factures Sihaam)"
    ECCP_FACTURE = "eccp_facture", "ECCP (Factures Sihaam)"


class AccountBalanceSnapshot(models.Model):
    """
    Time-series audit record tracking the historical balance of every account channel.
    Maintains previous balance, current balance, net change, causing transaction, and timestamps.
    """
    channel = models.CharField(
        max_length=64,
        choices=AccountMonitoringChannel.choices,
        db_index=True,
        verbose_name="Monitored Account Channel"
    )
    account_label = models.CharField(max_length=150, verbose_name="Account Label / Title")
    activity = models.CharField(max_length=50, db_index=True, verbose_name="Activity (Gaming, eSIM, Facture, Wholesale)")
    source_type = models.CharField(max_length=50, db_index=True, verbose_name="Source Type (BaridiMob, ECCP, G2Bulk, Airalo)")

    # Balances
    current_balance = models.DecimalField(max_digits=18, decimal_places=4, verbose_name="Current Balance (Native)")
    currency = models.CharField(max_length=10, default="DZD", verbose_name="Native Currency")
    current_balance_dzd = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Current Balance (DZD)")
    previous_balance_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Previous Balance (DZD)")
    balance_change_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Net Balance Change (DZD)")

    # Change status & Trigger
    change_type = models.CharField(
        max_length=20,
        choices=[("INCREASE", "Increase"), ("DECREASE", "Decrease"), ("STABLE", "Stable")],
        default="STABLE",
        db_index=True,
        verbose_name="Change Direction"
    )
    trigger_type = models.CharField(
        max_length=50,
        default="PERIODIC_SYNC",
        db_index=True,
        verbose_name="Trigger Mechanism"
    )

    # Linked Transaction Information
    causing_transaction_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, verbose_name="Causing Transaction TID / ID")
    causing_transaction_desc = models.CharField(max_length=255, blank=True, null=True, verbose_name="Causing Transaction Description")
    causing_transaction_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Causing Transaction Amount (DZD)")

    # Timestamps
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Snapshot Recorded Timestamp")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Upstream Sync Timestamp")

    notes = models.TextField(blank=True, null=True, verbose_name="Monitoring Notes")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Additional Snapshot Metadata")

    class Meta:
        verbose_name = "Account Balance Snapshot"
        verbose_name_plural = "Account Balance Snapshots"
        ordering = ["-recorded_at", "-id"]
        indexes = [
            models.Index(fields=["channel", "-recorded_at"], name="idx_acc_snap_chan_time"),
            models.Index(fields=["activity", "-recorded_at"], name="idx_acc_snap_act_time"),
        ]

    def __str__(self):
        return f"[{self.get_channel_display()}] {self.recorded_at.strftime('%Y-%m-%d %H:%M')} | {self.current_balance_dzd:,.2f} DZD (Change: {self.balance_change_dzd:+,.2f} DZD)"


# ==============================================================================
# 11. IDOOM BATCH REFILL & REFUND MODELS
# ==============================================================================

class IdoomBatchRefill(models.Model):
    """
    Audited record for Idoom card stock replenishment batches uploaded by Treasury Officer (Walid).
    Calculates total procurement cost, face value, and segregated profit.
    """
    batch_reference = models.CharField(max_length=64, unique=True, db_index=True, verbose_name="Batch Reference")
    total_cards_count = models.PositiveIntegerField(default=0, verbose_name="Total Cards Count")
    total_face_value_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Total Face Value (DZD)")
    total_cost_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Procurement Cost (DZD)")
    expected_profit_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Expected Profit (DZD)")
    breakdown_json = models.JSONField(default=dict, blank=True, verbose_name="Denominations Breakdown")
    uploaded_file_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Uploaded File Name")
    executed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Executed By")
    withdrawal_record = models.ForeignKey('WithdrawalRecord', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Linked Withdrawal Outflow")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Batch Creation Timestamp")

    class Meta:
        verbose_name = "Idoom Batch Refill Record"
        verbose_name_plural = "Idoom Batch Refill Records"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[Idoom Refill #{self.batch_reference}] {self.total_cards_count} cards | Cost: {self.total_cost_dzd:,.2f} DZD | Profit: {self.expected_profit_dzd:,.2f} DZD"


class IdoomRefundRecord(models.Model):
    """
    Audited record for defective/failed Idoom voucher cards.
    Handles reversal refund to client and rollbacks phantom profit from profit reserve.
    """
    refund_reference = models.CharField(max_length=64, unique=True, db_index=True, verbose_name="Refund Reference")
    epay_transaction_id = models.CharField(max_length=100, db_index=True, verbose_name="Epay Transaction ID")
    client_phone_or_account = models.CharField(max_length=64, blank=True, verbose_name="Customer Account / Phone")
    denomination_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Refunded Amount (DZD)")
    reversed_profit_dzd = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name="Reversed Profit (DZD)")
    reason = models.CharField(max_length=255, default="FAILED_DEFECTIVE_CARD", verbose_name="Refund Rationale")
    executed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Executed By")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Refund Timestamp")

    class Meta:
        verbose_name = "Idoom Defective Card Refund"
        verbose_name_plural = "Idoom Defective Card Refunds"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[Idoom Refund #{self.refund_reference}] TID: {self.epay_transaction_id} | Amount: {self.denomination_dzd:,.2f} DZD"
