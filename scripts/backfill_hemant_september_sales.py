import os
import sys
import re
from pyxlsb import open_workbook
from datetime import datetime
from collections import defaultdict

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.db.client import get_supabase
from backend.master_data.service import master_service

def parse_excel_date(dt_val):
    if not dt_val:
        return None
    dt_str = str(dt_val).strip()
    # Support DD.MM.YY or DD.MM.YYYY
    for fmt in ("%d.%m.%y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

def backfill():
    client = get_supabase()
    if not client:
        print("ERROR: Supabase client not available.")
        return

    sep_batch_id = "ec2d8867-c75f-43ec-b0e9-926e8ec04633"
    tenant_id = "a0000000-0000-0000-0000-000000000001"
    hemant_uid = "aa9490b4-848d-47e8-8096-584dfcfb7b41"

    print(f"Connecting to database... Target user: Hemant Kashyap ({hemant_uid})")

    # 1. Check existing rows
    existing = client.table("user_sales_fact").select("id").eq("user_id", hemant_uid).eq("batch_id", sep_batch_id).limit(10).execute()
    existing_count = len(existing.data or [])
    if existing_count > 0:
        print(f"Notice: Found existing rows ({existing_count}) for Hemant with batch {sep_batch_id}. Purging to re-insert clean dataset...")
        client.table("user_sales_fact").delete().eq("user_id", hemant_uid).eq("batch_id", sep_batch_id).execute()

    # 2. Build Company Cache and Brand Cache
    clean_fn = master_service._clean
    comp_res = client.table("companies").select("company_id, company_name").execute()
    company_cache = {}
    for c in (comp_res.data or []):
        cid = str(c["company_id"])
        cname = str(c.get("company_name") or "")
        company_cache[clean_fn(cname)] = cid
        company_cache[master_service._clean_company(cname)] = cid

    brand_res = client.table("brands").select("brand_id, brand_name, company_id").execute()
    brand_cache = {}
    for b in (brand_res.data or []):
        bid = str(b["brand_id"])
        bname = str(b.get("brand_name") or "")
        brand_cache[clean_fn(bname)] = bid

    print(f"Caches loaded: {len(company_cache)} companies, {len(brand_cache)} brands.")

    # 3. Read IMFL Data Sep-2026.xlsb
    file_path = "IMFL Data Sep-2026.xlsb"
    print(f"Reading {file_path} for Hemant Kumar Kashyap...")
    
    fact_records = []
    skipped_comp = 0
    skipped_brand = 0

    with open_workbook(file_path) as wb:
        with wb.get_sheet(wb.sheets[0]) as sheet:
            for i, row in enumerate(sheet.rows()):
                if i < 4:
                    continue
                vals = [cell.v for cell in row]
                if not vals or len(vals) < 15:
                    continue

                ase = str(vals[9] or "").strip()
                if "hemant" not in ase.lower():
                    continue

                dt_raw = vals[0]
                dt_str = parse_excel_date(dt_raw)
                if not dt_str:
                    continue

                comp_raw = str(vals[4] or "").strip()
                brand_raw = str(vals[11] or "").strip()
                case_val = float(vals[13] or 0.0)
                btl_val = float(vals[14] or 0.0)

                cid = company_cache.get(master_service._clean_company(comp_raw)) or company_cache.get(clean_fn(comp_raw))
                if not cid:
                    skipped_comp += 1
                    continue

                bid = brand_cache.get(clean_fn(brand_raw))
                if not bid:
                    skipped_brand += 1
                    continue

                fact_records.append({
                    "user_id": hemant_uid,
                    "company_id": cid,
                    "brand_id": bid,
                    "sale_date": dt_str,
                    "cases": round(case_val + (btl_val / 100.0), 2),
                    "bottles": btl_val,
                    "bl": 0.0,
                    "batch_id": sep_batch_id,
                    "tenant_id": tenant_id
                })

    print(f"Extracted {len(fact_records)} records for Hemant (skipped comp: {skipped_comp}, skipped brand: {skipped_brand})")

    # 4. Bulk Insert into user_sales_fact in chunks
    chunk_size = 1000
    inserted = 0
    for idx in range(0, len(fact_records), chunk_size):
        chunk = fact_records[idx:idx + chunk_size]
        res = client.table("user_sales_fact").insert(chunk).execute()
        inserted += len(chunk)
        print(f"Inserted chunk {idx // chunk_size + 1}: {inserted}/{len(fact_records)} records...")

    print(f"Successfully backfilled {inserted} records into user_sales_fact!")

    # 5. Clear Redis sales cache to reflect immediate update
    from backend.db.redis_client import safe_delete_pattern
    import asyncio
    try:
        asyncio.run(safe_delete_pattern("rll:mobile:sales:*"))
        print("Cleared sales cache keys.")
    except Exception as e_cache:
        print(f"Notice clearing cache: {e_cache}")

    print("Backfill completed!")

if __name__ == "__main__":
    backfill()
