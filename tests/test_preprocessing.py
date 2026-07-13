"""Tests for preprocessing.py — pure DataFrame transformations."""

import pandas as pd

from preprocessing import (
    drop_duplicate_rows,
    drop_empty_rows_and_columns,
    transpose_dataframe,
)

# ---------------------------------------------------------------------------
# transpose_dataframe
# ---------------------------------------------------------------------------


def test_transpose_dataframe_with_2x2_produces_correct_columns_and_row() -> None:
    # Arrange
    dataframe = pd.DataFrame({"A": [1, 3], "B": [2, 4]})

    # Act
    result = transpose_dataframe(dataframe)

    # Assert — columns become ["A","1","3"], single row ["B","2","4"]
    assert list(result.columns) == ["A", "1", "3"]
    assert result.shape == (1, 3)
    row_values = result.iloc[0].tolist()
    assert row_values == ["B", "2", "4"]


def test_transpose_dataframe_round_trip_preserves_values() -> None:
    # Arrange
    dataframe = pd.DataFrame({"A": [1, 3], "B": [2, 4]})

    # Act — transpose twice
    once = transpose_dataframe(dataframe)
    twice = transpose_dataframe(once)

    # Assert — values and labels match original (as strings)
    assert list(twice.columns) == [str(c) for c in dataframe.columns]
    for col in dataframe.columns:
        original_vals = [str(v) for v in dataframe[col].tolist()]
        round_trip_vals = [str(v) for v in twice[str(col)].tolist()]
        assert original_vals == round_trip_vals


def test_transpose_dataframe_does_not_mutate_input() -> None:
    # Arrange
    dataframe = pd.DataFrame({"X": [10], "Y": [20]})
    original_columns = list(dataframe.columns)

    # Act
    transpose_dataframe(dataframe)

    # Assert — input unchanged
    assert list(dataframe.columns) == original_columns


def test_transpose_dataframe_preserves_missing_cells_as_empty_strings() -> None:
    # Arrange
    dataframe = pd.DataFrame({"A": ["value"], "B": [None]})

    # Act
    result = transpose_dataframe(dataframe)

    # Assert
    assert result.iloc[0].tolist() == ["B", ""]
    assert "nan" not in result.to_string().lower()


# ---------------------------------------------------------------------------
# drop_empty_rows_and_columns
# ---------------------------------------------------------------------------


def test_drop_empty_rows_and_columns_removes_all_empty_row_and_column() -> None:
    # Arrange — row index 1 is all-NaN/empty, column "Empty" is all-NaN
    dataframe = pd.DataFrame(
        {
            "A": ["x", "", "z"],
            "B": ["1", "", "3"],
            "Empty": [None, None, None],
        }
    )

    # Act
    result = drop_empty_rows_and_columns(dataframe)

    # Assert — row 1 and column "Empty" removed
    assert "Empty" not in result.columns
    assert result.shape == (2, 2)
    assert result["A"].tolist() == ["x", "z"]


def test_drop_empty_rows_and_columns_treats_empty_strings_as_empty() -> None:
    # Arrange — row 0 is all empty strings
    dataframe = pd.DataFrame({"A": ["", "data"], "B": ["", "value"]})

    # Act
    result = drop_empty_rows_and_columns(dataframe)

    # Assert
    assert result.shape == (1, 2)
    assert result["A"].iloc[0] == "data"


def test_drop_empty_rows_and_columns_does_not_mutate_input() -> None:
    # Arrange
    dataframe = pd.DataFrame({"A": ["x", None], "B": [None, None]})
    original_shape = dataframe.shape

    # Act
    drop_empty_rows_and_columns(dataframe)

    # Assert
    assert dataframe.shape == original_shape


# ---------------------------------------------------------------------------
# drop_duplicate_rows
# ---------------------------------------------------------------------------


def test_drop_duplicate_rows_removes_duplicate_and_keeps_first() -> None:
    # Arrange
    dataframe = pd.DataFrame({"A": [1, 2, 1], "B": [10, 20, 10]})

    # Act
    result = drop_duplicate_rows(dataframe)

    # Assert
    assert result.shape == (2, 2)
    assert result["A"].tolist() == [1, 2]
    assert result["B"].tolist() == [10, 20]


def test_drop_duplicate_rows_resets_index() -> None:
    # Arrange
    dataframe = pd.DataFrame({"A": [1, 1, 2]})

    # Act
    result = drop_duplicate_rows(dataframe)

    # Assert
    assert list(result.index) == [0, 1]


def test_drop_duplicate_rows_does_not_mutate_input() -> None:
    # Arrange
    dataframe = pd.DataFrame({"A": [1, 1]})
    original_len = len(dataframe)

    # Act
    drop_duplicate_rows(dataframe)

    # Assert
    assert len(dataframe) == original_len
