import pytest

from ring_puzzle.solver import (
    extend_head,
    extend_tail,
    shift_left1,
    shift_left2,
    shift_left3,
    shift_right1,
    shift_right2,
    shift_right3,
)
from ring_puzzle.util import (
    RingState,
    get_max_run,
    normalize,
    rotate_left,
    rotate_right,
    rotate_shortest,
)


def apply_moves(ring: list[int], moves: list[str]) -> list[int]:
    """Helper function to apply a sequence of moves to a ring state, for testing purposes.
    
    Args:
        ring: The initial state of the ring.
        moves: A list of moves to apply to the ring.

    Returns:
        The state of the ring after applying the moves.
    """
    state = ring[:]
    for move in moves:
        if move == "L":
            state = state[1:] + state[:1]
        elif move == "R":
            state = state[-1:] + state[:-1]
        elif move == "F":
            state[:4] = reversed(state[:4])
        else:
            raise ValueError(f"Unknown move: {move}")
    return state


def test_normalize_maps_rotated_solution_to_canonical_order() -> None:
    """Test that the normalize function correctly identifies a rotated solution as equivalent
    to the canonical solved state."""
    rotated = list(range(8, 21)) + list(range(1, 8))

    assert normalize(rotated) == list(range(1, 21))


def test_get_max_run_handles_cyclic_solution() -> None:
    """Test that get_max_run correctly identifies the longest run in a ring that is a rotated
    version of the solved state.
    
    In this case, the longest run should be the entire ring, even though it wraps around the end.
    """
    rotated = list(range(8, 21)) + list(range(1, 8))

    assert get_max_run(rotated) == (0, 20, None)


def test_get_max_run_reports_expected_distance_for_partial_run() -> None:
    """Test that get_max_run correctly identifies the longest run and the distance to the
    next element.
    
    Here the longest run is [1, 2] (position 0, length 2), and the next element (3) has distance 3
    from (2).
    """
    ring = [1, 2, 4, 5, 3]

    assert get_max_run(ring) == (0, 2, 3)


def test_rotate_left_and_right_are_inverses() -> None:
    """Test that rotating left and then right (or vice versa) restores the original ring state,
    and that the moves are recorded correctly."""
    original = RingState(ring=[1, 2, 3, 4, 5])

    rotated = rotate_left(original, 2)
    restored = rotate_right(rotated, 2)

    assert restored.ring == original.ring
    assert restored.moves == ["L", "L", "R", "R"]


def test_rotate_shortest_prefers_right_when_shorter() -> None:
    """Test that rotate_shortest chooses the right rotation when it results in fewer moves than
    the left rotation."""
    state = RingState(ring=[1, 2, 3, 4, 5])

    rotated = rotate_shortest(state, 4)

    assert rotated.ring == [5, 1, 2, 3, 4]
    assert rotated.moves == ["R"]


@pytest.mark.parametrize(
    ("macro", "ring", "expected", "moves"),
    [
        (shift_left3, [1, 2, 3, 4, 5], [4, 3, 2, 1, 5], ["F"]),
        (shift_left2, [1, 2, 3, 4, 5], [3, 4, 5, 1, 2], ["L", "F", "R", "F"]),
        (shift_left1, [1, 2, 3, 4, 5], [2, 1, 5, 4, 3], ["F", "L", "F", "R", "F"]),
    ],
)
def test_shift_left_macros_match_documented_permutations(
    macro, ring: list[int], expected: list[int], moves: list[str]
) -> None:
    """Test that the shift_left macros produce the expected permutations and record the
    correct moves."""
    result = macro(RingState(ring=ring, offset=7, moves=["L"]))

    assert result.ring == expected
    assert result.offset == 7
    assert result.moves == ["L", *moves]
    assert apply_moves(ring, moves) == expected


@pytest.mark.parametrize(
    "ring",
    [
        [1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 6, 14, 15, 16, 17, 18, 19, 20, 7, 8],
        [1, 2, 3, 4, 5, 8, 9, 10, 6, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 7],
        [1, 2, 3, 4, 7, 8, 9, 5, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 6],
    ],
)
def test_extend_max_run_increases_longest_run_and_records_replayable_moves(
    ring: list[int],
) -> None:
    """Test that extend_max_run increases the length of the longest run and records moves that can
    be applied to the original ring to achieve the new state."""
    before_start, before_length, _ = get_max_run(ring)

    result = extend_tail(RingState(ring=ring))

    after_start, after_length, _ = get_max_run(result.ring)
    assert after_length > before_length
    assert result.ring == apply_moves(ring, result.moves)
    assert (before_start, after_start) is not None


def test_extend_max_run_raises_on_solved_ring() -> None:
    """Test that extend_max_run raises a ValueError when the input ring is already in a solved
    state, since no moves are needed."""
    solved = RingState(ring=list(range(1, 21)))

    with pytest.raises(ValueError, match="already solved"):
        extend_tail(solved)


def test_extend_max_run_raises_when_endgame_strategy_is_needed() -> None:
    """Test that extend_max_run raises a ValueError when the input ring requires a different
    strategy, indicating that the endgame strategy is needed."""
    ring = list(range(1, 17)) + [18, 17, 19, 20]

    with pytest.raises(ValueError, match="different strategy"):
        extend_tail(RingState(ring=ring))


@pytest.mark.parametrize(
    ("macro", "ring", "expected", "moves"),
    [
        (shift_right3, [1, 2, 3, 4, 5], [4, 3, 2, 1, 5], ["F"]),
        (shift_right2, [1, 2, 3, 4, 5], [4, 5, 1, 2, 3], ["R", "F", "L", "F"]),
        (shift_right1, [1, 2, 3, 4, 5], [1, 5, 4, 3, 2], ["F", "R", "F", "L", "F"]),
    ],
)
def test_shift_right_macros_match_documented_permutations(
    macro, ring: list[int], expected: list[int], moves: list[str]
) -> None:
    """Test that the shift_right macros produce the expected permutations and record the
    correct moves."""
    result = macro(RingState(ring=ring, offset=7, moves=["L"]))

    assert result.ring == expected
    assert result.offset == 7
    assert result.moves == ["L", *moves]
    assert apply_moves(ring, moves) == expected


@pytest.mark.parametrize(
    "ring",
    [
        # pred at dist_head=2 (shift_right2 path)
        [10, 20, 11, 12, 13, 14, 15, 16, 17, 18, 19, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        # pred at dist_head=3 (shift_right3 path)
        [10, 20, 19, 11, 12, 13, 14, 15, 16, 17, 18, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        # pred at dist_head >= 4 (repeated shift_right4 path)
        [10, 20, 19, 18, 17, 11, 12, 13, 14, 15, 16, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    ],
)
def test_extend_head_increases_longest_run_and_records_replayable_moves(
    ring: list[int],
) -> None:
    """Test that extend_head increases the length of the longest run by one (at the head)
    and records moves that can be replayed on the original ring."""
    _, before_length, _ = get_max_run(ring)

    result = extend_head(RingState(ring=ring))

    _, after_length, _ = get_max_run(result.ring)
    assert after_length > before_length
    assert result.ring == apply_moves(ring, result.moves)


def test_extend_head_raises_on_solved_ring() -> None:
    """Test that extend_head raises a ValueError when the ring is already solved."""
    solved = RingState(ring=list(range(1, 21)))

    with pytest.raises(ValueError, match="already solved"):
        extend_head(solved)