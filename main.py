import flet as ft

from converter import dataframe_to_latex, read_table_file


async def main(page: ft.Page) -> None:
    page.title = "Excel2TeX"
    page.padding = 24
    page.spacing = 16

    clipboard = ft.Clipboard()
    page.services.append(clipboard)

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

    def set_status(message: str, is_error: bool = False) -> None:
        status_text.value = message
        status_text.color = ft.Colors.RED_700 if is_error else ft.Colors.GREEN_700

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
            latex_code = dataframe_to_latex(dataframe)
        except Exception as error:
            output_field.value = ""
            selected_file_text.value = selected_file.name
            set_status(f"Could not convert file: {error}", is_error=True)
            page.update()
            return

        selected_file_text.value = selected_file.name
        output_field.value = latex_code
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

    file_picker = ft.FilePicker()
    page.services.append(file_picker)

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

    left_pane = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Input", theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
                upload_zone,
                status_text,
            ],
            spacing=16,
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
