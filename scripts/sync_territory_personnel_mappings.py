import os
import re
import asyncio
import pandas as pd
from difflib import SequenceMatcher
from backend.db.supabase_client import get_supabase_client
from backend.db.redis_client import safe_delete

def clean_str(s: str) -> str:
    if not s or pd.isna(s):
        return ""
    # Normalize slashes, dashes, spaces
    return re.sub(r'[^a-zA-Z0-9]', '', str(s)).lower()

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, clean_str(a), clean_str(b)).ratio()

def find_best_user(name: str, users: list) -> dict:
    if not name or name.lower() in ("unassigned", "none", "null", "nan"):
        return None
    
    clean_target = clean_str(name)
    USER_ALIASES = {
        "cptak": "chandraprakashtak",
        "cp": "chandraprakash"
    }
    if clean_target in USER_ALIASES:
        clean_target = USER_ALIASES[clean_target]

    best_u = None
    best_score = 0.0

    for u in users:
        fn = u.get("first_name") or ""
        ln = u.get("last_name") or ""
        full = f"{fn} {ln}".strip()
        clean_full = clean_str(full)
        clean_fn = clean_str(fn)

        # Exact match
        if clean_full == clean_target:
            return u
        
        # Target contained in full name or vice-versa
        if len(clean_target) >= 4 and (clean_target in clean_full or clean_full in clean_target):
            score = 0.95
        elif len(clean_fn) >= 4 and clean_target == clean_fn:
            score = 0.90
        else:
            score = similarity(name, full)

        if score > best_score:
            best_score = score
            best_u = u

    if best_score >= 0.70:
        return best_u
    return None

def find_best_depot(depot_name: str, db_depots: list) -> dict:
    clean_target = clean_str(depot_name)
    best_d = None
    best_score = 0.0

    for d in db_depots:
        name = d.get("name") or ""
        clean_d = clean_str(name)

        if clean_d == clean_target:
            return d
        
        if clean_target in clean_d or clean_d in clean_target:
            score = 0.90
        else:
            score = similarity(depot_name, name)

        if score > best_score:
            best_score = score
            best_d = d

    if best_score >= 0.65:
        return best_d
    return None

def find_best_hq(hq_name: str, db_hqs: list) -> dict:
    clean_target = clean_str(hq_name)
    for h in db_hqs:
        name = h.get("name") or ""
        if clean_str(name) == clean_target or clean_target in clean_str(name):
            return h
    return None

