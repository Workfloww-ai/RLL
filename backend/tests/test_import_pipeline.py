import pytest
from io import BytesIO
import pandas as pd
from fastapi import UploadFile
from backend.services.import_pipeline import import_pipeline, upload_batches_db

@pytest.mark.asyncio
async def test_process_excel_file_upload():
    # Create sample DataFrame matching mandatory columns
    df = pd.DataFrame({
        "Date": ["2026-07-29", "2026-07-29"],
        "Depot Code": ["DEP_JPR_01", "DEP_JPR_01"],
        "License Number": ["LIC-2026-001", "LIC-2026-002"],
        "Brand Code": ["ROYAL_STAG", "ROYAL_STAG"],
        "Packing Size": ["750ml Bottle", "750ml Bottle"],
        "Cases": [10.0, 20.0],
        "Bottles": [120.0, 240.0],
        "Bulk Liters": [90.0, 180.0],
        "Sale Value": [50000.0, 100000.0]
    })
    
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    excel_buffer.seek(0)
    
    upload_file = UploadFile(filename="test_sales_batch.xlsx", file=excel_buffer)
    user_id = "00000000-0000-0000-0000-000000000001"
    
    res = await import_pipeline.process_file_upload(upload_file, user_id)
    assert res["upload_status"] == "completed"
    assert res["total_rows"] == 2
    assert res["imported_rows"] == 2
    assert res["duplicate_rows"] == 0
    assert res["failed_rows"] == 0
