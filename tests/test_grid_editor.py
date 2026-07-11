"""Tests for grid_editor: interactive Flet grid editor with selection and editing."""

import flet as ft
import pytest

from grid_converter import grid_to_latex
from grid_editor import (
    CELL_HEIGHT,
    CELL_WIDTH,
    GridEditor,
    build_grid_view,
    grid_has_merges,
)
from table_model import Cell, CellAlignment, TableGrid

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_grid_2x2() -> TableGrid:
    """2-row, 2-col grid with header."""
    return TableGrid(
        rows=[
            [Cell(content="A"), Cell(content="B")],
            [Cell(content="1"), Cell(content="2")],
        ],
        has_header=True,
    )


def _merged_colspan_grid() -> TableGrid:
    """3x3 grid with a 2-column merge in the header row."""
    grid = TableGrid(
        rows=[
            [Cell(content="AB"), Cell(content=""), Cell(content="C")],
            [Cell(content="1"), Cell(content="2"), Cell(content="3")],
            [Cell(content="4"), Cell(content="5"), Cell(content="6")],
        ],
        has_header=True,
    )
    grid.merge_cells(0, 0, 1, 2)
    return grid


def _merged_rowspan_grid() -> TableGrid:
    """3x2 grid with a 2-row merge in the first column."""
    grid = TableGrid(
        rows=[
            [Cell(content="Span"), Cell(content="B")],
            [Cell(content=""), Cell(content="D")],
            [Cell(content="E"), Cell(content="F")],
        ],
        has_header=True,
    )
    grid.merge_cells(0, 0, 2, 1)
    return grid


# ---------------------------------------------------------------------------
# Tests -- empty grids
# ---------------------------------------------------------------------------


class TestBuildGridViewEmpty:
    """Edge cases for empty or zero-dimension grids."""

    def test_empty_grid_returns_text(self) -> None:
        grid = TableGrid(rows=[], has_header=False)
        result = build_grid_view(grid)
        assert isinstance(result, ft.Text)

    def test_zero_cols_returns_text(self) -> None:
        grid = TableGrid(rows=[[]], has_header=False)
        result = build_grid_view(grid)
        assert isinstance(result, ft.Text)


# ---------------------------------------------------------------------------
# Tests -- simple grids (no merges)
# ---------------------------------------------------------------------------


class TestBuildGridViewSimple:
    """Tests for simple grids without merges."""

    def test_returns_container(self) -> None:
        result = build_grid_view(_simple_grid_2x2())
        assert isinstance(result, ft.Container)

    def test_contains_stack(self) -> None:
        result = build_grid_view(_simple_grid_2x2())
        assert isinstance(result.content, ft.Stack)

    def test_control_count_matches_cells(self) -> None:
        result = build_grid_view(_simple_grid_2x2())
        stack = result.content
        # 2x2 grid = 4 cells, no merges => 4 controls
        assert len(stack.controls) == 4

    def test_container_dimensions(self) -> None:
        grid = _simple_grid_2x2()
        result = build_grid_view(grid)
        assert result.width == 2 * CELL_WIDTH
        assert result.height == 2 * CELL_HEIGHT


# ---------------------------------------------------------------------------
# Tests -- merged grids
# ---------------------------------------------------------------------------


class TestBuildGridViewMerged:
    """Tests for grids with colspan and rowspan merges."""

    def test_colspan_reduces_control_count(self) -> None:
        result = build_grid_view(_merged_colspan_grid())
        stack = result.content
        # 3x3 = 9 cells, 1 covered by colspan => 8 controls
        assert len(stack.controls) == 8

    def test_rowspan_reduces_control_count(self) -> None:
        result = build_grid_view(_merged_rowspan_grid())
        stack = result.content
        # 3x2 = 6 cells, 1 covered by rowspan => 5 controls
        assert len(stack.controls) == 5

    def test_colspan_cell_has_scaled_width(self) -> None:
        result = build_grid_view(_merged_colspan_grid())
        stack = result.content
        # First control is the merged header (row=0, col=0, colspan=2)
        merged_cell = stack.controls[0]
        assert merged_cell.width == 2 * CELL_WIDTH

    def test_rowspan_cell_has_scaled_height(self) -> None:
        result = build_grid_view(_merged_rowspan_grid())
        stack = result.content
        # First control is the merged cell (row=0, col=0, rowspan=2)
        merged_cell = stack.controls[0]
        assert merged_cell.height == 2 * CELL_HEIGHT

    def test_combined_merge_reduces_count(self) -> None:
        """A 2x2 merge covers 3 cells, leaving 1 anchor."""
        grid = TableGrid(
            rows=[
                [Cell(content="Big"), Cell(content=""), Cell(content="C")],
                [Cell(content=""), Cell(content=""), Cell(content="F")],
                [Cell(content="G"), Cell(content="H"), Cell(content="I")],
            ],
            has_header=True,
        )
        grid.merge_cells(0, 0, 2, 2)
        result = build_grid_view(grid)
        stack = result.content
        # 3x3 = 9 cells, 3 covered => 6 controls
        assert len(stack.controls) == 6


