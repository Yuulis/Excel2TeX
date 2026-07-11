"""Tests for grid_history: undo/redo history manager for TableGrid snapshots."""

import copy

from grid_converter import grid_to_latex
from grid_history import MAX_HISTORY, GridHistory
from table_model import Cell, TableGrid

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _grid_2x2() -> TableGrid:
    """2-row, 2-col grid with header."""
    return TableGrid(
        rows=[
            [Cell(content="A"), Cell(content="B")],
            [Cell(content="1"), Cell(content="2")],
        ],
        has_header=True,
    )


def _grid_3x3() -> TableGrid:
    """3-row, 3-col grid for merge tests."""
    return TableGrid(
        rows=[
            [Cell(content="A"), Cell(content="B"), Cell(content="C")],
            [Cell(content="1"), Cell(content="2"), Cell(content="3")],
            [Cell(content="4"), Cell(content="5"), Cell(content="6")],
        ],
        has_header=True,
    )


# ---------------------------------------------------------------------------
# Tests -- can_undo / can_redo flags
# ---------------------------------------------------------------------------


class TestGridHistoryFlags:
    """Tests for can_undo and can_redo properties."""

    def test_initial_state_cannot_undo(self) -> None:
        history = GridHistory()
        assert not history.can_undo

    def test_initial_state_cannot_redo(self) -> None:
        history = GridHistory()
        assert not history.can_redo

    def test_after_push_can_undo(self) -> None:
        history = GridHistory()
        history.push(_grid_2x2())
        assert history.can_undo

    def test_after_push_cannot_redo(self) -> None:
        history = GridHistory()
        history.push(_grid_2x2())
        assert not history.can_redo

    def test_after_undo_can_redo(self) -> None:
        history = GridHistory()
        grid = _grid_2x2()
        history.push(grid)
        history.undo(grid)
        assert history.can_redo

    def test_after_undo_all_cannot_undo(self) -> None:
        history = GridHistory()
        grid = _grid_2x2()
        history.push(grid)
        history.undo(grid)
        assert not history.can_undo


# ---------------------------------------------------------------------------
# Tests -- push / undo / redo sequence
# ---------------------------------------------------------------------------


class TestGridHistorySequence:
    """Tests for push/undo/redo returning correct snapshots."""

    def test_undo_returns_previous_state(self) -> None:
        history = GridHistory()
        grid = _grid_2x2()
        history.push(grid)
        grid.set_content(1, 0, "CHANGED")
        restored = history.undo(grid)
        assert restored is not None
        assert restored.get_cell(1, 0).content == "1"

    def test_redo_returns_undone_state(self) -> None:
        history = GridHistory()
        grid = _grid_2x2()
        history.push(grid)
        grid.set_content(1, 0, "CHANGED")
        restored = history.undo(grid)
        assert restored is not None
        redone = history.redo(restored)
        assert redone is not None
        assert redone.get_cell(1, 0).content == "CHANGED"

    def test_multiple_pushes_undo_in_order(self) -> None:
        history = GridHistory()
        grid = _grid_2x2()

        history.push(copy.deepcopy(grid))
        grid.set_content(1, 0, "X")

        history.push(copy.deepcopy(grid))
        grid.set_content(1, 1, "Y")

        # Undo second mutation.
        restored = history.undo(grid)
        assert restored is not None
        assert restored.get_cell(1, 0).content == "X"
        assert restored.get_cell(1, 1).content == "2"

        # Undo first mutation.
        restored2 = history.undo(restored)
        assert restored2 is not None
        assert restored2.get_cell(1, 0).content == "1"

    def test_undo_on_empty_returns_none(self) -> None:
        history = GridHistory()
        assert history.undo(_grid_2x2()) is None

    def test_redo_on_empty_returns_none(self) -> None:
        history = GridHistory()
        assert history.redo(_grid_2x2()) is None


# ---------------------------------------------------------------------------
# Tests -- redo cleared on new push
# ---------------------------------------------------------------------------


