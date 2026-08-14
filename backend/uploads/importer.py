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