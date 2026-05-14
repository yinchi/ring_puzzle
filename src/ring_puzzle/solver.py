"""Early-game solver for the ring puzzle.

The ring is a circular sequence of 20 numbered beads. The goal is to arrange all beads
in ascending consecutive order using three legal moves:

  L  — rotate the ring one step to the left (bead at position 0 moves to the end)
  R  — rotate the ring one step to the right (last bead moves to position 0)
  F  — flip positions 0–3, reversing those four beads in place

Solve strategy
--------------

The solver works in two phases:

1. **Early game** (this module): repeatedly extend the longest consecutive run by one
   bead at a time, alternating between growing from the tail or the head of the run
   (whichever is cheaper). Continues until the run reaches `ENDGAME_RUN_LENGTH`.

2. **Endgame** (`endgame.py`): look up the remaining 4-bead configuration in a
   pre-computed table and replay the stored move sequence.

Shift primitives
----------------

Each extension step positions a target bead just outside the flip zone and applies one
of six compound shift macros. The macros come in symmetric pairs:

  Tail (`shift_leftN`)  — target moves N positions LEFT to land just right of the run
  Head (`shift_rightN`) — target moves N positions RIGHT to land just left of the run

For N=3 the shift costs 1 move (F); for N=2, 4 moves; for N=1, 5 moves.
"""

from .endgame import solve_endgame
from .shifts import shift_left1, shift_left2, shift_left3, shift_right1, shift_right2, shift_right3
from .util import (
    ENDGAME_RUN_LENGTH,
    FLIP_SIZE,
    MoveList,
    RingState,
    get_max_run,
    is_solved,
    rotate_shortest,
)


def extend_tail(state: RingState) -> RingState:
    """Extend the longest run of consecutive numbers at the TAIL by one bead.

    Symmetric counterpart to extend_head, which extends at the head.
    Rotates so the next consecutive bead is in the flip zone, then applies the appropriate
    `shift_leftN`.  Gaps greater than 3 are handled by a series of `shift_left3`'s before the final
    `shift_leftN`.

    The `dist` reported by `get_max_run` is the cyclic distance from the end of the run to the next
    consecutive number, which is the target bead. A distance of 1 means the target bead is adjacent
    to the run, which would actually make it part of the run, so the minimum value is 2 (one bead
    in between).

    When the run cannot be extended without touching the existing run, raises a `ValueError`, which
    signals that the autosolver should switch to a different strategy (e.g., table lookup) to
    solve the remaining configuration.
    """
    ring_size = len(state.ring)

    # Identify the run ONCE by the value of its head bead, not by position.
    # This forms a fixed target (by bead identities, not positions) to append or prepend to.
    start_index, original_run_length, _ = get_max_run(state.ring)

    # If the run is already the full ring, we shouldn't be trying to extend it.
    if original_run_length == ring_size:
        raise ValueError("Ring is already solved, no moves needed to extend the run.")

    # Compute the target bead values for appending or prepending to the run.
    # We compute both because sometimes during our manipulations, the run may grow at either end as
    # a side effect, so we want to be able to detect both.
    run_head_val = state.ring[start_index]
    run_tail_val = ((run_head_val + original_run_length - 2) % ring_size) + 1
    append_val = (run_tail_val % ring_size) + 1
    prepend_val = ((run_head_val - 2) % ring_size) + 1

    # Find the number of unsolved beads outside the run, which is the "maneuvering space"
    # available to extend the run without touching it.
    unsolved_length = ring_size - original_run_length

    # Large distances (4 or more) can be solved by repeatedly applying `shift_left3`, followed by a
    # final `shift_leftN` for the remaining distance of 1, 2, or 3. Terminate if the run
    # length increases early as a side effect, or raise `ValueError` if the shift cannot be applied
    # safely.
    while True:
        # Locate the run's current head and tail positions (change with each rotation).
        run_head_pos = next(i for i, v in enumerate(state.ring) if v == run_head_val)
        run_tail_pos = (run_head_pos + original_run_length - 1) % ring_size

        # Termination: the target is now adjacent to the run tail (tail grew),
        # or the predecessor landed adjacent to the run head as a side effect (head grew).
        if state.ring[(run_tail_pos + 1) % ring_size] == append_val:
            return state
        if state.ring[(run_head_pos - 1) % ring_size] == prepend_val:
            return state

        # Locate the target bead and compute its distance from the run tail.
        target_pos = next(i for i, v in enumerate(state.ring) if v == append_val)
        dist = (target_pos - run_tail_pos) % ring_size

        # Rotate target into the flip area and apply the appropriate shift operation.
        # Each shift_leftN expects the target at a specific position:
        # - shift_left1: target at position 1 (0-based, so the second bead in the flip zone)
        # - shift_left2: target at position 2 (0-based, so the third bead in the flip zone)
        # - shift_left3: target at position 3 (0-based, so the fourth bead in the flip zone)

        # Note that a distance of 3 or more automatically implies `unsolved_length` of at least 4,
        # which is enough maneuvering space to use `shift_left3` (a single flip) without touching
        # the run.  However, for distances of 2 or 3, we require `unsolved_length` of at least 5
        # to use `shift_left2` or `shift_left1` safely.
        if dist >= FLIP_SIZE:
            state = rotate_shortest(state, (target_pos - 3) % ring_size)
            state = shift_left3(state)
        elif dist == 3:
            if unsolved_length < 5:
                raise ValueError(
                    "Cannot extend the run without touching it, need a different strategy."
                )
            state = rotate_shortest(state, (target_pos - 2) % ring_size)
            state = shift_left2(state)
        elif dist == 2:
            if unsolved_length < 5:
                raise ValueError(
                    "Cannot extend the run without touching it, need a different strategy."
                )
            state = rotate_shortest(state, (target_pos - 1) % ring_size)
            state = shift_left1(state)
        else:
            raise ValueError(f"Unexpected distance value: {dist}")


