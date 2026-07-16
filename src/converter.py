from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import pandas as pd

# Sentinel placeholders used during LaTeX escaping to avoid double-replacement.
_BACKSLASH_PLACEHOLDER = "\x00BACKSLASH\x00"
_CARET_PLACEHOLDER = "\x00CARET\x00"
_TILDE_PLACEHOLDER = "\x00TILDE\x00"

_ALIGNMENT_COMMANDS = {
    "center": r"\centering",
    "left": r"\raggedright",
    "right": r"\raggedleft",
}
_SCALE_FACTOR_ERROR = "Scale factor must be a positive number."


@dataclass(frozen=True)
class ConversionOptions:
    """Options controlling LaTeX table generation."""

    # Additional info (existing)
    caption: str | None = None
    label: str | None = None
    # Phase 1: styling & alignment
    text_alignment: str = "c"
    table_alignment: str = "center"
    bold_first_row: bool = False
    bold_first_column: bool = False
    use_float_position: bool = True
    float_position: str = "htbp"
    # Phase 2: advanced latex & safety
    escape: bool = True
    border_style: str = "all"
    table_type: str = "tabular"
    full_document: bool = False
    scale_factor: float | None = None

    def __post_init__(self) -> None:
        """Validate options that must remain safe LaTeX command arguments."""
        if self.scale_factor is None:
            return
        if not isfinite(self.scale_factor) or self.scale_factor <= 0:
            raise ValueError(_SCALE_FACTOR_ERROR)


def parse_scale_factor(value: str) -> float | None:
    """Parse a Scale box field value; a blank value disables scaling."""
    stripped = value.strip()
    if not stripped:
        return None
    try:
        scale_factor = float(stripped)
    except ValueError as error:
        raise ValueError(_SCALE_FACTOR_ERROR) from error
    if not isfinite(scale_factor) or scale_factor <= 0:
        raise ValueError(_SCALE_FACTOR_ERROR)
    return scale_factor


def dataframe_to_latex(
    dataframe: pd.DataFrame,
    options: ConversionOptions | None = None,
) -> str:
    """Convert a non-empty DataFrame into a LaTeX table string.

    Parameters
    ----------
    dataframe:
        Source data.  Must have at least one row and one column.
    options:
        Conversion settings.  ``None`` uses ``ConversionOptions()`` defaults.
    """
    if dataframe.empty:
        raise ValueError(
            "Input table is empty. Please provide a CSV or XLSX file "
            "with at least one data row and one column."
        )

    if options is None:
        options = ConversionOptions()

    column_names = [str(col) for col in dataframe.columns]
    col_spec = _build_column_spec(len(column_names), options)

    header_cells = _format_header_cells(column_names, options)
    body_rows = _format_body_rows(dataframe, options)

    table_lines = _build_table_lines(col_spec, header_cells, body_rows, options)

    if options.full_document:
        table_lines = _wrap_full_document(table_lines, options)

    return "\n".join(table_lines)


# ---------- column spec ---------------------------------------------------


def _build_column_spec(column_count: int, options: ConversionOptions) -> str:
    """Build the LaTeX column specification string."""
    letter = options.text_alignment
    if options.border_style == "all":
        return "|" + "|".join(letter for _ in range(column_count)) + "|"
    return letter * column_count


# ---------- escaping -------------------------------------------------------


def _escape_latex(text: str) -> str:
    """Escape LaTeX special characters in *text*.

    Backslash is replaced first (via placeholder) so that the backslashes
    introduced by later replacements are not themselves escaped.
    """
    # Phase 1 – placeholders for chars that become multi-char sequences
    text = text.replace("\\", _BACKSLASH_PLACEHOLDER)
    text = text.replace("^", _CARET_PLACEHOLDER)
    text = text.replace("~", _TILDE_PLACEHOLDER)

    # Phase 2 – simple prefix-escapes
    for char in ("&", "%", "_", "{", "}", "$", "#"):
        text = text.replace(char, f"\\{char}")

    # Phase 3 – resolve placeholders
    text = text.replace(_BACKSLASH_PLACEHOLDER, r"\textbackslash{}")
    text = text.replace(_CARET_PLACEHOLDER, r"\textasciicircum{}")
    text = text.replace(_TILDE_PLACEHOLDER, r"\textasciitilde{}")
    return text


