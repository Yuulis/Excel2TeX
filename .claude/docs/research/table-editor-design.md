# Table Editor Feature -- Architecture & Design

> Produced 2026-07-09 by Opus subagent analysis of the Excel2TeX codebase.
> Source files analyzed: converter.py (389 LOC), main.py (473 LOC),
> preprocessing.py (82 LOC), tests/test_converter.py (630 LOC).

---

## Analysis

### Problem Statement

The current data model stores table data as a `pd.DataFrame` in `main.py`
`state["dataframe"]`. DataFrames have no concept of merged cells (cells
spanning multiple rows or columns). To support interactive merge/split,
insert/delete rows/columns, and per-cell alignment, a richer data structure
is needed.

### Two Candidate Data Models

**Option A -- Grid of Cell Objects (anchor + covered flags)**

A 2D list of `Cell` dataclass instances. Each cell knows its own `content`,
`colspan`, `rowspan`, and `alignment`. "Anchor" cells (top-left of a merge)
carry colspan/rowspan > 1. Positions covered by a span hold a sentinel
`CoveredCell` (or a Cell with a `is_covered=True` flag) pointing back to
the anchor.

Pros:
- Every position in the grid is addressable in O(1).
- Converter iterates row-by-row, column-by-column; O(1) per cell to decide
  whether to emit content or skip.
- Insert/delete row/col is a list splice plus updating spans that cross the
  insertion point.
- Per-cell alignment stored directly on the cell -- no secondary lookup.
- Validation (overlap detection) is O(1) per position: just check
  `is_covered`.

Cons:
- Slightly more memory than a flat DataFrame for large tables (negligible
  for typical report-sized tables <1000 cells).
- Serialization requires a custom to_dict / from_dict (not a problem for
  this project since we never persist intermediate state).

**Option B -- DataFrame + Separate Merge-Region List**

Keep the DataFrame for cell content. Maintain a parallel list of
`MergeRegion(top_row, left_col, row_span, col_span, alignment)`. The
converter cross-references this list when building each row.

Pros:
- Minimal change to existing code; DataFrame stays as-is.
- Preprocessing functions continue to work on the DataFrame.

Cons:
- Merge overlap validation requires scanning the full region list -- O(m)
  per merge where m = number of existing merges.
- Row/column insert/delete must adjust every MergeRegion's coordinates --
  error-prone.
- Per-cell alignment for non-merged cells needs yet another structure (a
  parallel 2D array of alignments), duplicating the grid idea partially.
- Converter must look up merge regions for each cell during row building --
  O(m) per cell in the worst case, or requires building a secondary
  "occupied" grid anyway, making Option B converge to Option A.
- Transpose and other structural transforms become complex when merge
  regions must be rotated.

### Decision: Option A -- Grid of Cell Objects

Option A is chosen because:
1. It is the natural representation for a grid editor with cell-level
   properties.
2. Converter logic is simpler (iterate positions, check flag, emit or skip).
3. Option B converges to needing an "occupied" grid during conversion
   anyway, so the DataFrame becomes redundant overhead.
4. Validation is O(1) per position.
5. Insert/delete/transpose operations are straightforward list operations.

---

## Recommended Data Model (with code sketch)

### table_model.py

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CellAlignment(Enum):
    """Per-cell horizontal alignment. None means inherit from options."""
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
    alignment: CellAlignment | None = None  # None = inherit global
    is_covered: bool = False
    # For covered cells: coordinates of the anchor cell that owns this position.
    anchor_row: int | None = None
    anchor_col: int | None = None


