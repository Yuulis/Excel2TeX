import flet as ft

from ui_layout import build_settings_panel


def test_build_settings_panel_uses_medium_heading_and_stretched_content() -> None:
    control = ft.TextField(label="Example")

    panel = build_settings_panel("Settings", [control])

    assert isinstance(panel.content, ft.Column)
    assert panel.content.horizontal_alignment == ft.CrossAxisAlignment.STRETCH
    assert panel.content.controls[0].theme_style == ft.TextThemeStyle.TITLE_MEDIUM
    assert panel.content.controls[1] is control
