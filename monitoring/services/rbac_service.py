"""
Institutional Role-Based Access Control (RBAC) Service.
Provisions and enforces institutional operator roles matching the SofizPay Vite Terminal.
All roles, permissions, and log entries strictly adhere to institutional fintech standards.
"""
import logging
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

logger = logging.getLogger(__name__)

INSTITUTIONAL_ROLES = {
    'Super Administrator': {
        'description': 'Master cryptographic and financial administrator with full permissions across all Vite Terminal features and backend settings.',
        'color': '#7c3aed',
        'is_super': True,
        'models': '__all__'
    },
    'Game Family Operator': {
        'description': 'Authorized for Gaming orders, purchasing USDT via Binance P2P using Salah BaridiMob funds, and filling/depositing wholesale inventory into G2Bulk supplier account.',
        'color': '#7c3aed',
        'is_super': False,
        'app_labels': ['monitoring'],
        'models': ['gamingfinancialstatus', 'supplieraccount', 'gamingcapitalentry', 'gameprofitrecord', 'accountworkingcapital', 'baridimobaccount', 'gamingbaridimobaccount', 'withdrawalrecord', 'binanceaccount'],
        'actions': ['add', 'change', 'view']
    },
    'Facture Family Operator': {
        'description': 'Authorized for utility bills settlement monitoring (Sonelgaz, ADE, Algerie Telecom), BaridiMob postal accounts, and funding receipts.',
        'color': '#0284c7',
        'is_super': False,
        'app_labels': ['monitoring'],
        'models': ['utilityfinancialstatus', 'baridimobaccount', 'baridimobfundingreceipt', 'utilitywithdrawalrecord', 'utilitycapitalentry', 'utilitybillrecord', 'accountworkingcapital'],
        'actions': ['add', 'change', 'view']
    },
    'eSIM Family Operator': {
        'description': 'Authorized for telecom eSIM data packages, international profiles distribution, and eSIM working capital settlements.',
        'color': '#059669',
        'is_super': False,
        'app_labels': ['monitoring'],
        'models': ['esimfinancialstatus', 'esimwithdrawalrecord', 'esimcapitalentry', 'accountworkingcapital'],
        'actions': ['add', 'change', 'view']
    },
    'Fintech Treasury Officer': {
        'description': 'Authorized for Stellar blockchain wallet management, cryptographic key configuration, liquidity sweep transfers, and Binance P2P sourcing.',
        'color': '#2563eb',
        'is_super': False,
        'app_labels': ['monitoring'],
        'models': ['stellarwallet', 'walletsweeplog', 'monitoringglobalsettings', 'balanceauditlog', 'binanceaccount', 'binancep2poperation', 'capitalentry', 'expenserecord', 'withdrawalrecord', 'accountworkingcapital'],
        'actions': ['add', 'change', 'view']
    },
    'Withdrawal Operations Officer': {
        'description': 'Authorized strictly for transferring accumulated collection funds from Collection accounts/wallets into Salah BaridiMob account. Does NOT handle Binance USDT purchases or G2Bulk supplier funding.',
        'color': '#ea580c',
        'is_super': False,
        'app_labels': ['monitoring'],
        'models': ['withdrawalrecord', 'baridimobfundingreceipt', 'baridimobaccount', 'gamingbaridimobaccount', 'stellarwallet', 'walletsweeplog', 'expenserecord'],
        'actions': ['add', 'change', 'view']
    },
    'Compliance & Financial Auditor': {
        'description': 'Independent audit and compliance observer with strictly read-only inspection access across all transaction ledgers and security logs.',
        'color': '#475569',
        'is_super': False,
        'app_labels': ['monitoring'],
        'models': '__all__',
        'actions': ['view']
    }
}


