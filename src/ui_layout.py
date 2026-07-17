"""Shared dimensions for the full-screen Flet interface."""

from collections.abc import Sequence

import flet as ft

PAGE_PADDING = 16
PANE_PADDING = 12
PANE_SPACING = 12
PANEL_PADDING = 16
PANEL_SPACING = 12
PANEL_BORDER_RADIUS = 8
PANEL_BORDER_WIDTH = 1

BUTTON_WIDTH = 160
BUTTON_HEIGHT = 42

LEFT_PANE_EXPAND = 3
CENTER_PANE_EXPAND = 5
RIGHT_PANE_EXPAND = 4


def build_settings_panel(title: str, controls: Sequence[ft.Control]) -> ft.Container:
    """Build a full-width settings panel with a consistent heading."""
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
                *controls,
            ],
            spacing=PANEL_SPACING,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        border=ft.Border.all(PANEL_BORDER_WIDTH, ft.Colors.BLUE_GREY_200),
        border_radius=PANEL_BORDER_RADIUS,
        padding=PANEL_PADDING,
    )