# ---------- cell formatting ------------------------------------------------


def _format_latex_cell(value: object) -> str:
    """Convert a single cell value to its string representation."""
    if pd.isna(value):
        return ""
    return str(value)


def _format_header_cells(
    column_names: list[str],
    options: ConversionOptions,
) -> list[str]:
    """Return header cells with optional escaping and bold."""
    cells: list[str] = []
    for name in column_names:
        cell = _escape_latex(name) if options.escape else name
        if options.bold_first_row:
            cell = rf"\textbf{{{cell}}}"
        cells.append(cell)
    return cells


def _format_body_rows(
    dataframe: pd.DataFrame,
    options: ConversionOptions,
) -> list[list[str]]:
    """Return body rows as lists of formatted cell strings."""
    rows: list[list[str]] = []
    for row_values in dataframe.itertuples(index=False, name=None):
        cells: list[str] = []
        for col_idx, value in enumerate(row_values):
            cell = _format_latex_cell(value)
            if options.escape:
                cell = _escape_latex(cell)
            if options.bold_first_column and col_idx == 0:
                cell = rf"\textbf{{{cell}}}"
            cells.append(cell)
        rows.append(cells)
    return rows


# ---------- rules / hlines ------------------------------------------------


def _top_rule(options: ConversionOptions) -> str | None:
    """Rule after \\begin{tabular} / top of the table."""
    if options.border_style in ("all", "horizontal"):
        return r"\hline"
    if options.border_style == "booktabs":
        return r"\toprule"
    return None


def _mid_rule(options: ConversionOptions) -> str | None:
    """Rule after the header row."""
    if options.border_style in ("all", "horizontal"):
        return r"\hline"
    if options.border_style == "booktabs":
        return r"\midrule"
    return None


def _bottom_rule(options: ConversionOptions) -> str | None:
    """Rule before \\end{tabular} / bottom of the table."""
    if options.border_style in ("all", "horizontal"):
        return r"\hline"
    if options.border_style == "booktabs":
        return r"\bottomrule"
    return None


def _body_row_rule(options: ConversionOptions) -> str | None:
    """Rule after each body row (only for the *all* grid style)."""
    if options.border_style == "all":
        return r"\hline"
    return None


# ---------- table assembly -------------------------------------------------


def _join_row(cells: Sequence[str]) -> str:
    """Join cell strings into a single LaTeX row."""
    return f"{' & '.join(cells)} \\\\"


def _escaped_caption(options: ConversionOptions) -> str | None:
    """Return the caption text (escaped if required), or None."""
    caption = options.caption
    if not caption or not caption.strip():
        return None
    if options.escape:
        caption = _escape_latex(caption)
    return caption


def _build_table_lines(
    col_spec: str,
    header_cells: list[str],
    body_rows: list[list[str]],
    options: ConversionOptions,
) -> list[str]:
    """Assemble the full set of LaTeX lines for the table."""
    lines: list[str] = []
    is_longtable = options.table_type == "longtable"

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

    # --- optional scale wrapper and inner environment ---
    scale_box_opening = _scale_box_opening(options)
    if scale_box_opening is not None:
        lines.append(scale_box_opening)

    if options.table_type == "tabularx":
        lines.append(rf"\begin{{tabularx}}{{\textwidth}}{{{col_spec}}}")
    elif is_longtable:
        lines.append(rf"\begin{{longtable}}{{{col_spec}}}")
        # longtable: caption & label go inside, before the top rule
        caption = _escaped_caption(options)
        if caption is not None:
            lines.append(rf"\caption{{{caption}}}\\")
        if options.label and options.label.strip():
            lines.append(rf"\label{{{options.label}}}")
    else:
        lines.append(rf"\begin{{tabular}}{{{col_spec}}}")

    # --- top rule ---
    rule = _top_rule(options)
    if rule:
        lines.append(rule)

    # --- header row ---
    lines.append(_join_row(header_cells))

    # --- mid rule ---
    rule = _mid_rule(options)
    if rule:
        lines.append(rule)

    # --- body rows ---
    row_rule = _body_row_rule(options)
    for row_cells in body_rows:
        lines.append(_join_row(row_cells))
        if row_rule:
            lines.append(row_rule)

    # --- bottom rule (skip for "all" — last body row rule doubles as bottom) ---
    if options.border_style != "all":
        rule = _bottom_rule(options)
        if rule:
            lines.append(rule)

    # --- end inner environment ---
    env_name = options.table_type
    lines.append(rf"\end{{{env_name}}}")

    if scale_box_opening is not None:
        lines.append("}")

    # --- end outer float ---
    if not is_longtable:
        lines.append(r"\end{table}")

    return lines


