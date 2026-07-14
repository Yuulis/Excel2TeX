"""Pure preprocessing functions for DataFrames.

Every function returns a NEW DataFrame — inputs are never mutated.
"""

import pandas as pd


def transpose_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Transpose the entire grid, treating column headers as the first row.

    The column headers become the first column of the transposed result, and
    the first column of the original becomes the new column headers.

    Example:
        columns [A, B], rows [[1,2],[3,4]]
        -> columns ["A","1","3"], single row ["B","2","4"]
    """
    full_matrix = [list(dataframe.columns)] + dataframe.astype(object).values.tolist()
    transposed = list(map(list, zip(*full_matrix, strict=False)))
    new_columns = [_cell_to_text(cell) for cell in transposed[0]]
    new_data = [[_cell_to_text(cell) for cell in row] for row in transposed[1:]]
    return pd.DataFrame(new_data, columns=new_columns)


def _cell_to_text(value: object) -> str:
    """Convert a table value to text while preserving missing cells as empty."""
    return "" if pd.isna(value) else str(value)


def drop_empty_rows_and_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Drop rows and columns where ALL cells are NaN or empty string.

    Empty strings are treated as missing for the purpose of this operation,
    but remaining empty strings in non-dropped rows/columns are preserved.
    """
    result = dataframe.copy()
    # Treat empty strings as NA for the drop decision.
    marker = result.replace("", pd.NA)
    rows_to_keep = marker.dropna(how="all").index
    cols_to_keep = marker.dropna(how="all", axis=1).columns
    return result.loc[rows_to_keep, cols_to_keep].reset_index(drop=True)


def drop_duplicate_rows(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Drop fully-duplicate data rows, keeping the first occurrence."""
    return dataframe.drop_duplicates(keep="first").reset_index(drop=True)
