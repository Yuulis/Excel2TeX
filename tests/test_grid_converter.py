"""Tests for grid_converter: grid_to_latex with merge, alignment, and all options."""

import pytest

from converter import ConversionOptions
from grid_converter import grid_to_latex
from table_model import Cell, CellAlignment, TableGrid

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_grid_3x3() -> TableGrid:
    """3-row, 3-col grid with header (A, B, C) and body rows."""
    return TableGrid(
        rows=[
            [Cell(content="A"), Cell(content="B"), Cell(content="C")],
            [Cell(content="1"), Cell(content="2"), Cell(content="3")],
            [Cell(content="4"), Cell(content="5"), Cell(content="6")],
        ],
        has_header=True,
    )


def _simple_grid_2x2() -> TableGrid:
    """2-row, 2-col grid with header (A, B) and one body row."""
    return TableGrid(
        rows=[
            [Cell(content="A"), Cell(content="B")],
            [Cell(content="1"), Cell(content="2")],
        ],
        has_header=True,
    )


# ---------------------------------------------------------------------------
# Basic output
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_simple_grid_produces_valid_table() -> None:
    # Arrange
    grid = _simple_grid_2x2()

    # Act
    latex = grid_to_latex(grid)
    lines = latex.splitlines()

    # Assert — matches structure of dataframe_to_latex defaults
    assert lines == [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\begin{tabular}{|c|c|}",
        r"\hline",
        r"A & B \\",
        r"\hline",
        r"1 & 2 \\",
        r"\hline",
        r"\end{tabular}",
        r"\end{table}",
    ]


def test_grid_to_latex_with_empty_grid_raises_value_error() -> None:
    # Arrange
    grid = TableGrid()

    # Act / Assert
    with pytest.raises(ValueError, match="empty"):
        grid_to_latex(grid)


# ---------------------------------------------------------------------------
# Horizontal merge (multicolumn)
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_horizontal_merge_emits_multicolumn() -> None:
    # Arrange
    grid = _simple_grid_3x3()
    grid.merge_cells(0, 0, 1, 2)  # merge header (0,0)-(0,1)

    # Act
    latex = grid_to_latex(grid)

    # Assert
    assert r"\multicolumn{2}{|c|}{A}" in latex
    assert r"1 & 2 & 3 \\" in latex


# ---------------------------------------------------------------------------
# Vertical merge (multirow)
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_vertical_merge_emits_multirow() -> None:
    # Arrange
    grid = _simple_grid_3x3()
    grid.merge_cells(0, 0, 2, 1)  # merge (0,0)-(1,0) vertically

    # Act
    latex = grid_to_latex(grid)

    # Assert
    assert r"\multirow{2}{*}{A}" in latex
    # Covered row should have empty placeholder
    lines = latex.splitlines()
    # Find the row after the cline — it should start with empty " &"
    covered_row = [line for line in lines if line.startswith(" & ")]
    assert len(covered_row) == 1


def test_grid_to_latex_with_vertical_merge_emits_cline() -> None:
    # Arrange
    grid = _simple_grid_3x3()
    grid.merge_cells(0, 0, 2, 1)  # vertical merge in col 0

    # Act
    latex = grid_to_latex(grid)

    # Assert — \cline only on non-blocked columns
    assert r"\cline{2-3}" in latex


# ---------------------------------------------------------------------------
# Combined 2x2 merge
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_2x2_merge_emits_multicolumn_and_multirow() -> None:
    # Arrange
    grid = _simple_grid_3x3()
    grid.merge_cells(0, 0, 2, 2)  # 2x2 merge at (0,0)

    # Act
    latex = grid_to_latex(grid)

    # Assert — anchor row: multicolumn wrapping multirow
    assert r"\multicolumn{2}{|c|}{\multirow{2}{*}{A}} & C \\" in latex
    # Covered row: empty multicolumn placeholder
    assert r"\multicolumn{2}{|c|}{} & 3 \\" in latex
    # Partial rule for blocked columns
    assert r"\cline{3-3}" in latex


# ---------------------------------------------------------------------------
# Per-cell alignment
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_per_cell_alignment_emits_single_multicolumn() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    grid.set_alignment(1, 0, CellAlignment.RIGHT)

    # Act
    latex = grid_to_latex(grid)

    # Assert — single-column multicolumn for alignment override
    assert r"\multicolumn{1}{|r|}{1}" in latex
    # Other cell unaffected
    assert "2 \\\\" in latex


def test_grid_to_latex_with_per_cell_alignment_no_border_no_pipes() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    grid.set_alignment(1, 0, CellAlignment.LEFT)
    options = ConversionOptions(border_style="none")

    # Act
    latex = grid_to_latex(grid, options)

    # Assert — no vertical bars in multicolumn spec
    assert r"\multicolumn{1}{l}{1}" in latex


# ---------------------------------------------------------------------------
# Border styles
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_none_border_no_rules() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    options = ConversionOptions(border_style="none")

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\hline" not in latex
    assert r"\toprule" not in latex
    assert r"\begin{tabular}{cc}" in latex


def test_grid_to_latex_with_horizontal_border_produces_three_hlines() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    options = ConversionOptions(border_style="horizontal")

    # Act
    latex = grid_to_latex(grid, options)
    hline_count = latex.count(r"\hline")

    # Assert — top, after header, bottom
    assert hline_count == 3


def test_grid_to_latex_with_booktabs_produces_correct_rules() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    options = ConversionOptions(border_style="booktabs")

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\toprule" in latex
    assert r"\midrule" in latex
    assert r"\bottomrule" in latex
    assert r"\hline" not in latex


