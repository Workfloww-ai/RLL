import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Query, Request, status
from pydantic import BaseModel
from backend.core.security import create_access_token, get_current_user, RoleChecker
from backend.db.client import get_supabase
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
    client = get_supabase()
    
    user_data = None
    
    if client:
        try:
            # 1. Verify credentials with an ephemeral Supabase Auth client to avoid mutating the global client
            temp_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            auth_response = temp_client.auth.sign_in_with_password({"email": email, "password": credentials.password})
            if not auth_response or not auth_response.user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

            # 2. Get user profile and role
            res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").ilike("email", email).execute()
            if res.data and len(res.data) > 0:
                db_user = res.data[0]
                if not db_user.get("is_active", True):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User account is deactivated"
                    )

                role_name = "admin"
                try:
                    ur_res = client.table("user_roles").select("user_id, role_id, is_active, roles(role_id, role_name)").eq("user_id", db_user["user_id"]).execute()
                    if ur_res.data:
                        for ur in ur_res.data:
                            if ur.get("is_active", True):
                                role_obj = ur.get("roles") or {}
                                if role_obj.get("role_name"):
                                    role_name = role_obj["role_name"]
                                    break
                except Exception:
                    pass

                # 3. Guardrail: Enforce Mobile roles
                if role_name.lower() not in ["tsm", "ase", "leader", "admin", "territory executive"]:
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
                    "hq_location": "All Headquarters"
                }
        except HTTPException:
            raise
        except Exception as e:
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
                res_all = client.table("users").select("user_id, email, phone, first_name, last_name, is_active").execute()
                if res_all.data:
                    for u in res_all.data:
                        u_p = ''.join(c for c in (u.get("phone") or "") if c.isdigit())
                        if u_p and (clean_phone_10 in u_p or u_p in clean_phone_10):
                            db_user = u
                            break
        except Exception as e:
            logger.warning(f"User lookup error in send_mobile_otp: {e}")

    # Enforce registered user requirement
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This mobile number is not registered."
        )

    if not db_user.get("is_active", True):
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

    if not phone or not otp_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number and 6-digit OTP code are required")

    # Verify 6-digit OTP from DB
    is_valid = verify_otp_from_db(phone, otp_code)
    if not is_valid:
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
                    "hq_location": "All Headquarters"
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Error resolving user profile on OTP verify: {e}")

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This mobile number is not registered."
        )

    # Generate Access Token valid for 30 days for mobile application
    sub_identity = user_data.get("email") or user_data.get("phone") or user_data.get("user_id")
    token = create_access_token(
        data={"sub": sub_identity, "role": user_data["role_name"], "user_id": user_data["user_id"]},
        expires_delta=timedelta(days=30)
    )

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
                "hq_location": "All Headquarters"
            }
    except Exception as e:
        logger.warning(f"Error fetching profile in /mobile/me: {e}")

    return current_user


@router.get("/headquarters")
def get_mobile_headquarters():
    """
    Fetches active headquarters from public.headquarters table in Supabase.
    """
    client = get_supabase()
    try:
        res = client.table("headquarters").select("headquarters_id, name, is_active").eq("is_active", True).order("name").execute()
        hq_data = res.data or []
        hq_names = ["All Headquarters"] + [h["name"] for h in hq_data if h.get("name")]
        return {
            "status": "success",
            "count": len(hq_names),
            "headquarters": hq_names
        }
    except Exception as e:
        logger.error(f"Error fetching headquarters: {e}")
        raise HTTPException(status_code=500, detail=f"Database error fetching headquarters: {e}")


