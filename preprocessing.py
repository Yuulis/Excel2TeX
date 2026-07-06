"""Pure preprocessing functions for DataFrames.

Every function returns a NEW DataFrame — inputs are never mutated.
"""

import pandas as pd

# Valid case options for apply_text_case.
_VALID_CASES = {"upper", "lower", "capitalize"}


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
    new_columns = [str(cell) for cell in transposed[0]]
    new_data = [[str(cell) for cell in row] for row in transposed[1:]]
    return pd.DataFrame(new_data, columns=new_columns)


def apply_text_case(dataframe: pd.DataFrame, case: str) -> pd.DataFrame:
    """Apply a text-case transformation to string/object data cells.

    Numeric and NaN cells are left unchanged.  Column headers are preserved.

    Args:
        dataframe: Source data.
        case: One of ``"upper"``, ``"lower"``, or ``"capitalize"``
              (title-case each word via ``str.title()``).

    Raises:
        ValueError: If *case* is not one of the valid options.
    """
    if case not in _VALID_CASES:
        raise ValueError(
            f"Invalid case '{case}'. Must be one of: {', '.join(sorted(_VALID_CASES))}"
        )

    result = dataframe.copy()

    case_fn_map: dict[str, callable] = {
        "upper": str.upper,
        "lower": str.lower,
        "capitalize": str.title,
    }
    fn = case_fn_map[case]

    for col in result.columns:
        if result[col].dtype.kind == "O":
            result[col] = result[col].apply(
                lambda x, _fn=fn: _fn(x) if isinstance(x, str) else x
            )

    return result


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
