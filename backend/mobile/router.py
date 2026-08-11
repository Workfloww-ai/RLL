import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
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

                # 3. Guardrail: Enforce Mobile-only roles
                if role_name.lower() not in ["tsm", "ase", "leader"]:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access Denied: Mobile app is restricted to field personnel."
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

    # 3. Create Access Token
    token = create_access_token(data={"sub": user_data["email"], "role": user_data["role_name"], "user_id": user_data["user_id"]})

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
    email = req.email.lower().strip()
    phone = req.phone.strip()

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
    email = req.email.lower().strip()
    phone = req.phone.strip()
    otp_code = req.otp.strip()

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
                    "email": db_user.get("email") or email,
                    "first_name": db_user.get("first_name", email.split("@")[0].capitalize() if email else "User"),
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

    # Generate Access Token
    token = create_access_token(data={"sub": user_data["email"], "role": user_data["role_name"], "user_id": user_data["user_id"]})

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_data
    }


@router.get("/me")
async def get_mobile_user_profile(
    current_user: dict = Depends(RoleChecker(['tsm', 'ase', 'leader']))
):
    """
    Fetch current logged-in user profile with depot details.
    """
    client = get_supabase()
    email = (current_user.get("sub") or current_user.get("email") or "").lower().strip()
    if not client or not email:
        return current_user

    try:
        res = client.table("users").select("user_id, email, first_name, last_name, phone, is_active").ilike("email", email).execute()
        if res.data and len(res.data) > 0:
            db_user = res.data[0]
            role_name = current_user.get("role", "TSM")
            depot_name = "Jaipur Depot"
            try:
                ud_res = client.table("user_depot").select("depot_id, depots(depot_id, name)").eq("user_id", db_user["user_id"]).execute()
                if ud_res.data:
                    d_obj = ud_res.data[0].get("depots") or {}
                    if d_obj.get("name"):
                        depot_name = d_obj["name"]
            except Exception:
                pass

            return {
                "user_id": str(db_user.get("user_id")),
                "email": db_user.get("email"),
                "first_name": db_user.get("first_name", email.split("@")[0].capitalize()),
                "last_name": db_user.get("last_name", ""),
                "phone": db_user.get("phone", ""),
                "role_name": role_name,
                "depot_name": depot_name,
                "hq_location": "All Headquarters"
            }
    except Exception as e:
        logger.warning(f"Error fetching profile in /mobile/me: {e}")

    return current_user


