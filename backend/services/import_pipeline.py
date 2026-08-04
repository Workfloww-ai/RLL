import io
import os
import gc
import time
import logging
import tempfile
import shutil
import zipfile
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
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

# Fallback in-memory DBs for local execution
upload_batches_db: Dict[int, Dict[str, Any]] = {}
upload_logs_db: List[Dict[str, Any]] = []
sales_db: List[Dict[str, Any]] = []
dashboard_summary_db: Dict[str, Dict[str, Any]] = {}
audit_logs_db: List[Dict[str, Any]] = []
batch_counter = 1

class ImportPipelineEngine:

    async def prepare_file_upload(self, file: UploadFile, user_id: str) -> Tuple[Dict[str, Any], str]:
        """
        Phase 1: Validates extension, streams file to local temp disk, uploads to Supabase storage,
        and creates an initial 'pending' record in upload_batches table. Returns (batch_record, temp_path).
        """
        global batch_counter
        filename = file.filename or "uploaded_file.xlsx"
        filename_lower = filename.lower()

        allowed_extensions = (".xlsx", ".xls", ".numbers", ".csv")
        if not filename_lower.endswith(allowed_extensions):
            raise ValueError(f"Invalid file format '{filename}'. Only {', '.join(allowed_extensions)} files are accepted.")

        client = get_supabase()
        storage_path = f"uploads/{int(time.time())}_{filename}"

        uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        _, ext = os.path.splitext(filename)
        temp_file_name = f"temp_{int(time.time())}_{filename}"
        temp_path = os.path.join(uploads_dir, temp_file_name)

        with open(temp_path, "wb") as buffer:
            file.file.seek(0)
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(temp_path)
        logger.info(f"Received file: {filename} (Size: {file_size} bytes)")
        if file_size == 0:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise ValueError("The uploaded file is completely empty (0 bytes).")

        if client:
            try:
                try:
                    client.storage.get_bucket("excel-uploads")
                except Exception:
                    try:
                        client.storage.create_bucket("excel-uploads", options={"public": False})
                    except Exception as b_err:
                        logger.info(f"Storage bucket setup notice: {b_err}")

                with open(temp_path, "rb") as f:
                    client.storage.from_("excel-uploads").upload(
                        path=storage_path,
                        file=f,
                        file_options={"content-type": "application/octet-stream", "upsert": "true"}
                    )
                logger.info(f"Uploaded file {filename} to Supabase Storage at {storage_path}")
            except Exception as st_err:
                logger.warning(f"Could not upload to Supabase Storage: {st_err}. Proceeding with processing.")

        now_str = datetime.now().isoformat()
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        batch_id = batch_counter
        batch_counter += 1

        batch_record = {
            "source_file": filename,
            "load_type": "daily",
            "covers_start": today_str,
            "covers_end": today_str,
            "row_count": 0,
            "status": "pending",
            "uploaded_by": user_id,
            "is_active": True,
            "created_at": now_str,
            "updated_at": now_str,
            "created_by": user_id,
            "updated_by": user_id,
            # Local metrics
            "remarks": "Upload received. Processing in background...",
            "processing_time_seconds": 0.0,
            "imported_rows": 0,
            "duplicate_rows": 0,
            "failed_rows": 0,
            "storage_path": storage_path
        }

        sb_id = self._insert_batch_record_to_supabase(batch_record)
        if sb_id:
            batch_id = sb_id
        batch_record["batch_id"] = batch_id
        upload_batches_db[batch_id] = batch_record

        return batch_record, temp_path

    def process_file_background(self, batch_record: Dict[str, Any], temp_path: str, user_id: str):
        """
        Phase 2: Asynchronous background processing of large files (550k+ rows).
        Uses chunked stream processing, high-performance row iteration, and batch DB flushes.
        """
        start_time = time.time()
        batch_id = batch_record["batch_id"]
        filename = batch_record["source_file"]
        filename_lower = filename.lower()

        logger.info(f"[Batch {batch_id}] Starting background processing for file: {filename}")
        self._log_pipeline_step(batch_id, "PARSING_FILE", "started", f"Parsing file {filename}")

        try:
            # Step 1: Parse Raw Rows
            raw_rows = []
            try:
                if filename_lower.endswith(".numbers"):
                    doc = Document(temp_path)
                    sheets = doc.sheets
                    if sheets and sheets[0].tables:
                        raw_rows = list(sheets[0].tables[0].rows(values_only=True))
                elif filename_lower.endswith(".csv"):
                    try:
                        df_temp = pd.read_csv(temp_path, header=None, encoding='utf-8')
                    except UnicodeDecodeError:
                        try:
                            df_temp = pd.read_csv(temp_path, header=None, encoding='windows-1252')
                        except UnicodeDecodeError:
                            df_temp = pd.read_csv(temp_path, header=None, encoding='latin1')
                    raw_rows = df_temp.values.tolist()
                else:
                    df_temp = None
                    last_err = None
                    engines_to_try = ["calamine", "openpyxl", "xlrd"]
                    for engine in engines_to_try:
                        try:
                            df_temp = pd.read_excel(temp_path, header=None, engine=engine)
                            break
                        except Exception as eng_err:
                            last_err = eng_err
                    if df_temp is None:
                        raise ValueError(f"All parsing engines failed. Last error: {str(last_err)}")
                    raw_rows = df_temp.values.tolist()
            except Exception as e:
                logger.error(f"[Batch {batch_id}] Error parsing file content: {e}")
                self._log_pipeline_step(batch_id, "PARSING_FILE", "failed", str(e))
                batch_record.update({
                    "status": "failed",
                    "remarks": f"Failed to parse file: {str(e)}",
                    "processing_time_seconds": round(time.time() - start_time, 2),
                    "updated_at": datetime.now().isoformat()
                })
                self._update_batch_record_in_supabase(batch_id, batch_record)
                return

            if not raw_rows:
                batch_record.update({
                    "status": "failed",
                    "remarks": "Uploaded file contains no data rows.",
                    "processing_time_seconds": round(time.time() - start_time, 2),
                    "updated_at": datetime.now().isoformat()
                })
                self._update_batch_record_in_supabase(batch_id, batch_record)
                return

            # Step 2: Dynamic Header Detection
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
            
            del raw_rows
            gc.collect()

            df = pd.DataFrame(data_rows, columns=headers).dropna(how="all")
            del data_rows
            gc.collect()

            total_rows = len(df)
            batch_record["row_count"] = total_rows

            # Step 3: Column Mapping & Alias Check
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
                    "batch_id": batch_id,
                    "column_name": ", ".join(missing_cols),
                    "error_message": f"File is missing required columns: {missing_cols}",
                    "is_active": True
                }
                upload_logs_db.append(log_entry)
                self._save_log_batch_to_supabase([log_entry])

                batch_record.update({
                    "status": "failed",
                    "failed_rows": total_rows,
                    "remarks": f"Missing mandatory columns: {missing_cols}",
                    "processing_time_seconds": round(time.time() - start_time, 2),
                    "updated_at": datetime.now().isoformat()
                })
                self._update_batch_record_in_supabase(batch_id, batch_record)
                self._log_pipeline_step(batch_id, "VALIDATE_COLUMNS", "failed", f"Missing columns: {missing_cols}")
                return

            # Extract date range for covers_start / covers_end
            if col_map.get("Date"):
                try:
                    parsed_dates = pd.to_datetime(df[col_map["Date"]], format='mixed', errors='coerce').dropna()
                    if not parsed_dates.empty:
                        batch_record["covers_start"] = parsed_dates.min().strftime("%Y-%m-%d")
                        batch_record["covers_end"] = parsed_dates.max().strftime("%Y-%m-%d")
                except Exception as e:
                    logger.warning(f"Could not parse dates: {e}")

            # Step 4: High-Performance Chunked Processing to sales_fact table
            imported_rows = 0
            duplicate_rows = 0
            failed_rows = 0
            seen_keys = set()
            
            sales_buffer = []
            logs_buffer = []
            
            SALES_CHUNK_SIZE = 5000
            LOGS_CHUNK_SIZE = 1000

            records = df.to_dict('records')
            del df
            gc.collect()

            for idx, row in enumerate(records):
                row_num = idx + 1
                try:
                    sales_date_raw = str(row.get(col_map["Date"], datetime.today().strftime('%Y-%m-%d'))).strip().split(" ")[0]
                    depot_name_val = str(row.get(col_map["Depot Code"], "DEFAULT")).strip()
                    licensee_name_val = str(row.get(col_map["License Number"], "DEFAULT")).strip()
                    brand_name_val = str(row.get(col_map["Brand Code"], "DEFAULT")).strip()
                    packing_name_val = str(row.get(col_map["Packing Size"], "DEFAULT")).strip()

                    cases = float(row.get(col_map["Cases"], 0.0) or 0.0)
                    bottles = float(row.get(col_map["Bottles"], 0.0) or 0.0)
                    bulk_liters = float(row.get(col_map["Bulk Liters"], 0.0) or 0.0)

                    row_key = (sales_date_raw.lower(), depot_name_val.lower(), licensee_name_val.lower(), brand_name_val.lower(), packing_name_val.lower())
                    if row_key in seen_keys:
                        duplicate_rows += 1
                        logs_buffer.append({
                            "batch_id": batch_id,
                            "column_name": "row_key",
                            "error_message": f"Row {row_num}: Duplicate sales entry found in batch.",
                            "is_active": True
                        })
                        continue
                    seen_keys.add(row_key)

                    depot_id = master_service.resolve_depot_id(depot_name_val)
                    licensee_id = master_service.resolve_licensee_id(licensee_name_val, depot_id)
                    brand_id = master_service.resolve_brand_id(brand_name_val)
                    packaging_id = master_service.resolve_packaging_id(packing_name_val)

                    # Match exact Supabase sales_fact columns
                    sale_entry = {
                        "batch_id": batch_id,
                        "sale_date": sales_date_raw,
                        "depot_id": depot_id,
                        "licensee_id": licensee_id,
                        "brand_id": brand_id,
                        "packaging_id": packaging_id,
                        "total_case": cases,
                        "total_btl": bottles,
                        "total_bl": bulk_liters,
                        "is_active": True,
                        "created_by": user_id,
                        "updated_by": user_id
                    }
                    sales_buffer.append(sale_entry)
                    imported_rows += 1

                except Exception as e:
                    failed_rows += 1
                    logs_buffer.append({
                        "batch_id": batch_id,
                        "column_name": "row_processing",
                        "error_message": f"Row {row_num}: {str(e)}",
                        "is_active": True
                    })

                # Flush sales buffer to Supabase sales_fact table
                if len(sales_buffer) >= SALES_CHUNK_SIZE:
                    self._save_sales_to_supabase(sales_buffer)
                    sales_buffer.clear()

                # Flush log buffer to Supabase upload_validation_errors table
                if len(logs_buffer) >= LOGS_CHUNK_SIZE:
                    upload_logs_db.extend(logs_buffer)
                    self._save_log_batch_to_supabase(logs_buffer)
                    logs_buffer.clear()

            # Flush remaining buffers
            if sales_buffer:
                self._save_sales_to_supabase(sales_buffer)
                sales_buffer.clear()

            if logs_buffer:
                upload_logs_db.extend(logs_buffer)
                self._save_log_batch_to_supabase(logs_buffer)
                logs_buffer.clear()

            del records
            gc.collect()

            processing_time = round(time.time() - start_time, 2)
            final_status = "loaded" if failed_rows == 0 else "failed"

            batch_record.update({
                "imported_rows": imported_rows,
                "duplicate_rows": duplicate_rows,
                "failed_rows": failed_rows,
                "processing_time_seconds": processing_time,
                "status": final_status,
                "updated_at": datetime.now().isoformat(),
                "remarks": f"Imported {imported_rows} rows in {processing_time}s. Duplicates: {duplicate_rows}, Failed: {failed_rows}."
            })
            self._update_batch_record_in_supabase(batch_id, batch_record)
            self._log_pipeline_step(batch_id, "LOAD_SALES_FACT", "succeeded", f"Imported {imported_rows} sales records into sales_fact.")

            audit_entry = {
                "table_name": "sales_fact",
                "record_id": str(batch_id),
                "action": "UPLOAD_EXCEL_SALES",
                "new_data": {"batch_id": batch_id, "imported_rows": imported_rows},
                "changed_by": user_id
            }
            audit_logs_db.append(audit_entry)
            self._save_audit_log_to_supabase(audit_entry)

            logger.info(f"[Batch {batch_id}] Successfully finished processing {total_rows} rows in {processing_time} seconds.")

        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    async def process_file_upload(self, file: UploadFile, user_id: str) -> Dict[str, Any]:
        """
        Backwards-compatible synchronous method.
        """
        batch_record, temp_path = await self.prepare_file_upload(file, user_id)
        self.process_file_background(batch_record, temp_path, user_id)
        return batch_record

    def _insert_batch_record_to_supabase(self, record: Dict[str, Any]) -> Optional[int]:
        client = get_supabase()
        if client:
            try:
                clean_rec = record.copy()
                clean_rec.pop("batch_id", None)
                local_fields = ["remarks", "processing_time_seconds", "imported_rows", "duplicate_rows", "failed_rows", "storage_path"]
                for f in local_fields:
                    clean_rec.pop(f, None)
                    
                res = client.table("upload_batches").insert(clean_rec).execute()
                if res.data and len(res.data) > 0:
                    real_id = res.data[0]["batch_id"]
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
                clean_updates.pop("batch_id", None)
                local_fields = ["remarks", "processing_time_seconds", "imported_rows", "duplicate_rows", "failed_rows", "storage_path"]
                for f in local_fields:
                    clean_updates.pop(f, None)
                    
                client.table("upload_batches").update(clean_updates).eq("batch_id", batch_id).execute()
                logger.info(f"Updated upload_batch ID {batch_id} in Supabase")
            except Exception as e:
                logger.warning(f"Error updating upload_batch ID {batch_id} in Supabase: {e}")

    def _save_log_batch_to_supabase(self, logs_list: List[Dict[str, Any]]):
        client = get_supabase()
        if client and logs_list:
            try:
                chunk_size = 500
                for i in range(0, len(logs_list), chunk_size):
                    client.table("upload_validation_errors").insert(logs_list[i:i + chunk_size]).execute()
            except Exception as e:
                logger.warning(f"Error persisting upload_validation_errors batch to Supabase: {e}")

    def _log_pipeline_step(self, batch_id: int, step: str, status: str, message: str):
        client = get_supabase()
        if client:
            try:
                payload = {
                    "batch_id": batch_id,
                    "step": step,
                    "status": status,
                    "message": message
                }
                client.table("upload_pipeline_logs").insert(payload).execute()
            except Exception as e:
                logger.warning(f"Error logging to upload_pipeline_logs: {e}")

    def _save_sales_to_supabase(self, sales_list: List[Dict[str, Any]]):
        client = get_supabase()
        if client and sales_list:
            try:
                chunk_size = 1000
                for i in range(0, len(sales_list), chunk_size):
                    client.table("sales_fact").insert(sales_list[i:i + chunk_size]).execute()
            except Exception as e:
                logger.warning(f"Error persisting sales_fact to Supabase: {e}")

    def _save_audit_log_to_supabase(self, audit_record: Dict[str, Any]):
        client = get_supabase()
        if client:
            try:
                client.table("audit_logs").insert(audit_record).execute()
            except Exception as e:
                logger.warning(f"Error persisting audit_log to Supabase: {e}")

import_pipeline = ImportPipelineEngine()
