from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock
from .models import (
    MonitoringGlobalSettings,
    StellarWallet,
    SupplierAccount,
    CapitalEntry,
    ExpenseRecord,
    GameProfitRecord,
    BalanceAuditLog
)
from .services.stellar_service import StellarService
from .services.g2bulk_service import G2BulkService
from .services.balance_engine import BalanceEngine


class FinancialMonitoringTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.settings = MonitoringGlobalSettings.get_settings()
        self.settings.usd_to_dzd_exchange_rate = Decimal("240.00")
        self.settings.dzt_asset_code = "DZT"
        self.settings.dzt_asset_issuer = "GCAZI7YBLIDJWIVEL7ETNAZGPP3LC24NO6KAOBWZHUERXQ7M5BC52DLV"
        self.settings.save()

    def test_golden_balance_equation_perfect_match(self):
        """
        Formula:
        (Stellar DZT + G2Bulk DZD) + (Expenses) == (Capital Inflows) + (Profits)
        Left: (50,000 + 24,000) + 1,000 = 75,000 DZT
        Right: 70,000 (Capital) + 5,000 (Profits) = 75,000 DZT
        Discrepancy: 0.00 DZT -> BALANCED
        """
        wallet = StellarWallet.objects.create(
            name="PUBG Mobile Collection Wallet",
            family="GAME",
            role="COLLECTION",
            public_address="GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5",
            dzt_balance=Decimal("50000.00")
        )
        supplier = SupplierAccount.objects.create(
            provider="G2BULK",
            name="G2Bulk Official Account",
            balance_usd=Decimal("100.00") # 100 USD * 240 = 24,000 DZD
        )
        supplier.update_dzd_equivalent()
        supplier.save()

        # Inflow (Capital)
        CapitalEntry.objects.create(
            title="Initial Seed Capital",
            amount_dzd=Decimal("70000.00")
        )

        # Profits
        GameProfitRecord.objects.create(
            order_reference="ORD-FF-1001",
            game_code="freefire",
            cost_price_usd=Decimal("2.00"),
            cost_price_dzd=Decimal("480.00"),
            sale_price_dzd=Decimal("5480.00"),
            net_profit_dzd=Decimal("5000.00")
        )

        # Expenses
        ExpenseRecord.objects.create(
            title="Network gas and hosting fees",
            category="BLOCKCHAIN_FEE",
            amount_dzd=Decimal("1000.00")
        )

        result = BalanceEngine.run_audit(sync_live=False)

        self.assertTrue(result['is_balanced'])
        self.assertEqual(result['status'], 'BALANCED')
        self.assertEqual(result['dzt_wallets_total'], Decimal("50000.00"))
        self.assertEqual(result['g2bulk_dzd_total'], Decimal("24000.00"))
        self.assertEqual(result['total_assets'], Decimal("74000.00"))
        self.assertEqual(result['total_expenses'], Decimal("1000.00"))
        self.assertEqual(result['left_side_total'], Decimal("75000.00"))
        self.assertEqual(result['total_capital'], Decimal("70000.00"))
        self.assertEqual(result['total_profits'], Decimal("5000.00"))
        self.assertEqual(result['right_side_total'], Decimal("75000.00"))
        self.assertEqual(result['discrepancy'], Decimal("0.00"))

    def test_golden_balance_equation_discrepancy_detected(self):
        """
        Left: (10,000 DZT) + 0 Expenses = 10,000 DZT
        Right: 50,000 Capital + 0 Profits = 50,000 DZT
        Discrepancy: -40,000 DZT -> DISCREPANCY_DETECTED (Capital deficit)
        """
        StellarWallet.objects.create(
            name="Wallet 1",
            public_address="GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            dzt_balance=Decimal("10000.00")
        )
        CapitalEntry.objects.create(
            title="Large Inflow",
            amount_dzd=Decimal("50000.00")
        )

        result = BalanceEngine.run_audit(sync_live=False)

        self.assertFalse(result['is_balanced'])
        self.assertEqual(result['status'], 'DISCREPANCY_DETECTED')
        self.assertEqual(result['discrepancy'], Decimal("-40000.00"))

    @patch('httpx.Client.get')
    def test_stellar_service_parser(self, mock_get):
        """Test Stellar Horizon API parser extracting DZT and XLM"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "balances": [
                {"asset_type": "native", "balance": "34.5000000"},
                {
                    "asset_type": "credit_alphanum4",
                    "asset_code": "DZT",
                    "asset_issuer": "GCAZI7YBLIDJWIVEL7ETNAZGPP3LC24NO6KAOBWZHUERXQ7M5BC52DLV",
                    "balance": "12500.7500000"
                },
                {
                    "asset_type": "credit_alphanum4",
                    "asset_code": "USDC",
                    "asset_issuer": "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN",
                    "balance": "100.0000000"
                }
            ]
        }
        mock_get.return_value = mock_response

        wallet = StellarWallet.objects.create(
            name="Audit Test Wallet",
            public_address="GCKF5USV6R46S672SDFVBHJKIUYTFDESAZXCVBNMKJHGFDS"
        )

        res = StellarService.sync_wallet(wallet)
        self.assertTrue(res['success'])
        self.assertEqual(res['dzt'], Decimal("12500.7500"))

        wallet.refresh_from_db()
        self.assertEqual(wallet.dzt_balance, Decimal("12500.7500"))

    @patch('httpx.Client.get')
    def test_g2bulk_service_sync(self, mock_get):
        """Test G2Bulk API balance sync"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "user_id": 12345,
            "username": "sofizpay_official",
            "first_name": "SofizPay",
            "balance": 450.75
        }
        mock_get.return_value = mock_response

        supplier = SupplierAccount.objects.create(
            provider="G2BULK",
            name="G2Bulk Official",
            api_key="test-api-key"
        )

        res = G2BulkService.sync_supplier(supplier)
        self.assertTrue(res['success'])
        self.assertEqual(supplier.balance_usd, Decimal("450.75"))
        self.assertEqual(supplier.balance_dzd_equivalent, Decimal("108180.00")) # 450.75 * 240
        self.assertEqual(supplier.account_uid, "12345")
        self.assertEqual(supplier.account_username, "sofizpay_official")

    def test_dashboard_and_api_views(self):
        """Test HTTP status for root redirect and API endpoints with and without API key"""
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 302) # Redirects to /admin/

        # Test unauthorized request (without API Key)
        resp_unauth = self.client.get(reverse('monitoring:api_status'))
        self.assertEqual(resp_unauth.status_code, 403)

        # Test authorized request (with API Key)
        api_key = 'sk_live_sofiz_fin_8f93e1b072c449a8bb63920e5c1d84f7'
        resp_status = self.client.get(reverse('monitoring:api_status'), HTTP_X_API_KEY=api_key)
        self.assertEqual(resp_status.status_code, 200)
        self.assertIn('is_balanced', resp_status.json())

        resp_sync = self.client.post(reverse('monitoring:api_sync'), HTTP_X_API_KEY=api_key)
        self.assertEqual(resp_sync.status_code, 200)
        self.assertTrue(resp_sync.json()['success'])

    def test_internal_wallet_overdraft_prevention(self):
        """Test that send_payment strictly blocks overdraft and prevents unauthorized money fabrication"""
        source = StellarWallet.objects.create(
            name="Test Source Wallet",
            family="GAME",
            role="WITHDRAWAL",
            public_address="GBSOURCE111111111111111111111111111111111111111111111111",
            dzt_balance=Decimal("200.00"),
            secret_seed=""
        )
        dest = StellarWallet.objects.create(
            name="Test Dest Wallet",
            family="TREASURY",
            role="VAULT",
            public_address="GBDEST222222222222222222222222222222222222222222222222222",
            dzt_balance=Decimal("0.00"),
            secret_seed=""
        )

        res = StellarService.send_payment(
            source_wallet=source,
            destination_wallet=dest,
            amount=Decimal("500.00")
        )
        self.assertFalse(res['success'])
        self.assertIn("Insufficient liquidity", res['error'])

        source.refresh_from_db()
        dest.refresh_from_db()
        self.assertEqual(source.dzt_balance, Decimal("200.00"))
        self.assertEqual(dest.dzt_balance, Decimal("0.00"))

    def test_algerie_poste_glitch_quarantine(self):
        """Test Algérie Poste negative glitch quarantine prevents Golden Balance equation distortion"""
        from .models import BaridiMobAccount
        from django.utils import timezone

        acc = BaridiMobAccount.objects.create(
            account_name="Sihaam31 Working Capital",
            rip_number="00799999009999999999",
            balance_dzd=Decimal("10000.00"),
            last_stable_balance=Decimal("10000.00"),
            is_active=True
        )

        # Baseline audit before glitch
        audit_1 = BalanceEngine.run_audit(sync_live=False, send_alerts=False)

        # Postal glitch occurs: server returns negative balance (-6,000 DZD)
        acc.is_glitch_quarantined = True
        acc.quarantined_glitch_amount = Decimal("-6000.00")
        acc.glitch_detected_at = timezone.now()
        acc.save()

        # Audit during glitch
        audit_2 = BalanceEngine.run_audit(sync_live=False, send_alerts=False)

        # Discrepancy must remain identical because the quarantine protects the equation
        self.assertEqual(audit_1['discrepancy'], audit_2['discrepancy'])
        self.assertIn("Algérie Poste Glitch Quarantined", audit_2['notes'])

        # Postal glitch self-corrects after days
        acc.is_glitch_quarantined = False
        acc.glitch_resolved_at = timezone.now()
        acc.balance_dzd = Decimal("10000.00")
        acc.save()

        audit_3 = BalanceEngine.run_audit(sync_live=False, send_alerts=False)
        self.assertEqual(audit_1['discrepancy'], audit_3['discrepancy'])
