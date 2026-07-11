"""Grid editor toolbar: merge/split, insert/delete, alignment controls.

Encapsulates the grid editing toolbar UI and event handlers so that
main.py stays focused on page-level layout and state management.
All grid operations delegate to GridEditor methods; status and page
updates are managed via caller-supplied callbacks.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from grid_editor import GridEditor
from table_model import CellAlignment

# -- Type aliases for caller-supplied callbacks --------------------------------

EditorGetter = Callable[[], GridEditor | None]
StatusSetter = Callable[[str, bool], None]
PageUpdater = Callable[[], None]

# -- Alignment label-to-enum mapping -------------------------------------------

_ALIGNMENT_MAP: dict[str, CellAlignment | None] = {
    "Left": CellAlignment.LEFT,
    "Center": CellAlignment.CENTER,
    "Right": CellAlignment.RIGHT,
    "Inherit": None,
}

_NO_DATA_MSG = "No data loaded. Load a file first."


# -- Public builder ------------------------------------------------------------


def build_grid_toolbar(
    get_editor: EditorGetter,
    set_status: StatusSetter,
    page_update: PageUpdater,
) -> tuple[ft.Column, ft.OutlinedButton]:
    """Build the grid editor toolbar with all editing controls.

    Returns ``(toolbar_column, range_mode_button)`` so the caller can
    reset the range-mode visual when the editor is rebuilt.

    Args:
        get_editor: Returns the current GridEditor, or None if no data.
        set_status: ``(message, is_error)`` callback for status display.
        page_update: Callback to push Flet page updates.
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
        try:
            action(editor)
            set_status(success_msg, False)
        except ValueError as err:
            set_status(str(err), True)
        page_update()

    # -- range mode -----------------------------------------------------------

    range_mode_button = ft.OutlinedButton(
        content="Range Select",
        icon=ft.Icons.SELECT_ALL,
    )

    async def on_toggle_range_mode(_: ft.ControlEvent) -> None:
        editor = get_editor()
        if editor is None:
            set_status(_NO_DATA_MSG, True)
            page_update()
            return
        new_mode = not editor.range_mode
        editor.range_mode = new_mode
        if new_mode:
            range_mode_button.style = ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_100,
            )
            set_status(
                "Range select ON. Click a second cell to define a range.",
                False,
            )
        else:
            range_mode_button.style = None
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

    alignment_dropdown = ft.Dropdown(
        label="Cell align",
        value="Inherit",
        options=[ft.dropdown.Option(label) for label in _ALIGNMENT_MAP],
        dense=True,
        width=140,
    )

    async def on_alignment_change(_: ft.ControlEvent) -> None:
        editor = get_editor()
        if editor is None:
            set_status(_NO_DATA_MSG, True)
            page_update()
            return
        selected = alignment_dropdown.value or "Inherit"
        alignment = _ALIGNMENT_MAP.get(selected)
        try:
            editor.set_selected_alignment(alignment)
            display = selected if selected != "Inherit" else "Inherit (global default)"
            set_status(f"Alignment set to {display}.", False)
        except ValueError as err:
            set_status(str(err), True)
        page_update()

    alignment_dropdown.on_select = on_alignment_change

    # -- build toolbar layout -------------------------------------------------

    merge_split_row = ft.Row(
        controls=[
            range_mode_button,
            ft.OutlinedButton(
                content="Merge cells",
                icon=ft.Icons.MERGE_TYPE,
                on_click=on_merge_cells,
            ),
            ft.OutlinedButton(
                content="Split cell",
                icon=ft.Icons.CALL_SPLIT,
                on_click=on_split_cell,
            ),
            alignment_dropdown,
        ],
        spacing=8,
    )

    insert_delete_row = ft.Row(
        controls=[
            ft.OutlinedButton(
                content="Insert row ↑",
                on_click=on_insert_row_above,
            ),
            ft.OutlinedButton(
                content="Insert row ↓",
                on_click=on_insert_row_below,
            ),
            ft.OutlinedButton(
                content="Insert col ←",
                on_click=on_insert_col_left,
            ),
            ft.OutlinedButton(
                content="Insert col →",
                on_click=on_insert_col_right,
            ),
            ft.OutlinedButton(
                content="Delete row",
                icon=ft.Icons.DELETE_OUTLINE,
                on_click=on_delete_row,
            ),
            ft.OutlinedButton(
                content="Delete col",
                icon=ft.Icons.DELETE_OUTLINE,
                on_click=on_delete_col,
            ),
        ],
        spacing=8,
        wrap=True,
        run_spacing=4,
    )

    toolbar = ft.Column(
        controls=[merge_split_row, insert_delete_row],
        spacing=6,
    )

    return toolbar, range_mode_button
