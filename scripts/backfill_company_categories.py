"""
Script: scripts/backfill_company_categories.py
Description: Backfills the 'category' column in public.companies table using 'IMFL Data Apr-26 (1).xlsb'.
Target: test_db by default. Live DB requires explicit confirmation.
"""

import sys
import pyxlsb
from backend.db.client import get_supabase
from backend.master_data.service import master_service

EXCEL_FILE = "IMFL Data Apr-26 (1).xlsb"

# Pre-defined RLL portfolio companies for safe fallback
RLL_PORTFOLIO = {
    "amrut",
    "ardent",
    "beyond water",
    "beyondwater",
    "campari",
    "diageo",
    "in brew",
    "inbrew",
    "khoday",
    "mhi",
    "rll",
    "rajasthan liquor limited",
    "sgs",
    "william grants",
    "william grant",
    "williamgrant",
}

def extract_excel_mappings(file_path: str):
    mappings = {}
    print(f"📖 Reading {file_path}...")
    with pyxlsb.open_workbook(file_path) as wb:
        sheet_name = wb.sheets[0]
        with wb.get_sheet(sheet_name) as sheet:
            for idx, row in enumerate(sheet.rows()):
                if idx < 2:
                    continue
                vals = [c.v for c in row]
                if len(vals) > 5 and vals[4] is not None and vals[5] is not None:
                    comp = str(vals[4]).strip()
                    cat = str(vals[5]).strip()
                    if comp and cat and comp.lower() != "company name":
                        if comp not in mappings:
                            mappings[comp] = cat

    print(f"✅ Found {len(mappings)} unique companies with category in Excel.")
    return mappings

def run_backfill(dry_run: bool = True):
    client = get_supabase()
    if not client:
        print("❌ Supabase client unavailable.")
        return

    excel_mappings = extract_excel_mappings(EXCEL_FILE)

    # Fetch existing companies
    print("Fetching existing companies from database...")
    try:
        res = client.table("companies").select("company_id, company_name, category").execute()
    except Exception as e:
        print(f"❌ Error querying companies (has migration 055 been applied?): {e}")
        return

    db_companies = res.data or []
    print(f"Found {len(db_companies)} companies in database.")

    # Match and prepare updates
    updates = []
    for comp in db_companies:
        c_id = str(comp["company_id"])
        c_name = str(comp.get("company_name") or "").strip()
        current_cat = comp.get("category")

        # Determine target category
        target_cat = None

        # 1. Direct match
        if c_name in excel_mappings:
            target_cat = excel_mappings[c_name]
        else:
            # 2. Normalized match
            clean_db = master_service._clean_company(c_name)
            for ex_comp, ex_cat in excel_mappings.items():
                if master_service._clean_company(ex_comp) == clean_db:
                    target_cat = ex_cat
                    break

        # 3. Known portfolio fallback
        if not target_cat:
            clean_tok = master_service._clean_company(c_name)
            if any(p.replace(" ", "") in clean_tok for p in RLL_PORTFOLIO):
                target_cat = "RLL"
            else:
                target_cat = "Others"

        if current_cat != target_cat:
            updates.append({
                "company_id": c_id,
                "company_name": c_name,
                "old_category": current_cat,
                "new_category": target_cat
            })

    print(f"\nFound {len(updates)} companies needing category update.")
    print("--- SAMPLE UPDATES ---")
    for u in updates[:15]:
        print(f"  • {u['company_name']}: '{u['old_category']}' -> '{u['new_category']}'")

    if dry_run:
        print("\n[DRY RUN] No database changes made. Pass '--commit' to apply.")
        return

    print("\nApplying updates to database...")
    success_count = 0
    for u in updates:
        try:
            client.table("companies").update({"category": u["new_category"]}).eq("company_id", u["company_id"]).execute()
            success_count += 1
        except Exception as e_up:
            print(f"⚠️ Failed to update {u['company_name']}: {e_up}")

    print(f"✅ Successfully updated {success_count}/{len(updates)} companies.")

if __name__ == "__main__":
    is_dry = "--commit" not in sys.argv
    run_backfill(dry_run=is_dry)

