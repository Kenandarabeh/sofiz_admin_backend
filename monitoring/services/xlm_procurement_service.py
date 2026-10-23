"""
Institutional XLM Liquidity Procurement & On-Chain Replenishment Service
Handles the 4-stage procurement workflow:
Stage 1: BaridiMob Outflow Dispatched -> P2P USDT Acquired (Binance/Bybit)
Stage 2: USDT Converted to Native XLM
Stage 3: On-Chain Blockchain Withdrawal to Master Central Treasury Vault
Stage 4: Consensus Horizon Verification & Automatic Ledger Completion
"""
import logging
from decimal import Decimal
from django.utils import timezone
from django.db import transaction, models
from django.contrib.auth import get_user_model
from ..models import (
    XLMLiquidityFundingRecord,
    XLMFundingStage,
    StellarWallet,
    BaridiMobAccount,
    MonitoringGlobalSettings,
    WithdrawalRecord,
    WithdrawalStage,
    WithdrawalPurpose,
    WalletFamily,
    WalletRole,
    BinanceAccount,
)
from .stellar_service import StellarService
from .balance_engine import BalanceEngine

logger = logging.getLogger(__name__)
User = get_user_model()

MASTER_VAULT_ADDRESS = "GBYCZO2R2QPLJ4DD2YMYSWSGTOVSFTHI3H22KZVK6DSHENLAJ5MBW4TY"
MIN_XLM_SAFETY_THRESHOLD = Decimal("100.0000000")