@router.get("/sales")
async def get_mobile_sales(
    date_from: Optional[str] = Query(None, description="Start Date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="End Date YYYY-MM-DD"),
    period: str = Query("Daily", description="Daily | MTD | YTD"),
    selected_hq: str = Query("All Headquarters", description="Headquarters filter"),
    current_user: dict = Depends(RoleChecker(['tsm', 'ase', 'leader']))
):
    """
    Returns real aggregated sales data for Companies, Depots, and TSMs directly calculated from Supabase.
    Includes ALL master companies (13), depots (53), and TSM managers (8) populated dynamically with live sales.
    """
    client = get_supabase()
    selected_period = period.strip().capitalize() if period else "Daily"
    if selected_period not in ["Daily", "MTD", "YTD"]:
        selected_period = "Daily"

    # 1. Fetch Master Companies (13)
    master_companies = {}
    try:
        c_res = client.table("companies").select("company_id, company_name").execute()
        for c in (c_res.data or []):
            c_name = c.get("company_name")
            if not c_name or c_name == "Others":
                continue
            c_id = c_name.lower().replace(" ", "-").replace("/", "-")
            master_companies[c_id] = {
                "id": c_id,
                "name": c_name,
                "isPinned": c_id in ["rll", "diageo-inbrew"] or c_name.upper() == "RLL",
                "hqLocation": "All Headquarters",
                "data": {
                    "Daily": {"cases": 0, "bottles": 0, "bl": 0.0},
                    "MTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                    "YTD": {"cases": 0, "bottles": 0, "bl": 0.0},
                },
                "brands_map": {}
            }
    except Exception as e:
        logger.warning(f"Error fetching master companies: {e}")

    # 2. Fetch Master Depots (53)
    master_depots = {}
    try:
        d_res = client.table("depots").select("depot_id, name, headquarters(name)").execute()
        for d in (d_res.data or []):
            d_id = str(d.get("depot_id"))
            d_name = d.get("name")
            hq_obj = d.get("headquarters") or {}
            hq_name = hq_obj.get("name") or "Jaipur"
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

    # 3. Fetch Master TSM Managers (8) & map user_depot + ase_tsm_mapping relationships
    master_tsms = {}
    tsm_depot_lookup = {}  # depot_id -> set of tsm_user_ids
    try:
        tsm_res = client.table("user_roles").select(
            "user_id, users(user_id, first_name, last_name, email), roles!inner(role_name)"
        ).eq("roles.role_name", "TSM").execute()

        for t in (tsm_res.data or []):
            u = t.get("users") or {}
            u_id = str(u.get("user_id"))
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

        # Fetch direct user_depot mappings for all users
        ud_res = client.table("user_depot").select("user_id, depot_id").execute()
        user_depots_map = {}
        for ud in (ud_res.data or []):
            uid = str(ud.get("user_id"))
            did = str(ud.get("depot_id"))
            if uid not in user_depots_map:
                user_depots_map[uid] = set()
            user_depots_map[uid].add(did)

        # Fetch ASE underling mapping for TSMs (ase_tsm_mapping)
        atm_res = client.table("ase_tsm_mapping").select("tsm_user_id, ase_user_id").execute()
        tsm_ase_lookup = {}
        for atm in (atm_res.data or []):
            tid = str(atm.get("tsm_user_id"))
            aid = str(atm.get("ase_user_id"))
            if tid not in tsm_ase_lookup:
                tsm_ase_lookup[tid] = set()
            tsm_ase_lookup[tid].add(aid)

        # Build full depot set for each TSM (Direct TSM depots + ASE underling depots)
        for tid, t_obj in master_tsms.items():
            # 1. Direct depots
            t_obj["depot_ids"].update(user_depots_map.get(tid, set()))
            # 2. Underling ASE depots
            for aid in tsm_ase_lookup.get(tid, set()):
                t_obj["depot_ids"].update(user_depots_map.get(aid, set()))

            # Register in reverse lookup map
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
        allowed_depots = set(user_depots_map.get(user_id, [])) if 'user_depots_map' in locals() else set()
        master_tsms = {}

    # 4. Determine target date range
    end_date = date_to or date_from
    if not end_date:
        try:
            max_res = client.table("dashboard_summary_daily").select("sale_date").order("sale_date", desc=True).limit(1).execute()
            if max_res.data and max_res.data[0].get("sale_date"):
                end_date = max_res.data[0]["sale_date"]
            else:
                end_date = "2026-05-31"
        except Exception:
            end_date = "2026-05-31"

    if selected_period == "Daily":
        start_date = date_from or end_date
    elif selected_period == "MTD":
        start_date = date_from or (end_date[:8] + "01")
    elif selected_period == "YTD":
        start_date = date_from or (end_date[:4] + "-01-01")
    else:
        start_date = date_from or end_date

    # 5. Query dashboard_summary_daily for target date range with full pagination
    records = []
    try:
        page = 0
        page_size = 1000
        while True:
            res = client.table("dashboard_summary_daily").select(
                "sale_date, total_case, total_btl, total_bl, company_id, brand_id, depot_id, headquarters_id, companies(company_name), brands(brand_id, brand_name), depots(depot_id, name), headquarters(headquarters_id, name)"
            ).gte("sale_date", start_date).lte("sale_date", end_date).range(page * page_size, (page + 1) * page_size - 1).execute()
            chunk = res.data or []
            if not chunk:
                break
            records.extend(chunk)
            if len(chunk) < page_size:
                break
            page += 1
    except Exception as e:
        logger.warning(f"Error querying dashboard_summary_daily: {e}")

    # 6. Aggregate Sales Into Master Records
    for row in records:
        comp_obj = row.get("companies") or {}
        comp_name = comp_obj.get("company_name") or "Others"

        brand_obj = row.get("brands") or {}
        brand_name = brand_obj.get("brand_name") or "Generic Brand"
        brand_id = str(brand_obj.get("brand_id") or brand_name.lower().replace(" ", "-"))

        depot_obj = row.get("depots") or {}
        raw_depot_id = str(row.get("depot_id") or "")
        depot_name = depot_obj.get("name") or "Central Depot"
        target_depot_id = raw_depot_id or depot_name.lower().replace(" ", "-")

        # RBAC Skip non-allowed depots
        if user_role in ["tsm", "ase"] and target_depot_id not in allowed_depots:
            continue

        hq_obj = row.get("headquarters") or {}
        hq_name = hq_obj.get("name") or "Jaipur"

        cases = int(row.get("total_case") or 0)
        bottles = int(row.get("total_btl") or 0)
        bl = float(row.get("total_bl") or 0.0)

        # A. Company Aggregation (Only named companies in Company list)
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
            for pk in ["Daily", "MTD", "YTD"]:
                master_companies[comp_id]["data"][pk]["cases"] += cases
                master_companies[comp_id]["data"][pk]["bottles"] += bottles
                master_companies[comp_id]["data"][pk]["bl"] += bl

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
            for pk in ["Daily", "MTD", "YTD"]:
                b_map[brand_id]["data"][pk]["cases"] += cases
                b_map[brand_id]["data"][pk]["bottles"] += bottles
                b_map[brand_id]["data"][pk]["bl"] += bl

        # B. Depot Aggregation (Includes ALL sales across depots)
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

        for pk in ["Daily", "MTD", "YTD"]:
            target_depot["data"][pk]["cases"] += cases
            target_depot["data"][pk]["bottles"] += bottles
            target_depot["data"][pk]["bl"] += bl

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
        for pk in ["Daily", "MTD", "YTD"]:
            db_map[brand_id]["data"][pk]["cases"] += cases
            db_map[brand_id]["data"][pk]["bottles"] += bottles
            db_map[brand_id]["data"][pk]["bl"] += bl

        # C. TSM Aggregation (Includes ALL sales across TSM mapped depots)
        target_tsm_uids = tsm_depot_lookup.get(raw_depot_id, set())
        for tsm_user_id in target_tsm_uids:
            if tsm_user_id in master_tsms:
                t_obj = master_tsms[tsm_user_id]
                for pk in ["Daily", "MTD", "YTD"]:
                    t_obj["data"][pk]["cases"] += cases
                    t_obj["data"][pk]["bottles"] += bottles
                    t_obj["data"][pk]["bl"] += bl

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
                for pk in ["Daily", "MTD", "YTD"]:
                    tb_map[brand_id]["data"][pk]["cases"] += cases
                    tb_map[brand_id]["data"][pk]["bottles"] += bottles
                    tb_map[brand_id]["data"][pk]["bl"] += bl

    # Format lists & apply HQ filter if selected
    formatted_companies = []
    for c_id, c_data in master_companies.items():
        c_data["brands"] = list(c_data.pop("brands_map").values())
        if selected_hq != "All Headquarters" and c_data.get("hqLocation"):
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
        # Clean up temporary depot_ids set before returning
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
        "record_count": len(records),
        "period": selected_period,
        "companies": formatted_companies,
        "depots": formatted_depots,
        "tsms": formatted_tsms
    }

    return {
        "status": "success",
        "record_count": len(records),
        "period": selected_period,
        "companies": formatted_companies,
        "depots": formatted_depots,
        "tsms": formatted_tsms
    }

