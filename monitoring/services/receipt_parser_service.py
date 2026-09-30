"""
BaridiMob Receipt Parser & Data Extraction Service for SofizAdmin
Extracts transaction reference, amount, sender/recipient RIPs, and fees from BaridiMob PDF receipts or images.
Implements SHA256 deduplication to prevent duplicate receipt submissions.
"""
import re
import os
import io
import hashlib
import logging
import subprocess
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)


class ReceiptParserError(Exception):
    pass


class DuplicateReceiptError(ReceiptParserError):
    pass


class ReceiptParserService:

    @staticmethod
    def calculate_file_hash(file_obj) -> str:
        """Calculates SHA256 hash of uploaded file content to prevent exact duplicate uploads"""
        hasher = hashlib.sha256()
        if hasattr(file_obj, 'chunks'):
            for chunk in file_obj.chunks():
                hasher.update(chunk)
            file_obj.seek(0)
        elif hasattr(file_obj, 'read'):
            pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
            hasher.update(file_obj.read())
            file_obj.seek(pos)
        elif isinstance(file_obj, (str, bytes)):
            if isinstance(file_obj, str) and os.path.isfile(file_obj):
                with open(file_obj, 'rb') as f:
                    hasher.update(f.read())
            else:
                hasher.update(file_obj if isinstance(file_obj, bytes) else file_obj.encode('utf-8'))
        return hasher.hexdigest()

    @classmethod
    def check_receipt_usage(cls, file_hash: str = None, reference: str = None, exclude_withdrawal_id: int = None, exclude_receipt_id: int = None) -> dict:
        """
        Institutional Anti-Reuse / Anti-Double-Spending Verification.
        Verifies that neither the SHA256 file hash nor the transaction reference
        has been utilized in any existing WithdrawalRecord or processed BaridiMobFundingReceipt.
        """
        from monitoring.models import WithdrawalRecord, BaridiMobFundingReceipt, FundingCycleStatus
        from django.db.models import Q

        # 1. Check in WithdrawalRecord
        w_query = Q()
        if file_hash:
            w_query |= Q(file_hash=file_hash)
        if reference and len(reference.strip()) >= 4:
            clean_ref = reference.strip()
            w_query |= Q(reference__iexact=clean_ref)

        if w_query:
            qs = WithdrawalRecord.objects.filter(w_query)
            if exclude_withdrawal_id:
                qs = qs.exclude(id=exclude_withdrawal_id)
            existing_w = qs.first()
            if existing_w:
                ref_label = existing_w.reference or reference or "N/A"
                return {
                    'is_used': True,
                    'used_in': 'WITHDRAWAL',
                    'record_id': existing_w.id,
                    'title': existing_w.title,
                    'reference': ref_label,
                    'date': str(existing_w.withdrawal_date),
                    'amount_dzd': float(existing_w.amount_dzd),
                    'stage': existing_w.stage,
                    'reason': f"Receipt reference '{ref_label}' has already been used in Withdrawal #{existing_w.id} ({existing_w.title}). Reusing receipts is strictly forbidden.",
                }

        # 2. Check in BaridiMobFundingReceipt
        f_query = Q()
        if file_hash:
            f_query |= Q(file_hash=file_hash)
        if reference and len(reference.strip()) >= 4:
            clean_ref = reference.strip()
            f_query |= Q(reference__iexact=clean_ref)

        if f_query:
            qs_f = BaridiMobFundingReceipt.objects.filter(f_query)
            if exclude_receipt_id:
                qs_f = qs_f.exclude(id=exclude_receipt_id)
            existing_f = qs_f.first()
            if existing_f:
                # Check if linked to any withdrawal
                linked_w = existing_f.withdrawal_record or existing_f.linked_withdrawal_records.first()
                if linked_w and (not exclude_withdrawal_id or linked_w.id != exclude_withdrawal_id):
                    return {
                        'is_used': True,
                        'used_in': 'WITHDRAWAL_LINKED',
                        'record_id': linked_w.id,
                        'title': linked_w.title,
                        'reference': existing_f.reference,
                        'date': str(linked_w.withdrawal_date),
                        'amount_dzd': float(linked_w.amount_dzd),
                        'stage': linked_w.stage,
                        'reason': f"Receipt #{existing_f.reference} is already linked to Withdrawal #{linked_w.id} ({linked_w.title}). Reusing receipts is strictly forbidden.",
                    }

                # Check if funding cycle itself is already consumed / beyond PENDING_P2P
                if existing_f.status != FundingCycleStatus.PENDING_P2P:
                    return {
                        'is_used': True,
                        'used_in': 'FUNDING_CYCLE',
                        'record_id': existing_f.id,
                        'reference': existing_f.reference,
                        'status': existing_f.get_status_display(),
                        'amount_dzd': float(existing_f.amount_dzd or 0),
                        'reason': f"Receipt #{existing_f.reference} has already been processed in Funding Cycle #{existing_f.id} (Status: {existing_f.get_status_display()}). Reusing receipts is strictly forbidden.",
                    }

        return {'is_used': False}

    @classmethod
    def extract_text_from_pdf(cls, file_obj) -> str:
        """Extracts text from PDF using pypdf with fallback to pdftotext binary"""
        raw_text = ""
        
        # 1. Try pypdf first (Python native)
        try:
            from pypdf import PdfReader
            if hasattr(file_obj, 'chunks') or hasattr(file_obj, 'read'):
                pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
                reader = PdfReader(file_obj)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        raw_text += text + "\n"
                file_obj.seek(pos)
            elif isinstance(file_obj, str) and os.path.isfile(file_obj):
                reader = PdfReader(file_obj)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        raw_text += text + "\n"
        except Exception as e:
            logger.warning(f"pypdf extraction failed or partial: {e}")

        # 2. Fallback to pdftotext if pypdf got nothing
        if not raw_text.strip():
            try:
                import tempfile
                temp_path = None
                if hasattr(file_obj, 'chunks'):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                        for chunk in file_obj.chunks():
                            tmp.write(chunk)
                        temp_path = tmp.name
                    file_obj.seek(0)
                elif isinstance(file_obj, str) and os.path.isfile(file_obj):
                    temp_path = file_obj

                if temp_path:
                    res = subprocess.run(['pdftotext', '-layout', temp_path, '-'], capture_output=True, text=True, timeout=15)
                    if res.returncode == 0 and res.stdout:
                        raw_text = res.stdout
                    if temp_path != file_obj and os.path.exists(temp_path):
                        os.remove(temp_path)
            except Exception as e:
                logger.error(f"pdftotext binary extraction failed: {e}")

        return raw_text

    @classmethod
    def parse_receipt(cls, file_obj, filename: str = "", system_type: str = None) -> dict:
        """Alias for parse_baridimob_receipt"""
        return cls.parse_baridimob_receipt(file_obj, filename, system_type=system_type)

    @classmethod
    def parse_baridimob_receipt(cls, file_obj, filename: str = "", system_type: str = None) -> dict:
        """
        Parses BaridiMob electronic receipt (PDF or Image) and extracts:
        - reference: N° de transaction / Référence
        - amount_dzd: Decimal
        - fee_dzd: Decimal (standard 50.00 DZD)
        - sender_rip: str
        - recipient_rip: str
        - date_str: str
        - file_hash: str
        - raw_text: str
        """
        file_hash = cls.calculate_file_hash(file_obj)
        if isinstance(file_obj, str):
            name_lower = (filename or file_obj).lower()
        else:
            name_lower = (filename or getattr(file_obj, 'name', '')).lower()
        raw_text = ""

        if name_lower.endswith('.pdf') or 'pdf' in getattr(file_obj, 'content_type', ''):
            raw_text = cls.extract_text_from_pdf(file_obj)
        else:
            # Image handling (if PIL / image)
            raw_text = f"[Image Upload: {name_lower}]"

        extracted = cls._parse_text_fields(raw_text)
        extracted["file_hash"] = file_hash
        extracted["raw_text"] = raw_text
        extracted["account_verification"] = cls.verify_recipient_account(
            recipient_rip=extracted.get("recipient_rip"),
            sender_rip=extracted.get("sender_rip"),
            system_type=system_type
        )

        return extracted

    @classmethod
    def verify_recipient_account(cls, recipient_rip: str = None, sender_rip: str = None, system_type: str = None) -> dict:
        """
        Validates that the recipient address/RIP extracted from the BaridiMob receipt
        is registered and stored in the system's authorized BaridiMobAccount ledger.
        Strict Security Policy: Reject sending funds to any external account not registered in the system.
        """
        from monitoring.models import BaridiMobAccount, SubSystemType
        from django.db import models

        clean_recip = re.sub(r'\D', '', str(recipient_rip or '')).strip()
        clean_sender = re.sub(r'\D', '', str(sender_rip or '')).strip()

        # Build query for active system accounts, optionally filtering by system_type if provided
        q_filter = models.Q(is_active=True)
        if system_type:
            q_filter &= (models.Q(system_type=system_type) | models.Q(system_type=SubSystemType.ALL))

        # 1. Primary Check: Recipient RIP exists in active system accounts
        if clean_recip:
            acc = BaridiMobAccount.objects.filter(q_filter, rip_number=clean_recip).first()
            if not acc and not system_type:
                acc = BaridiMobAccount.objects.filter(rip_number=clean_recip, is_active=True).first()
            if acc:
                return {
                    'is_registered': True,
                    'account_id': acc.id,
                    'account_name': acc.account_name,
                    'rip_number': acc.rip_number,
                    'system_type': acc.system_type,
                    'role': 'RECIPIENT',
                    'message': f"Verified authorized system account for {acc.get_system_type_display()}: {acc.account_name} (RIP: {acc.rip_number})"
                }

        # 2. Secondary Check: Sender RIP exists in active system accounts
        if clean_sender:
            acc = BaridiMobAccount.objects.filter(q_filter, rip_number=clean_sender).first()
            if not acc and not system_type:
                acc = BaridiMobAccount.objects.filter(rip_number=clean_sender, is_active=True).first()
            if acc:
                return {
                    'is_registered': True,
                    'account_id': acc.id,
                    'account_name': acc.account_name,
                    'rip_number': acc.rip_number,
                    'system_type': acc.system_type,
                    'role': 'SENDER',
                    'message': f"Verified authorized system account for {acc.get_system_type_display()}: {acc.account_name} (RIP: {acc.rip_number})"
                }

        # Fallback check: if the RIP is in system accounts under a different subsystem, give clear informative message
        existing_other = None
        if clean_recip:
            existing_other = BaridiMobAccount.objects.filter(rip_number=clean_recip, is_active=True).first()
        elif clean_sender:
            existing_other = BaridiMobAccount.objects.filter(rip_number=clean_sender, is_active=True).first()

        target_rip = clean_recip or clean_sender or "N/A"
        if existing_other:
            return {
                'is_registered': True,
                'account_id': existing_other.id,
                'account_name': existing_other.account_name,
                'rip_number': existing_other.rip_number,
                'system_type': existing_other.system_type,
                'role': 'SYSTEM_ACCOUNT',
                'message': f"System account: {existing_other.account_name} ({target_rip})"
            }

        return {
            'is_registered': False,
            'is_external': True,
            'target_rip': target_rip,
            'role': 'EXTERNAL_COUNTERPARTY',
            'message': f"External counterparty / P2P seller account: {target_rip}"
        }

    @classmethod
    def _parse_text_fields(cls, text: str) -> dict:
        """Extracts fields using robust regex patterns for French and Arabic BaridiMob formats"""
        result = {
            "reference": None,
            "amount_dzd": None,
            "fee_dzd": Decimal("50.00"),
            "sender_rip": None,
            "recipient_rip": None,
            "date_str": None,
        }

        if not text or not text.strip():
            return result

        # 1. Transaction Reference (External ID / Identifiant de transaction / N° de transaction / Référence / رقم المعاملة)
        ref_match = re.search(
            r'(?:Identifiant\s*de\s*transa[c]?tion|N[°o]\s*(?:de\s*)?transa[c]?tion|External\s*id|External\s*ID|Transaction\s*ID|Operation\s*ID|R[ée]f[ée]rence|رقم\s*المعاملة|رقم\s*العملية|المرجع)\s*[:：\-]?\s*([A-Za-z0-9\-_]{6,30})',
            text,
            re.IGNORECASE
        )
        if ref_match:
            result["reference"] = ref_match.group(1).strip()
        else:
            # Fallback: look for 10-20 digit transaction numbers
            num_match = re.search(r'\b(202\d{9,16}|\d{10,18})\b', text)
            if num_match:
                result["reference"] = num_match.group(1).strip()

        # 2. Amount in DZD (Amount / Montant / DZD)
        amount_patterns = [
            r'(?:Montant|Montant\s*du\s*virement|Amount|Transfer\s*Amount|Total\s*Amount|المبلغ|المبلغ\s*المحول|القيمة)\s*[:：\-]?\s*([\d\s,\.]+)\s*(?:DZD|DA|دج)?',
            r'([\d\s,\.]+)\s*(?:DZD|DA|دج)\b',
        ]
        for pat in amount_patterns:
            matches = re.finditer(pat, text, re.IGNORECASE)
            for m in matches:
                raw_amt = m.group(1).strip()
                parsed_amt = cls._clean_decimal(raw_amt)
                if parsed_amt and parsed_amt > Decimal("0.00"):
                    # Don't pick 50.00 as main amount if it's the standard fee
                    if parsed_amt != Decimal("50.00") or result["amount_dzd"] is None:
                        result["amount_dzd"] = parsed_amt
                        break
            if result["amount_dzd"]:
                break

        # 3. Fees (Fee / Frais / Commission)
        fee_match = re.search(
            r'(?:Frais|Commission|Fee[s]?|الرسوم|العمولة)\s*[:：\-]?\s*([\d\s,\.]+)\s*(?:DZD|DA|دج)?',
            text,
            re.IGNORECASE
        )
        if fee_match:
            parsed_fee = cls._clean_decimal(fee_match.group(1).strip())
            if parsed_fee:
                result["fee_dzd"] = parsed_fee

        # 4. RIP Numbers (20 digits starting with 007)
        recip_match = re.search(r'(?:Recipient|Destinataire|Beneficiary|المستفيد)\s*[:：\-]?\s*(007\d{17})', text, re.IGNORECASE)
        if recip_match:
            result["recipient_rip"] = recip_match.group(1).strip()

        sender_match = re.search(r'(?:Sender|Emetteur|Exp[ée]diteur|المرسل)\s*[:：\-]?\s*(007\d{17})', text, re.IGNORECASE)
        if sender_match:
            result["sender_rip"] = sender_match.group(1).strip()

        # Fallback to positional RIPs if contextual search did not find both
        rips = re.findall(r'\b(007\d{17})\b', text)
        if not result["recipient_rip"]:
            if len(rips) >= 2:
                result["sender_rip"] = rips[0]
                result["recipient_rip"] = rips[1]
            elif len(rips) == 1:
                result["recipient_rip"] = rips[0]
        elif not result["sender_rip"] and len(rips) >= 2:
            for r in rips:
                if r != result["recipient_rip"]:
                    result["sender_rip"] = r
                    break

        # 5. Date
        date_match = re.search(r'(\d{2}[\/\-\.]\d{2}[\/\-\.]\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)', text)
        if date_match:
            result["date_str"] = date_match.group(1).strip()

        return result

    @staticmethod
    def _clean_decimal(val_str: str) -> Decimal:
        """Converts strings like '100 000,00' or '100,000.00' to Decimal"""
        if not val_str:
            return None
        cleaned = val_str.replace(' ', '').replace('\xa0', '').strip()
        # Handle comma as decimal separator vs thousands separator
        if ',' in cleaned and '.' in cleaned:
            if cleaned.rfind('.') > cleaned.rfind(','):
                cleaned = cleaned.replace(',', '')
            else:
                cleaned = cleaned.replace('.', '').replace(',', '.')
        elif ',' in cleaned:
            cleaned = cleaned.replace(',', '.')

        cleaned = re.sub(r'[^\d\.]', '', cleaned)
        try:
            return Decimal(cleaned).quantize(Decimal('0.01'))
        except Exception:
            return None