class XLMProcurementService:

    @classmethod
    def get_pipeline_overview(cls, force_sync: bool = False) -> dict:
        """
        Retrieves real-time pipeline status for XLM procurement:
        1. Live on-chain native XLM balance of Master Vault GBYCZO...
        2. Low XLM reserve safety threshold check (< 100 XLM).
        3. Shared ECCP / BaridiMob account balance & 3-quota allocation (Games, eSIM, XLM).
        4. Active and completed procurement cycles across the 4 stages.
        """
        # 1. Fetch & sync Central Treasury Vault
        vault = StellarWallet.objects.filter(public_address=MASTER_VAULT_ADDRESS).first()
        if not vault:
            vault = StellarWallet.objects.filter(family=WalletFamily.TREASURY, role=WalletRole.VAULT).first()

        if vault and (force_sync or not vault.last_synced_at):
            try:
                StellarService.sync_wallet(vault)
                vault.refresh_from_db()
            except Exception as e:
                logger.warning(f"Error syncing master vault for XLM pipeline: {e}")

        vault_xlm_balance = getattr(vault, 'native_xlm_balance', Decimal('0.0000000')) if vault else Decimal('0.0000000')
        vault_dzt_balance = getattr(vault, 'dzt_balance', Decimal('0.0000')) if vault else Decimal('0.0000')
        is_low_xlm_reserve = vault_xlm_balance < MIN_XLM_SAFETY_THRESHOLD

        # 2. Shared BaridiMob Account (Account #3 - Salah Gaming/Shared Account) & 3-Way Quota Split
        salah_alloc = BalanceEngine.get_salah_baridimob_allocation()
        shared_acc = BaridiMobAccount.objects.filter(rip_number__icontains="001738866535").first()
        if not shared_acc:
            shared_acc = BaridiMobAccount.objects.filter(account_name__icontains="Salah").first() or BaridiMobAccount.objects.first()

        eccp_balance = salah_alloc.get('eccp_balance_dzd') or (getattr(shared_acc, 'eccp_balance_dzd', Decimal('0.00')) if shared_acc else Decimal('0.00'))
        baridimob_balance = salah_alloc.get('baridimob_card_balance_dzd') or (getattr(shared_acc, 'balance_dzd', Decimal('0.00')) if shared_acc else Decimal('0.00'))

        # Quota and active in-transit allocations
        active_gaming_inflows = WithdrawalRecord.objects.filter(
            stage__in=[WithdrawalStage.ALLOCATED, WithdrawalStage.BINANCE_P2P],
            purpose_code=WithdrawalPurpose.G2BULK_P2P
        ).values_list('amount_dzd', flat=True)
        gaming_transit_dzd = sum(active_gaming_inflows or [Decimal('0.00')])

        active_esim_inflows = WithdrawalRecord.objects.filter(
            stage__in=[WithdrawalStage.ALLOCATED, WithdrawalStage.BINANCE_P2P],
            purpose_code=WithdrawalPurpose.ESIM_REFILL
        ).values_list('amount_dzd', flat=True)
        esim_transit_dzd = sum(active_esim_inflows or [Decimal('0.00')])

        active_xlm_inflows = XLMLiquidityFundingRecord.objects.filter(
            stage__in=[
                XLMFundingStage.STAGE_1_BARIDIMOB,
                XLMFundingStage.STAGE_2_CONVERT,
                XLMFundingStage.STAGE_3_WITHDRAW,
            ]
        ).values_list('amount_dzd', flat=True)
        xlm_transit_dzd = sum(active_xlm_inflows or [Decimal('0.00')])

        # 3. Pipeline Cycles
        all_cycles = XLMLiquidityFundingRecord.objects.all().order_by('-created_at')
        cycles_list = []
        for c in all_cycles[:60]:
            cycles_list.append({
                'id': c.id,
                'cycle_reference': c.cycle_reference,
                'amount_dzd': float(c.amount_dzd),
                'receipt_reference': c.receipt_reference,
                'receipt_file_url': c.receipt_file.url if c.receipt_file else None,
                'receipt_verified': c.receipt_verified,
                'stage': c.stage,
                'p2p_order_id': c.p2p_order_id,
                'p2p_platform': c.p2p_platform,
                'usdt_acquired': float(c.usdt_acquired) if c.usdt_acquired is not None else None,
                'p2p_rate_dzd': float(c.p2p_rate_dzd) if c.p2p_rate_dzd is not None else None,
                'xlm_acquired': float(c.xlm_acquired) if c.xlm_acquired is not None else None,
                'convert_rate_usdt': float(c.convert_rate_usdt) if c.convert_rate_usdt is not None else None,
                'stellar_tx_hash': c.stellar_tx_hash,
                'network_fee_xlm': float(c.network_fee_xlm) if c.network_fee_xlm is not None else 0.0,
                'stellar_net_xlm_sent': float(c.stellar_net_xlm_sent) if c.stellar_net_xlm_sent is not None else None,
                'on_chain_verified': c.on_chain_verified,
                'on_chain_verified_at': c.on_chain_verified_at.isoformat() if c.on_chain_verified_at else None,
                'stellar_ledger_sequence': c.stellar_ledger_sequence,
                'vault_balance_after_xlm': float(c.vault_balance_after_xlm) if c.vault_balance_after_xlm is not None else None,
                'executed_by_name': c.executed_by.username if c.executed_by else 'Walid / Treasury',
                'notes': c.notes,
                'created_at': c.created_at.isoformat(),
                'updated_at': c.updated_at.isoformat(),
            })

        stage_counts = {
            'stage_1': all_cycles.filter(stage=XLMFundingStage.STAGE_1_BARIDIMOB).count(),
            'stage_2': all_cycles.filter(stage=XLMFundingStage.STAGE_2_CONVERT).count(),
            'stage_3': all_cycles.filter(stage=XLMFundingStage.STAGE_3_WITHDRAW).count(),
            'stage_4': all_cycles.filter(stage=XLMFundingStage.STAGE_4_COMPLETED).count(),
        }

        total_procured_xlm = sum(
            c.stellar_net_xlm_sent or c.xlm_acquired or Decimal('0')
            for c in all_cycles.filter(stage=XLMFundingStage.STAGE_4_COMPLETED)
        )

        binance = BinanceAccount.objects.filter(is_active=True).first()
        monitoring_settings = MonitoringGlobalSettings.get_settings()
        p2p_rate_val = getattr(monitoring_settings, 'usd_to_dzd_exchange_rate', Decimal('254.00')) or Decimal('254.00')

        walid_wallet = StellarWallet.objects.filter(
            models.Q(family=WalletFamily.XLM, role=WalletRole.WITHDRAWAL) |
            models.Q(name__icontains='Walid')
        ).first()

        return {
            'success': True,
            'walid_sourcing_wallet': {
                'id': walid_wallet.id if walid_wallet else None,
                'name': 'Treasury Withdrawal Sourcing Wallet',
                'public_address': walid_wallet.public_address if walid_wallet else '',
                'dzt_balance': float(getattr(walid_wallet, 'dzt_balance', Decimal('0.0000')) or 0.0),
                'native_xlm_balance': float(getattr(walid_wallet, 'native_xlm_balance', Decimal('0.0000000')) or 0.0),
            } if walid_wallet else None,
            'vault': {
                'name': vault.name if vault else 'Big SofizPay Central Treasury Vault',
                'public_address': vault.public_address if vault else MASTER_VAULT_ADDRESS,
                'native_xlm_balance': float(vault_xlm_balance),
                'dzt_balance': float(vault_dzt_balance),
                'min_safety_threshold': float(MIN_XLM_SAFETY_THRESHOLD),
                'is_low_xlm_reserve': is_low_xlm_reserve,
                'last_synced_at': vault.last_synced_at.isoformat() if vault and vault.last_synced_at else None,
            },
            'binance_account': {
                'account_name': binance.account_name if binance else 'Binance Corporate P2P',
                'funding_balance_usdt': float(getattr(binance, 'balance_usdt', Decimal('0.00'))),
            } if binance else None,
            'p2p_rate': {
                'rate': float(p2p_rate_val),
            },
            'shared_postal_account': {
                'account_name': 'Gaming Operational Account',
                'rip_number': salah_alloc.get('rip_number') or (shared_acc.rip_number if shared_acc else '00799999001738866535'),
                'eccp_balance_dzd': float(eccp_balance),
                'baridimob_card_balance_dzd': float(baridimob_balance),
                'eccp_last_synced_at': salah_alloc.get('eccp_last_synced_at'),
                'gaming_transit_dzd': float(gaming_transit_dzd),
                'esim_transit_dzd': float(esim_transit_dzd),
                'xlm_transit_dzd': float(xlm_transit_dzd),
                'salah_allocation': salah_alloc,
                'gaming_quota': salah_alloc.get('gaming', {}),
                'esim_quota': salah_alloc.get('esim', {}),
                'xlm_quota': salah_alloc.get('xlm', {}),
            },
            'salah_baridimob_allocation': salah_alloc,
            'stage_counts': stage_counts,
            'total_procured_xlm': float(total_procured_xlm),
            'cycles': cycles_list,
        }

    @classmethod
    @transaction.atomic
    def initiate_cycle(
        cls,
        amount_dzd: Decimal,
        receipt_reference: str,
        receipt_file=None,
        executed_by=None,
        notes: str = "",
        source_cycle_ids: list = None,
    ) -> dict:
        """
        Stage 1 Entry: Walid enters the BaridiMob receipt to fund XLM procurement.
        Creates a new cycle record in STAGE_1_BARIDIMOB.
        Also supports consolidating multiple pending source cycles into a combined cycle.
        """
        amount = Decimal(str(amount_dzd))
        if amount <= Decimal("0.00"):
            raise ValueError("Refill amount must be greater than zero DZD.")

        clean_ref = str(receipt_reference or "").strip()
        if not clean_ref:
            raise ValueError("BaridiMob receipt reference is strictly required.")

        # Duplicate check on receipt reference
        if XLMLiquidityFundingRecord.objects.filter(receipt_reference=clean_ref).exists():
            raise ValueError(f"BaridiMob receipt reference #{clean_ref} has already been registered in a previous cycle.")

        # Generate unique cycle reference
        today_str = timezone.now().strftime("%Y%m%d")
        existing_today = XLMLiquidityFundingRecord.objects.filter(cycle_reference__contains=f"XLM-CYC-{today_str}").count()
        cycle_ref = f"XLM-CYC-{today_str}-{existing_today + 1:04d}"

        cycle = XLMLiquidityFundingRecord.objects.create(
            cycle_reference=cycle_ref,
            amount_dzd=amount,
            receipt_reference=clean_ref,
            receipt_file=receipt_file,
            receipt_verified=False,
            stage=XLMFundingStage.STAGE_1_BARIDIMOB,
            stellar_destination_address=MASTER_VAULT_ADDRESS,
            executed_by=executed_by,
            notes=notes or f"Initiated BaridiMob outflow of {amount:,.2f} DZD for Stellar XLM procurement.",
        )

        if source_cycle_ids:
            now_str = timezone.now().strftime('%Y-%m-%d %H:%M')
            src_cycles = XLMLiquidityFundingRecord.objects.filter(id__in=source_cycle_ids)
            for sc in src_cycles:
                sc.stage = XLMFundingStage.STAGE_4_COMPLETED
                sc.notes = (sc.notes or '').strip() + f"\n• [Consolidated @ {now_str}] Consumed into Combined XLM Procurement Cycle #{cycle.cycle_reference}."
                sc.save(update_fields=['stage', 'notes'])

        logger.info(f"Initiated XLM Liquidity Procurement cycle #{cycle.cycle_reference} for {amount:,.2f} DZD.")
        return {'success': True, 'cycle_id': cycle.id, 'cycle_reference': cycle.cycle_reference}


    @classmethod
    @transaction.atomic
    def advance_to_convert(
        cls,
        cycle_id: int,
        p2p_order_id: str,
        usdt_acquired: Decimal,
        p2p_rate_dzd: Decimal,
        p2p_platform: str = "BINANCE",
        notes: str = ""
    ) -> dict:
        """
        Transitions Stage 1 -> Stage 2:
        Sofiane acquires USDT via Binance/Bybit P2P using Walid's BaridiMob payment.
        """
        cycle = XLMLiquidityFundingRecord.objects.select_for_update().get(id=cycle_id)
        if cycle.stage != XLMFundingStage.STAGE_1_BARIDIMOB:
            raise ValueError(f"Cycle #{cycle.cycle_reference} is in stage '{cycle.stage}', cannot advance to Convert.")

        usdt_amt = Decimal(str(usdt_acquired))
        rate_dzd = Decimal(str(p2p_rate_dzd))
        if usdt_amt <= 0:
            raise ValueError("Acquired USDT amount must be greater than zero.")
        if rate_dzd <= 0:
            raise ValueError("P2P exchange rate must be greater than zero.")

        cycle.p2p_order_id = str(p2p_order_id or "").strip()
        cycle.p2p_platform = str(p2p_platform or "BINANCE").upper()
        cycle.usdt_acquired = usdt_amt
        cycle.p2p_rate_dzd = rate_dzd
        cycle.stage = XLMFundingStage.STAGE_2_CONVERT
        if notes:
            cycle.notes = (cycle.notes or '') + f"\n• [Stage 1 -> 2]: {notes}"
        cycle.save()

        logger.info(f"Cycle #{cycle.cycle_reference} advanced to STAGE_2_CONVERT ({usdt_amt:,.2f} USDT acquired).")
        return {'success': True, 'cycle_id': cycle.id, 'stage': cycle.stage}

    @classmethod
    @transaction.atomic
    def advance_to_withdraw(
        cls,
        cycle_id: int,
        xlm_acquired: Decimal,
        convert_rate_usdt: Decimal,
        convert_fee_usdt: Decimal = Decimal("0.0000"),
        notes: str = ""
    ) -> dict:
        """
        Transitions Stage 2 -> Stage 3:
        Sofiane converts the acquired USDT to native XLM on Binance/exchange.
        """
        cycle = XLMLiquidityFundingRecord.objects.select_for_update().get(id=cycle_id)
        if cycle.stage != XLMFundingStage.STAGE_2_CONVERT:
            raise ValueError(f"Cycle #{cycle.cycle_reference} is in stage '{cycle.stage}', cannot advance to Withdraw.")

        xlm_amt = Decimal(str(xlm_acquired))
        rate_usdt = Decimal(str(convert_rate_usdt))
        if xlm_amt <= 0:
            raise ValueError("Acquired XLM amount must be greater than zero.")

        cycle.xlm_acquired = xlm_amt
        cycle.convert_rate_usdt = rate_usdt
        cycle.convert_fee_usdt = Decimal(str(convert_fee_usdt or "0.0000"))
        cycle.stage = XLMFundingStage.STAGE_3_WITHDRAW
        if notes:
            cycle.notes = (cycle.notes or '') + f"\n• [Stage 2 -> 3]: {notes}"
        cycle.save()

        logger.info(f"Cycle #{cycle.cycle_reference} advanced to STAGE_3_WITHDRAW ({xlm_amt:,.4f} XLM ready for withdrawal).")
        return {'success': True, 'cycle_id': cycle.id, 'stage': cycle.stage}

    @classmethod
    def verify_and_complete_on_chain(
        cls,
        cycle_id: int,
        stellar_tx_hash: str = None,
        binance_withdrawal_id: str = None,
        network_fee_xlm: Decimal = None,
        force_auto_detect: bool = False
    ) -> dict:
        """
        Stage 4: Blockchain consensus confirmation via Stellar Horizon.
        Does NOT rely on manual input or synthetic balance assumption.
        Validates the Stellar ledger transaction directly on-chain, confirms delivery to
        GBYCZO2R2QPLJ4DD2YMYSWSGTOVSFTHI3H22KZVK6DSHENLAJ5MBW4TY, sets STAGE_4_COMPLETED,
        and refreshes the live vault balance straight from the blockchain.
        """
        with transaction.atomic():
            cycle = XLMLiquidityFundingRecord.objects.select_for_update().get(id=cycle_id)
            if cycle.stage == XLMFundingStage.STAGE_4_COMPLETED and cycle.on_chain_verified:
                return {
                    'success': True,
                    'already_completed': True,
                    'message': 'Cycle is already verified on-chain and completed.',
                    'tx_hash': cycle.stellar_tx_hash,
                }

            if cycle.stage not in [XLMFundingStage.STAGE_3_WITHDRAW, XLMFundingStage.STAGE_4_COMPLETED]:
                raise ValueError(f"Cycle #{cycle.cycle_reference} is in stage '{cycle.stage}', must be in Stage 3 (Withdrawal) to verify on-chain.")

            tx_hash = (stellar_tx_hash or cycle.stellar_tx_hash or "").strip()
            if not tx_hash:
                raise ValueError("Stellar blockchain transaction hash (Tx Hash) is required for on-chain verification.")

            if binance_withdrawal_id:
                cycle.binance_withdrawal_id = str(binance_withdrawal_id).strip()
            if network_fee_xlm is not None:
                cycle.network_fee_xlm = Decimal(str(network_fee_xlm))

            cycle.stellar_tx_hash = tx_hash
            cycle.save(update_fields=['stellar_tx_hash', 'binance_withdrawal_id', 'network_fee_xlm', 'updated_at'])

        # Query Stellar Horizon blockchain outside of DB lock to prevent connection pool exhaustion
        verif = StellarService.verify_xlm_payment_on_chain(
            tx_hash=tx_hash,
            expected_destination=MASTER_VAULT_ADDRESS,
            expected_amount=cycle.xlm_acquired
        )

        if not verif.get('verified'):
            return {
                'success': False,
                'error': verif.get('error', 'Blockchain on-chain verification failed.')
            }

        # Successful on-chain confirmation: Update database atomically and sync vault live balance
        with transaction.atomic():
            cycle = XLMLiquidityFundingRecord.objects.select_for_update().get(id=cycle_id)
            cycle.on_chain_verified = True
            cycle.on_chain_verified_at = timezone.now()
            cycle.stellar_ledger_sequence = verif.get('ledger')
            cycle.stellar_net_xlm_sent = verif.get('net_xlm_received')
            cycle.stage = XLMFundingStage.STAGE_4_COMPLETED

            # Sync vault live on-chain balance immediately
            vault = StellarWallet.objects.filter(public_address=MASTER_VAULT_ADDRESS).first()
            if vault:
                try:
                    StellarService.sync_wallet(vault)
                    vault.refresh_from_db()
                    cycle.vault_balance_after_xlm = vault.native_xlm_balance
                except Exception as e:
                    logger.warning(f"Failed to sync vault balance post-verification: {e}")

            cycle.save()

        logger.info(
            f"Successfully verified XLM cycle #{cycle.cycle_reference} on Stellar Horizon. "
            f"Delivered: {cycle.stellar_net_xlm_sent:,.4f} XLM on ledger #{cycle.stellar_ledger_sequence}."
        )

        return {
            'success': True,
            'cycle_id': cycle.id,
            'cycle_reference': cycle.cycle_reference,
            'stage': cycle.stage,
            'tx_hash': cycle.stellar_tx_hash,
            'net_xlm_received': float(cycle.stellar_net_xlm_sent or 0.0),
            'ledger': cycle.stellar_ledger_sequence,
            'vault_new_xlm_balance': float(cycle.vault_balance_after_xlm or 0.0),
        }
