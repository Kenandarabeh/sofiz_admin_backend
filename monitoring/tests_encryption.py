from decimal import Decimal
from django.test import TestCase
from django.db import connection
from stellar_sdk import Keypair
from monitoring.models import StellarWallet, MonitoringGlobalSettings
from core.encryption import (
    encrypt_value,
    decrypt_value,
    is_encrypted,
    ENCRYPTION_PREFIX,
    get_encryption_key,
)


class FieldEncryptionTests(TestCase):
    def setUp(self):
        # Sample test Stellar keypair
        self.test_kp = Keypair.random()
        self.public_key = self.test_kp.public_key
        self.secret_seed = self.test_kp.secret

    def test_low_level_encryption_roundtrip(self):
        plaintext = "sk_sofizadmin_live_sample_secret_key_12345"
        encrypted = encrypt_value(plaintext)

        self.assertTrue(encrypted.startswith(ENCRYPTION_PREFIX))
        self.assertNotEqual(encrypted, plaintext)
        self.assertTrue(is_encrypted(encrypted))

        # Test idempotence (no double-encryption)
        re_encrypted = encrypt_value(encrypted)
        self.assertEqual(re_encrypted, encrypted)

        # Test decryption
        decrypted = decrypt_value(encrypted)
        self.assertEqual(decrypted, plaintext)

    def test_backward_compatibility_unencrypted_value(self):
        plaintext = "unencrypted_legacy_api_key"
        self.assertFalse(is_encrypted(plaintext))
        # decrypt_value must pass through unencrypted strings gracefully
        result = decrypt_value(plaintext)
        self.assertEqual(result, plaintext)

    def test_stellar_wallet_model_transparent_encryption(self):
        # 1. Create a StellarWallet with plaintext secret_seed
        wallet = StellarWallet.objects.create(
            name="Test Encrypted Collection Wallet",
            family="GAME",
            role="COLLECTION",
            category="GAMING",
            public_address=self.public_key,
            secret_seed=self.secret_seed,
            dzt_balance=Decimal("1000.0000"),
            is_active=True,
        )

        # 2. Check that in-memory Python property returns the decrypted plaintext SK
        self.assertEqual(wallet.secret_seed, self.secret_seed)
        self.assertTrue(wallet.secret_seed.startswith("S"))
        self.assertEqual(len(wallet.secret_seed), 56)

        # 3. Verify Keypair can be recreated seamlessly from wallet.secret_seed
        reconstructed_kp = Keypair.from_secret(wallet.secret_seed)
        self.assertEqual(reconstructed_kp.public_key, self.public_key)

        # 4. Check RAW database column via SQL to ensure it is encrypted in storage!
        with connection.cursor() as cursor:
            cursor.execute("SELECT secret_seed FROM monitoring_stellarwallet WHERE id = %s;", [wallet.id])
            raw_db_value = cursor.fetchone()[0]

        self.assertTrue(raw_db_value.startswith(ENCRYPTION_PREFIX))
        self.assertNotEqual(raw_db_value, self.secret_seed)
        self.assertNotIn(self.secret_seed, raw_db_value)

        # 5. Reload fresh instance from DB and verify automatic transparent decryption
        fresh_wallet = StellarWallet.objects.get(id=wallet.id)
        self.assertEqual(fresh_wallet.secret_seed, self.secret_seed)

    def test_global_settings_epay_key_encryption(self):
        sample_api_key = "sk_sofizadmin_live_777888999aabbccddeeff"
        settings = MonitoringGlobalSettings.objects.create(
            epay_api_key=sample_api_key,
            g2bulk_api_key="g2bulk_live_secret_key_abc",
        )

        # In-memory access should be decrypted
        self.assertEqual(settings.epay_api_key, sample_api_key)
        self.assertEqual(settings.g2bulk_api_key, "g2bulk_live_secret_key_abc")

        # In raw database, it MUST be encrypted
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT epay_api_key, g2bulk_api_key FROM monitoring_monitoringglobalsettings WHERE id = %s;",
                [settings.id]
            )
            raw_epay, raw_g2bulk = cursor.fetchone()

        self.assertTrue(raw_epay.startswith(ENCRYPTION_PREFIX))
        self.assertTrue(raw_g2bulk.startswith(ENCRYPTION_PREFIX))
        self.assertNotEqual(raw_epay, sample_api_key)
        self.assertNotEqual(raw_g2bulk, "g2bulk_live_secret_key_abc")