@router.get("/companies")
def get_mobile_companies(
    current_user: dict = Depends(get_current_user)
):
    """
    Fetches active liquor companies and their associated brands from Supabase.
    """
    client = get_supabase()
    try:
        c_res = client.table("companies").select("company_id, company_name, is_active, created_at").eq("is_active", True).order("company_name").execute()
        companies_data = c_res.data or []

        b_res = client.table("brands").select("brand_id, brand_name, company_id, is_active, created_at").eq("is_active", True).order("brand_name").execute()
        brands_data = b_res.data or []

        brands_by_company: Dict[str, List[Dict[str, Any]]] = {}
        for b in brands_data:
            cid = str(b.get("company_id") or "")
            if cid:
                if cid not in brands_by_company:
                    brands_by_company[cid] = []
                brands_by_company[cid].append({
                    "brand_id": str(b.get("brand_id")),
                    "brand_name": b.get("brand_name"),
                    "company_id": cid,
                    "is_active": b.get("is_active", True),
                    "created_at": b.get("created_at")
                })

        result = []
        for c in companies_data:
            cid = str(c.get("company_id"))
            result.append({
                "company_id": cid,
                "company_name": c.get("company_name"),
                "is_active": c.get("is_active", True),
                "created_at": c.get("created_at"),
                "brands": brands_by_company.get(cid, [])
            })

        return {
            "status": "success",
            "count": len(result),
            "companies": result
        }
    except Exception as e:
        logger.error(f"Error fetching mobile companies: {e}")
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
    date_from: Optional[str] = Query(None, description="Start Date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End Date YYYY-MM-DD"),
    period: str = Query("Daily", description="Daily | MTD | YTD"),
    selected_hq: str = Query("All Headquarters", description="Headquarters filter"),
    current_user: dict = Depends(RoleChecker(['tsm', 'ase', 'leader', 'admin']))
):
    """
    Returns real aggregated sales data for Companies, Depots, and TSMs directly calculated from Supabase.
    Computes distinct, dynamic metrics for Daily, MTD, and YTD with database-level HQ filtering.
    """
    client = get_supabase()
    selected_period = period.strip().capitalize() if period else "Daily"
    if selected_period not in ["Daily", "MTD", "YTD"]:
        selected_period = "Daily"

    # Pre-fetch lookup maps to avoid socket leaks and PostgREST embedded join errors
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

    # 1. Fetch Master Companies
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

    # 2. Fetch Master Depots & Headquarters lookup
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

    # 3. Fetch Master TSM Managers
    master_tsms = {}
    tsm_depot_lookup = {}  # depot_id -> set of tsm_user_ids
    user_depots_map = {}
    try:
        roles_res = client.table("roles").select("role_id, role_name").execute()
        tsm_role_id = None
        for r in (roles_res.data or []):
            if str(r.get("role_name", "")).upper() == "TSM":
                tsm_role_id = str(r["role_id"])

        if tsm_role_id:
            ur_res = client.table("user_roles").select("user_id").eq("role_id", tsm_role_id).eq("is_active", True).execute()
            tsm_user_ids = [str(ur["user_id"]) for ur in (ur_res.data or [])]
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
        tsm_ase_lookup = {}
        for atm in (atm_res.data or []):
            tid = str(atm.get("tsm_user_id"))
            aid = str(atm.get("ase_user_id"))
            if tid not in tsm_ase_lookup:
                tsm_ase_lookup[tid] = set()
            tsm_ase_lookup[tid].add(aid)

        for tid, t_obj in master_tsms.items():
            t_obj["depot_ids"].update(user_depots_map.get(tid, set()))
            for aid in tsm_ase_lookup.get(tid, set()):
                t_obj["depot_ids"].update(user_depots_map.get(aid, set()))
            for did in t_obj["depot_ids"]:
                if did not in tsm_depot_lookup:
                    tsm_depot_lookup[did] = set()
                tsm_depot_lookup[did].add(tid)
    except Exception as e:
        logger.warning(f"Error fetching master TSMs: {e}")

    # RBAC Data Filtering
    user_role = (current_user.get("role_name") or current_user.get("role") or "").lower()
    user_id = current_user.get("user_id")

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

    # 4. Determine Date Ranges using Latest Database Upload Date
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
    elif date_from and date_from <= latest_sale_date:
        end_date = date_from

    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except Exception:
        end_dt = datetime.utcnow().date()
        end_date = end_dt.strftime("%Y-%m-%d")

    daily_start = date_from if (date_from and date_from <= latest_sale_date) else end_date
    mtd_start = end_dt.replace(day=1).strftime("%Y-%m-%d")
    fy_year = end_dt.year if end_dt.month >= 4 else end_dt.year - 1
    ytd_start = f"{fy_year}-04-01"

    # Headquarters Filter Resolution
    target_hq_id = None
    if selected_hq and selected_hq != "All Headquarters":
        try:
            hq_res = client.table("headquarters").select("headquarters_id").ilike("name", selected_hq.strip()).execute()
            if hq_res.data:
                target_hq_id = hq_res.data[0]["headquarters_id"]
        except Exception as e:
            logger.warning(f"HQ lookup error for {selected_hq}: {e}")

    # Single pass fetch from earliest required date (ytd_start) up to end_date
    query_start = min(daily_start, mtd_start, ytd_start)
    query_end = end_date

    def fetch_page(p: int):
        try:
            q = client.table("dashboard_summary_daily").select(
                "sale_date, total_case, total_btl, total_bl, company_id, brand_id, depot_id, headquarters_id"
            ).gte("sale_date", query_start).lte("sale_date", query_end)

            if target_hq_id:
                q = q.eq("headquarters_id", target_hq_id)

            res = q.range(p * 1000, (p + 1) * 1000 - 1).execute()
            return res.data or []
        except Exception as e_p:
            logger.warning(f"Error fetching page {p}: {e_p}")
            return []

    loop = asyncio.get_event_loop()
    all_records = []
    batch_size = 10
    max_batches = 10
    stop_fetching = False

    for batch_idx in range(max_batches):
        if stop_fetching:
            break
        futures = [
            loop.run_in_executor(None, fetch_page, batch_idx * batch_size + i)
            for i in range(batch_size)
        ]
        chunks = await asyncio.gather(*futures)
        for chunk in chunks:
            if not chunk:
                stop_fetching = True
                break
            all_records.extend(chunk)
            if len(chunk) < 1000:
                stop_fetching = True
                break

    total_records_processed = len(all_records)

    # In-memory single-pass aggregation
    for row in all_records:
        s_date = str(row.get("sale_date") or "")

        active_periods = []
        if daily_start <= s_date <= end_date:
            active_periods.append("Daily")
        if mtd_start <= s_date <= end_date:
            active_periods.append("MTD")
        if ytd_start <= s_date <= end_date:
            active_periods.append("YTD")

        if not active_periods:
            continue

        c_id_raw = str(row.get("company_id") or "")
        comp_name = companies_lookup.get(c_id_raw)
        if not comp_name or comp_name.strip().lower() == "others":
            continue

        b_id_raw = str(row.get("brand_id") or "")
        b_info = brands_lookup.get(b_id_raw, {})
        brand_name = b_info.get("name") or "Generic Brand"
        brand_id = b_id_raw or brand_name.lower().replace(" ", "-")

        raw_depot_id = str(row.get("depot_id") or "")
        depot_info = master_depots.get(raw_depot_id) or {}
        depot_name = depot_info.get("name") or "Central Depot"
        target_depot_id = raw_depot_id or depot_name.lower().replace(" ", "-")

        if user_role in ["tsm", "ase"] and target_depot_id not in allowed_depots:
            continue

        raw_hq_id = str(row.get("headquarters_id") or "")
        hq_name = hq_lookup.get(raw_hq_id) or depot_info.get("hq_name") or "All Headquarters"

        cases = int(row.get("total_case") or 0)
        bottles = int(row.get("total_btl") or 0)
        bl = float(row.get("total_bl") or 0.0)

        for period_key in active_periods:
            # A. Company Aggregation
            if comp_name != "Others":
                comp_id = comp_name.lower().replace(" ", "-").replace("/", "-")
                if comp_id not in master_companies:
                    master_companies[comp_id] = {
                        "id": comp_id,
                        "name": comp_name,
                        "isPinned": comp_id in ["rll", "diageo-inbrew"] or comp_name.upper() == "RLL",
                        "hqLocation": hq_name,
                        "data": {
                            "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                            "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                            "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                        },
                        "brands_map": {}
                    }

                master_companies[comp_id]["hqLocation"] = hq_name
                master_companies[comp_id]["data"][period_key]["cases"] += cases
                master_companies[comp_id]["data"][period_key]["bottles"] += bottles
                master_companies[comp_id]["data"][period_key]["bl"] += bl

                b_map = master_companies[comp_id]["brands_map"]
                if brand_id not in b_map:
                    b_map[brand_id] = {
                        "id": brand_id,
                        "name": brand_name,
                        "data": {
                            "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                            "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                            "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                        }
                    }
                b_map[brand_id]["data"][period_key]["cases"] += cases
                b_map[brand_id]["data"][period_key]["bottles"] += bottles
                b_map[brand_id]["data"][period_key]["bl"] += bl

            # B. Depot Aggregation
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

            target_depot["data"][period_key]["cases"] += cases
            target_depot["data"][period_key]["bottles"] += bottles
            target_depot["data"][period_key]["bl"] += bl

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
            db_map[brand_id]["data"][period_key]["cases"] += cases
            db_map[brand_id]["data"][period_key]["bottles"] += bottles
            db_map[brand_id]["data"][period_key]["bl"] += bl

            # C. TSM Aggregation
            target_tsm_uids = tsm_depot_lookup.get(raw_depot_id, set())
            for tsm_user_id in target_tsm_uids:
                if tsm_user_id in master_tsms:
                    t_obj = master_tsms[tsm_user_id]
                    t_obj["data"][period_key]["cases"] += cases
                    t_obj["data"][period_key]["bottles"] += bottles
                    t_obj["data"][period_key]["bl"] += bl

                    tb_map = t_obj["brands_map"]
                    if brand_id not in tb_map:
                        tb_map[brand_id] = {
                            "brandId": brand_id,
                            "brandName": brand_name,
                            "data": {
                                "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                                "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                                "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                            }
                        }
                    tb_map[brand_id]["data"][period_key]["cases"] += cases
                    tb_map[brand_id]["data"][period_key]["bottles"] += bottles
                    tb_map[brand_id]["data"][period_key]["bl"] += bl

    # Format lists & apply HQ filter if selected
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
    for t_id, t_data in master_tsms.items():
        t_data["brands"] = list(t_data.pop("brands_map").values())
        depot_ids_list = list(t_data.pop("depot_ids", set()))
        if depot_ids_list:
            first_depot = master_depots.get(depot_ids_list[0])
            if first_depot:
                t_data["hqLocation"] = first_depot["hqName"]
        if selected_hq != "All Headquarters" and t_data.get("hqLocation") and t_data["hqLocation"] != "All Headquarters":
            if t_data["hqLocation"].lower() != selected_hq.lower():
                continue
        formatted_tsms.append(t_data)

    return {
        "status": "success",
        "latest_sale_date": latest_sale_date,
        "record_count": total_records_processed,
        "period": selected_period,
        "companies": formatted_companies,
        "depots": formatted_depots,
        "tsms": formatted_tsms
    }
