import logging
import sys
from backend.db.client import get_supabase
from backend.services.master_service import master_service
from backend.db.supabase_client import ensure_calendar_dates
from backend.services.user_service import user_service
from backend.services.analytics_refresh_service import analytics_refresh_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("process_staged_raw")

def process_batch_raw(batch_id: int):
    client = get_supabase()
    if not client:
        logger.error("Supabase client unavailable")
        return

    logger.info(f"--- Processing Batch {batch_id} ---")

    # 0. Populate Users, Roles & Hierarchy from Raw Staging Data
    try:
        user_stats = user_service.populate_users_and_hierarchy_from_raw(batch_id)
        logger.info(f"Batch {batch_id}: Populated {user_stats.get('users', 0)} users and {user_stats.get('mappings', 0)} hierarchy mappings.")
    except Exception as u_err:
        logger.warning(f"Batch {batch_id}: Failed to populate users & hierarchy: {u_err}")

    master_service.prefetch_all_caches()

    # 1. Fetch raw sales
    page = 0
    page_size = 1000
    all_raw = []
    while True:
        res = (
            client.table("raw_sales_upload")
            .select("raw_id, sale_date_raw, licensee_raw, trade_raw, group_name_raw, hq_raw, deo_office_raw, circle_office_raw, depot_raw, ase_raw, asm_tsm_raw, brand_name_raw, packing_raw, total_case, total_btl, total_bl")
            .eq("batch_id", batch_id)
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        )
        data = res.data or []
        if not data:
            break
        all_raw.extend(data)
        page += 1
        if page % 25 == 0:
            logger.info(f"Batch {batch_id}: fetched {len(all_raw)} raw rows...")

    logger.info(f"Batch {batch_id}: Total fetched {len(all_raw)} raw rows.")

    if not all_raw:
        return

    # 2. Extract unique master strings and pre-resolve
    unique_groups = list({r["group_name_raw"] for r in all_raw if r.get("group_name_raw")})
    unique_offices = list({r["deo_office_raw"] for r in all_raw if r.get("deo_office_raw")})
    unique_circles = list({r["circle_office_raw"] for r in all_raw if r.get("circle_office_raw")})
    unique_hqs = list({r["hq_raw"] for r in all_raw if r.get("hq_raw")})
    unique_companies = list({r["company_raw"] for r in all_raw if r.get("company_raw")})
    unique_brands = list({r["brand_name_raw"] for r in all_raw if r.get("brand_name_raw")})
    unique_packagings = list({r["packing_raw"] for r in all_raw if r.get("packing_raw")})

    group_cache = master_service.bulk_resolve_groups(unique_groups)
    office_cache = master_service.bulk_resolve_offices(unique_offices)
    circle_cache = master_service.bulk_resolve_circles(unique_circles)
    hq_cache = master_service.bulk_resolve_headquarters(unique_hqs)
    company_cache = master_service.bulk_resolve_companies(unique_companies)

    depot_items = [
        {
            "depot_name": r.get("depot_raw"),
            "office_id": office_cache.get(master_service._clean(r.get("deo_office_raw"))),
            "circle_id": circle_cache.get(master_service._clean(r.get("circle_office_raw"))),
            "headquarters_id": hq_cache.get(master_service._clean(r.get("hq_raw"))),
        }
        for r in all_raw if r.get("depot_raw")
    ]
    depot_cache = master_service.bulk_resolve_depots(depot_items)

    lic_items = [
        {
            "licensee_name": r.get("licensee_raw"),
            "trade": r.get("trade_raw"),
            "group_name": r.get("group_name_raw"),
            "group_id": group_cache.get(master_service._clean(r.get("group_name_raw"))),
            "headquarters_id": hq_cache.get(master_service._clean(r.get("hq_raw"))),
            "office_id": office_cache.get(master_service._clean(r.get("deo_office_raw"))),
            "circle_id": circle_cache.get(master_service._clean(r.get("circle_office_raw"))),
        }
        for r in all_raw if r.get("licensee_raw")
    ]
    licensee_cache = master_service.bulk_resolve_licensees(lic_items)

    brand_items = [{"brand_name": r.get("brand_name_raw")} for r in all_raw if r.get("brand_name_raw")]
    brand_cache = master_service.bulk_resolve_brands(brand_items)
    packaging_cache = master_service.bulk_resolve_packagings(unique_packagings)

    clean_fn = master_service._clean
    fact_records = []
    sale_dates = set()

    for r in all_raw:
        s_date_raw = str(r.get("sale_date_raw", "")).strip()
        # Format DD.MM.YY or DD.MM.YYYY to YYYY-MM-DD
        try:
            parts = s_date_raw.split(".")
            if len(parts) == 3:
                day, month, year = parts[0], parts[1], parts[2]
                if len(year) == 2:
                    year = "20" + year
                s_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            else:
                s_date = s_date_raw
        except Exception:
            s_date = s_date_raw

        lic_id = licensee_cache.get(clean_fn(r.get("licensee_raw")))
        brd_id = brand_cache.get(clean_fn(r.get("brand_name_raw")))
        pkg_id = packaging_cache.get(clean_fn(r.get("packing_raw")))
        dep_id = depot_cache.get(clean_fn(r.get("depot_raw")))
        cmp_id = company_cache.get(clean_fn(r.get("company_raw")))

        if s_date and lic_id and brd_id and pkg_id and dep_id:
            sale_dates.add(s_date)
            fact_records.append({
                "sale_date": s_date,
                "licensee_id": lic_id,
                "brand_id": brd_id,
                "company_id": cmp_id,
                "packaging_id": pkg_id,
                "depot_id": dep_id,
                "total_case": float(r.get("total_case") or 0.0),
                "total_btl": float(r.get("total_btl") or 0.0),
                "total_bl": float(r.get("total_bl") or 0.0),
                "batch_id": batch_id,
                "is_active": True,
            })

    logger.info(f"Batch {batch_id}: resolved {len(fact_records)} fact records across {len(sale_dates)} unique dates.")

    # 3. Ensure dim_calendar dates exist
    ensure_calendar_dates(list(sale_dates))

    # 4. Insert into sales_fact in chunks (ensuring partitions exist)
    for s_date in sale_dates:
        if len(s_date) >= 7:
            yr, mo = int(s_date[:4]), int(s_date[5:7])
            next_yr = yr if mo < 12 else yr + 1
            next_mo = mo + 1 if mo < 12 else 1
            s_d = f"{yr:04d}-{mo:02d}-01"
            e_d = f"{next_yr:04d}-{next_mo:02d}-01"
            part_tbl = f"sales_fact_{yr:04d}_{mo:02d}"
            part_sql = f"CREATE TABLE IF NOT EXISTS public.{part_tbl} PARTITION OF public.sales_fact FOR VALUES FROM ('{s_d}') TO ('{e_d}');"
            try:
                client.rpc("exec_sql", {"sql_query": part_sql}).execute()
            except Exception:
                pass

    chunk_size = 500
    for i in range(0, len(fact_records), chunk_size):
        chunk = fact_records[i:i + chunk_size]
        client.table("sales_fact").insert(chunk).execute()
        if (i // chunk_size) % 10 == 0:
            logger.info(f"Batch {batch_id}: inserted {i + len(chunk)}/{len(fact_records)} fact rows...")

    logger.info(f"Batch {batch_id}: sales_fact insert complete.")

    # 5. Trigger analytics refresh for batch dates
    analytics_refresh_service.refresh_sales_analytics_for_dates(list(sale_dates))
    
    # 6. Clean up temporary raw staging data after full processing
    try:
        client.table("raw_sales_upload").delete().eq("batch_id", batch_id).execute()
        logger.info(f"Batch {batch_id}: Cleaned up temporary raw_sales_upload data.")
    except Exception as clean_err:
        logger.warning(f"Batch {batch_id}: Failed to delete temporary raw records: {clean_err}")

    # 7. Update batch status
    client.table("upload_batches").update({"status": "loaded"}).eq("batch_id", batch_id).execute()
    logger.info(f"--- Batch {batch_id} Processing Successfully Completed! ---")

if __name__ == "__main__":
    for b_id in [10, 2]:
        process_batch_raw(b_id)