# ---------------------------------------------------------------------------
# Tests -- GridEditor class API
# ---------------------------------------------------------------------------


class TestGridEditorBuild:
    """Tests for the GridEditor class build method."""

    def test_build_returns_container(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        result = editor.build()
        assert isinstance(result, ft.Container)

    def test_build_empty_returns_text(self) -> None:
        editor = GridEditor(TableGrid(rows=[], has_header=False))
        result = editor.build()
        assert isinstance(result, ft.Text)

    def test_build_with_merged_cells(self) -> None:
        editor = GridEditor(_merged_colspan_grid())
        result = editor.build()
        stack = result.content
        assert len(stack.controls) == 8


# ---------------------------------------------------------------------------
# Tests -- selection
# ---------------------------------------------------------------------------


class TestGridEditorSelection:
    """Tests for cell selection state management."""

    def test_initial_selection_is_none(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        assert editor.selected_cell is None

    def test_select_cell_updates_state(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        editor._select_cell(0, 1)
        assert editor.selected_cell == (0, 1)

    def test_select_different_cell_changes_state(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        editor._select_cell(0, 0)
        editor._select_cell(1, 1)
        assert editor.selected_cell == (1, 1)

    def test_select_same_cell_is_noop(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        editor._select_cell(0, 0)
        # Selecting the same cell again should not change state.
        editor._select_cell(0, 0)
        assert editor.selected_cell == (0, 0)


# ---------------------------------------------------------------------------
# Tests -- editing
# ---------------------------------------------------------------------------


class TestGridEditorEdit:
    """Tests for cell text editing through apply_edit."""

    def test_apply_edit_updates_grid_content(self) -> None:
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()
        editor.apply_edit(1, 0, "NEW")
        assert grid.get_cell(1, 0).content == "NEW"

    def test_apply_edit_invokes_callback(self) -> None:
        grid = _simple_grid_2x2()
        callback_log: list[tuple[int, int, str]] = []

        def on_edit(row: int, col: int, text: str) -> None:
            callback_log.append((row, col, text))

        editor = GridEditor(grid, on_cell_edit=on_edit)
        editor.build()
        editor.apply_edit(0, 0, "Edited")
        assert callback_log == [(0, 0, "Edited")]

    def test_apply_edit_without_callback_succeeds(self) -> None:
        grid = _simple_grid_2x2()
        editor = GridEditor(grid, on_cell_edit=None)
        editor.build()
        editor.apply_edit(1, 1, "OK")
        assert grid.get_cell(1, 1).content == "OK"

    def test_apply_edit_on_covered_cell_raises(self) -> None:
        grid = _merged_colspan_grid()
        editor = GridEditor(grid)
        editor.build()
        # Cell (0, 1) is covered by the colspan merge at (0, 0).
        with pytest.raises(ValueError, match="covered"):
            editor.apply_edit(0, 1, "bad")

    def test_edit_reflects_in_latex_output(self) -> None:
        """Editing a cell should change the LaTeX output from grid_to_latex."""
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()

        latex_before = grid_to_latex(grid)
        editor.apply_edit(1, 0, "CHANGED")
        latex_after = grid_to_latex(grid)

        assert "CHANGED" not in latex_before
        assert "CHANGED" in latex_after

    def test_edit_header_cell_reflects_in_latex(self) -> None:
        """Editing a header cell should update the LaTeX output."""
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()

        editor.apply_edit(0, 0, "NewHeader")
        latex = grid_to_latex(grid)
        assert "NewHeader" in latex

    def test_multiple_edits_accumulate(self) -> None:
        """Multiple edits should all be reflected in the grid."""
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()

        editor.apply_edit(0, 0, "H1")
        editor.apply_edit(0, 1, "H2")
        editor.apply_edit(1, 0, "D1")
        editor.apply_edit(1, 1, "D2")

        assert grid.get_cell(0, 0).content == "H1"
        assert grid.get_cell(0, 1).content == "H2"
        assert grid.get_cell(1, 0).content == "D1"
        assert grid.get_cell(1, 1).content == "D2"


# ---------------------------------------------------------------------------
# Tests -- range selection
# ---------------------------------------------------------------------------


def _grid_3x3() -> TableGrid:
    """3-row, 3-col grid for range / merge / split tests."""
    return TableGrid(
        rows=[
            [Cell(content="A"), Cell(content="B"), Cell(content="C")],
            [Cell(content="1"), Cell(content="2"), Cell(content="3")],
            [Cell(content="4"), Cell(content="5"), Cell(content="6")],
        ],
        has_header=True,
    )


class TestGridEditorRangeSelection:
    """Tests for rectangular range selection math."""

    def test_no_selection_returns_none(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        assert editor.get_selection_rect() is None

    def test_single_cell_rect(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        editor._select_cell(0, 1)
        assert editor.get_selection_rect() == (0, 1, 0, 1)

    def test_normalizes_top_left_to_bottom_right(self) -> None:
        """Start at bottom-right, end at top-left -- rect is normalized."""
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        editor._on_cell_click(1, 1)
        editor.range_mode = True
        editor._on_cell_click(0, 0)
        assert editor.get_selection_rect() == (0, 0, 1, 1)

    def test_normalizes_bottom_left_to_top_right(self) -> None:
        """Start at bottom-left, end at top-right -- rect is normalized."""
        editor = GridEditor(_grid_3x3())
        editor.build()
        editor._on_cell_click(2, 0)
        editor.range_mode = True
        editor._on_cell_click(0, 2)
        assert editor.get_selection_rect() == (0, 0, 2, 2)

    def test_range_mode_off_collapses_to_start(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        editor._on_cell_click(0, 0)
        editor.range_mode = True
        editor._on_cell_click(1, 1)
        assert editor.get_selection_rect() == (0, 0, 1, 1)
        editor.range_mode = False
        assert editor.get_selection_rect() == (0, 0, 0, 0)

    def test_normal_click_resets_range(self) -> None:
        """In normal mode each click replaces the selection entirely."""
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        editor._on_cell_click(0, 0)
        editor._on_cell_click(1, 1)
        assert editor.get_selection_rect() == (1, 1, 1, 1)

    def test_range_mode_extends_from_existing_start(self) -> None:
        editor = GridEditor(_grid_3x3())
        editor.build()
        editor._on_cell_click(0, 0)
        editor.range_mode = True
        editor._on_cell_click(1, 2)
        assert editor.get_selection_rect() == (0, 0, 1, 2)


# ---------------------------------------------------------------------------
# Tests -- merge_selection
# ---------------------------------------------------------------------------


class TestGridEditorMerge:
    """Tests for merge_selection delegating to TableGrid."""

    def test_merge_valid_range_updates_grid(self) -> None:
        grid = _grid_3x3()
        editor = GridEditor(grid)
        editor.build()
        editor._on_cell_click(0, 0)
        editor.range_mode = True
        editor._on_cell_click(0, 1)
        editor.merge_selection()

        anchor = grid.get_cell(0, 0)
        assert anchor.colspan == 2
        assert anchor.rowspan == 1
        assert grid.get_cell(0, 1).is_covered

    def test_merge_2x2_updates_grid(self) -> None:
        grid = _grid_3x3()
        editor = GridEditor(grid)
        editor.build()
        editor._on_cell_click(0, 0)
        editor.range_mode = True
        editor._on_cell_click(1, 1)
        editor.merge_selection()

        anchor = grid.get_cell(0, 0)
        assert anchor.colspan == 2
        assert anchor.rowspan == 2
        for r, c in [(0, 1), (1, 0), (1, 1)]:
            assert grid.get_cell(r, c).is_covered

    def test_merge_reflects_in_latex_multicolumn(self) -> None:
        grid = _grid_3x3()
        editor = GridEditor(grid)
        editor.build()
        editor._on_cell_click(0, 0)
        editor.range_mode = True
        editor._on_cell_click(0, 1)
        editor.merge_selection()

        latex = grid_to_latex(grid)
        assert r"\multicolumn{2}" in latex

    def test_merge_reflects_in_latex_multirow(self) -> None:
        grid = _grid_3x3()
        editor = GridEditor(grid)
        editor.build()
        editor._on_cell_click(0, 0)
        editor.range_mode = True
        editor._on_cell_click(1, 0)
        editor.merge_selection()

        latex = grid_to_latex(grid)
        assert r"\multirow{2}" in latex

    def test_merge_no_selection_raises(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        with pytest.raises(ValueError, match="No cells selected"):
            editor.merge_selection()

    def test_merge_single_cell_raises(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        editor._on_cell_click(0, 0)
        with pytest.raises(ValueError, match="more than one cell"):
            editor.merge_selection()

    def test_merge_overlapping_existing_raises(self) -> None:
        grid = _grid_3x3()
        grid.merge_cells(0, 0, 1, 2)
        editor = GridEditor(grid)
        editor.build()
        # Try to merge a region that overlaps the existing merge.
        editor._on_cell_click(0, 0)
        editor.range_mode = True
        editor._on_cell_click(1, 2)
        with pytest.raises(ValueError):
            editor.merge_selection()

    def test_merge_invokes_on_grid_change(self) -> None:
        grid = _grid_3x3()
        callback_log: list[str] = []
        editor = GridEditor(grid, on_grid_change=lambda: callback_log.append("changed"))
        editor.build()
        editor._on_cell_click(0, 0)
        editor.range_mode = True
        editor._on_cell_click(0, 1)
        editor.merge_selection()
        assert callback_log == ["changed"]


# ---------------------------------------------------------------------------
# Tests -- split_selection
# ---------------------------------------------------------------------------


class TestGridEditorSplit:
    """Tests for split_selection delegating to TableGrid."""

    def test_split_restores_individual_cells(self) -> None:
        grid = _grid_3x3()
        grid.merge_cells(0, 0, 2, 2)
        editor = GridEditor(grid)
        editor.build()
        editor._on_cell_click(0, 0)
        editor.split_selection()

        assert grid.get_cell(0, 0).colspan == 1
        assert grid.get_cell(0, 0).rowspan == 1
        for r, c in [(0, 1), (1, 0), (1, 1)]:
            assert not grid.get_cell(r, c).is_covered

    def test_split_non_merged_raises(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        editor._on_cell_click(0, 0)
        with pytest.raises(ValueError, match="not merged"):
            editor.split_selection()

    def test_split_no_selection_raises(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        with pytest.raises(ValueError, match="No cell selected"):
            editor.split_selection()

    def test_split_removes_multicolumn_from_latex(self) -> None:
        grid = _grid_3x3()
        grid.merge_cells(0, 0, 1, 2)
        latex_merged = grid_to_latex(grid)
        assert r"\multicolumn" in latex_merged

        editor = GridEditor(grid)
        editor.build()
        editor._on_cell_click(0, 0)
        editor.split_selection()

        latex_split = grid_to_latex(grid)
        assert r"\multicolumn" not in latex_split

    def test_split_invokes_on_grid_change(self) -> None:
        grid = _grid_3x3()
        grid.merge_cells(0, 0, 1, 2)
        callback_log: list[str] = []
        editor = GridEditor(grid, on_grid_change=lambda: callback_log.append("changed"))
        editor.build()
        editor._on_cell_click(0, 0)
        editor.split_selection()
        assert callback_log == ["changed"]


# ---------------------------------------------------------------------------
# Tests -- insert / delete
# ---------------------------------------------------------------------------


class TestGridEditorInsertDelete:
    """Tests for insert_row/col and delete_row/col via the editor."""

    def test_insert_row_above_increases_rows(self) -> None:
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(0, 0)
        editor.insert_row_above()
        assert grid.num_rows == 3
        # Original header row shifted down.
        assert grid.get_cell(1, 0).content == "A"
        assert grid.get_cell(0, 0).content == ""

    def test_insert_row_below_increases_rows(self) -> None:
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(0, 0)
        editor.insert_row_below()
        assert grid.num_rows == 3
        assert grid.get_cell(0, 0).content == "A"
        assert grid.get_cell(1, 0).content == ""

    def test_insert_col_left_increases_cols(self) -> None:
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(0, 0)
        editor.insert_col_left()
        assert grid.num_cols == 3
        # Original col shifted right.
        assert grid.get_cell(0, 1).content == "A"
        assert grid.get_cell(0, 0).content == ""

    def test_insert_col_right_increases_cols(self) -> None:
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(0, 0)
        editor.insert_col_right()
        assert grid.num_cols == 3
        assert grid.get_cell(0, 0).content == "A"
        assert grid.get_cell(0, 1).content == ""

    def test_delete_row_decreases_rows(self) -> None:
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(0, 0)
        editor.delete_row()
        assert grid.num_rows == 1
        # Remaining row is the original data row.
        assert grid.get_cell(0, 0).content == "1"

    def test_delete_col_decreases_cols(self) -> None:
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(0, 0)
        editor.delete_col()
        assert grid.num_cols == 1
        assert grid.get_cell(0, 0).content == "B"

    def test_delete_last_row_raises_error(self) -> None:
        grid = TableGrid(
            rows=[[Cell(content="only")]],
            has_header=False,
        )
        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(0, 0)
        with pytest.raises(ValueError, match="last remaining row"):
            editor.delete_row()

    def test_delete_last_col_raises_error(self) -> None:
        grid = TableGrid(
            rows=[[Cell(content="only")]],
            has_header=False,
        )
        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(0, 0)
        with pytest.raises(ValueError, match="last remaining column"):
            editor.delete_col()

    def test_insert_without_selection_raises(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        with pytest.raises(ValueError, match="No cell selected"):
            editor.insert_row_above()

    def test_delete_without_selection_raises(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        with pytest.raises(ValueError, match="No cell selected"):
            editor.delete_row()

    def test_insert_row_invokes_callback(self) -> None:
        grid = _simple_grid_2x2()
        log: list[str] = []
        editor = GridEditor(grid, on_grid_change=lambda: log.append("changed"))
        editor.build()
        editor._select_cell(0, 0)
        editor.insert_row_below()
        assert log == ["changed"]

    def test_delete_col_invokes_callback(self) -> None:
        grid = _simple_grid_2x2()
        log: list[str] = []
        editor = GridEditor(grid, on_grid_change=lambda: log.append("changed"))
        editor.build()
        editor._select_cell(0, 0)
        editor.delete_col()
        assert log == ["changed"]


# ---------------------------------------------------------------------------
# Tests -- per-cell alignment
# ---------------------------------------------------------------------------


class TestGridEditorAlignment:
    """Tests for set_selected_alignment via the editor."""

    def test_set_alignment_changes_cell(self) -> None:
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(1, 0)
        editor.set_selected_alignment(CellAlignment.LEFT)
        assert grid.get_cell(1, 0).alignment == CellAlignment.LEFT

    def test_set_alignment_inherit_clears(self) -> None:
        grid = _simple_grid_2x2()
        grid.set_alignment(1, 0, CellAlignment.RIGHT)
        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(1, 0)
        editor.set_selected_alignment(None)
        assert grid.get_cell(1, 0).alignment is None

    def test_alignment_reflects_in_latex(self) -> None:
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(1, 0)
        editor.set_selected_alignment(CellAlignment.LEFT)
        latex = grid_to_latex(grid)
        assert r"\multicolumn{1}{|l|}{1}" in latex

    def test_alignment_inherit_removes_multicolumn(self) -> None:
        grid = _simple_grid_2x2()
        grid.set_alignment(1, 0, CellAlignment.LEFT)
        latex_with = grid_to_latex(grid)
        assert r"\multicolumn{1}" in latex_with

        editor = GridEditor(grid)
        editor.build()
        editor._select_cell(1, 0)
        editor.set_selected_alignment(None)
        latex_without = grid_to_latex(grid)
        assert r"\multicolumn{1}" not in latex_without

    def test_alignment_without_selection_raises(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()
        with pytest.raises(ValueError, match="No cell selected"):
            editor.set_selected_alignment(CellAlignment.CENTER)

    def test_alignment_invokes_callback(self) -> None:
        grid = _simple_grid_2x2()
        log: list[str] = []
        editor = GridEditor(grid, on_grid_change=lambda: log.append("changed"))
        editor.build()
        editor._select_cell(1, 0)
        editor.set_selected_alignment(CellAlignment.RIGHT)
        assert log == ["changed"]


# ---------------------------------------------------------------------------
# Tests -- grid_has_merges
# ---------------------------------------------------------------------------


class TestGridHasMerges:
    """Tests for the grid_has_merges utility function."""

    def test_no_merges_returns_false(self) -> None:
        assert not grid_has_merges(_simple_grid_2x2())

    def test_with_merge_returns_true(self) -> None:
        grid = _simple_grid_2x2()
        grid.merge_cells(0, 0, 1, 2)
        assert grid_has_merges(grid)

    def test_none_grid_returns_false(self) -> None:
        assert not grid_has_merges(None)

    def test_after_split_returns_false(self) -> None:
        grid = _simple_grid_2x2()
        grid.merge_cells(0, 0, 1, 2)
        grid.split_cell(0, 0)
        assert not grid_has_merges(grid)


# ---------------------------------------------------------------------------
# Tests -- grid_toolbar module import
# ---------------------------------------------------------------------------


def test_grid_toolbar_imports() -> None:
    """Verify grid_toolbar module can be imported."""
    import grid_toolbar

    assert hasattr(grid_toolbar, "build_grid_toolbar")
