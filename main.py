import copy

import flet as ft

from converter import ConversionOptions, dataframe_to_latex, read_table_file
from preprocessing import (
    apply_text_case,
    drop_duplicate_rows,
    drop_empty_rows_and_columns,
    transpose_dataframe,
)


async def main(page: ft.Page) -> None:
    page.title = "Excel2TeX"
    page.padding = 24
    page.spacing = 16

    clipboard = ft.Clipboard()
    page.services.append(clipboard)

    state: dict[str, object] = {
        "dataframe": None,
        "original_dataframe": None,
    }

    # --- shared widgets ---

    selected_file_text = ft.Text("No file selected")
    status_text = ft.Text("Select a CSV or XLSX file to generate LaTeX.")
    output_field = ft.TextField(
        value="",
        read_only=True,
        multiline=True,
        min_lines=20,
        expand=True,
        border_radius=6,
        hint_text="Generated LaTeX will appear here.",
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
            table_type=table_type_dropdown.value or "tabular",
            full_document=bool(full_document_checkbox.value),
        )

    def render_output() -> None:
        dataframe = state["dataframe"]
        if dataframe is None:
            return
        options = _build_options()
        output_field.value = dataframe_to_latex(dataframe, options)

    # --- event handlers ---

    async def on_option_change(_: ft.ControlEvent) -> None:
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
            render_output()
        except Exception as error:
            output_field.value = ""
            state["dataframe"] = None
            state["original_dataframe"] = None
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
        if state["dataframe"] is None:
            set_status("No data loaded. Load a file first.", is_error=True)
            page.update()
            return
        state["dataframe"] = transpose_dataframe(state["dataframe"])
        render_output()
        set_status("Transposed data.")
        page.update()

    async def on_uppercase(_: ft.ControlEvent) -> None:
        if state["dataframe"] is None:
            set_status("No data loaded. Load a file first.", is_error=True)
            page.update()
            return
        state["dataframe"] = apply_text_case(state["dataframe"], "upper")
        render_output()
        set_status("Applied UPPERCASE.")
        page.update()

    async def on_lowercase(_: ft.ControlEvent) -> None:
        if state["dataframe"] is None:
            set_status("No data loaded. Load a file first.", is_error=True)
            page.update()
            return
        state["dataframe"] = apply_text_case(state["dataframe"], "lower")
        render_output()
        set_status("Applied lowercase.")
        page.update()

    async def on_capitalize(_: ft.ControlEvent) -> None:
        if state["dataframe"] is None:
            set_status("No data loaded. Load a file first.", is_error=True)
            page.update()
            return
        state["dataframe"] = apply_text_case(state["dataframe"], "capitalize")
        render_output()
        set_status("Applied Capitalize.")
        page.update()

    async def on_drop_empty(_: ft.ControlEvent) -> None:
        if state["dataframe"] is None:
            set_status("No data loaded. Load a file first.", is_error=True)
            page.update()
            return
        state["dataframe"] = drop_empty_rows_and_columns(state["dataframe"])
        render_output()
        set_status("Dropped empty rows and columns.")
        page.update()

    async def on_drop_duplicates(_: ft.ControlEvent) -> None:
        if state["dataframe"] is None:
            set_status("No data loaded. Load a file first.", is_error=True)
            page.update()
            return
        state["dataframe"] = drop_duplicate_rows(state["dataframe"])
        render_output()
        set_status("Dropped duplicate rows.")
        page.update()

    async def on_reset(_: ft.ControlEvent) -> None:
        if state["original_dataframe"] is None:
            set_status("No data loaded. Load a file first.", is_error=True)
            page.update()
            return
        state["dataframe"] = copy.deepcopy(state["original_dataframe"])
        render_output()
        set_status("Reset to original data.")
        page.update()

    # --- wire on_change for all controls ---

    file_picker = ft.FilePicker()
    page.services.append(file_picker)

    all_option_controls = [
        caption_field,
        label_field,
        table_type_dropdown,
        full_document_checkbox,
        float_position_switch,
        border_style_dropdown,
        bold_first_row_checkbox,
        bold_first_column_checkbox,
        table_alignment_dropdown,
        text_alignment_dropdown,
        escape_switch,
    ]
    for control in all_option_controls:
        if isinstance(control, ft.Dropdown):
            control.on_select = on_option_change
        else:
            control.on_change = on_option_change

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
                ),
                selected_file_text,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        ),
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_200),
        border_radius=8,
        padding=24,
        on_click=open_file_picker,
    )

    operation_buttons = ft.Row(
        controls=[
            ft.OutlinedButton(content="Transpose", on_click=on_transpose),
            ft.OutlinedButton(content="UPPERCASE", on_click=on_uppercase),
            ft.OutlinedButton(content="lowercase", on_click=on_lowercase),
            ft.OutlinedButton(content="Capitalize", on_click=on_capitalize),
            ft.OutlinedButton(content="Drop empty", on_click=on_drop_empty),
            ft.OutlinedButton(content="Drop duplicates", on_click=on_drop_duplicates),
            ft.OutlinedButton(content="Reset", on_click=on_reset),
        ],
        wrap=True,
        spacing=8,
        run_spacing=8,
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
            spacing=12,
        ),
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_200),
        border_radius=8,
        padding=16,
    )

    additional_info_panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Additional Info", theme_style=ft.TextThemeStyle.TITLE_SMALL),
                caption_field,
                label_field,
            ],
            spacing=12,
        ),
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_200),
        border_radius=8,
        padding=16,
    )

    structure_type_panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Structure & Type", theme_style=ft.TextThemeStyle.TITLE_SMALL),
                table_type_dropdown,
                full_document_checkbox,
                float_position_switch,
            ],
            spacing=12,
        ),
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_200),
        border_radius=8,
        padding=16,
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
            spacing=12,
        ),
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_200),
        border_radius=8,
        padding=16,
    )

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
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
        ),
        expand=1,
        padding=16,
    )
    right_pane = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            "Generated TeX",
                            theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                            expand=True,
                        ),
                        ft.FilledButton(
                            content="Copy",
                            icon=ft.Icons.CONTENT_COPY,
                            on_click=copy_output,
                        ),
                        ft.FilledButton(
                            content="Download (.tex)",
                            icon=ft.Icons.DOWNLOAD,
                            on_click=download_output,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                output_field,
            ],
            spacing=12,
            expand=True,
        ),
        expand=2,
        padding=16,
    )

    page.add(
        ft.Row(
            controls=[left_pane, right_pane],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    )


if __name__ == "__main__":
    ft.run(main)
