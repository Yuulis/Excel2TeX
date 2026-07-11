"""Cell-grid data model for table editing with merge support.

Provides Cell, CellAlignment, TableGrid, and dataframe_to_grid for
representing tables with merged cells, per-cell alignment, and structural
mutations (insert/delete rows/columns, merge/split).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


class CellAlignment(Enum):
    """Per-cell horizontal alignment. Values match LaTeX column spec letters."""

    LEFT = "l"
    CENTER = "c"
    RIGHT = "r"


@dataclass
class Cell:
    """A single cell in the table grid.

    Anchor cells (top-left of a merged region) have colspan >= 1 and
    rowspan >= 1.  Covered cells (occupied by an anchor's span) have
    is_covered = True and store a reference to the anchor position.
    """

    content: str = ""
    colspan: int = 1
    rowspan: int = 1
    alignment: CellAlignment | None = None
    is_covered: bool = False
    anchor_row: int | None = None
    anchor_col: int | None = None


@dataclass
class TableGrid:
    """A 2D grid of cells with metadata for LaTeX table generation.

    rows[r][c] gives the Cell at row r, column c.
    Row 0 is the header row when has_header is True.
    """

    rows: list[list[Cell]] = field(default_factory=list)
    has_header: bool = True

    # -- properties ----------------------------------------------------------

    @property
    def num_rows(self) -> int:
        """Return the number of rows in the grid."""
        return len(self.rows)

    @property
    def num_cols(self) -> int:
        """Return the number of columns in the grid."""
        if not self.rows:
            return 0
        return len(self.rows[0])

    # -- accessors -----------------------------------------------------------

    def get_cell(self, row: int, col: int) -> Cell:
        """Return the cell at (row, col). Raises IndexError if out of bounds."""
        return self.rows[row][col]

    def set_content(self, row: int, col: int, content: str) -> None:
        """Set text content of a cell. Raises ValueError if cell is covered."""
        cell = self.rows[row][col]
        if cell.is_covered:
            raise ValueError(
                f"Cell ({row}, {col}) is covered by merge anchor "
                f"at ({cell.anchor_row}, {cell.anchor_col})."
            )
        cell.content = content

    def set_alignment(
        self, row: int, col: int, alignment: CellAlignment | None
    ) -> None:
        """Set per-cell alignment. Only valid on non-covered cells."""
        cell = self.rows[row][col]
        if cell.is_covered:
            raise ValueError(
                f"Cell ({row}, {col}) is covered; set alignment on anchor."
            )
        cell.alignment = alignment

    # -- merge / split -------------------------------------------------------

    def merge_cells(
        self,
        top_row: int,
        left_col: int,
        row_span: int,
        col_span: int,
    ) -> None:
        """Merge a rectangular region. Validates before applying.

        The anchor cell retains its content. All other cells in the region
        are marked as covered with their content discarded.
        """
        validate_merge(self, top_row, left_col, row_span, col_span)
        anchor = self.rows[top_row][left_col]
        anchor.colspan = col_span
        anchor.rowspan = row_span
        for r in range(top_row, top_row + row_span):
            for c in range(left_col, left_col + col_span):
                if r == top_row and c == left_col:
                    continue
                covered = self.rows[r][c]
                covered.is_covered = True
                covered.anchor_row = top_row
                covered.anchor_col = left_col
                covered.content = ""
                covered.colspan = 1
                covered.rowspan = 1
                covered.alignment = None

    def split_cell(self, row: int, col: int) -> None:
        """Split a previously merged anchor cell back to individual cells."""
        cell = self.rows[row][col]
        if cell.colspan == 1 and cell.rowspan == 1:
            raise ValueError(f"Cell ({row}, {col}) is not merged.")
        for r in range(row, row + cell.rowspan):
            for c in range(col, col + cell.colspan):
                if r == row and c == col:
                    continue
                target = self.rows[r][c]
                target.is_covered = False
                target.anchor_row = None
                target.anchor_col = None
        cell.colspan = 1
        cell.rowspan = 1

    # -- row / column insert / delete ----------------------------------------

    def insert_row(self, at: int) -> None:
        """Insert an empty row at index *at*. Adjusts spans crossing this row."""
        num_cols = self.num_cols

        # Step 1: increment rowspan for anchors above whose span crosses *at*.
        for r in range(at):
            for c in range(num_cols):
                cell = self.rows[r][c]
                if not cell.is_covered and cell.rowspan > 1:
                    if r + cell.rowspan > at:
                        cell.rowspan += 1

        # Step 2: insert the new empty row.
        new_row = [Cell() for _ in range(num_cols)]
        self.rows.insert(at, new_row)

        # Step 3: update anchor_row references for shifted cells.
        for r in range(at + 1, self.num_rows):
            for c in range(num_cols):
                cell = self.rows[r][c]
                if cell.is_covered and cell.anchor_row is not None:
                    if cell.anchor_row >= at:
                        cell.anchor_row += 1

        # Step 4: mark new-row cells as covered if within vertical spans.
        if at == 0:
            return
        for c in range(num_cols):
            above = self.rows[at - 1][c]
            if above.is_covered and above.anchor_row is not None:
                anchor = self.rows[above.anchor_row][above.anchor_col]
                if above.anchor_row + anchor.rowspan > at:
                    new_row[c].is_covered = True
                    new_row[c].anchor_row = above.anchor_row
                    new_row[c].anchor_col = above.anchor_col
            elif not above.is_covered and above.rowspan > 1:
                # Anchor at (at-1) with rowspan>1 always covers position *at*.
                new_row[c].is_covered = True
                new_row[c].anchor_row = at - 1
                new_row[c].anchor_col = c

    def insert_col(self, at: int) -> None:
        """Insert an empty column at index *at*. Adjusts spans crossing it."""
        # Step 1: increment colspan for anchors left of *at* whose span crosses.
        for r in range(self.num_rows):
            for c in range(min(at, len(self.rows[r]))):
                cell = self.rows[r][c]
                if not cell.is_covered and cell.colspan > 1:
                    if c + cell.colspan > at:
                        cell.colspan += 1

        # Step 2: insert new cell at position *at* in each row.
        for r in range(self.num_rows):
            self.rows[r].insert(at, Cell())

        # Step 3: update anchor_col for cells right of insertion.
        for r in range(self.num_rows):
            for c in range(at + 1, len(self.rows[r])):
                cell = self.rows[r][c]
                if cell.is_covered and cell.anchor_col is not None:
                    if cell.anchor_col >= at:
                        cell.anchor_col += 1

        # Step 4: mark new cells as covered if within horizontal spans.
        if at == 0:
            return
        for r in range(self.num_rows):
            left = self.rows[r][at - 1]
            if left.is_covered and left.anchor_col is not None:
                anchor = self.rows[left.anchor_row][left.anchor_col]
                if left.anchor_col + anchor.colspan > at:
                    new_cell = self.rows[r][at]
                    new_cell.is_covered = True
                    new_cell.anchor_row = left.anchor_row
                    new_cell.anchor_col = left.anchor_col
            elif not left.is_covered and left.colspan > 1:
                new_cell = self.rows[r][at]
                new_cell.is_covered = True
                new_cell.anchor_row = r
                new_cell.anchor_col = at - 1

    def delete_row(self, at: int) -> None:
        """Delete row *at*. Raises if it contains a multirow anchor."""
        for c in range(self.num_cols):
            cell = self.rows[at][c]
            if not cell.is_covered and cell.rowspan > 1:
                raise ValueError(
                    f"Cannot delete row {at}: cell ({at}, {c}) is a "
                    f"multirow anchor. Split the merge first."
                )

        # Shrink rowspan for anchors above whose span covers this row.
        for r in range(at):
            for c in range(self.num_cols):
                cell = self.rows[r][c]
                if not cell.is_covered and cell.rowspan > 1:
                    if r + cell.rowspan > at:
                        cell.rowspan -= 1

        self.rows.pop(at)

        # Update anchor_row references for remaining cells.
        for r in range(at, self.num_rows):
            for c in range(self.num_cols):
                cell = self.rows[r][c]
                if cell.is_covered and cell.anchor_row is not None:
                    if cell.anchor_row > at:
                        cell.anchor_row -= 1

    def delete_col(self, at: int) -> None:
        """Delete column *at*. Raises if it contains a multicolumn anchor."""
        for r in range(self.num_rows):
            cell = self.rows[r][at]
            if not cell.is_covered and cell.colspan > 1:
                raise ValueError(
                    f"Cannot delete col {at}: cell ({r}, {at}) is a "
                    f"multicolumn anchor. Split the merge first."
                )

        # Shrink colspan for anchors left of *at* whose span covers it.
        for r in range(self.num_rows):
            for c in range(at):
                cell = self.rows[r][c]
                if not cell.is_covered and cell.colspan > 1:
                    if c + cell.colspan > at:
                        cell.colspan -= 1

        for r in range(self.num_rows):
            self.rows[r].pop(at)

        # Update anchor_col references for remaining cells.
        for r in range(self.num_rows):
            for c in range(at, len(self.rows[r])):
                cell = self.rows[r][c]
                if cell.is_covered and cell.anchor_col is not None:
                    if cell.anchor_col > at:
                        cell.anchor_col -= 1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_merge(
    grid: TableGrid,
    top_row: int,
    left_col: int,
    row_span: int,
    col_span: int,
) -> None:
    """Validate that the merge region is legal. Raises ValueError if not."""
    if row_span < 1 or col_span < 1:
        raise ValueError("Span dimensions must be >= 1.")
    if row_span == 1 and col_span == 1:
        raise ValueError("Merge region must span more than one cell.")
    if top_row < 0 or left_col < 0:
        raise ValueError("Region origin must be non-negative.")
    if top_row + row_span > grid.num_rows:
        raise ValueError("Merge region extends beyond grid rows.")
    if left_col + col_span > grid.num_cols:
        raise ValueError("Merge region extends beyond grid columns.")
    for r in range(top_row, top_row + row_span):
        for c in range(left_col, left_col + col_span):
            cell = grid.rows[r][c]
            if cell.is_covered:
                raise ValueError(
                    f"Cell ({r}, {c}) is already part of a merge "
                    f"anchored at ({cell.anchor_row}, {cell.anchor_col}). "
                    f"Split that merge first."
                )
            if (r != top_row or c != left_col) and (
                cell.colspan > 1 or cell.rowspan > 1
            ):
                raise ValueError(
                    f"Cell ({r}, {c}) is itself a merge anchor "
                    f"(span {cell.rowspan}x{cell.colspan}). "
                    f"Split it first before merging this region."
                )


# ---------------------------------------------------------------------------
# DataFrame conversion
# ---------------------------------------------------------------------------


def dataframe_to_grid(
    dataframe: pd.DataFrame,
    include_header: bool = True,
) -> TableGrid:
    """Convert a pandas DataFrame into a TableGrid.

    If *include_header* is True (default), row 0 of the grid contains the
    column names, and subsequent rows contain the data.
    """
    import pandas as pd_mod  # noqa: F811 – deferred import

    cols = [str(c) for c in dataframe.columns]
    rows: list[list[Cell]] = []

    if include_header:
        header_row = [Cell(content=name) for name in cols]
        rows.append(header_row)

    for row_values in dataframe.itertuples(index=False, name=None):
        cells = []
        for value in row_values:
            content = "" if pd_mod.isna(value) else str(value)
            cells.append(Cell(content=content))
        rows.append(cells)

    return TableGrid(rows=rows, has_header=include_header)