def test_grid_to_latex_with_booktabs_and_vertical_merge_emits_cmidrule() -> None:
    # Arrange
    grid = _simple_grid_3x3()
    grid.merge_cells(0, 0, 2, 1)
    options = ConversionOptions(border_style="booktabs")

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\cmidrule{2-3}" in latex
    assert r"\cline" not in latex


# ---------------------------------------------------------------------------
# Bold
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_bold_first_row_wraps_header() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    options = ConversionOptions(bold_first_row=True)

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\textbf{A} & \textbf{B} \\" in latex
    assert r"\textbf{1}" not in latex


def test_grid_to_latex_with_bold_first_column_wraps_body_col0() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    options = ConversionOptions(bold_first_column=True)

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\textbf{1} & 2 \\" in latex
    assert r"\textbf{A}" not in latex


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_special_chars_escapes_correctly() -> None:
    # Arrange
    grid = TableGrid(
        rows=[
            [Cell(content="A & B"), Cell(content="100%")],
            [Cell(content="x_1"), Cell(content="ok")],
        ],
        has_header=True,
    )

    # Act
    latex = grid_to_latex(grid)

    # Assert
    assert r"A \& B" in latex
    assert r"100\%" in latex
    assert r"x\_1" in latex


def test_grid_to_latex_with_escape_disabled_leaves_raw() -> None:
    # Arrange
    grid = TableGrid(
        rows=[
            [Cell(content="A & B"), Cell(content="C")],
            [Cell(content="1"), Cell(content="2")],
        ],
        has_header=True,
    )
    options = ConversionOptions(escape=False)

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert "A & B" in latex
    assert r"\&" not in latex


# ---------------------------------------------------------------------------
# Multirow package injection
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_multirow_full_document_adds_package() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    grid.rows.append([Cell(content="3"), Cell(content="4")])
    grid.merge_cells(1, 0, 2, 1)  # vertical merge
    options = ConversionOptions(full_document=True)

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\usepackage{multirow}" in latex
    assert r"\documentclass{article}" in latex


def test_grid_to_latex_without_multirow_full_document_no_package() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    options = ConversionOptions(full_document=True)

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\usepackage{multirow}" not in latex


def test_grid_to_latex_with_full_document_booktabs_includes_both_packages() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    grid.rows.append([Cell(content="3"), Cell(content="4")])
    grid.merge_cells(1, 0, 2, 1)
    options = ConversionOptions(full_document=True, border_style="booktabs")

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\usepackage{booktabs}" in latex
    assert r"\usepackage{multirow}" in latex


# ---------------------------------------------------------------------------
# Table types
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_longtable_no_table_wrapper() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    options = ConversionOptions(table_type="longtable")

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\begin{longtable}" in latex
    assert r"\end{longtable}" in latex
    assert r"\begin{table}" not in latex


def test_grid_to_latex_with_tabularx_uses_textwidth() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    options = ConversionOptions(table_type="tabularx")

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\begin{tabularx}{\textwidth}" in latex
    assert r"\end{tabularx}" in latex


# ---------------------------------------------------------------------------
# Caption and label
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_caption_and_label() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    options = ConversionOptions(caption="My Table", label="tab:my")

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\caption{My Table}" in latex
    assert r"\label{tab:my}" in latex


def test_grid_to_latex_with_longtable_caption_inside() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    options = ConversionOptions(
        table_type="longtable", caption="LT Caption", label="tab:lt"
    )

    # Act
    latex = grid_to_latex(grid, options)
    lines = latex.splitlines()

    # Assert — caption inside longtable, ends with \\
    longtable_idx = next(
        i for i, line in enumerate(lines) if r"\begin{longtable}" in line
    )
    caption_idx = next(i for i, line in enumerate(lines) if r"\caption{" in line)
    assert caption_idx > longtable_idx
    assert lines[caption_idx].endswith("\\\\")


# ---------------------------------------------------------------------------
# Text alignment
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_left_alignment_changes_colspec() -> None:
    # Arrange
    grid = _simple_grid_2x2()
    options = ConversionOptions(text_alignment="l", border_style="none")

    # Act
    latex = grid_to_latex(grid, options)

    # Assert
    assert r"\begin{tabular}{ll}" in latex


# ---------------------------------------------------------------------------
# Full-width multirow (all columns blocked)
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_full_width_multirow_suppresses_rule() -> None:
    # Arrange — single-column grid with vertical merge
    grid = TableGrid(
        rows=[
            [Cell(content="X")],
            [Cell(content="Y")],
            [Cell(content="Z")],
        ],
        has_header=True,
    )
    grid.merge_cells(0, 0, 2, 1)  # blocks the only column
    options = ConversionOptions(border_style="all")

    # Act
    latex = grid_to_latex(grid, options)
    lines = latex.splitlines()

    # Assert — no rule between rows 0 and 1 (fully blocked)
    multirow_line_idx = next(i for i, line in enumerate(lines) if r"\multirow" in line)
    next_line = lines[multirow_line_idx + 1]
    # The next line should be the covered placeholder row, not \hline or \cline
    assert r"\hline" not in next_line
    assert r"\cline" not in next_line


# ---------------------------------------------------------------------------
# Merge at non-zero column with "all" borders
# ---------------------------------------------------------------------------


def test_grid_to_latex_with_merge_at_col1_maintains_vertical_rules() -> None:
    # Arrange
    grid = _simple_grid_3x3()
    grid.merge_cells(0, 1, 1, 2)  # merge header cols 1-2

    # Act
    latex = grid_to_latex(grid)

    # Assert — multicolumn spec has | on both sides
    assert r"\multicolumn{2}{|c|}{B}" in latex
