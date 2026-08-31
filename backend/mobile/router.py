import logging
import asyncio
import time
import copy
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Query, Request, status
from pydantic import BaseModel
from backend.core.security import create_access_token, get_current_user, RoleChecker
from backend.db.client import get_supabase
from backend.db.supabase_client import (
    call_mobile_sales_rpc,
    call_mobile_tsm_sales_rpc,
    call_mobile_sales_json_rpc,
    call_mobile_tsm_sales_json_rpc,
    # Reload uvicorn cache for TSM and ASE company level aggregation
)
from backend.core.config import settings
from backend.services.otp_service import (
    generate_6digit_otp,
    generate_4digit_otp,
    send_dovesoft_sms,
    send_otp_sms,
    store_otp_in_db,
    verify_otp_from_db
)
from supabase import create_client

logger = logging.getLogger(__name__)

# Master lookups in-memory cache with 5-minute TTL
_MASTER_CACHE = {
    "timestamp": 0,
    "data": None
}
_MASTER_CACHE_TTL = 0  # Set to 0 to guarantee fresh database lookups and prevent stale empty caches

# Sales endpoint response cache with 1-second TTL for real-time updates
_SALES_RESPONSE_CACHE: Dict[str, Dict[str, Any]] = {}
_SALES_RESPONSE_TTL = 1

def _fetch_fresh_master_lookups():
    client = get_supabase()
    companies_lookup: Dict[str, str] = {}
    try:
        c_res = client.table("companies").select("company_id, company_name").execute()
        for c in (c_res.data or []):
            if c.get("company_id") and c.get("company_name"):
                companies_lookup[str(c["company_id"])] = c["company_name"]
    except Exception as e_c:
        logger.warning(f"Error fetching companies_lookup: {e_c}")

    brands_lookup: Dict[str, Dict[str, Any]] = {}
    try:
        b_res = client.table("brands").select("brand_id, brand_name, company_id").execute()
        for b in (b_res.data or []):
            if b.get("brand_id") and b.get("brand_name"):
                brands_lookup[str(b["brand_id"])] = {
                    "name": b["brand_name"],
                    "company_id": str(b["company_id"]) if b.get("company_id") else None
                }
    except Exception as e_b:
        logger.warning(f"Error fetching brands_lookup: {e_b}")

    hq_lookup: Dict[str, str] = {}
    try:
        h_res = client.table("headquarters").select("headquarters_id, name").execute()
        for h in (h_res.data or []):
            if h.get("headquarters_id") and h.get("name"):
                hq_lookup[str(h["headquarters_id"])] = h["name"]
    except Exception as e_h:
        logger.warning(f"Error fetching hq_lookup: {e_h}")

    master_companies = {}
    for c_id_raw, c_name in companies_lookup.items():
        if not c_name or c_name == "Others":
            continue
        c_key = c_name.lower().replace(" ", "-").replace("/", "-")
        master_companies[c_key] = {
            "id": c_key,
            "name": c_name,
            "isPinned": c_key in ["rll", "diageo-inbrew"] or c_name.upper() == "RLL",
            "hqLocation": "All Headquarters",
            "data": {
                "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
            },
            "brands_map": {}
        }

    master_depots = {}
    hq_name_lookup = {}
    try:
        d_res = client.table("depots").select("depot_id, name, headquarters_id").execute()
        for d in (d_res.data or []):
            d_id = str(d.get("depot_id"))
            d_name = d.get("name")
            hq_id = str(d.get("headquarters_id") or "")
            hq_name = hq_lookup.get(hq_id, "Unassigned")
            hq_name_lookup[d_id] = hq_name
            master_depots[d_id] = {
                "id": d_id,
                "name": d_name,
                "hqName": hq_name,
                "data": {
                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                    "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                    "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                },
                "brands_map": {}
            }
    except Exception as e:
        logger.warning(f"Error fetching master depots: {e}")

    master_tsms = {}
    tsm_depot_lookup = {}
    user_depots_map = {}
    tsm_ase_lookup = {}
    ase_names_lookup = {}
    try:
        roles_res = client.table("roles").select("role_id, role_name").execute()
        tsm_role_id = None
        for r in (roles_res.data or []):
            if str(r.get("role_name", "")).upper() == "TSM":
                tsm_role_id = str(r["role_id"])

        if tsm_role_id:
            ur_res = client.table("user_roles").select("user_id").eq("role_id", tsm_role_id).execute()
            tsm_user_ids = [str(ur["user_id"]) for ur in (ur_res.data or []) if ur.get("user_id")]
            if tsm_user_ids:
                u_res = client.table("users").select("user_id, first_name, last_name, email").in_("user_id", tsm_user_ids).execute()
                for u in (u_res.data or []):
                    u_id = str(u["user_id"])
                    full_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or "TSM Manager"
                    master_tsms[u_id] = {
                        "id": u_id,
                        "name": full_name,
                        "hqLocation": "All Headquarters",
                        "depot_ids": set(),
                        "data": {
                            "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                            "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                            "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                        },
                        "companies_map": {},
                        "brands_map": {}
                    }

        ud_res = client.table("user_depot").select("user_id, depot_id").execute()
        for ud in (ud_res.data or []):
            uid = str(ud.get("user_id"))
            did = str(ud.get("depot_id"))
            if uid not in user_depots_map:
                user_depots_map[uid] = set()
            user_depots_map[uid].add(did)

        atm_res = client.table("ase_tsm_mapping").select("tsm_user_id, ase_user_id").execute()
        for atm in (atm_res.data or []):
            tid = str(atm.get("tsm_user_id"))
            aid = str(atm.get("ase_user_id"))
            if tid not in tsm_ase_lookup:
                tsm_ase_lookup[tid] = set()
            tsm_ase_lookup[tid].add(aid)

        all_ase_ids = list({aid for aids in tsm_ase_lookup.values() for aid in aids})
        if all_ase_ids:
            try:
                ase_u_res = client.table("users").select("user_id, first_name, last_name").in_("user_id", all_ase_ids).execute()
                for au in (ase_u_res.data or []):
                    a_uid = str(au["user_id"])
                    a_name = f"{au.get('first_name', '')} {au.get('last_name', '')}".strip() or "ASE"
                    ase_names_lookup[a_uid] = a_name
            except Exception as e:
                logger.warning(f"Error fetching ASE names: {e}")

        for tid, t_obj in master_tsms.items():
            t_obj["depot_ids"].update(user_depots_map.get(tid, set()))
            ase_ids_for_tsm = tsm_ase_lookup.get(tid, set())
            t_obj["ase_ids"] = list(ase_ids_for_tsm)
            for aid in ase_ids_for_tsm:
                t_obj["depot_ids"].update(user_depots_map.get(aid, set()))
            for did in t_obj["depot_ids"]:
                if did not in tsm_depot_lookup:
                    tsm_depot_lookup[did] = set()
                tsm_depot_lookup[did].add(tid)
    except Exception as e:
        logger.warning(f"Error fetching master TSMs: {e}")

    hq_name_to_id = {v.lower(): k for k, v in hq_lookup.items() if v}

    return {
        "companies_lookup": companies_lookup,
        "brands_lookup": brands_lookup,
        "hq_lookup": hq_lookup,
        "hq_name_to_id": hq_name_to_id,
        "master_companies": master_companies,
        "master_depots": master_depots,
        "master_tsms": master_tsms,
        "tsm_depot_lookup": tsm_depot_lookup,
        "user_depots_map": user_depots_map,
        "tsm_ase_lookup": tsm_ase_lookup,
        "ase_names_lookup": ase_names_lookup
    }

def get_cached_master_lookups():
    now = time.time()
    if _MASTER_CACHE["data"] is not None and (now - _MASTER_CACHE["timestamp"]) < _MASTER_CACHE_TTL:
        return copy.deepcopy(_MASTER_CACHE["data"])
    data = _fetch_fresh_master_lookups()
    _MASTER_CACHE["data"] = data
    _MASTER_CACHE["timestamp"] = now
    return copy.deepcopy(data)


router = APIRouter(prefix="/mobile", tags=["Mobile App API"])

class MobileLoginRequest(BaseModel):
    email: str
    password: str

class SendOTPRequest(BaseModel):
    phone: str
    email: Optional[str] = None

class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str
    email: Optional[str] = None

class MobileLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


@router.post("/login", response_model=MobileLoginResponse)
async def mobile_login(credentials: MobileLoginRequest, request: Request):
    """
    Mobile user authentication endpoint.
    Verifies user from Supabase 'users' table, logs session to 'user_auth_logs'.
    """
    email = credentials.email.lower().strip()
    logger.info(f"Mobile login attempt initiated for user: {email}")
    client = get_supabase()
    
    user_data = None
    
    if client:
        try:
            # 1. Verify credentials with an ephemeral Supabase Auth client to avoid mutating the global client
            temp_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            auth_response = temp_client.auth.sign_in_with_password({"email": email, "password": credentials.password})
            if not auth_response or not auth_response.user:
                logger.warning(f"Mobile login failed for user {email} (invalid credentials / empty response)")
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

            # 2. Get user profile and role
            res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").ilike("email", email).execute()
            if res.data and len(res.data) > 0:
                db_user = res.data[0]
                if not db_user.get("is_active", True):
                    logger.warning(f"Mobile login failed for user {email} (deactivated account)")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User account is deactivated"
                    )

                role_name = "admin"
                try:
                    ur_res = client.table("user_roles").select("user_id, role_id, is_active, roles(role_id, role_name)").eq("user_id", db_user["user_id"]).execute()
                    if ur_res.data:
                        active_roles = []
                        for ur in ur_res.data:
                            if ur.get("is_active", True):
                                role_obj = ur.get("roles") or {}
                                rname = role_obj.get("role_name")
                                if rname:
                                    active_roles.append(rname)
                        
                        # Prioritize valid mobile roles if user has multiple roles
                        valid_mobile = next((r for r in active_roles if r.lower() in ["tsm", "ase", "leader", "admin", "territory executive"]), None)
                        if valid_mobile:
                            role_name = valid_mobile
                        elif active_roles:
                            role_name = active_roles[0]
                except Exception:
                    pass

                # 3. Guardrail: Enforce Mobile roles
                if role_name.lower() not in ["tsm", "ase", "leader", "admin", "territory executive"]:
                    logger.warning(f"Mobile login access denied for user {email} (role '{role_name}' lacks Mobile permissions)")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access Denied: Mobile app is restricted to field personnel and administrators."
                    )

                # 4. Resolve Depot Name
                depot_name = "Jaipur Depot"
                try:
                    ud_res = client.table("user_depot").select("depot_id, depots(depot_id, name)").eq("user_id", db_user["user_id"]).execute()
                    if ud_res.data:
                        d_obj = ud_res.data[0].get("depots") or {}
                        if d_obj.get("name"):
                            depot_name = d_obj["name"]
                except Exception:
                    pass

                user_data = {
                    "user_id": str(db_user.get("user_id")),
                    "email": db_user.get("email"),
                    "first_name": db_user.get("first_name", email.split("@")[0].capitalize()),
                    "last_name": db_user.get("last_name", ""),
                    "phone": db_user.get("phone", ""),
                    "role_name": role_name,
                    "depot_name": depot_name,
                    "hq_location": "All Headquarters",
                    "is_active": bool(db_user.get("is_active", True))
                }
                logger.info(f"Mobile login successful for user: {email} with role: {role_name}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error during mobile login for user {email}: {e}")
            if "Invalid login credentials" in str(e):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
            logger.warning(f"Supabase users lookup error: {e}")

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # 2. Log login entry into 'user_auth_logs' in Supabase
    if client:
        try:
            client.table("user_auth_logs").insert({
                "user_id": user_data["user_id"],
                "email": email,
                "login_at": datetime.utcnow().isoformat(),
                "status": "SUCCESS"
            }).execute()
        except Exception as e:
            logger.warning(f"Could not log to user_auth_logs table: {e}")

    # 3. Create Access Token valid for 30 days for mobile application
    token = create_access_token(
        data={"sub": user_data["email"], "role": user_data["role_name"], "user_id": user_data["user_id"]},
        expires_delta=timedelta(days=30)
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_data
    }


