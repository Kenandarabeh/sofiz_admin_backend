"""
REST API Serializers for SofizAdmin Monitoring Backend
Designed for consumption by the React + Vite frontend single-page application.
Adheres to strict enterprise financial & API standards.
"""
from rest_framework import serializers
from decimal import Decimal
from django.utils import timezone
from .models import (
    MonitoringGlobalSettings,
    StellarWallet,
    WalletSweepLog,
    SupplierAccount,
    BaridiMobAccount,
    BaridiMobTransaction,
    CapitalEntry,
    WithdrawalRecord,
    LiquidityRetraitRecord,
    BaridiMobFundingReceipt,
    ExpenseRecord,
    GameProfitRecord,
    UtilityBillRecord,
    BalanceAuditLog,
    BybitAccount,
    AiraloAccount,
    eSIMFundingRecord,
    eSIMOrderRecord,
    G2BulkReplenishmentWindow,
    IdoomBatchRefill,
    IdoomRefundRecord,
    IPTVBatchRefill,
    IPTVRefundRecord,
)
from .services.receipt_parser_service import ReceiptParserService
from .services.stellar_sweep_service import StellarSweepService
from .services.stellar_service import StellarService


class MonitoringGlobalSettingsSerializer(serializers.ModelSerializer):
    games_collection_wallet_name = serializers.ReadOnlyField(source='games_collection_wallet.name')
    central_treasury_wallet_name = serializers.ReadOnlyField(source='central_treasury_wallet.name')

    class Meta:
        model = MonitoringGlobalSettings
        fields = [
            'id',
            'data_source_mode',
            'usd_to_dzd_exchange_rate',
            'dzt_asset_code',
            'dzt_asset_issuer',
            'stellar_horizon_url',
            'is_auto_sync_enabled',
            'last_global_sync',
            'games_collection_wallet',
            'games_collection_wallet_name',
            'central_treasury_wallet',
            'central_treasury_wallet_name',
            'total_live_profits_dzd',
            'total_live_sales_dzd',
            'total_live_orders_count',
            'g2bulk_min_threshold_usd',
            'g2bulk_base_url',
            'binance_merchant_id',
        ]
        read_only_fields = [
            'id',
            'usd_to_dzd_exchange_rate',
            'total_live_profits_dzd',
            'total_live_sales_dzd',
            'total_live_orders_count',
            'last_global_sync',
        ]


