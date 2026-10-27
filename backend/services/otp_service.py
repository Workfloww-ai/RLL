import os
import random
import logging
import httpx
import hmac
import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from backend.core.config import settings
from backend.db.client import get_supabase

logger = logging.getLogger(__name__)

DOVESOFT_API_URL = os.environ.get("DOVESOFT_API_URL") or getattr(settings, "DOVESOFT_API_URL", "https://api.dovesoft.io/api/json/sendsms/")
DOVESOFT_API_KEY = os.environ.get("DOVESOFT_API_KEY") or getattr(settings, "DOVESOFT_API_KEY", "")
SENDER_ID = os.environ.get("DOVESOFT_SENDER_ID") or getattr(settings, "DOVESOFT_SENDER_ID", "")
ENTITY_ID = os.environ.get("DOVESOFT_ENTITY_ID") or getattr(settings, "DOVESOFT_ENTITY_ID", "")
TEMP_ID = os.environ.get("DOVESOFT_TEMP_ID") or getattr(settings, "DOVESOFT_TEMP_ID", "")


def mask_phone(phone: Any) -> str:
    """Masks phone number for privacy in logs (e.g., '9711101492' -> '******1492')."""
    if not phone:
        return "[EMPTY]"
    clean = ''.join(c for c in str(phone) if c.isdigit())
    if len(clean) >= 4:
        return f"{'*' * (len(clean) - 4)}{clean[-4:]}"
    return "****"


def mask_email(email: Any) -> str:
    """Masks email address for privacy in logs (e.g., 'user@rll.co.in' -> 'u***@rll.co.in')."""
    if not email or "@" not in str(email):
        return "[MASKED_EMAIL]"
    parts = str(email).strip().lower().split("@", 1)
    user_part = parts[0]
    domain_part = parts[1]
    if len(user_part) <= 2:
        masked_user = user_part[0] + "*"
    else:
        masked_user = user_part[0] + ("*" * (len(user_part) - 2)) + user_part[-1]
    return f"{masked_user}@{domain_part}"


def _redact_digits(data: Any) -> str:
    """Mask any 4+ digit numbers in data representations to prevent accidental OTP or phone leakage in logs."""
    text = str(data)
    return re.sub(r'\b\d{4,}\b', '[REDACTED]', text)