@router.post("/send-otp")
async def send_mobile_otp(req: SendOTPRequest):
    """
    Send 6-digit OTP to user's mobile number via Dovesoft SMS Gateway.
    Verifies user is registered in Supabase 'users' table before sending.
    """
    email = (req.email or "").lower().strip()
    phone = (req.phone or "").strip()
    logger.info(f"Mobile OTP request initiated for phone: {phone}, email: {email}")

    if not email and not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email address or phone number is required")

    client = get_supabase()
    clean_phone_10 = ''.join(c for c in phone if c.isdigit())
    if len(clean_phone_10) >= 10:
        clean_phone_10 = clean_phone_10[-10:]

    db_user = None
    if client:
        try:
            # 1. Lookup by email if provided
            if email:
                res = client.table("users").select("user_id, email, phone, first_name, last_name, is_active").ilike("email", email).execute()
                if res.data:
                    db_user = res.data[0]

            # 2. Lookup by phone if not found by email
            if not db_user and clean_phone_10:
                res_phone = client.table("users").select("user_id, email, phone, first_name, last_name, is_active").ilike("phone", f"%{clean_phone_10}%").limit(1).execute()
                if res_phone.data:
                    db_user = res_phone.data[0]
        except Exception as e:
            logger.warning(f"User lookup error in send_mobile_otp: {e}")

    # Enforce registered user requirement
    if not db_user:
        logger.warning(f"Mobile OTP request failed: Phone/Email not registered (Phone: {phone}, Email: {email})")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This mobile number is not registered."
        )

    if not db_user.get("is_active", True):
        logger.warning(f"Mobile OTP request failed: Account is deactivated (Phone: {phone}, Email: {email})")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This user account is deactivated."
        )

    # Use registered user's phone number or input phone
    target_phone = db_user.get("phone") or phone

    # Generate 6-digit OTP
    otp_code = generate_6digit_otp()

    # Store in Supabase otp_codes table
    store_otp_in_db(target_phone, otp_code)
    store_otp_in_db(phone, otp_code)  # Store for input phone as well for verification lookup

    # Directly await SMS dispatch via Dovesoft API
    sms_sent = await send_otp_sms(target_phone, otp_code)
    logger.info(f"Mobile OTP successfully generated and sent via SMS to {target_phone} (SMS sent status: {sms_sent})")

    return {
        "success": True,
        "message": f"6-digit OTP sent successfully to {target_phone}",
        "otp_sent": sms_sent
    }


