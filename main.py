from __future__ import annotations

import copy
from collections.abc import Callable
from typing import TYPE_CHECKING

import flet as ft

from converter import (
    ConversionOptions,
    dataframe_to_latex,
    parse_scale_factor,
    read_table_file,
)
from grid_converter import grid_to_latex
from grid_editor import GridEditor, grid_has_merges
from grid_history import GridHistory
from grid_toolbar import alignment_to_label, build_grid_toolbar
from preprocessing import (
    drop_duplicate_rows,
    drop_empty_rows_and_columns,
    transpose_dataframe,
)
from table_model import TableGrid, dataframe_to_grid, grid_to_dataframe
from ui_layout import (
    BUTTON_HEIGHT,
    BUTTON_WIDTH,
    CENTER_PANE_EXPAND,
    LEFT_PANE_EXPAND,
    PAGE_PADDING,
    PANE_PADDING,
    PANE_SPACING,
    PANEL_BORDER_RADIUS,
    PANEL_BORDER_WIDTH,
    PANEL_PADDING,
    PANEL_SPACING,
    RIGHT_PANE_EXPAND,
)

if TYPE_CHECKING:
    import pandas as pd

_SCALE_BOX_INPUT_ERROR = "Scale boxには正の数を入力してください。"


async def main(page: ft.Page) -> None:
    page.title = "Excel2TeX"
    page.padding = PAGE_PADDING
    page.spacing = PANE_SPACING
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.window.maximized = True

    clipboard = ft.Clipboard()
    page.services.append(clipboard)

    state: dict[str, object] = {
        "dataframe": None,
        "original_dataframe": None,
        "grid": None,
        "original_grid": None,
        "editor": None,
        "edit_session_cell": None,
    }

    history = GridHistory()

    # --- shared widgets ---

    selected_file_text = ft.Text("No file selected")
    status_text = ft.Text("Select a CSV or XLSX file to generate LaTeX.")
    output_field = ft.TextField(
        value="",
        read_only=True,
        multiline=True,
        min_lines=20,
        expand=True,
        filled=True,
        bgcolor=ft.Colors.BLUE_GREY_900,
        color=ft.Colors.GREY_100,
        border_color=ft.Colors.BLUE_GREY_600,
        focused_border_color=ft.Colors.BLUE_300,
        border_radius=6,
        hint_text="Generated LaTeX will appear here.",
    )
    grid_preview_content = ft.Container(
        content=ft.Text("No data loaded.", color=ft.Colors.GREY_500),
    )

    # --- Additional Info controls ---

    caption_field = ft.TextField(label="Caption", dense=True)
    label_field = ft.TextField(label="Label", dense=True)

    # --- Structure & Type controls ---

    table_type_dropdown = ft.Dropdown(
        label="Table type",
        value="tabular",
        options=[
            ft.dropdown.Option("tabular"),
            ft.dropdown.Option("longtable"),
            ft.dropdown.Option("tabularx"),
        ],
        dense=True,
    )
    full_document_checkbox = ft.Checkbox(label="Full document (MWE)", value=False)
    float_position_switch = ft.Switch(label="Float position [htbp]", value=True)
    scale_box_field = ft.TextField(
        label="Scale box",
        hint_text="e.g. 0.85 (blank = off)",
        value="",
        dense=True,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    # --- Style & Design controls ---

    border_style_dropdown = ft.Dropdown(
        label="Border style",
        value="all",
        options=[
            ft.dropdown.Option("all"),
            ft.dropdown.Option("horizontal"),
            ft.dropdown.Option("none"),
            ft.dropdown.Option("booktabs"),
        ],
        dense=True,
    )
    bold_first_row_checkbox = ft.Checkbox(label="Bold first row", value=False)
    bold_first_column_checkbox = ft.Checkbox(label="Bold first column", value=False)
    table_alignment_dropdown = ft.Dropdown(
        label="Table alignment",
        value="center",
        options=[
            ft.dropdown.Option("center"),
            ft.dropdown.Option("left"),
            ft.dropdown.Option("right"),
        ],
        dense=True,
    )
    text_alignment_dropdown = ft.Dropdown(
        label="Text alignment",
        value="c",
        options=[
            ft.dropdown.Option("l"),
            ft.dropdown.Option("c"),
            ft.dropdown.Option("r"),
        ],
        dense=True,
    )
    escape_switch = ft.Switch(label="Escape special chars", value=True)

    # --- helpers ---

    def set_status(message: str, is_error: bool = False) -> None:
        status_text.value = message
        status_text.color = ft.Colors.RED_700 if is_error else ft.Colors.GREEN_700

    def _build_options() -> ConversionOptions:
        """Gather all control values into a ConversionOptions."""
        table_type = table_type_dropdown.value or "tabular"
        scale_factor: float | None = None
        if table_type != "longtable":
            try:
                scale_factor = parse_scale_factor(scale_box_field.value or "")
            except ValueError:
                pass
        return ConversionOptions(
            caption=caption_field.value or None,
            label=label_field.value or None,
            text_alignment=text_alignment_dropdown.value or "c",
            table_alignment=table_alignment_dropdown.value or "center",
            bold_first_row=bool(bold_first_row_checkbox.value),
            bold_first_column=bool(bold_first_column_checkbox.value),
            use_float_position=bool(float_position_switch.value),
            float_position="htbp",
            escape=bool(escape_switch.value),
            border_style=border_style_dropdown.value or "all",
            table_type=table_type,
            full_document=bool(full_document_checkbox.value),
            scale_factor=scale_factor,
        )

    def render_output() -> None:
        grid = state["grid"]
        options = _build_options()
        if grid is not None:
            output_field.value = grid_to_latex(grid, options)
            return
        dataframe = state["dataframe"]
        if dataframe is None:
            return
        output_field.value = dataframe_to_latex(dataframe, options)

    # --- history helpers ---

    def _update_history_buttons() -> None:
        """Sync undo/redo button disabled state with history stacks."""
        undo_button.disabled = not history.can_undo
        redo_button.disabled = not history.can_redo

    def _record_history() -> None:
        """Push a pre-mutation snapshot of the current grid."""
        grid = state["grid"]
        if grid is not None:
            history.push(grid)
            _update_history_buttons()

    def _discard_last_history() -> None:
        """Rollback the last snapshot on failed mutation."""
        history.discard_last()
        _update_history_buttons()

    # --- grid callbacks ---

    def _on_before_edit(row: int, col: int) -> None:
        """Snapshot before the first keystroke on a new cell (coalescing).

        Only one snapshot is taken per edit session on the same cell.
        Switching to a different cell resets the session via
        ``_on_selection_change``.
        """
        if state.get("edit_session_cell") == (row, col):
            return
        state["edit_session_cell"] = (row, col)
        grid = state["grid"]
        if grid is not None:
            history.push(grid)
            _update_history_buttons()

    def _on_cell_edit(row: int, col: int, text: str) -> None:  # noqa: ARG001
        """Handle a cell content edit from the grid editor."""
        render_output()
        page.update()

    def _on_selection_change(row: int, col: int) -> None:
        """Update the alignment dropdown to reflect the selected cell."""
        state["edit_session_cell"] = None
        grid = state["grid"]
        if grid is None:
            return
        cell = grid.get_cell(row, col)
        label = alignment_to_label(cell.alignment)
        set_alignment_display(label)

    def _on_grid_change() -> None:
        """Called after a structural grid change (merge/split/insert/delete).

        Rebuilds the grid preview and re-renders the LaTeX output.
        Does NOT call page.update -- the caller handler is responsible.
        """
        state["edit_session_cell"] = None
        _refresh_grid_view()
        render_output()
        _update_history_buttons()

    def _on_grid_scroll(e: ft.OnScrollEvent) -> None:
        """Forward vertical scroll events to the editor for windowing."""
        editor = state.get("editor")
        if editor is not None and editor.handle_scroll(e):
            page.update()

    def _refresh_grid_view() -> None:
        """Rebuild the grid preview from the current grid state."""
        grid = state["grid"]
        if grid is None:
            grid_preview_content.content = ft.Text(
                "No data loaded.", color=ft.Colors.GREY_500
            )
            state["editor"] = None
            return
        editor = GridEditor(
            grid,
            on_cell_edit=_on_cell_edit,
            on_grid_change=_on_grid_change,
            on_selection_change=_on_selection_change,
            on_before_edit=_on_before_edit,
            options=_build_options(),
        )
        state["editor"] = editor
        grid_preview_content.content = editor.build()
        # Reset range mode visuals (new editor starts with range_mode=False).
        if range_mode_button is not None:
            range_mode_button.style = None

    # --- undo / redo handlers ---

    def _handle_undo() -> None:
        """Undo the last grid mutation."""
        grid = state["grid"]
        if grid is None:
            return
        restored = history.undo(grid)
        if restored is None:
            return
        state["grid"] = restored
        state["edit_session_cell"] = None
        _refresh_grid_view()
        render_output()
        _update_history_buttons()
        set_alignment_display("Inherit")
        set_status("Undo.")
        page.update()

    def _handle_redo() -> None:
        """Redo the last undone grid mutation."""
        grid = state["grid"]
        if grid is None:
            return
        restored = history.redo(grid)
        if restored is None:
            return
        state["grid"] = restored
        state["edit_session_cell"] = None
        _refresh_grid_view()
        render_output()
        _update_history_buttons()
        set_alignment_display("Inherit")
        set_status("Redo.")
        page.update()

    # --- preprocessing guard ---

    def _grid_has_merges() -> bool:
        """Return True if the current grid has any merged cells."""
        return grid_has_merges(state["grid"])

    _MERGE_GUARD_MSG = (
        "Preprocessing is disabled while merged cells exist. "
        "Reset or split merges first."
    )

    def _apply_preprocessing(
        operation: Callable[[pd.DataFrame], pd.DataFrame],
        message: str,
    ) -> None:
        """Apply a DataFrame preprocessing operation with merge guard."""
        if state["dataframe"] is None:
            set_status("No data loaded. Load a file first.", is_error=True)
            page.update()
            return
        if _grid_has_merges():
            set_status(_MERGE_GUARD_MSG, is_error=True)
            page.update()
            return
        grid = state["grid"]
        if not isinstance(grid, TableGrid):
            set_status("No editable table is available.", is_error=True)
            page.update()
            return
        history.push(grid)
        state["edit_session_cell"] = None
        current_dataframe = grid_to_dataframe(grid)
        state["dataframe"] = operation(current_dataframe)
        state["grid"] = dataframe_to_grid(state["dataframe"])
        _refresh_grid_view()
        render_output()
        _update_history_buttons()
        set_status(message)
        page.update()

    # --- event handlers ---

    async def on_option_change(event: ft.ControlEvent) -> None:
        scale_box_field.disabled = table_type_dropdown.value == "longtable"
        scale_box_field.error_text = None
        if not scale_box_field.disabled:
            try:
                parse_scale_factor(scale_box_field.value or "")
            except ValueError:
                scale_box_field.error_text = _SCALE_BOX_INPUT_ERROR
                set_status(_SCALE_BOX_INPUT_ERROR, is_error=True)
                page.update()
                return
        if event.control in preview_style_controls and state["grid"] is not None:
            _refresh_grid_view()
        render_output()
        page.update()

    async def open_file_picker(_: ft.ControlEvent) -> None:
        files = await file_picker.pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["csv", "xlsx"],
        )
        if not files:
            set_status("No file selected.", is_error=True)
            page.update()
            return

        selected_file = files[0]
        if selected_file.path is None:
            set_status("Selected file path is not available.", is_error=True)
            page.update()
            return

        try:
            dataframe = read_table_file(selected_file.path)
            state["original_dataframe"] = dataframe
            state["dataframe"] = dataframe.copy()
            grid = dataframe_to_grid(dataframe)
            state["original_grid"] = copy.deepcopy(grid)
            state["grid"] = grid
            history.clear()
            state["edit_session_cell"] = None
            _refresh_grid_view()
            render_output()
            _update_history_buttons()
        except Exception as error:
            output_field.value = ""
            state["dataframe"] = None
            state["original_dataframe"] = None
            state["grid"] = None
            state["original_grid"] = None
            _refresh_grid_view()
            selected_file_text.value = selected_file.name
            set_status(f"Could not convert file: {error}", is_error=True)
            page.update()
            return

        selected_file_text.value = selected_file.name
        set_status("LaTeX code generated.")
        page.update()

    async def copy_output(_: ft.ControlEvent) -> None:
        if not output_field.value:
            set_status("There is no LaTeX code to copy.", is_error=True)
            page.update()
            return

        await clipboard.set(output_field.value)
        set_status("Copied LaTeX code to clipboard.")
        page.update()

    # --- Flet 0.85.3 save_file API (file_picker.py:247-301) ---
    # async save_file(...) -> Optional[str]
    # On desktop: returns the chosen file path string, or None if cancelled.
    # The file is NOT created by Flet; we must write it ourselves.

    async def download_output(_: ft.ControlEvent) -> None:
        if state["dataframe"] is None:
            set_status("No data loaded. Load a file first.", is_error=True)
            page.update()
            return

        if not output_field.value:
            set_status("There is no LaTeX code to download.", is_error=True)
            page.update()
            return

        save_path = await file_picker.save_file(
            dialog_title="Save LaTeX file",
            file_name="output.tex",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["tex"],
        )

        if save_path is None:
            set_status("Download cancelled.", is_error=False)
            page.update()
            return

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(output_field.value)
            set_status(f"Saved to {save_path}.")
        except Exception as error:
            set_status(f"Could not save file: {error}", is_error=True)

        page.update()

    # --- preprocessing handlers ---

    async def on_transpose(_: ft.ControlEvent) -> None:
        _apply_preprocessing(transpose_dataframe, "Transposed data.")

    async def on_drop_empty(_: ft.ControlEvent) -> None:
        _apply_preprocessing(
            drop_empty_rows_and_columns,
            "Dropped empty rows and columns.",
        )

    async def on_drop_duplicates(_: ft.ControlEvent) -> None:
        _apply_preprocessing(drop_duplicate_rows, "Dropped duplicate rows.")

    async def on_reset(_: ft.ControlEvent) -> None:
        if state["original_dataframe"] is None:
            set_status("No data loaded. Load a file first.", is_error=True)
            page.update()
            return
        state["dataframe"] = copy.deepcopy(state["original_dataframe"])
        state["grid"] = copy.deepcopy(state["original_grid"])
        history.clear()
        state["edit_session_cell"] = None
        _refresh_grid_view()
        render_output()
        _update_history_buttons()
        set_alignment_display("Inherit")
        set_status("Reset to original data.")
        page.update()

    # --- wire on_change for all controls ---

    file_picker = ft.FilePicker()
    page.services.append(file_picker)

    all_option_controls = [
        caption_field,
        label_field,
        table_type_dropdown,
        scale_box_field,
        full_document_checkbox,
        float_position_switch,
        border_style_dropdown,
        bold_first_row_checkbox,
        bold_first_column_checkbox,
        table_alignment_dropdown,
        text_alignment_dropdown,
        escape_switch,
    ]
    preview_style_controls = [
        border_style_dropdown,
        bold_first_row_checkbox,
        bold_first_column_checkbox,
        text_alignment_dropdown,
    ]
    for control in all_option_controls:
        if isinstance(control, ft.Dropdown):
            control.on_select = on_option_change
        else:
            control.on_change = on_option_change

    # --- Grid toolbar ---

    toolbar_result = build_grid_toolbar(
        get_editor=lambda: state.get("editor"),
        set_status=set_status,
        page_update=page.update,
        on_before_mutation=_record_history,
        on_mutation_failed=_discard_last_history,
        on_undo=_handle_undo,
        on_redo=_handle_redo,
    )
    grid_toolbar = toolbar_result.toolbar
    range_mode_button = toolbar_result.range_mode_button
    undo_button = toolbar_result.undo_button
    redo_button = toolbar_result.redo_button
    set_alignment_display = toolbar_result.set_alignment_display

    # --- layout ---

    upload_zone = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(ft.Icons.UPLOAD_FILE, size=36),
                ft.Text("CSV / XLSX"),
                ft.FilledButton(
                    content="Select file",
                    icon=ft.Icons.FOLDER_OPEN,
                    on_click=open_file_picker,
                    width=BUTTON_WIDTH,
                    height=BUTTON_HEIGHT,
                ),
                selected_file_text,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=PANEL_SPACING,
        ),
        border=ft.Border.all(PANEL_BORDER_WIDTH, ft.Colors.BLUE_GREY_200),
        border_radius=PANEL_BORDER_RADIUS,
        padding=PANEL_PADDING,
        on_click=open_file_picker,
    )

    operation_buttons = ft.Row(
        controls=[
            ft.OutlinedButton(
                content="Transpose",
                on_click=on_transpose,
                width=BUTTON_WIDTH,
                height=BUTTON_HEIGHT,
            ),
            ft.OutlinedButton(
                content="Drop empty",
                on_click=on_drop_empty,
                width=BUTTON_WIDTH,
                height=BUTTON_HEIGHT,
            ),
            ft.OutlinedButton(
                content="Drop duplicates",
                on_click=on_drop_duplicates,
                width=BUTTON_WIDTH,
                height=BUTTON_HEIGHT,
            ),
            ft.OutlinedButton(
                content="Reset",
                on_click=on_reset,
                width=BUTTON_WIDTH,
                height=BUTTON_HEIGHT,
            ),
        ],
        wrap=True,
        spacing=8,
        run_spacing=8,
        alignment=ft.MainAxisAlignment.CENTER,
    )

    data_source_panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "Data Source & Operations",
                    theme_style=ft.TextThemeStyle.TITLE_SMALL,
                ),
                upload_zone,
                operation_buttons,
            ],
            spacing=PANEL_SPACING,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        border=ft.Border.all(PANEL_BORDER_WIDTH, ft.Colors.BLUE_GREY_200),
        border_radius=PANEL_BORDER_RADIUS,
        padding=PANEL_PADDING,
    )

    additional_info_panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Additional Info", theme_style=ft.TextThemeStyle.TITLE_SMALL),
                caption_field,
                label_field,
            ],
            spacing=PANEL_SPACING,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        border=ft.Border.all(PANEL_BORDER_WIDTH, ft.Colors.BLUE_GREY_200),
        border_radius=PANEL_BORDER_RADIUS,
        padding=PANEL_PADDING,
    )

    structure_type_panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Structure & Type", theme_style=ft.TextThemeStyle.TITLE_SMALL),
                table_type_dropdown,
                scale_box_field,
                full_document_checkbox,
                float_position_switch,
            ],
            spacing=PANEL_SPACING,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        border=ft.Border.all(PANEL_BORDER_WIDTH, ft.Colors.BLUE_GREY_200),
        border_radius=PANEL_BORDER_RADIUS,
        padding=PANEL_PADDING,
    )

    style_design_panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Style & Design", theme_style=ft.TextThemeStyle.TITLE_SMALL),
                border_style_dropdown,
                bold_first_row_checkbox,
                bold_first_column_checkbox,
                table_alignment_dropdown,
                text_alignment_dropdown,
                escape_switch,
            ],
            spacing=PANEL_SPACING,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        border=ft.Border.all(PANEL_BORDER_WIDTH, ft.Colors.BLUE_GREY_200),
        border_radius=PANEL_BORDER_RADIUS,
        padding=PANEL_PADDING,
    )

    # --- 3-pane layout: left (options), center (table preview), right (TeX) ---

    left_pane = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Input", theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
                data_source_panel,
                additional_info_panel,
                structure_type_panel,
                style_design_panel,
                status_text,
            ],
            spacing=PANE_SPACING,
            scroll=ft.ScrollMode.AUTO,
        ),
        expand=LEFT_PANE_EXPAND,
        padding=PANE_PADDING,
    )

    grid_scroll_column = ft.Column(
        controls=[
            ft.Row(
                controls=[grid_preview_content],
                scroll=ft.ScrollMode.AUTO,
            ),
        ],
        scroll=ft.ScrollMode.AUTO,
        on_scroll=_on_grid_scroll,
    )

    center_pane = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "Table Preview",
                    theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                ),
                grid_toolbar,
                ft.Container(
                    content=grid_scroll_column,
                    expand=True,
                    border=ft.Border.all(PANEL_BORDER_WIDTH, ft.Colors.BLUE_GREY_200),
                    border_radius=PANEL_BORDER_RADIUS,
                    padding=8,
                ),
            ],
            spacing=PANE_SPACING,
            expand=True,
        ),
        expand=CENTER_PANE_EXPAND,
        padding=PANE_PADDING,
    )

    right_pane = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "Generated TeX",
                    theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                ),
                ft.Row(
                    controls=[
                        ft.FilledButton(
                            content="Copy",
                            icon=ft.Icons.CONTENT_COPY,
                            on_click=copy_output,
                            width=BUTTON_WIDTH,
                            height=BUTTON_HEIGHT,
                        ),
                        ft.FilledButton(
                            content="Download (.tex)",
                            icon=ft.Icons.DOWNLOAD,
                            on_click=download_output,
                            width=BUTTON_WIDTH,
                            height=BUTTON_HEIGHT,
                        ),
                    ],
                    wrap=True,
                    spacing=8,
                    run_spacing=8,
                ),
                output_field,
            ],
            spacing=PANE_SPACING,
            expand=True,
        ),
        expand=RIGHT_PANE_EXPAND,
        padding=PANE_PADDING,
    )

    page.add(
        ft.Row(
            controls=[left_pane, center_pane, right_pane],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    )


if __name__ == "__main__":
    ft.run(main)
