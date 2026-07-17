"""Grid editor toolbar: merge/split, insert/delete, alignment, undo/redo.

Encapsulates the grid editing toolbar UI and event handlers so that
main.py stays focused on page-level layout and state management.
All grid operations delegate to GridEditor methods; status and page
updates are managed via caller-supplied callbacks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from grid_editor import GridEditor
from table_model import CellAlignment
from ui_layout import BUTTON_HEIGHT, BUTTON_WIDTH

# -- Type aliases for caller-supplied callbacks --------------------------------

EditorGetter = Callable[[], GridEditor | None]
StatusSetter = Callable[[str, bool], None]
PageUpdater = Callable[[], None]
MutationHook = Callable[[], None]

# -- Alignment label-to-enum mapping -------------------------------------------

_ALIGNMENT_MAP: dict[str, CellAlignment | None] = {
    "Left": CellAlignment.LEFT,
    "Center": CellAlignment.CENTER,
    "Right": CellAlignment.RIGHT,
    "Inherit": None,
}

_REVERSE_ALIGNMENT_MAP: dict[CellAlignment | None, str] = {
    CellAlignment.LEFT: "Left",
    CellAlignment.CENTER: "Center",
    CellAlignment.RIGHT: "Right",
    None: "Inherit",
}

_NO_DATA_MSG = "No data loaded. Load a file first."


# -- Public helper -------------------------------------------------------------


def alignment_to_label(alignment: CellAlignment | None) -> str:
    """Map a CellAlignment enum value (or None) to a dropdown display label."""
    return _REVERSE_ALIGNMENT_MAP.get(alignment, "Inherit")


# -- Return type ---------------------------------------------------------------


@dataclass
class ToolbarResult:
    """Return value of ``build_grid_toolbar`` exposing interactive controls."""

    toolbar: ft.Column
    range_mode_button: ft.IconButton
    undo_button: ft.IconButton
    redo_button: ft.IconButton
    set_alignment_display: Callable[[str], None]


# -- Public builder ------------------------------------------------------------


def build_grid_toolbar(
    get_editor: EditorGetter,
    set_status: StatusSetter,
    page_update: PageUpdater,
    on_before_mutation: MutationHook | None = None,
    on_mutation_failed: MutationHook | None = None,
    on_undo: MutationHook | None = None,
    on_redo: MutationHook | None = None,
) -> ToolbarResult:
    """Build the grid editor toolbar with all editing controls.

    Returns a ``ToolbarResult`` giving the caller access to controls
    that need external state updates (range-mode button, undo/redo
    buttons, alignment display setter).

    Args:
        get_editor: Returns the current GridEditor, or None if no data.
        set_status: ``(message, is_error)`` callback for status display.
        page_update: Callback to push Flet page updates.
        on_before_mutation: Called before each grid mutation to snapshot
            state for undo.
        on_mutation_failed: Called when a mutation raises ``ValueError``
            to discard the most recent snapshot.
        on_undo: Callback for the Undo button.
        on_redo: Callback for the Redo button.
    """

    # -- shared helper --------------------------------------------------------

    def _run_editor_action(
        action: Callable[[GridEditor], None],
        success_msg: str,
    ) -> None:
        """Execute an editor action with null-check and error handling."""
        editor = get_editor()
        if editor is None:
            set_status(_NO_DATA_MSG, True)
            page_update()
            return
        if on_before_mutation is not None:
            on_before_mutation()
        try:
            action(editor)
            set_status(success_msg, False)
        except ValueError as err:
            if on_mutation_failed is not None:
                on_mutation_failed()
            set_status(str(err), True)
        page_update()

    # -- range mode -----------------------------------------------------------

    range_mode_button = ft.IconButton(
        icon=ft.Icons.SELECT_ALL,
        selected=False,
        selected_icon=ft.Icons.SELECT_ALL,
        selected_icon_color=ft.Colors.BLUE_300,
        tooltip="Toggle range selection",
    )

    async def on_toggle_range_mode(_: ft.ControlEvent) -> None:
        editor = get_editor()
        if editor is None:
            set_status(_NO_DATA_MSG, True)
            page_update()
            return
        new_mode = not editor.range_mode
        editor.range_mode = new_mode
        range_mode_button.selected = new_mode
        if new_mode:
            set_status(
                "Range select ON. Click a second cell to define a range.",
                False,
            )
        else:
            set_status("Range select OFF. Single-cell selection.", False)
        page_update()

    range_mode_button.on_click = on_toggle_range_mode

    # -- merge / split --------------------------------------------------------

    async def on_merge_cells(_: ft.ControlEvent) -> None:
        _run_editor_action(
            lambda ed: ed.merge_selection(),
            "Cells merged successfully.",
        )

    async def on_split_cell(_: ft.ControlEvent) -> None:
        _run_editor_action(
            lambda ed: ed.split_selection(),
            "Cell split successfully.",
        )

    # -- insert / delete ------------------------------------------------------

    async def on_insert_row_above(_: ft.ControlEvent) -> None:
        _run_editor_action(
            lambda ed: ed.insert_row_above(),
            "Row inserted above.",
        )

    async def on_insert_row_below(_: ft.ControlEvent) -> None:
        _run_editor_action(
            lambda ed: ed.insert_row_below(),
            "Row inserted below.",
        )

    async def on_insert_col_left(_: ft.ControlEvent) -> None:
        _run_editor_action(
            lambda ed: ed.insert_col_left(),
            "Column inserted to the left.",
        )

    async def on_insert_col_right(_: ft.ControlEvent) -> None:
        _run_editor_action(
            lambda ed: ed.insert_col_right(),
            "Column inserted to the right.",
        )

    async def on_delete_row(_: ft.ControlEvent) -> None:
        _run_editor_action(
            lambda ed: ed.delete_row(),
            "Row deleted.",
        )

    async def on_delete_col(_: ft.ControlEvent) -> None:
        _run_editor_action(
            lambda ed: ed.delete_col(),
            "Column deleted.",
        )

    # -- alignment ------------------------------------------------------------

    _programmatic_update: list[bool] = [False]

    alignment_dropdown = ft.Dropdown(
        label="Cell align",
        value="Inherit",
        options=[ft.dropdown.Option(label) for label in _ALIGNMENT_MAP],
        dense=True,
    )

    def set_alignment_display(label: str) -> None:
        """Set the dropdown value programmatically without triggering handler."""
        _programmatic_update[0] = True
        alignment_dropdown.value = label
        _programmatic_update[0] = False

    async def on_alignment_change(_: ft.ControlEvent) -> None:
        if _programmatic_update[0]:
            return
        editor = get_editor()
        if editor is None:
            set_status(_NO_DATA_MSG, True)
            page_update()
            return
        selected = alignment_dropdown.value or "Inherit"
        alignment = _ALIGNMENT_MAP.get(selected)
        if on_before_mutation is not None:
            on_before_mutation()
        try:
            editor.set_selected_alignment(alignment)
            display = selected if selected != "Inherit" else "Inherit (global default)"
            set_status(f"Alignment set to {display}.", False)
        except ValueError as err:
            if on_mutation_failed is not None:
                on_mutation_failed()
            set_status(str(err), True)
        page_update()

    alignment_dropdown.on_select = on_alignment_change

    # -- undo / redo ----------------------------------------------------------

    undo_button = ft.IconButton(
        icon=ft.Icons.UNDO,
        tooltip="Undo",
        disabled=True,
    )
    redo_button = ft.IconButton(
        icon=ft.Icons.REDO,
        tooltip="Redo",
        disabled=True,
    )

    async def on_undo_click(_: ft.ControlEvent) -> None:
        if on_undo is not None:
            on_undo()

    async def on_redo_click(_: ft.ControlEvent) -> None:
        if on_redo is not None:
            on_redo()

    undo_button.on_click = on_undo_click
    redo_button.on_click = on_redo_click

    # -- build toolbar layout -------------------------------------------------

    merge_button = ft.IconButton(
        icon=ft.Icons.MERGE_TYPE,
        tooltip="Merge selected cells",
        on_click=on_merge_cells,
    )
    split_button = ft.IconButton(
        icon=ft.Icons.CALL_SPLIT,
        tooltip="Split selected cell",
        on_click=on_split_cell,
    )
    insert_row_above_button = ft.IconButton(
        icon=ft.Text("+↑", size=16, weight=ft.FontWeight.BOLD),
        tooltip="Insert row above",
        on_click=on_insert_row_above,
    )
    insert_row_below_button = ft.IconButton(
        icon=ft.Text("+↓", size=16, weight=ft.FontWeight.BOLD),
        tooltip="Insert row below",
        on_click=on_insert_row_below,
    )
    delete_row_button = ft.IconButton(
        icon=ft.Icons.DELETE_OUTLINE,
        tooltip="Delete selected row",
        on_click=on_delete_row,
    )
    insert_col_left_button = ft.IconButton(
        icon=ft.Text("←+", size=16, weight=ft.FontWeight.BOLD),
        tooltip="Insert column to the left",
        on_click=on_insert_col_left,
    )
    insert_col_right_button = ft.IconButton(
        icon=ft.Text("+→", size=16, weight=ft.FontWeight.BOLD),
        tooltip="Insert column to the right",
        on_click=on_insert_col_right,
    )
    delete_col_button = ft.IconButton(
        icon=ft.Icons.DELETE_OUTLINE,
        tooltip="Delete selected column",
        on_click=on_delete_col,
    )

    icon_buttons = [
        undo_button,
        redo_button,
        range_mode_button,
        merge_button,
        split_button,
        insert_row_above_button,
        insert_row_below_button,
        delete_row_button,
        insert_col_left_button,
        insert_col_right_button,
        delete_col_button,
    ]
    for button in icon_buttons:
        button.width = BUTTON_HEIGHT
        button.height = BUTTON_HEIGHT

    alignment_dropdown.width = BUTTON_WIDTH
    alignment_dropdown.height = BUTTON_HEIGHT

    def _build_group(label: str, controls: list[ft.Control]) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(label, size=12, color=ft.Colors.BLUE_GREY_300),
                    *controls,
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            border=ft.Border.all(1, ft.Colors.BLUE_GREY_700),
            border_radius=6,
            padding=4,
            expand=True,
        )

    primary_actions = ft.Row(
        controls=[
            _build_group("Edit", [undo_button, redo_button]),
            _build_group(
                "Cells",
                [range_mode_button, merge_button, split_button, alignment_dropdown],
            ),
        ],
        spacing=8,
        wrap=False,
    )

    structure_actions = ft.Row(
        controls=[
            _build_group(
                "Rows",
                [insert_row_above_button, insert_row_below_button, delete_row_button],
            ),
            _build_group(
                "Columns",
                [insert_col_left_button, insert_col_right_button, delete_col_button],
            ),
        ],
        spacing=8,
        wrap=False,
    )

    toolbar = ft.Column(
        controls=[primary_actions, structure_actions],
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    return ToolbarResult(
        toolbar=toolbar,
        range_mode_button=range_mode_button,
        undo_button=undo_button,
        redo_button=redo_button,
        set_alignment_display=set_alignment_display,
    )
