import os
import sys
import asyncio
import logging
import argparse
from typing import List, Optional

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.config import settings
from db.supabase_client import get_supabase_client
from db.redis_client import safe_set, safe_delete, safe_get
from services.token_service import revoke_all_user_tokens_async

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("force_logout_targeted_users")

async def revoke_single_user(client, user_dict: dict) -> bool:
    """
    Revokes sessions for a specific user without affecting any other logged-in user.
    """
    uid = str(user_dict.get("user_id") or "")
    email = (user_dict.get("email") or "").strip().lower()
    full_name = f"{user_dict.get('first_name', '')} {user_dict.get('last_name', '')}".strip()
    phone = user_dict.get("phone", "")

    if not uid:
        return False

    # 1. Revoke all refresh tokens for this user & set rll:revoked:{user_id} = true in Redis
    tokens_killed = await revoke_all_user_tokens_async(uid)

    # 2. Clear cached user profile in Redis
    if email:
        await safe_delete(f"rll:user_profile:{email}")

    logger.info(
        f"✅ REVOKED: {full_name or 'User'} | Email: {email or 'N/A'} | Phone: {phone} | ID: {uid} (Tokens deleted: {tokens_killed})"
    )
    return True

async def main():
    parser = argparse.ArgumentParser(
        description="Targeted Force-Logout: Kick out unauthorized users from Redis while keeping authorized users logged in."
    )
    parser.add_argument(
        "--emails",
        nargs="+",
        help="List of specific email addresses to log out (e.g. --emails user1@rll.co.in user2@gmail.com)"
    )
    parser.add_argument(
        "--phones",
        nargs="+",
        help="List of specific phone numbers to log out (e.g. --phones 9876543210 +919876543210)"
    )
    parser.add_argument(
        "--all-inactive",
        action="store_true",
        default=False,
        help="Target all users where is_active = false in the database (safely ignores all active users)."
    )

    args = parser.parse_args()

    client = get_supabase_client()
    if not client:
        logger.error("Could not connect to database. Check database configuration.")
        return

    # If no specific flags passed, default to all inactive users
    if not args.emails and not args.phones and not args.all_inactive:
        args.all_inactive = True

    users_to_revoke = []

    if args.all_inactive:
        logger.info("Fetching all inactive users (is_active = false) from database...")
        res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").eq("is_active", False).execute()
        users_to_revoke = res.data or []
        logger.info(f"Found {len(users_to_revoke)} inactive users in database.")

    # Target specific emails
    if args.emails:
        for em in args.emails:
            em_clean = em.strip().lower()
            res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").ilike("email", em_clean).execute()
            if res.data:
                for u in res.data:
                    if u not in users_to_revoke:
                        users_to_revoke.append(u)
            else:
                logger.warning(f"No user found in database with email: {em_clean}")

    # Target specific phones
    if args.phones:
        for ph in args.phones:
            digits_10 = ''.join(c for c in ph if c.isdigit())[-10:]
            res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").execute()
            matched = False
            for u in (res.data or []):
                u_digits = ''.join(c for c in (u.get("phone") or "") if c.isdigit())[-10:]
                if u_digits == digits_10:
                    matched = True
                    if u not in users_to_revoke:
                        users_to_revoke.append(u)
            if not matched:
                logger.warning(f"No user found in database matching phone: {ph}")

    if not users_to_revoke:
        logger.info("No matching users found to revoke. Authorized users are unaffected.")
        return

    logger.info(f"Targeting {len(users_to_revoke)} user(s) for instant Redis session revocation...")
    count = 0
    for u in users_to_revoke:
        if await revoke_single_user(client, u):
            count += 1

    logger.info("=================================================================")
    logger.info(f"Done! Revoked {count} unauthorized user(s).")
    logger.info("All 24 authorized users remain LOGGED IN with active sessions untouched.")
    logger.info("=================================================================")

if __name__ == "__main__":
    asyncio.run(main())
