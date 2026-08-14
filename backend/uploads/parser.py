import io
import os
import tempfile

import pandas as pd
# pyrefly: ignore [missing-import]
from fastapi import UploadFile
# pyrefly: ignore [missing-import]
from numbers_parser import Document
# pyrefly: ignore [missing-import]
from backend.uploads.constants import REQUIRED_HEADERS


async def parse_excel(file: UploadFile) -> pd.DataFrame:
    """
    Reads an uploaded Excel (.xlsx, .xls) or Apple Numbers (.numbers)
    file into a pandas DataFrame.
    """

    contents = await file.read()
    filename = file.filename.lower() if file.filename else ""

    if filename.endswith(".numbers"):
        with tempfile.NamedTemporaryFile(suffix=".numbers", delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        try:
            doc = Document(tmp_path)
            sheets = doc.sheets

            if not sheets or not sheets[0].tables:
                return pd.DataFrame()

            table = sheets[0].tables[0]
            data = table.rows(values_only=True)

            if not data:
                return pd.DataFrame()

            headers = [
                str(h).strip() if h is not None else ""
                for h in data[0]
            ]

            # If row 0 contains no header text (all empty strings),
            # treat all rows as data.
            if not any(headers):
                cols = [f"Column {i + 1}" for i in range(len(data[0]))]
                dataframe = pd.DataFrame(data, columns=cols)
            else:
                dataframe = pd.DataFrame(data[1:], columns=headers)

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    else:
        # Read the sheet without assuming any header
        preview = pd.read_excel(
            io.BytesIO(contents),
            header=None,
            engine="openpyxl" if filename.endswith(".xlsx") else None,
        )

        header_row = None

        for idx, row in preview.iterrows():
            values = {
                str(value).strip().upper()
                for value in row
                if pd.notna(value)
            }

            matches = len(REQUIRED_HEADERS.intersection(values))

            if matches >= 3:
                header_row = idx
                break

        if header_row is None:
            raise ValueError(
                "Could not detect the header row in the uploaded Excel file."
            )

        # Read the Excel again using the detected header row
        dataframe = pd.read_excel(
            io.BytesIO(contents),
            header=header_row,
            engine="openpyxl" if filename.endswith(".xlsx") else None,
        )

    # Clean column names
    dataframe.columns = [str(col).strip() for col in dataframe.columns]

    # Remove completely empty rows
    dataframe = dataframe.dropna(how="all")

    # Remove completely empty columns
    dataframe = dataframe.dropna(axis=1, how="all")

    # Replace remaining NaN values with empty strings
    dataframe = dataframe.fillna("")

    return dataframe