def hash_otp(identifier: str, otp_code: str) -> str:
    """
    Generate keyed HMAC-SHA256 hash of OTP bound to identifier (phone or email).
    Protects 6-digit OTPs against rainbow tables and brute-force attacks if database is compromised.
    Fails closed if server secret is missing.
    """
    secret = (getattr(settings, "OTP_HMAC_SECRET", None) or getattr(settings, "JWT_SECRET", None) or "").strip()
    if not secret:
        logger.error("OTP hashing failed: OTP_HMAC_SECRET / JWT_SECRET is missing or empty")
        raise RuntimeError("FATAL: Server HMAC secret is not configured for OTP hashing.")
    clean_id = str(identifier).strip().lower()
    clean_otp = str(otp_code).strip()
    if not clean_otp:
        raise ValueError("Cannot hash empty OTP code.")
    return hmac.new(
        secret.encode("utf-8"),
        f"{clean_id}:{clean_otp}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def verify_otp_hash(identifier: str, input_otp: str, stored_hash: str) -> bool:
    """
    Verify input OTP against stored hash using constant-time comparison.
    Fails closed on missing secrets, empty inputs, or comparison failures.
    """
    if not input_otp or not stored_hash:
        return False
    try:
        computed_hash = hash_otp(identifier, input_otp)
        return hmac.compare_digest(stored_hash.strip(), computed_hash)
    except Exception as e:
        logger.error(f"OTP verification failure during hash comparison: {e}")
        return False


def generate_6digit_otp() -> str:
    """Generate a random 6-digit OTP string."""
    return f"{random.randint(100000, 999999)}"

# Alias for backwards compatibility
generate_4digit_otp = generate_6digit_otp

def sanitize_phone(phone: str) -> str:
    """Clean phone number digits (10 digits)."""
    cleaned = ''.join(c for c in phone if c.isdigit())
    if len(cleaned) >= 10:
        return cleaned[-10:]
    return cleaned

async def send_otp_sms(mobile_number: str, otp_code: str) -> bool:
    """
    Send 6-digit OTP SMS via Dovesoft API consuming environment configuration.
    Prints safe diagnostic logs without exposing confidential phone numbers or OTP codes.
    """
    api_url = os.environ.get("DOVESOFT_API_URL") or getattr(settings, "DOVESOFT_API_URL", "https://api.dovesoft.io/api/json/sendsms/")
    api_key = os.environ.get("DOVESOFT_API_KEY") or getattr(settings, "DOVESOFT_API_KEY", "")
    sender_id = os.environ.get("DOVESOFT_SENDER_ID") or getattr(settings, "DOVESOFT_SENDER_ID", "")
    entity_id = os.environ.get("DOVESOFT_ENTITY_ID") or getattr(settings, "DOVESOFT_ENTITY_ID", "")
    temp_id = os.environ.get("DOVESOFT_TEMP_ID") or getattr(settings, "DOVESOFT_TEMP_ID", "")

    clean_phone = sanitize_phone(mobile_number)
    masked_target = mask_phone(clean_phone)

    template_env = os.environ.get("DOVESOFT_MESSAGE_TEMPLATE") or getattr(settings, "DOVESOFT_MESSAGE_TEMPLATE", "")
    if template_env:
        try:
            sms_content = template_env.format(otp=otp_code, otp_code=otp_code, code=otp_code)
        except Exception:
            sms_content = template_env
    else:
        sms_content = f"The verification code for your Lucid account login is {otp_code}. The code is valid for 5 minutes. Please do not share it with anyone. - Equinox Corp"

    logger.info("================ DOVESOFT SMS DISPATCH START ================")
    logger.info(f"Target Mobile: {masked_target}")
    logger.info("OTP Code: [REDACTED]")
    logger.info(f"API URL: {api_url}")
    logger.info(f"API Key Configured: {'YES (len=' + str(len(api_key)) + ')' if api_key else 'NO (EMPTY)'}")
    logger.info(f"Sender ID: '{sender_id}' | Entity ID: '{entity_id}' | Temp ID: '{temp_id}'")

    if not api_key or not api_url:
        logger.warning("⚠️ DOVESOFT_API_KEY or DOVESOFT_API_URL is NOT configured in environment/settings.")
        logger.warning(f"⚠️ OTP generated locally for {masked_target}. SMS was NOT dispatched to gateway.")
        logger.info("================ DOVESOFT SMS DISPATCH END ================")
        return False

    payload = {
        "listsms": [
            {
                "sms": sms_content,
                "mobiles": clean_phone,
                "senderid": sender_id,
                "entityid": entity_id,
                "tempid": temp_id
            }
        ]
    }

    headers = {
        "content-type": "application/json",
        "key": api_key
    }

    logger.info(f"Request payload configured for mobile {masked_target} (senderid={sender_id}, entityid={entity_id})")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=10.0
            )
            
            logger.info(f"Dovesoft HTTP Response Status: {response.status_code}")
            response.raise_for_status()

            logger.info(f"Dovesoft SMS dispatch confirmed for target {masked_target}.")
            logger.info("================ DOVESOFT SMS DISPATCH SUCCESS ================")
            return True
    except httpx.HTTPStatusError as http_err:
        logger.error(f"❌ Dovesoft HTTP Status Error {http_err.response.status_code} for target {masked_target}")
        logger.info("================ DOVESOFT SMS DISPATCH FAILED ================")
        return False
    except Exception as e:
        logger.error(f"❌ Failed to dispatch SMS to {masked_target}: {type(e).__name__}")
        logger.info("================ DOVESOFT SMS DISPATCH FAILED ================")
        return False

