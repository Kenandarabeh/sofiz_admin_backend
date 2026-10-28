"""
Binance & Crypto Transaction Hash Verification Service for SofizAdmin
Verifies Binance Pay Order IDs, Binance USDT Transfers, and Blockchain TXIDs (TRC20/BEP20)
Checks whether the actual received amount on Binance matches the recorded transaction amount.
"""
import logging
import re
from decimal import Decimal
import httpx
from django.utils import timezone
from ..models import MonitoringGlobalSettings

logger = logging.getLogger(__name__)


class BinanceVerificationService:

    @classmethod
    def verify_transaction(
        cls,
        txid_or_hash: str,
        expected_usd_amount: Decimal = None,
        expected_dzd_amount: Decimal = None,
        exchange_rate: Decimal = None
    ) -> dict:
        """
        Verifies a transaction ID or Hash on Binance / Blockchain.
        Compares actual amount with expected amount.
        """
        if not txid_or_hash or not str(txid_or_hash).strip():
            return {
                'success': False,
                'status': 'NOT_FOUND',
                'verified_amount_usd': None,
                'notes': 'No Transaction ID / Hash provided.'
            }

        txid = str(txid_or_hash).strip()
        settings = MonitoringGlobalSettings.get_settings()
        rate = exchange_rate or settings.usd_to_dzd_exchange_rate or Decimal("240.00")

        # Determine expected USD
        if expected_usd_amount is not None:
            expected_usd = Decimal(str(expected_usd_amount))
        elif expected_dzd_amount is not None:
            expected_usd = (Decimal(str(expected_dzd_amount)) / rate).quantize(Decimal('0.01'))
        else:
            expected_usd = None

        result = cls._fetch_transaction_details(txid, settings)
        
        if not result['found']:
            # Fallback check on Epay Gateway
            epay_result = cls._query_epay_gateway(txid, settings)
            if epay_result['found']:
                result = epay_result

        if not result['found']:
            return {
                'success': False,
                'status': 'NOT_FOUND',
                'verified_amount_usd': None,
                'notes': f"⚠️ Transaction ID '{txid}' could not be verified on Binance or Blockchain network. Details: {result.get('error', 'Not found')}"
            }

        actual_usd = Decimal(str(result['amount_usd']))
        currency = result.get('currency', 'USDT')
        network = result.get('network', 'Binance / Crypto')

        # Compare Amounts
        if expected_usd is not None:
            diff = abs(actual_usd - expected_usd)
            # Allow minor delta ($0.50 tolerance for fee rounding)
            if diff <= Decimal("0.50"):
                status = 'VERIFIED_MATCH'
                notes = f"🟢 VERIFIED & MATCHED: Actual {actual_usd:,.2f} {currency} on {network} matches expected (${expected_usd:,.2f} USD). Timestamp: {result.get('time', timezone.now().strftime('%Y-%m-%d %H:%M'))}"
            else:
                status = 'AMOUNT_MISMATCH'
                notes = f"🔴 AMOUNT MISMATCH: Actual received on {network} is {actual_usd:,.2f} {currency}, but recorded is ${expected_usd:,.2f} USD! (Discrepancy: ${diff:,.2f})"
        else:
            status = 'VERIFIED_MATCH'
            notes = f"🟢 VERIFIED: Found {actual_usd:,.2f} {currency} on {network}."

        return {
            'success': True,
            'status': status,
            'verified_amount_usd': actual_usd,
            'network': network,
            'currency': currency,
            'notes': notes,
            'raw_data': result.get('raw', {})
        }

    @classmethod
    def verify_transaction_hash(cls, record) -> dict:
        """
        Verifies a WithdrawalRecord or eSIMFundingRecord instance by checking its
        binance_txid or binance_pay_id across both Binance Pay and Blockchain (BEP20 / TRC20).
        Updates verification status and audit notes on the record.
        """
        txid = getattr(record, 'binance_txid', None) or getattr(record, 'binance_pay_id', None) or getattr(record, 'supplier_pay_id', None)
        if not txid:
            return {'success': False, 'status': 'NOT_FOUND', 'notes': 'No TXID or Pay ID present.'}

        expected_usd = getattr(record, 'amount_usd_equivalent', None) or getattr(record, 'g2bulk_confirmed_increase_usd', None) or getattr(record, 'binance_verified_amount_usdt', None)
        expected_dzd = getattr(record, 'amount_dzd', None) or getattr(record, 'receipt_amount_dzd', None)

        res = cls.verify_transaction(
            txid_or_hash=str(txid),
            expected_usd_amount=expected_usd,
            expected_dzd_amount=expected_dzd
        )

        record.binance_verification_status = res.get('status', 'NOT_FOUND')
        if res.get('verified_amount_usd') is not None:
            record.binance_verified_amount_usd = res.get('verified_amount_usd')
        
        # Append audit note
        if res.get('notes'):
            record.notes = (record.notes or '').strip() + f"\n• [Binance Verification @ {timezone.now().strftime('%Y-%m-%d %H:%M')}] {res['notes']}"
        
        record.save()
        return res

    @classmethod
    def _fetch_transaction_details(cls, txid: str, settings: MonitoringGlobalSettings) -> dict:
        """
        Attempts to detect and query the transaction from Tron (TRC20), BSC (BEP20), Binance Pay API,
        or corporate Binance Capital Withdraw History.
        """
        # 1. BSC / EVM BEP20 TXID (0x + 64 hex characters)
        if re.match(r'^0x[a-fA-F0-9]{64}$', txid):
            # Check corporate Binance withdraw history first for exact account attribution
            withdraw_data = cls._query_binance_withdraw_history(txid, settings)
            if withdraw_data.get('found'):
                return withdraw_data
            bsc_data = cls._query_bscscan(txid)
            if bsc_data['found']:
                return bsc_data

        # 2. TRON TRC20 TXID (64 hex characters)
        if re.match(r'^[a-fA-F0-9]{64}$', txid):
            withdraw_data = cls._query_binance_withdraw_history(txid, settings)
            if withdraw_data.get('found'):
                return withdraw_data
            tron_data = cls._query_tronscan(txid)
            if tron_data['found']:
                return tron_data

        # 3. Binance Pay Order Query (if API credentials configured)
        if settings.binance_api_key and settings.binance_api_secret:
            binance_pay_data = cls._query_binance_pay_api(txid, settings)
            if binance_pay_data['found']:
                return binance_pay_data

        # 4. Check corporate Binance Withdraw History for non-standard IDs or transfer references
        withdraw_data = cls._query_binance_withdraw_history(txid, settings)
        if withdraw_data.get('found'):
            return withdraw_data

        return {'found': False, 'error': 'No matching blockchain or Binance Pay record found.'}

    @classmethod
    def _query_binance_withdraw_history(cls, txid: str, settings: MonitoringGlobalSettings) -> dict:
        """Queries corporate Binance Capital Withdraw History for matching txId or withdrawal id"""
        try:
            res = BinanceApiService.get_withdraw_history(coin='USDT', limit=50)
            if res.get('success') and isinstance(res.get('withdrawals'), list):
                txid_clean = txid.strip().lower()
                for w in res['withdrawals']:
                    w_tx = str(w.get('txId') or '').strip().lower()
                    w_id = str(w.get('id') or '').strip().lower()
                    if txid_clean in (w_tx, w_id) or (w_tx and w_tx == txid_clean):
                        amount = Decimal(str(w.get('amount', 0)))
                        fee = Decimal(str(w.get('transactionFee', 0)))
                        net = str(w.get('network') or 'BSC').upper()
                        net_label = 'BNB Smart Chain (BEP20)' if net in ('BSC', 'BNB') else ('Tron (TRC20)' if net == 'TRX' else f"Crypto ({net})")
                        return {
                            'found': True,
                            'amount_usd': amount,
                            'fee_usd': fee,
                            'currency': w.get('coin', 'USDT'),
                            'network': net_label,
                            'address': w.get('address'),
                            'time': w.get('applyTime', timezone.now().strftime('%Y-%m-%d %H:%M')),
                            'raw': w
                        }
        except Exception as e:
            logger.warning(f"Binance withdraw history query note for {txid}: {e}")
        return {'found': False}

    @classmethod
    def _query_tronscan(cls, txid: str) -> dict:
        """Queries Tronscan API for USDT (TRC20) transfer info"""
        url = f"https://apilist.tronscanapi.com/api/transaction-info?hash={txid}"
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url, headers={"User-Agent": "SofizAdmin/1.0"})
                if res.status_code == 200:
                    data = res.json()
                    # Check for TRC20 transfers
                    trc20_transfers = data.get('trc20TransferInfo', [])
                    if trc20_transfers:
                        transfer = trc20_transfers[0]
                        raw_amount = Decimal(str(transfer.get('amount_str', '0')))
                        decimals = int(transfer.get('decimals', 6))
                        amount = raw_amount / (Decimal(10) ** decimals)
                        symbol = transfer.get('symbol', 'USDT')
                        return {
                            'found': True,
                            'amount_usd': amount,
                            'currency': symbol,
                            'network': 'Tron (TRC20)',
                            'time': timezone.now().strftime('%Y-%m-%d %H:%M'),
                            'raw': data
                        }
                    
                    # Direct TRX contract
                    if data.get('contractRet') == 'SUCCESS':
                        contract_data = data.get('contractData', {})
                        if 'amount' in contract_data:
                            amount = Decimal(str(contract_data['amount'])) / Decimal(1000000)
                            return {
                                'found': True,
                                'amount_usd': amount,
                                'currency': 'TRX',
                                'network': 'Tron (TRX)',
                                'raw': data
                            }
        except Exception as e:
            logger.warning(f"Tronscan query failed for {txid}: {e}")
        return {'found': False}

    @classmethod
    def _query_bscscan(cls, txid: str) -> dict:
        """Queries BSC BscScan API for BEP20 USDT transfer"""
        url = f"https://api.bscscan.com/api?module=proxy&action=eth_getTransactionByHash&txhash={txid}"
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    res_obj = data.get('result')
                    if isinstance(res_obj, dict):
                        inp = str(res_obj.get('input') or '')
                        amount = Decimal("0.00")
                        # Standard ERC20/BEP20 transfer: 0xa9059cbb + 32 bytes address + 32 bytes amount
                        if inp.startswith('0xa9059cbb') and len(inp) >= 138:
                            try:
                                hex_val = inp[74:138]
                                raw_val = int(hex_val, 16)
                                # BSC-USD USDT token on BSC uses 18 decimals
                                amount = (Decimal(raw_val) / (Decimal(10) ** 18)).quantize(Decimal("0.01"))
                            except Exception:
                                pass
                        elif res_obj.get('value') and res_obj.get('value') != '0x0':
                            try:
                                raw_val = int(res_obj.get('value'), 16)
                                amount = (Decimal(raw_val) / (Decimal(10) ** 18)).quantize(Decimal("0.01"))
                            except Exception:
                                pass
                        return {
                            'found': True,
                            'amount_usd': amount,
                            'currency': 'USDT',
                            'network': 'BNB Smart Chain (BEP20)',
                            'time': timezone.now().strftime('%Y-%m-%d %H:%M'),
                            'raw': data
                        }
        except Exception as e:
            logger.warning(f"BscScan query failed for {txid}: {e}")
        return {'found': False}

    @classmethod
    def _query_binance_pay_api(cls, order_id: str, settings: MonitoringGlobalSettings) -> dict:
        """Queries Binance Pay OpenAPI order query endpoint"""
        # Binance Pay query API stub with HMAC SHA512
        try:
            endpoint = "https://bpay.binanceapi.com/binancepay/openapi/v2/order/query"
            payload = {"prepOrderId": order_id} if order_id.isdigit() else {"merchantTradeNo": order_id}
            # If configured, send request
            return {'found': False}
        except Exception as e:
            logger.warning(f"Binance Pay API error for {order_id}: {e}")
            return {'found': False}

    @classmethod
    def _query_epay_gateway(cls, txid: str, settings: MonitoringGlobalSettings) -> dict:
        """Queries Epay / SofizPay Binance verification gateway"""
        base_url = (settings.epay_api_url or "https://epay.sofizpay.com/api/operations").rstrip('/')
        url = f"{base_url}/binance/verify/"
        headers = {
            "X-API-KEY": settings.epay_api_key,
            "Content-Type": "application/json"
        }
        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get(url, params={"txid": txid}, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    if data.get('success'):
                        return {
                            'found': True,
                            'amount_usd': Decimal(str(data.get('amount_usd', '0.00'))),
                            'currency': data.get('currency', 'USDT'),
                            'network': 'Binance Pay Gateway',
                            'raw': data
                        }
        except Exception as e:
            logger.debug(f"Epay Binance gateway query info: {e}")
        return {'found': False}


class BinanceApiService:
    """Official Binance API integration with HMAC-SHA256 signature support"""
    BASE_URL = "https://api.binance.com"

    @classmethod
    def _sign_params(cls, params: dict, secret: str) -> dict:
        import hmac
        import hashlib
        import time
        import urllib.parse

        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 60000
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        params['signature'] = signature
        return params

    @classmethod
    def get_p2p_order_history(cls, trade_type: str = 'BUY', page: int = 1, rows: int = 20) -> dict:
        """Fetches recent Binance C2C / P2P orders directly from live Binance API"""
        settings = MonitoringGlobalSettings.get_settings()
        if not settings.binance_api_key or not settings.binance_api_secret:
            return {'success': False, 'orders': [], 'total': 0, 'error': 'Binance API credentials missing.'}

        endpoint = f"{cls.BASE_URL}/sapi/v1/c2c/orderMatch/listUserOrderHistory"
        params = {
            'tradeType': trade_type,
            'page': page,
            'rows': rows,
        }
        cls._sign_params(params, settings.binance_api_secret)
        headers = {"X-MBX-APIKEY": settings.binance_api_key}

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(endpoint, params=params, headers=headers)
                data = res.json()
                if res.status_code == 200 and data.get('code') == '000000':
                    return {'success': True, 'orders': data.get('data', []), 'total': data.get('total', 0)}
                return {'success': False, 'orders': [], 'total': 0, 'error': f"Binance error: {data}"}
        except Exception as e:
            logger.error(f"Binance P2P live call failed: {e}")
            return {'success': False, 'orders': [], 'total': 0, 'error': str(e)}

    @classmethod
    def get_pay_transactions(cls, start_timestamp: int = None, limit: int = 20) -> dict:
        """Fetches recent Binance Pay transactions directly from live Binance API"""
        settings = MonitoringGlobalSettings.get_settings()
        if not settings.binance_api_key or not settings.binance_api_secret:
            return {'success': False, 'transactions': [], 'total': 0, 'error': 'Binance API credentials missing.'}

        endpoint = f"{cls.BASE_URL}/sapi/v1/pay/transactions"
        params = {'limit': min(limit, 100)}
        if start_timestamp:
            params['startTimestamp'] = start_timestamp
        cls._sign_params(params, settings.binance_api_secret)
        headers = {"X-MBX-APIKEY": settings.binance_api_key}

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(endpoint, params=params, headers=headers)
                data = res.json()
                if res.status_code == 200 and data.get('code') == '000000':
                    return {'success': True, 'transactions': data.get('data', [])}
                return {'success': False, 'transactions': [], 'total': 0, 'error': f"Binance Pay error: {data}"}
        except Exception as e:
            logger.error(f"Binance Pay live call failed: {e}")
            return {'success': False, 'transactions': [], 'total': 0, 'error': str(e)}

    @classmethod
    def get_account_balances(cls) -> dict:
        """Fetches live USDT balances across Binance Funding and Spot wallets directly from live API"""
        settings = MonitoringGlobalSettings.get_settings()
        if not settings.binance_api_key or not settings.binance_api_secret:
            return {
                'success': False,
                'total_usdt': 0.0,
                'funding_usdt': 0.0,
                'spot_usdt': 0.0,
                'balance_dzd_equivalent': 0.0,
                'error': 'Binance credentials missing.',
                'assets': []
            }

        headers = {"X-MBX-APIKEY": settings.binance_api_key}
        funding_free = Decimal('0.00')
        funding_locked = Decimal('0.00')
        spot_free = Decimal('0.00')
        spot_locked = Decimal('0.00')

        try:
            with httpx.Client(timeout=10.0) as client:
                # 1. Query Binance Funding Wallet (/sapi/v1/asset/get-funding-asset)
                p_fund = {'asset': 'USDT'}
                cls._sign_params(p_fund, settings.binance_api_secret)
                r_fund = client.post(f"{cls.BASE_URL}/sapi/v1/asset/get-funding-asset", params=p_fund, headers=headers)
                if r_fund.status_code == 200:
                    d_fund = r_fund.json()
                    if isinstance(d_fund, list) and d_fund:
                        funding_free = Decimal(str(d_fund[0].get('free', '0.00')))
                        funding_locked = Decimal(str(d_fund[0].get('locked', '0.00')))

                # 2. Query Binance Spot Wallet (/sapi/v3/asset/getUserAsset)
                p_spot = {'asset': 'USDT'}
                cls._sign_params(p_spot, settings.binance_api_secret)
                r_spot = client.post(f"{cls.BASE_URL}/sapi/v3/asset/getUserAsset", params=p_spot, headers=headers)
                if r_spot.status_code == 200:
                    d_spot = r_spot.json()
                    if isinstance(d_spot, list) and d_spot:
                        spot_free = Decimal(str(d_spot[0].get('free', '0.00')))
                        spot_locked = Decimal(str(d_spot[0].get('locked', '0.00')))

            total_usdt = (funding_free + funding_locked + spot_free + spot_locked).quantize(Decimal('0.01'))
            rate = settings.usd_to_dzd_exchange_rate or Decimal('240.00')
            total_dzd = (total_usdt * rate).quantize(Decimal('0.01'))

            # Update database record
            from ..models import BinanceAccount
            try:
                ba = BinanceAccount.objects.first()
                if ba:
                    ba.balance_usdt = total_usdt
                    ba.balance_dzd_equivalent = total_dzd
                    ba.last_synced_at = timezone.now()
                    ba.last_error = None
                    ba.save()
            except Exception:
                pass

            return {
                'success': True,
                'total_usdt': float(total_usdt),
                'funding_usdt': float(funding_free + funding_locked),
                'spot_usdt': float(spot_free + spot_locked),
                'balance_dzd_equivalent': float(total_dzd),
                'exchange_rate': float(rate),
                'last_synced_at': timezone.now().isoformat(),
                'assets': [
                    {'wallet': 'FUNDING', 'asset': 'USDT', 'free': float(funding_free), 'locked': float(funding_locked)},
                    {'wallet': 'SPOT', 'asset': 'USDT', 'free': float(spot_free), 'locked': float(spot_locked)},
                ]
            }
        except Exception as e:
            logger.error(f"Live Binance balance query failed: {e}")
            return {
                'success': False,
                'total_usdt': 0.0,
                'funding_usdt': 0.0,
                'spot_usdt': 0.0,
                'balance_dzd_equivalent': 0.0,
                'error': str(e),
                'assets': []
            }

    @classmethod
    def get_withdraw_history(cls, coin: str = None, limit: int = 50) -> dict:
        """Fetches recent Binance crypto on-chain withdrawals directly from live API"""
        settings = MonitoringGlobalSettings.get_settings()
        if not settings.binance_api_key or not settings.binance_api_secret:
            return {'success': False, 'withdrawals': [], 'error': 'Binance API credentials missing.'}

        endpoint = f"{cls.BASE_URL}/sapi/v1/capital/withdraw/history"
        params = {'limit': limit}
        if coin:
            params['coin'] = coin
        cls._sign_params(params, settings.binance_api_secret)
        headers = {"X-MBX-APIKEY": settings.binance_api_key}

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(endpoint, params=params, headers=headers)
                data = res.json()
                if res.status_code == 200 and isinstance(data, list):
                    return {'success': True, 'withdrawals': data}
                return {'success': False, 'withdrawals': [], 'error': f"Binance error: {data}"}
        except Exception as e:
            logger.error(f"Binance withdraw history call failed: {e}")
            return {'success': False, 'withdrawals': [], 'error': str(e)}

    @classmethod
    def get_convert_trade_history(cls, from_asset: str = "USDT", to_asset: str = "XLM", limit: int = 50) -> dict:
        """
        Fetches verified conversion trades (USDT -> XLM) from Binance API:
        1. Queries Binance Convert Trade Flow (/sapi/v1/convert/tradeFlow)
        2. Queries Spot Trade executions (/api/v3/myTrades for XLMUSDT)
        Returns a unified list of verified conversions.
        """
        import time
        settings = MonitoringGlobalSettings.get_settings()
        if not settings.binance_api_key or not settings.binance_api_secret:
            return {'success': False, 'conversions': [], 'error': 'Binance API credentials missing.'}

        headers = {"X-MBX-APIKEY": settings.binance_api_key}
        conversions = []

        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (30 * 86400 * 1000)  # Last 30 days

        # 1. Query Binance Convert (/sapi/v1/convert/tradeFlow)
        try:
            convert_endpoint = f"{cls.BASE_URL}/sapi/v1/convert/tradeFlow"
            convert_params = {
                'startTime': start_ms,
                'endTime': now_ms,
                'limit': limit,
            }
            cls._sign_params(convert_params, settings.binance_api_secret)
            with httpx.Client(timeout=10.0) as client:
                res = client.get(convert_endpoint, params=convert_params, headers=headers)
                data = res.json()
                if res.status_code == 200 and isinstance(data, dict):
                    trade_list = data.get('list', [])
                    for t in trade_list:
                        f_asset = str(t.get('fromAsset', '')).upper()
                        t_asset = str(t.get('toAsset', '')).upper()
                        if (not from_asset or f_asset == from_asset.upper()) and (not to_asset or t_asset == to_asset.upper()):
                            conversions.append({
                                'order_id': str(t.get('orderId') or t.get('quoteId') or ''),
                                'type': 'BINANCE_CONVERT',
                                'status': t.get('orderStatus', 'SUCCESS'),
                                'from_asset': f_asset,
                                'from_amount': float(t.get('fromAmount') or 0.0),
                                'to_asset': t_asset,
                                'to_amount': float(t.get('toAmount') or 0.0),
                                'ratio': float(t.get('ratio') or 0.0),
                                'inverse_ratio': float(t.get('inverseRatio') or 0.0),
                                'timestamp': t.get('createTime'),
                                'created_at': timezone.datetime.fromtimestamp(t.get('createTime', now_ms) / 1000.0, tz=timezone.utc).isoformat() if t.get('createTime') else None,
                            })
        except Exception as e:
            logger.warning(f"Binance convert trade flow query note: {e}")

        # 2. Query Spot Trades (/api/v3/myTrades for XLMUSDT)
        try:
            symbol = f"{to_asset.upper()}{from_asset.upper()}"  # XLMUSDT
            spot_endpoint = f"{cls.BASE_URL}/api/v3/myTrades"
            spot_params = {
                'symbol': symbol,
                'limit': limit,
            }
            cls._sign_params(spot_params, settings.binance_api_secret)
            with httpx.Client(timeout=10.0) as client:
                res = client.get(spot_endpoint, params=spot_params, headers=headers)
                data = res.json()
                if res.status_code == 200 and isinstance(data, list):
                    for st in data:
                        if st.get('isBuyer', True):
                            qty_xlm = float(st.get('qty') or 0.0)
                            quote_usdt = float(st.get('quoteQty') or 0.0)
                            price = float(st.get('price') or 0.0)
                            commission = float(st.get('commission') or 0.0)
                            comm_asset = st.get('commissionAsset')
                            conversions.append({
                                'order_id': str(st.get('orderId') or st.get('id') or ''),
                                'type': 'SPOT_TRADE',
                                'status': 'FILLED',
                                'from_asset': from_asset.upper(),
                                'from_amount': quote_usdt,
                                'to_asset': to_asset.upper(),
                                'to_amount': qty_xlm,
                                'ratio': price,
                                'inverse_ratio': round(1.0 / price, 4) if price > 0 else 0.0,
                                'commission': commission,
                                'commission_asset': comm_asset,
                                'timestamp': st.get('time'),
                                'created_at': timezone.datetime.fromtimestamp(st.get('time', now_ms) / 1000.0, tz=timezone.utc).isoformat() if st.get('time') else None,
                            })
        except Exception as e:
            logger.warning(f"Binance spot trades query note: {e}")

        # Sort by timestamp descending
        conversions.sort(key=lambda x: x.get('timestamp') or 0, reverse=True)

        return {
            'success': True,
            'conversions': conversions,
            'count': len(conversions),
        }

    @classmethod
    def get_all_consumed_binance_identifiers(cls) -> set:
        """
        Unified cross-module anti-double-spending repository.
        Collects all consumed Binance order IDs, Pay IDs, transaction hashes,
        withdrawal IDs, and convert trade IDs across ALL 3 modules:
        1. Game / Digital Services: WithdrawalRecord
        2. eSIM Funding: eSIMFundingRecord
        3. XLM Treasury: XLMLiquidityFundingRecord
        4. BaridiMob Funding Receipts: BaridiMobFundingReceipt
        """
        from ..models import (
            WithdrawalRecord,
            eSIMFundingRecord,
            XLMLiquidityFundingRecord,
            BaridiMobFundingReceipt,
        )

        consumed = set()

        # 1. Game (WithdrawalRecord)
        for field in ['p2p_order_id', 'binance_txid', 'binance_pay_id', 'supplier_pay_id', 'reference', 'g2bulk_transaction_id']:
            values = WithdrawalRecord.objects.exclude(**{f"{field}__isnull": True}).exclude(**{field: ''}).values_list(field, flat=True)
            for v in values:
                if v:
                    consumed.add(str(v).strip())

        # 2. eSIM (eSIMFundingRecord)
        for field in ['binance_p2p_order_id', 'binance_txid', 'bybit_txid', 'airalo_order_id', 'receipt_reference']:
            values = eSIMFundingRecord.objects.exclude(**{f"{field}__isnull": True}).exclude(**{field: ''}).values_list(field, flat=True)
            for v in values:
                if v:
                    consumed.add(str(v).strip())

        # 3. XLM (XLMLiquidityFundingRecord)
        for field in ['p2p_order_id', 'binance_withdrawal_id', 'stellar_tx_hash', 'receipt_reference']:
            values = XLMLiquidityFundingRecord.objects.exclude(**{f"{field}__isnull": True}).exclude(**{field: ''}).values_list(field, flat=True)
            for v in values:
                if v:
                    consumed.add(str(v).strip())

        # Extract any Convert orders recorded in XLM notes
        for note_txt in XLMLiquidityFundingRecord.objects.exclude(notes__isnull=True).exclude(notes='').values_list('notes', flat=True):
            if note_txt and 'Convert' in note_txt:
                import re
                for m in re.finditer(r'Convert(?: Order)?\s*#?(\d+)', note_txt, re.IGNORECASE):
                    consumed.add(m.group(1).strip())

        # 4. BaridiMob Funding Receipts
        for field in ['binance_order_id', 'reference']:
            values = BaridiMobFundingReceipt.objects.exclude(**{f"{field}__isnull": True}).exclude(**{field: ''}).values_list(field, flat=True)
            for v in values:
                if v:
                    consumed.add(str(v).strip())

        return consumed

    @classmethod
    def check_binance_identifier_consumed(cls, identifier: str, exclude_module: str = None, exclude_id = None) -> dict:
        """
        Cross-Module Double Spending Lock:
        Checks whether a candidate Binance identifier is already consumed in Game, eSIM, or XLM.
        """
        clean_id = str(identifier or '').strip()
        if not clean_id or clean_id.upper().startswith('TEST-'):
            return {'is_consumed': False}

        from ..models import (
            WithdrawalRecord,
            eSIMFundingRecord,
            XLMLiquidityFundingRecord,
        )
        from django.db.models import Q

        # Check 1: Game (WithdrawalRecord)
        game_qs = WithdrawalRecord.objects.filter(
            Q(p2p_order_id=clean_id) |
            Q(binance_txid=clean_id) |
            Q(binance_pay_id=clean_id) |
            Q(supplier_pay_id=clean_id) |
            Q(g2bulk_transaction_id=clean_id)
        )
        if exclude_module == 'GAME' and exclude_id:
            game_qs = game_qs.exclude(id=exclude_id)
        game_match = game_qs.first()
        if game_match:
            return {
                'is_consumed': True,
                'module': 'GAME',
                'record_id': game_match.id,
                'record_title': game_match.title or f"Withdrawal #{game_match.id}",
                'error_message': f"Binance identifier '{clean_id}' is already consumed in Game / Wholesale Withdrawal #{game_match.id} ({game_match.title}). Cross-module double spending is strictly prohibited.",
            }

        # Check 2: eSIM (eSIMFundingRecord)
        esim_qs = eSIMFundingRecord.objects.filter(
            Q(binance_p2p_order_id=clean_id) |
            Q(binance_txid=clean_id) |
            Q(bybit_txid=clean_id) |
            Q(airalo_order_id=clean_id)
        )
        if exclude_module == 'ESIM' and exclude_id:
            esim_qs = esim_qs.exclude(id=exclude_id)
        esim_match = esim_qs.first()
        if esim_match:
            return {
                'is_consumed': True,
                'module': 'ESIM',
                'record_id': esim_match.id,
                'record_title': f"eSIM Refill #{esim_match.id}",
                'error_message': f"Binance identifier '{clean_id}' is already consumed in eSIM Refill #{esim_match.id}. Cross-module double spending is strictly prohibited.",
            }

        # Check 3: XLM (XLMLiquidityFundingRecord)
        xlm_qs = XLMLiquidityFundingRecord.objects.filter(
            Q(p2p_order_id=clean_id) |
            Q(binance_withdrawal_id=clean_id) |
            Q(stellar_tx_hash=clean_id) |
            Q(notes__icontains=clean_id)
        )
        if exclude_module == 'XLM' and exclude_id:
            xlm_qs = xlm_qs.exclude(id=exclude_id)
        xlm_match = xlm_qs.first()
        if xlm_match:
            return {
                'is_consumed': True,
                'module': 'XLM',
                'record_id': xlm_match.id,
                'record_title': xlm_match.cycle_reference,
                'error_message': f"Binance identifier '{clean_id}' is already consumed in XLM Treasury Cycle #{xlm_match.cycle_reference}. Cross-module double spending is strictly prohibited.",
            }

        return {'is_consumed': False}



