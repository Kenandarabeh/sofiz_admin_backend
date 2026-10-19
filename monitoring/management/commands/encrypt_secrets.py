from django.core.management.base import BaseCommand
from django.db import connection
from monitoring.models import StellarWallet, MonitoringGlobalSettings
from core.encryption import is_encrypted, encrypt_value, decrypt_value, ENCRYPTION_PREFIX


class Command(BaseCommand):
    help = "Audits and transparently encrypts all Stellar Secret Keys (sk) and API secrets in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Audit check only. Reports plaintext vs encrypted secrets without modifying records.',
        )

    def handle(self, *args, **options):
        is_check = options.get('check', False)
        self.stdout.write(self.style.NOTICE("============================================================"))
        self.stdout.write(self.style.NOTICE("🔒 Institutional Vault Secret Key Encryption Routine"))
        self.stdout.write(self.style.NOTICE("============================================================"))

        # 1. Audit / Encrypt Stellar Wallets
        wallets_encrypted = 0
        wallets_already_encrypted = 0
        wallets_empty = 0

        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name, secret_seed FROM monitoring_stellarwallet ORDER BY id;")
            raw_wallets = cursor.fetchall()

        for w_id, w_name, raw_seed in raw_wallets:
            if not raw_seed or not str(raw_seed).strip():
                wallets_empty += 1
                continue

            clean_seed = str(raw_seed).strip()
            if clean_seed.startswith(ENCRYPTION_PREFIX):
                wallets_already_encrypted += 1
                self.stdout.write(f"  [OK - ENCRYPTED] Wallet #{w_id} ({w_name}): {clean_seed[:18]}...")
            else:
                if is_check:
                    self.stdout.write(self.style.WARNING(f"  [UNENCRYPTED] Wallet #{w_id} ({w_name}): Plaintext SK present"))
                else:
                    encrypted_token = encrypt_value(clean_seed)
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "UPDATE monitoring_stellarwallet SET secret_seed = %s WHERE id = %s;",
                            [encrypted_token, w_id]
                        )
                    wallets_encrypted += 1
                    self.stdout.write(self.style.SUCCESS(f"  [ENCRYPTED] Wallet #{w_id} ({w_name}) ➔ {encrypted_token[:20]}..."))

        # 2. Audit / Encrypt GlobalSettings Credentials
        settings_encrypted = 0
        settings_already_encrypted = 0

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, epay_api_key, baridimob_secret_token, g2bulk_api_key, 
                       binance_api_secret, bybit_api_secret, airalo_client_secret
                FROM monitoring_monitoringglobalsettings
                ORDER BY id;
            """)
            raw_settings = cursor.fetchall()

        fields_to_encrypt = [
            ('epay_api_key', 1),
            ('baridimob_secret_token', 2),
            ('g2bulk_api_key', 3),
            ('binance_api_secret', 4),
            ('bybit_api_secret', 5),
            ('airalo_client_secret', 6),
        ]

        for row in raw_settings:
            s_id = row[0]
            for field_name, col_idx in fields_to_encrypt:
                val = row[col_idx]
                if not val or not str(val).strip():
                    continue
                val_str = str(val).strip()
                if val_str.startswith(ENCRYPTION_PREFIX):
                    settings_already_encrypted += 1
                else:
                    if is_check:
                        self.stdout.write(self.style.WARNING(f"  [UNENCRYPTED] GlobalSettings #{s_id} field '{field_name}': Plaintext present"))
                    else:
                        encrypted_token = encrypt_value(val_str)
                        with connection.cursor() as cursor:
                            cursor.execute(
                                f"UPDATE monitoring_monitoringglobalsettings SET {field_name} = %s WHERE id = %s;",
                                [encrypted_token, s_id]
                            )
                        settings_encrypted += 1
                        self.stdout.write(self.style.SUCCESS(f"  [ENCRYPTED] GlobalSettings #{s_id} field '{field_name}' ➔ {encrypted_token[:20]}..."))

        self.stdout.write(self.style.NOTICE("------------------------------------------------------------"))
        if is_check:
            self.stdout.write(self.style.SUCCESS(
                f"Audit Complete: {wallets_already_encrypted} wallets encrypted, "
                f"{wallets_encrypted} pending encryption, {wallets_empty} empty seeds."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Encryption Complete: {wallets_encrypted} wallets newly encrypted, "
                f"{wallets_already_encrypted} already encrypted, {settings_encrypted} settings fields encrypted."
            ))
        self.stdout.write(self.style.NOTICE("============================================================"))
