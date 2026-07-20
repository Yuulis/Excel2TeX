"""Tests for grid_editor: interactive Flet grid editor with selection and editing."""

from types import SimpleNamespace

import flet as ft
import pytest

from converter import ConversionOptions
from grid_converter import grid_to_latex
from grid_editor import (
    CELL_HEIGHT,
    CELL_WIDTH,
    COLUMN_SELECTOR_HEIGHT,
    DEFAULT_VIEWPORT_HEIGHT,
    ROW_SELECTOR_WIDTH,
    VIRTUALIZE_ROW_THRESHOLD,
    GridEditor,
    build_grid_view,
    cell_visible_in_row_range,
    compute_visible_row_range,
    grid_has_merges,
    should_use_windowing,
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
        # 4 cells + corner + 2 row + 2 column selectors.
        assert len(stack.controls) == 9

    def test_container_dimensions(self) -> None:
        grid = _simple_grid_2x2()
        result = build_grid_view(grid)
        assert result.width == ROW_SELECTOR_WIDTH + 2 * CELL_WIDTH
        assert result.height == COLUMN_SELECTOR_HEIGHT + 2 * CELL_HEIGHT


# ---------------------------------------------------------------------------
# Tests -- merged grids
# ---------------------------------------------------------------------------


class TestBuildGridViewMerged:
    """Tests for grids with colspan and rowspan merges."""

    def test_colspan_reduces_control_count(self) -> None:
        result = build_grid_view(_merged_colspan_grid())
        stack = result.content
        # 8 visible cells + corner + 3 row + 3 column selectors.
        assert len(stack.controls) == 15

    def test_rowspan_reduces_control_count(self) -> None:
        result = build_grid_view(_merged_rowspan_grid())
        stack = result.content
        # 5 visible cells + corner + 3 row + 2 column selectors.
        assert len(stack.controls) == 11

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
        # 6 visible cells + corner + 3 row + 3 column selectors.
        assert len(stack.controls) == 13


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
        assert len(stack.controls) == 15


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

    def test_select_row_uses_full_row_rectangle(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()

        editor.select_row(1)

        assert editor.selected_cell == (1, 0)
        assert editor.get_selection_rect() == (1, 0, 1, 1)
        assert editor._row_selector_containers[1].bgcolor == ft.Colors.BLUE_700

    def test_select_column_uses_full_column_rectangle(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()

        editor.select_column(1)

        assert editor.selected_cell == (0, 1)
        assert editor.get_selection_rect() == (0, 1, 1, 1)
        assert editor._column_selector_containers[1].bgcolor == ft.Colors.BLUE_700

    def test_preview_builds_clickable_row_and_column_selectors(self) -> None:
        editor = GridEditor(_simple_grid_2x2())
        editor.build()

        row_selector = editor._row_selector_containers[1]
        row_click = row_selector.on_click
        assert callable(row_click)
        row_click(SimpleNamespace(page=None))
        assert editor.get_selection_rect() == (1, 0, 1, 1)

        column_selector = editor._column_selector_containers[1]
        column_click = column_selector.on_click
        assert callable(column_click)
        column_click(SimpleNamespace(page=None))
        assert editor.get_selection_rect() == (0, 1, 1, 1)


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

    def test_edit_complete_callback_runs_on_cell_blur(self) -> None:
        grid = _simple_grid_2x2()
        callback_log: list[tuple[int, int, str]] = []
        editor = GridEditor(
            grid,
            on_edit_complete=lambda row, col, text: callback_log.append(
                (row, col, text)
            ),
        )
        editor.build()
        editor.apply_edit(1, 0, "Edited")
        text_field = editor._cell_containers[(1, 0)].content

        text_field.on_blur(SimpleNamespace())

        assert callback_log == [(1, 0, "Edited")]

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
# Tests -- on_selection_change callback
# ---------------------------------------------------------------------------


class TestGridEditorSelectionChange:
    """Tests for the on_selection_change callback."""

    def test_fires_on_single_click(self) -> None:
        log: list[tuple[int, int]] = []
        editor = GridEditor(
            _simple_grid_2x2(),
            on_selection_change=lambda r, c: log.append((r, c)),
        )
        editor.build()
        editor._on_cell_click(0, 1)
        assert log == [(0, 1)]

    def test_fires_on_each_normal_click(self) -> None:
        log: list[tuple[int, int]] = []
        editor = GridEditor(
            _simple_grid_2x2(),
            on_selection_change=lambda r, c: log.append((r, c)),
        )
        editor.build()
        editor._on_cell_click(0, 0)
        editor._on_cell_click(1, 1)
        assert log == [(0, 0), (1, 1)]

    def test_does_not_fire_on_range_end_click(self) -> None:
        """In range mode, extending the end should NOT fire the callback."""
        log: list[tuple[int, int]] = []
        editor = GridEditor(
            _simple_grid_2x2(),
            on_selection_change=lambda r, c: log.append((r, c)),
        )
        editor.build()
        editor._on_cell_click(0, 0)  # fires
        editor.range_mode = True
        editor._on_cell_click(1, 1)  # should NOT fire (range end)
        assert log == [(0, 0)]

    def test_no_callback_is_safe(self) -> None:
        """No crash when on_selection_change is None."""
        editor = GridEditor(_simple_grid_2x2(), on_selection_change=None)
        editor.build()
        editor._on_cell_click(0, 0)
        assert editor.selected_cell == (0, 0)


# ---------------------------------------------------------------------------
# Tests -- on_before_edit callback
# ---------------------------------------------------------------------------


class TestGridEditorBeforeEdit:
    """Tests for the on_before_edit callback."""

    def test_fires_before_content_change(self) -> None:
        """on_before_edit must fire before the grid content is mutated."""
        grid = _simple_grid_2x2()
        captured_content: list[str] = []

        def before_edit(row: int, col: int) -> None:
            # Capture the content BEFORE mutation.
            captured_content.append(grid.get_cell(row, col).content)

        editor = GridEditor(grid, on_before_edit=before_edit)
        editor.build()
        editor.apply_edit(1, 0, "NEW")

        # The captured content should be the ORIGINAL value, not "NEW".
        assert captured_content == ["1"]
        assert grid.get_cell(1, 0).content == "NEW"

    def test_no_callback_is_safe(self) -> None:
        grid = _simple_grid_2x2()
        editor = GridEditor(grid, on_before_edit=None)
        editor.build()
        editor.apply_edit(0, 0, "OK")
        assert grid.get_cell(0, 0).content == "OK"


# ---------------------------------------------------------------------------
# Tests -- alignment_to_label mapping
# ---------------------------------------------------------------------------


class TestAlignmentToLabel:
    """Tests for the alignment_to_label helper in grid_toolbar."""

    def test_left(self) -> None:
        from grid_toolbar import alignment_to_label

        assert alignment_to_label(CellAlignment.LEFT) == "Left"

    def test_center(self) -> None:
        from grid_toolbar import alignment_to_label

        assert alignment_to_label(CellAlignment.CENTER) == "Center"

    def test_right(self) -> None:
        from grid_toolbar import alignment_to_label

        assert alignment_to_label(CellAlignment.RIGHT) == "Right"

    def test_none_maps_to_inherit(self) -> None:
        from grid_toolbar import alignment_to_label

        assert alignment_to_label(None) == "Inherit"


# ---------------------------------------------------------------------------
# Tests -- grid_toolbar module import
# ---------------------------------------------------------------------------


def test_grid_toolbar_imports() -> None:
    """Verify grid_toolbar module can be imported."""
    import grid_toolbar

    assert hasattr(grid_toolbar, "build_grid_toolbar")


def test_grid_cells_use_dark_theme_colors() -> None:
    """Cell backgrounds and text must remain legible in dark mode."""
    from grid_editor import CELL_BG, HEADER_BG, TEXT_COLOR

    editor = GridEditor(_simple_grid_2x2())
    editor.build()

    header = editor._cell_containers[(0, 0)]
    body = editor._cell_containers[(1, 0)]
    assert header.bgcolor == HEADER_BG
    assert body.bgcolor == CELL_BG
    assert header.content.text_style.color == TEXT_COLOR
    assert body.content.text_style.color == TEXT_COLOR


def test_grid_cells_use_global_text_alignment() -> None:
    editor = GridEditor(
        _simple_grid_2x2(),
        options=ConversionOptions(text_alignment="r"),
    )
    editor.build()

    assert editor._cell_containers[(0, 0)].content.text_align == ft.TextAlign.RIGHT
    assert editor._cell_containers[(1, 1)].content.text_align == ft.TextAlign.RIGHT


def test_grid_cell_alignment_overrides_global_alignment() -> None:
    grid = _simple_grid_2x2()
    grid.set_alignment(1, 0, CellAlignment.LEFT)
    editor = GridEditor(
        grid,
        options=ConversionOptions(text_alignment="r"),
    )
    editor.build()

    assert editor._cell_containers[(1, 0)].content.text_align == ft.TextAlign.LEFT
    assert editor._cell_containers[(1, 1)].content.text_align == ft.TextAlign.RIGHT


def test_grid_cells_reflect_bold_row_and_column_options() -> None:
    editor = GridEditor(
        _simple_grid_2x2(),
        options=ConversionOptions(
            bold_first_row=True,
            bold_first_column=True,
        ),
    )
    editor.build()

    assert (
        editor._cell_containers[(0, 0)].content.text_style.weight == ft.FontWeight.BOLD
    )
    assert (
        editor._cell_containers[(0, 1)].content.text_style.weight == ft.FontWeight.BOLD
    )
    assert (
        editor._cell_containers[(1, 0)].content.text_style.weight == ft.FontWeight.BOLD
    )
    assert editor._cell_containers[(1, 1)].content.text_style.weight is None


def test_grid_cells_have_no_border_for_none_style() -> None:
    editor = GridEditor(
        _simple_grid_2x2(),
        options=ConversionOptions(border_style="none"),
    )
    editor.build()

    assert editor._cell_containers[(0, 0)].border is None
    assert editor._cell_containers[(1, 0)].border is None


def test_grid_cells_have_horizontal_rules_without_vertical_rules() -> None:
    editor = GridEditor(
        _simple_grid_2x2(),
        options=ConversionOptions(border_style="horizontal"),
    )
    editor.build()

    header_border = editor._cell_containers[(0, 0)].border
    body_border = editor._cell_containers[(1, 0)].border
    assert header_border.top.width == 1
    assert header_border.bottom.width == 1
    assert header_border.left.width == 0
    assert body_border.top is None
    assert body_border.bottom.width == 1


def test_grid_cells_use_heavy_outer_booktabs_rules() -> None:
    editor = GridEditor(
        _simple_grid_2x2(),
        options=ConversionOptions(border_style="booktabs"),
    )
    editor.build()

    header_border = editor._cell_containers[(0, 0)].border
    body_border = editor._cell_containers[(1, 0)].border
    assert header_border.top.width == 2
    assert header_border.bottom.width == 1
    assert header_border.left.width == 0
    assert body_border.bottom.width == 2


def test_update_options_restyles_visible_cells_without_rebuilding() -> None:
    editor = GridEditor(_simple_grid_2x2())
    editor.build()
    original_containers = dict(editor._cell_containers)

    editor.update_options(
        ConversionOptions(
            bold_first_row=True,
            text_alignment="r",
            border_style="none",
        )
    )

    assert editor._cell_containers == original_containers
    assert all(
        editor._cell_containers[position] is container
        for position, container in original_containers.items()
    )
    header_field = editor._cell_containers[(0, 0)].content
    body_field = editor._cell_containers[(1, 1)].content
    assert header_field.text_style.weight == ft.FontWeight.BOLD
    assert body_field.text_align == ft.TextAlign.RIGHT
    assert all(container.border is None for container in original_containers.values())


def test_grid_toolbar_action_groups_stay_in_two_horizontal_rows() -> None:
    """Edit/Cells and Rows/Columns should remain side by side."""
    from grid_toolbar import build_grid_toolbar

    result = build_grid_toolbar(
        get_editor=lambda: None,
        set_status=lambda _message, _is_error: None,
        page_update=lambda: None,
    )

    primary_actions, structure_actions = result.toolbar.controls
    assert primary_actions.wrap is False
    assert structure_actions.wrap is False
    assert len(primary_actions.controls) == 2
    assert len(structure_actions.controls) == 2
    assert all(group.expand is True for group in primary_actions.controls)
    assert all(group.expand is True for group in structure_actions.controls)
    assert result.toolbar.horizontal_alignment == ft.CrossAxisAlignment.STRETCH


def test_grid_toolbar_controls_use_consistent_dimensions() -> None:
    """Icon actions are square and the alignment dropdown keeps a usable width."""
    from grid_toolbar import build_grid_toolbar
    from ui_layout import BUTTON_HEIGHT, BUTTON_WIDTH

    result = build_grid_toolbar(
        get_editor=lambda: None,
        set_status=lambda _message, _is_error: None,
        page_update=lambda: None,
    )

    grouped_controls = [
        control
        for row in result.toolbar.controls
        for group in row.controls
        for control in group.content.controls[1:]
    ]
    icon_buttons = [
        control for control in grouped_controls if isinstance(control, ft.IconButton)
    ]
    dropdowns = [
        control for control in grouped_controls if isinstance(control, ft.Dropdown)
    ]

    assert len(icon_buttons) == 11
    assert all(button.width == BUTTON_HEIGHT for button in icon_buttons)
    assert all(button.height == BUTTON_HEIGHT for button in icon_buttons)
    assert len(dropdowns) == 1
    assert dropdowns[0].width == BUTTON_WIDTH
    assert dropdowns[0].height == BUTTON_HEIGHT


def test_grid_toolbar_groups_actions_and_labels_icon_buttons() -> None:
    """Toolbar actions should be grouped and discoverable through tooltips."""
    from grid_toolbar import build_grid_toolbar

    result = build_grid_toolbar(
        get_editor=lambda: None,
        set_status=lambda _message, _is_error: None,
        page_update=lambda: None,
    )

    groups = [group for row in result.toolbar.controls for group in row.controls]
    labels = [group.content.controls[0].value for group in groups]
    icon_buttons = [
        control
        for group in groups
        for control in group.content.controls[1:]
        if isinstance(control, ft.IconButton)
    ]

    assert labels == ["Edit", "Cells", "Rows", "Columns"]
    assert all(button.tooltip for button in icon_buttons)

    row_insert_buttons = groups[2].content.controls[1:3]
    column_insert_buttons = groups[3].content.controls[1:3]
    assert [button.icon.value for button in row_insert_buttons] == ["+↑", "+↓"]
    assert [button.icon.value for button in column_insert_buttons] == ["←+", "+→"]


# ---------------------------------------------------------------------------
# Tests -- viewport windowing: should_use_windowing
# ---------------------------------------------------------------------------


class TestShouldUseWindowing:
    """Tests for the windowing threshold check."""

    def test_below_threshold_returns_false(self) -> None:
        assert not should_use_windowing(10)
        assert not should_use_windowing(VIRTUALIZE_ROW_THRESHOLD - 1)

    def test_at_threshold_returns_true(self) -> None:
        assert should_use_windowing(VIRTUALIZE_ROW_THRESHOLD)

    def test_above_threshold_returns_true(self) -> None:
        assert should_use_windowing(VIRTUALIZE_ROW_THRESHOLD + 100)

    def test_custom_threshold(self) -> None:
        assert not should_use_windowing(5, threshold=10)
        assert should_use_windowing(10, threshold=10)
        assert should_use_windowing(20, threshold=10)


# ---------------------------------------------------------------------------
# Tests -- viewport windowing: compute_visible_row_range
# ---------------------------------------------------------------------------


class TestComputeVisibleRowRange:
    """Tests for the viewport row range computation."""

    def test_viewport_at_top(self) -> None:
        first, last = compute_visible_row_range(100, 40, 0.0, 800.0, 5)
        assert first == 0
        # int(800/40) + 5 = 20 + 5 = 25
        assert last == 25

    def test_viewport_at_middle(self) -> None:
        first, last = compute_visible_row_range(100, 40, 2000.0, 800.0, 5)
        # int(2000/40) - 5 = 50 - 5 = 45
        assert first == 45
        # int(2800/40) + 5 = 70 + 5 = 75
        assert last == 75

    def test_viewport_at_bottom_clamps_last(self) -> None:
        first, last = compute_visible_row_range(100, 40, 3200.0, 800.0, 5)
        # int(3200/40) - 5 = 80 - 5 = 75
        assert first == 75
        # clamped to total_rows - 1
        assert last == 99

    def test_first_row_clamps_to_zero(self) -> None:
        first, _last = compute_visible_row_range(100, 40, 100.0, 400.0, 10)
        # int(100/40) - 10 = 2 - 10 = -8 -> clamped to 0
        assert first == 0

    def test_small_grid_returns_all(self) -> None:
        first, last = compute_visible_row_range(5, 40, 0.0, 800.0, 5)
        assert first == 0
        assert last == 4

    def test_zero_rows_returns_zero_tuple(self) -> None:
        result = compute_visible_row_range(0, 40, 0.0, 800.0, 5)
        assert result == (0, 0)

    def test_zero_overscan(self) -> None:
        first, last = compute_visible_row_range(100, 40, 400.0, 400.0, 0)
        # int(400/40) = 10, int(800/40) = 20
        assert first == 10
        assert last == 20


# ---------------------------------------------------------------------------
# Tests -- viewport windowing: cell_visible_in_row_range
# ---------------------------------------------------------------------------


class TestCellVisibleInRowRange:
    """Tests for span-aware cell visibility checks."""

    def test_single_cell_inside_range(self) -> None:
        assert cell_visible_in_row_range(5, 1, 0, 10)

    def test_single_cell_above_range(self) -> None:
        assert not cell_visible_in_row_range(2, 1, 5, 10)

    def test_single_cell_below_range(self) -> None:
        assert not cell_visible_in_row_range(15, 1, 5, 10)

    def test_cell_at_first_boundary(self) -> None:
        assert cell_visible_in_row_range(5, 1, 5, 10)

    def test_cell_at_last_boundary(self) -> None:
        assert cell_visible_in_row_range(10, 1, 5, 10)

    def test_merged_cell_straddling_top_boundary(self) -> None:
        # Cell at row 3 with rowspan 4 (rows 3-6), range 5-10.
        assert cell_visible_in_row_range(3, 4, 5, 10)

    def test_merged_cell_straddling_bottom_boundary(self) -> None:
        # Cell at row 9 with rowspan 3 (rows 9-11), range 5-10.
        assert cell_visible_in_row_range(9, 3, 5, 10)

    def test_merged_cell_entirely_above(self) -> None:
        # Cell at row 1 with rowspan 2 (rows 1-2), range 5-10.
        assert not cell_visible_in_row_range(1, 2, 5, 10)

    def test_merged_cell_entirely_below(self) -> None:
        # Cell at row 12 with rowspan 3 (rows 12-14), range 5-10.
        assert not cell_visible_in_row_range(12, 3, 5, 10)

    def test_merged_cell_spanning_entire_range(self) -> None:
        # Cell at row 3 with rowspan 10 (rows 3-12), range 5-10.
        assert cell_visible_in_row_range(3, 10, 5, 10)

    def test_merged_cell_just_touching_top(self) -> None:
        # Cell at row 3 with rowspan 3 (rows 3-5), range 5-10.
        # cell_bottom = 5 >= visible_first = 5 -> True
        assert cell_visible_in_row_range(3, 3, 5, 10)

    def test_merged_cell_just_missing_top(self) -> None:
        # Cell at row 3 with rowspan 2 (rows 3-4), range 5-10.
        # cell_bottom = 4, visible_first = 5 -> 4 >= 5 is False
        assert not cell_visible_in_row_range(3, 2, 5, 10)


# ---------------------------------------------------------------------------
# Tests -- viewport windowing: GridEditor integration
# ---------------------------------------------------------------------------


class TestGridEditorWindowing:
    """Tests for windowing behavior in the GridEditor."""

    def test_small_grid_builds_all_controls(self) -> None:
        """Below threshold: all cells rendered, no windowing."""
        grid = _simple_grid_2x2()  # 2 rows < threshold
        editor = GridEditor(grid)
        result = editor.build()
        stack = result.content
        assert len(stack.controls) == 9  # 4 cells + 5 selectors

    def test_large_grid_builds_fewer_controls(self) -> None:
        """At/above threshold: only visible-window controls built."""
        num_rows = VIRTUALIZE_ROW_THRESHOLD + 10
        rows = [[Cell(content=f"r{r}c{c}") for c in range(3)] for r in range(num_rows)]
        grid = TableGrid(rows=rows, has_header=True)
        editor = GridEditor(grid)
        result = editor.build()
        stack = result.content
        total_cells = num_rows * 3
        assert len(stack.controls) < total_cells
        assert len(stack.controls) > 0

    def test_large_grid_preserves_full_dimensions(self) -> None:
        """Windowed grid container has full width/height for scrollbar."""
        num_rows = VIRTUALIZE_ROW_THRESHOLD + 10
        rows = [[Cell(content=f"r{r}c{c}") for c in range(3)] for r in range(num_rows)]
        grid = TableGrid(rows=rows, has_header=True)
        editor = GridEditor(grid)
        result = editor.build()
        assert result.width == ROW_SELECTOR_WIDTH + 3 * CELL_WIDTH
        assert result.height == COLUMN_SELECTOR_HEIGHT + num_rows * CELL_HEIGHT

    def test_handle_scroll_noop_for_small_grid(self) -> None:
        """handle_scroll returns False for non-windowed grids."""
        grid = _simple_grid_2x2()
        editor = GridEditor(grid)
        editor.build()
        event = ft.OnScrollEvent(
            name="scroll",
            control=ft.Column(),
            event_type=ft.ScrollType.UPDATE,
            pixels=100.0,
            min_scroll_extent=0.0,
            max_scroll_extent=1000.0,
            viewport_dimension=400.0,
        )
        assert not editor.handle_scroll(event)

    def test_handle_scroll_rebuilds_on_range_change(self) -> None:
        """handle_scroll returns True when the visible range changes."""
        num_rows = VIRTUALIZE_ROW_THRESHOLD + 40
        rows = [[Cell(content=f"r{r}c{c}") for c in range(2)] for r in range(num_rows)]
        grid = TableGrid(rows=rows, has_header=True)
        editor = GridEditor(grid)
        editor.build()
        # Scroll far enough to change the visible range
        event = ft.OnScrollEvent(
            name="scroll",
            control=ft.Column(),
            event_type=ft.ScrollType.UPDATE,
            pixels=float(num_rows * CELL_HEIGHT // 2),
            min_scroll_extent=0.0,
            max_scroll_extent=float(num_rows * CELL_HEIGHT),
            viewport_dimension=float(DEFAULT_VIEWPORT_HEIGHT),
        )
        result = editor.handle_scroll(event)
        assert result is True
        # Controls were rebuilt (different set of cells)
        assert len(editor._cell_containers) > 0

    def test_handle_scroll_noop_for_same_range(self) -> None:
        """handle_scroll returns False when range hasn't changed."""
        num_rows = VIRTUALIZE_ROW_THRESHOLD + 40
        rows = [[Cell(content=f"r{r}c{c}") for c in range(2)] for r in range(num_rows)]
        grid = TableGrid(rows=rows, has_header=True)
        editor = GridEditor(grid)
        editor.build()
        # Scroll a tiny amount that stays in the same overscan range
        event = ft.OnScrollEvent(
            name="scroll",
            control=ft.Column(),
            event_type=ft.ScrollType.UPDATE,
            pixels=1.0,
            min_scroll_extent=0.0,
            max_scroll_extent=float(num_rows * CELL_HEIGHT),
            viewport_dimension=float(DEFAULT_VIEWPORT_HEIGHT),
        )
        assert not editor.handle_scroll(event)

    def test_windowed_grid_includes_straddling_merge(self) -> None:
        """A merged cell straddling the window boundary is included."""
        num_rows = VIRTUALIZE_ROW_THRESHOLD + 10
        rows = [[Cell(content=f"r{r}c{c}") for c in range(2)] for r in range(num_rows)]
        grid = TableGrid(rows=rows, has_header=True)
        # Merge rows 0-3 in column 0 (large rowspan at top)
        grid.merge_cells(0, 0, 4, 1)
        editor = GridEditor(grid)
        editor.build()
        # The merged anchor at (0, 0) should be in the visible cells
        assert (0, 0) in editor._cell_containers

    def test_scrolled_window_includes_merge_anchor_above_visible_range(self) -> None:
        num_rows = VIRTUALIZE_ROW_THRESHOLD + 60
        rows = [[Cell(content=f"r{r}c{c}") for c in range(2)] for r in range(num_rows)]
        grid = TableGrid(rows=rows, has_header=True)
        grid.merge_cells(30, 0, 20, 1)
        editor = GridEditor(grid)
        editor.build()
        event = ft.OnScrollEvent(
            name="scroll",
            control=ft.Column(),
            event_type=ft.ScrollType.UPDATE,
            pixels=float(40 * CELL_HEIGHT),
            min_scroll_extent=0.0,
            max_scroll_extent=float(num_rows * CELL_HEIGHT),
            viewport_dimension=400.0,
        )

        editor.handle_scroll(event)

        assert editor._visible_range[0] > 30
        assert (30, 0) in editor._cell_containers

    def test_scrolling_does_not_scan_rows_before_visible_window(self) -> None:
        class CountingRows(list[list[Cell]]):
            access_count = 0

            def __getitem__(self, index: int) -> list[Cell]:
                self.access_count += 1
                return super().__getitem__(index)

        num_rows = 5000
        rows = CountingRows(
            [[Cell(content=f"r{r}c{c}") for c in range(2)] for r in range(num_rows)]
        )
        editor = GridEditor(TableGrid(rows=rows, has_header=True))
        editor.build()
        rows.access_count = 0
        event = ft.OnScrollEvent(
            name="scroll",
            control=ft.Column(),
            event_type=ft.ScrollType.UPDATE,
            pixels=float((num_rows - 30) * CELL_HEIGHT),
            min_scroll_extent=0.0,
            max_scroll_extent=float(num_rows * CELL_HEIGHT),
            viewport_dimension=400.0,
        )

        editor.handle_scroll(event)

        assert rows.access_count < 500