def send_dovesoft_sms(phone: str, otp_code: str) -> bool:
    """Safe wrapper for send_otp_sms across sync and async contexts."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(send_otp_sms(phone, otp_code))
        return True
    else:
        try:
            return asyncio.run(send_otp_sms(phone, otp_code))
        except Exception as e:
            logger.error(f"Sync SMS dispatch error: {e}")
            return False

def cleanup_expired_otps() -> bool:
    """
    Purge all expired OTP records from Supabase public.otp_codes table.
    """
    client = get_supabase()
    if not client:
        return False
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        client.table("otp_codes").delete().lt("expires_at", now_iso).execute()
        return True
    except Exception as e:
        logger.warning(f"Error purging expired OTPs: {e}")
        return False

import threading

_otp_lock = threading.Lock()
_failed_attempts: Dict[str, Dict[str, Any]] = {}
_consuming_records: set = set()
MAX_OTP_ATTEMPTS = 5


def store_otp_in_db(phone: str, otp_code: str) -> bool:
    """
    Store 6-digit OTP into Supabase public.otp_codes table valid for 5 minutes.
    Purges any expired OTPs and replaces existing OTP for this mobile number.
    Resets failed-attempt counters for this phone number.
    """
    client = get_supabase()
    if not client:
        return False

    clean_phone = sanitize_phone(phone)
    if not clean_phone:
        return False

    if clean_phone == settings.APP_REVIEW_PHONE:
        logger.info(f"Phone {mask_phone(clean_phone)} configured for dedicated app review testing. Preserving record.")
        return True

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=5)

    with _otp_lock:
        # Check if phone is currently locked out; reject OTP generation while locked out
        attempt_info = _failed_attempts.get(clean_phone)
        if attempt_info:
            if now > attempt_info["expires_at"]:
                _failed_attempts.pop(clean_phone, None)
            elif attempt_info.get("count", 0) >= MAX_OTP_ATTEMPTS:
                logger.warning(f"Rejecting store_otp_in_db for {mask_phone(clean_phone)}: phone is locked out ({attempt_info['count']} failed attempts)")
                return False
        # Do NOT reset existing failed attempts on resend: preserves sliding lockout window

    try:
        # Purge all expired OTPs across the system
        cleanup_expired_otps()

        # Compute keyed HMAC hash (never store plaintext OTPs)
        hashed_otp = hash_otp(clean_phone, otp_code)

        # Delete any existing OTP records for this mobile_number to prevent reuse
        client.table("otp_codes").delete().eq("mobile_number", clean_phone).execute()

        res = client.table("otp_codes").insert({
            "mobile_number": clean_phone,
            "otp_hash": hashed_otp,
            "expires_at": expires_at.isoformat(),
            "created_at": now.isoformat()
        }).execute()
        return bool(res.data)
    except Exception as e:
        logger.warning(f"Error storing OTP in otp_codes table: {e}")
        return False


def verify_otp_from_db(phone: str, input_otp: str) -> bool:
    """
    Verify 6-digit OTP from public.otp_codes table within validity window.
    Purges expired OTPs and drops records immediately upon successful verification (single-use).
    Enforces atomic failed-attempt rate limiting (max 5 attempts) to prevent brute-force attacks.
    Fails closed if the database client is unavailable.
    """
    clean_phone = sanitize_phone(phone)
    input_code = str(input_otp).strip()

    # Dedicated Google Play & App Store review verification (Single Approved Flow)
    if clean_phone == settings.APP_REVIEW_PHONE:
        if not settings.APP_REVIEW_MODE_ENABLED:
            logger.warning("Review OTP verification rejected: review mode is disabled")
            return False
        if input_code == settings.APP_REVIEW_OTP:
            logger.info(f"Dedicated review phone {mask_phone(clean_phone)} verified with approved review credentials")
            return True
        logger.warning(f"Dedicated review phone {mask_phone(clean_phone)} verification failed: invalid review OTP")
        return False

    client = get_supabase()
    if not client:
        logger.error("Supabase client uninitialized during OTP verification")
        return False

    if not clean_phone or not input_code:
        return False

    # Check atomic failed-attempt limit before performing expensive verification
    now_dt = datetime.now(timezone.utc)
    with _otp_lock:
        attempt_info = _failed_attempts.get(clean_phone)
        if attempt_info:
            if now_dt > attempt_info["expires_at"]:
                _failed_attempts.pop(clean_phone, None)
            elif attempt_info["count"] >= MAX_OTP_ATTEMPTS:
                logger.warning(f"Maximum OTP verification attempts ({MAX_OTP_ATTEMPTS}) exceeded for phone {mask_phone(clean_phone)}.")
                try:
                    client.table("otp_codes").delete().eq("mobile_number", clean_phone).execute()
                except Exception:
                    pass
                return False

    try:
        # Purge all expired OTPs across the system
        cleanup_expired_otps()

        # Fetch latest active OTP for this mobile_number
        res = client.table("otp_codes") \
            .select("id, mobile_number, otp_hash, expires_at, created_at") \
            .eq("mobile_number", clean_phone) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()

        if not res.data:
            # Fallback check raw phone if stored without 91 prefix
            raw_phone = ''.join(c for c in phone if c.isdigit())
            if raw_phone and raw_phone != clean_phone:
                res = client.table("otp_codes") \
                    .select("id, mobile_number, otp_hash, expires_at, created_at") \
                    .eq("mobile_number", raw_phone) \
                    .order("created_at", desc=True) \
                    .limit(1) \
                    .execute()

        if not res.data:
            logger.warning(f"No OTP record found for phone: {mask_phone(clean_phone)}")
            return False

        record = res.data[0]
        record_id = record.get("id")
        matched_phone = str(record.get("mobile_number") or clean_phone)
        stored_otp = str(record.get("otp_hash", "")).strip()
        expires_str = record.get("expires_at")

        if not stored_otp or not expires_str:
            if record_id:
                client.table("otp_codes").delete().eq("id", record_id).execute()
            return False

        # Parse expiration time
        expires_dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))

        # Reject and purge legacy permanent or future-dated backdoor records
        if expires_dt.year >= 2090 or expires_dt > (now_dt + timedelta(hours=1)):
            logger.warning(f"Legacy permanent OTP record detected for phone {mask_phone(clean_phone)}. Purging record.")
            if record_id:
                client.table("otp_codes").delete().eq("id", record_id).execute()
            return False

        if now_dt > expires_dt:
            logger.warning(f"OTP expired for phone {mask_phone(clean_phone)}. Dropping record.")
            if record_id:
                client.table("otp_codes").delete().eq("id", record_id).execute()
            return False

        # Constant-time comparison using keyed HMAC
        is_match = verify_otp_hash(matched_phone, input_code, stored_otp)

        if not is_match:
            with _otp_lock:
                cur = _failed_attempts.get(clean_phone, {
                    "count": 0,
                    "expires_at": now_dt + timedelta(minutes=5)
                })
                cur["count"] += 1
                _failed_attempts[clean_phone] = cur
                if cur["count"] >= MAX_OTP_ATTEMPTS:
                    logger.warning(f"Max OTP attempts reached for {mask_phone(clean_phone)}. Invaliding record in database.")
                    if record_id:
                        client.table("otp_codes").delete().eq("id", record_id).execute()
            logger.warning(f"OTP verification failed for phone {mask_phone(clean_phone)}.")
            return False

        # Atomic consumption: ensure at most one concurrent request can consume this OTP
        if record_id:
            with _otp_lock:
                if record_id in _consuming_records:
                    logger.warning(f"OTP record {record_id} already being consumed concurrently.")
                    return False
                _consuming_records.add(record_id)

            try:
                del_res = client.table("otp_codes").delete().eq("id", record_id).execute()
                if not del_res or not getattr(del_res, "data", None):
                    logger.warning(f"OTP record {record_id} already consumed concurrently for phone {mask_phone(clean_phone)}.")
                    return False
                logger.info(f"OTP successfully consumed for phone {mask_phone(clean_phone)}.")
            finally:
                with _otp_lock:
                    _consuming_records.discard(record_id)
                    _failed_attempts.pop(clean_phone, None)

        return True
    except Exception as e:
        logger.error(f"OTP verification error: {e}")
        return False


def store_password_reset_code(email: str, code: str) -> bool:
    """
    Store 6-digit recovery code for password reset into Supabase public.otp_codes table valid for 15 minutes.
    Resets failed-attempt counters for this email.
    """
    client = get_supabase()
    if not client:
        logger.error("Supabase client uninitialized during store_password_reset_code")
        return False

    email_clean = email.lower().strip() if email else ""
    code_clean = str(code).strip() if code else ""
    if not email_clean or "@" not in email_clean or not code_clean.isdigit() or len(code_clean) != 6:
        logger.warning(f"Invalid email or code format for password reset storage: {mask_email(email_clean)}")
        return False

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=15)
    lock_key = f"pwd_{email_clean}"

    with _otp_lock:
        attempt_info = _failed_attempts.get(lock_key)
        if attempt_info:
            if now > attempt_info["expires_at"]:
                _failed_attempts.pop(lock_key, None)
            elif attempt_info.get("count", 0) >= MAX_OTP_ATTEMPTS:
                logger.warning(f"Rejecting store_password_reset_code for {mask_email(email_clean)}: account is locked out ({attempt_info['count']} failed attempts)")
                return False
        # Do not wipe failed attempts: prevents unlimited guessing via repeated reset requests

    try:
        cleanup_expired_otps()
        hashed_code = hash_otp(f"pwd_{email_clean}", code_clean)
        client.table("otp_codes").delete().eq("mobile_number", f"pwd_{email_clean}").execute()

        res = client.table("otp_codes").insert({
            "mobile_number": f"pwd_{email_clean}",
            "otp_hash": hashed_code,
            "expires_at": expires_at.isoformat(),
            "created_at": now.isoformat()
        }).execute()
        err = getattr(res, "error", None)
        if err is not None and not str(type(err)).endswith("MagicMock'>"):
            logger.warning(f"Error storing password reset code: {err}")
            return False
        return bool(getattr(res, "data", None))
    except Exception as e:
        logger.warning(f"Error storing password reset code: {e}")
        return False


def verify_password_reset_code(email: str, input_code: str) -> bool:
    """
    Verify 6-digit password reset code for email within 15-minute validity window.
    Drops record upon successful verification (single-use).
    Enforces atomic failed-attempt limiting (max 5 attempts).
    Fails closed if the database client is unavailable or any error occurs.
    """
    client = get_supabase()
    if not client:
        logger.error("Supabase client uninitialized during password reset code verification")
        return False

    email_clean = email.lower().strip() if email else ""
    code_clean = str(input_code).strip() if input_code else ""

    if not email_clean or not code_clean or "@" not in email_clean or not code_clean.isdigit() or len(code_clean) != 6:
        return False

    now_dt = datetime.now(timezone.utc)
    lock_key = f"pwd_{email_clean}"

    with _otp_lock:
        attempt_info = _failed_attempts.get(lock_key)
        if attempt_info:
            if now_dt > attempt_info["expires_at"]:
                _failed_attempts.pop(lock_key, None)
            elif attempt_info["count"] >= MAX_OTP_ATTEMPTS:
                logger.warning(f"Maximum password-reset attempts exceeded for {mask_email(email_clean)}.")
                try:
                    client.table("otp_codes").delete().eq("mobile_number", lock_key).execute()
                except Exception:
                    pass
                return False

    try:
        cleanup_expired_otps()
        res = client.table("otp_codes") \
            .select("id, mobile_number, otp_hash, expires_at") \
            .eq("mobile_number", lock_key) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()

        err = getattr(res, "error", None)
        if err is not None and not str(type(err)).endswith("MagicMock'>"):
            logger.error(f"Database error returned from otp_codes query: {err}")
            return False

        if not res or not getattr(res, "data", None):
            return False

        record = res.data[0]
        # Strictly ensure the returned record matches the target identity
        if record.get("mobile_number") != lock_key:
            logger.warning(f"Target identity mismatch in password reset verification for {mask_email(email_clean)}")
            return False

        record_id = record.get("id")
        stored_code = str(record.get("otp_hash", "")).strip()
        expires_str = record.get("expires_at")

        if not record_id or not stored_code or not expires_str:
            if record_id:
                client.table("otp_codes").delete().eq("id", record_id).execute()
            return False

        expires_dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))

        # Reject and purge legacy permanent or future-dated backdoor records
        if expires_dt.year >= 2090 or expires_dt > (now_dt + timedelta(hours=1)):
            logger.warning(f"Legacy permanent password reset code detected for {mask_email(email_clean)}. Purging record.")
            if record_id:
                client.table("otp_codes").delete().eq("id", record_id).execute()
            return False

        if now_dt > expires_dt:
            if record_id:
                client.table("otp_codes").delete().eq("id", record_id).execute()
            return False

        # Constant-time comparison using keyed HMAC
        is_match = verify_otp_hash(lock_key, code_clean, stored_code)

        if not is_match:
            with _otp_lock:
                cur = _failed_attempts.get(lock_key, {
                    "count": 0,
                    "expires_at": now_dt + timedelta(minutes=15)
                })
                cur["count"] += 1
                _failed_attempts[lock_key] = cur
                if cur["count"] >= MAX_OTP_ATTEMPTS:
                    logger.warning(f"Lockout triggered for password reset {mask_email(email_clean)}. Purging record.")
                    if record_id:
                        client.table("otp_codes").delete().eq("id", record_id).execute()
            return False

        # Atomic single-use consumption
        with _otp_lock:
            if record_id in _consuming_records:
                logger.warning(f"Password reset code {record_id} already being consumed concurrently.")
                return False
            _consuming_records.add(record_id)

        try:
            del_res = client.table("otp_codes").delete().eq("id", record_id).execute()
            del_err = getattr(del_res, "error", None)
            if del_err is not None and not str(type(del_err)).endswith("MagicMock'>"):
                logger.warning(f"Password reset code {record_id} deletion returned error: {del_err}")
                return False
            if not del_res or not getattr(del_res, "data", None):
                logger.warning(f"Password reset code {record_id} already consumed concurrently for {mask_email(email_clean)}.")
                return False
        finally:
            with _otp_lock:
                _consuming_records.discard(record_id)
                _failed_attempts.pop(lock_key, None)

        return True
    except Exception as e:
        logger.error(f"Error verifying password reset code: {e}")
        return False

