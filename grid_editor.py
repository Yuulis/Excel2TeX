"""Interactive Flet grid editor for TableGrid with range selection and merge/split.

Renders a TableGrid as a Flet control with cells positioned in a Stack,
visually reflecting merged cells (colspan/rowspan).  Each non-covered cell
is an editable TextField.  Supports single-cell and rectangular range
selection (via an explicit "range mode" toggle).  Merge and split operations
delegate to TableGrid and invoke a callback so the caller can rebuild.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from table_model import CellAlignment, TableGrid

# -- Layout constants --------------------------------------------------------

CELL_WIDTH = 120
CELL_HEIGHT = 40
HEADER_BG = ft.Colors.BLUE_GREY_100
CELL_BG = ft.Colors.WHITE
SELECTED_BG = ft.Colors.BLUE_50
BORDER_COLOR = ft.Colors.BLUE_GREY_300
SELECTED_BORDER_COLOR = ft.Colors.BLUE_700
BORDER_WIDTH = 1
SELECTED_BORDER_WIDTH = 2
FONT_SIZE = 13
CELL_PADDING = 4
MIN_GRID_DIMENSION = 1

# -- Callback type aliases ---------------------------------------------------

CellEditCallback = Callable[[int, int, str], None]
GridChangeCallback = Callable[[], None]


# -- GridEditor class --------------------------------------------------------


class GridEditor:
    """Interactive grid editor widget for a TableGrid.

    Tracks selection state (single cell or rectangular range).  Provides
    ``merge_selection()`` and ``split_selection()`` that delegate to
    ``TableGrid`` mutation methods, then notify the caller via
    *on_grid_change*.

    **Range selection UX:**
    Flet 0.85 ``TextField.on_focus`` does not expose keyboard modifiers
    (shift state), so range selection uses an explicit *range_mode*
    toggle controlled by the caller.  When ``range_mode`` is ``False``
    a click sets a single-cell selection.  When ``range_mode`` is
    ``True`` and a start cell already exists, the next click defines
    the opposite corner of a rectangular range.

    Args:
        grid: The table grid to render and edit.
        on_cell_edit: Optional callback invoked after a cell content
            edit.  Signature: ``(row, col, new_text) -> None``.
        on_grid_change: Optional callback invoked after a structural
            change (merge or split).  The caller should rebuild the
            grid view and re-render LaTeX output.
    """

    def __init__(
        self,
        grid: TableGrid,
        on_cell_edit: CellEditCallback | None = None,
        on_grid_change: GridChangeCallback | None = None,
    ) -> None:
        self._grid = grid
        self._on_cell_edit = on_cell_edit
        self._on_grid_change = on_grid_change

        self._selection_start: tuple[int, int] | None = None
        self._selection_end: tuple[int, int] | None = None
        self._range_mode: bool = False

        self._cell_containers: dict[tuple[int, int], ft.Container] = {}

    # -- public API ----------------------------------------------------------

    def build(self) -> ft.Control:
        """Build the interactive grid as a Flet control.

        Returns a ``Container`` wrapping a ``Stack`` of positioned cell
        controls, or a placeholder ``Text`` when the grid is empty.
        """
        if self._grid.num_rows == 0 or self._grid.num_cols == 0:
            return ft.Text("No data to display.", color=ft.Colors.GREY_500)

        total_width = self._grid.num_cols * CELL_WIDTH
        total_height = self._grid.num_rows * CELL_HEIGHT
        self._cell_containers.clear()
        cell_controls = self._build_cell_controls()

        return ft.Container(
            content=ft.Stack(controls=cell_controls),
            width=total_width,
            height=total_height,
        )

    def apply_edit(self, row: int, col: int, text: str) -> None:
        """Apply a text edit to the grid and invoke the callback.

        Mutates the ``TableGrid`` via ``set_content`` (single source of
        truth), then invokes *on_cell_edit* if provided.
        """
        self._grid.set_content(row, col, text)
        if self._on_cell_edit is not None:
            self._on_cell_edit(row, col, text)

    @property
    def selected_cell(self) -> tuple[int, int] | None:
        """Return the primary selected ``(row, col)`` or ``None``."""
        return self._selection_start

    @property
    def range_mode(self) -> bool:
        """Return whether range selection mode is active."""
        return self._range_mode

    @range_mode.setter
    def range_mode(self, enabled: bool) -> None:
        """Enable or disable range selection mode.

        When disabled, the selection end collapses back to the start
        (single-cell selection).
        """
        self._range_mode = enabled
        if not enabled and self._selection_start is not None:
            self._selection_end = self._selection_start
            self._update_selection_highlight()

    def get_selection_rect(self) -> tuple[int, int, int, int] | None:
        """Return the normalized inclusive selection rectangle.

        Returns ``(row0, col0, row1, col1)`` where ``row0 <= row1`` and
        ``col0 <= col1``.  Returns ``None`` if no selection is active.
        """
        if self._selection_start is None or self._selection_end is None:
            return None
        r0, c0 = self._selection_start
        r1, c1 = self._selection_end
        return (min(r0, r1), min(c0, c1), max(r0, r1), max(c0, c1))

    def _notify_grid_change(self) -> None:
        """Invoke the grid-change callback if one is registered."""
        if self._on_grid_change is not None:
            self._on_grid_change()

    def merge_selection(self) -> None:
        """Merge the currently selected rectangular range.

        Delegates to ``TableGrid.merge_cells``.  Raises ``ValueError``
        if no selection is active or if the merge is invalid (propagated
        from ``TableGrid`` validation).
        """
        rect = self.get_selection_rect()
        if rect is None:
            raise ValueError("No cells selected for merge.")
        top_row, left_col, bottom_row, right_col = rect
        row_span = bottom_row - top_row + 1
        col_span = right_col - left_col + 1
        # Delegate -- raises ValueError on validation failure.
        self._grid.merge_cells(top_row, left_col, row_span, col_span)
        self._selection_start = (top_row, left_col)
        self._selection_end = (top_row, left_col)
        self._notify_grid_change()

    def split_selection(self) -> None:
        """Split the currently selected merged cell.

        Operates on the selection-start cell.  If the start cell is a
        covered cell, resolves to its anchor before splitting.  Raises
        ``ValueError`` if no selection or if the cell is not merged.
        """
        if self._selection_start is None:
            raise ValueError("No cell selected for split.")
        row, col = self._selection_start
        cell = self._grid.get_cell(row, col)
        # Resolve covered cell to its anchor.
        if (
            cell.is_covered
            and cell.anchor_row is not None
            and cell.anchor_col is not None
        ):
            row, col = cell.anchor_row, cell.anchor_col
        # Delegate -- raises ValueError if the cell is not merged.
        self._grid.split_cell(row, col)
        self._selection_start = (row, col)
        self._selection_end = (row, col)
        self._notify_grid_change()

    # -- insert / delete / alignment -----------------------------------------

    def insert_row_above(self) -> None:
        """Insert an empty row above the selected cell.

        Raises ValueError if no cell is selected.
        """
        if self._selection_start is None:
            raise ValueError("No cell selected.")
        row, col = self._selection_start
        self._grid.insert_row(row)
        self._selection_start = (row + 1, col)
        self._selection_end = self._selection_start
        self._notify_grid_change()

    def insert_row_below(self) -> None:
        """Insert an empty row below the selected cell.

        Raises ValueError if no cell is selected.
        """
        if self._selection_start is None:
            raise ValueError("No cell selected.")
        row, _col = self._selection_start
        self._grid.insert_row(row + 1)
        self._selection_end = self._selection_start
        self._notify_grid_change()

    def insert_col_left(self) -> None:
        """Insert an empty column to the left of the selected cell.

        Raises ValueError if no cell is selected.
        """
        if self._selection_start is None:
            raise ValueError("No cell selected.")
        row, col = self._selection_start
        self._grid.insert_col(col)
        self._selection_start = (row, col + 1)
        self._selection_end = self._selection_start
        self._notify_grid_change()

    def insert_col_right(self) -> None:
        """Insert an empty column to the right of the selected cell.

        Raises ValueError if no cell is selected.
        """
        if self._selection_start is None:
            raise ValueError("No cell selected.")
        _row, col = self._selection_start
        self._grid.insert_col(col + 1)
        self._selection_end = self._selection_start
        self._notify_grid_change()

    def delete_row(self) -> None:
        """Delete the row containing the selected cell.

        Raises ValueError if no cell is selected, the grid has only one
        row, or the row contains a multirow anchor.
        """
        if self._selection_start is None:
            raise ValueError("No cell selected.")
        if self._grid.num_rows <= MIN_GRID_DIMENSION:
            raise ValueError("Cannot delete the last remaining row.")
        row, col = self._selection_start
        self._grid.delete_row(row)
        new_row = min(row, self._grid.num_rows - 1)
        self._selection_start = (new_row, col)
        self._selection_end = self._selection_start
        self._notify_grid_change()

    def delete_col(self) -> None:
        """Delete the column containing the selected cell.

        Raises ValueError if no cell is selected, the grid has only one
        column, or the column contains a multicolumn anchor.
        """
        if self._selection_start is None:
            raise ValueError("No cell selected.")
        if self._grid.num_cols <= MIN_GRID_DIMENSION:
            raise ValueError("Cannot delete the last remaining column.")
        row, col = self._selection_start
        self._grid.delete_col(col)
        new_col = min(col, self._grid.num_cols - 1)
        self._selection_start = (row, new_col)
        self._selection_end = self._selection_start
        self._notify_grid_change()

    def set_selected_alignment(self, alignment: CellAlignment | None) -> None:
        """Set the horizontal alignment of the selected cell.

        Pass ``None`` to clear the per-cell override and inherit the
        global alignment from ConversionOptions.

        Raises ValueError if no cell is selected or the cell is covered.
        """
        if self._selection_start is None:
            raise ValueError("No cell selected.")
        row, col = self._selection_start
        self._grid.set_alignment(row, col, alignment)
        self._notify_grid_change()

    # -- private: cell building ----------------------------------------------

    def _build_cell_controls(self) -> list[ft.Control]:
        """Create positioned Container controls for every non-covered cell."""
        controls: list[ft.Control] = []
        for r in range(self._grid.num_rows):
            for c in range(self._grid.num_cols):
                cell = self._grid.get_cell(r, c)
                if cell.is_covered:
                    continue
                control = self._build_single_cell(
                    content=cell.content,
                    row=r,
                    col=c,
                    colspan=cell.colspan,
                    rowspan=cell.rowspan,
                    is_header=r == 0 and self._grid.has_header,
                )
                self._cell_containers[(r, c)] = control
                controls.append(control)
        return controls

    def _build_single_cell(
        self,
        *,
        content: str,
        row: int,
        col: int,
        colspan: int,
        rowspan: int,
        is_header: bool,
    ) -> ft.Container:
        """Create a positioned cell Container with an editable TextField.

        Width and height scale by *colspan* and *rowspan* so that merged
        regions appear as a single large cell.
        """
        x = col * CELL_WIDTH
        y = row * CELL_HEIGHT
        w = colspan * CELL_WIDTH
        h = rowspan * CELL_HEIGHT
        bg = HEADER_BG if is_header else CELL_BG
        text_weight = ft.FontWeight.BOLD if is_header else None

        def on_change(e: ft.ControlEvent, r: int = row, c: int = col) -> None:
            self.apply_edit(r, c, e.data)

        def on_focus(
            e: ft.ControlEvent,
            r: int = row,
            c: int = col,
        ) -> None:
            self._on_cell_click(r, c)
            page = e.page
            if page is not None:
                page.update()

        text_field = ft.TextField(
            value=content,
            text_size=FONT_SIZE,
            text_style=ft.TextStyle(weight=text_weight),
            border=ft.InputBorder.NONE,
            content_padding=ft.Padding(CELL_PADDING, 0, CELL_PADDING, 0),
            dense=True,
            on_change=on_change,
            on_focus=on_focus,
        )

        return ft.Container(
            content=text_field,
            left=x,
            top=y,
            width=w,
            height=h,
            bgcolor=bg,
            border=ft.Border.all(BORDER_WIDTH, BORDER_COLOR),
            padding=0,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    # -- private: selection --------------------------------------------------

    def _on_cell_click(self, row: int, col: int) -> None:
        """Handle a cell click for selection.

        Normal mode: replaces the selection with a single cell.
        Range mode: if a start cell already exists, sets the end cell
        to form a rectangular range; otherwise sets a new start.
        """
        if self._range_mode and self._selection_start is not None:
            self._selection_end = (row, col)
        else:
            self._selection_start = (row, col)
            self._selection_end = (row, col)
        self._update_selection_highlight()

    def _update_selection_highlight(self) -> None:
        """Update visual highlighting for all cells based on current selection."""
        rect = self.get_selection_rect()
        for (r, c), container in self._cell_containers.items():
            in_selection = rect is not None and _cell_overlaps_rect(
                self._grid, r, c, rect
            )
            is_header = r == 0 and self._grid.has_header
            if in_selection:
                container.bgcolor = SELECTED_BG
                container.border = ft.Border.all(
                    SELECTED_BORDER_WIDTH, SELECTED_BORDER_COLOR
                )
            else:
                container.bgcolor = HEADER_BG if is_header else CELL_BG
                container.border = ft.Border.all(BORDER_WIDTH, BORDER_COLOR)

    # -- backward compatibility aliases (C1 tests call these) ----------------

    def _select_cell(self, row: int, col: int) -> None:
        """Select a single cell. C1-compatible alias for ``_on_cell_click``."""
        self._on_cell_click(row, col)

    def _deselect_current(self) -> None:
        """Clear selection and reset all cells to default style."""
        self._selection_start = None
        self._selection_end = None
        self._update_selection_highlight()


# -- Module-level helpers ----------------------------------------------------


def _cell_overlaps_rect(
    grid: TableGrid,
    cell_row: int,
    cell_col: int,
    rect: tuple[int, int, int, int],
) -> bool:
    """Check if a cell (possibly multi-span) overlaps a selection rectangle.

    Args:
        grid: The table grid containing the cell.
        cell_row: Row of the cell anchor.
        cell_col: Column of the cell anchor.
        rect: ``(row0, col0, row1, col1)`` inclusive rectangle.

    Returns:
        True if the cell occupies any position within the rectangle.
    """
    r0, c0, r1, c1 = rect
    cell = grid.get_cell(cell_row, cell_col)
    cell_bottom = cell_row + cell.rowspan - 1
    cell_right = cell_col + cell.colspan - 1
    return cell_row <= r1 and cell_bottom >= r0 and cell_col <= c1 and cell_right >= c0


def grid_has_merges(grid: TableGrid | None) -> bool:
    """Return True if the grid contains any merged cells.

    A grid has merges if any non-covered cell has colspan > 1 or
    rowspan > 1.  Returns False if the grid is None or empty.
    """
    if grid is None:
        return False
    return any(
        cell.colspan > 1 or cell.rowspan > 1
        for row in grid.rows
        for cell in row
        if not cell.is_covered
    )


# -- Backward-compatible public API ------------------------------------------


def build_grid_view(
    grid: TableGrid,
    on_cell_edit: CellEditCallback | None = None,
) -> ft.Control:
    """Build an interactive grid editor for a TableGrid.

    Convenience wrapper around :class:`GridEditor` that preserves the
    original ``build_grid_view(grid)`` call signature while accepting
    an optional *on_cell_edit* callback for live editing.

    Args:
        grid: The table grid to render and edit.
        on_cell_edit: Optional callback invoked after a cell edit.

    Returns:
        A Flet Container wrapping the grid editor, or a placeholder
        Text when the grid is empty.
    """
    editor = GridEditor(grid, on_cell_edit)
    return editor.build()
