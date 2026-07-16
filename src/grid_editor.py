"""Interactive Flet grid editor for TableGrid with range selection and merge/split.

Renders a TableGrid as a Flet control with cells positioned in a Stack,
visually reflecting merged cells (colspan/rowspan).  Each non-covered cell
is an editable TextField.  Supports single-cell and rectangular range
selection (via an explicit "range mode" toggle).  Merge and split operations
delegate to TableGrid and invoke a callback so the caller can rebuild.

For grids at or above ``VIRTUALIZE_ROW_THRESHOLD`` rows, viewport
windowing is activated: only cells whose row span intersects the
currently visible scroll window (plus an overscan buffer) are built
as Flet controls.  The full grid height is preserved on the Stack
container so scrollbar sizing stays correct.  The caller must wire
the scroll container's ``on_scroll`` to ``GridEditor.handle_scroll``
to drive re-windowing on scroll.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from converter import ConversionOptions
from table_model import CellAlignment, TableGrid

# -- Layout constants --------------------------------------------------------

CELL_WIDTH = 120
CELL_HEIGHT = 40
ROW_SELECTOR_WIDTH = 40
COLUMN_SELECTOR_HEIGHT = 28
HEADER_BG = ft.Colors.BLUE_GREY_800
CELL_BG = ft.Colors.BLUE_GREY_900
SELECTED_BG = ft.Colors.BLUE_900
SELECTOR_BG = ft.Colors.BLUE_GREY_700
SELECTED_SELECTOR_BG = ft.Colors.BLUE_700
BORDER_COLOR = ft.Colors.BLUE_GREY_600
SELECTED_BORDER_COLOR = ft.Colors.BLUE_300
TEXT_COLOR = ft.Colors.GREY_100
CURSOR_COLOR = ft.Colors.BLUE_200
BOOKTABS_RULE_COLOR = ft.Colors.BLUE_GREY_400
BORDER_WIDTH = 1
SELECTED_BORDER_WIDTH = 2
BOOKTABS_HEAVY_BORDER_WIDTH = 2
FONT_SIZE = 13
CELL_PADDING = 4
MIN_GRID_DIMENSION = 1

_TEXT_ALIGNMENT_MAP: dict[str, ft.TextAlign] = {
    "l": ft.TextAlign.LEFT,
    "c": ft.TextAlign.CENTER,
    "r": ft.TextAlign.RIGHT,
}

# -- Viewport windowing constants --------------------------------------------

VIRTUALIZE_ROW_THRESHOLD = 50
"""Row count at or above which viewport windowing activates."""

VIEWPORT_OVERSCAN_ROWS = 5
"""Extra rows rendered above and below the visible viewport."""

DEFAULT_VIEWPORT_HEIGHT = 800.0
"""Initial viewport height estimate (pixels) before the first scroll event."""

# -- Callback type aliases ---------------------------------------------------

CellEditCallback = Callable[[int, int, str], None]
GridChangeCallback = Callable[[], None]
SelectionChangeCallback = Callable[[int, int], None]
BeforeEditCallback = Callable[[int, int], None]


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
        on_selection_change: Optional callback invoked when the primary
            selected cell changes (single-click).  Signature:
            ``(row, col) -> None``.
        on_before_edit: Optional callback invoked **before** a cell's
            content is mutated by ``apply_edit``.  Useful for snapshotting
            pre-edit state (undo coalescing).  Signature:
            ``(row, col) -> None``.
        options: Conversion options used to style the editable preview.
    """

    def __init__(
        self,
        grid: TableGrid,
        on_cell_edit: CellEditCallback | None = None,
        on_grid_change: GridChangeCallback | None = None,
        on_selection_change: SelectionChangeCallback | None = None,
        on_before_edit: BeforeEditCallback | None = None,
        options: ConversionOptions | None = None,
    ) -> None:
        self._grid = grid
        self._on_cell_edit = on_cell_edit
        self._on_grid_change = on_grid_change
        self._on_selection_change = on_selection_change
        self._on_before_edit = on_before_edit
        self._options = options or ConversionOptions()

        self._selection_start: tuple[int, int] | None = None
        self._selection_end: tuple[int, int] | None = None
        self._range_mode: bool = False
        self._selection_scope: str = "cell"

        self._cell_containers: dict[tuple[int, int], ft.Container] = {}
        self._row_selector_containers: dict[int, ft.Container] = {}
        self._column_selector_containers: dict[int, ft.Container] = {}
        self._corner_selector: ft.Container | None = None

        # Windowing state (large-table optimization)
        self._stack: ft.Stack | None = None
        self._windowed: bool = False
        self._visible_range: tuple[int, int] = (0, 0)

    # -- public API ----------------------------------------------------------

    def build(self) -> ft.Control:
        """Build the interactive grid as a Flet control.

        Returns a ``Container`` wrapping a ``Stack`` of positioned cell
        controls, or a placeholder ``Text`` when the grid is empty.

        For grids at or above ``VIRTUALIZE_ROW_THRESHOLD`` rows, only
        cells in the initial viewport (plus overscan) are built.  Wire
        the scroll container's ``on_scroll`` to ``handle_scroll`` to
        update visible cells as the user scrolls.
        """
        if self._grid.num_rows == 0 or self._grid.num_cols == 0:
            return ft.Text("No data to display.", color=ft.Colors.GREY_500)

        total_width = ROW_SELECTOR_WIDTH + self._grid.num_cols * CELL_WIDTH
        total_height = COLUMN_SELECTOR_HEIGHT + self._grid.num_rows * CELL_HEIGHT
        self._cell_containers.clear()
        self._clear_selector_controls()
        self._windowed = should_use_windowing(self._grid.num_rows)

        if self._windowed:
            self._visible_range = compute_visible_row_range(
                self._grid.num_rows,
                CELL_HEIGHT,
                0.0,
                DEFAULT_VIEWPORT_HEIGHT,
                VIEWPORT_OVERSCAN_ROWS,
            )
            cell_controls = self._build_cell_controls_for_range(
                self._visible_range,
            )
        else:
            cell_controls = self._build_cell_controls()

        selector_controls = self._build_selector_controls(
            self._visible_range if self._windowed else None
        )
        self._stack = ft.Stack(controls=[*cell_controls, *selector_controls])
        return ft.Container(
            content=self._stack,
            width=total_width,
            height=total_height,
        )

    def handle_scroll(self, event: ft.OnScrollEvent) -> bool:
        """Update the windowed viewport in response to a scroll event.

        Recomputes the visible row range and rebuilds cell controls when
        the range changes.  The caller should call ``page.update()``
        when this method returns ``True``.

        Note: editing a cell that scrolls out of the visible window
        will lose focus.  This is expected for viewport windowing.

        Returns:
            True if visible controls were rebuilt; False otherwise.
        """
        if not self._windowed or self._stack is None:
            return False
        new_range = compute_visible_row_range(
            self._grid.num_rows,
            CELL_HEIGHT,
            event.pixels,
            event.viewport_dimension,
            VIEWPORT_OVERSCAN_ROWS,
        )
        if new_range == self._visible_range:
            return False
        self._visible_range = new_range
        self._cell_containers.clear()
        self._clear_selector_controls()
        cell_controls = self._build_cell_controls_for_range(new_range)
        selector_controls = self._build_selector_controls(new_range)
        self._stack.controls = [*cell_controls, *selector_controls]
        self._update_selection_highlight()
        return True

    def apply_edit(self, row: int, col: int, text: str) -> None:
        """Apply a text edit to the grid and invoke the callback.

        Fires *on_before_edit* **before** mutating the ``TableGrid``
        (allows the caller to snapshot for undo).  Then mutates via
        ``set_content`` and invokes *on_cell_edit* if provided.
        """
        if self._on_before_edit is not None:
            self._on_before_edit(row, col)
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
        if (
            not enabled
            and self._selection_start is not None
            and self._selection_scope == "cell"
        ):
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

    def select_row(self, row: int) -> None:
        """Select an entire row through its preview-side row selector."""
        if row < 0 or row >= self._grid.num_rows:
            raise IndexError("Row selection is outside the grid.")
        self._selection_start = (row, 0)
        self._selection_end = (row, self._grid.num_cols - 1)
        self._selection_scope = "row"
        self._notify_selection_change(row, 0)
        self._update_selection_highlight()

    def select_column(self, col: int) -> None:
        """Select an entire column through its preview-top column selector."""
        if col < 0 or col >= self._grid.num_cols:
            raise IndexError("Column selection is outside the grid.")
        self._selection_start = (0, col)
        self._selection_end = (self._grid.num_rows - 1, col)
        self._selection_scope = "column"
        self._notify_selection_change(0, col)
        self._update_selection_highlight()

    def select_all(self) -> None:
        """Select the entire table through the preview corner selector."""
        self._selection_start = (0, 0)
        self._selection_end = (self._grid.num_rows - 1, self._grid.num_cols - 1)
        self._selection_scope = "all"
        self._notify_selection_change(0, 0)
        self._update_selection_highlight()

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

    def _build_cell_controls_for_range(
        self, row_range: tuple[int, int]
    ) -> list[ft.Control]:
        """Create positioned cell controls for the given row range.

        Includes cells whose rowspan straddles the range boundary so
        that merged cells partially overlapping the viewport render
        correctly.
        """
        first_row, last_row = row_range
        controls: list[ft.Control] = []
        for r in range(self._grid.num_rows):
            if r > last_row:
                break
            for c in range(self._grid.num_cols):
                cell = self._grid.get_cell(r, c)
                if cell.is_covered:
                    continue
                if not cell_visible_in_row_range(r, cell.rowspan, first_row, last_row):
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

    def _clear_selector_controls(self) -> None:
        """Clear cached row and column selector controls before rebuilding."""
        self._row_selector_containers.clear()
        self._column_selector_containers.clear()
        self._corner_selector = None

    def _build_selector_controls(
        self,
        row_range: tuple[int, int] | None,
    ) -> list[ft.Control]:
        """Build clickable spreadsheet-style row and column selectors."""
        controls: list[ft.Control] = []

        def select_all(event: ft.ControlEvent) -> None:
            self.select_all()
            if event.page is not None:
                event.page.update()

        corner = self._selector_container(
            label="",
            left=0,
            top=0,
            width=ROW_SELECTOR_WIDTH,
            height=COLUMN_SELECTOR_HEIGHT,
            on_click=select_all,
        )
        self._corner_selector = corner
        controls.append(corner)

        for col in range(self._grid.num_cols):

            def select_column(event: ft.ControlEvent, col_index: int = col) -> None:
                self.select_column(col_index)
                if event.page is not None:
                    event.page.update()

            selector = self._selector_container(
                label=_column_label(col),
                left=ROW_SELECTOR_WIDTH + col * CELL_WIDTH,
                top=0,
                width=CELL_WIDTH,
                height=COLUMN_SELECTOR_HEIGHT,
                on_click=select_column,
            )
            self._column_selector_containers[col] = selector
            controls.append(selector)

        first_row, last_row = row_range or (0, self._grid.num_rows - 1)
        for row in range(first_row, last_row + 1):

            def select_row(event: ft.ControlEvent, row_index: int = row) -> None:
                self.select_row(row_index)
                if event.page is not None:
                    event.page.update()

            selector = self._selector_container(
                label=str(row + 1),
                left=0,
                top=COLUMN_SELECTOR_HEIGHT + row * CELL_HEIGHT,
                width=ROW_SELECTOR_WIDTH,
                height=CELL_HEIGHT,
                on_click=select_row,
            )
            self._row_selector_containers[row] = selector
            controls.append(selector)

        return controls

    def _selector_container(
        self,
        *,
        label: str,
        left: int,
        top: int,
        width: int,
        height: int,
        on_click: Callable[[ft.ControlEvent], None],
    ) -> ft.Container:
        """Create one clickable row, column, or corner selector."""
        return ft.Container(
            content=ft.Text(label, color=TEXT_COLOR, weight=ft.FontWeight.BOLD),
            left=left,
            top=top,
            width=width,
            height=height,
            alignment=ft.Alignment.CENTER,
            bgcolor=SELECTOR_BG,
            border=ft.Border.all(BORDER_WIDTH, BORDER_COLOR),
            on_click=on_click,
        )

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
        x = ROW_SELECTOR_WIDTH + col * CELL_WIDTH
        y = COLUMN_SELECTOR_HEIGHT + row * CELL_HEIGHT
        w = colspan * CELL_WIDTH
        h = rowspan * CELL_HEIGHT
        bg = HEADER_BG if is_header else CELL_BG
        text_weight = self._cell_text_weight(row, col)
        text_alignment = self._cell_text_alignment(row, col)

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
            text_style=ft.TextStyle(color=TEXT_COLOR, weight=text_weight),
            text_align=text_alignment,
            cursor_color=CURSOR_COLOR,
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
            border=self._cell_border(row, rowspan),
            padding=0,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    def _cell_text_weight(self, row: int, col: int) -> ft.FontWeight | None:
        """Return the weight produced by the current bold options."""
        if self._options.bold_first_row and row == 0:
            return ft.FontWeight.BOLD
        if self._options.bold_first_column and col == 0 and row != 0:
            return ft.FontWeight.BOLD
        return None

    def _cell_text_alignment(self, row: int, col: int) -> ft.TextAlign:
        """Resolve a per-cell alignment override or the global default."""
        alignment = self._grid.get_cell(row, col).alignment
        alignment_letter = (
            alignment.value if alignment else self._options.text_alignment
        )
        return _TEXT_ALIGNMENT_MAP.get(alignment_letter, ft.TextAlign.CENTER)

    def _cell_border(self, row: int, rowspan: int) -> ft.Border | None:
        """Build the visual border corresponding to the LaTeX border style."""
        style = self._options.border_style
        if style == "all":
            return ft.Border.all(BORDER_WIDTH, BORDER_COLOR)
        if style == "none":
            return None

        is_first_row = row == 0
        is_last_row = row + rowspan >= self._grid.num_rows
        if style == "booktabs":
            top_width = BOOKTABS_HEAVY_BORDER_WIDTH if is_first_row else 0
            bottom_width = (
                BOOKTABS_HEAVY_BORDER_WIDTH
                if is_last_row
                else BORDER_WIDTH
                if is_first_row
                else 0
            )
            return _horizontal_border(top_width, bottom_width, BOOKTABS_RULE_COLOR)

        top_width = BORDER_WIDTH if is_first_row else 0
        bottom_width = BORDER_WIDTH if is_first_row or is_last_row else 0
        return _horizontal_border(top_width, bottom_width, BORDER_COLOR)

    # -- private: selection --------------------------------------------------

    def _on_cell_click(self, row: int, col: int) -> None:
        """Handle a cell click for selection.

        Normal mode: replaces the selection with a single cell and
        fires *on_selection_change*.
        Range mode: if a start cell already exists, sets the end cell
        to form a rectangular range; otherwise sets a new start.
        """
        if self._range_mode and self._selection_start is not None:
            self._selection_end = (row, col)
        else:
            self._selection_start = (row, col)
            self._selection_end = (row, col)
            self._notify_selection_change(row, col)
        self._selection_scope = "cell"
        self._update_selection_highlight()

    def _notify_selection_change(self, row: int, col: int) -> None:
        """Notify the page that the primary selection cell changed."""
        if self._on_selection_change is not None:
            self._on_selection_change(row, col)

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
                cell = self._grid.get_cell(r, c)
                container.border = self._cell_border(r, cell.rowspan)
        for row, selector in self._row_selector_containers.items():
            selected = self._selection_scope in {"row", "all"} and (
                self._selection_scope == "all"
                or self._selection_start is not None
                and self._selection_start[0] == row
            )
            self._style_selector(selector, selected)
        for col, selector in self._column_selector_containers.items():
            selected = self._selection_scope in {"column", "all"} and (
                self._selection_scope == "all"
                or self._selection_start is not None
                and self._selection_start[1] == col
            )
            self._style_selector(selector, selected)
        if self._corner_selector is not None:
            self._style_selector(self._corner_selector, self._selection_scope == "all")

    def _style_selector(self, selector: ft.Container, selected: bool) -> None:
        """Apply selected or default styling to a row/column selector."""
        selector.bgcolor = SELECTED_SELECTOR_BG if selected else SELECTOR_BG
        selector.border = ft.Border.all(
            SELECTED_BORDER_WIDTH if selected else BORDER_WIDTH,
            SELECTED_BORDER_COLOR if selected else BORDER_COLOR,
        )

    # -- backward compatibility aliases (C1 tests call these) ----------------

    def _select_cell(self, row: int, col: int) -> None:
        """Select a single cell. C1-compatible alias for ``_on_cell_click``."""
        self._on_cell_click(row, col)

    def _deselect_current(self) -> None:
        """Clear selection and reset all cells to default style."""
        self._selection_start = None
        self._selection_end = None
        self._selection_scope = "cell"
        self._update_selection_highlight()