class StellarWalletSerializer(serializers.ModelSerializer):
    family_display = serializers.CharField(source='get_family_display', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    has_secret = serializers.SerializerMethodField()

    class Meta:
        model = StellarWallet
        fields = [
            'id',
            'name',
            'family',
            'family_display',
            'role',
            'role_display',
            'category',
            'category_display',
            'public_address',
            'secret_seed',
            'dzt_balance',
            'is_active',
            'has_secret',
            'last_synced_at',
            'last_error',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'last_synced_at',
            'last_error',
            'created_at',
            'updated_at',
        ]
        extra_kwargs = {
            'secret_seed': {'write_only': True, 'required': False},
            'dzt_balance': {'required': False},
        }

    def get_has_secret(self, obj) -> bool:
        return bool(obj.secret_seed and str(obj.secret_seed).strip().startswith('S'))


class WalletSweepLogSerializer(serializers.ModelSerializer):
    source_wallet_name = serializers.ReadOnlyField(source='source_wallet.name')
    destination_wallet_name = serializers.ReadOnlyField(source='destination_wallet.name')
    sweep_type_display = serializers.CharField(source='get_sweep_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = WalletSweepLog
        fields = [
            'id',
            'timestamp',
            'source_wallet',
            'source_wallet_name',
            'destination_wallet',
            'destination_wallet_name',
            'amount_dzt',
            'sweep_type',
            'sweep_type_display',
            'status',
            'status_display',
            'stellar_tx_hash',
            'epay_reported_profit',
            'epay_reported_sales',
            'error_details',
            'created_at',
        ]
        read_only_fields = fields


class SupplierAccountSerializer(serializers.ModelSerializer):
    provider_display = serializers.CharField(source='get_provider_display', read_only=True)
    min_balance_threshold_dzd = serializers.SerializerMethodField()
    is_below_threshold = serializers.SerializerMethodField()
    deficit_usd = serializers.SerializerMethodField()
    deficit_dzd = serializers.SerializerMethodField()

    class Meta:
        model = SupplierAccount
        fields = [
            'id',
            'provider',
            'provider_display',
            'name',
            'balance_usd',
            'balance_dzd_equivalent',
            'min_balance_threshold_usd',
            'min_balance_threshold_dzd',
            'is_below_threshold',
            'deficit_usd',
            'deficit_dzd',
            'account_username',
            'account_uid',
            'api_key',
            'is_active',
            'last_synced_at',
            'last_error',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'balance_dzd_equivalent',
            'last_synced_at',
            'last_error',
            'created_at',
            'updated_at',
        ]
        extra_kwargs = {
            'api_key': {'write_only': True, 'required': False},
            'balance_usd': {'required': False},
        }

    def get_min_balance_threshold_dzd(self, obj):
        settings = MonitoringGlobalSettings.get_settings()
        rate = settings.usd_to_dzd_exchange_rate
        threshold = obj.min_balance_threshold_usd or Decimal("500.0000")
        return float((threshold * Decimal(str(rate))).quantize(Decimal("0.01")))

    def get_is_below_threshold(self, obj):
        threshold = obj.min_balance_threshold_usd or Decimal("500.0000")
        return bool(obj.balance_usd < threshold)

    def get_deficit_usd(self, obj):
        threshold = obj.min_balance_threshold_usd or Decimal("500.0000")
        if obj.balance_usd < threshold:
            return float((threshold - obj.balance_usd).quantize(Decimal("0.0001")))
        return 0.0

    def get_deficit_dzd(self, obj):
        threshold = obj.min_balance_threshold_usd or Decimal("500.0000")
        if obj.balance_usd < threshold:
            settings = MonitoringGlobalSettings.get_settings()
            rate = settings.usd_to_dzd_exchange_rate
            diff = (threshold - obj.balance_usd) * Decimal(str(rate))
            return float(diff.quantize(Decimal("0.01")))
        return 0.0

    def create(self, validated_data):
        instance = super().create(validated_data)
        instance.update_dzd_equivalent()
        instance.save(update_fields=['balance_dzd_equivalent'])
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        instance.update_dzd_equivalent()
        instance.save(update_fields=['balance_dzd_equivalent'])
        return instance


class BaridiMobAccountSerializer(serializers.ModelSerializer):
    system_type_display = serializers.CharField(source='get_system_type_display', read_only=True)

    class Meta:
        model = BaridiMobAccount
        fields = [
            'id',
            'account_name',
            'rip_number',
            'system_type',
            'system_type_display',
            'account_email',
            'balance_dzd',
            'secret_token',
            'devid',
            'is_active',
            'last_synced_at',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'secret_token': {'write_only': True, 'required': False},
            'devid': {'write_only': True, 'required': False},
        }


class BaridiMobTransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.ReadOnlyField(source='account.account_name')
    account_system_type = serializers.ReadOnlyField(source='account.system_type')

    class Meta:
        model = BaridiMobTransaction
        fields = [
            'id',
            'account',
            'account_name',
            'account_system_type',
            'tid',
            'ref_num',
            'amount',
            'fee_amount',
            'transaction_type',
            'operation_code',
            'is_bank_fee',
            'description',
            'available_balance',
            'transaction_date',
            'raw_data',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CapitalEntrySerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    destination_wallet_name = serializers.ReadOnlyField(source='destination_wallet.name')
    destination_supplier_name = serializers.ReadOnlyField(source='destination_supplier.name')

    class Meta:
        model = CapitalEntry
        fields = [
            'id',
            'title',
            'category',
            'category_display',
            'amount_dzd',
            'deposit_date',
            'source_account',
            'destination_wallet',
            'destination_wallet_name',
            'destination_supplier',
            'destination_supplier_name',
            'destination_baridimob',
            'binance_txid',
            'binance_verified_amount_usd',
            'binance_verification_status',
            'binance_verification_notes',
            'binance_verified_at',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WithdrawalRecordSerializer(serializers.ModelSerializer):
    system_type_display = serializers.CharField(source='get_system_type_display', read_only=True)
    withdrawal_type_display = serializers.CharField(source='get_withdrawal_type_display', read_only=True)
    purpose_code_display = serializers.CharField(source='get_purpose_code_display', read_only=True)
    stage_display = serializers.CharField(source='get_stage_display', read_only=True)
    stage_number = serializers.ReadOnlyField()
    next_action = serializers.ReadOnlyField()
    source_wallet_name = serializers.ReadOnlyField(source='source_wallet.name')
    destination_supplier_name = serializers.ReadOnlyField(source='destination_supplier.name')
    purpose_default_notes = serializers.ReadOnlyField()
    receipt_file_url = serializers.ReadOnlyField()

    class Meta:
        model = WithdrawalRecord
        fields = [
            'id',
            'title',
            'purpose_code',
            'purpose_code_display',
            'purpose_default_notes',
            'system_type',
            'system_type_display',
            'withdrawal_type',
            'withdrawal_type_display',
            'stage',
            'stage_display',
            'stage_number',
            'next_action',
            'amount_dzd',
            'amount_usd_equivalent',
            'withdrawal_date',
            'source_wallet',
            'source_wallet_name',
            'source_baridimob',
            'destination_supplier',
            'destination_supplier_name',
            'destination_recipient',
            'binance_txid',
            'p2p_order_id',
            'p2p_rate',
            'binance_pay_id',
            'g2bulk_transaction_id',
            'supplier_pay_id',
            'g2bulk_confirmed_increase_usd',
            'binance_fee_usd',
            'binance_fee_dzd',
            'binance_verified_amount_usd',
            'binance_verification_status',
            'binance_verification_notes',
            'binance_verified_at',
            'reference',
            'stellar_tx_hash',
            'file_hash',
            'receipt_file',
            'receipt_file_url',
            'funding_receipt',
            'recipient_rip',
            'receipt_amount_dzd',
            'receipt_verified',
            'notes',
            'created_by',
            'operator_name',
            'created_by_user',
            'last_operator_user',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'stage_number', 'next_action', 'receipt_file', 'receipt_file_url', 'created_at', 'updated_at']


class LiquidityRetraitRecordSerializer(serializers.ModelSerializer):
    """
    Serializer strictly for Pure Liquidity Retrait (Fund Outflows).
    Isolated from Binance/G2Bulk/Supplier procurement fields.
    """
    system_type_display = serializers.CharField(source='get_system_type_display', read_only=True)
    withdrawal_type_display = serializers.CharField(source='get_withdrawal_type_display', read_only=True)
    purpose_code_display = serializers.CharField(source='get_purpose_code_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    source_wallet_name = serializers.ReadOnlyField(source='source_wallet.name')
    receipt_file_url = serializers.ReadOnlyField()

    class Meta:
        model = LiquidityRetraitRecord
        fields = [
            'id',
            'title',
            'system_type',
            'system_type_display',
            'withdrawal_type',
            'withdrawal_type_display',
            'purpose_code',
            'purpose_code_display',
            'amount_dzd',
            'withdrawal_date',
            'status',
            'status_display',
            'source_wallet',
            'source_wallet_name',
            'source_baridimob',
            'destination_recipient',
            'recipient_rip',
            'receipt_amount_dzd',
            'receipt_verified',
            'reference',
            'file_hash',
            'receipt_file',
            'receipt_file_url',
            'stellar_tx_hash',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'receipt_file', 'receipt_file_url', 'created_at', 'updated_at']


class BaridiMobFundingReceiptSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for the full G2Bulk Supplier Funding Lifecycle:
    Stage 1: BaridiMob receipt + Stellar internal transfer
    Stage 2: Binance P2P purchase
    Stage 3: Binance Pay to G2Bulk
    Stage 4: G2Bulk balance credit & reconciliation
    """
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    source_wallet_name = serializers.ReadOnlyField(source='source_wallet.name')
    destination_wallet_name = serializers.ReadOnlyField(source='destination_wallet.name')
    supplier_name = serializers.ReadOnlyField(source='supplier_account.name')
    expense_amount = serializers.ReadOnlyField(source='expense_record.amount_dzd')

    class Meta:
        model = BaridiMobFundingReceipt
        fields = [
            'id',
            'receipt_file',
            'reference',
            'file_hash',
            'amount_dzd',
            'recipient_rip',
            'responsible_person',
            'source_wallet',
            'source_wallet_name',
            'destination_wallet',
            'destination_wallet_name',
            'stellar_tx_hash',
            'supplier_account',
            'supplier_name',
            'expense_record',
            'expense_amount',
            'withdrawal_record',
            'binance_order_id',
            'usdt_acquired',
            'p2p_rate',
            'usdt_sent_to_g2bulk',
            'binance_fee_usd',
            'g2bulk_increase_usd',
            'status',
            'status_display',
            'notes',
            'receipt_date',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'receipt_file',
            'reference',
            'file_hash',
            'amount_dzd',
            'recipient_rip',
            'stellar_tx_hash',
            'expense_record',
            'created_at',
            'updated_at',
        ]


class ExpenseRecordSerializer(serializers.ModelSerializer):
    title = serializers.CharField(required=False, allow_blank=True, max_length=200)
    system_type_display = serializers.CharField(source='get_system_type_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = ExpenseRecord
        fields = [
            'id',
            'title',
            'system_type',
            'system_type_display',
            'category',
            'category_display',
            'amount_dzd',
            'expense_date',
            'reference',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        if not validated_data.get('title'):
            category = validated_data.get('category', 'OPERATIONAL')
            notes = validated_data.get('notes', '')
            sys_type = validated_data.get('system_type', 'GENERAL')
            if notes:
                validated_data['title'] = f"[{sys_type}] {notes[:50]}"
            else:
                validated_data['title'] = f"[{sys_type}] {category} Expense"
        return super().create(validated_data)


class ReceiptUploadSerializer(serializers.Serializer):
    """
    Accepts either direct receipt data (pure database record) or an uploaded PDF/image 
    for in-memory parsing. Strictly never forces storing files on disk.
    """
    receipt_file = serializers.FileField(required=False, allow_null=True)
    reference = serializers.CharField(required=False, allow_blank=True)
    amount_dzd = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, allow_null=True)
    recipient_rip = serializers.CharField(required=False, allow_blank=True)
    receipt_date = serializers.DateField(required=False, allow_null=True)
    responsible_person = serializers.CharField(required=False, default="P2P Purchasing Officer", allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_receipt_file(self, file_obj):
        if not file_obj:
            return None
        name_lower = getattr(file_obj, 'name', '').lower()
        if not (name_lower.endswith('.pdf') or name_lower.endswith(('.png', '.jpg', '.jpeg', '.webp'))):
            raise serializers.ValidationError("File must be a PDF document or a valid image (PNG/JPG).")
        return file_obj


class LinkP2POrderSerializer(serializers.Serializer):
    """Links Binance P2P purchase of USDT to the funding cycle"""
    binance_order_id = serializers.CharField(required=True)
    usdt_acquired = serializers.DecimalField(max_digits=15, decimal_places=4, required=False)
    p2p_rate = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class LinkG2BulkTransferSerializer(serializers.Serializer):
    """Links transfer of USDT to G2Bulk's Binance account"""
    usdt_sent_to_g2bulk = serializers.DecimalField(max_digits=15, decimal_places=4, required=True)
    binance_pay_order_id = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class GameProfitRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameProfitRecord
        fields = '__all__'


class UtilityBillRecordSerializer(serializers.ModelSerializer):
    service_display = serializers.CharField(source='get_service_display', read_only=True)

    class Meta:
        model = UtilityBillRecord
        fields = '__all__'


class BalanceAuditLogSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = BalanceAuditLog
        fields = '__all__'
        read_only_fields = [
            'id',
            'checked_at',
            'total_dzt_wallets',
            'total_g2bulk_dzd',
            'total_baridimob_dzd',
            'total_in_transit_dzd',
            'total_assets_dzd',
            'total_expenses_dzd',
            'left_side_total',
            'total_capital_dzd',
            'total_profits_dzd',
            'right_side_total',
            'discrepancy_dzd',
            'status',
            'notes',
        ]


class BybitAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BybitAccount
        fields = '__all__'


class AiraloAccountSerializer(serializers.ModelSerializer):
    balance_dzd_equivalent = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = AiraloAccount
        fields = '__all__'


class eSIMFundingRecordSerializer(serializers.ModelSerializer):
    stage_display = serializers.CharField(source='get_stage_display', read_only=True)
    source_baridimob_name = serializers.CharField(source='source_baridimob.account_name', read_only=True)

    class Meta:
        model = eSIMFundingRecord
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class eSIMOrderRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = eSIMOrderRecord
        fields = '__all__'


class G2BulkReplenishmentWindowSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    is_active = serializers.BooleanField(source='is_currently_active', read_only=True)
    remaining_seconds = serializers.IntegerField(read_only=True)
    elapsed_seconds = serializers.IntegerField(read_only=True)
    progress_pct = serializers.FloatField(read_only=True)

    class Meta:
        model = G2BulkReplenishmentWindow
        fields = [
            'id',
            'supplier',
            'supplier_name',
            'status',
            'status_display',
            'is_active',
            'started_at',
            'duration_hours',
            'expires_at',
            'completed_at',
            'initiated_by',
            'initial_balance_usd',
            'target_replenish_amount_usd',
            'final_balance_usd',
            'final_discrepancy_dzd',
            'alert_dispatched',
            'alert_dispatched_at',
            'suppressed_alerts_count',
            'notes',
            'remaining_seconds',
            'elapsed_seconds',
            'progress_pct',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'started_at',
            'expires_at',
            'completed_at',
            'created_at',
            'updated_at',
        ]


class IdoomBatchRefillSerializer(serializers.ModelSerializer):
    executed_by_username = serializers.CharField(source='executed_by.username', read_only=True)
    withdrawal_reference = serializers.CharField(source='withdrawal_record.reference', read_only=True)

    class Meta:
        model = IdoomBatchRefill
        fields = [
            'id',
            'batch_reference',
            'total_cards_count',
            'total_face_value_dzd',
            'total_cost_dzd',
            'expected_profit_dzd',
            'breakdown_json',
            'uploaded_file_name',
            'executed_by',
            'executed_by_username',
            'withdrawal_record',
            'withdrawal_reference',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class IdoomRefundRecordSerializer(serializers.ModelSerializer):
    executed_by_username = serializers.CharField(source='executed_by.username', read_only=True)

    class Meta:
        model = IdoomRefundRecord
        fields = [
            'id',
            'refund_reference',
            'epay_transaction_id',
            'client_phone_or_account',
            'denomination_dzd',
            'reversed_profit_dzd',
            'reason',
            'executed_by',
            'executed_by_username',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class IPTVBatchRefillSerializer(serializers.ModelSerializer):
    executed_by_username = serializers.CharField(source='executed_by.username', read_only=True)
    withdrawal_reference = serializers.CharField(source='withdrawal_record.reference', read_only=True)

    class Meta:
        model = IPTVBatchRefill
        fields = [
            'id',
            'batch_reference',
            'total_cards_count',
            'total_face_value_dzd',
            'total_cost_dzd',
            'expected_profit_dzd',
            'breakdown_json',
            'uploaded_file_name',
            'executed_by',
            'executed_by_username',
            'withdrawal_record',
            'withdrawal_reference',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class IPTVRefundRecordSerializer(serializers.ModelSerializer):
    executed_by_username = serializers.CharField(source='executed_by.username', read_only=True)

    class Meta:
        model = IPTVRefundRecord
        fields = [
            'id',
            'refund_reference',
            'epay_transaction_id',
            'client_phone_or_account',
            'denomination_dzd',
            'reversed_profit_dzd',
            'reason',
            'executed_by',
            'executed_by_username',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


# ==============================================================================
# FLEXY TELECOM SUBSYSTEM SERIALIZERS
# ==============================================================================

class FlexyFundingTrancheSerializer(serializers.ModelSerializer):
    executed_by_username = serializers.CharField(source='executed_by.username', read_only=True)
    source_wallet_name = serializers.CharField(source='source_wallet.name', read_only=True)
    source_wallet_address = serializers.CharField(source='source_wallet.public_address', read_only=True)

    class Meta:
        from .models import FlexyFundingTranche
        model = FlexyFundingTranche
        fields = [
            'id',
            'tranche_reference',
            'initial_amount_dzd',
            'remaining_balance_dzd',
            'bonus_mobilis_pct',
            'bonus_pixx_pct',
            'bonus_djezzy_pct',
            'bonus_ooredoo_pct',
            'shemsnet_tx_id',
            'stellar_tx_hash',
            'source_wallet',
            'source_wallet_name',
            'source_wallet_address',
            'withdrawal_record',
            'executed_by',
            'executed_by_username',
            'is_active',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FlexyOperationRecordSerializer(serializers.ModelSerializer):
    tranche_ref = serializers.CharField(source='tranche.tranche_reference', read_only=True)

    class Meta:
        from .models import FlexyOperationRecord
        model = FlexyOperationRecord
        fields = [
            'id',
            'operation_reference',
            'shemsnet_op_id',
            'operator',
            'phone_number',
            'face_amount_dzd',
            'procurement_cost_dzd',
            'net_profit_dzd',
            'applied_bonus_pct',
            'tranche',
            'tranche_ref',
            'is_swept',
            'sweep_batch',
            'status',
            'raw_response',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class FlexyDualSweepBatchSerializer(serializers.ModelSerializer):
    executed_by_username = serializers.CharField(source='executed_by.username', read_only=True)
    source_wallet_name = serializers.CharField(source='source_wallet.name', read_only=True)
    collection_wallet_name = serializers.CharField(source='collection_wallet.name', read_only=True)
    profit_wallet_name = serializers.CharField(source='profit_wallet.name', read_only=True)

    class Meta:
        from .models import FlexyDualSweepBatch
        model = FlexyDualSweepBatch
        fields = [
            'id',
            'batch_reference',
            'operator',
            'total_volume_dzd',
            'total_capital_dzd',
            'total_profit_dzd',
            'source_wallet',
            'source_wallet_name',
            'collection_wallet',
            'collection_wallet_name',
            'profit_wallet',
            'profit_wallet_name',
            'collection_tx_hash',
            'profit_tx_hash',
            'executed_by',
            'executed_by_username',
            'status',
            'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']



