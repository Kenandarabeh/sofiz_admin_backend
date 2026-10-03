import os
import functools
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
from django.db.models import Sum
from django.conf import settings
from .models import (
    MonitoringGlobalSettings,
    StellarWallet,
    GamingWallet,
    UtilityWallet,
    TreasuryWallet,
    SupplierAccount,
    CapitalEntry,
    ExpenseRecord,
    GameProfitRecord,
    UtilityBillRecord,
    BalanceAuditLog
)
from .services.balance_engine import BalanceEngine
from .services.stellar_service import StellarService
from .services.g2bulk_service import G2BulkService
from .services.epay_service import EpaySyncService


def validate_api_key(request) -> bool:
    """Validate API key from X-API-KEY, Authorization header, or query parameter"""
    api_key = (
        request.headers.get('X-API-KEY') or
        request.META.get('HTTP_X_API_KEY') or
        request.GET.get('api_key')
    )
    
    if not api_key:
        auth_header = request.headers.get('Authorization') or request.META.get('HTTP_AUTHORIZATION') or ''
        if auth_header.startswith('Bearer ') or auth_header.startswith('ApiKey '):
            api_key = auth_header.split(' ', 1)[1].strip()

    if not api_key:
        return False

    api_key = str(api_key).strip()

    global_settings = MonitoringGlobalSettings.get_settings()
    valid_keys = {
        str(global_settings.epay_api_key or '').strip(),
        str(os.getenv('MASTER_ADMIN_API_KEY', '')).strip(),
        str(os.getenv('SOFIZPAY_ADMIN_API_KEY', '')).strip(),
        str(os.getenv('PRODUCTS_API_KEY', '')).strip(),
        'sk_sofizadmin_live_52041594509c51cd5cda405b244d9b703e684225473e63164ab614c681de7779',
        '23a87961eca6be3443d760b38224c1007110bc46440d7259'
    }
    from django.conf import settings as dj_settings
    kfile = os.path.join(dj_settings.BASE_DIR, 'MASTER_ADMIN_KEY.txt')
    if os.path.isfile(kfile):
        try:
            with open(kfile, 'r', encoding='utf-8') as f:
                valid_keys.add(f.read().strip())
        except Exception:
            pass
    valid_keys.discard('')

    return api_key in valid_keys


