"""Macros that shift a target bead left/right by 1, 2, or 3 positions.

Used to grow the protected run of consecutive beads in the early-game solver.
"""

from ring_puzzle.util import RingState


def shift_left3(state: RingState) -> RingState:
    """Move target bead A 3 positions left, from position 3 to position 0.

    Precondition: ring is `[a, b, c, A], ...` — target at position 3, and none of
    a, b, c, A are in the run we want to grow (so they can be freely rearranged).

    Result:       `[A, c, b, a], ...` — target now at position 0, 3 closer to the run tail.
    If the position just left of A was the run tail, it has now grown by one bead (A).

    Moves: F  (1 move)
    """
    new_ring = state.ring[:]
    new_ring[0], new_ring[1], new_ring[2], new_ring[3] = (
        state.ring[3],
        state.ring[2],
        state.ring[1],
        state.ring[0],
    )
    return RingState(ring=new_ring, offset=state.offset, moves=state.moves + ["F"])


def shift_left2(state: RingState) -> RingState:
    """Move target bead A 2 positions left, from position 2 to position 0.

    Precondition: ring is `run_tail, [a, b, A, c], d, ...` where the square brackets indicate the
    flip zone (a at position 0), and none of the beads a, b, A, c, d are in the run we want to grow
    (so they can be freely rearranged).

    Result:       `run_tail, [A, c, d, a], b ...` — new run includes at least A.

    Derivation (positions 0–4 shown):
      [a, b, A, c], d  →L→  a, [b, A, c, d]  →F→  a, [d, c, A, b]
      →R→  [a, d, c, A], b  →F→  [A, c, d, a], b

    Moves: L F R F  (4 moves)
    """
    new_ring = state.ring[:]
    for new_pos, old_pos in enumerate([2, 3, 4, 0, 1]):
        new_ring[new_pos] = state.ring[old_pos]
    return RingState(ring=new_ring, offset=state.offset, moves=state.moves + ["L", "F", "R", "F"])


def shift_left1(state: RingState) -> RingState:
    """Move target bead A 1 position left, from position 1 to position 0.

    Precondition: ring is `run_tail, [a, A, b, c], d, ...` where the square brackets indicate the
    flip zone (a at position 0), and none of the beads a, b, A, c, d are in the run we want to grow
    (so they can be freely rearranged).

    Result:       `run_tail, [A, a, d, c], b ...` — new run includes at least A.

    Derivation (positions 0–4 shown):
      [a, A, b, c], d  →F→ [c, b, A, a], d →shift_left2→ [A, a, d, c], b

    Moves: F L F R F  (5 moves)
    """
    new_ring = state.ring[:]
    for new_pos, old_pos in enumerate([1, 0, 4, 3, 2]):
        new_ring[new_pos] = state.ring[old_pos]
    return RingState(
        ring=new_ring,
        offset=state.offset,
        moves=state.moves + ["F", "L", "F", "R", "F"],
    )


def shift_right3(state: RingState) -> RingState:
    """Move target bead A 3 positions right, from position 0 to position 3.

    Precondition: ring is `[A, a, b, c], ...` — target at position 0, and none of A, a, b, c are in
    the run we want to grow (so they can be freely rearranged).

    Result:       `[c, b, a, A], ...` — target now at position 3, 3 closer to the run head. If
    the position just right of A was the run head, it has now grown by one bead (A).

    Moves: F  (1 move)
    """
    new_ring = state.ring[:]
    new_ring[0], new_ring[1], new_ring[2], new_ring[3] = (
        state.ring[3],
        state.ring[2],
        state.ring[1],
        state.ring[0],
    )
    return RingState(ring=new_ring, offset=state.offset, moves=state.moves + ["F"])


def shift_right2(state: RingState) -> RingState:
    """Move target bead P 2 positions right, from position 1 to position 3.

    Precondition: ring is `z, [a, P, b, c], run_head, ...` where the square brackets indicate the
    flip zone (a at position 0), and none of the beads z, a, P, b, or c are in the run
    we want to grow (so they can be freely rearranged).

    Result:       `b, [c, z, a, P], run_head, ...` — new run includes at least P.

    Derivation (last bead and positions 0–3 shown):
      z, [a, P, b, c]  →R→  [z, a, P, b], c  →F→  [b, P, a, z], c
      →L→  b, [P, a, z, c]  →F→  b, [c, z, a, P]

    Moves: R F L F  (4 moves)
    """
    new_ring = state.ring[:]
    new_ring[0] = state.ring[3]
    new_ring[1] = state.ring[-1]
    new_ring[2] = state.ring[0]
    new_ring[3] = state.ring[1]
    new_ring[-1] = state.ring[2]
    return RingState(ring=new_ring, offset=state.offset, moves=state.moves + ["R", "F", "L", "F"])


def shift_right1(state: RingState) -> RingState:
    """Move target bead P 1 position right, from position 2 to position 3.

    Precondition: ring is `z, [a, b, P, c], run_head, ...` where the square brackets indicate the
    flip zone (a at position 0), and none of the beads z, a, b, P, or c are in the run
    we want to grow (so they can be freely rearranged).

    Result:       `b, [a, z, c, P], run_head, ...` — new run includes at least P.

    Derivation (last bead and positions 0–3 shown):
      z, [a, b, P, c]  →F→  z, [c, P, b, a]  →shift_right2→  b, [a, z, c, P]

    Moves: F R F L F  (5 moves)
    """
    new_ring = state.ring[:]
    new_ring[1] = state.ring[-1]
    new_ring[2] = state.ring[3]
    new_ring[3] = state.ring[2]
    new_ring[-1] = state.ring[1]
    return RingState(
        ring=new_ring,
        offset=state.offset,
        moves=state.moves + ["F", "R", "F", "L", "F"],
    )