# -- Module-level helpers ----------------------------------------------------


def _horizontal_border(
    top_width: float,
    bottom_width: float,
    color: ft.ColorValue,
) -> ft.Border:
    """Create a border containing horizontal rules only."""
    return ft.Border(
        top=ft.BorderSide(top_width, color) if top_width else None,
        bottom=ft.BorderSide(bottom_width, color) if bottom_width else None,
    )


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


def _column_label(index: int) -> str:
    """Return spreadsheet-style column labels: A..Z, AA..AZ, and so on."""
    label = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def compute_visible_row_range(
    total_rows: int,
    row_height: int,
    viewport_top: float,
    viewport_height: float,
    overscan_rows: int,
) -> tuple[int, int]:
    """Compute the inclusive range of rows visible in the viewport.

    Pure function for viewport windowing math.  Converts pixel offsets
    to row indices, adds overscan, and clamps to grid bounds.

    Args:
        total_rows: Total number of rows in the grid.
        row_height: Height of a single row in pixels.
        viewport_top: Vertical scroll offset from the top in pixels.
        viewport_height: Height of the visible viewport in pixels.
        overscan_rows: Extra rows to render beyond the viewport edges.

    Returns:
        ``(first_row, last_row)`` inclusive, clamped to
        ``[0, total_rows - 1]``.
    """
    if total_rows <= 0 or row_height <= 0:
        return (0, 0)
    first_row = max(0, int(viewport_top / row_height) - overscan_rows)
    viewport_bottom = viewport_top + viewport_height
    last_row = min(
        total_rows - 1,
        int(viewport_bottom / row_height) + overscan_rows,
    )
    return (first_row, last_row)


def cell_visible_in_row_range(
    cell_row: int,
    cell_rowspan: int,
    visible_first: int,
    visible_last: int,
) -> bool:
    """Check if a cell's vertical span intersects the visible row range.

    Args:
        cell_row: Row index of the cell anchor.
        cell_rowspan: Number of rows the cell spans.
        visible_first: First visible row (inclusive).
        visible_last: Last visible row (inclusive).

    Returns:
        True if any part of the cell falls within the visible range.
    """
    cell_bottom = cell_row + cell_rowspan - 1
    return cell_bottom >= visible_first and cell_row <= visible_last


def should_use_windowing(
    total_rows: int,
    threshold: int = VIRTUALIZE_ROW_THRESHOLD,
) -> bool:
    """Return True if viewport windowing should be used for this grid.

    Args:
        total_rows: Number of rows in the grid.
        threshold: Row count at/above which windowing activates.
    """
    return total_rows >= threshold


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
