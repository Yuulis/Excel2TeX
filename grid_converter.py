"""Grid-based LaTeX table converter.

Converts a TableGrid into LaTeX output, supporting merged cells
(multicolumn / multirow), per-cell alignment overrides, and all
ConversionOptions features from the existing converter.
"""

from __future__ import annotations

from converter import (
    _ALIGNMENT_COMMANDS,
    ConversionOptions,
    _build_column_spec,
    _escape_latex,
    _escaped_caption,
    _join_row,
    _top_rule,
)
from table_model import Cell, CellAlignment, TableGrid

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def grid_to_latex(
    grid: TableGrid,
    options: ConversionOptions | None = None,
) -> str:
    """Convert a TableGrid into a LaTeX table string.

    Supports merged cells (multicolumn, multirow), per-cell alignment,
    and all existing ConversionOptions features.
    """
    if grid.num_rows == 0 or grid.num_cols == 0:
        raise ValueError(
            "Input grid is empty. Please provide data "
            "with at least one row and one column."
        )

    if options is None:
        options = ConversionOptions()

    table_lines = _build_grid_table_lines(grid, options)

    if options.full_document:
        table_lines = _wrap_grid_full_document(table_lines, grid, options)

    return "\n".join(table_lines)


# ---------------------------------------------------------------------------
# Multicolumn spec
# ---------------------------------------------------------------------------


def _multicolumn_spec(
    start_col: int,
    colspan: int,
    alignment: CellAlignment | None,
    options: ConversionOptions,
) -> str:
    r"""Build the column spec for a ``\multicolumn`` command.

    Includes vertical rules at the left and right boundaries when
    border_style is ``"all"``.  The alignment letter comes from the
    cell's per-cell alignment or falls back to *options.text_alignment*.
    """
    letter = alignment.value if alignment else options.text_alignment
    if options.border_style == "all":
        # Always include | on both sides to maintain vertical grid lines.
        return f"|{letter}|"
    return letter


# ---------------------------------------------------------------------------
# Cell content formatting
# ---------------------------------------------------------------------------


def _format_grid_cell_content(
    cell: Cell,
    row_idx: int,
    col_idx: int,
    grid: TableGrid,
    options: ConversionOptions,
) -> str:
    """Format a single cell's text content with escaping and bold."""
    content = cell.content

    if options.escape:
        content = _escape_latex(content)

    is_first_row = row_idx == 0

    if options.bold_first_row and is_first_row:
        content = rf"\textbf{{{content}}}"
    elif options.bold_first_column and col_idx == 0 and not is_first_row:
        content = rf"\textbf{{{content}}}"

    return content


# ---------------------------------------------------------------------------
# Row building
# ---------------------------------------------------------------------------


def _build_grid_row(
    grid: TableGrid,
    row_idx: int,
    options: ConversionOptions,
) -> list[str]:
    """Build the list of cell strings for a single row.

    Handles multicolumn / multirow wrapping and skips covered cells.
    """
    cells_output: list[str] = []
    col = 0

    while col < grid.num_cols:
        cell = grid.rows[row_idx][col]

        if cell.is_covered:
            # Vertically covered by a multirow from a previous row.
            # (Horizontally covered cells are skipped via colspan jump.)
            anchor = grid.rows[cell.anchor_row][cell.anchor_col]
            if cell.anchor_col == col:
                # Leftmost column of the covered region in this row.
                if anchor.colspan > 1:
                    spec = _multicolumn_spec(
                        col, anchor.colspan, anchor.alignment, options
                    )
                    cells_output.append(
                        f"\\multicolumn{{{anchor.colspan}}}{{{spec}}}{{}}"
                    )
                else:
                    cells_output.append("")
                col += anchor.colspan
            else:
                # Interior of a colspan already handled — skip.
                col += 1
            continue

        # --- Format content ---
        content = _format_grid_cell_content(cell, row_idx, col, grid, options)

        # --- Multirow wrapping (must come before multicolumn) ---
        if cell.rowspan > 1:
            content = f"\\multirow{{{cell.rowspan}}}{{*}}{{{content}}}"

        # --- Multicolumn wrapping ---
        if cell.colspan > 1 or cell.alignment is not None:
            spec = _multicolumn_spec(col, cell.colspan, cell.alignment, options)
            content = f"\\multicolumn{{{cell.colspan}}}{{{spec}}}{{{content}}}"

        cells_output.append(content)
        col += cell.colspan

    return cells_output


# ---------------------------------------------------------------------------
# Rule / hline logic
# ---------------------------------------------------------------------------


def _find_blocked_columns(grid: TableGrid, row_idx: int) -> set[int]:
    """Return columns blocked by multirow spans at the boundary after *row_idx*."""
    blocked: set[int] = set()
    for c in range(grid.num_cols):
        cell = grid.rows[row_idx][c]
        if cell.is_covered and cell.anchor_row is not None:
            anchor = grid.rows[cell.anchor_row][cell.anchor_col]
            if cell.anchor_row + anchor.rowspan > row_idx + 1:
                for cc in range(cell.anchor_col, cell.anchor_col + anchor.colspan):
                    blocked.add(cc)
        elif not cell.is_covered and cell.rowspan > 1:
            for cc in range(c, c + cell.colspan):
                blocked.add(cc)
    return blocked


