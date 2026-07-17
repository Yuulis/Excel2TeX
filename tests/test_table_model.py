"""Tests for table_model: Cell, CellAlignment, TableGrid, and dataframe_to_grid."""

import pandas as pd
import pytest

from table_model import (
    Cell,
    CellAlignment,
    TableGrid,
    clone_grid,
    dataframe_to_grid,
    grid_to_dataframe,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_grid() -> TableGrid:
    """3x3 grid with header row (A, B, C) and two data rows."""
    return dataframe_to_grid(
        pd.DataFrame({"A": [1, 4], "B": [2, 5], "C": [3, 6]}),
        include_header=True,
    )


def _small_grid() -> TableGrid:
    """2x2 grid without header for merge tests."""
    grid = TableGrid(
        rows=[
            [Cell(content="a"), Cell(content="b")],
            [Cell(content="c"), Cell(content="d")],
        ],
        has_header=False,
    )
    return grid


# ---------------------------------------------------------------------------
# dataframe_to_grid
# ---------------------------------------------------------------------------


def test_dataframe_to_grid_with_header_includes_column_names() -> None:
    # Arrange
    df = pd.DataFrame({"X": [10], "Y": [20]})

    # Act
    grid = dataframe_to_grid(df, include_header=True)

    # Assert
    assert grid.num_rows == 2
    assert grid.num_cols == 2
    assert grid.has_header is True
    assert grid.rows[0][0].content == "X"
    assert grid.rows[0][1].content == "Y"
    assert grid.rows[1][0].content == "10"
    assert grid.rows[1][1].content == "20"


def test_dataframe_to_grid_without_header_excludes_column_names() -> None:
    # Arrange
    df = pd.DataFrame({"X": [10], "Y": [20]})

    # Act
    grid = dataframe_to_grid(df, include_header=False)

    # Assert
    assert grid.num_rows == 1
    assert grid.has_header is False
    assert grid.rows[0][0].content == "10"


def test_dataframe_to_grid_with_nan_converts_to_empty_string() -> None:
    # Arrange
    df = pd.DataFrame({"A": [None, 1.0]})

    # Act
    grid = dataframe_to_grid(df)

    # Assert — NaN becomes ""
    assert grid.rows[1][0].content == ""
    assert grid.rows[2][0].content == "1.0"


def test_grid_to_dataframe_uses_current_edited_content() -> None:
    # Arrange
    grid = dataframe_to_grid(pd.DataFrame({"Name": ["Alice", "Bob"]}))
    grid.set_content(1, 0, "Carol")

    # Act
    dataframe = grid_to_dataframe(grid)

    # Assert
    assert dataframe["Name"].tolist() == ["Carol", "Bob"]


def test_grid_to_dataframe_preserves_empty_cells() -> None:
    # Arrange
    grid = TableGrid(
        rows=[
            [Cell(content="A"), Cell(content="B")],
            [Cell(content="value"), Cell(content="")],
        ]
    )

    # Act
    dataframe = grid_to_dataframe(grid)

    # Assert
    assert dataframe.iloc[0].tolist() == ["value", ""]


def test_clone_grid_preserves_metadata_and_is_independent() -> None:
    grid = _small_grid()
    grid.set_alignment(0, 0, CellAlignment.RIGHT)
    grid.merge_cells(0, 0, 2, 2)

    cloned = clone_grid(grid)
    cloned.set_content(0, 0, "changed")
    cloned.split_cell(0, 0)

    assert cloned is not grid
    assert cloned.rows[0][0] is not grid.rows[0][0]
    assert grid.get_cell(0, 0).content == "a"
    assert grid.get_cell(0, 0).rowspan == 2
    assert grid.get_cell(0, 0).colspan == 2
    assert grid.get_cell(0, 0).alignment == CellAlignment.RIGHT
    assert grid.get_cell(1, 1).is_covered


def test_drop_operations_can_use_current_grid_content() -> None:
    # Arrange
    from preprocessing import drop_duplicate_rows, drop_empty_rows_and_columns

    grid = dataframe_to_grid(pd.DataFrame({"A": ["first", "second"], "B": ["x", "y"]}))
    grid.set_content(2, 0, "first")
    grid.set_content(2, 1, "x")
    grid.insert_row(3)

    # Act
    current = grid_to_dataframe(grid)
    without_empty = drop_empty_rows_and_columns(current)
    without_duplicates = drop_duplicate_rows(without_empty)

    # Assert
    assert without_duplicates.to_dict(orient="records") == [{"A": "first", "B": "x"}]


# ---------------------------------------------------------------------------
# get_cell / set_content / set_alignment
# ---------------------------------------------------------------------------


def test_get_cell_returns_correct_cell() -> None:
    # Arrange
    grid = _simple_grid()

    # Act
    cell = grid.get_cell(0, 1)

    # Assert
    assert cell.content == "B"


def test_set_content_updates_cell_content() -> None:
    # Arrange
    grid = _simple_grid()

    # Act
    grid.set_content(1, 0, "new")

    # Assert
    assert grid.get_cell(1, 0).content == "new"


def test_set_content_on_covered_cell_raises_value_error() -> None:
    # Arrange
    grid = _small_grid()
    grid.merge_cells(0, 0, 1, 2)  # merge (0,0)-(0,1)

    # Act / Assert
    with pytest.raises(ValueError, match="covered"):
        grid.set_content(0, 1, "fail")


def test_set_alignment_updates_cell_alignment() -> None:
    # Arrange
    grid = _simple_grid()

    # Act
    grid.set_alignment(1, 1, CellAlignment.RIGHT)

    # Assert
    assert grid.get_cell(1, 1).alignment == CellAlignment.RIGHT


def test_set_alignment_on_covered_cell_raises_value_error() -> None:
    # Arrange
    grid = _small_grid()
    grid.merge_cells(0, 0, 2, 1)  # vertical merge

    # Act / Assert
    with pytest.raises(ValueError, match="covered"):
        grid.set_alignment(1, 0, CellAlignment.LEFT)


# ---------------------------------------------------------------------------
# merge_cells
# ---------------------------------------------------------------------------


def test_merge_cells_horizontal_creates_covered_cells() -> None:
    # Arrange
    grid = _simple_grid()  # 3 rows x 3 cols

    # Act — merge header columns 0-1
    grid.merge_cells(0, 0, 1, 2)

    # Assert
    anchor = grid.get_cell(0, 0)
    assert anchor.colspan == 2
    assert anchor.rowspan == 1
    assert not anchor.is_covered

    covered = grid.get_cell(0, 1)
    assert covered.is_covered
    assert covered.anchor_row == 0
    assert covered.anchor_col == 0
    assert covered.content == ""

    # Unaffected cell
    assert not grid.get_cell(0, 2).is_covered


def test_merge_cells_vertical_creates_covered_cells() -> None:
    # Arrange
    grid = _simple_grid()

    # Act — merge rows 0-1 in column 0
    grid.merge_cells(0, 0, 2, 1)

    # Assert
    anchor = grid.get_cell(0, 0)
    assert anchor.rowspan == 2
    assert anchor.colspan == 1

    covered = grid.get_cell(1, 0)
    assert covered.is_covered
    assert covered.anchor_row == 0
    assert covered.anchor_col == 0


def test_merge_cells_2x2_creates_four_cells() -> None:
    # Arrange
    grid = _simple_grid()

    # Act — merge (0,0)-(1,1) as 2x2
    grid.merge_cells(0, 0, 2, 2)

    # Assert
    anchor = grid.get_cell(0, 0)
    assert anchor.colspan == 2
    assert anchor.rowspan == 2
    for r, c in [(0, 1), (1, 0), (1, 1)]:
        cell = grid.get_cell(r, c)
        assert cell.is_covered
        assert cell.anchor_row == 0
        assert cell.anchor_col == 0


# ---------------------------------------------------------------------------
# merge validation errors
# ---------------------------------------------------------------------------


def test_merge_cells_single_cell_raises_value_error() -> None:
    grid = _simple_grid()
    with pytest.raises(ValueError, match="more than one cell"):
        grid.merge_cells(0, 0, 1, 1)


def test_merge_cells_zero_span_raises_value_error() -> None:
    grid = _simple_grid()
    with pytest.raises(ValueError, match=">= 1"):
        grid.merge_cells(0, 0, 0, 2)


def test_merge_cells_negative_origin_raises_value_error() -> None:
    grid = _simple_grid()
    with pytest.raises(ValueError, match="non-negative"):
        grid.merge_cells(-1, 0, 1, 2)


def test_merge_cells_out_of_bounds_rows_raises_value_error() -> None:
    grid = _simple_grid()
    with pytest.raises(ValueError, match="beyond grid rows"):
        grid.merge_cells(0, 0, 10, 1)


def test_merge_cells_out_of_bounds_cols_raises_value_error() -> None:
    grid = _simple_grid()
    with pytest.raises(ValueError, match="beyond grid columns"):
        grid.merge_cells(0, 0, 1, 10)


def test_merge_cells_overlapping_existing_covered_raises_value_error() -> None:
    # Arrange
    grid = _simple_grid()
    grid.merge_cells(0, 0, 1, 2)  # (0,1) is now covered

    # Act / Assert — new merge overlaps with existing covered cell
    with pytest.raises(ValueError, match="already part of a merge"):
        grid.merge_cells(0, 1, 2, 1)


def test_merge_cells_overlapping_existing_anchor_raises_value_error() -> None:
    # Arrange
    grid = _simple_grid()
    grid.merge_cells(0, 0, 1, 2)  # anchor at (0,0) with colspan=2

    # Act / Assert — new merge includes existing anchor
    with pytest.raises(ValueError, match="merge anchor"):
        grid.merge_cells(0, 0, 2, 3)


# ---------------------------------------------------------------------------
# split_cell
# ---------------------------------------------------------------------------


def test_split_cell_restores_individual_cells() -> None:
    # Arrange
    grid = _simple_grid()
    grid.merge_cells(0, 0, 2, 2)

    # Act
    grid.split_cell(0, 0)

    # Assert
    anchor = grid.get_cell(0, 0)
    assert anchor.colspan == 1
    assert anchor.rowspan == 1
    for r, c in [(0, 1), (1, 0), (1, 1)]:
        cell = grid.get_cell(r, c)
        assert not cell.is_covered
        assert cell.anchor_row is None
        assert cell.anchor_col is None


def test_split_cell_on_non_merged_cell_raises_value_error() -> None:
    grid = _simple_grid()
    with pytest.raises(ValueError, match="not merged"):
        grid.split_cell(0, 0)


# ---------------------------------------------------------------------------
# insert_row
# ---------------------------------------------------------------------------


def test_insert_row_at_end_appends_empty_row() -> None:
    # Arrange
    grid = _small_grid()  # 2x2
    original_rows = grid.num_rows

    # Act
    grid.insert_row(grid.num_rows)

    # Assert
    assert grid.num_rows == original_rows + 1
    assert grid.get_cell(2, 0).content == ""
    assert grid.get_cell(2, 1).content == ""


def test_insert_row_inside_vertical_merge_extends_rowspan() -> None:
    # Arrange
    grid = TableGrid(
        rows=[
            [Cell(content="A"), Cell(content="B")],
            [Cell(content="C"), Cell(content="D")],
            [Cell(content="E"), Cell(content="F")],
        ],
        has_header=False,
    )
    grid.merge_cells(0, 0, 3, 1)  # anchor at (0,0) rowspan=3

    # Act — insert inside the merge
    grid.insert_row(2)

    # Assert
    assert grid.num_rows == 4
    anchor = grid.get_cell(0, 0)
    assert anchor.rowspan == 4  # extended
    assert grid.get_cell(2, 0).is_covered  # new row is covered
    assert grid.get_cell(2, 0).anchor_row == 0


def test_insert_row_after_merge_no_adjustment() -> None:
    # Arrange
    grid = _small_grid()
    grid.merge_cells(0, 0, 2, 1)  # rowspan=2, rows 0-1

    # Act — insert after the merge
    grid.insert_row(2)

    # Assert
    anchor = grid.get_cell(0, 0)
    assert anchor.rowspan == 2  # unchanged
    assert not grid.get_cell(2, 0).is_covered


def test_insert_row_at_beginning_shifts_anchor_references() -> None:
    # Arrange
    grid = _small_grid()
    grid.merge_cells(0, 0, 2, 1)  # anchor (0,0), covered (1,0)

    # Act
    grid.insert_row(0)

    # Assert — original anchor shifted to row 1
    assert grid.num_rows == 3
    assert not grid.get_cell(0, 0).is_covered  # new empty row
    anchor = grid.get_cell(1, 0)
    assert anchor.rowspan == 2
    covered = grid.get_cell(2, 0)
    assert covered.is_covered
    assert covered.anchor_row == 1


# ---------------------------------------------------------------------------
# insert_col
# ---------------------------------------------------------------------------


def test_insert_col_at_end_appends_empty_column() -> None:
    # Arrange
    grid = _small_grid()

    # Act
    grid.insert_col(grid.num_cols)

    # Assert
    assert grid.num_cols == 3
    assert grid.get_cell(0, 2).content == ""


def test_insert_col_inside_horizontal_merge_extends_colspan() -> None:
    # Arrange
    grid = TableGrid(
        rows=[
            [Cell(content="A"), Cell(content="B"), Cell(content="C")],
            [Cell(content="D"), Cell(content="E"), Cell(content="F")],
        ],
        has_header=False,
    )
    grid.merge_cells(0, 0, 1, 3)  # anchor at (0,0) colspan=3

    # Act — insert inside the merge
    grid.insert_col(2)

    # Assert
    assert grid.num_cols == 4
    anchor = grid.get_cell(0, 0)
    assert anchor.colspan == 4  # extended
    assert grid.get_cell(0, 2).is_covered  # new cell is covered
    assert grid.get_cell(0, 2).anchor_col == 0


def test_insert_col_after_merge_no_adjustment() -> None:
    # Arrange
    grid = _small_grid()
    grid.merge_cells(0, 0, 1, 2)  # colspan=2

    # Act — insert after the merge
    grid.insert_col(2)

    # Assert
    anchor = grid.get_cell(0, 0)
    assert anchor.colspan == 2  # unchanged


# ---------------------------------------------------------------------------
# delete_row
# ---------------------------------------------------------------------------


def test_delete_row_simple_removes_row() -> None:
    # Arrange
    grid = _simple_grid()  # 3 rows
    original_content_row2 = grid.get_cell(2, 0).content

    # Act — delete middle row
    grid.delete_row(1)

    # Assert
    assert grid.num_rows == 2
    assert grid.get_cell(1, 0).content == original_content_row2


def test_delete_row_containing_multirow_anchor_raises_value_error() -> None:
    # Arrange
    grid = _small_grid()
    grid.merge_cells(0, 0, 2, 1)

    # Act / Assert
    with pytest.raises(ValueError, match="multirow anchor"):
        grid.delete_row(0)


def test_delete_row_covered_by_merge_shrinks_rowspan() -> None:
    # Arrange
    grid = TableGrid(
        rows=[
            [Cell(content="A"), Cell(content="B")],
            [Cell(content="C"), Cell(content="D")],
            [Cell(content="E"), Cell(content="F")],
        ],
        has_header=False,
    )
    grid.merge_cells(0, 0, 3, 1)  # rowspan=3

    # Act — delete middle covered row
    grid.delete_row(1)

    # Assert
    assert grid.num_rows == 2
    anchor = grid.get_cell(0, 0)
    assert anchor.rowspan == 2  # shrunk


# ---------------------------------------------------------------------------
# delete_col
# ---------------------------------------------------------------------------


def test_delete_col_simple_removes_column() -> None:
    # Arrange
    grid = _simple_grid()  # 3 cols

    # Act
    grid.delete_col(1)

    # Assert
    assert grid.num_cols == 2
    assert grid.get_cell(0, 0).content == "A"
    assert grid.get_cell(0, 1).content == "C"


def test_delete_col_containing_multicolumn_anchor_raises_value_error() -> None:
    # Arrange
    grid = _small_grid()
    grid.merge_cells(0, 0, 1, 2)

    # Act / Assert
    with pytest.raises(ValueError, match="multicolumn anchor"):
        grid.delete_col(0)


def test_delete_col_covered_by_merge_shrinks_colspan() -> None:
    # Arrange
    grid = TableGrid(
        rows=[
            [Cell(content="A"), Cell(content="B"), Cell(content="C")],
            [Cell(content="D"), Cell(content="E"), Cell(content="F")],
        ],
        has_header=False,
    )
    grid.merge_cells(0, 0, 1, 3)  # colspan=3

    # Act — delete middle covered column
    grid.delete_col(1)

    # Assert
    assert grid.num_cols == 2
    anchor = grid.get_cell(0, 0)
    assert anchor.colspan == 2  # shrunk


# ---------------------------------------------------------------------------
# Properties on empty grid
# ---------------------------------------------------------------------------


def test_empty_grid_has_zero_dimensions() -> None:
    # Arrange / Act
    grid = TableGrid()

    # Assert
    assert grid.num_rows == 0
    assert grid.num_cols == 0