def extend_head(state: RingState) -> RingState:
    """Extend the longest run at the HEAD by one bead (the predecessor value).

    Symmetric counterpart to extend_tail, which extends at the tail.
    Rotates so the predecessor bead P is in the flip zone with the run head
    just beyond it, then applies the appropriate shift_rightN.
    """
    ring_size = len(state.ring)

    # Identify the run ONCE by value (same reasoning as extend_tail).
    start_index, original_run_length, _ = get_max_run(state.ring)

    # If the run is already the full ring, we shouldn't be trying to extend it.
    if original_run_length == ring_size:
        raise ValueError("Ring is already solved, no moves needed to extend the head.")

    # Compute the target bead values for appending or prepending to the run.
    # We compute both because sometimes during our manipulations, the run may grow at either end as
    # a side effect, so we want to be able to detect both.
    run_head_val = state.ring[start_index]
    pred_val = ((run_head_val - 2) % ring_size) + 1  # locked predecessor to add at head
    run_tail_val = ((run_head_val + original_run_length - 2) % ring_size) + 1
    tail_next_val = (run_tail_val % ring_size) + 1  # used to detect tail-grew side-effect
    unsolved_length = ring_size - original_run_length

    while True:
        # Locate the run's current head position (changes with each rotation).
        run_head_pos = next(i for i, v in enumerate(state.ring) if v == run_head_val)
        run_tail_pos = (run_head_pos + original_run_length - 1) % ring_size

        # Termination: predecessor now adjacent to run head (head grew),
        # or next-after-tail landed adjacent as a side effect (tail grew).
        if state.ring[(run_head_pos - 1) % ring_size] == pred_val:
            return state
        if state.ring[(run_tail_pos + 1) % ring_size] == tail_next_val:
            return state

        # Locate the locked predecessor and compute clockwise distance to run head.
        pred_pos = next(i for i, v in enumerate(state.ring) if v == pred_val)
        dist_head = (run_head_pos - pred_pos) % ring_size

        # Rotate target into the flip area and apply the appropriate shift operation.
        # Each `shift_rightN` expects the target at a specific position:
        # - `shift_right1`: target at position 2 (0-based, so the third bead in the flip zone)
        # - `shift_right2`: target at position 1 (0-based, so the second bead in the flip zone)
        # - `shift_right3`: target at position 0 (0-based, so the first bead in the flip zone)

        # Note that a distance of 3 or more automatically implies `unsolved_length` of at least 4,
        # which is enough maneuvering space to use `shift_right3` (a single flip) without touching
        # the run.  However, for distances of 2 or 3, we require `unsolved_length` of at least 5
        # to use `shift_right2` or `shift_right1` safely.
        if dist_head >= FLIP_SIZE:
            # Rotate so predecessor is at position 0; run head at dist_head >= FLIP_SIZE.
            state = rotate_shortest(state, pred_pos % ring_size)
            state = shift_right3(state)
        elif dist_head == 3:
            if unsolved_length < 5:
                raise ValueError(
                    "Cannot extend the head without touching the run, need a different strategy."
                )
            # Rotate so predecessor is at position 1; run head at position 4.
            state = rotate_shortest(state, (pred_pos - 1) % ring_size)
            state = shift_right2(state)
        elif dist_head == 2:
            if unsolved_length < 5:
                raise ValueError(
                    "Cannot extend the head without touching the run, need a different strategy."
                )
            # Rotate so predecessor is at position 2; run head at position 4.
            state = rotate_shortest(state, (pred_pos - 2) % ring_size)
            state = shift_right1(state)
        else:
            raise ValueError(f"Unexpected dist_head value: {dist_head}")