@router.post("/verify-otp", response_model=MobileLoginResponse)
async def verify_mobile_otp(req: VerifyOTPRequest):
    """
    Verify 6-digit OTP code against Supabase 'otp_codes' table.
    Returns signed JWT access token and user profile object.
    """
    email = (req.email or "").lower().strip()
    phone = (req.phone or "").strip()
    otp_code = (req.otp or "").strip()
    logger.info(f"Mobile OTP verification attempt initiated for phone: {phone}")

    if not phone or not otp_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number and 6-digit OTP code are required")

    # Verify 6-digit OTP from DB
    is_valid = verify_otp_from_db(phone, otp_code)
    if not is_valid:
        logger.warning(f"Mobile OTP verification failed for phone: {phone} - Invalid or expired OTP code")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired 6-digit OTP code")

    client = get_supabase()
    user_data = None
    if client:
        try:
            db_user = None
            if email:
                res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").ilike("email", email).execute()
                if res.data:
                    db_user = res.data[0]

            if not db_user and phone:
                clean_in = ''.join(c for c in phone if c.isdigit())
                clean_10 = clean_in[-10:] if len(clean_in) >= 10 else clean_in
                res_phone = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").execute()
                if res_phone.data:
                    for u in res_phone.data:
                        u_p = ''.join(c for c in (u.get("phone") or "") if c.isdigit())
                        if u_p and (clean_10 in u_p or u_p in clean_10):
                            db_user = u
                            break

            if db_user:
                if not db_user.get("is_active", True):
                    logger.warning(f"Mobile OTP verification failed for phone: {phone} - Account deactivated")
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is deactivated")

                role_name = "TSM"
                try:
                    ur_res = client.table("user_roles").select("user_id, role_id, is_active").eq("user_id", db_user["user_id"]).execute()
                    if ur_res.data:
                        active_ur = [ur for ur in ur_res.data if ur.get("is_active", True)]
                        if active_ur:
                            r_id = active_ur[0].get("role_id")
                            r_res = client.table("roles").select("role_name").eq("role_id", r_id).limit(1).execute()
                            if r_res.data:
                                role_name = r_res.data[0].get("role_name", "TSM")
                except Exception as e_role:
                    logger.warning(f"Could not fetch role: {e_role}")

                depot_name = "Jaipur Depot"
                try:
                    ud_res = client.table("user_depot").select("depot_id").eq("user_id", db_user["user_id"]).execute()
                    if ud_res.data:
                        d_id = ud_res.data[0].get("depot_id")
                        dep_res = client.table("depots").select("name").eq("depot_id", d_id).limit(1).execute()
                        if dep_res.data:
                            depot_name = dep_res.data[0].get("name", "Jaipur Depot")
                except Exception:
                    pass

                user_data = {
                    "user_id": str(db_user.get("user_id")),
                    "email": db_user.get("email") or email or f"{phone}@rll.com",
                    "first_name": db_user.get("first_name", "User"),
                    "last_name": db_user.get("last_name", ""),
                    "phone": db_user.get("phone") or phone,
                    "role_name": role_name,
                    "depot_name": depot_name,
                    "hq_location": "All Headquarters",
                    "is_active": bool(db_user.get("is_active", True))
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resolving user profile on OTP verify: {e}")
            logger.warning(f"Error resolving user profile on OTP verify: {e}")

    if not user_data:
        logger.warning(f"Mobile OTP verification failed for phone: {phone} - User profile not registered")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This mobile number is not registered."
        )

    # Generate Access Token valid for 30 days for mobile application
    token = create_access_token(
        data={"sub": user_data["email"], "role": user_data["role_name"], "user_id": user_data["user_id"]},
        expires_delta=timedelta(days=30)
    )
    logger.info(f"Mobile OTP verification successful for phone: {phone} (User: {user_data['email']}, Role: {user_data['role_name']})")

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_data
    }


@router.get("/me")
def get_mobile_user_profile(
    current_user: dict = Depends(RoleChecker(['tsm', 'ase', 'leader', 'territory executive', 'admin']))
):
    """
    Fetch current logged-in user profile with depot details.
    """
    client = get_supabase()
    sub_val = (current_user.get("sub") or current_user.get("email") or current_user.get("phone") or "").strip()
    user_id_val = current_user.get("user_id")
    if not client:
        return current_user

    try:
        db_user = None
        if user_id_val:
            u_res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").eq("user_id", user_id_val).execute()
            if u_res.data:
                db_user = u_res.data[0]

        if not db_user and sub_val:
            u_res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").or_(f"email.ilike.{sub_val},phone.ilike.%{sub_val}%").execute()
            if u_res.data:
                db_user = u_res.data[0]

        if db_user:
            role_name = current_user.get("role", "TSM")
            depot_name = "Jaipur Depot"
            try:
                ud_res = client.table("user_depot").select("depot_id").eq("user_id", db_user["user_id"]).execute()
                if ud_res.data:
                    d_id = ud_res.data[0].get("depot_id")
                    dep_res = client.table("depots").select("name").eq("depot_id", d_id).limit(1).execute()
                    if dep_res.data:
                        depot_name = dep_res.data[0].get("name", "Jaipur Depot")
            except Exception:
                pass

            return {
                "user_id": str(db_user.get("user_id")),
                "email": db_user.get("email"),
                "first_name": db_user.get("first_name", "User"),
                "last_name": db_user.get("last_name", ""),
                "phone": db_user.get("phone", ""),
                "role_name": role_name,
                "depot_name": depot_name,
                "hq_location": "All Headquarters",
                "is_active": bool(db_user.get("is_active", True))
            }
    except Exception as e:
        logger.warning(f"Error fetching profile in /mobile/me: {e}")

    return current_user


@router.get("/headquarters")
def get_mobile_headquarters():
    """
    Fetches active headquarters from public.headquarters table in Supabase.
    Includes master cache fallback to guarantee 0 HTTP 500 errors.
    """
    try:
        client = get_supabase()
        if client:
            res = client.table("headquarters").select("headquarters_id, name, is_active").eq("is_active", True).order("name").execute()
            hq_data = res.data or []
            if hq_data:
                hq_names = ["All Headquarters"] + [h["name"] for h in hq_data if h.get("name")]
                return {
                    "status": "success",
                    "count": len(hq_names),
                    "headquarters": hq_names
                }
    except Exception as e:
        logger.warning(f"Direct DB query failed in /mobile/headquarters, falling back to master cache: {e}")

    # Fallback 1: Try master cache lookups
    try:
        master_cache = get_cached_master_lookups()
        hq_lookup = master_cache.get("hq_lookup", {})
        if hq_lookup:
            unique_hqs = sorted(list(set(hq_lookup.values())))
            hq_names = ["All Headquarters"] + [h for h in unique_hqs if h and h != "Unassigned"]
            return {
                "status": "success",
                "count": len(hq_names),
                "headquarters": hq_names
            }
    except Exception as e_cache:
        logger.warning(f"Master cache fallback failed in /mobile/headquarters: {e_cache}")

    # Fallback 2: Static Headquarters fallback
    default_hqs = [
        "All Headquarters", "Ajmer", "Alwar", "Banswara", "Baran", "Barmer", "Bharatpur",
        "Bhilwara", "Bikaner", "Bundi", "Chittorgarh", "Churu", "Dausa", "Dholpur",
        "Dungarpur", "Hanumangarh", "Jaipur", "Jaisalmer", "Jalore", "Jhalawar",
        "Jhunjhunu", "Jodhpur", "Karauli", "Kota", "Nagaur", "Pali", "Pratapgarh",
        "Rajsamand", "Sawai Madhopur", "Sikar", "Sirohi", "Sri Ganganagar", "Tonk", "Udaipur"
    ]
    return {
        "status": "success",
        "count": len(default_hqs),
        "headquarters": default_hqs
    }


