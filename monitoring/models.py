import os
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


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


class WalletFamily(models.TextChoices):
    GAME = 'GAME', 'Game Family (Gaming & Top-Ups)'
    FACTURE = 'FACTURE', 'Facture Family (Bills & Utilities)'
    ESIM = 'ESIM', 'eSIM Family (eSIM & Telecom)'
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
    TREASURY = 'TREASURY', 'Central Treasury Reserve (Stellar DZT)'
    ALL = 'ALL', 'All Sub-Systems (Universal Authorized)'


class BinanceVerificationStatus(models.TextChoices):
    UNVERIFIED = 'UNVERIFIED', 'Unverified'
    VERIFIED_MATCH = 'VERIFIED_MATCH', 'Verified (Amount Matches)'
    AMOUNT_MISMATCH = 'AMOUNT_MISMATCH', 'Mismatch (Wrong Amount)'
    NOT_FOUND = 'NOT_FOUND', 'Not Found / Invalid Hash'


class WithdrawalType(models.TextChoices):
    SUPPLIER_FUNDING = 'SUPPLIER_FUNDING', 'Supplier Account Funding (Purchasing G2Bulk Balance)'
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
    g2bulk_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="G2Bulk API Key")
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
    epay_api_key = models.CharField(max_length=255, default="sk_sofizadmin_live_52041594509c51cd5cda405b244d9b703e684225473e63164ab614c681de7779", verbose_name="Epay API Key (X-API-KEY)")
    binance_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="Binance API Key")
    binance_api_secret = models.CharField(max_length=255, blank=True, null=True, verbose_name="Binance API Secret")
    binance_merchant_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Binance Merchant ID / Pay ID")
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
    baridimob_secret_token = models.CharField(
        max_length=255,
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
    secret_seed = models.CharField(max_length=100, blank=True, null=True, verbose_name="Stellar Secret Seed (S...)")
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
            settings = MonitoringGlobalSettings.get_settings()
            rate = settings.usd_to_dzd_exchange_rate
        self.balance_dzd_equivalent = (self.balance_usd * Decimal(str(rate))).quantize(Decimal("0.01"))


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
    sender_rip = models.CharField(max_length=50, blank=True, null=True, verbose_name="Sender RIP")
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
    receipt_file = models.FileField(upload_to='receipts/%Y/%m/', verbose_name="BaridiMob Receipt File (PDF or Image)")
    reference = models.CharField(max_length=100, unique=True, null=True, blank=True, db_index=True, verbose_name="Transaction Reference / N° Transaction")
    file_hash = models.CharField(max_length=64, unique=True, null=True, blank=True, db_index=True, verbose_name="SHA256 File Hash")
    amount_dzd = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True, verbose_name="Receipt Amount (DZD / DZT)")
    fee_dzd = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("50.00"), blank=True, verbose_name="BaridiMob Fee (DZD)")
    sender_rip = models.CharField(max_length=50, blank=True, null=True, verbose_name="Sender RIP")
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



