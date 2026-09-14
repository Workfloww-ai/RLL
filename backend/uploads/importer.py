import time
from typing import Iterator

import pandas as pd

from backend.db.client import get_supabase

# Configurable chunk size
CHUNK_SIZE = 5000


def dataframe_chunks(
    dataframe: pd.DataFrame,
    chunk_size: int = CHUNK_SIZE
) -> Iterator[pd.DataFrame]:
    """
    Yield DataFrame chunks.
    """

    for start in range(0, len(dataframe), chunk_size):
        yield dataframe.iloc[start:start + chunk_size]


async def process_dataframe(
    dataframe: pd.DataFrame,
    table_name: str,
):
    """
    Split dataframe into chunks and upload each chunk.
    """

    supabase = get_supabase()

    total_rows = len(dataframe)

    inserted_rows = 0

    chunk_number = 1

    start_time = time.time()

    for chunk in dataframe_chunks(dataframe):

        print(
            f"Uploading chunk {chunk_number} "
            f"({len(chunk)} rows)"
        )

        records = chunk.to_dict(orient="records")

        response = (
            supabase
            .table(table_name)
            .insert(records)
            .execute()
        )

        inserted_rows += len(records)

        chunk_number += 1

    return {
        "rows": total_rows,
        "chunks_processed": chunk_number - 1,
        "rows_inserted": inserted_rows,
        "processing_time": round(time.time() - start_time, 2)
    }


async def process_upload_batch_chunked(
    batch_id: int,
    file_path: str,
    load_type: str = "daily",
    covers_start: str = None,
    covers_end: str = None,
    chunk_size: int = 2500,
):
    """
    Executes the standard enterprise import pipeline for a given saved file path and batch_id.
    """
    import os
    from backend.uploads.service import import_pipeline
    try:
        with open(file_path, "rb") as f:
            contents = f.read()
        filename = os.path.basename(file_path)
        import_pipeline.process_file_upload_async(
            filename=filename,
            contents=contents,
            user_id="system",
            batch_id=batch_id,
        )
    except Exception as e:
        print(f"Error in process_upload_batch_chunked for batch {batch_id}: {e}")