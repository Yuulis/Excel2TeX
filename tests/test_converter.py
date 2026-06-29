from pathlib import Path

import pandas as pd
import pytest

from converter import dataframe_to_latex, read_table_file


def test_dataframe_to_latex_with_2x2_dataframe_contains_default_table_parts() -> None:
    # Arrange
    dataframe = pd.DataFrame(
        {
            "A": [1, 3],
            "B": [2, 4],
        }
    )

    # Act
    latex_code = dataframe_to_latex(dataframe)

    # Assert
    assert r"\begin{table}" in latex_code
    assert r"\begin{tabular}{cc}" in latex_code
    assert r"A & B \\" in latex_code
    assert r"1 & 2 \\" in latex_code
    assert r"3 & 4 \\" in latex_code


def test_dataframe_to_latex_with_empty_dataframe_raises_clear_error() -> None:
    # Arrange
    dataframe = pd.DataFrame()

    # Act / Assert
    with pytest.raises(ValueError, match="Input table is empty"):
        dataframe_to_latex(dataframe)


def test_dataframe_to_latex_with_three_columns_uses_matching_structure() -> None:
    # Arrange
    dataframe = pd.DataFrame(
        [
            ["alpha", "beta", "gamma"],
        ],
        columns=["First", "Second", "Third"],
    )

    # Act
    latex_code = dataframe_to_latex(dataframe)
    latex_lines = latex_code.splitlines()

    # Assert
    assert latex_lines == [
        r"\begin{table}",
        r"\centering",
        r"\begin{tabular}{ccc}",
        r"First & Second & Third \\",
        r"alpha & beta & gamma \\",
        r"\end{tabular}",
        r"\end{table}",
    ]


def test_read_table_file_with_csv_path_returns_dataframe(tmp_path: Path) -> None:
    # Arrange
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("A,B\n1,2\n3,4\n", encoding="utf-8")

    # Act
    dataframe = read_table_file(csv_path)

    # Assert
    assert dataframe.to_dict(orient="list") == {"A": [1, 3], "B": [2, 4]}
