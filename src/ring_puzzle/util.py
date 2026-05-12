"""Utility functions and data structures for the ring puzzle solver.

Note the solver is split into two parts: the early-game solver, which greedily extends the longest
run of consecutive beads until it reaches length 16, and the endgame solver, which uses a
precomputed table of optimal solutions for all configurations of the 4 flipping beads when the
protected run is length 16. This module contains shared utilities used by both solvers, as well as
the main program loop for the interactive terminal interface.
"""

from dataclasses import dataclass, field

# Flip moves reverse the first FLIP_SIZE elements of the ring.
FLIP_SIZE = 4

# Number of beads in the ring.
RING_SIZE = 20

# A solved ring is the numbers 1 through RING_SIZE in order, allowing for any rotation but
# not reflections.
SOLVED_RING = list(range(1, RING_SIZE + 1))

ENDGAME_RUN_LENGTH = RING_SIZE - FLIP_SIZE

type MoveList = list[str]

# A tuple of FLIP_SIZE ints, representing the values of the beads in the flipping zone of the
# puzzle.
type Quartet = tuple[int, int, int, int]


def is_solved(ring: list[int]) -> bool:
    """Check if the ring is in a solved state, allowing for any rotation."""
    return any(
        ring == SOLVED_RING[offset:] + SOLVED_RING[:offset]
        for offset in range(len(SOLVED_RING))
    )


def get_max_run(ring: list[int]) -> tuple[int, int, int | None]:
    """Find the longest run of consecutive numbers in the ring.

    Returns a tuple of (start_index, length, dist) for the longest run.
    Note that `start_index` is a position, not the value of the element (puzzle bead) at that
    position.

    `dist` is the cyclic distance from the end of the run to the next consecutive number.
    This is important for determining how to manipulate the ring to extend the run.

    Note that `is_solved` is faster than checking if `get_max_run` returns a run of length
    `RING_SIZE`.

    Args:
        ring: A list of integers representing the current configuration of the ring.
              May be normalized or not.
    """
    ring_size = len(ring)

    # Doubling the ring ensures the consecutive run appears contiguously in the list representation.
    doubled_ring = ring + ring
    max_run_start = 0
    max_run_length = 1

    # Iterate through each starting position in the original ring and count the length of the run
    # of consecutive numbers starting from that position.
    for start in range(ring_size):
        current_run_length = 1

        # While the run length is less than the ring size (ensure we don't count more than one full
        # loop) and the next number is consecutive (modulo `ring_size`), increment the
        # run length.
        while (
            current_run_length < ring_size
            and (
                doubled_ring[start + current_run_length]
                - doubled_ring[start + current_run_length - 1]
            )
            % ring_size
            == 1
        ):
            current_run_length += 1

        # If a new longest run is found, update the max run information.
        if current_run_length > max_run_length:
            max_run_start = start
            max_run_length = current_run_length

    # Calculate the distance to the next consecutive number after the run.
    # Return None if the whole ring is a run.
    if max_run_length == ring_size:
        dist = None
    else:
        # Get the bead values at the start and end of the run.
        num_run_start = ring[max_run_start]
        num_run_end = ((num_run_start + max_run_length - 2) % ring_size) + 1
        # Search for the next consecutive number after the run.
        next_consecutive = (num_run_end % ring_size) + 1
        dist = None
        run_end = (max_run_start + max_run_length - 1) % ring_size
        for i in range(ring_size):
            if ring[i] == next_consecutive:
                dist = (i - run_end) % ring_size
                break
    return max_run_start, max_run_length, dist


def normalize(ring: list[int]) -> list[int]:
    """Normalize the ring.

    Normalization shifts all bead labels modulo 20 so that the longest run of consecutive
    numbers starts at 1."""

    max_run_start, _, _ = get_max_run(ring)

    # Shift labels in 1-based modular arithmetic so the run starts at bead 1.
    offset = 1 - ring[max_run_start]

    # Shift all bead labels by the calculated offset.
    normalized_ring = [((bead + offset - 1) % RING_SIZE) + 1 for bead in ring]
    return normalized_ring


@dataclass
class RingState:
    ring: list[int]
    """Current configuration of the ring after moves applied"""
    offset: int = field(default=0)
    """If we normalize the ring in the autosolver, this is the offset compared to the
    original ring (after any manual normalization)."""
    moves: list[str] = field(default_factory=list)
    """List of moves applied to reach this state. Each move is one of 'L', 'R', 'F'
    (for left, right, flip)."""


def rotate_left(state: RingState, steps: int = 1) -> RingState:
    """Rotate the ring left by `steps` positions.

    Each step moves the bead at position 0 to the end of the ring.
    Negative steps are interpreted as rightward rotations.
    """
    if steps < 0:
        return rotate_right(state, -steps)
    ring_size = len(state.ring)
    steps %= ring_size
    if steps == 0:
        return state

    return RingState(
        ring=state.ring[steps:] + state.ring[:steps],
        offset=state.offset,
        moves=state.moves + ["L"] * steps,
    )


def rotate_right(state: RingState, steps: int = 1) -> RingState:
    """Rotate the ring right by `steps` positions.

    Each step moves the last bead to position 0.
    Negative steps are interpreted as leftward rotations.
    """
    if steps < 0:
        return rotate_left(state, -steps)
    ring_size = len(state.ring)
    steps %= ring_size
    if steps == 0:
        return state

    return RingState(
        ring=state.ring[-steps:] + state.ring[:-steps],
        offset=state.offset,
        moves=state.moves + ["R"] * steps,
    )


def rotate_shortest(state: RingState, left_steps: int) -> RingState:
    """Rotate by the shorter path to the target position.

    `left_steps` is the distance expressed as leftward steps. The function
    computes the equivalent rightward distance and applies whichever requires
    fewer moves, preferring left on a tie.
    """
    ring_size = len(state.ring)
    left_steps %= ring_size
    right_steps = (ring_size - left_steps) % ring_size

    if left_steps <= right_steps:
        return rotate_left(state, left_steps)

    return rotate_right(state, right_steps)
