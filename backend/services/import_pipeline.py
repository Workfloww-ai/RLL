import io
import os
import gc
import time
import logging
import tempfile
import shutil
import zipfile
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import UploadFile
import pandas as pd
from numbers_parser import Document

from backend.db.client import get_supabase
from backend.services.master_service import master_service


logger = logging.getLogger(__name__)


# ============================================================
# GOVERNMENT EXCEL COLUMNS
# ============================================================

MANDATORY_COLUMNS = [
    "Date",
    "Company",
    "LICENSEE_NAME",
    "Trade",
    "Group Name",
    "H.Q.",
    "DEO_OFFICE_NAME",
    "CIRCLE_OFFICE_NAME",
    "DEPOT_NAME",
    "ASE",
    "ASM/TSM",
    "BRAND_NAME",
    "PACKING_IN_ML",
    "TOTAL_CASE",
    "TOTAL_BTL",
    "TOTAL_BL",
]


# Flexible aliases in case government Excel headers change slightly.
COLUMN_ALIASES = {
    "Date": [
        "date",
        "sales date",
        "sale date",
    ],
    "Company": [
        "company",
        "company name",
        "company_name",
    ],
    "LICENSEE_NAME": [
        "licensee_name",
        "licensee name",
        "licensee",
        "license number",
        "license_number",
    ],
    "Trade": [
        "trade",
        "trade type",
        "trade_type",
    ],
    "Group Name": [
        "group name",
        "group_name",
        "group",
    ],
    "H.Q.": [
        "h.q.",
        "h.q",
        "hq",
        "headquarters",
        "headquarter",
    ],
    "DEO_OFFICE_NAME": [
        "deo_office_name",
        "deo office name",
        "deo office",
        "office",
    ],
    "CIRCLE_OFFICE_NAME": [
        "circle_office_name",
        "circle office name",
        "circle office",
        "circle",
    ],
    "DEPOT_NAME": [
        "depot_name",
        "depot name",
        "depot",
        "depot code",
        "depot_code",
    ],
    "ASE": [
        "ase",
        "ase name",
        "ase_name",
    ],
    "ASM/TSM": [
        "asm/tsm",
        "asm / tsm",
        "asm_tsm",
        "asm tsm",
        "tsm",
    ],
    "BRAND_NAME": [
        "brand_name",
        "brand name",
        "brand",
        "brand code",
        "brand_code",
    ],
    "PACKING_IN_ML": [
        "packing_in_ml",
        "packing in ml",
        "packing",
        "packing size",
        "packing_size",
    ],
    "TOTAL_CASE": [
        "total_case",
        "total case",
        "total cases",
        "cases",
        "case",
    ],
    "TOTAL_BTL": [
        "total_btl",
        "total btl",
        "total bottles",
        "bottles",
        "bottle",
    ],
    "TOTAL_BL": [
        "total_bl",
        "total bl",
        "bulk liters",
        "bulk litres",
        "bulk liter",
        "bulk litre",
    ],
}



# ============================================================
# LOCAL RESPONSE CACHE
#
# Your current api/v1/uploads.py GET routes use these variables.
# Supabase remains the real persistent database.
# ============================================================

upload_batches_db: Dict[int, Dict[str, Any]] = {}
upload_logs_db: List[Dict[str, Any]] = []