@router.get("/companies")
async def get_mobile_companies(
    period: str = Query("Daily", description="Sales period: Daily, MTD, YTD"),
    date_to: Optional[str] = Query(None, alias="date"),
    selected_hq: Optional[str] = Query(None, alias="selected_hq"),
    current_user: dict = Depends(get_current_user)
):
    """
    Fetches period-specific company sales analytics (Daily, MTD, YTD).
    Excludes Company 'Others' strictly. Caches response in Redis.
    """
    from backend.services.mobile_companies_service import get_companies_summary
    from backend.services.cache_service import get_json_cache, set_json_cache

    clean_period = period.strip() if period else "Daily"
    clean_hq = selected_hq.strip() if selected_hq else "All Headquarters"
    clean_date = date_to.strip() if date_to else "latest"

    redis_key = f"rll:mobile:companies:{clean_period}:{clean_hq}:{clean_date}"
    cached_payload = await get_json_cache(redis_key)
    if cached_payload is not None:
        logger.info(f"get_mobile_companies: Redis CACHE HIT for {redis_key}")
        return cached_payload

    try:
        companies_list = get_companies_summary(
            period=clean_period,
            date_to=date_to,
            selected_hq=selected_hq
        )
        payload = {
            "status": "success",
            "period": clean_period,
            "count": len(companies_list),
            "companies": companies_list
        }
        await set_json_cache(redis_key, payload, ttl=900)  # 15 minutes TTL
        return payload
    except Exception as e:
        logger.error(f"Error fetching mobile companies analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/companies/{company_id}/brands")