class TestGridHistoryRedoClear:
    """Tests that a new push clears the redo stack."""

    def test_push_clears_redo(self) -> None:
        history = GridHistory()
        grid = _grid_2x2()
        history.push(grid)
        grid.set_content(1, 0, "X")
        history.undo(grid)
        assert history.can_redo

        # New push should clear redo.
        history.push(_grid_2x2())
        assert not history.can_redo

    def test_redo_after_new_push_returns_none(self) -> None:
        history = GridHistory()
        grid = _grid_2x2()
        history.push(grid)
        history.undo(grid)

        history.push(_grid_2x2())
        assert history.redo(_grid_2x2()) is None


# ---------------------------------------------------------------------------
# Tests -- depth cap
# ---------------------------------------------------------------------------


class TestGridHistoryDepthCap:
    """Tests that the undo stack respects max_depth."""

    def test_depth_cap_enforced(self) -> None:
        cap = 5
        history = GridHistory(max_depth=cap)
        grid = _grid_2x2()
        for i in range(cap + 3):
            g = copy.deepcopy(grid)
            g.set_content(1, 0, str(i))
            history.push(g)
        # Should only have `cap` items on undo stack.
        count = 0
        current = grid
        while history.can_undo:
            current = history.undo(current)
            count += 1
        assert count == cap

    def test_default_max_is_constant(self) -> None:
        history = GridHistory()
        assert history._max_depth == MAX_HISTORY


# ---------------------------------------------------------------------------
# Tests -- clear
# ---------------------------------------------------------------------------


class TestGridHistoryClear:
    """Tests for clear() resetting both stacks."""

    def test_clear_empties_undo(self) -> None:
        history = GridHistory()
        history.push(_grid_2x2())
        history.clear()
        assert not history.can_undo

    def test_clear_empties_redo(self) -> None:
        history = GridHistory()
        grid = _grid_2x2()
        history.push(grid)
        history.undo(grid)
        assert history.can_redo
        history.clear()
        assert not history.can_redo


# ---------------------------------------------------------------------------
# Tests -- discard_last
# ---------------------------------------------------------------------------


class TestGridHistoryDiscardLast:
    """Tests for discard_last() rolling back a failed mutation."""

    def test_discard_last_removes_top(self) -> None:
        history = GridHistory()
        history.push(_grid_2x2())
        assert history.can_undo
        history.discard_last()
        assert not history.can_undo

    def test_discard_last_on_empty_is_safe(self) -> None:
        history = GridHistory()
        history.discard_last()  # Should not raise.
        assert not history.can_undo


# ---------------------------------------------------------------------------
# Tests -- undo/redo of merge (integration with grid_to_latex)
# ---------------------------------------------------------------------------


class TestGridHistoryMergeIntegration:
    """Tests that undo restores unmerged grid and redo re-applies."""

    def test_undo_merge_restores_unmerged(self) -> None:
        grid = _grid_3x3()
        history = GridHistory()
        history.push(grid)

        grid.merge_cells(0, 0, 1, 2)
        latex_merged = grid_to_latex(grid)
        assert r"\multicolumn{2}" in latex_merged

        restored = history.undo(grid)
        assert restored is not None
        latex_unmerged = grid_to_latex(restored)
        assert r"\multicolumn" not in latex_unmerged
        assert restored.get_cell(0, 0).colspan == 1
        assert not restored.get_cell(0, 1).is_covered

    def test_redo_reapplies_merge(self) -> None:
        grid = _grid_3x3()
        history = GridHistory()
        history.push(grid)

        grid.merge_cells(0, 0, 1, 2)
        restored = history.undo(grid)
        assert restored is not None

        reapplied = history.redo(restored)
        assert reapplied is not None
        latex = grid_to_latex(reapplied)
        assert r"\multicolumn{2}" in latex
        assert reapplied.get_cell(0, 0).colspan == 2
        assert reapplied.get_cell(0, 1).is_covered

    def test_undo_preserves_deep_independence(self) -> None:
        """Mutating the restored grid must not affect the redo snapshot."""
        grid = _grid_3x3()
        history = GridHistory()
        history.push(grid)
        grid.merge_cells(0, 0, 1, 2)

        restored = history.undo(grid)
        assert restored is not None
        restored.set_content(0, 0, "MODIFIED")

        reapplied = history.redo(restored)
        assert reapplied is not None
        # Redo should return the merged grid with original content, not "MODIFIED".
        assert reapplied.get_cell(0, 0).content == "A"
        assert reapplied.get_cell(0, 0).colspan == 2