def run_sync(dry_run: bool = True):
    client = get_supabase_client()
    if not client:
        print("ERROR: Could not get Supabase client.")
        return

    db_depots = client.table("depots").select("depot_id, name, headquarters_id").execute().data or []
    db_users = client.table("users").select("user_id, first_name, last_name, email").execute().data or []
    db_hqs = client.table("headquarters").select("headquarters_id, name").execute().data or []

    print(f"Loaded from DB: {len(db_depots)} depots, {len(db_users)} users, {len(db_hqs)} HQs")

    # Read xlsb mappings
    df = pd.read_excel("IMFL Ind. May-26.xlsb", engine="pyxlsb", skiprows=2)
    mappings = df[["DEPOT_NAME", "H.Q.", "ASE", "ASM/TSM"]].dropna(subset=["DEPOT_NAME"]).drop_duplicates()

    user_depot_rows = []
    user_hq_rows = []
    seen_user_depots = set()
    seen_user_hqs = set()

    matched_depots = 0
    matched_ases = 0
    matched_tsms = 0

    for _, row in mappings.iterrows():
        raw_depot = str(row["DEPOT_NAME"]).strip()
        raw_hq = str(row["H.Q."]).strip() if pd.notna(row["H.Q."]) else ""
        raw_ase = str(row["ASE"]).strip() if pd.notna(row["ASE"]) else ""
        raw_tsm = str(row["ASM/TSM"]).strip() if pd.notna(row["ASM/TSM"]) else ""

        depot_obj = find_best_depot(raw_depot, db_depots)
        if not depot_obj:
            print(f"⚠️  Could not match depot: {raw_depot}")
            continue

        matched_depots += 1
        d_id = depot_obj["depot_id"]
        hq_id = depot_obj.get("headquarters_id")

        if not hq_id and raw_hq:
            hq_obj = find_best_hq(raw_hq, db_hqs)
            if hq_obj:
                hq_id = hq_obj["headquarters_id"]
                if not dry_run:
                    client.table("depots").update({"headquarters_id": hq_id}).eq("depot_id", d_id).execute()

        # Parse ASE names (can be comma or slash separated, e.g. "Laxman/Vikas")
        ase_names = [n.strip() for n in re.split(r'[/,]', raw_ase) if n.strip()]
        for a_name in ase_names:
            u_ase = find_best_user(a_name, db_users)
            if u_ase:
                u_id = u_ase["user_id"]
                key = (u_id, d_id)
                if key not in seen_user_depots:
                    seen_user_depots.add(key)
                    user_depot_rows.append({"user_id": u_id, "depot_id": d_id})
                    matched_ases += 1
                # Map ASE to Headquarter (strictly 1:1)
                if hq_id and u_id not in seen_user_hqs:
                    seen_user_hqs.add(u_id)
                    user_hq_rows.append({
                        "user_id": u_id,
                        "headquarters_id": hq_id,
                        "is_active": True,
                        "tenant_id": "a0000000-0000-0000-0000-000000000001"
                    })
            else:
                print(f"ℹ️  ASE not in DB: '{a_name}' (depot: {depot_obj['name']})")

        # Parse TSM names
        tsm_names = [n.strip() for n in re.split(r'[/,]', raw_tsm) if n.strip()]
        for t_name in tsm_names:
            u_tsm = find_best_user(t_name, db_users)
            if u_tsm:
                u_id = u_tsm["user_id"]
                # Map to HQ (strictly 1:1)
                if hq_id and u_id not in seen_user_hqs:
                    seen_user_hqs.add(u_id)
                    user_hq_rows.append({
                        "user_id": u_id,
                        "headquarters_id": hq_id,
                        "is_active": True,
                        "tenant_id": "a0000000-0000-0000-0000-000000000001"
                    })
                    matched_tsms += 1
                # Also map to depot
                dep_key = (u_id, d_id)
                if dep_key not in seen_user_depots:
                    seen_user_depots.add(dep_key)
                    user_depot_rows.append({"user_id": u_id, "depot_id": d_id})
            else:
                print(f"ℹ️  TSM not in DB: '{t_name}' (depot: {depot_obj['name']})")

    print(f"\n--- MATCHING SUMMARY ---")
    print(f"Depots matched: {matched_depots}/{len(mappings)}")
    print(f"user_depot rows to insert: {len(user_depot_rows)}")
    print(f"user_headquarters_mapping rows to insert: {len(user_hq_rows)}")

    if not dry_run:
        print("\nExecuting database upserts in test database...")
        # Upsert user_depot in batches of 50
        for i in range(0, len(user_depot_rows), 50):
            batch = user_depot_rows[i:i+50]
            client.table("user_depot").upsert(batch, on_conflict="user_id,depot_id").execute()
        print(f"✅ Successfully populated {len(user_depot_rows)} rows into public.user_depot")

        # Insert user_headquarters_mapping
        hq_user_ids = list({r["user_id"] for r in user_hq_rows})
        for u_id in hq_user_ids:
            try:
                client.table("user_headquarters_mapping").delete().eq("user_id", u_id).execute()
            except Exception:
                pass
        for i in range(0, len(user_hq_rows), 50):
            batch = user_hq_rows[i:i+50]
            client.table("user_headquarters_mapping").insert(batch).execute()
        print(f"✅ Successfully populated {len(user_hq_rows)} rows into public.user_headquarters_mapping")

        # Clear Redis cache
        async def clear_cache():
            await safe_delete("rll:cache:depots_list")
            await safe_delete("rll:cache:users_list")
            await safe_delete("rll:cache:headquarters_list")
            print("✅ Purged Redis depots & users caches.")
        asyncio.run(clear_cache())

if __name__ == "__main__":
    import sys
    dry = "--commit" not in sys.argv
    if dry:
        print("=== DRY RUN (pass --commit to apply to test DB) ===")
    else:
        print("=== COMMITTING TO TEST DB ===")
    run_sync(dry_run=dry)
