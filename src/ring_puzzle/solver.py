from dataclasses import dataclass, field


def normalize(ring: list[int]) -> list[int]:
    """Normalize the ring.

    Normalization shifts all bead labels modulo 20 so that the longest run of consecutive
    numbers starts at 1."""

    max_run_start, _, _ = get_max_run(ring)

    # Shift labels in 1-based modular arithmetic so the run starts at bead 1.
    offset = 1 - ring[max_run_start]

    # Shift all bead labels by the calculated offset.
    normalized_ring = [((bead + offset - 1) % 20) + 1 for bead in ring]
    return normalized_ring


def get_max_run(ring: list[int]) -> tuple[int, int, int | None]:
    """Find the longest run of consecutive numbers in the ring.

    Returns a tuple of (start_index, length, dist) for the longest run.
    Note that `start_index` is a position, not the value of the element (puzzle bead) at that
    position.

    `dist` is the cyclic distance from the end of the run to the next consecutive number.
    This is important for determining how to manipulate the ring to extend the run.

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
    """Rotate the ring left by the requested number of steps."""
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
    """Rotate the ring right by the requested number of steps."""
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
    """Rotate by the shorter of the equivalent left and right distances."""
    ring_size = len(state.ring)
    left_steps %= ring_size
    right_steps = (ring_size - left_steps) % ring_size

    if left_steps <= right_steps:
        return rotate_left(state, left_steps)

    return rotate_right(state, right_steps)


def _stage_target_for_shift_left3(state: RingState, target_position: int) -> RingState:
    """Rotate so the target bead sits at index 3 for a `shift_left3` step."""
    return rotate_shortest(state, (target_position - 3) % len(state.ring))


def _stage_gap_front(state: RingState, run_end: int) -> RingState:
    """Rotate so the unsolved gap immediately after the protected run starts at index 0."""
    return rotate_shortest(state, (run_end + 1) % len(state.ring))


def extend_max_run(state: RingState) -> RingState:
    """Extend the longest run of consecutive numbers by one, if possible.

    Given a ring state, find a list of moves to extend the longest run of consecutive numbers
    by one, if possible, without touching the existing run. This is the core logic for the
    autosolver, which repeatedly calls this function to gradually solve the ring.

    The `dist` reported by `get_max_run` is the cyclic distance from the end of the run to the next
    consecutive number, which is the target bead. A distance of 1 means the target bead is adjacent
    to the run, which would actually make it part of the run, so the minimum value is 2 (one bead
    in between).

    When the run cannot be extended without touching the existing run, raises a ValueError, which
    signals that the autosolver should switch to a different strategy (e.g., table lookup) to
    solve the remaining configuration.
    """
    original_run_length = get_max_run(state.ring)[1]
    ring_size = len(state.ring)

    while True:
        start_index, run_length, dist = get_max_run(state.ring)

        # If the run has been extended, return the new state to allow the autosolver to re-evaluate
        # the configuration and decide on the next steps.
        if run_length > original_run_length:
            return state

        # If the run cannot be extended, raise an error to signal the autosolver to switch
        # strategies.
        if dist is None:
            raise ValueError(
                "Ring is already solved, no moves needed to extend the run."
            )

        # Calculate the end index of the run for convenience.
        run_end = (start_index + run_length - 1) % ring_size

        # Calculate the number of beads that are not part of the protected run, which is important
        # for determining if we can manipulate the ring without touching the run.
        unsolved_length = ring_size - run_length

        # If the distance is large enough, we can directly stage the target bead for a `shift_left3`
        # step.
        if dist > 4:
            target_position = (run_end + dist) % ring_size
            state = _stage_target_for_shift_left3(state, target_position)
            state = shift_left3(state)
            continue

        if dist == 4:
            # Move the end of the run to just before the flip region, so the target bead sits at
            # the fourth flippable position, then apply the shift_left3 macro.
            state = _stage_gap_front(state, run_end)
            state = shift_left3(state)
        elif dist == 3:
            if unsolved_length < 5:
                raise ValueError(
                    "Cannot extend the run without touching it, need a different strategy."
                )
            # Move the end of the run to just before the flip region, so the target bead sits at
            # the third flippable position, then apply the shift_left2 macro.
            state = _stage_gap_front(state, run_end)
            state = shift_left2(state)
        elif dist == 2:
            if unsolved_length < 5:
                raise ValueError(
                    "Cannot extend the run without touching it, need a different strategy."
                )
            # Move the end of the run to just before the flip region, so the target bead sits at
            # the second flippable position, then apply the shift_left1 macro.
            state = _stage_gap_front(state, run_end)
            state = shift_left1(state)
        else:
            raise ValueError(f"Unexpected distance value: {dist}")


def shift_left3(state: RingState) -> RingState:
    """Convert `a b c A` to `A c b a`.

    Applies a single flip to move A 3 positions to the left.
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
    """Convert `a b A c d` to `A c d a b`.
                0 1 2 3 4      2 3 4 0 1

    Moves: L F R F

    Beads:
    (a b A c) d
    After L: -> a (b A c d)
    After F: -> a (d c A b)
    After R: -> (a d c A) b
    After F: -> (A c d a) b

    A moves 2 positions to the left.
    """
    new_ring = state.ring[:]
    for new_pos, old_pos in enumerate([2, 3, 4, 0, 1]):
        new_ring[new_pos] = state.ring[old_pos]
    return RingState(
        ring=new_ring, offset=state.offset, moves=state.moves + ["L", "F", "R", "F"]
    )


def shift_left1(state: RingState) -> RingState:
    """Convert `a A b c d` to `A a d c b`.
                0 1 2 3 4      1 0 4 3 2

    Moves: F shift_left2

    Beads:
    (a A b c) d
    After F: -> (c b A a) d
    After shift_left2: -> (A a d c) b

    A moves 1 position to the left.
    """
    new_ring = state.ring[:]
    for new_pos, old_pos in enumerate([1, 0, 4, 3, 2]):
        new_ring[new_pos] = state.ring[old_pos]
    return RingState(
        ring=new_ring,
        offset=state.offset,
        moves=state.moves + ["F", "L", "F", "R", "F"],
    )