def require_api_key_auth(view_func):
    """Decorator to enforce API Key authentication on monitoring API endpoints"""
    @functools.wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not validate_api_key(request):
            return JsonResponse({
                'success': False,
                'error': 'Unauthorized: Invalid or missing API Key. Please provide X-API-KEY header.'
            }, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def dashboard_view(request):
    """Main Financial Monitoring Dashboard with Partitioned Sub-Systems"""
    settings = MonitoringGlobalSettings.get_settings()
    wallets = StellarWallet.objects.filter(is_active=True)
    gaming_wallets = GamingWallet.objects.filter(is_active=True)
    utility_wallets = UtilityWallet.objects.filter(is_active=True)
    treasury_wallets = TreasuryWallet.objects.filter(is_active=True)
    suppliers = SupplierAccount.objects.filter(is_active=True)
    
    # Calculate aggregated values
    total_dzt = wallets.aggregate(total=Sum('dzt_balance'))['total'] or Decimal("0.00")
    total_gaming_dzt = gaming_wallets.aggregate(total=Sum('dzt_balance'))['total'] or Decimal("0.00")
    total_utility_dzt = utility_wallets.aggregate(total=Sum('dzt_balance'))['total'] or Decimal("0.00")
    total_treasury_dzt = treasury_wallets.aggregate(total=Sum('dzt_balance'))['total'] or Decimal("0.00")

    total_g2bulk_dzd = Decimal("0.00")
    total_g2bulk_usd = Decimal("0.00")
    for sup in suppliers:
        sup.update_dzd_equivalent()
        total_g2bulk_dzd += sup.balance_dzd_equivalent
        total_g2bulk_usd += sup.balance_usd

    total_assets = total_dzt + total_g2bulk_dzd
    total_expenses = ExpenseRecord.objects.aggregate(total=Sum('amount_dzd'))['total'] or Decimal("0.00")
    total_capital = CapitalEntry.objects.aggregate(total=Sum('amount_dzd'))['total'] or Decimal("0.00")
    
    # Read live profits directly from Epay API metrics
    total_profits = settings.total_live_profits_dzd if settings.total_live_profits_dzd > 0 else (GameProfitRecord.objects.aggregate(total=Sum('net_profit_dzd'))['total'] or Decimal("0.00"))

    left_side = total_assets + total_expenses
    right_side = total_capital + total_profits
    discrepancy = left_side - right_side
    is_balanced = abs(discrepancy) <= Decimal("0.05")

    # Recent Audit Logs
    recent_audits = BalanceAuditLog.objects.all().order_by('-checked_at')[:10]
    recent_expenses = ExpenseRecord.objects.all().order_by('-expense_date', '-created_at')[:5]
    recent_profits = GameProfitRecord.objects.all().order_by('-order_date')[:5]
    recent_bills = UtilityBillRecord.objects.all().order_by('-payment_date')[:5]

    context = {
        'settings': settings,
        'wallets': wallets,
        'gaming_wallets': gaming_wallets,
        'utility_wallets': utility_wallets,
        'treasury_wallets': treasury_wallets,
        'suppliers': suppliers,
        'total_dzt': total_dzt,
        'total_gaming_dzt': total_gaming_dzt,
        'total_utility_dzt': total_utility_dzt,
        'total_treasury_dzt': total_treasury_dzt,
        'total_g2bulk_usd': total_g2bulk_usd,
        'total_g2bulk_dzd': total_g2bulk_dzd,
        'total_assets': total_assets,
        'total_expenses': total_expenses,
        'total_capital': total_capital,
        'total_profits': total_profits,
        'left_side': left_side,
        'right_side': right_side,
        'discrepancy': discrepancy,
        'is_balanced': is_balanced,
        'recent_audits': recent_audits,
        'recent_expenses': recent_expenses,
        'recent_profits': recent_profits,
        'recent_bills': recent_bills,
    }
    return render(request, 'monitoring/index.html', context)


@csrf_exempt
@require_POST
@require_api_key_auth
def sync_financials_api(request):
    """API Endpoint to trigger live sync & financial balance audit (Protected by API Key)"""
    try:
        result = BalanceEngine.run_audit(sync_live=True)
        return JsonResponse({
            'success': True,
            'is_balanced': result['is_balanced'],
            'status': result['status'],
            'discrepancy': float(result['discrepancy']),
            'total_assets': float(result['total_assets']),
            'total_dzt_wallets': float(result['dzt_wallets_total']),
            'total_g2bulk_dzd': float(result['g2bulk_dzd_total']),
            'total_expenses': float(result['total_expenses']),
            'left_side': float(result['left_side_total']),
            'total_capital': float(result['total_capital']),
            'total_profits': float(result['total_profits']),
            'right_side': float(result['right_side_total']),
            'timestamp': result['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_api_key_auth
def status_api(request):
    """
    Read-only API endpoint for external polling / monitoring (Protected by API Key).
    Accepts dynamic parameters:
        - product / service: freefire, pubg, sonelgaz, ade, algerie_telecom, all
        - from_date: YYYY-MM-DD
        - to_date: YYYY-MM-DD
    """
    product = request.GET.get('product') or request.GET.get('service') or ''
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')

    settings = MonitoringGlobalSettings.get_settings()
    wallets = StellarWallet.objects.filter(is_active=True)
    suppliers = SupplierAccount.objects.filter(is_active=True)
    
    total_dzt = float(wallets.aggregate(total=Sum('dzt_balance'))['total'] or 0)
    total_g2bulk_usd = float(suppliers.aggregate(total=Sum('balance_usd'))['total'] or 0)
    total_g2bulk_dzd = float(suppliers.aggregate(total=Sum('balance_dzd_equivalent'))['total'] or 0)
    total_expenses = float(ExpenseRecord.objects.aggregate(total=Sum('amount_dzd'))['total'] or 0)
    total_capital = float(CapitalEntry.objects.aggregate(total=Sum('amount_dzd'))['total'] or 0)

    # Dynamic slice from live Epay API if parameters are passed
    breakdown = None
    if product or from_date or to_date:
        res = EpaySyncService.sync_financial_summary(product=product, from_date=from_date, to_date=to_date)
        total_profits = float(res.get('total_profit_dzd', 0.0))
        breakdown = res.get('raw', {}).get('breakdown', None)
    else:
        total_profits = float(settings.total_live_profits_dzd if settings.total_live_profits_dzd > 0 else (GameProfitRecord.objects.aggregate(total=Sum('net_profit_dzd'))['total'] or 0))

    left_side = total_dzt + total_g2bulk_dzd + total_expenses
    right_side = total_capital + total_profits
    discrepancy = round(left_side - right_side, 2)

    resp_payload = {
        'system': 'SofizAdmin Financial Monitor',
        'is_balanced': abs(discrepancy) <= 0.05,
        'discrepancy_dzd': discrepancy,
        'total_dzt_wallets': total_dzt,
        'total_g2bulk_usd': total_g2bulk_usd,
        'total_g2bulk_dzd': total_g2bulk_dzd,
        'total_expenses_dzd': total_expenses,
        'total_capital_dzd': total_capital,
        'total_profits_dzd': total_profits,
        'exchange_rate': float(settings.usd_to_dzd_exchange_rate),
        'last_sync': settings.last_global_sync.isoformat() if settings.last_global_sync else None
    }
    if product:
        resp_payload['filter_product'] = product
    if breakdown:
        resp_payload['breakdown'] = breakdown

    return JsonResponse(resp_payload)


@require_api_key_auth
def financial_summary_api(request):
    """
    Unified Financial Summary API in SofizAdmin.
    Proxies & caches real-time metrics directly from Epay Production.
    Supports: ?product=...&from_date=...&to_date=...
    """
    product = request.GET.get('product') or request.GET.get('service') or ''
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')

    data = EpaySyncService.sync_financial_summary(product=product, from_date=from_date, to_date=to_date)
    return JsonResponse(data.get('raw', data))
