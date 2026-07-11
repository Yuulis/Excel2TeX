"""Undo/redo history manager for TableGrid snapshots.

Maintains bounded stacks of deep-copied TableGrid snapshots to support
undo and redo of grid mutations.  Each ``push()`` saves a pre-mutation
snapshot.  Text-edit coalescing is the caller's responsibility (push once
per edit session, not per keystroke).
"""

from __future__ import annotations

import copy

from table_model import TableGrid

# Maximum number of undo snapshots to retain.
MAX_HISTORY = 50


class GridHistory:
    """Bounded undo/redo history for TableGrid snapshots.

    Usage pattern::

        history.push(grid)           # snapshot pre-mutation state
        grid.merge_cells(...)        # mutate
        # ... later ...
        restored = history.undo(grid)  # undo -> previous state
        re_done  = history.redo(restored)  # redo -> re-apply

    Any new ``push()`` clears the redo stack.  ``discard_last()`` rolls
    back a push when the subsequent mutation fails (e.g. ValueError).
    """

    def __init__(self, max_depth: int = MAX_HISTORY) -> None:
        self._undo_stack: list[TableGrid] = []
        self._redo_stack: list[TableGrid] = []
        self._max_depth = max_depth

    # -- query ---------------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        """Return True if there is at least one snapshot to undo to."""
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        """Return True if there is at least one snapshot to redo."""
        return len(self._redo_stack) > 0

    # -- mutation ------------------------------------------------------------

    def push(self, grid: TableGrid) -> None:
        """Save a deep-copied pre-mutation snapshot.  Clears redo stack."""
        snapshot = copy.deepcopy(grid)
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._max_depth:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def discard_last(self) -> None:
        """Remove the most recent undo snapshot (rollback on failed mutation)."""
        if self._undo_stack:
            self._undo_stack.pop()

    def undo(self, current: TableGrid) -> TableGrid | None:
        """Undo: restore previous state, push *current* to redo.

        Returns the restored ``TableGrid`` or ``None`` if stack is empty.
        """
        if not self._undo_stack:
            return None
        self._redo_stack.append(copy.deepcopy(current))
        return self._undo_stack.pop()

    def redo(self, current: TableGrid) -> TableGrid | None:
        """Redo: restore next state, push *current* to undo.

        Returns the restored ``TableGrid`` or ``None`` if stack is empty.
        """
        if not self._redo_stack:
            return None
        self._undo_stack.append(copy.deepcopy(current))
        return self._redo_stack.pop()

    def clear(self) -> None:
        """Clear both undo and redo stacks (e.g. on reset or file load)."""
        self._undo_stack.clear()
        self._redo_stack.clear()
