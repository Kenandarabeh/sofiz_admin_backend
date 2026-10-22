"""
Stellar Horizon API Service for SofizAdmin Financial Monitoring
Specifically queries live DZT and XLM balances for all registered Stellar wallets.
"""
import logging
import uuid
from decimal import Decimal
from django.utils import timezone
import httpx
import time
from ..models import StellarWallet, MonitoringGlobalSettings, WalletSweepLog, SweepStatus, SweepType, WalletRole

logger = logging.getLogger(__name__)

# Institutional Persistent Connection Pool for Stellar Horizon
_HTTP_LIMITS = httpx.Limits(max_keepalive_connections=25, max_connections=35)
_HTTP_TIMEOUT = httpx.Timeout(4.5, connect=3.0)
_SHARED_CLIENT = None


def get_shared_client() -> httpx.Client:
    """Provides a thread-safe persistent HTTP/1.1 client with keep-alive connections to Stellar Horizon"""
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None or _SHARED_CLIENT.is_closed:
        _SHARED_CLIENT = httpx.Client(limits=_HTTP_LIMITS, timeout=_HTTP_TIMEOUT)
    return _SHARED_CLIENT


class StellarService:
    # 6.0 seconds consensus window matching Stellar SCP 5-second ledger closure time
    _consensus_cache = {}  # {public_address: (timestamp, dict)}
    _CACHE_WINDOW_SEC = 6.0

    @classmethod
    def get_account_balances(
        cls,
        public_address: str,
        horizon_url: str = None,
        target_dzt_code: str = None,
        target_dzt_issuer: str = None,
        client: httpx.Client = None,
        force: bool = False
    ) -> dict:
        """
        Query public account info directly from live Stellar Horizon API on-chain.
        Returns:
            dict: {"dzt": Decimal, "xlm": Decimal, "all_assets": list, "raw": dict}
        """
        now = time.time()
        if not force and public_address in cls._consensus_cache:
            cached_ts, cached_data = cls._consensus_cache[public_address]
            if now - cached_ts < cls._CACHE_WINDOW_SEC:
                return cached_data

        if not horizon_url or target_dzt_code is None or target_dzt_issuer is None:
            settings = MonitoringGlobalSettings.get_settings()
            base_url = horizon_url or settings.stellar_horizon_url.rstrip('/')
            dzt_code = (target_dzt_code or settings.dzt_asset_code).upper()
            dzt_issuer = (target_dzt_issuer if target_dzt_issuer is not None else settings.dzt_asset_issuer).strip()
        else:
            base_url = horizon_url.rstrip('/')
            dzt_code = target_dzt_code.upper()
            dzt_issuer = target_dzt_issuer.strip()

        url = f"{base_url}/accounts/{public_address}"

        http_client = client or get_shared_client()
        response = http_client.get(url)

        if response.status_code == 404:
            raise ValueError(f"Stellar account not found / not funded: {public_address}")
        elif response.status_code != 200:
            raise ValueError(f"Horizon API error ({response.status_code}): {response.text}")
        
        data = response.json()
        balances = data.get("balances", [])
        
        dzt_balance = Decimal("0.0000")
        xlm_balance = Decimal("0.0000")
        all_assets = []
        
        for b in balances:
            asset_type = b.get("asset_type")
            balance_val = Decimal(str(b.get("balance", "0")))
            
            if asset_type == "native":
                xlm_balance = balance_val
                all_assets.append({"code": "XLM", "issuer": "native", "balance": balance_val})
            else:
                code = b.get("asset_code", "")
                issuer = b.get("asset_issuer", "")
                all_assets.append({"code": code, "issuer": issuer, "balance": balance_val})
                
                # Match DZT asset code and issuer if specified
                if code.upper() == dzt_code:
                    if not dzt_issuer or issuer == dzt_issuer:
                        dzt_balance += balance_val

        result = {
            "dzt": dzt_balance,
            "xlm": xlm_balance,
            "all_assets": all_assets,
            "sequence": data.get("sequence"),
            "subentry_count": data.get("subentry_count"),
        }
        cls._consensus_cache[public_address] = (now, result)
        return result

    @classmethod
    def sync_wallet(cls, wallet: StellarWallet, client: httpx.Client = None, force: bool = False) -> dict:
        """
        Sync a single Stellar wallet directly from live Stellar Horizon on-chain API.
        Strict institutional standard: Blockchain consensus is the single source of truth.
        """
        try:
            res = cls.get_account_balances(wallet.public_address, client=client, force=force)
            # Blockchain is absolute truth: always record exact on-chain balance
            wallet.dzt_balance = res["dzt"]
            wallet.native_xlm_balance = res.get("xlm", Decimal("0.0000000"))
            wallet.last_synced_at = timezone.now()
            wallet.last_error = None
            wallet.save(update_fields=['dzt_balance', 'native_xlm_balance', 'last_synced_at', 'last_error', 'updated_at'])
            return {
                "success": True,
                "wallet": wallet,
                "dzt": wallet.dzt_balance,
                "xlm": wallet.native_xlm_balance,
                "on_chain": True
            }
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Live Stellar Horizon sync failed for wallet '{wallet.name}' ({wallet.public_address}): {error_msg}")
            wallet.dzt_balance = Decimal("0.0000")
            wallet.last_synced_at = timezone.now()
            wallet.last_error = f"Blockchain Error: {error_msg}"
            try:
                wallet.save(update_fields=['dzt_balance', 'last_synced_at', 'last_error', 'updated_at'])
            except Exception:
                pass
            return {
                "success": False,
                "wallet": wallet,
                "dzt": Decimal("0.0000"),
                "xlm": Decimal("0.0000000"),
                "error": error_msg,
                "blockchain_error": True
            }

    @classmethod
    def sync_wallets_parallel(cls, wallets: list, force: bool = False) -> list:
        """
        Sync a list of Stellar wallets directly from live Stellar Horizon on-chain API in parallel.
        Uses persistent HTTP connection pool and concurrent ThreadPoolExecutor for HTTP queries ONLY.
        Database persistence occurs in the calling thread to guarantee zero PostgreSQL connection leaks.
        """
        if not wallets:
            return []
        from concurrent.futures import ThreadPoolExecutor

        client = get_shared_client()
        settings = MonitoringGlobalSettings.get_settings()
        horizon_url = settings.stellar_horizon_url.rstrip('/')
        target_dzt_code = settings.dzt_asset_code.upper()
        target_dzt_issuer = settings.dzt_asset_issuer.strip()

        def _fetch_balance(w):
            try:
                res = cls.get_account_balances(
                    w.public_address,
                    horizon_url=horizon_url,
                    target_dzt_code=target_dzt_code,
                    target_dzt_issuer=target_dzt_issuer,
                    client=client,
                    force=force
                )
                return {"success": True, "res": res}
            except Exception as e:
                return {"success": False, "error": str(e)}
            finally:
                try:
                    from django import db
                    db.connections.close_all()
                except Exception:
                    pass

        max_workers = min(4, len(wallets))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            fetch_results = list(executor.map(_fetch_balance, wallets))

        now = timezone.now()
        output_results = []
        wallets_to_save = []
        for wallet, item in zip(wallets, fetch_results):
            if item.get("success"):
                res = item["res"]
                wallet.dzt_balance = res["dzt"]
                wallet.native_xlm_balance = res.get("xlm", Decimal("0.0000000"))
                wallet.last_synced_at = now
                wallet.last_error = None
                output_results.append({
                    "success": True,
                    "wallet": wallet,
                    "dzt": wallet.dzt_balance,
                    "xlm": wallet.native_xlm_balance,
                    "on_chain": True
                })
            else:
                err = item.get("error", "Unknown error")
                logger.warning(f"Live Stellar Horizon sync failed for wallet '{wallet.name}' ({wallet.public_address}): {err}")
                wallet.dzt_balance = Decimal("0.0000")
                wallet.last_synced_at = now
                wallet.last_error = f"Blockchain Error: {err}"
                output_results.append({
                    "success": False,
                    "wallet": wallet,
                    "dzt": Decimal("0.0000"),
                    "xlm": Decimal("0.0000000"),
                    "error": err,
                    "blockchain_error": True
                })
            wallets_to_save.append(wallet)

        # Persist updated balances in database using caller's connection
        try:
            StellarWallet.objects.bulk_update(
                wallets_to_save,
                ['dzt_balance', 'native_xlm_balance', 'last_synced_at', 'last_error', 'updated_at']
            )
        except Exception:
            for w in wallets_to_save:
                try:
                    w.save(update_fields=['dzt_balance', 'native_xlm_balance', 'last_synced_at', 'last_error', 'updated_at'])
                except Exception as save_err:
                    logger.error(f"Failed to persist wallet {w.name} in DB: {save_err}")

        return output_results

    @classmethod
    def sync_all_wallets(cls, force: bool = False, *args, **kwargs) -> list:
        """Sync all active Stellar wallets in parallel directly from live Stellar Horizon on-chain"""
        wallets = list(StellarWallet.objects.filter(is_active=True))
        return cls.sync_wallets_parallel(wallets, force=force)

    @classmethod
    def verify_xlm_payment_on_chain(
        cls,
        tx_hash: str,
        expected_destination: str = "GBYCZO2R2QPLJ4DD2YMYSWSGTOVSFTHI3H22KZVK6DSHENLAJ5MBW4TY",
        expected_amount: Decimal = None
    ) -> dict:
        """
        Directly checks Stellar Horizon blockchain consensus for an on-chain payment.
        Verifies transaction status, destination address, and native XLM delivered.
        """
        if not tx_hash or len(tx_hash.strip()) < 10:
            return {'verified': False, 'error': 'Invalid transaction hash provided.'}

        clean_hash = tx_hash.strip().lower()
        horizon_url = MonitoringGlobalSettings.get_settings().stellar_horizon_url.rstrip('/')
        
        try:
            with httpx.Client(timeout=6.0) as client:
                # 1. Fetch transaction record
                tx_res = client.get(f"{horizon_url}/transactions/{clean_hash}")
                if tx_res.status_code == 404:
                    return {'verified': False, 'error': 'Transaction hash not found on Stellar blockchain.'}
                if tx_res.status_code != 200:
                    return {'verified': False, 'error': f"Horizon error: {tx_res.text}"}

                tx_data = tx_res.json()
                if not tx_data.get('successful', False):
                    return {'verified': False, 'error': 'Transaction is marked as FAILED on Stellar blockchain.'}

                ledger = tx_data.get('ledger')
                created_at = tx_data.get('created_at')

                # 2. Fetch operations for this transaction
                ops_res = client.get(f"{horizon_url}/transactions/{clean_hash}/operations")
                if ops_res.status_code != 200:
                    return {'verified': False, 'error': 'Failed to retrieve operations for transaction hash.'}

                ops_data = ops_res.json()
                records = ops_data.get('_embedded', {}).get('records', [])

                net_xlm_received = Decimal('0.0000000')
                matched_dest = False

                for op in records:
                    op_type = op.get('type')
                    # Standard payment or account creation (which funds native XLM)
                    if op_type == 'payment':
                        dest = op.get('to')
                        asset_type = op.get('asset_type')
                        if dest == expected_destination and asset_type == 'native':
                            matched_dest = True
                            net_xlm_received += Decimal(str(op.get('amount', '0')))
                    elif op_type == 'create_account':
                        dest = op.get('account')
                        if dest == expected_destination:
                            matched_dest = True
                            net_xlm_received += Decimal(str(op.get('starting_balance', '0')))

                if not matched_dest or net_xlm_received <= 0:
                    return {
                        'verified': False,
                        'error': f"Transaction does not contain a native XLM payment to expected vault {expected_destination}."
                    }

                return {
                    'verified': True,
                    'tx_hash': clean_hash,
                    'ledger': ledger,
                    'created_at': created_at,
                    'destination': expected_destination,
                    'net_xlm_received': net_xlm_received,
                    'raw_tx': tx_data
                }
        except Exception as e:
            logger.error(f"Error querying Stellar Horizon for tx {clean_hash}: {e}")
            return {'verified': False, 'error': f"Horizon connection failure: {str(e)}"}

    @classmethod
    def send_payment(
        cls,
        source_wallet: StellarWallet = None,
        destination_wallet: StellarWallet = None,
        source_seed: str = None,
        destination_address: str = None,
        amount: Decimal = Decimal("0.00"),
        asset_code: str = None,
        asset_issuer: str = None,
        memo_text: str = None,
        sweep_type: str = SweepType.SWEEP_TRANSFER,
    ) -> dict:
        """
        Executes an audited DZT/XLM liquidity payment from a source collection wallet to a destination vault wallet.
        - Uses live Stellar Horizon SDK if source_seed is configured.
        - Safely executes atomic internal ledger debit/credit and logs WalletSweepLog if secret seed is in cold storage.
        - Returns {'success': True, 'hash': ..., 'amount': ...}
        """
        amount = Decimal(str(amount or 0))
        if amount <= Decimal("0.00"):
            return {'success': False, 'error': 'Transfer amount must be greater than zero.'}

        settings = MonitoringGlobalSettings.get_settings()

        # Resolve Source Wallet
        if not source_wallet and source_seed:
            try:
                from stellar_sdk import Keypair
                source_pub = Keypair.from_secret(source_seed.strip()).public_key
                source_wallet = StellarWallet.objects.filter(public_address=source_pub).first()
            except Exception:
                source_wallet = None
        if not source_wallet:
            source_wallet = settings.games_collection_wallet or StellarWallet.objects.filter(category='GAMING', is_active=True).first()

        # Check if pure withdrawal/outflow (receipt already sent outside, no destination wallet to credit)
        is_pure_withdrawal = (
            sweep_type in ['WITHDRAWAL', 'LIQUIDITY_REFILL', SweepType.WITHDRAWAL]
            or (destination_wallet is None and not destination_address)
        )

        if not is_pure_withdrawal:
            # Resolve Destination Wallet (Central Treasury Master Vault) for internal transfers
            if not destination_wallet and destination_address:
                destination_wallet = StellarWallet.objects.filter(public_address=destination_address).first()
            if not destination_wallet:
                destination_wallet = settings.central_treasury_wallet or StellarWallet.objects.filter(category__in=['TREASURY', 'SWEEP_VAULT'], is_active=True).first()

            dest_addr = destination_address or (destination_wallet.public_address if destination_wallet else None)
            if not dest_addr:
                return {'success': False, 'error': 'Destination wallet address is not configured.'}

            if source_wallet and destination_wallet and source_wallet.id == destination_wallet.id:
                return {'success': True, 'same_wallet': True, 'hash': None, 'amount': amount, 'message': 'Source and destination wallets are identical.'}
        else:
            destination_wallet = None
            dest_addr = None

        code = (asset_code or settings.dzt_asset_code).strip().upper()
        issuer = (asset_issuer or settings.dzt_asset_issuer).strip()
        src_seed = (source_seed or (source_wallet.secret_seed if source_wallet else None) or '').strip()

        from django.db import transaction as db_transaction
        import uuid

        # Check if valid Stellar private key is present
        has_secret = bool(src_seed.startswith('S') and len(src_seed) == 56)
        on_chain_success = False
        tx_hash = None
        on_chain_error = None
        is_on_chain = False

        # 1. Enforce atomic row-level locking & liquidity validation across all pathways
        try:
            with db_transaction.atomic():
                if source_wallet:
                    locked_source = StellarWallet.objects.select_for_update().get(id=source_wallet.id)
                    if locked_source.dzt_balance < amount:
                        err_msg = (
                            f"Insufficient liquidity in source wallet '{locked_source.name}'. "
                            f"Available: {locked_source.dzt_balance:,.2f} DZT, Requested: {amount:,.2f} DZT."
                        )
                        logger.warning(err_msg)
                        return {'success': False, 'error': err_msg}

                # 2. Attempt On-Chain Stellar Submission if secret key is configured
                if has_secret:
                    try:
                        from stellar_sdk import Server, Keypair, TransactionBuilder, Network, Asset
                        from stellar_sdk.exceptions import BadResponseError, ConnectionError as StellarConnError, NotFoundError
                        import requests

                        horizon_url = settings.stellar_horizon_url.rstrip('/')
                        server = Server(horizon_url=horizon_url)
                        source_kp = Keypair.from_secret(src_seed)
                        source_account = server.load_account(source_kp.public_key)
                        
                        # Dynamic fee with congestion buffer (2x base fee, min 200 stroops)
                        base_fee = max(server.fetch_base_fee() * 2, 200)

                        if code != 'XLM' and issuer:
                            asset = Asset(code, issuer)
                        else:
                            asset = Asset.native()

                        builder = TransactionBuilder(
                            source_account=source_account,
                            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                            base_fee=base_fee
                        ).append_payment_op(
                            destination=dest_addr,
                            asset=asset,
                            amount=f"{amount:.4f}"
                        ).set_timeout(30)

                        if memo_text:
                            builder.add_text_memo(str(memo_text)[:28])

                        tx = builder.build()
                        tx.sign(source_kp)
                        
                        # Pre-compute deterministic transaction hash BEFORE sending to network
                        tx_hash = tx.hash_hex()

                        try:
                            resp = server.submit_transaction(tx)
                            tx_hash = resp.get('hash', tx_hash)
                            on_chain_success = True
                            is_on_chain = True
                            logger.info(f"On-chain Stellar transfer confirmed: {amount} {code} -> {dest_addr} (TX Hash: {tx_hash})")
                        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, StellarConnError) as net_err:
                            # Network Timeout Recovery: Probe Horizon to verify if tx closed in ledger
                            logger.warning(f"Stellar Horizon submission timed out for tx {tx_hash}. Querying ledger to confirm status...")
                            try:
                                confirmed_tx = server.transactions().transaction(tx_hash)
                                if confirmed_tx and confirmed_tx.get('successful'):
                                    on_chain_success = True
                                    is_on_chain = True
                                    logger.info(f"Recovered on-chain Stellar tx {tx_hash} from ledger after network timeout.")
                                else:
                                    on_chain_error = f"Stellar transaction {tx_hash} failed on ledger after timeout."
                            except NotFoundError:
                                on_chain_error = f"Stellar transaction {tx_hash} was not found on ledger following network timeout."
                            except Exception as probe_err:
                                on_chain_error = f"Stellar timeout recovery probe failed: {probe_err}"

                        except BadResponseError as bre:
                            # Extract granular Stellar error codes (e.g. op_underfunded, op_no_trust, tx_bad_seq)
                            result_codes = getattr(bre, 'extras', {}).get('result_codes', {}) if hasattr(bre, 'extras') else {}
                            tx_code = result_codes.get('transaction', 'tx_unknown')
                            op_codes = result_codes.get('operations', [])
                            on_chain_error = f"Stellar on-chain rejection [tx={tx_code}, ops={op_codes}]: {bre}"
                            logger.error(on_chain_error)

                    except Exception as e:
                        on_chain_error = f"Stellar setup/pre-flight error: {e}"
                        logger.warning(f"On-chain Stellar error: {on_chain_error}. Falling back to audited internal ledger...")

                # 3. Post-execution balance adjustment & audit log creation
                if on_chain_success:
                    # Live on-chain execution succeeded: sync balances
                    if source_wallet:
                        cls.sync_wallet(source_wallet)
                    if destination_wallet:
                        cls.sync_wallet(destination_wallet)

                    log_entry = WalletSweepLog.objects.create(
                        source_wallet=source_wallet,
                        destination_wallet=destination_wallet,
                        amount_dzt=amount,
                        sweep_type=sweep_type,
                        stellar_tx_hash=tx_hash,
                        status=SweepStatus.SUCCESS,
                        error_details=f"On-chain Stellar payment confirmed. Memo: {memo_text or 'N/A'}"
                    )
                else:
                    # Audited internal ledger debit/credit with row lock
                    if source_wallet:
                        locked_source.dzt_balance -= amount
                        locked_source.save(update_fields=['dzt_balance'])
                        source_wallet.dzt_balance = locked_source.dzt_balance

                    if destination_wallet and not is_pure_withdrawal:
                        locked_dest = StellarWallet.objects.select_for_update().get(id=destination_wallet.id)
                        locked_dest.dzt_balance += amount
                        locked_dest.save(update_fields=['dzt_balance'])
                        destination_wallet.dzt_balance = locked_dest.dzt_balance

                    tx_hash = tx_hash or (f"WITHDRAWAL-DZT-{uuid.uuid4().hex[:16].upper()}" if is_pure_withdrawal else f"INTERNAL-DZT-{uuid.uuid4().hex[:16].upper()}")
                    audit_msg = f"Audited internal withdrawal executed. Memo: {memo_text or 'N/A'}" if is_pure_withdrawal else f"Audited internal treasury transfer completed. Memo: {memo_text or 'N/A'}"
                    if on_chain_error:
                        audit_msg += f" | On-chain fallback note: {on_chain_error}"

                    log_entry = WalletSweepLog.objects.create(
                        source_wallet=source_wallet,
                        destination_wallet=destination_wallet if not is_pure_withdrawal else None,
                        amount_dzt=amount,
                        sweep_type='WITHDRAWAL' if is_pure_withdrawal else sweep_type,
                        stellar_tx_hash=tx_hash,
                        status=SweepStatus.SUCCESS,
                        error_details=audit_msg
                    )

            logger.info(f"Liquidity withdrawal/transfer executed: {amount} DZT from {getattr(source_wallet, 'name', 'Source')} (Ref: {tx_hash}, On-Chain: {is_on_chain})")
            return {
                'success': True,
                'is_on_chain': is_on_chain,
                'hash': tx_hash,
                'amount': amount,
                'log_id': log_entry.id,
                'warning': on_chain_error if not is_on_chain and has_secret else None
            }
        except Exception as e:
            err_msg = f"Transfer database transaction failed: {e}"
            logger.error(err_msg)
            return {'success': False, 'error': err_msg}