class RBACService:
    ROLE_MAPPING = {
        'GAME_OPERATOR': 'Game Family Operator',
        'FACTURE_OPERATOR': 'Facture Family Operator',
        'ESIM_OPERATOR': 'eSIM Family Operator',
        'TREASURY_OFFICER': 'Fintech Treasury Officer',
        'WITHDRAWAL_OFFICER': 'Withdrawal Operations Officer',
        'AUDITOR': 'Compliance & Financial Auditor',
        'ALL_FAMILIES': 'Super Administrator',
    }

    @classmethod
    def assign_multiple_mission_roles(cls, user, mission_roles):
        """Assigns multiple institutional Groups to the user based on their mission roles list."""
        cls.provision_institutional_roles()
        if isinstance(mission_roles, str):
            mission_roles = [r.strip() for r in mission_roles.split(',') if r.strip()]
        elif not isinstance(mission_roles, (list, tuple, set)):
            mission_roles = [mission_roles] if mission_roles else []

        assigned_groups = []
        has_super = False

        for m_role in mission_roles:
            group_name = cls.ROLE_MAPPING.get(m_role)
            if group_name:
                group = Group.objects.filter(name=group_name).first()
                if group and group not in assigned_groups:
                    assigned_groups.append(group)
            if m_role == 'ALL_FAMILIES' or group_name == 'Super Administrator':
                has_super = True

        user.groups.clear()
        if assigned_groups:
            user.groups.add(*assigned_groups)

        user.is_superuser = has_super
        user.is_staff = True
        user.save(update_fields=['is_superuser', 'is_staff'])
        return [g.name for g in assigned_groups]

    @classmethod
    def assign_mission_role(cls, user, mission_role):
        """Assigns the corresponding institutional Group to the user based on their mission role."""
        groups = cls.assign_multiple_mission_roles(user, [mission_role])
        return groups[0] if groups else None
    @classmethod
    def provision_institutional_roles(cls):
        """
        Idempotently creates or updates the 5 institutional Django Groups and maps
        model permissions corresponding to the Vite Frontend operational modules.
        """
        created_count = 0
        with transaction.atomic():
            for role_name, config in INSTITUTIONAL_ROLES.items():
                group, created = Group.objects.get_or_create(name=role_name)
                if created:
                    created_count += 1

                # If super administrator, assign all permissions
                if config.get('is_super'):
                    all_perms = Permission.objects.all()
                    group.permissions.set(all_perms)
                    continue

                target_models = config.get('models', [])
                target_actions = config.get('actions', ['view'])

                if target_models == '__all__':
                    # Auditor: view-only permissions for all monitoring models
                    perms = Permission.objects.filter(
                        content_type__app_label='monitoring',
                        codename__startswith='view_'
                    )
                    group.permissions.set(perms)
                else:
                    perms_to_add = []
                    for model_name in target_models:
                        try:
                            ct = ContentType.objects.get(app_label='monitoring', model=model_name)
                            for act in target_actions:
                                codename = f"{act}_{model_name}"
                                p = Permission.objects.filter(content_type=ct, codename=codename).first()
                                if p:
                                    perms_to_add.append(p)
                        except ContentType.DoesNotExist:
                            continue
                    group.permissions.set(perms_to_add)

        logger.info(f"Institutional RBAC: Provisioned {len(INSTITUTIONAL_ROLES)} groups ({created_count} newly created).")
        return len(INSTITUTIONAL_ROLES)

    @classmethod
    def get_user_role_info(cls, user):
        """Returns structured role badge info for an operator user"""
        if not user or not user.is_authenticated:
            return {'name': 'Anonymous', 'color': '#94a3b8', 'description': 'Unauthenticated user'}

        if user.is_superuser:
            return {
                'name': 'Super Administrator',
                'color': '#7c3aed',
                'description': 'Full Master Administrator with unrestricted cryptographic and financial access.'
            }

        user_groups = list(user.groups.values_list('name', flat=True))
        for role_name, info in INSTITUTIONAL_ROLES.items():
            if role_name in user_groups:
                return {
                    'name': role_name,
                    'color': info['color'],
                    'description': info['description']
                }

        if user.is_staff:
            return {'name': 'Staff Operator', 'color': '#2563eb', 'description': 'Internal staff operator'}
        return {'name': 'Standard User', 'color': '#64748b', 'description': 'Standard system user'}
