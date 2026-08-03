from unittest import result

from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.uploads.importer import process_dataframe
from backend.uploads.importer import process_dataframe

try:
    from backend.uploads.parser import parse_excel
except ModuleNotFoundError:
    from uploads.parser import parse_excel

router = APIRouter(
    prefix="/upload",
    tags=["Excel Upload"]
)


@router.post("/upload")
async def upload_excel(file: UploadFile = File(...)):
    filename_lower = file.filename.lower() if file.filename else ""
    if not filename_lower.endswith((".xlsx", ".xls", ".numbers")):
        raise HTTPException(
            status_code=400,
            detail="Only Excel (.xlsx, .xls) and Apple Numbers (.numbers) files are allowed."
        )

    dataframe = await parse_excel(file)

    result = await process_dataframe(
        dataframe=dataframe,
        table_name="sales"  
    )

    return {
        "filename": file.filename,
        "columns": list(dataframe.columns),
        **result
    }