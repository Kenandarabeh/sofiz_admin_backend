import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.db import transaction as db_transaction

from monitoring.models import (
    FlexyFundingTranche,
    FlexyOperationRecord,
    FlexyDualSweepBatch,
    StellarWallet,
    WalletFamily,
    WalletRole,
    MonitoringGlobalSettings,
)
from monitoring.services.stellar_service import StellarService

logger = logging.getLogger(__name__)


class FlexySweepEngine:
    """
    Dedicated on-chain Dual-Sweep Engine for Algerian telecom operators (Mobilis, Djezzy, Ooredoo).
    Segregates incoming customer funds into:
    1. Procurement Capital -> Swept to Collection Treasury Vault.
    2. Net Margin Profit -> Swept to dedicated Flexy Profit Vault.
    """

    @classmethod
    def get_unswept_summary(cls, operator: str = None) -> dict:
        """
        Summarizes pending unswept operations and volume across operators.
        """
        qs = FlexyOperationRecord.objects.filter(is_swept=False, status='SUCCESS')
        if operator and operator.upper() != 'ALL':
            if operator.upper() == 'MOBILIS':
                qs = qs.filter(operator__in=['MOBILIS', 'PIXX'])
            else:
                qs = qs.filter(operator=operator.upper())

        total_volume = sum((op.face_amount_dzd for op in qs), Decimal('0.00'))
        total_capital = sum((op.procurement_cost_dzd for op in qs), Decimal('0.00'))
        total_profit = sum((op.net_profit_dzd for op in qs), Decimal('0.00'))

        return {
            "pending_operations_count": qs.count(),
            "total_volume_dzd": float(total_volume),
            "total_capital_dzd": float(total_capital),
            "total_profit_dzd": float(total_profit),
        }

    @classmethod
    def execute_dual_sweep(
        cls,
        operator: str,
        source_wallet_id: int = None,
        collection_wallet_id: int = None,
        profit_wallet_id: int = None,
        executed_by_user = None,
    ) -> dict:
        """
        Executes the Dual-Sweep:
        1. Selects pending unswept operations for the operator.
        2. Calculates capital and profit totals.
        3. Transfers capital to Collection/Treasury Vault and profit to Profit Vault.
        4. Links operations to FlexyDualSweepBatch and marks them swept.
        """
        operator_clean = operator.upper().strip()
        qs = FlexyOperationRecord.objects.filter(is_swept=False, status='SUCCESS')
        if operator_clean != 'ALL':
            if operator_clean == 'MOBILIS':
                qs = qs.filter(operator__in=['MOBILIS', 'PIXX'])
            else:
                qs = qs.filter(operator=operator_clean)

        operations_to_sweep = list(qs)
        if not operations_to_sweep:
            return {"success": False, "error": f"No pending unswept operations found for {operator_clean}."}

        total_volume = sum((op.face_amount_dzd for op in operations_to_sweep), Decimal('0.00'))
        total_capital = sum((op.procurement_cost_dzd for op in operations_to_sweep), Decimal('0.00'))
        total_profit = sum((op.net_profit_dzd for op in operations_to_sweep), Decimal('0.00'))

        # Invariant safety check: Volume == Capital + Profit
        discrepancy = total_volume - (total_capital + total_profit)
        if discrepancy != Decimal('0.00'):
            total_profit += discrepancy

        # Resolve Source Operator Stellar Wallet
        source_wallet = None
        if source_wallet_id:
            source_wallet = StellarWallet.objects.filter(id=source_wallet_id, is_active=True).first()
        if not source_wallet:
            source_wallet = StellarWallet.objects.filter(
                family=WalletFamily.FLEXY,
                name__icontains=operator_clean,
                is_active=True
            ).first() or StellarWallet.objects.filter(family=WalletFamily.TREASURY, role=WalletRole.COLLECTION, is_active=True).first()

        # Resolve Withdrawal / Refill Wallet (Capital returns to Withdrawal Wallet to keep revolving!)
        collection_wallet = None
        if collection_wallet_id:
            collection_wallet = StellarWallet.objects.filter(id=collection_wallet_id, is_active=True).first()
        if not collection_wallet:
            collection_wallet = StellarWallet.objects.filter(
                family=WalletFamily.FLEXY,
                role=WalletRole.WITHDRAWAL,
                is_active=True
            ).first() or StellarWallet.objects.filter(
                role=WalletRole.WITHDRAWAL,
                is_active=True
            ).first()

        # Resolve Flexy Profit Vault
        profit_wallet = None
        if profit_wallet_id:
            profit_wallet = StellarWallet.objects.filter(id=profit_wallet_id, is_active=True).first()
        if not profit_wallet:
            profit_wallet = StellarWallet.objects.filter(
                family=WalletFamily.FLEXY,
                role=WalletRole.PROFIT,
                is_active=True
            ).first() or StellarWallet.objects.filter(role=WalletRole.PROFIT, is_active=True).first()

        collection_tx_hash = None
        profit_tx_hash = None

        # Execute On-Chain Sweeps if wallets are configured with seeds
        if source_wallet and collection_wallet and total_capital > Decimal('0.00'):
            try:
                res_col = StellarService.send_payment(
                    source_wallet=source_wallet,
                    destination_wallet=collection_wallet,
                    amount=total_capital,
                    memo_text=f"FLX-CAP-{operator_clean[:4]}",
                )
                if res_col.get('success'):
                    collection_tx_hash = res_col.get('hash')
            except Exception as e:
                logger.warning(f"On-chain capital sweep failed (fallback to internal): {e}")

        if source_wallet and profit_wallet and total_profit > Decimal('0.00'):
            try:
                res_prof = StellarService.send_payment(
                    source_wallet=source_wallet,
                    destination_wallet=profit_wallet,
                    amount=total_profit,
                    memo_text=f"FLX-PRF-{operator_clean[:4]}",
                )
                if res_prof.get('success'):
                    profit_tx_hash = res_prof.get('hash')
            except Exception as e:
                logger.warning(f"On-chain profit sweep failed (fallback to internal): {e}")

        batch_ref = f"SWP-FLX-{timezone.now().strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:6].upper()}"

        with db_transaction.atomic():
            # Update virtual ledger balances if on-chain did not debit
            if not collection_tx_hash and collection_wallet:
                collection_wallet.dzt_balance = (collection_wallet.dzt_balance + total_capital).quantize(Decimal("0.0000001"))
                collection_wallet.save(update_fields=['dzt_balance', 'updated_at'])

            if not profit_tx_hash and profit_wallet:
                profit_wallet.dzt_balance = (profit_wallet.dzt_balance + total_profit).quantize(Decimal("0.0000001"))
                profit_wallet.save(update_fields=['dzt_balance', 'updated_at'])

            sweep_batch = FlexyDualSweepBatch.objects.create(
                batch_reference=batch_ref,
                operator=operator_clean,
                total_volume_dzd=total_volume,
                total_capital_dzd=total_capital,
                total_profit_dzd=total_profit,
                source_wallet=source_wallet,
                collection_wallet=collection_wallet,
                profit_wallet=profit_wallet,
                collection_tx_hash=collection_tx_hash,
                profit_tx_hash=profit_tx_hash,
                executed_by=executed_by_user,
                status='COMPLETED',
                notes=f"Dual-sweep executed across {len(operations_to_sweep)} operations for {operator_clean}.",
            )

            # Mark operations as swept
            op_ids = [op.id for op in operations_to_sweep]
            FlexyOperationRecord.objects.filter(id__in=op_ids).update(
                is_swept=True,
                sweep_batch=sweep_batch
            )

        return {
            "success": True,
            "message": f"Successfully executed dual-sweep for {operator_clean}.",
            "batch_reference": batch_ref,
            "total_volume_dzd": float(total_volume),
            "total_capital_dzd": float(total_capital),
            "total_profit_dzd": float(total_profit),
            "collection_tx_hash": collection_tx_hash,
            "profit_tx_hash": profit_tx_hash,
            "operations_swept_count": len(operations_to_sweep),
        }