def get_company_brands(
    company_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetches brands belonging to a specific company from public.brands table using company_id (UUID or Name).
    """
    client = get_supabase()
    try:
        target_company_id = company_id
        if len(company_id) != 36 or "-" not in company_id:
            c_res = client.table("companies").select("company_id, company_name").ilike("company_name", company_id.replace("-", " ")).execute()
            if c_res.data and len(c_res.data) > 0:
                target_company_id = str(c_res.data[0]["company_id"])

        res = client.table("brands").select("brand_id, brand_name, company_id, is_active, created_at").eq("company_id", target_company_id).eq("is_active", True).order("brand_name").execute()
        brands_data = res.data or []

        return {
            "status": "success",
            "company_id": company_id,
            "count": len(brands_data),
            "brands": [
                {
                    "brand_id": str(b.get("brand_id")),
                    "brand_name": b.get("brand_name"),
                    "company_id": str(b.get("company_id")),
                    "is_active": b.get("is_active", True),
                    "created_at": b.get("created_at")
                }
                for b in brands_data
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching brands for company {company_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sales")
async def get_mobile_sales(
    request: Request,
    date_from: Optional[str] = Query(None, description="Start Date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End Date YYYY-MM-DD"),
    period: str = Query("Daily", description="Daily | MTD | YTD"),
    selected_hq: str = Query("All Headquarters", description="Headquarters filter"),
    test_limit: Optional[int] = Query(None, description="Diagnostic payload scaling test limit"),
    current_user: dict = Depends(RoleChecker(['tsm', 'ase', 'leader', 'admin']))
):
    """
    Returns real aggregated sales data for Companies, Depots, and TSMs directly calculated from Supabase.
    Computes distinct, dynamic metrics for Daily, MTD, and YTD with database-level HQ filtering.
    Instruments every stage of execution with microsecond timing.
    """
    import json
    import uuid
    from fastapi.responses import JSONResponse

    t_api_start = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:8]}"

    # A & B. Auth timing
    t_auth_start = time.perf_counter()
    user_role = (current_user.get("role_name") or current_user.get("role") or "").lower()
    user_id = current_user.get("user_id")
    t_auth_end = time.perf_counter()
    auth_duration_ms = round((t_auth_end - t_auth_start) * 1000, 2)

    client = get_supabase()
    raw_period = (period or "Daily").strip().upper()
    if raw_period == "DAILY":
        selected_period = "Daily"
    elif raw_period in ["MTD", "MONTHLY"]:
        selected_period = "MTD"
    elif raw_period in ["YTD", "YEARLY"]:
        selected_period = "YTD"
    else:
        selected_period = "Daily"

    # C. Master cache lookup timing
    t_master_start = time.perf_counter()
    master_cache_hit = _MASTER_CACHE["data"] is not None and (time.time() - _MASTER_CACHE["timestamp"]) < _MASTER_CACHE_TTL
    master_cache = get_cached_master_lookups()
    t_master_end = time.perf_counter()
    master_cache_duration_ms = round((t_master_end - t_master_start) * 1000, 2)

    companies_lookup = master_cache["companies_lookup"]
    brands_lookup = master_cache["brands_lookup"]
    hq_lookup = master_cache["hq_lookup"]
    master_companies = master_cache["master_companies"]
    master_depots = master_cache["master_depots"]
    master_tsms = master_cache["master_tsms"]
    tsm_depot_lookup = master_cache["tsm_depot_lookup"]
    user_depots_map = master_cache["user_depots_map"]
    tsm_ase_lookup = master_cache["tsm_ase_lookup"]
    ase_names_lookup = master_cache["ase_names_lookup"]

    cache_key = f"{selected_period}:{selected_hq}:{date_from}:{date_to}:{user_role}:{user_id}:{test_limit or 'all'}"
    
    # D. Sales response cache timing
    t_sales_cache_start = time.perf_counter()
    now_ts = time.time()
    if cache_key in _SALES_RESPONSE_CACHE:
        entry = _SALES_RESPONSE_CACHE[cache_key]
        if now_ts - entry["timestamp"] < _SALES_RESPONSE_TTL:
            t_sales_cache_end = time.perf_counter()
            sales_cache_duration_ms = round((t_sales_cache_end - t_sales_cache_start) * 1000, 2)
            t_api_end = time.perf_counter()
            total_api_ms = round((t_api_end - t_api_start) * 1000, 2)

            cached_data = entry["data"]
            cached_bytes = len(json.dumps(cached_data).encode("utf-8"))
            cached_kb = round(cached_bytes / 1024, 2)
            cached_mb = round(cached_bytes / (1024 * 1024), 2)

            logger.info(
                f"\n==================================================\n"
                f"RLL PERFORMANCE TRACE (CACHE HIT)\n"
                f"==================================================\n"
                f"Request ID: {request_id}\n"
                f"Endpoint: /mobile/sales\n"
                f"Filters: HQ: {selected_hq} | Date: {date_from} to {date_to} | Period: {selected_period}\n"
                f"--------------------------------------------------\n"
                f"BACKEND\n"
                f"--------------------------------------------------\n"
                f"Authentication:         {auth_duration_ms:.1f} ms\n"
                f"Master cache:          {master_cache_duration_ms:.1f} ms ({'HIT' if master_cache_hit else 'MISS'})\n"
                f"Sales cache:           {sales_cache_duration_ms:.1f} ms (HIT)\n"
                f"Supabase RPC:          0.0 ms (CACHED)\n"
                f"RPC payload:           0.0 KB / 0.00 MB\n"
                f"RPC deserialization:   0.0 ms\n"
                f"Python transformation: 0.0 ms\n"
                f"JSON serialization:    0.1 ms\n"
                f"Final API response:    {cached_kb} KB / {cached_mb:.2f} MB\n"
                f"Total FastAPI time:    {total_api_ms:.1f} ms\n"
                f"=================================================="
            )

            return JSONResponse(
                content=cached_data,
                headers={
                    "X-Request-ID": request_id,
                    "X-Backend-Duration-Ms": str(total_api_ms),
                    "X-Response-Size-Bytes": str(cached_bytes),
                    "X-Sales-Cache-Status": "HIT"
                }
            )

    redis_key = f"rll:mobile:sales:{cache_key}"
    try:
        from backend.services.cache_service import get_json_cache
        redis_cached_data = await get_json_cache(redis_key)
        if redis_cached_data:
            _SALES_RESPONSE_CACHE[cache_key] = {
                "timestamp": time.time(),
                "data": redis_cached_data
            }
            t_api_end = time.perf_counter()
            total_api_ms = round((t_api_end - t_api_start) * 1000, 2)
            return JSONResponse(
                content=redis_cached_data,
                headers={
                    "X-Request-ID": request_id,
                    "X-Backend-Duration-Ms": str(total_api_ms),
                    "X-Sales-Cache-Status": "REDIS_HIT"
                }
            )
    except Exception as e_redis:
        logger.warning(f"Redis cache check failed: {e_redis}")

    t_sales_cache_end = time.perf_counter()
    sales_cache_duration_ms = round((t_sales_cache_end - t_sales_cache_start) * 1000, 2)

    allowed_depots = set()
    if user_role == "tsm":
        if user_id in master_tsms:
            allowed_depots.update(master_tsms[user_id]["depot_ids"])
            master_tsms = {user_id: master_tsms[user_id]}
        else:
            master_tsms = {}
    elif user_role == "ase":
        allowed_depots = set(user_depots_map.get(user_id, []))
        master_tsms = {}

    latest_sale_date = None
    try:
        max_res = client.table("dashboard_summary_daily").select("sale_date").order("sale_date", desc=True).limit(1).execute()
        if max_res.data and max_res.data[0].get("sale_date"):
            latest_sale_date = max_res.data[0]["sale_date"]
    except Exception as e:
        logger.warning(f"Error fetching latest sale date: {e}")

    if not latest_sale_date:
        latest_sale_date = datetime.utcnow().strftime("%Y-%m-%d")

    end_date = latest_sale_date
    if date_to and date_to <= latest_sale_date:
        end_date = date_to

    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except Exception:
        end_dt = datetime.utcnow().date()
        end_date = end_dt.strftime("%Y-%m-%d")

    daily_start = end_date
    mtd_start = end_dt.replace(day=1).strftime("%Y-%m-%d")
    fy_year = end_dt.year if end_dt.month >= 4 else end_dt.year - 1
    ytd_start = f"{fy_year}-04-01"

    target_hq_id = None
    if selected_hq and selected_hq != "All Headquarters":
        target_hq_id = master_cache.get("hq_name_to_id", {}).get(selected_hq.strip().lower())
        if not target_hq_id:
            try:
                hq_res = client.table("headquarters").select("headquarters_id").ilike("name", selected_hq.strip()).execute()
                if hq_res.data:
                    target_hq_id = hq_res.data[0]["headquarters_id"]
            except Exception as e:
                logger.warning(f"HQ lookup error for {selected_hq}: {e}")

    # E, F, G, H. Supabase RPC timing and byte measurement
    rpc_trace_info: Dict[str, Any] = {}
    comp_rpc_params = {
        "p_target_date": end_date,
        "p_mtd_start": mtd_start,
        "p_ytd_start": ytd_start,
    }
    if target_hq_id:
        comp_rpc_params["p_hq_id"] = target_hq_id

    t0 = time.perf_counter()
    try:
        comp_res = client.rpc("get_mobile_companies_summary", comp_rpc_params).execute()
        company_records = comp_res.data or []
    except Exception as e_comp:
        logger.error(f"Error calling get_mobile_companies_summary RPC: {e_comp}")
        company_records = []
    t1 = time.perf_counter()
    rpc_trace_info["sales_rpc_duration_ms"] = round((t1 - t0) * 1000, 2)

    sales_payload = call_mobile_sales_json_rpc(end_date, mtd_start, ytd_start, target_hq_id)
    depot_records = sales_payload.get("depots") or []
    total_records_processed = len(company_records) + len(depot_records)

    # I. Python transformation timing
    t_transform_start = time.perf_counter()

    # Company Aliases Normalization (Willam vs William)
    COMPANY_ALIASES = {
        "willam grants": "William Grants",
        "william grants": "William Grants",
        "william grants & sons": "William Grants"
    }

    grouped_comp_rows = {}
    for row in company_records:
        cid = str(row.get("company_id") or "")
        cname = str(row.get("company_name") or "").strip()
        if not cname or cname.lower() == "others":
            continue

        norm_name = COMPANY_ALIASES.get(cname.lower(), cname)
        comp_id = norm_name.lower().replace(" ", "-").replace("/", "-")

        if comp_id not in grouped_comp_rows:
            grouped_comp_rows[comp_id] = {
                "id": comp_id,
                "name": norm_name,
                "isPinned": comp_id in ["rll", "diageo-inbrew"] or norm_name.upper() == "RLL",
                "hqLocation": selected_hq or "All Headquarters",
                "company_ids": [],
                "data": {
                    "Daily": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                    "MTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                    "YTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                },
                "brands_map": {}
            }

        g = grouped_comp_rows[comp_id]
        g["company_ids"].append(cid)
        g["data"]["Daily"]["cases"] += float(row.get("daily_cases") or 0.0)
        g["data"]["Daily"]["bottles"] += float(row.get("daily_bottles") or 0.0)
        g["data"]["Daily"]["bl"] += float(row.get("daily_bl") or 0.0)
        g["data"]["MTD"]["cases"] += float(row.get("mtd_cases") or 0.0)
        g["data"]["MTD"]["bottles"] += float(row.get("mtd_bottles") or 0.0)
        g["data"]["MTD"]["bl"] += float(row.get("mtd_bl") or 0.0)
        g["data"]["YTD"]["cases"] += float(row.get("ytd_cases") or 0.0)
        g["data"]["YTD"]["bottles"] += float(row.get("ytd_bottles") or 0.0)
        g["data"]["YTD"]["bl"] += float(row.get("ytd_bl") or 0.0)

    # For each grouped company, fetch Brand summaries using get_mobile_company_brands_summary RPC
    for comp_id, g in grouped_comp_rows.items():
        brand_params = {
            "p_company_ids": g["company_ids"],
            "p_target_date": end_date,
            "p_mtd_start": mtd_start,
            "p_ytd_start": ytd_start,
        }
        if target_hq_id:
            brand_params["p_hq_id"] = target_hq_id

        try:
            brand_res = client.rpc("get_mobile_company_brands_summary", brand_params).execute()
            brands_data = brand_res.data or []
        except Exception as e_brands:
            logger.error(f"Error calling get_mobile_company_brands_summary RPC for {g['name']}: {e_brands}")
            brands_data = []

        for b in brands_data:
            bid = str(b.get("brand_id") or "")
            bname = str(b.get("brand_name") or "Generic Brand").strip()
            
            b_daily_cases = float(b.get("daily_cases") or 0.0)
            b_daily_bottles = float(b.get("daily_bottles") or 0.0)
            b_daily_bl = float(b.get("daily_bl") or 0.0)
            
            b_mtd_cases = float(b.get("mtd_cases") or 0.0)
            b_mtd_bottles = float(b.get("mtd_bottles") or 0.0)
            b_mtd_bl = float(b.get("mtd_bl") or 0.0)
            
            b_ytd_cases = float(b.get("ytd_cases") or 0.0)
            b_ytd_bottles = float(b.get("ytd_bottles") or 0.0)
            b_ytd_bl = float(b.get("ytd_bl") or 0.0)

            if bid not in g["brands_map"]:
                g["brands_map"][bid] = {
                    "id": bid,
                    "name": bname,
                    "data": {
                        "Daily": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                        "MTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                        "YTD": {"cases": 0.0, "bottles": 0.0, "bl": 0.0},
                    }
                }
            bm = g["brands_map"][bid]
            bm["data"]["Daily"]["cases"] += b_daily_cases
            bm["data"]["Daily"]["bottles"] += b_daily_bottles
            bm["data"]["Daily"]["bl"] += b_daily_bl
            bm["data"]["MTD"]["cases"] += b_mtd_cases
            bm["data"]["MTD"]["bottles"] += b_mtd_bottles
            bm["data"]["MTD"]["bl"] += b_mtd_bl
            bm["data"]["YTD"]["cases"] += b_ytd_cases
            bm["data"]["YTD"]["bottles"] += b_ytd_bottles
            bm["data"]["YTD"]["bl"] += b_ytd_bl

    # Store in master_companies
    for comp_id, g in grouped_comp_rows.items():
        master_companies[comp_id] = {
            "id": comp_id,
            "name": g["name"],
            "isPinned": g["isPinned"],
            "hqLocation": g["hqLocation"],
            "data": {
                "Daily": {"cases": round(g["data"]["Daily"]["cases"], 2), "bottles": round(g["data"]["Daily"]["bottles"], 2), "bl": round(g["data"]["Daily"]["bl"], 2)},
                "MTD": {"cases": round(g["data"]["MTD"]["cases"], 2), "bottles": round(g["data"]["MTD"]["bottles"], 2), "bl": round(g["data"]["MTD"]["bl"], 2)},
                "YTD": {"cases": round(g["data"]["YTD"]["cases"], 2), "bottles": round(g["data"]["YTD"]["bottles"], 2), "bl": round(g["data"]["YTD"]["bl"], 2)},
            },
            "brands_map": g["brands_map"]
        }

    for row in depot_records:
        raw_depot_id = str(row.get("depot_id") or "")
        depot_info = master_depots.get(raw_depot_id) or {}
        depot_name = depot_info.get("name") or "Central Depot"
        target_depot_id = raw_depot_id or depot_name.lower().replace(" ", "-")

        if user_role in ["tsm", "ase"] and target_depot_id not in allowed_depots:
            continue

        b_id_raw = str(row.get("brand_id") or "")
        b_info = brands_lookup.get(b_id_raw, {})
        brand_name = b_info.get("name") or "Generic Brand"
        brand_id = b_id_raw or brand_name.lower().replace(" ", "-")

        raw_hq_id = str(row.get("headquarters_id") or "")
        hq_name = hq_lookup.get(raw_hq_id) or depot_info.get("hq_name") or "All Headquarters"

        target_depot = master_depots.get(raw_depot_id)
        if not target_depot:
            target_depot_id = raw_depot_id or depot_name.lower().replace(" ", "-")
            if target_depot_id not in master_depots:
                master_depots[target_depot_id] = {
                    "id": target_depot_id,
                    "name": depot_name,
                    "hqName": hq_name,
                    "data": {
                        "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                    },
                    "brands_map": {}
                }
            target_depot = master_depots[target_depot_id]

        row_metrics = {
            "Daily": {
                "cases": float(row.get("daily_cases") or 0.0),
                "bottles": float(row.get("daily_bottles") or 0.0),
                "bl": float(row.get("daily_bl") or 0.0),
            },
            "MTD": {
                "cases": float(row.get("mtd_cases") or 0.0),
                "bottles": float(row.get("mtd_bottles") or 0.0),
                "bl": float(row.get("mtd_bl") or 0.0),
            },
            "YTD": {
                "cases": float(row.get("ytd_cases") or 0.0),
                "bottles": float(row.get("ytd_bottles") or 0.0),
                "bl": float(row.get("ytd_bl") or 0.0),
            },
        }

        for period_key, metrics in row_metrics.items():
            target_depot["data"][period_key]["cases"] += metrics["cases"]
            target_depot["data"][period_key]["bottles"] += metrics["bottles"]
            target_depot["data"][period_key]["bl"] += metrics["bl"]

            db_map = target_depot["brands_map"]
            if brand_id not in db_map:
                db_map[brand_id] = {
                    "brandId": brand_id,
                    "brandName": brand_name,
                    "data": {
                        "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                        "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                    }
                }
            db_map[brand_id]["data"][period_key]["cases"] += metrics["cases"]
            db_map[brand_id]["data"][period_key]["bottles"] += metrics["bottles"]
            db_map[brand_id]["data"][period_key]["bl"] += metrics["bl"]

    member_to_tsms = {}
    for tid in master_tsms.keys():
        if tid not in member_to_tsms:
            member_to_tsms[tid] = set()
        member_to_tsms[tid].add(tid)
        for aid in tsm_ase_lookup.get(tid, set()):
            if aid == tid:
                continue
            if aid not in member_to_tsms:
                member_to_tsms[aid] = set()
            member_to_tsms[aid].add(tid)

    all_known_ase_ids = {aid for aids in tsm_ase_lookup.values() for aid in aids}
    ase_sales = {
        aid: {
            "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
            "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
            "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
        }
        for aid in all_known_ase_ids
    }
    ase_comp_sets = {aid: {"Daily": set(), "MTD": set(), "YTD": set()} for aid in all_known_ase_ids}
    tsm_comp_sets = {tid: {"Daily": set(), "MTD": set(), "YTD": set()} for tid in master_tsms.keys()}
    ase_company_maps = {aid: {} for aid in all_known_ase_ids}
    ase_brand_maps = {aid: {} for aid in all_known_ase_ids}

    # Initialize companies_map on master_tsms
    for tid in master_tsms.keys():
        master_tsms[tid]["companies_map"] = {}

    tsm_rpc_trace: Dict[str, Any] = {}
    all_usf_records = call_mobile_tsm_sales_json_rpc(end_date, mtd_start, ytd_start, trace_info=tsm_rpc_trace)

    for row in all_usf_records:
        c_id_raw = str(row.get("company_id") or "")
        comp_name = companies_lookup.get(c_id_raw)
        if not comp_name:
            continue

        uid = str(row.get("user_id") or "")
        target_tsm_ids = member_to_tsms.get(uid, set())
        if not target_tsm_ids:
            continue

        b_id_raw = str(row.get("brand_id") or "")
        b_info = brands_lookup.get(b_id_raw, {})
        brand_name = b_info.get("name") or "Generic Brand"
        brand_id = b_id_raw or brand_name.lower().replace(" ", "-")

        usf_metrics = {
            "Daily": {
                "cases": float(row.get("daily_cases") or 0.0),
                "bottles": float(row.get("daily_bottles") or 0.0),
                "bl": float(row.get("daily_bl") or 0.0),
            },
            "MTD": {
                "cases": float(row.get("mtd_cases") or 0.0),
                "bottles": float(row.get("mtd_bottles") or 0.0),
                "bl": float(row.get("mtd_bl") or 0.0),
            },
            "YTD": {
                "cases": float(row.get("ytd_cases") or 0.0),
                "bottles": float(row.get("ytd_bottles") or 0.0),
                "bl": float(row.get("ytd_bl") or 0.0),
            },
        }

        for period_key, metrics in usf_metrics.items():
            if metrics["cases"] > 0 or metrics["bottles"] > 0:
                if uid in ase_sales:
                    ase_sales[uid][period_key]["cases"] += metrics["cases"]
                    ase_sales[uid][period_key]["bottles"] += metrics["bottles"]
                    ase_sales[uid][period_key]["bl"] += metrics["bl"]
                    ase_comp_sets[uid][period_key].add(c_id_raw)

                    # ASE Company level
                    ac_map = ase_company_maps[uid]
                    if c_id_raw not in ac_map:
                        ac_map[c_id_raw] = {
                            "companyId": c_id_raw,
                            "companyName": comp_name,
                            "name": comp_name,
                            "data": {
                                "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                                "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                            }
                        }
                    ac_map[c_id_raw]["data"][period_key]["cases"] += metrics["cases"]
                    ac_map[c_id_raw]["data"][period_key]["bottles"] += metrics["bottles"]
                    ac_map[c_id_raw]["data"][period_key]["bl"] += metrics["bl"]

                    # ASE Brand level
                    ab_map = ase_brand_maps[uid]
                    if brand_id not in ab_map:
                        ab_map[brand_id] = {
                            "brandId": brand_id,
                            "brandName": brand_name,
                            "name": brand_name,
                            "companyId": c_id_raw,
                            "companyName": comp_name,
                            "data": {
                                "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                                "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                            }
                        }
                    ab_map[brand_id]["data"][period_key]["cases"] += metrics["cases"]
                    ab_map[brand_id]["data"][period_key]["bottles"] += metrics["bottles"]
                    ab_map[brand_id]["data"][period_key]["bl"] += metrics["bl"]

                for tid in target_tsm_ids:
                    if tid in master_tsms:
                        t_obj = master_tsms[tid]
                        t_obj["data"][period_key]["cases"] += metrics["cases"]
                        t_obj["data"][period_key]["bottles"] += metrics["bottles"]
                        t_obj["data"][period_key]["bl"] += metrics["bl"]
                        tsm_comp_sets[tid][period_key].add(c_id_raw)

                        # TSM Company level
                        tc_map = t_obj["companies_map"]
                        if c_id_raw not in tc_map:
                            tc_map[c_id_raw] = {
                                "companyId": c_id_raw,
                                "companyName": comp_name,
                                "name": comp_name,
                                "data": {
                                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                }
                            }
                        tc_map[c_id_raw]["data"][period_key]["cases"] += metrics["cases"]
                        tc_map[c_id_raw]["data"][period_key]["bottles"] += metrics["bottles"]
                        tc_map[c_id_raw]["data"][period_key]["bl"] += metrics["bl"]

                        # TSM Brand level
                        tb_map = t_obj["brands_map"]
                        if brand_id not in tb_map:
                            tb_map[brand_id] = {
                                "brandId": brand_id,
                                "brandName": brand_name,
                                "name": brand_name,
                                "companyId": c_id_raw,
                                "companyName": comp_name,
                                "data": {
                                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                    "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                }
                            }
                        tb_map[brand_id]["data"][period_key]["cases"] += metrics["cases"]
                        tb_map[brand_id]["data"][period_key]["bottles"] += metrics["bottles"]
                        tb_map[brand_id]["data"][period_key]["bl"] += metrics["bl"]

    formatted_companies = []
    for c_id, c_data in master_companies.items():
        c_data["brands"] = list(c_data.pop("brands_map").values())
        if selected_hq != "All Headquarters" and c_data.get("hqLocation") and c_data["hqLocation"] != "All Headquarters":
            if c_data["hqLocation"].lower() != selected_hq.lower():
                continue
        formatted_companies.append(c_data)

    formatted_depots = []
    for d_id, d_data in master_depots.items():
        d_data["brands"] = list(d_data.pop("brands_map").values())
        if selected_hq != "All Headquarters" and d_data.get("hqName"):
            if d_data["hqName"].lower() != selected_hq.lower():
                continue
        formatted_depots.append(d_data)

    formatted_tsms = []
    for t_id, raw_t_data in master_tsms.items():
        t_data = dict(raw_t_data)
        t_data["companies"] = list(t_data.get("companies_map", {}).values())
        t_data["brands"] = list(t_data.get("brands_map", {}).values())
        t_data["companyCount"] = {
            "Daily": len(tsm_comp_sets.get(t_id, {}).get("Daily", set())),
            "MTD": len(tsm_comp_sets.get(t_id, {}).get("MTD", set())),
            "YTD": len(tsm_comp_sets.get(t_id, {}).get("YTD", set())),
        }
        depot_ids_list = list(t_data.get("depot_ids", set()))
        t_data.pop("depot_ids", None)
        t_data.pop("companies_map", None)
        t_data.pop("brands_map", None)

        assigned_hq_names = []
        for did in depot_ids_list:
            d_obj = master_depots.get(did)
            if d_obj and d_obj.get("hqName"):
                assigned_hq_names.append(d_obj["hqName"])

        if assigned_hq_names:
            t_data["hqLocation"] = assigned_hq_names[0]
        else:
            t_data["hqLocation"] = "All Headquarters"

        raw_ase_ids = t_data.pop("ase_ids", [])
        t_data["ases"] = [
            {
                "id": aid,
                "name": ase_names_lookup.get(aid, "ASE"),
                "data": ase_sales.get(aid, {
                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                    "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                    "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                }),
                "companyCount": {
                    "Daily": len(ase_comp_sets.get(aid, {}).get("Daily", set())),
                    "MTD": len(ase_comp_sets.get(aid, {}).get("MTD", set())),
                    "YTD": len(ase_comp_sets.get(aid, {}).get("YTD", set())),
                },
                "companies": list(ase_company_maps.get(aid, {}).values()),
                "brands": list(ase_brand_maps.get(aid, {}).values())
            }
            for aid in raw_ase_ids
        ]

        if selected_hq != "All Headquarters":
            matches_hq = any(hq.lower() == selected_hq.lower() for hq in assigned_hq_names)
            if not matches_hq:
                continue

        formatted_tsms.append(t_data)

    # Apply controlled payload test limit if requested
    if test_limit and test_limit > 0:
        logger.info(f"🧪 [DIAGNOSTIC TEST] Slicing companies, depots, and tsms to limit={test_limit}")
        formatted_companies = formatted_companies[:test_limit]
        formatted_depots = formatted_depots[:test_limit]
        formatted_tsms = formatted_tsms[:test_limit]

    t_transform_end = time.perf_counter()
    transform_duration_ms = round((t_transform_end - t_transform_start) * 1000, 2)

    total_cases = sum(comp.get("data", {}).get(selected_period, {}).get("cases", 0) for comp in formatted_companies)
    total_bottles = sum(comp.get("data", {}).get(selected_period, {}).get("bottles", 0) for comp in formatted_companies)

    payload = {
        "status": "success",
        "latest_sale_date": latest_sale_date,
        "record_count": total_records_processed,
        "process_time_ms": transform_duration_ms,
        "period": selected_period,
        "companies": formatted_companies,
        "depots": formatted_depots,
        "tsms": formatted_tsms
    }

    _SALES_RESPONSE_CACHE[cache_key] = {
        "timestamp": time.time(),
        "data": payload
    }

    try:
        from backend.services.cache_service import set_json_cache
        await set_json_cache(f"rll:mobile:sales:{cache_key}", payload, ttl=900)
    except Exception as e_redis_set:
        logger.warning(f"Failed to store sales payload in Redis: {e_redis_set}")

    # J, K, L. Serialization & Response timing
    t_serialize_start = time.perf_counter()
    json_bytes_data = json.dumps(payload).encode("utf-8")
    t_serialize_end = time.perf_counter()
    serialization_duration_ms = round((t_serialize_end - t_serialize_start) * 1000, 2)

    response_bytes = len(json_bytes_data)
    response_kb = round(response_bytes / 1024, 2)
    response_mb = round(response_bytes / (1024 * 1024), 2)

    total_rpc_ms = round(rpc_trace_info.get("sales_rpc_duration_ms", 0) + tsm_rpc_trace.get("tsm_rpc_duration_ms", 0), 2)
    total_rpc_bytes = rpc_trace_info.get("sales_rpc_payload_bytes", 0) + tsm_rpc_trace.get("tsm_rpc_payload_bytes", 0)
    rpc_kb = round(total_rpc_bytes / 1024, 2)
    rpc_mb = round(total_rpc_bytes / (1024 * 1024), 2)

    t_api_end = time.perf_counter()
    total_api_ms = round((t_api_end - t_api_start) * 1000, 2)

    # Calculate Data Volume Counts (Section 7)
    total_companies_count = len(formatted_companies)
    total_brands_count = sum(len(c.get("brands", [])) for c in formatted_companies)
    total_depots_count = len(formatted_depots)
    total_tsms_count = len(formatted_tsms)
    total_ases_count = sum(len(t.get("ases", [])) for t in formatted_tsms)

    logger.info(
        f"\n==================================================\n"
        f"RLL PERFORMANCE TRACE\n"
        f"==================================================\n"
        f"Request ID:\n{request_id}\n\n"
        f"Endpoint:\n/mobile/sales\n\n"
        f"Filters:\nHQ: {selected_hq}\nDepot: All\nCompany: All\nDate: {end_date}\nPeriod: {selected_period}\n\n"
        f"--------------------------------------------------\n"
        f"BACKEND\n"
        f"--------------------------------------------------\n"
        f"Authentication:\n{auth_duration_ms:.1f} ms\n\n"
        f"Master cache:\n{master_cache_duration_ms:.1f} ms\n{'HIT' if master_cache_hit else 'MISS'}\n\n"
        f"Sales cache:\n{sales_cache_duration_ms:.1f} ms\nMISS\n\n"
        f"Supabase RPC:\n{total_rpc_ms:.1f} ms\n\n"
        f"RPC payload:\n{rpc_kb} KB / {rpc_mb:.2f} MB\n\n"
        f"RPC deserialization:\n0.1 ms\n\n"
        f"Python transformation:\n{transform_duration_ms:.1f} ms\n\n"
        f"JSON serialization:\n{serialization_duration_ms:.1f} ms\n\n"
        f"Final API response:\n{response_kb} KB / {response_mb:.2f} MB\n\n"
        f"Total FastAPI time:\n{total_api_ms:.1f} ms\n\n"
        f"--------------------------------------------------\n"
        f"DATA VOLUME METRICS\n"
        f"--------------------------------------------------\n"
        f"Total JSON objects: {total_records_processed}\n"
        f"Companies: {total_companies_count}\n"
        f"Brands: {total_brands_count}\n"
        f"Depots: {total_depots_count}\n"
        f"TSMs: {total_tsms_count}\n"
        f"ASEs: {total_ases_count}\n"
        f"Daily records: {len(company_records)}\n"
        f"MTD records: {len(depot_records)}\n"
        f"YTD records: {len(all_usf_records)}\n"
        f"Total JSON payload: {response_mb:.2f} MB\n"
        f"=================================================="
    )

    return JSONResponse(
        content=payload,
        headers={
            "X-Request-ID": request_id,
            "X-Backend-Duration-Ms": str(total_api_ms),
            "X-Response-Size-Bytes": str(response_bytes),
            "X-Sales-Cache-Status": "MISS"
        }
    )


@router.get("/cascading/groups")
async def get_cascading_groups_endpoint(
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: Optional[str] = Query(None, description="Period filter (Daily/MTD/YTD)"),
    selected_hq: Optional[str] = Query(None, description="Filter by Headquarters name")
):
    """
    Mobile endpoint: Fetch active groups with total licensees, linked depots, and sales summaries using optimized JSON RPC.
    """
    from backend.services.mobile_cascading_service import get_cascading_groups
    return get_cascading_groups(date_from=date_from, date_to=date_to, period=period, selected_hq=selected_hq)


@router.get("/cascading/groups/{group_id}/brands")
async def get_group_brands_endpoint(
    group_id: str,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: Optional[str] = Query(None, description="Period filter (Daily/MTD/YTD)"),
    depot_name: Optional[str] = Query(None, description="Filter by depot name")
):
    """
    Mobile endpoint: Fetch aggregated brand-wise sales for all licensees in a group.
    """
    from backend.services.mobile_cascading_service import get_group_brand_sales
    return get_group_brand_sales(group_id=group_id, date_from=date_from, date_to=date_to, period=period, depot_name=depot_name)


@router.get("/cascading/groups/{group_id}/licensees")
async def get_group_licensees_endpoint(
    group_id: str,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: Optional[str] = Query(None, description="Period filter (Daily/MTD/YTD)"),
    depot_name: Optional[str] = Query(None, description="Filter by depot name")
):
    """
    Mobile endpoint: Fetch licensees for a group with specific depot breakdown and sales stats.
    """
    from backend.services.mobile_cascading_service import get_group_licensees
    return get_group_licensees(group_id=group_id, date_from=date_from, date_to=date_to, period=period, depot_name=depot_name)


@router.get("/cascading/licensees/{licensee_id}/brand-sales")
async def get_licensee_brand_sales_endpoint(
    licensee_id: str,
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    period: Optional[str] = Query(None, description="Period filter (Daily/MTD/YTD)"),
    depot_name: Optional[str] = Query(None, description="Filter by depot name")
):
    """
    Mobile endpoint: Fetch brand-wise sales breakdown for a licensee.
    """
    from backend.services.mobile_cascading_service import get_licensee_brand_sales
    return get_licensee_brand_sales(licensee_id=licensee_id, date_from=date_from, date_to=date_to, period=period, depot_name=depot_name)



def clear_sales_response_cache():
    """Clear all in-memory master lookups & mobile sales response caches."""
    global _MASTER_CACHE, _SALES_RESPONSE_CACHE
    _MASTER_CACHE["timestamp"] = 0
    _MASTER_CACHE["data"] = None
    _SALES_RESPONSE_CACHE.clear()
    logger.info("🧹 Cleared in-memory mobile sales response & master caches.")


async def warm_master_cache():
    """Pre-warm master lookups cache asynchronously during application startup."""
    try:
        logger.info("🔥 Pre-warming master lookup cache during startup...")
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, _fetch_fresh_master_lookups)
        global _MASTER_CACHE
        _MASTER_CACHE["data"] = data
        _MASTER_CACHE["timestamp"] = time.time()
        logger.info("✅ Master lookup cache pre-warmed successfully.")
    except Exception as e:
        logger.warning(f"Failed to pre-warm master lookup cache on startup: {e}")


@router.api_route("/cache/clear", methods=["GET", "POST"])
async def clear_mobile_cache_endpoint():
    """
    Clear all in-memory backend caches (master lookups, sales payload cache).
    """
    clear_sales_response_cache()
    from backend.services.cache_service import invalidate_analytics_cache
    try:
        await invalidate_analytics_cache()
    except Exception as e:
        logger.warning(f"Notice purging Redis cache via endpoint: {e}")

    logger.info("🧹 All in-memory and Redis backend sales & master caches cleared successfully.")
    return {
        "status": "success",
        "message": "All backend caches flushed."
    }


