# Ring Puzzle

This project is a small terminal implementation of the 20-bead oval track puzzle, also sold in
physical form as Top Spin by Binary Arts.

The puzzle has 20 numbered beads arranged on a loop. Two legal moves are available:

- rotate the entire loop left or right by one position
- flip the 4-bead window at the front, reversing those four beads in place

The goal is to return the beads to numerical order. In this codebase, a ring is considered solved
up to rotation, so any cyclic ordering `1, 2, ..., 20` counts as solved.

## Running

Run the game with:

```bash
uv run ring
```

Controls:

- left/right arrow: rotate the ring
- `f`: flip the front 4 beads
- `n`: start a new random puzzle
- `a`: reserved for the future auto-solver
- `q`: quit

## Current Structure

- [src/ring_puzzle/__init__.py](src/ring_puzzle/__init__.py) contains the curses UI and the live
	move logic.
- [src/ring_puzzle/solver.py](src/ring_puzzle/solver.py) contains helper logic for detecting the
	longest consecutive run and for the planned auto-solver macros.

## Solver Strategy

The current solver design is constructive rather than search-heavy.

### 1. Grow a protected consecutive run

The main idea is to find the longest cyclic run of consecutive values already present in the ring,
such as `..., 7, 8, 9, 10, ...`, and treat that as a protected solved region.

The planned `extend_max_run` step tries to add the next needed bead to that run without touching
the solved portion of the ring.

### 2. Use local insertion macros

The helpers `shift_left3`, `shift_left2`, and `shift_left1` encode short move sequences that move
the target bead left by 3, 2, or 1 positions within a small local workspace.

These macros are intended to work only while there is enough unsolved staging room after the
protected run. Once that slack becomes too small, the solver should stop using the constructive
phase rather than disturb the solved region.

### 3. Switch to an endgame table

When the remaining unsolved tail is too short for the 5-bead insertion macros, the solver should
switch to a small exact endgame lookup.

The current design assumption is that repeated successful applications of `extend_max_run` will
reduce the puzzle to a fixed solved block plus a final 4-bead endgame. If that invariant holds,
the endgame table is small enough to precompute directly.

### 4. Use normalization only as a lookup key

At the moment, normalization is not part of the live puzzle logic and should not be treated as a
legal move.

The likely use for normalization is only at the endgame boundary: canonicalize equivalent states
so one table can cover all rotationally equivalent cases. In other words, normalization should be
an internal solver representation choice, not a user-visible action.

## Notes

- The auto-solver is not implemented yet.
- The current UI supports manual play only.
- The project is intentionally small and experimental while the solver strategy is being worked
	out.

## Reference

For a mathematical and puzzle-oriented discussion of the same puzzle family, see Jamie
Mulholland's Oval Track / Top Spin notes:

- https://www.sfu.ca/~jtmulhol/math302/puzzles-ot.html
