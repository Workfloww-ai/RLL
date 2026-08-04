import io
import os
import time
import logging
import tempfile
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd
from fastapi import UploadFile
from numbers_parser import Document
from backend.db.client import get_supabase
from backend.services.master_service import master_service

logger = logging.getLogger(__name__)

# Mandatory column names expected in daily government excel uploads
MANDATORY_COLUMNS = [
    "Date", "Depot Code", "License Number", "Brand Code", "Packing Size", 
    "Cases", "Bottles", "Bulk Liters", "Sale Value"
]

# Fallback in-memory DBs for local/offline execution when Supabase instance is unreachable
upload_batches_db: Dict[int, Dict[str, Any]] = {}
upload_logs_db: List[Dict[str, Any]] = []
sales_db: List[Dict[str, Any]] = []
dashboard_summary_db: Dict[str, Dict[str, Any]] = {}
audit_logs_db: List[Dict[str, Any]] = []
batch_counter = 1
sales_counter = 1

class ImportPipelineEngine:

    async def process_file_upload(self, file: UploadFile, user_id: str) -> Dict[str, Any]:
        global batch_counter, sales_counter
        start_time = time.time()
        filename = file.filename or "uploaded_file.xlsx"
        filename_lower = filename.lower()

        # Step 1 & 2: Format & Bucket Regulation Validation (.xlsx, .xls, .numbers)
        allowed_extensions = (".xlsx", ".xls", ".numbers")
        if not filename_lower.endswith(allowed_extensions):
            raise ValueError(f"Invalid file format '{filename}'. Only {', '.join(allowed_extensions)} files are accepted.")

        contents = await file.read()
        client = get_supabase()

        # Try uploading file to Supabase Storage Bucket 'excel-uploads'
        storage_path = f"uploads/{int(time.time())}_{filename}"
        if client:
            try:
                # Ensure bucket exists
                try:
                    client.storage.get_bucket("excel-uploads")
                except Exception:
                    try:
                        client.storage.create_bucket("excel-uploads", options={"public": False})
                    except Exception as b_err:
                        logger.info(f"Storage bucket setup notice: {b_err}")
                
                # Upload file bytes to Supabase Storage
                client.storage.from_("excel-uploads").upload(
                    path=storage_path,
                    file=contents,
                    file_options={"content-type": "application/octet-stream", "upsert": "true"}
                )
                logger.info(f"Uploaded file {filename} to Supabase Storage at {storage_path}")
            except Exception as st_err:
                logger.warning(f"Could not upload to Supabase Storage: {st_err}. Proceeding with processing.")

        # Helper to extract raw rows from spreadsheet formats
        raw_rows = []
        if filename_lower.endswith(".numbers"):
            with tempfile.NamedTemporaryFile(suffix=".numbers", delete=False) as tmp:
                tmp.write(contents)
                tmp_path = tmp.name
            try:
                doc = Document(tmp_path)
                sheets = doc.sheets
                if sheets and sheets[0].tables:
                    raw_rows = list(sheets[0].tables[0].rows(values_only=True))
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        elif filename_lower.endswith(".csv"):
            df_temp = pd.read_csv(io.BytesIO(contents), header=None)
            raw_rows = df_temp.values.tolist()
        else:
            df_temp = pd.read_excel(io.BytesIO(contents), header=None, engine="openpyxl" if filename_lower.endswith(".xlsx") else None)
            raw_rows = df_temp.values.tolist()

        batch_id = batch_counter
        batch_counter += 1

        if not raw_rows:
            batch_record = {
                "upload_batch_id": batch_id,
                "file_name": filename,
                "storage_path": storage_path,
                "uploaded_by": user_id,
                "total_rows": 0,
                "imported_rows": 0,
                "duplicate_rows": 0,
                "failed_rows": 0,
                "processing_time_seconds": 0.0,
                "upload_status": "failed",
                "remarks": "Uploaded file contains no data rows.",
                "created_at": datetime.now().isoformat()
            }
            upload_batches_db[batch_id] = batch_record
            self._insert_batch_record_to_supabase(batch_record)
            return batch_record

        # Dynamic header row detection (searching first 15 rows)
        header_row_idx = 0
        known_keywords = ["date", "brand_name", "depot_name", "total_case", "licensee_name", "packing_in_ml", "depot code"]
        
        for idx, row in enumerate(raw_rows[:15]):
            row_str = [str(cell).strip().lower() if cell is not None else "" for cell in row]
            matches = sum(1 for kw in known_keywords if any(kw in cell for cell in row_str))
            if matches >= 2:
                header_row_idx = idx
                break

        headers = [str(cell).strip() if cell is not None else f"Column_{i+1}" for i, cell in enumerate(raw_rows[header_row_idx])]
        data_rows = raw_rows[header_row_idx + 1:]
        
        df = pd.DataFrame(data_rows, columns=headers)
        df = df.dropna(how="all")

        total_rows = len(df)

        batch_record = {
            "file_name": filename,
            "storage_path": storage_path,
            "uploaded_by": user_id,
            "total_rows": total_rows,
            "imported_rows": 0,
            "duplicate_rows": 0,
            "failed_rows": 0,
            "processing_time_seconds": 0.0,
            "upload_status": "processing",
            "remarks": None,
            "created_at": datetime.now().isoformat()
        }
        sb_id = self._insert_batch_record_to_supabase(batch_record)
        if sb_id:
            batch_id = sb_id
        batch_record["upload_batch_id"] = batch_id
        upload_batches_db[batch_id] = batch_record

        # Step 3: Column Validation with flexible Government Excel Column Aliases (case-insensitive via .lower())
        COLUMN_ALIASES = {
            "Date": ["date", "sales date", "invoice date"],
            "Depot Code": ["depot_name", "depot code", "depot_code", "depot"],
            "License Number": ["licensee_name", "license number", "license_number", "licensee"],
            "Brand Code": ["brand_name", "brand code", "brand_code", "brand"],
            "Packing Size": ["packing_in_ml", "packing size", "packing_size", "packing"],
            "Cases": ["total_case", "cases", "total_cases"],
            "Bottles": ["total_btl", "bottles", "total_bottles"],
            "Bulk Liters": ["total_bl", "bulk liters", "total_bulk_liters"],
            "Sale Value": ["sale value", "amount", "total_amount", "sale_value", "value"]
        }

        col_map = {}
        missing_cols = []
        
        for std_col, aliases in COLUMN_ALIASES.items():
            found_col = None
            for c in df.columns:
                c_clean = str(c).strip().lower()
                if any(alias == c_clean or alias in c_clean for alias in aliases):
                    found_col = c
                    break
            if found_col:
                col_map[std_col] = found_col
            elif std_col == "Sale Value":
                col_map["Sale Value"] = None
            else:
                missing_cols.append(std_col)

        if missing_cols:
            log_entry = {
                "upload_batch_id": batch_id,
                "row_number": 0,
                "column_name": ", ".join(missing_cols),
                "error_type": "MISSING_MANDATORY_COLUMNS",
                "error_message": f"File is missing required columns: {missing_cols}",
                "raw_data": {"columns_found": [str(c).strip().lower() for c in df.columns]},
                "created_at": datetime.now().isoformat()
            }
            upload_logs_db.append(log_entry)
            self._save_log_record_to_supabase(log_entry)

            batch_record.update({
                "upload_status": "failed",
                "failed_rows": total_rows,
                "remarks": f"Missing mandatory columns: {missing_cols}",
                "processing_time_seconds": round(time.time() - start_time, 2)
            })
            self._update_batch_record_in_supabase(batch_id, batch_record)
            return batch_record

        # Step 4: Duplicate Detection & Data Insertion
        imported_rows = 0
        duplicate_rows = 0
        failed_rows = 0
        seen_keys = set()
        new_sales = []

        for idx, row in df.iterrows():
            row_num = idx + 1
            if row_num % 10000 == 0:
                logger.info(f"Processing row {row_num}/{total_rows} in memory...")
            try:
                sales_date_raw = str(row.get(col_map["Date"], datetime.today().strftime('%Y-%m-%d'))).strip().split(" ")[0]
                depot_name_val = str(row.get(col_map["Depot Code"], "DEFAULT")).strip()
                licensee_name_val = str(row.get(col_map["License Number"], "DEFAULT")).strip()
                brand_name_val = str(row.get(col_map["Brand Code"], "DEFAULT")).strip()
                packing_name_val = str(row.get(col_map["Packing Size"], "DEFAULT")).strip()

                cases = float(row.get(col_map["Cases"], 0.0) or 0.0)
                bottles = float(row.get(col_map["Bottles"], 0.0) or 0.0)
                bulk_liters = float(row.get(col_map["Bulk Liters"], 0.0) or 0.0)
                
                raw_sale_val = row.get(col_map["Sale Value"]) if col_map.get("Sale Value") else None
                if raw_sale_val is not None and str(raw_sale_val).strip() != "":
                    sale_value = float(raw_sale_val)
                else:
                    sale_value = round(cases * 5000.0, 2)

                # Duplicate Key check (case-insensitive via .lower())
                row_key = (
                    sales_date_raw.lower(), 
                    depot_name_val.lower(), 
                    licensee_name_val.lower(), 
                    brand_name_val.lower(), 
                    packing_name_val.lower()
                )
                if row_key in seen_keys:
                    duplicate_rows += 1
                    dup_log = {
                        "upload_batch_id": batch_id,
                        "row_number": row_num,
                        "column_name": "row_key",
                        "error_type": "DUPLICATE_ROW",
                        "error_message": "Duplicate sales entry found in batch.",
                        "raw_data": {str(k).strip().lower(): str(v) for k, v in row.to_dict().items()},
                        "created_at": datetime.now().isoformat()
                    }
                    upload_logs_db.append(dup_log)
                    self._save_log_record_to_supabase(dup_log)
                    continue
                seen_keys.add(row_key)

                # Case-insensitive resolution & auto-creation of master records
                depot_id = master_service.resolve_depot_id(depot_name_val)
                licensee_id = master_service.resolve_licensee_id(licensee_name_val, depot_id)
                brand_id = master_service.resolve_brand_id(brand_name_val)
                packing_size_id = master_service.resolve_packing_size_id(packing_name_val)

                sale_entry = {
                    "sale_id": sales_counter,
                    "upload_batch_id": batch_id,
                    "sales_date": sales_date_raw,
                    "depot_id": depot_id,
                    "licensee_id": licensee_id,
                    "brand_id": brand_id,
                    "packing_size_id": packing_size_id,
                    "total_cases": cases,
                    "total_bottles": bottles,
                    "total_bulk_liters": bulk_liters,
                    "sale_value": sale_value,
                    "created_at": datetime.now().isoformat()
                }
                sales_counter += 1
                new_sales.append(sale_entry)
                imported_rows += 1

            except Exception as e:
                failed_rows += 1
                err_log = {
                    "upload_batch_id": batch_id,
                    "row_number": row_num,
                    "column_name": None,
                    "error_type": "ROW_PROCESSING_ERROR",
                    "error_message": str(e),
                    "raw_data": {k: str(v) for k, v in row.to_dict().items()},
                    "created_at": datetime.now().isoformat()
                }
                upload_logs_db.append(err_log)
                self._save_log_record_to_supabase(err_log)

        # Step 6: Bulk Insert Sales
        sales_db.extend(new_sales)
        self._save_sales_to_supabase(new_sales)

        # Step 7: Update Dashboard Summary Aggregations
        for s in new_sales:
            s_date = s["sales_date"]
            if s_date not in dashboard_summary_db:
                dashboard_summary_db[s_date] = {
                    "summary_date": s_date,
                    "total_sales": 0.0,
                    "total_cases": 0.0,
                    "total_bottles": 0.0,
                    "total_bulk_liters": 0.0,
                    "total_brands": set(),
                    "total_licensees": set(),
                    "top_brand_id": s["brand_id"],
                    "top_depot_id": s["depot_id"]
                }
            ds = dashboard_summary_db[s_date]
            ds["total_sales"] += s["sale_value"]
            ds["total_cases"] += s["total_cases"]
            ds["total_bottles"] += s["total_bottles"]
            ds["total_bulk_liters"] += s["total_bulk_liters"]
            ds["total_brands"].add(s["brand_id"])
            ds["total_licensees"].add(s["licensee_id"])

        self._save_dashboard_summary_to_supabase(dashboard_summary_db)

        # Step 8: Update Upload Batch Record
        processing_time = round(time.time() - start_time, 2)
        batch_record.update({
            "imported_rows": imported_rows,
            "duplicate_rows": duplicate_rows,
            "failed_rows": failed_rows,
            "processing_time_seconds": processing_time,
            "upload_status": "completed" if failed_rows == 0 else "partial_success",
            "remarks": f"Imported {imported_rows} rows successfully. Duplicates: {duplicate_rows}, Failed: {failed_rows}."
        })
        self._update_batch_record_in_supabase(batch_id, batch_record)

        # Step 9: Audit Log
        audit_entry = {
            "user_id": user_id,
            "action": "UPLOAD_EXCEL_SALES",
            "table_name": "sales",
            "record_id": str(batch_id),
            "new_value": {"batch_id": batch_id, "imported_rows": imported_rows},
            "created_at": datetime.now().isoformat()
        }
        audit_logs_db.append(audit_entry)
        self._save_audit_log_to_supabase(audit_entry)

        return batch_record

    def _insert_batch_record_to_supabase(self, record: Dict[str, Any]) -> Optional[int]:
        client = get_supabase()
        if client:
            try:
                clean_rec = record.copy()
                clean_rec.pop("upload_batch_id", None) # Let Postgres auto-increment bigserial
                res = client.table("upload_batches").insert(clean_rec).execute()
                if res.data and len(res.data) > 0:
                    real_id = res.data[0]["upload_batch_id"]
                    logger.info(f"Persisted upload_batch to Supabase with ID {real_id}")
                    return real_id
            except Exception as e:
                logger.warning(f"Error inserting upload_batch into Supabase: {e}")
        return None

    def _update_batch_record_in_supabase(self, batch_id: int, updates: Dict[str, Any]):
        client = get_supabase()
        if client:
            try:
                clean_updates = updates.copy()
                clean_updates.pop("upload_batch_id", None)
                client.table("upload_batches").update(clean_updates).eq("upload_batch_id", batch_id).execute()
                logger.info(f"Updated upload_batch ID {batch_id} in Supabase")
            except Exception as e:
                logger.warning(f"Error updating upload_batch ID {batch_id} in Supabase: {e}")

    def _save_log_record_to_supabase(self, log_record: Dict[str, Any]):
        client = get_supabase()
        if client:
            try:
                client.table("upload_logs").insert(log_record).execute()
            except Exception as e:
                logger.warning(f"Error persisting upload_log to Supabase: {e}")

    def _save_sales_to_supabase(self, sales_list: List[Dict[str, Any]]):
        client = get_supabase()
        if client and sales_list:
            try:
                db_sales = []
                for s in sales_list:
                    item = s.copy()
                    item.pop("sale_id", None) # Let Postgres auto-increment sequence
                    db_sales.append(item)
                
                # Batch insert in chunks of 500
                chunk_size = 500
                total_chunks = (len(db_sales) + chunk_size - 1) // chunk_size
                for i in range(0, len(db_sales), chunk_size):
                    chunk_num = (i // chunk_size) + 1
                    logger.info(f"Populating chunk {chunk_num}/{total_chunks} in Supabase (rows {i} to {i+chunk_size})...")
                    client.table("sales").insert(db_sales[i:i + chunk_size]).execute()
            except Exception as e:
                logger.warning(f"Error persisting sales to Supabase: {e}")

    def _save_dashboard_summary_to_supabase(self, summary_dict: Dict[str, Dict[str, Any]]):
        client = get_supabase()
        if client and summary_dict:
            try:
                for s_date, ds in summary_dict.items():
                    record = {
                        "summary_date": s_date,
                        "total_sales": round(ds["total_sales"], 2),
                        "total_cases": round(ds["total_cases"], 2),
                        "total_bottles": round(ds["total_bottles"], 2),
                        "total_bulk_liters": round(ds["total_bulk_liters"], 2),
                        "total_brands": len(ds["total_brands"]) if isinstance(ds["total_brands"], set) else 0,
                        "total_licensees": len(ds["total_licensees"]) if isinstance(ds["total_licensees"], set) else 0,
                        "top_brand_id": ds["top_brand_id"],
                        "top_depot_id": ds["top_depot_id"]
                    }
                    client.table("dashboard_summary_daily").upsert(record, on_conflict="summary_date").execute()
            except Exception as e:
                logger.warning(f"Error persisting dashboard_summary to Supabase: {e}")

    def _save_audit_log_to_supabase(self, audit_record: Dict[str, Any]):
        client = get_supabase()
        if client:
            try:
                client.table("audit_logs").insert(audit_record).execute()
            except Exception as e:
                logger.warning(f"Error persisting audit_log to Supabase: {e}")

import_pipeline = ImportPipelineEngine()