@dataclass
class TableGrid:
    """A 2D grid of cells with metadata for LaTeX table generation.

    rows[r][c] gives the Cell at row r, column c.
    Row 0 is the header row (column names from the original file).
    """
    rows: list[list[Cell]] = field(default_factory=list)
    # Whether row 0 should be treated as a header (affects mid-rule placement).
    has_header: bool = True

    @property
    def num_rows(self) -> int:
        return len(self.rows)

    @property
    def num_cols(self) -> int:
        if not self.rows:
            return 0
        return len(self.rows[0])

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

    def set_alignment(self, row: int, col: int, alignment: CellAlignment | None) -> None:
        """Set per-cell alignment. Only valid on anchor cells."""
        cell = self.rows[row][col]
        if cell.is_covered:
            raise ValueError(
                f"Cell ({row}, {col}) is covered; set alignment on anchor."
            )
        cell.alignment = alignment

    # --- merge / split ---

    def merge_cells(
        self,
        top_row: int,
        left_col: int,
        row_span: int,
        col_span: int,
    ) -> None:
        """Merge a rectangular region. Validates before applying.

        The anchor cell retains its content. All other cells in the region
        are marked as covered. Their content is discarded (caller should
        confirm with user if non-empty).
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

    # --- row / column insert / delete ---

    def insert_row(self, at: int) -> None:
        """Insert an empty row at index `at`. Adjusts spans crossing this row."""
        new_row = [Cell() for _ in range(self.num_cols)]
        # Adjust rowspan for anchors above that span past `at`.
        for r in range(at):
            for c in range(self.num_cols):
                cell = self.rows[r][c]
                if not cell.is_covered and cell.rowspan > 1:
                    if r + cell.rowspan > at:
                        cell.rowspan += 1
        # Update anchor_row references for covered cells below insertion.
        self.rows.insert(at, new_row)
        for r in range(at + 1, self.num_rows):
            for c in range(self.num_cols):
                cell = self.rows[r][c]
                if cell.is_covered and cell.anchor_row is not None:
                    if cell.anchor_row >= at:
                        cell.anchor_row += 1
        # Mark new row cells that fall within existing vertical spans as covered.
        for c in range(self.num_cols):
            # Check if cell above is covered or has rowspan extending here.
            if at > 0:
                above = self.rows[at - 1][c]
                if above.is_covered and above.anchor_row is not None:
                    anchor = self.rows[above.anchor_row][above.anchor_col]
                    if above.anchor_row + anchor.rowspan > at:
                        new_row[c].is_covered = True
                        new_row[c].anchor_row = above.anchor_row
                        new_row[c].anchor_col = above.anchor_col
                elif not above.is_covered and above.rowspan > 1:
                    if r + above.rowspan > at:  # noqa: F821 -- simplified
                        new_row[c].is_covered = True
                        new_row[c].anchor_row = at - 1
                        new_row[c].anchor_col = c

    def insert_col(self, at: int) -> None:
        """Insert an empty column at index `at`. Adjusts spans crossing this column."""
        for r in range(self.num_rows):
            # Adjust colspan for anchors left of `at` whose span crosses it.
            for c in range(min(at, len(self.rows[r]))):
                cell = self.rows[r][c]
                if not cell.is_covered and cell.colspan > 1:
                    if c + cell.colspan > at:
                        cell.colspan += 1
            self.rows[r].insert(at, Cell())
            # Update anchor_col for covered cells right of insertion.
            for c in range(at + 1, len(self.rows[r])):
                cell = self.rows[r][c]
                if cell.is_covered and cell.anchor_col is not None:
                    if cell.anchor_col >= at:
                        cell.anchor_col += 1
            # Mark new cell as covered if it falls within a horizontal span.
            if at > 0:
                left = self.rows[r][at - 1]
                if left.is_covered and left.anchor_col is not None:
                    anchor = self.rows[left.anchor_row][left.anchor_col]
                    if left.anchor_col + anchor.colspan > at:
                        new_cell = self.rows[r][at]
                        new_cell.is_covered = True
                        new_cell.anchor_row = left.anchor_row
                        new_cell.anchor_col = left.anchor_col

    def delete_row(self, at: int) -> None:
        """Delete row `at`. Adjusts spans. Raises if row is an anchor of a multirow."""
        # Check for anchors that would be destroyed.
        for c in range(self.num_cols):
            cell = self.rows[at][c]
            if not cell.is_covered and cell.rowspan > 1:
                raise ValueError(
                    f"Cannot delete row {at}: cell ({at}, {c}) is a "
                    f"multirow anchor. Split the merge first."
                )
        # Adjust rowspan for anchors above whose span covers this row.
        for r in range(at):
            for c in range(self.num_cols):
                cell = self.rows[r][c]
                if not cell.is_covered and cell.rowspan > 1:
                    if r + cell.rowspan > at:
                        cell.rowspan -= 1
        self.rows.pop(at)
        # Update anchor_row references.
        for r in range(at, self.num_rows):
            for c in range(self.num_cols):
                cell = self.rows[r][c]
                if cell.is_covered and cell.anchor_row is not None:
                    if cell.anchor_row > at:
                        cell.anchor_row -= 1

    def delete_col(self, at: int) -> None:
        """Delete column `at`. Adjusts spans. Raises if col is an anchor of a multicolumn."""
        for r in range(self.num_rows):
            cell = self.rows[r][at]
            if not cell.is_covered and cell.colspan > 1:
                raise ValueError(
                    f"Cannot delete col {at}: cell ({r}, {at}) is a "
                    f"multicolumn anchor. Split the merge first."
                )
        for r in range(self.num_rows):
            # Adjust colspan for anchors left of `at`.
            for c in range(at):
                cell = self.rows[r][c]
                if not cell.is_covered and cell.colspan > 1:
                    if c + cell.colspan > at:
                        cell.colspan -= 1
            self.rows[r].pop(at)
            # Update anchor_col references.
            for c in range(at, len(self.rows[r])):
                cell = self.rows[r][c]
                if cell.is_covered and cell.anchor_col is not None:
                    if cell.anchor_col > at:
                        cell.anchor_col -= 1


# --- Validation ---

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
    # Check for overlapping existing merges.
    for r in range(top_row, top_row + row_span):
        for c in range(left_col, left_col + col_span):
            cell = grid.rows[r][c]
            if cell.is_covered:
                raise ValueError(
                    f"Cell ({r}, {c}) is already part of a merge "
                    f"anchored at ({cell.anchor_row}, {cell.anchor_col}). "
                    f"Split that merge first."
                )
            if (r != top_row or c != left_col) and (cell.colspan > 1 or cell.rowspan > 1):
                raise ValueError(
                    f"Cell ({r}, {c}) is itself a merge anchor "
                    f"(span {cell.rowspan}x{cell.colspan}). "
                    f"Split it first before merging this region."
                )


# --- DataFrame Conversion ---

def dataframe_to_grid(
    dataframe: "pd.DataFrame",
    include_header: bool = True,
) -> TableGrid:
    """Convert a pandas DataFrame into a TableGrid.

    If include_header is True (default), row 0 of the grid contains the
    column names, and subsequent rows contain the data.
    """
    import pandas as pd

    cols = [str(c) for c in dataframe.columns]
    rows: list[list[Cell]] = []

    if include_header:
        header_row = [Cell(content=name) for name in cols]
        rows.append(header_row)

    for row_values in dataframe.itertuples(index=False, name=None):
        cells = []
        for value in row_values:
            content = "" if pd.isna(value) else str(value)
            cells.append(Cell(content=content))
        rows.append(cells)

    return TableGrid(rows=rows, has_header=include_header)
```

### Key Design Points

- `Cell` is a mutable dataclass (not frozen) since the editor modifies cells
  in place.
- `CellAlignment` is an enum (`"l"`, `"c"`, `"r"`) matching LaTeX column
  spec letters. `None` means "inherit from `ConversionOptions.text_alignment`".
- `is_covered` + `anchor_row`/`anchor_col` replaces the need for a separate
  merge-region list. The anchor cell's `colspan`/`rowspan` are the source of
  truth.
- `TableGrid` owns all mutation methods (merge, split, insert, delete) so
  invariants are maintained in one place.
- `dataframe_to_grid()` is a pure function for initial conversion.

### State Management Changes in main.py

```python
state: dict[str, object] = {
    "grid": None,            # TableGrid -- the live editable model
    "original_grid": None,   # TableGrid -- snapshot for reset
    "dataframe": None,       # pd.DataFrame -- kept for preprocessing ops
    "original_dataframe": None,
}
```

**Workflow:**
1. File load -> `read_table_file()` -> DataFrame -> `dataframe_to_grid()` -> TableGrid.
   Store both DataFrame (original) and grid (working copy).
2. Preprocessing operations (transpose, case, drop empty/duplicates) operate
   on the DataFrame, then re-derive the grid via `dataframe_to_grid()`. This
   avoids reimplementing all preprocessing on the grid model.
3. Once the user enters "editor mode" (merge/edit cells), they work on the
   grid directly. Preprocessing buttons could be disabled or could warn that
   they will reset merge information.
4. Reset: restore `original_grid` (deep copy) and `original_dataframe`.
5. `render_output()` calls `grid_to_latex(grid, options)` instead of
   `dataframe_to_latex(df, options)`.

---

## Converter API Changes

### New Public Function

```python
def grid_to_latex(
    grid: TableGrid,
    options: ConversionOptions | None = None,
) -> str:
    """Convert a TableGrid into a LaTeX table string.

    Supports merged cells (multicolumn, multirow), per-cell alignment,
    and all existing ConversionOptions features.
    """
```

### Backward Compatibility

`dataframe_to_latex()` remains unchanged. Internally it could optionally
delegate to `grid_to_latex` by converting the DataFrame first, but this is
not required for Phase A -- keeping both paths avoids regressions.

### Column Spec Changes

The LaTeX column spec (e.g., `|c|c|c|`) defines the *base* alignment for each
column. With per-cell alignment, the base spec still uses
`options.text_alignment` uniformly. Per-cell overrides are handled via
`\multicolumn{1}{spec}{content}` at the cell level (a single-column
multicolumn is valid LaTeX and is the standard way to override alignment for
one cell).

```python
def _build_grid_column_spec(num_cols: int, options: ConversionOptions) -> str:
    """Build base column spec. Same logic as _build_column_spec."""
    letter = options.text_alignment
    if options.border_style == "all":
        return "|" + "|".join(letter for _ in range(num_cols)) + "|"
    return letter * num_cols
```

### Row Building Algorithm

For each row in the grid:

```
col = 0
cells_output = []
while col < num_cols:
    cell = grid.rows[row_idx][col]

    if cell.is_covered:
        # Covered by a multirow from a previous row -- emit empty placeholder.
        # (Covered by multicolumn from left -- already skipped by colspan jump.)
        cells_output.append("")
        col += 1
        continue

    content = format_cell_content(cell, row_idx, col, options)

    # --- Multirow wrapping (must come before multicolumn) ---
    if cell.rowspan > 1:
        content = f"\\multirow{{{cell.rowspan}}}{{*}}{{{content}}}"

    # --- Multicolumn wrapping ---
    if cell.colspan > 1 or cell.alignment is not None:
        col_spec = _multicolumn_spec(col, cell.colspan, cell.alignment, options)
        content = f"\\multicolumn{{{cell.colspan}}}{{{col_spec}}}{{{content}}}"

    cells_output.append(content)
    col += cell.colspan  # skip covered columns
```

### Multicolumn Spec Builder

The `\multicolumn` spec must re-declare vertical rules at the boundaries:

```python
def _multicolumn_spec(
    start_col: int,
    colspan: int,
    alignment: CellAlignment | None,
    options: ConversionOptions,
) -> str:
    """Build the column spec for a \\multicolumn command.

    Includes vertical rules at the left and right boundaries based on
    border_style. The alignment letter comes from the cell's per-cell
    alignment or falls back to options.text_alignment.
    """
    letter = alignment.value if alignment else options.text_alignment
    if options.border_style == "all":
        # Left rule if this is column 0, right rule always.
        left = "|" if start_col == 0 else ""
        return f"{left}{letter}|"
    return letter
```

### Rule / Hline Logic with Multirow

When `\multirow` spans rows r to r+n-1, a full `\hline` after rows
r through r+n-2 would cut through the multirow. Instead:

**Algorithm for row separators:**

```
After emitting row r:
    if border_style requires a rule after this row:
        # Collect columns that are "mid-multirow" (covered by a rowspan
        # anchored above and extending below this row).
        blocked_cols = set()
        for c in range(num_cols):
            cell = grid.rows[r][c]
            if cell.is_covered and cell.anchor_row is not None:
                anchor = grid.rows[cell.anchor_row][cell.anchor_col]
                if cell.anchor_row + anchor.rowspan > r + 1:
                    # This column is blocked at this boundary.
                    for cc in range(cell.anchor_col, cell.anchor_col + anchor.colspan):
                        blocked_cols.add(cc)
            elif not cell.is_covered and cell.rowspan > 1:
                if r + cell.rowspan > r + 1:  # i.e., rowspan > 1
                    for cc in range(c, c + cell.colspan):
                        blocked_cols.add(cc)

        if not blocked_cols:
            emit full \hline (or \midrule / \bottomrule for booktabs)
        else:
            # Emit \cline{start-end} (or \cmidrule{start-end} for booktabs)
            # for each contiguous range of non-blocked columns.
            ranges = _contiguous_ranges(
                [c for c in range(num_cols) if c not in blocked_cols]
            )
            for (start, end) in ranges:
                if options.border_style == "booktabs":
                    emit f"\\cmidrule{{{start+1}-{end+1}}}"
                else:
                    emit f"\\cline{{{start+1}-{end+1}}}"
```

Helper:
```python
def _contiguous_ranges(cols: list[int]) -> list[tuple[int, int]]:
    """Group sorted column indices into contiguous (start, end) ranges."""
    if not cols:
        return []
    ranges = []
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
```

### usepackage Changes

In `_wrap_full_document`, add `"multirow"` to the packages list whenever
the grid contains any cell with `rowspan > 1`:

```python
# In _wrap_full_document or a new _wrap_grid_full_document:
if any(
    cell.rowspan > 1
    for row in grid.rows
    for cell in row
    if not cell.is_covered
):
    packages.append("multirow")
```

---

## Validation Rules

### Merge Validation (in `validate_merge()`)

1. **Rectangular selection only**: The merge region is defined by
   `(top_row, left_col, row_span, col_span)`. The UI must translate any
   selection into these four integers.

2. **No overlapping merges**: Every cell in the proposed region must be
   either (a) a non-merged, non-covered cell, or (b) the exact anchor of
   the same merge being re-applied. Any `is_covered` cell or any anchor
   cell with span > 1 (other than the proposed anchor) causes a
   `ValueError`.

3. **Bounds checking**: The region must not extend beyond the grid
   dimensions.

4. **Minimum size**: `row_span * col_span > 1` (cannot "merge" a single
   cell).

### Split Validation

- Only valid on an anchor cell (not covered, colspan > 1 or rowspan > 1).
- Attempting to split a non-merged cell raises `ValueError`.

### Error Surfacing

- All validation errors are raised as `ValueError` with descriptive
  messages.
- The UI layer catches `ValueError` and displays the message via the
  existing `set_status(message, is_error=True)` pattern in main.py.
- This follows the existing codebase convention (e.g.,
  `dataframe_to_latex` raises `ValueError` for empty DataFrames).

---

## Module Layout

### New Modules

| Module | Purpose | Estimated LOC |
|--------|---------|---------------|
| `table_model.py` | `Cell`, `CellAlignment`, `TableGrid` dataclasses; merge/split/insert/delete methods; `validate_merge()`; `dataframe_to_grid()` | 300-400 |
| `grid_converter.py` | `grid_to_latex()` function and all private helpers for grid-based LaTeX generation (multicolumn spec, row building, cline logic) | 250-350 |
| `tests/test_table_model.py` | Unit tests for TableGrid: merge, split, insert, delete, validation, dataframe_to_grid | 300-400 |
| `tests/test_grid_converter.py` | Unit tests for grid_to_latex: multicolumn, multirow, cline, per-cell alignment, all border styles, full document with multirow package | 400-500 |
| `grid_editor.py` | Flet UI helper: builds the interactive grid of TextFields, handles selection, context menu for merge/split, insert/delete buttons | 300-400 |

### Modified Modules

| Module | Changes | LOC Delta |
|--------|---------|-----------|
| `converter.py` | No changes in Phase A. In Phase B+, `dataframe_to_latex` may optionally delegate to `grid_to_latex` internally. | ~0 |
| `main.py` | Add grid state, replace `render_output` to use `grid_to_latex`, wire up grid_editor widget, disable preprocessing when merges exist. | +50-80 |
| `preprocessing.py` | No changes. Preprocessing continues to work on DataFrames; the grid is re-derived after preprocessing. | 0 |

### File Size Compliance

All new modules target 200-400 LOC. `tests/test_grid_converter.py` may
reach ~500 LOC due to comprehensive border-style x merge-type
combinations, but can be split into `test_grid_converter_basic.py` and
`test_grid_converter_merges.py` if needed.

---

## Implementation Plan (phased)

### Phase A: Data Model + Grid Converter + Tests

**Goal**: Pure-logic foundation with no UI changes. Everything testable
with pytest.

**Deliverables**:
1. `table_model.py` -- Cell, CellAlignment, TableGrid, validate_merge,
   dataframe_to_grid.
2. `grid_converter.py` -- grid_to_latex with multicolumn, multirow, cline
   logic, full_document multirow package support.
3. `tests/test_table_model.py` -- merge/split/insert/delete/validation tests.
4. `tests/test_grid_converter.py` -- output correctness for all
   ConversionOptions x merge combinations.

**Dependencies**: None (new modules only).

**Acceptance Checks**:
```bash
uv run pytest -v tests/test_table_model.py tests/test_grid_converter.py
uv run pytest -v tests/test_converter.py   # existing tests still pass
uv run ruff check .
uv run ruff format --check .
```

**Estimated effort**: 2-3 sessions.

### Phase B: Read-Only Grid Render in Flet

**Goal**: Display the loaded table as an interactive grid (TextFields in a
Flet Column/Row layout) instead of (or alongside) the raw LaTeX output.
No editing yet.

**Deliverables**:
1. `grid_editor.py` -- `build_grid_view(grid: TableGrid) -> ft.Control`
   function that renders the grid as a Flet widget tree. Merged cells
   visually span multiple grid positions. Covered positions are hidden or
   disabled.
2. `main.py` changes -- Wire grid view into the left pane. Switch
   `render_output()` to use `grid_to_latex()`.

**Dependencies**: Phase A complete.

**Acceptance Checks**:
```bash
uv run pytest -v          # all tests pass
uv run ruff check .
# Manual: load a CSV/XLSX, see grid rendered, LaTeX output matches
```

**Estimated effort**: 1-2 sessions.

### Phase C: Interactive Editing UI

**Goal**: Full editor functionality -- edit cell text, merge/split,
insert/delete rows/columns, per-cell alignment picker.

**Deliverables**:
1. `grid_editor.py` enhancements:
   - Cell text editing via TextField on_change -> `grid.set_content()`.
   - Cell selection (click/shift-click for range).
   - Context menu or toolbar: Merge Selected, Split, Set Alignment (l/c/r).
   - Insert Row Above/Below, Insert Column Left/Right buttons.
   - Delete Row, Delete Column buttons.
2. `main.py` changes:
   - Toolbar for grid operations.
   - Disable preprocessing buttons when merges exist (or add confirmation
     dialog).
   - Live LaTeX re-render on any grid change.

**Dependencies**: Phase B complete.

**Acceptance Checks**:
```bash
uv run pytest -v
uv run ruff check .
# Manual: merge cells, verify \multicolumn/\multirow in output.
# Manual: insert/delete rows/cols, verify output.
# Manual: per-cell alignment, verify \multicolumn{1}{spec}{content}.
# Manual: split merged cell, verify output reverts.
# Manual: reset, verify original grid restored.
```

**Estimated effort**: 2-3 sessions.

---

## Risks

### 1. Multirow + Hline/Cline Complexity (High)

The interaction between `\multirow`, `\hline`, `\cline`, and `\cmidrule`
is one of the most error-prone areas in LaTeX table generation. Edge cases
include:
- A multirow and multicolumn on the same cell (both commands nest).
- Multiple multirow spans in the same row requiring multiple `\cline`
  ranges.
- Booktabs `\cmidrule` with trim options `(lr)` for visual polish.
- `\cline` does not respect `\multicolumn` internal rules -- the column
  indices in `\cline` are always physical column indices.

**Mitigation**: Comprehensive test matrix covering all border_style x
merge combinations. Start with "all" and "none" border styles in Phase A;
add booktabs in a follow-up.

### 2. Insert/Delete Row/Column with Active Merges (Medium)

Inserting or deleting rows/columns that intersect with merged regions
requires careful coordinate adjustment. Off-by-one errors can corrupt the
grid (orphaned covered cells, wrong anchor references).

**Mitigation**: Unit tests for insert/delete at every position relative to
a merge (before, at anchor, inside span, after). Add a
`_validate_grid_integrity()` debug helper that asserts all covered cells
have valid anchor references and all anchors' spans match their covered
cells.

### 3. Preprocessing vs Grid Divergence (Medium)

Preprocessing functions (transpose, case, drop) work on the DataFrame.
After preprocessing, the grid is re-derived, discarding any merges or
per-cell alignment the user had set up. This could be surprising.

**Mitigation**: Two approaches (decide during Phase C):
- (a) Disable preprocessing when merges exist, with a warning.
- (b) Apply preprocessing to the grid directly (requires reimplementing
  transpose etc. on the grid model -- significant work).
Recommend (a) for Phase C; (b) as a future enhancement.

### 4. Large Table Performance in Flet Grid (Low-Medium)

Rendering 100+ rows of TextFields may be slow in Flet. The current MVP
targets "report-sized" tables (typically < 50 rows, < 20 columns), so
this is unlikely to be a blocker.

**Mitigation**: If performance becomes an issue, implement virtual
scrolling (render only visible rows) as a Phase D optimization.

### 5. Undo/Redo Not Planned (Low)

The current design has no undo/redo stack for grid edits (merge, split,
insert, delete, text changes). Users can only reset to the original.

**Mitigation**: Acceptable for initial release. If needed later, implement
a command-pattern undo stack on `TableGrid` mutations.

---

## Appendix: LaTeX Output Examples

### Horizontal Merge (multicolumn)

Input grid (3x3, cells (0,0)-(0,1) merged):

| Merged Header | | C |
|---|---|---|
| 1 | 2 | 3 |
| 4 | 5 | 6 |

Output (border_style="all"):
```latex
\begin{tabular}{|c|c|c|}
\hline
\multicolumn{2}{|c|}{Merged Header} & C \\
\hline
1 & 2 & 3 \\
\hline
4 & 5 & 6 \\
\hline
\end{tabular}
```

### Vertical Merge (multirow)

Input grid (3x2, cells (0,0)-(1,0) merged):

| Span | B |
|---|---|
| (covered) | D |
| E | F |

Output (border_style="all"):
```latex
\begin{tabular}{|c|c|}
\hline
\multirow{2}{*}{Span} & B \\
\cline{2-2}
 & D \\
\hline
E & F \\
\hline
\end{tabular}
```

### Combined Multicolumn + Multirow

Input grid (3x3, cells (0,0)-(1,1) merged as 2x2):

| Big Cell | | C |
|---|---|---|
| (covered) | (covered) | F |
| G | H | I |

Output (border_style="all"):
```latex
\begin{tabular}{|c|c|c|}
\hline
\multicolumn{2}{|c|}{\multirow{2}{*}{Big Cell}} & C \\
\cline{3-3}
\multicolumn{2}{|c|}{} & F \\
\hline
G & H & I \\
\hline
\end{tabular}
```

Note: In the second row, the covered columns under the 2x2 merge emit
`\multicolumn{2}{|c|}{}` (empty multicolumn) to maintain the column
structure while the `\multirow` from the anchor fills the visual space.
