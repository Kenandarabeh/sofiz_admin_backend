import json
import logging
from decimal import Decimal, ROUND_HALF_UP
import requests
from django.utils import timezone
from django.db import transaction as db_transaction
from django.conf import settings

from monitoring.models import (
    FlexyFundingTranche,
    FlexyOperationRecord,
    FlexyDualSweepBatch,
    WithdrawalRecord,
    WithdrawalPurpose,
    WithdrawalStage,
    WithdrawalType,
    SubSystemType,
    StellarWallet,
    WalletFamily,
    WalletRole,
    MonitoringGlobalSettings,
)

logger = logging.getLogger(__name__)


class ShemsnetService:
    """
    Institutional integration service for Shemsnet telecom gateway.
    Handles automated top-ups via Stellar Horizon, live balance/bonus polling,
    and FIFO tranche-based profit and cost segregation.
    """
    BASE_URL = "https://shemsnet.com"
    DEFAULT_USERNAME = "sofizpay"
    DEFAULT_PASSWORD = "DYbWY2Soagan"

    _session = None

    @classmethod
    def get_authenticated_session(cls) -> requests.Session:
        """
        Maintains an authenticated HTTP session with Shemsnet.
        Automatically logs in or refreshes if credentials expire.
        """
        if cls._session is not None:
            # Verify session validity with quick lightweight probe
            try:
                probe = cls._session.get(f"{cls.BASE_URL}/user-info/", timeout=4.0)
                if probe.status_code == 200:
                    return cls._session
            except Exception:
                pass

        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SofizAdmin Institutional Engine",
        })

        try:
            login_res = session.post(
                f"{cls.BASE_URL}/login/",
                json={"username": cls.DEFAULT_USERNAME, "password": cls.DEFAULT_PASSWORD},
                timeout=7.0
            )
            if login_res.status_code == 200:
                cls._session = session
                return session
            else:
                logger.error(f"Shemsnet login failed with status {login_res.status_code}: {login_res.text}")
                raise ConnectionError(f"Shemsnet login failed: {login_res.text}")
        except Exception as e:
            logger.error(f"Error establishing session with Shemsnet: {e}")
            raise

    @classmethod
    def get_live_user_status(cls) -> dict:
        """
        Fetches current operational cash balance, bonus balance, and bonus rates from Shemsnet.
        """
        session = cls.get_authenticated_session()
        res = session.get(f"{cls.BASE_URL}/user-info/", timeout=6.0)
        if res.status_code != 200:
            raise ConnectionError(f"Failed to fetch Shemsnet user status: {res.status_code} {res.text}")

        data = res.json()
        user_info = data.get("user", {})

        # Query latest transactions to extract live effective bonus rates
        rates = cls.get_live_bonus_rates()

        return {
            "success": True,
            "username": user_info.get("username", "sofizpay"),
            "operational_balance_dzd": float(Decimal(str(user_info.get("balance", "0.00")))),
            "accrued_bonus_dzd": float(Decimal(str(user_info.get("bonus", "0.00")))),
            "unclaimed_bonuses_count": int(user_info.get("unclaimed_bonuses", 0)),
            "rates": rates,
        }

    @classmethod
    def get_live_bonus_rates(cls) -> dict:
        """
        Inspects the active/latest recharge lot on Shemsnet to extract exact current bonus rates.
        Fallback to institutional baseline rates if no active lot exists.
        """
        fallback_rates = {
            "mobilis": 2.5000,
            "pixx": 5.0000,
            "djezzy": 0.5000,
            "ooredoo": 1.0000,
        }
        try:
            session = cls.get_authenticated_session()
            tx_res = session.get(f"{cls.BASE_URL}/transactions/", timeout=6.0)
            if tx_res.status_code == 200:
                data = tx_res.json()
                batches = data.get("transactions", [])
                if batches:
                    latest = batches[0]
                    return {
                        "mobilis": float(Decimal(str(latest.get("mobilis_bonus", "2.5000")))),
                        "pixx": float(Decimal(str(latest.get("pixx_bonus", "5.0000")))),
                        "djezzy": float(Decimal(str(latest.get("djezzy_bonus", "0.5000")))),
                        "ooredoo": float(Decimal(str(latest.get("ooredoo_bonus", "1.0000")))),
                    }
        except Exception as e:
            logger.warning(f"Could not fetch dynamic bonus rates from Shemsnet, using baseline: {e}")

        return fallback_rates

    @classmethod
    def sync_operations_feed(cls, max_pages: int = 5, limit: int = 100) -> dict:
        """
        Polls recent operations across multiple pages from Shemsnet, stores new records in database,
        and applies FIFO tranche consumption to accurately calculate procurement cost and net profit.
        """
        session = cls.get_authenticated_session()
        all_operations = []

        for page in range(1, max_pages + 1):
            try:
                res = session.get(f"{cls.BASE_URL}/operations/?page={page}", timeout=8.0)
                if res.status_code != 200:
                    break
                data = res.json()
                page_ops = data.get("operations", [])
                if not page_ops:
                    break
                all_operations.extend(page_ops)

                # Check if all operations on this page already exist in DB
                page_ids = [str(op.get("operation_id")) for op in page_ops if op.get("operation_id")]
                if page_ids:
                    existing_count = FlexyOperationRecord.objects.filter(shemsnet_op_id__in=page_ids).count()
                    if existing_count == len(page_ids):
                        # Stop fetching further pages since older records are already saved
                        break
            except Exception as e:
                logger.warning(f"Error fetching page {page} from Shemsnet operations: {e}")
                break

        if not all_operations:
            return {"success": True, "synced_count": 0, "new_count": 0}

        # Order operations from oldest to newest to ensure proper FIFO allocation
        operations = sorted(all_operations, key=lambda x: x.get("operation_id", 0))

        synced_count = 0
        new_count = 0

        with db_transaction.atomic():
            # Get active tranches locked for update
            active_tranches = list(
                FlexyFundingTranche.objects.select_for_update()
                .filter(is_active=True, remaining_balance_dzd__gt=Decimal("0.00"))
                .order_by("created_at")
            )

            # Fallback rate if no tranches are present in database
            live_rates = cls.get_live_bonus_rates()

            for op in operations[:limit]:
                op_id = str(op.get("operation_id"))
                if FlexyOperationRecord.objects.filter(shemsnet_op_id=op_id).exists():
                    synced_count += 1
                    continue

                raw_operator = str(op.get("operator", "MOBILIS")).strip().upper()
                face_amount = Decimal(str(op.get("amount", "0.00"))).quantize(Decimal("0.01"))
                phone = str(op.get("phone", ""))
                op_status = str(op.get("status", "success")).upper()
                created_at_str = op.get("created_at")

                from django.utils.dateparse import parse_datetime
                op_created_at = parse_datetime(created_at_str) if created_at_str else timezone.now()
                if not op_created_at:
                    op_created_at = timezone.now()
                elif timezone.is_naive(op_created_at):
                    op_created_at = timezone.make_aware(op_created_at, timezone.get_current_timezone())

                operator_key = raw_operator.lower()
                applied_bonus_pct = Decimal(str(live_rates.get(operator_key, 2.5)))
                allocated_tranche = None

                # FIFO Allocation across active tranches
                if op_status == "SUCCESS" and active_tranches:
                    for tranche in active_tranches:
                        if tranche.remaining_balance_dzd <= Decimal("0.00"):
                            tranche.is_active = False
                            tranche.save(update_fields=["is_active", "remaining_balance_dzd", "updated_at"])
                            continue

                        # Extract rate from tranche
                        if operator_key == "pixx":
                            applied_bonus_pct = tranche.bonus_pixx_pct
                        elif operator_key == "djezzy":
                            applied_bonus_pct = tranche.bonus_djezzy_pct
                        elif operator_key == "ooredoo":
                            applied_bonus_pct = tranche.bonus_ooredoo_pct
                        else:
                            applied_bonus_pct = tranche.bonus_mobilis_pct

                        allocated_amount = min(face_amount, tranche.remaining_balance_dzd)
                        tranche.remaining_balance_dzd = (tranche.remaining_balance_dzd - allocated_amount).quantize(Decimal("0.01"))
                        if tranche.remaining_balance_dzd <= Decimal("0.00"):
                            tranche.is_active = False

                        tranche.save(update_fields=["remaining_balance_dzd", "is_active", "updated_at"])
                        allocated_tranche = tranche
                        break

                # Precise cost & profit calculation:
                # Cost = Amount / (1 + Bonus_Rate)
                # Profit = Amount - Cost
                divisor = Decimal("1.00") + (applied_bonus_pct / Decimal("100.00"))
                cost = (face_amount / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                profit = (face_amount - cost).quantize(Decimal("0.01"))

                import uuid
                op_ref = f"FLX-OP-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

                FlexyOperationRecord.objects.create(
                    operation_reference=op_ref,
                    shemsnet_op_id=op_id,
                    operator=raw_operator,
                    phone_number=phone,
                    face_amount_dzd=face_amount,
                    procurement_cost_dzd=cost,
                    net_profit_dzd=profit,
                    applied_bonus_pct=applied_bonus_pct,
                    tranche=allocated_tranche,
                    status=op_status,
                    raw_response=op,
                    created_at=op_created_at,
                )
                new_count += 1
                synced_count += 1

        return {
            "success": True,
            "synced_count": synced_count,
            "new_count": new_count,
        }

    @classmethod
    def execute_automated_topup(cls, amount_dzt: Decimal, source_wallet_id: int, executed_by_user=None) -> dict:
        """
        Executes a One-Click Automated Refill from the Treasury DZT wallet to Shemsnet.
        1. Requests deposit address & memo from Shemsnet API (/sofizpay-address/).
        2. Submits on-chain DZT payment on Stellar Horizon with the memo.
        3. Calls Shemsnet /handle-sofizpay-payment/ with transaction hash to credit DZD balance immediately.
        4. Logs WithdrawalRecord and creates a new FlexyFundingTranche with locked-in bonus rates.
        """
        from decimal import Decimal
        amount_dzt = Decimal(str(amount_dzt)).quantize(Decimal("0.01"))
        if amount_dzt <= Decimal("0.00"):
            return {"success": False, "error": "Refill amount must be greater than zero."}

        # Resolve Source Wallet: Strictly mandatory dedicated Flexy Collection & Withdrawal Wallet
        source_wallet = StellarWallet.objects.filter(
            family=WalletFamily.FLEXY,
            role=WalletRole.WITHDRAWAL,
            is_active=True
        ).first()

        # Fallback to specific Flexy wallet if configured
        if not source_wallet and source_wallet_id:
            source_wallet = StellarWallet.objects.filter(id=source_wallet_id, family=WalletFamily.FLEXY, is_active=True).first()

        if not source_wallet:
            source_wallet = StellarWallet.objects.filter(
                family=WalletFamily.FLEXY,
                role=WalletRole.COLLECTION,
                is_active=True
            ).first()

        if not source_wallet:
            return {"success": False, "error": "Mandatory Flexy Collection & Withdrawal Wallet not found or inactive."}

        if source_wallet.dzt_balance < amount_dzt:
            return {
                "success": False,
                "error": f"Insufficient liquidity in withdrawal funding wallet '{source_wallet.name}'. Available: {source_wallet.dzt_balance:,.2f} DZT, Requested: {amount_dzt:,.2f} DZT."
            }

        session = cls.get_authenticated_session()

        # Step 1: Request Shemsnet Deposit Address and Unique Memo
        addr_res = session.get(f"{cls.BASE_URL}/sofizpay-address/", timeout=8.0)
        if addr_res.status_code != 200:
            return {"success": False, "error": f"Shemsnet rejected address request: {addr_res.text}"}

        addr_data = addr_res.json()
        shemsnet_address = addr_data.get("address")
        shemsnet_memo = addr_data.get("memo")

        if not shemsnet_address or not shemsnet_memo:
            return {"success": False, "error": f"Shemsnet returned invalid address or memo: {addr_data}"}

        # Step 2: Execute Stellar On-Chain Payment
        global_settings = MonitoringGlobalSettings.get_settings()
        dzt_code = (global_settings.dzt_asset_code or "DZT").strip()
        dzt_issuer = (global_settings.dzt_asset_issuer or "GCAZI7YBLIDJWIVEL7ETNAZGPP3LC24NO6KAOBWZHUERXQ7M5BC52DLV").strip()
        source_seed = (source_wallet.secret_seed or "").strip()

        if not source_seed or not source_seed.startswith("S") or len(source_seed) != 56:
            return {
                "success": False,
                "error": f"Treasury wallet '{source_wallet.name}' does not have a valid Stellar secret seed for automated signing."
            }

        try:
            from stellar_sdk import Server, Keypair, TransactionBuilder, Network, Asset, Memo, MemoType
            horizon_url = global_settings.stellar_horizon_url.rstrip("/")
            server = Server(horizon_url=horizon_url)

            source_kp = Keypair.from_secret(source_seed)
            source_account = server.load_account(source_kp.public_key)
            base_fee = max(server.fetch_base_fee() * 2, 200)

            asset = Asset(dzt_code, dzt_issuer)
            tx = (
                TransactionBuilder(
                    source_account=source_account,
                    network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                    base_fee=base_fee,
                )
                .append_payment_op(
                    destination=shemsnet_address,
                    asset=asset,
                    amount=str(amount_dzt),
                )
                .add_text_memo(str(shemsnet_memo))
                .set_timeout(30)
                .build()
            )
            tx.sign(source_kp)
            stellar_response = server.submit_transaction(tx)
            tx_hash = stellar_response.get("hash")
        except Exception as e:
            logger.error(f"Stellar Horizon submission failed during Shemsnet top-up: {e}")
            return {"success": False, "error": f"Stellar on-chain transaction failed: {str(e)}"}

        # Step 3: Confirm with Shemsnet Payment Handler
        try:
            confirm_payload = {
                "transaction_hash": tx_hash,
                "amount": str(amount_dzt),
            }
            confirm_res = session.post(f"{cls.BASE_URL}/handle-sofizpay-payment/", json=confirm_payload, timeout=10.0)
            confirm_data = confirm_res.json() if confirm_res.status_code == 200 else {}
        except Exception as e:
            logger.warning(f"Shemsnet confirm webhook responded with error: {e}")
            confirm_data = {"warning": str(e)}

        # Step 4: Atomic Database Recording (Withdrawal Record + Funding Tranche)
        import uuid
        batch_ref = f"FLX-TR-{timezone.now().strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:6].upper()}"
        live_rates = cls.get_live_bonus_rates()

        with db_transaction.atomic():
            # Update source wallet balance
            source_wallet.dzt_balance = (source_wallet.dzt_balance - amount_dzt).quantize(Decimal("0.0000001"))
            source_wallet.save(update_fields=["dzt_balance", "updated_at"])

            withdrawal = WithdrawalRecord.objects.create(
                title=f"Flexy Operational Refill Batch #{batch_ref}",
                reference=batch_ref,
                amount_dzd=amount_dzt,
                system_type=SubSystemType.FLEXY,
                purpose_code=WithdrawalPurpose.FLEXY_REFILL,
                withdrawal_type=WithdrawalType.LIQUIDITY_REFILL,
                stage=WithdrawalStage.COMPLETED,
                source_wallet=source_wallet,
                executed_by=executed_by_user,
                notes=(
                    f"Automated one-click refill to Shemsnet. Amount: {amount_dzt:,.2f} DZT. "
                    f"Stellar Tx: {tx_hash}. Memo: {shemsnet_memo}. Destination: {shemsnet_address}."
                ),
            )

            tranche = FlexyFundingTranche.objects.create(
                tranche_reference=batch_ref,
                initial_amount_dzd=amount_dzt,
                remaining_balance_dzd=amount_dzt,
                bonus_mobilis_pct=Decimal(str(live_rates.get("mobilis", 2.5))),
                bonus_pixx_pct=Decimal(str(live_rates.get("pixx", 5.0))),
                bonus_djezzy_pct=Decimal(str(live_rates.get("djezzy", 0.5))),
                bonus_ooredoo_pct=Decimal(str(live_rates.get("ooredoo", 1.0))),
                stellar_tx_hash=tx_hash,
                source_wallet=source_wallet,
                withdrawal_record=withdrawal,
                executed_by=executed_by_user,
                is_active=True,
                notes=f"Locked-in dynamic bonus rates at refill timestamp. Memo: {shemsnet_memo}.",
            )

        return {
            "success": True,
            "message": f"Successfully refilled {amount_dzt:,.2f} DZT to Shemsnet account.",
            "batch_reference": batch_ref,
            "amount_dzd": float(amount_dzt),
            "stellar_tx_hash": tx_hash,
            "shemsnet_memo": shemsnet_memo,
            "rates_applied": live_rates,
            "new_tranche_id": tranche.id,
            "withdrawal_id": withdrawal.id,
        }