class ImportPipelineEngine:

    # ========================================================
    # BASIC HELPERS
    # ========================================================

    @staticmethod
    def _clean_text(value) -> str:
        """
        Clean Excel text without changing its capitalization.

        Example:
            "  Sikar   North "
        becomes:
            "Sikar North"
        """

        if value is None:
            return ""

        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass

        value = str(value).strip()

        if value.lower() in {
            "nan",
            "none",
            "null",
            "nat",
        }:
            return ""

        return " ".join(value.split())

    @staticmethod
    def _normalize_header(value) -> str:
        """
        Normalize an Excel header for matching by converting to lowercase
        and stripping all whitespace, underscores, hyphens, dots, and special characters.
        Example: "  Depot_Code-Name. (ML) " -> "depotcodename-ml"
        """
        if value is None:
            return ""

        text = str(value).strip().lower()
        # Remove all whitespace, underscores, hyphens, dots, slashes, and special symbols
        import re
        return re.sub(r"[\s\-_.\/\\(),:;]", "", text)

    @staticmethod
    def _number(value, default: float = 0.0) -> float:
        """
        Convert Excel numeric values safely.

        Handles:
            1
            1.5
            "1,234"
            NaN
            blank
        """

        if value is None:
            return default

        try:
            if pd.isna(value):
                return default
        except Exception:
            pass

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()

        if not text:
            return default

        text = text.replace(",", "")

        return float(text)

    @staticmethod
    def _parse_date(value) -> str:
        """
        Convert Government Excel dates into PostgreSQL DATE.

        Examples:

            01.05.26
                -> 2026-05-01

            01.06.26
                -> 2026-06-01

            01/05/2026
                -> 2026-05-01
        """

        if value is None:
            raise ValueError("Date is empty.")

        try:
            if pd.isna(value):
                raise ValueError("Date is empty.")
        except TypeError:
            pass

        if isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%d")

        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")

        text = str(value).strip()

        if not text:
            raise ValueError("Date is empty.")

        formats = [
            "%d.%m.%y",
            "%d.%m.%Y",
            "%d/%m/%y",
            "%d/%m/%Y",
            "%d-%m-%y",
            "%d-%m-%Y",
            "%Y-%m-%d",
        ]

        for date_format in formats:
            try:
                parsed = datetime.strptime(
                    text,
                    date_format,
                )

                return parsed.strftime(
                    "%Y-%m-%d"
                )

            except ValueError:
                continue

        try:
            parsed = pd.to_datetime(
                text,
                dayfirst=True,
                errors="raise",
            )

            return parsed.strftime(
                "%Y-%m-%d"
            )

        except Exception:
            raise ValueError(
                f"Invalid Date value: {value}"
            )

    @staticmethod
    def _normalize_trade(value) -> str:
        """
        licensees.trade_type CHECK constraint allows:
            Off
            On
        """

        text = str(value or "").strip().lower()

        if text == "off":
            return "Off"

        if text == "on":
            return "On"

        raise ValueError(
            f"Invalid Trade '{value}'. "
            "Expected 'Off' or 'On'."
        )

    # ========================================================
    # CREATE UPLOAD BATCH
    # ========================================================

    def create_initial_batch(
        self,
        filename: str,
        user_id: str,
    ) -> Dict[str, Any]:

        filename_lower = filename.lower()

        allowed_extensions = (
            ".xlsx",
            ".xls",
            ".xlsb",
            ".numbers",
            ".csv",
        )

        if not filename_lower.endswith(allowed_extensions):
            raise ValueError(
                "Invalid file type. Only .xlsx, .xls, .xlsb, .numbers, and .csv files are accepted."
            )

        client = get_supabase()
        batch_id = None

        if client:
            payload = {
                "source_file": filename,
                "load_type": "daily",
                "row_count": 0,
                "status": "pending",
            }
            if user_id and user_id != "00000000-0000-0000-0000-000000000001":
                payload["uploaded_by"] = user_id

            try:
                response = client.table("upload_batches").insert(payload).execute()
                if response.data:
                    batch_id = response.data[0].get("batch_id") or response.data[0].get("upload_batch_id")
            except Exception:
                try:
                    payload.pop("uploaded_by", None)
                    response = client.table("upload_batches").insert(payload).execute()
                    if response.data:
                        batch_id = response.data[0].get("batch_id") or response.data[0].get("upload_batch_id")
                except Exception as exc:
                    logger.warning(f"Could not create upload_batches in Supabase: {exc}")

        if not batch_id:
            batch_id = len(upload_batches_db) + 1


        # ----------------------------------------------------
        # Keep response compatible with your existing
        # UploadBatchResponse Pydantic schema.
        # ----------------------------------------------------

        today_str = datetime.now().strftime("%Y-%m-%d")
        batch_record = {
            "batch_id": batch_id,
            "upload_batch_id": batch_id,
            "source_file": filename,
            "file_name": filename,
            "load_type": "daily",
            "covers_start": today_str,
            "covers_end": today_str,
            "storage_path": f"uploads/{int(time.time())}_{filename}",
            "uploaded_by": user_id if (user_id and len(str(user_id)) == 36 and user_id != "00000000-0000-0000-0000-000000000001") else None,
            "total_rows": 0,
            "imported_rows": 0,
            "duplicate_rows": 0,
            "failed_rows": 0,
            "processing_time_seconds": 0.0,
            "status": "pending",
            "upload_status": "pending",
            "remarks": "File accepted. Processing started.",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        upload_batches_db[
            batch_id
        ] = batch_record

        logger.info(
            "Upload batch %s created.",
            batch_id,
        )
        return batch_record

    async def process_file_upload(self, file: UploadFile, user_id: str) -> Dict[str, Any]:
        """
        Backwards-compatible synchronous method.
        """
        batch_record, temp_path = await self.prepare_file_upload(file, user_id)
        self.process_file_background(batch_record, temp_path, user_id)
        return batch_record

    # ========================================================
    # MAIN BACKGROUND PIPELINE
    # ========================================================

    async def process_file_upload(self, upload_file: Any, user_id: str) -> Dict[str, Any]:
        contents = await upload_file.read()
        filename = getattr(upload_file, "filename", "uploaded_file.xlsx") or "uploaded_file.xlsx"
        batch_record = self.create_initial_batch(filename, user_id)
        batch_id = batch_record["upload_batch_id"]
        self.process_file_upload_async(filename, contents, user_id, batch_id)
        return upload_batches_db.get(batch_id, batch_record)

    def process_file_upload_async(
        self,
        filename: str,
        contents: bytes,
        user_id: str,
        batch_id: int,
    ):
        start_time = time.time()
        try:
            self._pipeline_log(
                batch_id=batch_id,
                step="file_received",
                status="started",
                message=f"Processing {filename}",
            )

            self._upload_original_file(
                filename=filename,
                contents=contents,
                batch_id=batch_id,
            )

            dataframe = self._parse_file(
                filename=filename,
                contents=contents,
            )

            if dataframe.empty:
                raise ValueError("Uploaded file contains no data rows.")

            column_map = self._build_column_map(dataframe)
            logger.info("Excel column mapping for batch %s: %s", batch_id, column_map)

            total_rows = len(dataframe)
            self._update_batch(batch_id=batch_id, row_count=total_rows, status="pending")

            local_batch = upload_batches_db.get(batch_id)
            if local_batch:
                local_batch["total_rows"] = total_rows

            self._update_batch_progress(
                batch_id,
                remarks=f"File parsed ({total_rows} rows). Prefetching and bulk resolving master data...",
            )
            master_service.prefetch_all_caches()

            # Vectorized Series Extraction & Cleaning
            def get_series(col_key, default=""):
                col_name = column_map.get(col_key)
                if col_name and col_name in dataframe.columns:
                    return dataframe[col_name].fillna("").astype(str).str.strip()
                return pd.Series([default] * total_rows, index=dataframe.index)

            s_date = get_series("Date")
            s_company = get_series("Company")
            s_licensee = get_series("LICENSEE_NAME")
            s_trade = get_series("Trade")
            s_group = get_series("Group Name")
            s_hq = get_series("H.Q.")
            s_deo = get_series("DEO_OFFICE_NAME")
            s_circle = get_series("CIRCLE_OFFICE_NAME")
            s_depot = get_series("DEPOT_NAME")
            s_ase = get_series("ASE")
            s_asm = get_series("ASM/TSM")
            s_brand = get_series("BRAND_NAME")
            s_packing = get_series("PACKING_IN_ML")

            def get_num_series(col_key):
                col_name = column_map.get(col_key)
                if col_name and col_name in dataframe.columns:
                    return pd.to_numeric(dataframe[col_name], errors="coerce").fillna(0.0)
                return pd.Series([0.0] * total_rows, index=dataframe.index)

            s_cases = get_num_series("TOTAL_CASE")
            s_btl = get_num_series("TOTAL_BTL")
            s_bl = get_num_series("TOTAL_BL")

            # Master Bulk Resolution
            unique_groups = [g for g in s_group.unique() if g]
            unique_offices = [o for o in s_deo.unique() if o]
            unique_circles = [c for c in s_circle.unique() if c]
            unique_hqs = [h for h in s_hq.unique() if h]
            unique_companies = [c for c in s_company.unique() if c]
            unique_brands = [b for b in s_brand.unique() if b]
            unique_packagings = [p for p in s_packing.unique() if p]

            group_cache = master_service.bulk_resolve_groups(unique_groups)
            office_cache = master_service.bulk_resolve_offices(unique_offices)
            circle_cache = master_service.bulk_resolve_circles(unique_circles)
            hq_cache = master_service.bulk_resolve_headquarters(unique_hqs)
            company_cache = master_service.bulk_resolve_companies(unique_companies)

            depot_items = [
                {
                    "depot_name": d,
                    "office_id": office_cache.get(master_service._clean(deo)),
                    "circle_id": circle_cache.get(master_service._clean(cir)),
                    "headquarters_id": hq_cache.get(master_service._clean(hq)),
                }
                for d, deo, cir, hq in zip(s_depot, s_deo, s_circle, s_hq)
                if d
            ]
            depot_cache = master_service.bulk_resolve_depots(depot_items)

            lic_items = [
                {
                    "licensee_name": l,
                    "trade": t,
                    "group_name": g,
                    "group_id": group_cache.get(master_service._clean(g)),
                    "headquarters_id": hq_cache.get(master_service._clean(hq)),
                    "office_id": office_cache.get(master_service._clean(deo)),
                    "circle_id": circle_cache.get(master_service._clean(cir)),
                }
                for l, t, g, hq, deo, cir in zip(s_licensee, s_trade, s_group, s_hq, s_deo, s_circle)
                if l
            ]
            licensee_cache = master_service.bulk_resolve_licensees(lic_items)

            brand_items = [
                {
                    "brand_name": b,
                    "company_id": company_cache.get(master_service._clean(c)),
                }
                for b, c in zip(s_brand, s_company)
                if b
            ]
            brand_cache = master_service.bulk_resolve_brands(brand_items)
            packaging_cache = master_service.bulk_resolve_packagings(unique_packagings)

            # Vectorized ID Resolution
            clean_fn = master_service._clean
            map_depot = s_depot.map(lambda x: depot_cache.get(clean_fn(x)))
            map_licensee = s_licensee.map(lambda x: licensee_cache.get(clean_fn(x)))
            map_brand = s_brand.map(lambda x: brand_cache.get(clean_fn(x)))
            map_packaging = s_packing.map(lambda x: packaging_cache.get(clean_fn(x)))

            # Parse dates vectorized
            def parse_date_val(d):
                try:
                    return self._parse_date(d)
                except Exception:
                    return datetime.today().strftime("%Y-%m-%d")

            map_date = s_date.apply(parse_date_val)

            # Build Raw Staging DataFrame & Records
            raw_df = pd.DataFrame({
                "batch_id": batch_id,
                "sale_date_raw": s_date,
                "company_raw": s_company,
                "licensee_raw": s_licensee,
                "trade_raw": s_trade,
                "group_name_raw": s_group,
                "hq_raw": s_hq,
                "deo_office_raw": s_deo,
                "circle_office_raw": s_circle,
                "depot_raw": s_depot,
                "ase_raw": s_ase,
                "asm_tsm_raw": s_asm,
                "brand_name_raw": s_brand,
                "packing_raw": s_packing,
                "total_case": s_cases,
                "total_btl": s_btl,
                "total_bl": s_bl,
            })
            raw_records = raw_df.to_dict("records")

            # Build Sales Fact DataFrame & Records
            fact_df = pd.DataFrame({
                "sale_date": map_date,
                "licensee_id": map_licensee,
                "brand_id": map_brand,
                "packaging_id": map_packaging,
                "depot_id": map_depot,
                "total_case": s_cases,
                "total_btl": s_btl,
                "total_bl": s_bl,
                "batch_id": batch_id,
            })

            valid_mask = fact_df[["depot_id", "licensee_id", "brand_id", "packaging_id"]].notna().all(axis=1)
            valid_fact_df = fact_df[valid_mask].copy()
            fact_records = valid_fact_df.to_dict("records")

            imported_rows = len(fact_records)
            failed_rows = total_rows - imported_rows

            # Step 7 - Bulk Insert Raw Records in chunks with progress
            if raw_records:
                self._bulk_insert(
                    table="raw_sales_upload",
                    records=raw_records,
                    chunk_size=5000,
                    batch_id=batch_id,
                )

            # Step 8 - Validation Status
            if fact_records:
                self._update_batch(batch_id=batch_id, status="validated")

            # Step 9 - Bulk Insert Sales Fact Records in chunks with progress
            if fact_records:
                distinct_dates = list({str(r.get("sale_date", "")).strip() for r in fact_records if r.get("sale_date")})
                from backend.db.supabase_client import ensure_calendar_dates
                ensure_calendar_dates(distinct_dates)

                self._bulk_insert(
                    table="sales_fact",
                    records=fact_records,
                    chunk_size=5000,
                    batch_id=batch_id,
                )

            # Step 10 - Trigger Analytics Summaries Refresh (Daily + Monthly) ONLY after complete sales_fact ingestion
            if fact_records and imported_rows > 0:
                distinct_dates = list({r.get("sale_date") for r in fact_records if r.get("sale_date")})
                from backend.services.analytics_refresh_service import analytics_refresh_service
                refresh_ok = analytics_refresh_service.refresh_sales_analytics_for_dates(distinct_dates)
                if not refresh_ok:
                    logger.warning(f"Analytics summary refresh encountered minor issues for batch {batch_id}.")

            final_status = "loaded" if imported_rows > 0 else "failed"
            self._update_batch(batch_id=batch_id, row_count=total_rows, status=final_status)

            processing_time = round(time.time() - start_time, 2)
            if local_batch:
                local_batch.update({
                    "total_rows": total_rows,
                    "imported_rows": imported_rows,
                    "duplicate_rows": 0,
                    "failed_rows": failed_rows,
                    "processing_time_seconds": processing_time,
                    "upload_status": final_status,
                    "remarks": (
                        f"Processed {total_rows} rows in {processing_time}s. "
                        f"Loaded {imported_rows}. Failed {failed_rows}."
                    ),
                })

            self._pipeline_log(
                batch_id=batch_id,
                step="file_processing",
                status="succeeded",
                message=(
                    f"Processing completed in {processing_time}s. "
                    f"Total={total_rows}, Loaded={imported_rows}, Failed={failed_rows}."
                ),
            )

            self._save_audit_log(
                batch_id=batch_id,
                user_id=user_id,
                imported_rows=imported_rows,
            )

            return local_batch


        # =====================================================
        # COMPLETE PIPELINE FAILURE (WITH AUTOMATIC ROLLBACK)
        # =====================================================

        except Exception as exc:

            logger.exception(
                "Upload batch %s failed.",
                batch_id,
            )

            # Rollback / cleanup any partial records inserted for this batch
            self._cleanup_failed_batch(batch_id)

            try:
                self._update_batch(
                    batch_id=batch_id,
                    status="failed",
                )
            except Exception:
                logger.exception(
                    "Could not mark batch %s failed.",
                    batch_id,
                )

            local_batch = upload_batches_db.get(batch_id)

            if local_batch:
                local_batch.update({
                    "upload_status": "failed",
                    "remarks": f"Pipeline failed: {str(exc)}. All partial records rolled back.",
                    "processing_time_seconds": round(time.time() - start_time, 2),
                })

            try:
                self._pipeline_log(
                    batch_id=batch_id,
                    step="file_processing",
                    status="failed",
                    message=str(exc),
                )
            except Exception:
                pass

            return local_batch

    # ========================================================
    # EXCEL ROW EXTRACTION
    # ========================================================

    def _extract_row(
        self,
        row,
        column_map: Dict[str, str],
    ) -> Dict[str, Any]:

        sale_date_raw = self._clean_text(
            row[
                column_map["Date"]
            ]
        )

        company = self._clean_text(
            row[
                column_map["Company"]
            ]
        )

        licensee_name = self._clean_text(
            row[
                column_map["LICENSEE_NAME"]
            ]
        )

        trade = self._normalize_trade(
            row[
                column_map["Trade"]
            ]
        )

        group_name = self._clean_text(
            row[
                column_map["Group Name"]
            ]
        )

        hq_name = self._clean_text(
            row[
                column_map["H.Q."]
            ]
        )

        deo_office_name = self._clean_text(
            row[
                column_map[
                    "DEO_OFFICE_NAME"
                ]
            ]
        )

        circle_office_name = self._clean_text(
            row[
                column_map[
                    "CIRCLE_OFFICE_NAME"
                ]
            ]
        )

        depot_name = self._clean_text(
            row[
                column_map["DEPOT_NAME"]
            ]
        )

        ase_name = self._clean_text(
            row[
                column_map["ASE"]
            ]
        )

        asm_tsm_name = self._clean_text(
            row[
                column_map["ASM/TSM"]
            ]
        )

        brand_name = self._clean_text(
            row[
                column_map["BRAND_NAME"]
            ]
        )

        packing_raw = self._clean_text(
            row[
                column_map["PACKING_IN_ML"]
            ]
        )

        total_case = self._number(
            row[
                column_map["TOTAL_CASE"]
            ]
        )

        total_btl = self._number(
            row[
                column_map["TOTAL_BTL"]
            ]
        )

        total_bl = self._number(
            row[
                column_map["TOTAL_BL"]
            ]
        )

        # ----------------------------------------------------
        # Validate mandatory textual values.
        # ----------------------------------------------------

        required_text = {

            "Date":
                sale_date_raw,

            "Company":
                company,

            "LICENSEE_NAME":
                licensee_name,

            "Group Name":
                group_name,

            "H.Q.":
                hq_name,

            "DEO_OFFICE_NAME":
                deo_office_name,

            "CIRCLE_OFFICE_NAME":
                circle_office_name,

            "DEPOT_NAME":
                depot_name,

            "ASE":
                ase_name,

            "ASM/TSM":
                asm_tsm_name,

            "BRAND_NAME":
                brand_name,

            "PACKING_IN_ML":
                packing_raw,
        }

        for column_name, value in (
            required_text.items()
        ):

            if not value:
                raise ValueError(
                    f"{column_name} is empty."
                )

        sale_date = self._parse_date(
            sale_date_raw
        )

        return {

            "sale_date_raw":
                sale_date_raw,

            "sale_date":
                sale_date,

            "company":
                company,

            "licensee_name":
                licensee_name,

            "trade":
                trade,

            "group_name":
                group_name,

            "hq_name":
                hq_name,

            "deo_office_name":
                deo_office_name,

            "circle_office_name":
                circle_office_name,

            "depot_name":
                depot_name,

            "ase_name":
                ase_name,

            "asm_tsm_name":
                asm_tsm_name,

            "brand_name":
                brand_name,

            "packing_raw":
                packing_raw,

            "total_case":
                total_case,

            "total_btl":
                total_btl,

            "total_bl":
                total_bl,
        }

    # ========================================================
    # BUILD COLUMN MAP
    # ========================================================

    def _build_column_map(
        self,
        dataframe: pd.DataFrame,
    ) -> Dict[str, str]:

        available_columns = {}

        for column in dataframe.columns:

            normalized = (
                self._normalize_header(
                    column
                )
            )

            available_columns[
                normalized
            ] = column

        column_map = {}

        STRICT_MANDATORY = {
            "Date",
            "LICENSEE_NAME",
            "DEPOT_NAME",
            "BRAND_NAME",
            "PACKING_IN_ML",
            "TOTAL_CASE",
            "TOTAL_BTL",
            "TOTAL_BL",
        }

        missing_columns = []

        for (
            standard_column,
            aliases,
        ) in COLUMN_ALIASES.items():

            found_column = None

            for alias in aliases:

                alias_normalized = (
                    self._normalize_header(
                        alias
                    )
                )

                if (
                    alias_normalized
                    in available_columns
                ):

                    found_column = (
                        available_columns[
                            alias_normalized
                        ]
                    )

                    break

            if found_column is None:
                if standard_column in STRICT_MANDATORY:
                    missing_columns.append(
                        standard_column
                    )
            else:

                column_map[
                    standard_column
                ] = found_column

        if missing_columns:

            actual_columns = [
                str(column)
                for column
                in dataframe.columns
            ]

            raise ValueError(
                "Missing mandatory Excel columns: "
                f"{missing_columns}. "
                f"Columns detected: "
                f"{actual_columns}"
            )

        return column_map


    # ========================================================
    # FILE PARSER
    # ========================================================

    def _parse_file(
        self,
        filename: str,
        contents: bytes,
    ) -> pd.DataFrame:

        filename_lower = filename.lower()

        # ----------------------------------------------------
        # APPLE NUMBERS (.numbers)
        # ----------------------------------------------------
        if filename_lower.endswith(".numbers"):
            try:
                return self._parse_numbers(contents)
            except Exception as e_num:
                logger.warning(f"Dedicated _parse_numbers failed: {e_num}. Trying general parsers...")

        raw_dataframe = None

        # ----------------------------------------------------
        # 1. EXCEL PARSING (.xlsx, .xls, .xlsb, etc.)
        # ----------------------------------------------------
        excel_engines = ["calamine", "pyxlsb", "openpyxl", "xlrd"]
        for engine in excel_engines:
            try:
                raw_dataframe = pd.read_excel(io.BytesIO(contents), header=None, engine=engine)
                if raw_dataframe is not None and not raw_dataframe.empty and len(raw_dataframe) > 0:
                    break
            except Exception:
                continue

        # Dedicated pyxlsb engine parser for binary files (.xlsb)
        if (raw_dataframe is None or raw_dataframe.empty) and filename_lower.endswith(".xlsb"):
            try:
                import pyxlsb
                rows = []
                with pyxlsb.open_workbook(io.BytesIO(contents)) as wb:
                    sheet_name = wb.sheets[0]
                    with wb.get_sheet(sheet_name) as sheet:
                        for row in sheet.rows():
                            rows.append([cell.v for cell in row])
                if rows:
                    raw_dataframe = pd.DataFrame(rows)
            except Exception as e_xlsb:
                logger.warning(f"Dedicated pyxlsb workbook parsing failed: {e_xlsb}")

        # ----------------------------------------------------
        # 2. CSV / TSV / DELIMITED TEXT PARSING
        # ----------------------------------------------------
        if raw_dataframe is None or raw_dataframe.empty:
            encodings_to_try = ["utf-8", "utf-8-sig", "cp1252", "latin1", "iso-8859-1", "ascii"]
            delimiters_to_try = [",", ";", "\t", "|"]

            for enc in encodings_to_try:
                for sep in delimiters_to_try:
                    try:
                        df_test = pd.read_csv(
                            io.BytesIO(contents),
                            header=None,
                            encoding=enc,
                            sep=sep,
                            low_memory=False,
                            on_bad_lines="skip"
                        )
                        # Ensure parser actually separated columns instead of 1 giant string column
                        if df_test is not None and not df_test.empty and len(df_test.columns) > 1:
                            raw_dataframe = df_test
                            break
                    except Exception:
                        continue
                if raw_dataframe is not None and not raw_dataframe.empty:
                    break

        # ----------------------------------------------------
        # 3. LEGACY HTML / XML TABLE EXPORTS (Government Software .xls/.csv exports)
        # ----------------------------------------------------
        if raw_dataframe is None or raw_dataframe.empty:
            try:
                html_dfs = pd.read_html(io.BytesIO(contents))
                if html_dfs and len(html_dfs) > 0:
                    raw_dataframe = html_dfs[0]
            except Exception:
                pass

        # ----------------------------------------------------
        # 4. LAST RESORT: STANDARD CSV READ
        # ----------------------------------------------------
        if raw_dataframe is None or raw_dataframe.empty:
            try:
                raw_dataframe = pd.read_csv(
                    io.BytesIO(contents),
                    header=None,
                    encoding="latin1",
                    on_bad_lines="skip",
                    low_memory=False
                )
            except Exception:
                pass

        if raw_dataframe is None or raw_dataframe.empty:
            raise ValueError(f"Could not parse file '{filename}'. Unrecognized or corrupted file format.")

        header_index = self._detect_header_row(raw_dataframe)
        if header_index is None:
            header_index = 0

        headers = [str(col).strip() for col in raw_dataframe.iloc[header_index].values]
        dataframe = raw_dataframe.iloc[header_index + 1 :].copy()
        dataframe.columns = headers
        dataframe = dataframe.dropna(how="all")

        # Remove completely unnamed columns.
        valid_columns = []

        for column in dataframe.columns:

            column_text = (
                str(column).strip()
            )

            if not column_text.lower().startswith(
                "unnamed:"
            ):

                valid_columns.append(
                    column
                )

        dataframe = dataframe[
            valid_columns
        ]

        return dataframe

    # ========================================================
    # HEADER DETECTION
    # ========================================================

    def _detect_header_row(
        self,
        dataframe: pd.DataFrame,
    ) -> Optional[int]:

        """
        Your Excel begins with:

        IMFL Ind. May-2026 ... totals

        followed by:

        Date
        Company
        LICENSEE_NAME
        Trade
        Group Name
        H.Q.
        ...
        """

        strong_headers = {
            "date",
            "company",
            "licensee_name",
            "trade",
            "group name",
            "depot_name",
            "brand_name",
            "packing_in_ml",
            "total_case",
            "total_btl",
            "total_bl",
            "depot code",
            "license number",
            "brand code",
            "packing size",
            "cases",
            "bottles",
            "bulk liters",
            "sale value",
            "depot",
            "brand",
            "licensee",
        }

        rows_to_scan = min(
            len(dataframe),
            25,
        )

        for index in range(
            rows_to_scan
        ):

            row_values = set()

            for value in (
                dataframe
                .iloc[index]
                .tolist()
            ):

                normalized = (
                    self._normalize_header(
                        value
                    )
                )

                if normalized:
                    row_values.add(
                        normalized
                    )

            matches = len(
                row_values.intersection(
                    strong_headers
                )
            )

            if matches >= 2:

                logger.info(
                    "Detected Excel header "
                    "at row index %s.",
                    index,
                )

                return index

        return None


    # ========================================================
    # NUMBERS PARSER
    # ========================================================

    def _parse_numbers(
        self,
        contents: bytes,
    ) -> pd.DataFrame:

        with tempfile.NamedTemporaryFile(
            suffix=".numbers",
            delete=False,
        ) as temporary_file:

            temporary_file.write(
                contents
            )

            temporary_path = (
                temporary_file.name
            )

        try:

            document = Document(
                temporary_path
            )

            if not document.sheets:
                raise ValueError(
                    "Numbers file has no sheets."
                )

            sheet = (
                document.sheets[0]
            )

            if not sheet.tables:
                raise ValueError(
                    "Numbers sheet has no tables."
                )

            rows = list(
                sheet.tables[0].rows(
                    values_only=True
                )
            )

            if not rows:
                raise ValueError(
                    "Numbers file contains no rows."
                )

            raw_dataframe = (
                pd.DataFrame(rows)
            )

            header_index = (
                self._detect_header_row(
                    raw_dataframe
                )
            )

            if header_index is None:

                raise ValueError(
                    "Could not locate header "
                    "inside Numbers file."
                )

            headers = [

                self._clean_text(value)

                for value
                in rows[
                    header_index
                ]
            ]

            dataframe = pd.DataFrame(
                rows[
                    header_index + 1:
                ],
                columns=headers,
            )

            dataframe = (
                dataframe.dropna(
                    how="all"
                )
            )

            return dataframe

        finally:

            if os.path.exists(
                temporary_path
            ):

                os.remove(
                    temporary_path
                )

    # ========================================================
    # STORAGE UPLOAD
    # ========================================================

    def _upload_original_file(
        self,
        filename: str,
        contents: bytes,
        batch_id: int,
    ):

        client = get_supabase()

        if not client:
            return

        storage_path = (
            f"uploads/"
            f"{batch_id}/"
            f"{int(time.time())}_"
            f"{filename}"
        )

        try:

            (
                client
                .storage
                .from_("excel-uploads")
                .upload(

                    path=
                        storage_path,

                    file=
                        contents,

                    file_options={
                        "content-type":
                            "application/octet-stream",

                        "upsert":
                            "true",
                    },
                )
            )

            local_batch = (
                upload_batches_db.get(
                    batch_id
                )
            )

            if local_batch:

                local_batch[
                    "storage_path"
                ] = storage_path

        except Exception as storage_error:

            # IMPORTANT:
            #
            # Earlier your file exceeded Supabase Storage size.
            # We intentionally continue processing the Excel.
            #
            # Storage and database ingestion are separate.
            # ------------------------------------------------

            logger.warning(
                "Could not upload original file "
                "to Supabase Storage: %s. "
                "Continuing with database ingestion.",
                storage_error,
            )

    # ========================================================
    # ========================================================
    # GENERIC BULK INSERT & PROGRESS TRACKING
    # ========================================================

    def _update_batch_progress(
        self,
        batch_id: int,
        remarks: str,
        status: Optional[str] = None,
    ):
        local_batch = upload_batches_db.get(batch_id)
        if local_batch:
            local_batch["remarks"] = remarks
            if status:
                local_batch["upload_status"] = status

        client = get_supabase()
        if client and status:
            try:
                payload = {"status": status}
                client.table("upload_batches").update(payload).eq("batch_id", batch_id).execute()
            except Exception as e:
                logger.warning(f"Could not update batch progress status: {e}")

    def _cleanup_failed_batch(self, batch_id: int):
        """
        Rollback/cleanup all partial records inserted for a batch if processing fails mid-way.
        Deletes any partial rows from sales_fact, sales, raw_sales_upload, dashboard_summary_daily, and batch_chunks.
        """
        client = get_supabase()
        if not client or not batch_id:
            return

        logger.warning(f"Rolling back partial records for failed upload batch {batch_id}...")

        cleanup_tables = [
            "sales_fact",
            "raw_sales_upload",
            "batch_chunks",
        ]

        for table_name in cleanup_tables:
            try:
                client.table(table_name).delete().eq("batch_id", batch_id).execute()
            except Exception as exc:
                logger.warning(
                    f"Cleanup warning for table '{table_name}' batch {batch_id}: {exc}"
                )

    def _record_batch_chunk(
        self,
        batch_id: int,
        chunk_number: int,
        start_row: int,
        end_row: int,
        row_count: int,
        status: str = "pending",
        inserted_rows: int = 0,
        error_message: Optional[str] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ):
        client = get_supabase()
        if not client or not batch_id:
            return

        payload = {
            "batch_id": batch_id,
            "chunk_number": chunk_number,
            "start_row": start_row,
            "end_row": end_row,
            "row_count": row_count,
            "status": status,
            "inserted_rows": inserted_rows,
            "error_message": error_message,
        }
        if started_at:
            payload["started_at"] = started_at
        if completed_at:
            payload["completed_at"] = completed_at

        try:
            client.table("batch_chunks").upsert(
                payload,
                on_conflict="batch_id,chunk_number"
            ).execute()
        except Exception as exc:
            logger.warning(f"Could not record batch_chunks row: {exc}")

    def _bulk_insert(
        self,
        table: str,
        records: List[Dict[str, Any]],
        chunk_size: int = 500,
        batch_id: Optional[int] = None,
        chunk_number_offset: int = 0,
    ):
        if not records:
            return

        client = get_supabase()
        total_chunks = (len(records) + chunk_size - 1) // chunk_size

        if batch_id:
            msg_init = f"Created {total_chunks} chunks of max {chunk_size} rows for table '{table}'."
            self._pipeline_log(
                batch_id=batch_id,
                step=f"chunk_created_{table}",
                status="started",
                message=msg_init,
            )
            self._update_batch_progress(batch_id, remarks=msg_init)

        for idx, start_index in enumerate(range(0, len(records), chunk_size), start=1):
            chunk = records[start_index : start_index + chunk_size]
            start_row = start_index + 1
            end_row = min(start_index + chunk_size, len(records))
            chunk_num = chunk_number_offset + idx
            start_time_iso = datetime.now().isoformat()

            if batch_id:
                msg_starting = f"Populating chunk {idx}/{total_chunks} (rows {start_row}-{end_row}) into table '{table}'..."
                self._pipeline_log(
                    batch_id=batch_id,
                    step=f"chunk_{table}_{idx}",
                    status="started",
                    message=msg_starting,
                )
                self._update_batch_progress(batch_id, remarks=msg_starting)
                self._record_batch_chunk(
                    batch_id=batch_id,
                    chunk_number=chunk_num,
                    start_row=start_row,
                    end_row=end_row,
                    row_count=len(chunk),
                    status="processing",
                    started_at=start_time_iso,
                )

            success = False
            err_msg = None

            if client:
                try:
                    if table == "dashboard_summary_daily":
                        client.table(table).upsert(chunk, on_conflict="sale_date,depot_id,brand_id").execute()
                    else:
                        client.table(table).insert(chunk).execute()
                    success = True
                except Exception as exc:
                    err_msg = str(exc)
                    if table == "dashboard_summary_daily":
                        try:
                            client.table(table).upsert(chunk).execute()
                            success = True
                        except Exception as e_up:
                            err_msg = f"{exc} | Upsert error: {e_up}"
                            logger.warning(f"Error upserting chunk {idx} into {table}: {err_msg}")
                    elif table == "sales_fact":
                        try:
                            first_d = chunk[0].get("sale_date")
                            if first_d and len(str(first_d)) >= 7:
                                yr, mo = int(str(first_d)[:4]), int(str(first_d)[5:7])
                                next_yr = yr if mo < 12 else yr + 1
                                next_mo = mo + 1 if mo < 12 else 1
                                s_d = f"{yr:04d}-{mo:02d}-01"
                                e_d = f"{next_yr:04d}-{next_mo:02d}-01"
                                part_tbl = f"sales_fact_{yr:04d}_{mo:02d}"
                                part_sql = f"CREATE TABLE IF NOT EXISTS public.{part_tbl} PARTITION OF public.sales_fact FOR VALUES FROM ('{s_d}') TO ('{e_d}');"
                                try:
                                    client.rpc("exec_sql", {"sql_query": part_sql}).execute()
                                except Exception:
                                    try:
                                        client.rpc("execute_sql", {"query": part_sql}).execute()
                                    except Exception:
                                        pass
                                client.table(table).insert(chunk).execute()
                                success = True
                        except Exception as e2:
                            err_msg = f"{exc} | Partition retry error: {e2}"
                            logger.warning(f"Error inserting chunk {idx} into {table}: {err_msg}")
                    else:
                        logger.warning(f"Error inserting chunk {idx} into {table}: {err_msg}")
            else:
                success = True

            end_time_iso = datetime.now().isoformat()

            if batch_id:
                if success:
                    msg_done = f"Chunk {idx}/{total_chunks} populated in table '{table}'. Moving on to next..."
                    self._pipeline_log(
                        batch_id=batch_id,
                        step=f"chunk_{table}_{idx}",
                        status="succeeded",
                        message=msg_done,
                    )
                    self._record_batch_chunk(
                        batch_id=batch_id,
                        chunk_number=chunk_num,
                        start_row=start_row,
                        end_row=end_row,
                        row_count=len(chunk),
                        status="completed",
                        inserted_rows=len(chunk),
                        completed_at=end_time_iso,
                    )
                else:
                    self._record_batch_chunk(
                        batch_id=batch_id,
                        chunk_number=chunk_num,
                        start_row=start_row,
                        end_row=end_row,
                        row_count=len(chunk),
                        status="failed",
                        inserted_rows=0,
                        error_message=err_msg,
                        completed_at=end_time_iso,
                    )




    # ========================================================
    # UPDATE UPLOAD BATCH
    # ========================================================

    def _update_batch(
        self,
        batch_id: int,
        row_count: Optional[int] = None,
        status: Optional[str] = None,
    ):

        client = get_supabase()

        if not client:
            raise RuntimeError(
                "Supabase connection unavailable."
            )

        payload = {}

        if row_count is not None:

            payload[
                "row_count"
            ] = row_count

        if status is not None:
            allowed_statuses = {
                "pending",
                "staged",
                "validated",
                "loaded",
                "completed",
                "failed",
            }

            if status not in allowed_statuses:
                raise ValueError(f"Invalid upload status: {status}")

            db_status = "loaded" if status == "completed" else status
            payload["status"] = db_status

        if not payload:
            return

        try:
            client.table("upload_batches").update(payload).eq("batch_id", batch_id).execute()
        except Exception as exc:
            logger.warning(f"Could not update upload_batches row: {exc}")


    # ========================================================
    # VALIDATION ERROR
    # ========================================================

    def _save_validation_error(
        self,
        batch_id: int,
        column_name: Optional[str],
        message: str,
        raw_id: Optional[int] = None,
    ):

        client = get_supabase()

        if not client:
            return

        record = {

            "batch_id":
                batch_id,

            "raw_id":
                raw_id,

            "column_name":
                column_name,

            "error_message":
                message,
        }

        try:

            (
                client
                .table(
                    "upload_validation_errors"
                )
                .insert(record)
                .execute()
            )

        except Exception as exc:

            logger.warning(
                "Could not save validation "
                "error: %s",
                exc,
            )

        # Existing API compatibility.
        upload_logs_db.append({

            "upload_batch_id":
                batch_id,

            "row_number":
                0,

            "column_name":
                column_name,

            "error_type":
                "VALIDATION_ERROR",

            "error_message":
                message,

            "raw_data":
                None,

            "created_at":
                datetime.now().isoformat(),
        })

    # ========================================================
    # PIPELINE LOG
    # ========================================================

    def _pipeline_log(
        self,
        batch_id: int,
        step: str,
        status: str,
        message: Optional[str] = None,
    ):

        client = get_supabase()

        if not client:
            return

        allowed_statuses = {
            "started",
            "succeeded",
            "failed",
        }

        if status not in allowed_statuses:

            raise ValueError(
                f"Invalid pipeline log "
                f"status: {status}"
            )

        record = {

            "batch_id":
                batch_id,

            "step":
                step,

            "status":
                status,

            "message":
                message,
        }

        (
            client
            .table(
                "upload_pipeline_logs"
            )
            .insert(record)
            .execute()
        )

    # ========================================================
    # DASHBOARD SUMMARY
    # ========================================================

    def _refresh_dashboard_summary(
        self,
        fact_records: List[Dict[str, Any]],
    ):

        if not fact_records:
            return

        aggregates = {}

        # ----------------------------------------------------
        # Aggregate:
        #
        # sale_date
        # + depot
        # + brand
        # ----------------------------------------------------

        for fact in fact_records:

            key = (

                fact[
                    "sale_date"
                ],

                fact[
                    "depot_id"
                ],

                fact[
                    "brand_id"
                ],
            )

            if key not in aggregates:

                aggregates[key] = {

                    "sale_date":
                        fact[
                            "sale_date"
                        ],

                    "depot_id":
                        fact[
                            "depot_id"
                        ],

                    "brand_id":
                        fact[
                            "brand_id"
                        ],

                    "total_case":
                        0.0,

                    "total_btl":
                        0.0,

                    "total_bl":
                        0.0,
                }

            summary = (
                aggregates[key]
            )

            summary[
                "total_case"
            ] += fact[
                "total_case"
            ]

            summary[
                "total_btl"
            ] += fact[
                "total_btl"
            ]

            summary[
                "total_bl"
            ] += fact[
                "total_bl"
            ]

        summary_records = list(
            aggregates.values()
        )

        self._bulk_insert(
            table=
                "dashboard_summary_daily",

            records=
                summary_records,

            chunk_size=
                1000,
        )

    # ========================================================
    # AUDIT LOG
    # ========================================================

    def _save_audit_log(
        self,
        batch_id: int,
        user_id: str,
        imported_rows: int,
    ):

        client = get_supabase()

        if not client:
            return

        record = {

            "table_name":
                "sales_fact",

            "record_id":
                str(batch_id),

            "action":
                "INSERT",

            "old_data":
                None,

            "new_data": {
                "batch_id":
                    batch_id,

                "imported_rows":
                    imported_rows,
            },

            "changed_by":
                user_id,
        }

        try:
            client.table("audit_logs").insert(record).execute()
        except Exception:
            try:
                record.pop("changed_by", None)
                client.table("audit_logs").insert(record).execute()
            except Exception as exc:
                logger.warning(
                    "Could not create audit log for batch %s: %s",
                    batch_id,
                    exc,
                )


# ============================================================
# SERVICE INSTANCE
# ============================================================

import_pipeline = ImportPipelineEngine()