def _scale_box_opening(options: ConversionOptions) -> str | None:
    """Return a scalebox opening command when scaling applies to the table."""
    if options.scale_factor is None or options.table_type == "longtable":
        return None
    factor = format(options.scale_factor, "g")
    return rf"\scalebox{{{factor}}}{{%"


# ---------- MWE wrapper ----------------------------------------------------


def _wrap_full_document(
    table_lines: list[str],
    options: ConversionOptions,
) -> list[str]:
    """Wrap table lines in a minimal working LaTeX document."""
    lines: list[str] = [r"\documentclass{article}"]

    packages: list[str] = []
    if options.border_style == "booktabs":
        packages.append("booktabs")
    if options.table_type == "longtable":
        packages.append("longtable")
    if options.table_type == "tabularx":
        packages.append("tabularx")
    if _scale_box_opening(options) is not None:
        packages.append("graphicx")

    for pkg in sorted(packages):
        lines.append(rf"\usepackage{{{pkg}}}")

    lines.append(r"\begin{document}")
    lines.extend(table_lines)
    lines.append(r"\end{document}")
    return lines


# ---------- file I/O -------------------------------------------------------


def _is_cell_empty(value: object) -> bool:
    """Return True if *value* is considered empty (NaN, None, or blank string)."""
    if pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _find_first_data_row(raw: pd.DataFrame) -> int | None:
    """Return 0-based index of the first row with at least one non-empty cell.

    Returns ``None`` when every row is empty.
    """
    for idx in range(len(raw)):
        row = raw.iloc[idx]
        if not all(_is_cell_empty(cell) for cell in row):
            return idx
    return None


def _drop_leading_empty_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Drop columns from the left that are entirely empty.

    Stops at the first column that contains at least one non-empty value.
    Columns in the middle or right of the table are never dropped.
    """
    drop_count = 0
    for col_idx in range(len(df.columns)):
        column = df.iloc[:, col_idx]
        if all(_is_cell_empty(cell) for cell in column):
            drop_count += 1
        else:
            break
    if drop_count == 0:
        return df
    return df.iloc[:, drop_count:]


def read_table_file(file_path: str | Path) -> pd.DataFrame:
    """Read a supported table file into a DataFrame.

    Automatically skips leading empty rows and leading empty columns so that
    the actual data region becomes the header and body of the returned
    DataFrame.
    """
    path = Path(file_path)
    file_extension = path.suffix.lower()

    if file_extension not in (".csv", ".xlsx"):
        raise ValueError("Unsupported file type. Please select a CSV or XLSX file.")

    # Phase 1: raw read to detect the first non-empty row.
    if file_extension == ".csv":
        raw = pd.read_csv(path, header=None)
    else:
        raw = pd.read_excel(path, engine="openpyxl", header=None)

    top = _find_first_data_row(raw)
    if top is None:
        return pd.DataFrame()

    # Phase 2: re-read with proper header / dtype inference.
    top = int(top)  # ensure native int for skiprows
    if file_extension == ".csv":
        df = pd.read_csv(path, skiprows=top)
    else:
        df = pd.read_excel(path, engine="openpyxl", skiprows=top)

    # Drop leading empty columns only.
    df = _drop_leading_empty_columns(df)

    return df
