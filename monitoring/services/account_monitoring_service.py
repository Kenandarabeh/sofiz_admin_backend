import logging
from decimal import Decimal
from django.utils import timezone
from datetime import datetime, time, timedelta
from django.db import models

from monitoring.models import (
    AccountBalanceSnapshot,
    AccountMonitoringChannel,
    BaridiMobAccount,
    BaridiMobTransaction,
    SupplierAccount,
    AiraloAccount,
    MonitoringGlobalSettings,
)

logger = logging.getLogger(__name__)


class AccountMonitoringService:
    """
    Dedicated institutional service for continuous real-time balance tracking,
    time-series snapshot capture, net change calculations, and transaction-causality linkage.
    """

    @classmethod
    def get_exchange_rate(cls):
        try:
            settings = MonitoringGlobalSettings.get_settings()
            return Decimal(str(settings.usd_to_dzd_exchange_rate))
        except Exception:
            return Decimal("253.20")

    @classmethod
    def record_snapshot(
        cls,
        channel: str,
        account_label: str,
        activity: str,
        source_type: str,
        current_balance: Decimal,
        currency: str = "DZD",
        current_balance_dzd: Decimal = None,
        trigger_type: str = "PERIODIC_SYNC",
        causing_tx_id: str = None,
        causing_tx_desc: str = None,
        causing_tx_amount: Decimal = None,
        last_synced_at=None,
        notes: str = None,
        recorded_at=None,
    ) -> AccountBalanceSnapshot:
        """
        Records a single snapshot for an account channel, automatically computing previous balance and delta.
        """
        rate = cls.get_exchange_rate()
        if current_balance_dzd is None:
            if currency == "USD":
                current_balance_dzd = (current_balance * rate).quantize(Decimal("0.01"))
            else:
                current_balance_dzd = current_balance.quantize(Decimal("0.01"))

        # Fetch the most recent prior snapshot for this channel
        last_snap = AccountBalanceSnapshot.objects.filter(channel=channel).order_by("-recorded_at").first()

        if last_snap:
            previous_balance_dzd = last_snap.current_balance_dzd
        else:
            if causing_tx_amount is not None:
                # previous = current - tx_amount
                previous_balance_dzd = (current_balance_dzd - causing_tx_amount).quantize(Decimal("0.01"))
            else:
                previous_balance_dzd = current_balance_dzd

        balance_change_dzd = (current_balance_dzd - previous_balance_dzd).quantize(Decimal("0.01"))

        if balance_change_dzd > Decimal("0.00"):
            change_type = "INCREASE"
        elif balance_change_dzd < Decimal("0.00"):
            change_type = "DECREASE"
        else:
            change_type = "STABLE"

        snapshot = AccountBalanceSnapshot.objects.create(
            channel=channel,
            account_label=account_label,
            activity=activity,
            source_type=source_type,
            current_balance=current_balance,
            currency=currency,
            current_balance_dzd=current_balance_dzd,
            previous_balance_dzd=previous_balance_dzd,
            balance_change_dzd=balance_change_dzd,
            change_type=change_type,
            trigger_type=trigger_type,
            causing_transaction_id=causing_tx_id,
            causing_transaction_desc=causing_tx_desc,
            causing_transaction_amount=causing_tx_amount,
            last_synced_at=last_synced_at or timezone.now(),
            notes=notes,
            recorded_at=recorded_at or timezone.now(),
        )
        return snapshot

    @classmethod
    def capture_live_snapshots(cls, trigger: str = "MANUAL_SYNC"):
        """
        Captures a live snapshot across all 8 monitored channels:
        - g2bulk
        - airalo
        - baridimob_esim_quota
        - eccp_esim_quota
        - baridimob_game_quota
        - eccp_game_quota
        - baridimob_facture
        - eccp_facture
        """
        rate = cls.get_exchange_rate()
        now = timezone.now()

        # 1. G2Bulk Wholesale
        g2 = SupplierAccount.objects.filter(models.Q(provider__iexact="G2BULK") | models.Q(name__icontains="g2bulk")).first()
        g2_usd = Decimal(str(g2.balance_usd)) if g2 and g2.balance_usd is not None else Decimal("0.00")
        g2_dzd = (g2_usd * rate).quantize(Decimal("0.01"))
        cls.record_snapshot(
            channel=AccountMonitoringChannel.G2BULK,
            account_label="G2Bulk Wholesale Inventory",
            activity="Gaming",
            source_type="G2Bulk",
            current_balance=g2_usd,
            currency="USD",
            current_balance_dzd=g2_dzd,
            trigger_type=trigger,
            last_synced_at=g2.last_synced_at if g2 else now,
            notes="Wholesale gaming digital codes & pins inventory balance",
        )

        # 2. Airalo eSIM Wholesale
        air = AiraloAccount.objects.first()
        if not air:
            air = AiraloAccount.objects.create(
                account_name="Official Airalo Partner Account",
                available_balance_usd=Decimal("0.00"),
                is_active=True
            )

        air_usd = Decimal(str(air.available_balance_usd))
        air_dzd = air.balance_dzd_equivalent
        cls.record_snapshot(
            channel=AccountMonitoringChannel.AIRALO,
            account_label="Airalo eSIM Wholesale Partner",
            activity="eSIM",
            source_type="Airalo",
            current_balance=air_usd,
            currency="USD",
            current_balance_dzd=air_dzd,
            trigger_type=trigger,
            last_synced_at=air.last_synced_at if air else now,
            notes="Global eSIM data roaming package wholesale credit",
        )

        # 3 & 4. Salah Gaming & eSIM Account
        salah = BaridiMobAccount.objects.filter(id=3).first()
        if not salah:
            salah = BaridiMobAccount.objects.filter(account_name__icontains="salah").first()
        
        salah_card = Decimal(str(salah.balance_dzd)) if (salah and salah.balance_dzd is not None) else Decimal("0.00")
        salah_eccp = Decimal(str(salah.eccp_balance_dzd)) if (salah and salah.eccp_balance_dzd and salah.eccp_balance_dzd > 0) else salah_card
        salah_card_sync = salah.last_synced_at if salah else now
        salah_eccp_sync = salah.eccp_last_synced_at if salah else now

        # Operational Quotas derived from Walid's withdrawals and real account balance
        from .balance_engine import BalanceEngine
        walid_quotas = BalanceEngine.get_walid_withdrawal_quotas()

        game_target_val = walid_quotas['gaming_target_quota']
        esim_target_val = walid_quotas['esim_target_quota']
        total_target_val = game_target_val + esim_target_val

        if salah_card >= total_target_val:
            esim_card_quota = esim_target_val
            game_card_quota = (salah_card - esim_card_quota).quantize(Decimal("0.01"))
        elif total_target_val > Decimal("0.00"):
            ratio_g = game_target_val / total_target_val
            game_card_quota = (salah_card * ratio_g).quantize(Decimal("0.01"))
            esim_card_quota = (salah_card - game_card_quota).quantize(Decimal("0.01"))
        else:
            game_card_quota = salah_card
            esim_card_quota = Decimal("0.00")

        game_eccp_quota = game_card_quota
        esim_eccp_quota = esim_card_quota

        # Find latest transaction for Salah account
        latest_salah_tx = BaridiMobTransaction.objects.filter(account=salah).order_by("-transaction_date").first() if salah else None

        # BaridiMob (Quota Game)
        cls.record_snapshot(
            channel=AccountMonitoringChannel.BARIDIMOB_GAME_QUOTA,
            account_label="BaridiMob (Gaming Quota)",
            activity="Gaming",
            source_type="BaridiMob",
            current_balance=game_card_quota,
            currency="DZD",
            current_balance_dzd=game_card_quota,
            trigger_type=trigger,
            causing_tx_id=latest_salah_tx.tid if latest_salah_tx else None,
            causing_tx_desc=latest_salah_tx.description if latest_salah_tx else None,
            causing_tx_amount=latest_salah_tx.amount if latest_salah_tx else None,
            last_synced_at=salah_card_sync,
            notes=f"BaridiMob Card operational quota (Target: {game_target_val:,.2f} DZD, derived from Walid withdrawals) - Salah Account",
        )

        # ECCP (Quota Game)
        cls.record_snapshot(
            channel=AccountMonitoringChannel.ECCP_GAME_QUOTA,
            account_label="ECCP (Gaming Quota)",
            activity="Gaming",
            source_type="ECCP",
            current_balance=game_eccp_quota,
            currency="DZD",
            current_balance_dzd=game_eccp_quota,
            trigger_type=trigger,
            last_synced_at=salah_eccp_sync,
            notes=f"Algérie Poste Extrait de Compte postal quota (CCP 0017388665 Clé 35)",
        )

        # BaridiMob (Quota eSIM)
        cls.record_snapshot(
            channel=AccountMonitoringChannel.BARIDIMOB_ESIM_QUOTA,
            account_label="BaridiMob (eSIM Quota)",
            activity="eSIM",
            source_type="BaridiMob",
            current_balance=esim_card_quota,
            currency="DZD",
            current_balance_dzd=esim_card_quota,
            trigger_type=trigger,
            last_synced_at=salah_card_sync,
            notes=f"BaridiMob Card eSIM quota (Target: {esim_target_val:,.2f} DZD, derived from Walid withdrawals)",
        )

        # ECCP (Quota eSIM)
        cls.record_snapshot(
            channel=AccountMonitoringChannel.ECCP_ESIM_QUOTA,
            account_label="ECCP (eSIM Quota)",
            activity="eSIM",
            source_type="ECCP",
            current_balance=esim_eccp_quota,
            currency="DZD",
            current_balance_dzd=esim_eccp_quota,
            trigger_type=trigger,
            last_synced_at=salah_eccp_sync,
            notes=f"Algérie Poste Extrait de Compte postal quota for eSIM sourcing",
        )

        # 5 & 6. Sihaam Factures & Utility Bills Account
        sihaam = BaridiMobAccount.objects.filter(id=1).first()
        if not sihaam:
            sihaam = BaridiMobAccount.objects.filter(account_name__icontains="sihaam").first()

        sihaam_card = Decimal(str(sihaam.balance_dzd)) if (sihaam and sihaam.balance_dzd is not None) else Decimal("0.00")
        sihaam_eccp = Decimal(str(sihaam.eccp_balance_dzd)) if (sihaam and sihaam.eccp_balance_dzd and sihaam.eccp_balance_dzd > 0) else sihaam_card
        sihaam_card_sync = sihaam.last_synced_at if sihaam else now
        sihaam_eccp_sync = sihaam.eccp_last_synced_at if sihaam else now

        latest_sihaam_tx = BaridiMobTransaction.objects.filter(account=sihaam).order_by("-transaction_date").first() if sihaam else None

        # BaridiMob Facture
        cls.record_snapshot(
            channel=AccountMonitoringChannel.BARIDIMOB_FACTURE,
            account_label="BaridiMob (Factures Sihaam)",
            activity="Facture",
            source_type="BaridiMob",
            current_balance=sihaam_card,
            currency="DZD",
            current_balance_dzd=sihaam_card,
            trigger_type=trigger,
            causing_tx_id=latest_sihaam_tx.tid if latest_sihaam_tx else None,
            causing_tx_desc=latest_sihaam_tx.description if latest_sihaam_tx else None,
            causing_tx_amount=latest_sihaam_tx.amount if latest_sihaam_tx else None,
            last_synced_at=sihaam_card_sync,
            notes="Edahabia electronic card for Sonelgaz, ADE, & Algérie Télécom bill payments",
        )

        # ECCP Facture
        cls.record_snapshot(
            channel=AccountMonitoringChannel.ECCP_FACTURE,
            account_label="ECCP (Factures Sihaam)",
            activity="Facture",
            source_type="ECCP",
            current_balance=sihaam_eccp,
            currency="DZD",
            current_balance_dzd=sihaam_eccp,
            trigger_type=trigger,
            last_synced_at=sihaam_eccp_sync,
            notes="Algérie Poste Extrait de Compte postal solde (CCP 0022883344 Clé 11)",
        )

    @classmethod
    def seed_historical_audit_timeline(cls, force=False):
        """
        Captures real-time balance snapshots from active accounts.
        Zero mock or synthetic data is generated.
        """
        cls.capture_live_snapshots(trigger="PERIODIC_SYNC")

    @classmethod
    def get_all_monitored_accounts_payload(cls, date_str=None, hour_str=None, range_param='24h', time_mode='all', start_date=None, end_date=None):
        """
        Builds institutional 8-account monitoring data structure complete with Date & Time filtering:
        - Current Live Balance vs Historical Balance at specified hour (point-in-time balance inquiry)
        - Transactions filtered to exact hour or date range (start_date, end_date, today, yesterday, 7d, 30d)
        """
        cls.seed_historical_audit_timeline()
        cls.capture_live_snapshots(trigger="MONITORING_POLL")

        now = timezone.now()
        target_date = None
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                target_date = None

        start_date_obj = None
        end_date_obj = None
        if start_date:
            try:
                start_date_obj = datetime.strptime(str(start_date).strip(), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                start_date_obj = None
        if end_date:
            try:
                end_date_obj = datetime.strptime(str(end_date).strip(), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                end_date_obj = None

        target_hour = None
        if hour_str is not None and str(hour_str).strip() != '':
            try:
                target_hour = int(str(hour_str).split(':')[0])
            except (ValueError, IndexError):
                target_hour = None

        as_of_dt = None
        time_filter_active = False

        range_start_dt = None
        range_end_dt = None

        if start_date_obj and end_date_obj:
            range_start_dt = timezone.make_aware(datetime.combine(start_date_obj, time.min))
            range_end_dt = timezone.make_aware(datetime.combine(end_date_obj, time.max))
            as_of_dt = range_end_dt
            time_filter_active = True
        elif start_date_obj:
            range_start_dt = timezone.make_aware(datetime.combine(start_date_obj, time.min))
            range_end_dt = timezone.make_aware(datetime.combine(now.date(), time.max))
            as_of_dt = range_end_dt
            time_filter_active = True
        elif target_date and target_hour is not None:
            as_of_dt = timezone.make_aware(datetime.combine(target_date, time(hour=target_hour, minute=0, second=0)))
            range_start_dt = timezone.make_aware(datetime.combine(target_date, time.min))
            range_end_dt = as_of_dt
            time_filter_active = True
        elif target_hour is not None:
            as_of_dt = timezone.make_aware(datetime.combine(now.date(), time(hour=target_hour, minute=0, second=0)))
            range_start_dt = timezone.make_aware(datetime.combine(now.date(), time.min))
            range_end_dt = as_of_dt
            time_filter_active = True
        elif target_date:
            range_start_dt = timezone.make_aware(datetime.combine(target_date, time.min))
            range_end_dt = timezone.make_aware(datetime.combine(target_date, time.max))
            as_of_dt = range_end_dt
            time_filter_active = True
        elif range_param == 'today':
            range_start_dt = timezone.make_aware(datetime.combine(now.date(), time.min))
            range_end_dt = timezone.make_aware(datetime.combine(now.date(), time.max))
            as_of_dt = range_end_dt
            time_filter_active = True
        elif range_param == 'yesterday':
            y_date = now.date() - timedelta(days=1)
            range_start_dt = timezone.make_aware(datetime.combine(y_date, time.min))
            range_end_dt = timezone.make_aware(datetime.combine(y_date, time.max))
            as_of_dt = range_end_dt
            time_filter_active = True
        elif range_param == '7d':
            range_start_dt = timezone.make_aware(datetime.combine(now.date() - timedelta(days=7), time.min))
            range_end_dt = now
            as_of_dt = range_end_dt
            time_filter_active = True
        elif range_param == '30d':
            range_start_dt = timezone.make_aware(datetime.combine(now.date() - timedelta(days=30), time.min))
            range_end_dt = now
            as_of_dt = range_end_dt
            time_filter_active = True
        elif range_param == '24h':
            range_start_dt = now - timedelta(hours=24)
            range_end_dt = now

        rate = float(cls.get_exchange_rate())

        from .balance_engine import BalanceEngine
        walid_quotas = BalanceEngine.get_walid_withdrawal_quotas()
        gaming_target = float(walid_quotas['gaming_target_quota'])
        esim_target = float(walid_quotas['esim_target_quota'])
        factures_target = float(walid_quotas['factures_target_quota'])

        salah_acc_obj = BaridiMobAccount.objects.filter(id=3).first() or BaridiMobAccount.objects.filter(account_name__icontains='salah').first()
        sihaam_acc_obj = BaridiMobAccount.objects.filter(id=1).first() or BaridiMobAccount.objects.filter(account_name__icontains='sihaam').first()
        salah_solde_val = float(salah_acc_obj.eccp_balance_dzd or salah_acc_obj.balance_dzd or 0) if salah_acc_obj else 0.0
        sihaam_solde_val = float(sihaam_acc_obj.eccp_balance_dzd or sihaam_acc_obj.balance_dzd or 0) if sihaam_acc_obj else 0.0

        channels_metadata = [
            {
                'key': AccountMonitoringChannel.G2BULK,
                'title': 'G2Bulk Wholesale Inventory',
                'category': 'Gaming Wholesale',
                'activity': 'Gaming',
                'source': 'G2Bulk Official API',
                'currency': 'USD',
                'account_number': 'UID: 8147834549',
                'target_quota_dzd': None,
                'linked_account_id': None,
                'badge': 'Wholesale Partner',
                'linked_route': '/gaming',
            },
            {
                'key': AccountMonitoringChannel.AIRALO,
                'title': 'Airalo eSIM Wholesale Partner',
                'category': 'eSIM Wholesale',
                'activity': 'eSIM',
                'source': 'Airalo Telecom API',
                'currency': 'USD',
                'account_number': 'Official Airalo Partner',
                'target_quota_dzd': None,
                'linked_account_id': None,
                'badge': 'Telecom Partner',
                'linked_route': '/withdrawals/esim',
            },
            {
                'key': AccountMonitoringChannel.BARIDIMOB_ESIM_QUOTA,
                'title': 'BaridiMob — eSIM',
                'category': 'eSIM Working Capital',
                'activity': 'eSIM',
                'source': 'Algérie Poste Edahabia Card',
                'currency': 'DZD',
                'account_number': 'Salah (00799999001738866535)',
                'target_quota_dzd': esim_target,
                'sourcing_solde_dzd': salah_solde_val,
                'wallet_balance_dzt': None,
                'linked_account_id': 3,
                'badge': 'Edahabia Card',
                'linked_route': '/withdrawals/esim',
            },
            {
                'key': AccountMonitoringChannel.ECCP_ESIM_QUOTA,
                'title': 'ECCP — eSIM',
                'category': 'Postal Root Capital',
                'activity': 'eSIM',
                'source': 'Algérie Poste Extrait de Compte',
                'currency': 'DZD',
                'account_number': 'CCP 0017388665 Clé 35 (Salah)',
                'target_quota_dzd': esim_target,
                'sourcing_solde_dzd': salah_solde_val,
                'wallet_balance_dzt': None,
                'linked_account_id': 3,
                'badge': 'Extrait de Compte',
                'linked_route': '/withdrawals/esim',
            },
            {
                'key': AccountMonitoringChannel.BARIDIMOB_GAME_QUOTA,
                'title': 'BaridiMob — Gaming',
                'category': 'Gaming Working Capital',
                'activity': 'Gaming',
                'source': 'Algérie Poste Edahabia Card',
                'currency': 'DZD',
                'account_number': 'Salah (00799999001738866535)',
                'target_quota_dzd': gaming_target,
                'sourcing_solde_dzd': salah_solde_val,
                'wallet_balance_dzt': None,
                'linked_account_id': 3,
                'badge': 'Edahabia Card',
                'linked_route': '/gaming',
            },
            {
                'key': AccountMonitoringChannel.ECCP_GAME_QUOTA,
                'title': 'ECCP — Gaming',
                'category': 'Postal Root Capital',
                'activity': 'Gaming',
                'source': 'Algérie Poste Extrait de Compte',
                'currency': 'DZD',
                'account_number': 'CCP 0017388665 Clé 35 (Salah)',
                'target_quota_dzd': gaming_target,
                'sourcing_solde_dzd': salah_solde_val,
                'wallet_balance_dzt': None,
                'linked_account_id': 3,
                'badge': 'Extrait de Compte',
                'linked_route': '/gaming',
            },
            {
                'key': AccountMonitoringChannel.BARIDIMOB_FACTURE,
                'title': 'BaridiMob — Factures',
                'category': 'Utility Bills Card',
                'activity': 'Facture',
                'source': 'Algérie Poste Edahabia Card',
                'currency': 'DZD',
                'account_number': 'Sihaam (00799999004166560419)',
                'target_quota_dzd': factures_target,
                'sourcing_solde_dzd': sihaam_solde_val,
                'wallet_balance_dzt': None,
                'linked_account_id': 1,
                'badge': 'Edahabia Card',
                'linked_route': '/utility',
            },
            {
                'key': AccountMonitoringChannel.ECCP_FACTURE,
                'title': 'ECCP — Factures',
                'category': 'Postal Root Capital',
                'activity': 'Facture',
                'source': 'Algérie Poste Extrait de Compte',
                'currency': 'DZD',
                'account_number': 'CCP 0041665604 Clé 19 (Sihaam)',
                'target_quota_dzd': factures_target,
                'sourcing_solde_dzd': sihaam_solde_val,
                'wallet_balance_dzt': None,
                'linked_account_id': 1,
                'badge': 'Extrait de Compte',
                'linked_route': '/utility',
            },
        ]

        accounts_result = []

        for meta in channels_metadata:
            chan_key = meta['key']
            snapshots_qs = AccountBalanceSnapshot.objects.filter(channel=chan_key).order_by('-recorded_at')
            latest_snap = snapshots_qs.first()

            if not latest_snap:
                continue

            prior_snap = snapshots_qs[1:2].first()

            cur_bal_native = float(latest_snap.current_balance)
            cur_bal_dzd = float(latest_snap.current_balance_dzd)

            # Bind real-time current balance directly to live audited account states
            if chan_key == AccountMonitoringChannel.G2BULK:
                g2_live = SupplierAccount.objects.filter(models.Q(provider__iexact="G2BULK") | models.Q(name__icontains="g2bulk")).first()
                if g2_live and g2_live.balance_usd is not None:
                    cur_bal_native = float(g2_live.balance_usd)
                    cur_bal_dzd = float(g2_live.balance_dzd_equivalent or round(cur_bal_native * rate, 2))
            elif chan_key == AccountMonitoringChannel.AIRALO:
                air_live = AiraloAccount.objects.first()
                if air_live and air_live.available_balance_usd is not None:
                    cur_bal_native = float(air_live.available_balance_usd)
                    cur_bal_dzd = float(air_live.balance_dzd_equivalent or round(cur_bal_native * rate, 2))
            elif chan_key in [AccountMonitoringChannel.BARIDIMOB_GAME_QUOTA, AccountMonitoringChannel.BARIDIMOB_ESIM_QUOTA]:
                if salah_acc_obj and salah_acc_obj.balance_dzd is not None:
                    cur_bal_native = float(salah_acc_obj.balance_dzd)
                    cur_bal_dzd = cur_bal_native
            elif chan_key in [AccountMonitoringChannel.ECCP_GAME_QUOTA, AccountMonitoringChannel.ECCP_ESIM_QUOTA]:
                if salah_acc_obj and salah_acc_obj.eccp_balance_dzd is not None:
                    cur_bal_native = float(salah_acc_obj.eccp_balance_dzd)
                    cur_bal_dzd = cur_bal_native
            elif chan_key == AccountMonitoringChannel.BARIDIMOB_FACTURE:
                if sihaam_acc_obj and sihaam_acc_obj.balance_dzd is not None:
                    cur_bal_native = float(sihaam_acc_obj.balance_dzd)
                    cur_bal_dzd = cur_bal_native
            elif chan_key == AccountMonitoringChannel.ECCP_FACTURE:
                if sihaam_acc_obj and sihaam_acc_obj.eccp_balance_dzd is not None:
                    cur_bal_native = float(sihaam_acc_obj.eccp_balance_dzd)
                    cur_bal_dzd = cur_bal_native

            prev_bal_dzd = float(prior_snap.current_balance_dzd) if prior_snap else float(latest_snap.previous_balance_dzd)
            change_dzd = round(cur_bal_dzd - prev_bal_dzd, 2)

            if change_dzd > 0:
                change_type = 'INCREASE'
            elif change_dzd < 0:
                change_type = 'DECREASE'
            else:
                change_type = 'STABLE'

            # Continuous Timeline Sampling across the requested range
            all_chan_snaps = list(AccountBalanceSnapshot.objects.filter(channel=chan_key).order_by('recorded_at'))

            def get_snap_at(target_dt):
                cands = [s for s in all_chan_snaps if s.recorded_at <= target_dt]
                return cands[-1] if cands else (all_chan_snaps[0] if all_chan_snaps else None)

            effective_start = range_start_dt if range_start_dt else (now - timedelta(hours=24))
            effective_end = range_end_dt if range_end_dt else now

            span_seconds = max(1.0, (effective_end - effective_start).total_seconds())
            is_multi_day = span_seconds > 24 * 3600

            if span_seconds <= 26 * 3600:
                slot_step = timedelta(hours=1)
            elif span_seconds <= 8 * 24 * 3600:
                slot_step = timedelta(hours=4)
            elif span_seconds <= 45 * 24 * 3600:
                slot_step = timedelta(hours=12)
            else:
                slot_step = timedelta(days=1)

            points_by_dt = {}

            # 1. Start anchor point (balance at the very start of the period)
            start_snap = get_snap_at(effective_start)
            if start_snap:
                points_by_dt[effective_start] = {
                    'id': f'start-{start_snap.id}',
                    'dt': effective_start,
                    'balance': float(start_snap.current_balance),
                    'balance_dzd': float(start_snap.current_balance_dzd),
                    'trigger': 'PERIOD_START',
                    'notes': 'Beginning of period',
                }

            # 2. Intermediate regular time slots (forward-fill balance across each interval)
            cur_slot = effective_start + slot_step
            while cur_slot < effective_end:
                s = get_snap_at(cur_slot)
                if s:
                    points_by_dt[cur_slot] = {
                        'id': f'slot-{s.id}-{int(cur_slot.timestamp())}',
                        'dt': cur_slot,
                        'balance': float(s.current_balance),
                        'balance_dzd': float(s.current_balance_dzd),
                        'trigger': s.trigger_type,
                        'notes': s.notes or '',
                    }
                cur_slot += slot_step

            # 3. Include any actual snapshots within the period that had real balance changes
            for s in all_chan_snaps:
                if effective_start <= s.recorded_at <= effective_end:
                    if s.balance_change_dzd != 0:
                        points_by_dt[s.recorded_at] = {
                            'id': s.id,
                            'dt': s.recorded_at,
                            'balance': float(s.current_balance),
                            'balance_dzd': float(s.current_balance_dzd),
                            'trigger': s.trigger_type,
                            'notes': s.notes or '',
                        }

            # 4. End anchor point (latest state at the end of the requested period)
            end_snap = get_snap_at(effective_end)
            if end_snap:
                points_by_dt[effective_end] = {
                    'id': f'latest-{end_snap.id}',
                    'dt': effective_end,
                    'balance': float(end_snap.current_balance),
                    'balance_dzd': float(end_snap.current_balance_dzd),
                    'trigger': 'LIVE_STATE',
                    'notes': 'Current live audited balance',
                }

            # 5. Format timestamps and compute step deltas
            sorted_dts = sorted(points_by_dt.keys())
            graph_points = []
            seen_labels = set()
            prev_bal = None

            for dt_item in sorted_dts:
                pt = points_by_dt[dt_item]
                t_label = dt_item.strftime('%m-%d %H:%M') if is_multi_day else dt_item.strftime('%H:%M')
                if t_label in seen_labels and pt['trigger'] not in ('PERIOD_START', 'LIVE_STATE'):
                    continue
                seen_labels.add(t_label)

                cur_bal = pt['balance_dzd']
                step_change = round(cur_bal - prev_bal, 2) if prev_bal is not None else 0.0
                prev_bal = cur_bal

                graph_points.append({
                    'id': pt['id'],
                    'timestamp': t_label,
                    'full_date': dt_item.strftime('%Y-%m-%d %H:%M'),
                    'balance': pt['balance'],
                    'balance_dzd': cur_bal,
                    'change_dzd': step_change,
                    'trigger': pt['trigger'],
                    'notes': pt['notes'],
                })

            if graph_points:
                period_first_bal = graph_points[0]['balance_dzd']
                period_last_bal = graph_points[-1]['balance_dzd']
                change_dzd = round(period_last_bal - period_first_bal, 2)
                change_type = 'INCREASE' if change_dzd > 0 else ('DECREASE' if change_dzd < 0 else 'STABLE')

            if len(graph_points) < 3:
                now_dt = timezone.now()
                graph_points = [
                    {
                        'timestamp': (now_dt - timezone.timedelta(hours=3)).strftime('%H:00'),
                        'balance': cur_bal_native,
                        'balance_dzd': cur_bal_dzd,
                        'change_dzd': 0.0,
                    },
                    {
                        'timestamp': (now_dt - timezone.timedelta(hours=2)).strftime('%H:00'),
                        'balance': cur_bal_native,
                        'balance_dzd': cur_bal_dzd,
                        'change_dzd': 0.0,
                    },
                    {
                        'timestamp': (now_dt - timezone.timedelta(hours=1)).strftime('%H:00'),
                        'balance': cur_bal_native,
                        'balance_dzd': cur_bal_dzd,
                        'change_dzd': 0.0,
                    },
                    {
                        'timestamp': now_dt.strftime('%H:%M'),
                        'balance': cur_bal_native,
                        'balance_dzd': cur_bal_dzd,
                        'change_dzd': change_dzd,
                    },
                ]

            # Calculate historical balance as of as_of_dt (point-in-time balance inquiry)
            if time_filter_active and meta['linked_account_id']:
                future_txs = BaridiMobTransaction.objects.filter(
                    account_id=meta['linked_account_id'],
                    transaction_date__gt=as_of_dt
                )
                future_diff = sum(float(t.amount) for t in future_txs)
                balance_at_time = round(cur_bal_dzd - future_diff, 2)
            elif time_filter_active:
                snap_at_time = AccountBalanceSnapshot.objects.filter(
                    channel=chan_key,
                    recorded_at__lte=as_of_dt + timedelta(minutes=30)
                ).order_by('-recorded_at').first()
                balance_at_time = float(snap_at_time.current_balance_dzd) if snap_at_time else cur_bal_dzd
            else:
                balance_at_time = cur_bal_dzd

            diff_from_live = round(balance_at_time - cur_bal_dzd, 2)

            tx_list = []
            if meta['linked_account_id']:
                tx_qs = BaridiMobTransaction.objects.filter(account_id=meta['linked_account_id'])
                if time_filter_active and target_hour is not None and time_mode == 'exact':
                    tx_qs = tx_qs.filter(transaction_date__range=(as_of_dt, as_of_dt + timedelta(hours=1)))
                elif time_filter_active and target_hour is not None and time_mode == 'up_to':
                    day_start = timezone.make_aware(datetime.combine(as_of_dt.date(), time.min))
                    tx_qs = tx_qs.filter(transaction_date__range=(day_start, as_of_dt + timedelta(hours=1)))
                elif range_start_dt and range_end_dt:
                    tx_qs = tx_qs.filter(transaction_date__range=(range_start_dt, range_end_dt))
                elif range_start_dt:
                    tx_qs = tx_qs.filter(transaction_date__gte=range_start_dt)
                else:
                    tx_qs = tx_qs.filter(transaction_date__gte=now - timedelta(hours=24))

                raw_txs = tx_qs.order_by('-transaction_date')[:50]

                running_bal = balance_at_time if time_filter_active else cur_bal_dzd
                for tx in raw_txs:
                    tx_amt = float(tx.amount)
                    tx_prev_bal = round(running_bal - tx_amt, 2)
                    tx_list.append({
                        'tid': tx.tid,
                        'ref_num': tx.ref_num or '—',
                        'amount_dzd': tx_amt,
                        'is_credit': tx_amt > 0,
                        'fee_amount_dzd': float(tx.fee_amount) if tx.fee_amount else 0.0,
                        'previous_balance_dzd': tx_prev_bal,
                        'new_balance_dzd': running_bal,
                        'description': tx.description or tx.transaction_type or 'BaridiMob Operation Record',
                        'operation_code': tx.operation_code or 'POSTAL_OP',
                        'timestamp': tx.transaction_date.strftime('%Y-%m-%d %H:%M'),
                    })
                    running_bal = tx_prev_bal
            elif chan_key == AccountMonitoringChannel.G2BULK:
                from monitoring.models import WithdrawalRecord
                w_qs = WithdrawalRecord.objects.filter(
                    models.Q(system_type='GAMING') | models.Q(purpose_code__icontains='G2BULK') | models.Q(title__icontains='G2Bulk')
                )
                if range_start_dt and range_end_dt:
                    w_qs = w_qs.filter(created_at__range=(range_start_dt, range_end_dt))
                elif range_start_dt:
                    w_qs = w_qs.filter(created_at__gte=range_start_dt)

                raw_wths = w_qs.order_by('-created_at')[:25]
                running_bal = cur_bal_dzd
                for w in raw_wths:
                    amt = float(w.amount_dzd or 0)
                    tx_prev_bal = round(running_bal - amt, 2)
                    tx_list.append({
                        'tid': w.reference or f"WTH-{w.id}",
                        'ref_num': w.p2p_order_id or w.binance_txid or w.g2bulk_transaction_id or f"P2P Sourcing #{w.id}",
                        'amount_dzd': amt,
                        'is_credit': True,
                        'fee_amount_dzd': float(w.binance_fee_dzd or 0.0),
                        'previous_balance_dzd': tx_prev_bal,
                        'new_balance_dzd': running_bal,
                        'description': w.title or f"G2Bulk Inventory Replenishment ({amt:,.2f} DZD)",
                        'operation_code': f"STAGE_{w.stage}",
                        'timestamp': w.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(w, 'created_at') else '',
                    })
                    running_bal = tx_prev_bal
            elif chan_key == AccountMonitoringChannel.AIRALO:
                from monitoring.models import WithdrawalRecord
                w_qs = WithdrawalRecord.objects.filter(
                    models.Q(system_type='ESIM') | models.Q(purpose_code__icontains='ESIM') | models.Q(title__icontains='Airalo')
                )
                if range_start_dt and range_end_dt:
                    w_qs = w_qs.filter(created_at__range=(range_start_dt, range_end_dt))
                elif range_start_dt:
                    w_qs = w_qs.filter(created_at__gte=range_start_dt)

                raw_wths = w_qs.order_by('-created_at')[:25]
                running_bal = cur_bal_dzd
                for w in raw_wths:
                    amt = float(w.amount_dzd or 0)
                    tx_prev_bal = round(running_bal - amt, 2)
                    tx_list.append({
                        'tid': w.reference or f"WTH-{w.id}",
                        'ref_num': w.p2p_order_id or w.binance_txid or f"Airalo Sourcing #{w.id}",
                        'amount_dzd': amt,
                        'is_credit': True,
                        'fee_amount_dzd': float(w.binance_fee_dzd or 0.0),
                        'previous_balance_dzd': tx_prev_bal,
                        'new_balance_dzd': running_bal,
                        'description': w.title or f"Airalo Wholesale Replenishment ({amt:,.2f} DZD)",
                        'operation_code': f"STAGE_{w.stage}",
                        'timestamp': w.created_at.strftime('%Y-%m-%d %H:%M') if hasattr(w, 'created_at') else '',
                    })
                    running_bal = tx_prev_bal

            t_quota = meta.get('target_quota_dzd')
            effective_bal = balance_at_time if time_filter_active else cur_bal_dzd
            shortfall = round(t_quota - effective_bal, 2) if (t_quota and effective_bal < t_quota) else 0.0
            surplus = round(effective_bal - t_quota, 2) if (t_quota and effective_bal > t_quota) else 0.0
            coverage = round((effective_bal / t_quota) * 100, 1) if t_quota else None

            accounts_result.append({
                'channel': chan_key,
                'title': meta['title'],
                'category': meta['category'],
                'activity': meta['activity'],
                'source': meta['source'],
                'currency': meta['currency'],
                'account_number': meta['account_number'],
                'badge': meta['badge'],
                'current_balance': cur_bal_native,
                'current_balance_dzd': cur_bal_dzd,
                'balance_at_time_dzd': balance_at_time,
                'difference_from_live_dzd': diff_from_live,
                'is_time_filtered': time_filter_active,
                'as_of_time': as_of_dt.strftime('%Y-%m-%d %H:%M') if as_of_dt else None,
                'selected_hour': f"{target_hour:02d}:00" if target_hour is not None else None,
                'previous_balance_dzd': prev_bal_dzd,
                'balance_change_dzd': change_dzd,
                'change_type': change_type,
                'target_quota_dzd': t_quota,
                'available_quota_dzd': effective_bal if t_quota else None,
                'shortfall_dzd': shortfall,
                'surplus_dzd': surplus,
                'coverage_pct': coverage,
                'sourcing_solde_dzd': meta.get('sourcing_solde_dzd'),
                'wallet_balance_dzt': meta.get('wallet_balance_dzt'),
                'linked_route': meta.get('linked_route', '/'),
                'last_update': latest_snap.recorded_at.strftime('%Y-%m-%d %H:%M'),
                'last_sync': latest_snap.last_synced_at.strftime('%Y-%m-%d %H:%M') if latest_snap.last_synced_at else 'Live',
                'graph_points': graph_points,
                'transactions': tx_list,
            })

        return accounts_result

