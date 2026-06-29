from collections.abc import Sequence
from pathlib import Path

import pandas as pd


def dataframe_to_latex(dataframe: pd.DataFrame) -> str:
    """Convert a non-empty DataFrame into a plain LaTeX table."""
    if dataframe.empty:
        raise ValueError(
            "Input table is empty. Please provide a CSV or XLSX file with at least one data row and one column."
        )

    column_names = [str(column_name) for column_name in dataframe.columns]
    column_alignment = "c" * len(column_names)
    data_rows = [
        _format_latex_row(row_values)
        for row_values in dataframe.itertuples(index=False, name=None)
    ]

    lines = [
        r"\begin{table}",
        r"\centering",
        rf"\begin{{tabular}}{{{column_alignment}}}",
        _format_latex_row(column_names),
        *data_rows,
        r"\end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(lines)


def read_table_file(file_path: str | Path) -> pd.DataFrame:
    """Read a supported table file into a DataFrame."""
    path = Path(file_path)
    file_extension = path.suffix.lower()

    if file_extension == ".csv":
        return pd.read_csv(path)

    if file_extension == ".xlsx":
        return pd.read_excel(path, engine="openpyxl")

    raise ValueError("Unsupported file type. Please select a CSV or XLSX file.")


def _format_latex_row(values: Sequence[object]) -> str:
    cells = [_format_latex_cell(value) for value in values]
    return f"{' & '.join(cells)} \\\\"


def _format_latex_cell(value: object) -> str:
    if pd.isna(value):
        return ""

    return str(value)