def _two_ended_extend(state: RingState) -> RingState:
    """Extend the run by one bead, choosing the cheaper of tail or head extension.

    Tries both `extend_tail` (grow at the tail) and `extend_head` (grow at the
    head) independently from the current state, then returns the result that used
    fewer moves. If only one direction succeeds (e.g. the unsolved region is too
    small for the other), that result is returned unconditionally.

    The move count is determined by comparing the length of the full move list before and after
    the `extend_tail` or `extend_head` operation, and thus includes any necessary rotations to set
    up the shift macros, not just the shifts themselves.
    """
    tail_state: RingState | None = None
    head_state: RingState | None = None

    try:
        tail_state = extend_tail(state)
    except ValueError:
        pass

    try:
        head_state = extend_head(state)
    except ValueError:
        pass

    if tail_state is None and head_state is None:
        raise ValueError("Cannot extend the run at either end.")

    tail_cost = len(tail_state.moves) - len(state.moves) if tail_state is not None else float("inf")
    head_cost = len(head_state.moves) - len(state.moves) if head_state is not None else float("inf")

    # If both `extend_tail` and `extend_head` succeeded, return the one with fewer moves;
    # otherwise return the one that succeeded.
    if tail_cost <= head_cost:
        assert tail_state is not None
        return tail_state
    assert head_state is not None
    return head_state


def solve_from_state(state: RingState) -> RingState:
    """Solve from the given state using constructive then endgame phases.

    This repeatedly applies the two-ended greedy phase (extending at whichever
    end of the run is cheaper) until the protected run reaches the endgame
    threshold, then delegates to the endgame lookup solver.
    """
    while True:
        _, run_length, _ = get_max_run(state.ring)

        if is_solved(state.ring):
            return state

        if run_length >= ENDGAME_RUN_LENGTH:
            return solve_endgame(state)

        state = _two_ended_extend(state)


def solve_moves(ring: list[int]) -> MoveList:
    """Return a full replayable move sequence that solves the ring.

    Runs the two-phase solver (early-game greedy + endgame table lookup) and
    applies `cancel_opposite_rotations` to remove any LR or RL no-ops, which may occur at the
    boundary between the two phases.
    """
    moves = solve_from_state(RingState(ring=ring)).moves
    return cancel_opposite_rotations(moves)


def cancel_opposite_rotations(moves: MoveList) -> MoveList:
    """Remove consecutive opposite rotation pairs (LR or RL) from move sequence."""
    optimized: MoveList = []
    i = 0
    while i < len(moves):
        if i < len(moves) - 1 and (
            (moves[i] == "L" and moves[i + 1] == "R") or (moves[i] == "R" and moves[i + 1] == "L")
        ):
            # Skip both moves (they cancel)
            i += 2
        else:
            optimized.append(moves[i])
            i += 1
    return optimized