def _contiguous_ranges(cols: list[int]) -> list[tuple[int, int]]:
    """Group sorted column indices into contiguous (start, end) ranges."""
    if not cols:
        return []
    ranges: list[tuple[int, int]] = []
    start = cols[0]
    prev = cols[0]
    for c in cols[1:]:
        if c == prev + 1:
            prev = c
        else:
            ranges.append((start, prev))
            start = c
            prev = c
    ranges.append((start, prev))
    return ranges


def _determine_rules(
    row_idx: int,
    grid: TableGrid,
    options: ConversionOptions,
) -> list[str]:
    """Return the rule line(s) to emit after *row_idx*, or an empty list."""
    is_last = row_idx == grid.num_rows - 1
    is_header = row_idx == 0 and grid.has_header and grid.num_rows > 1

    if options.border_style == "none":
        return []
    if options.border_style in ("horizontal", "booktabs"):
        if not (is_header or is_last):
            return []
    # border_style == "all" always emits a rule.

    # Find blocked columns (multirow spans crossing this boundary).
    blocked: set[int] = set()
    if not is_last:
        blocked = _find_blocked_columns(grid, row_idx)

    if not blocked:
        # Full rule — pick the right command.
        if is_last and options.border_style == "booktabs":
            return [r"\bottomrule"]
        if is_header and options.border_style == "booktabs":
            return [r"\midrule"]
        return [r"\hline"]

    # Partial rule — cline or cmidrule for non-blocked columns.
    non_blocked = [c for c in range(grid.num_cols) if c not in blocked]
    if not non_blocked:
        return []

    ranges = _contiguous_ranges(non_blocked)
    cmd = "cmidrule" if options.border_style == "booktabs" else "cline"
    return [f"\\{cmd}{{{s + 1}-{e + 1}}}" for s, e in ranges]


# ---------------------------------------------------------------------------
# Table assembly
# ---------------------------------------------------------------------------


def _build_grid_table_lines(
    grid: TableGrid,
    options: ConversionOptions,
) -> list[str]:
    """Assemble the full set of LaTeX lines for the grid-based table."""
    lines: list[str] = []
    is_longtable = options.table_type == "longtable"
    col_spec = _build_column_spec(grid.num_cols, options)

    # --- outer float wrapper (not for longtable) ---
    if not is_longtable:
        if options.use_float_position:
            lines.append(rf"\begin{{table}}[{options.float_position}]")
        else:
            lines.append(r"\begin{table}")
        lines.append(_ALIGNMENT_COMMANDS.get(options.table_alignment, r"\centering"))
        caption = _escaped_caption(options)
        if caption is not None:
            lines.append(rf"\caption{{{caption}}}")
        if options.label and options.label.strip():
            lines.append(rf"\label{{{options.label}}}")

    # --- begin inner environment ---
    if options.table_type == "tabularx":
        lines.append(rf"\begin{{tabularx}}{{\textwidth}}{{{col_spec}}}")
    elif is_longtable:
        lines.append(rf"\begin{{longtable}}{{{col_spec}}}")
        caption = _escaped_caption(options)
        if caption is not None:
            lines.append(rf"\caption{{{caption}}}\\")
        if options.label and options.label.strip():
            lines.append(rf"\label{{{options.label}}}")
    else:
        lines.append(rf"\begin{{tabular}}{{{col_spec}}}")

    # --- top rule ---
    top = _top_rule(options)
    if top:
        lines.append(top)

    # --- rows and per-row rules ---
    for r in range(grid.num_rows):
        row_cells = _build_grid_row(grid, r, options)
        lines.append(_join_row(row_cells))
        rules = _determine_rules(r, grid, options)
        lines.extend(rules)

    # --- end inner environment ---
    env_name = options.table_type
    lines.append(rf"\end{{{env_name}}}")

    # --- end outer float ---
    if not is_longtable:
        lines.append(r"\end{table}")

    return lines


# ---------------------------------------------------------------------------
# Full-document wrapper
# ---------------------------------------------------------------------------


def _wrap_grid_full_document(
    table_lines: list[str],
    grid: TableGrid,
    options: ConversionOptions,
) -> list[str]:
    r"""Wrap *table_lines* in a minimal working LaTeX document.

    Adds ``\usepackage{multirow}`` when any cell has rowspan > 1.
    """
    lines: list[str] = [r"\documentclass{article}"]

    packages: list[str] = []
    if options.border_style == "booktabs":
        packages.append("booktabs")
    if options.table_type == "longtable":
        packages.append("longtable")
    if options.table_type == "tabularx":
        packages.append("tabularx")

    has_multirow = any(
        cell.rowspan > 1 for row in grid.rows for cell in row if not cell.is_covered
    )
    if has_multirow:
        packages.append("multirow")

    for pkg in sorted(packages):
        lines.append(rf"\usepackage{{{pkg}}}")

    lines.append(r"\begin{document}")
    lines.extend(table_lines)
    lines.append(r"\end{document}")
    return lines
