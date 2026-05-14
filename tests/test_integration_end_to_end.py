"""End-to-end integration tests for ring puzzle solver.

Tests the full solve pipeline from scrambled state to solved, including:
- Two-phase solving (constructive + endgame)
- Rotation cancellation and optimization
- Move sequence validity and replayability
"""

import random
import time

import pytest

from ring_puzzle import is_solved
from ring_puzzle.solver import cancel_opposite_rotations, solve_from_state, solve_moves
from ring_puzzle.util import RingState


def apply_moves_to_ring(ring: list[int], moves: list[str]) -> list[int]:
    """Apply a sequence of moves to a ring and return the result."""
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


class TestRotationCancellation:
    """Tests for the rotation cancellation optimization."""

    def test_cancel_opposite_rotations_lr_pair(self) -> None:
        moves = ["L", "R", "F"]
        assert cancel_opposite_rotations(moves) == ["F"]

    def test_cancel_opposite_rotations_rl_pair(self) -> None:
        moves = ["R", "L", "F"]
        assert cancel_opposite_rotations(moves) == ["F"]

    def test_cancel_opposite_rotations_ff_pair(self) -> None:
        moves = ["F", "F", "L"]
        assert cancel_opposite_rotations(moves) == ["L"]

    def test_cancel_nested(self) -> None:
        moves = ["F", "L", "L", "R", "R", "F"]
        # Three nested pairs all cancel out, leaving an empty sequence
        assert cancel_opposite_rotations(moves) == []

    def test_cancel_opposite_rotations_empty(self) -> None:
        assert cancel_opposite_rotations([]) == []

    def test_cancel_inner_pair(self) -> None:
        moves = ["L", "L", "R", "F"]
        # Inner pair cancels out, leaving ["L", "F"] which cannot be further reduced
        assert cancel_opposite_rotations(moves) == ["L", "F"]


class TestRotationCancellationReplayability:
    """Test that reduced move sequences after cancellation still solve the ring correctly."""

    @pytest.mark.parametrize(
        "start,moves,expected_cancelled",
        [
            (
                [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 17, 19, 20],
                ["L", "R", "F", "F"],
                [],
            ),
            (
                [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 20, 19, 18, 17],
                ["R", "L", "L", "L"],
                ["L", "L"],
            ),
        ],
    )
    def test_cancelled_moves_still_apply_correctly(
        self, start: list[int], moves: list[str], expected_cancelled: list[str]
    ) -> None:
        result_original = apply_moves_to_ring(start, moves)
        cancelled = cancel_opposite_rotations(moves)
        assert cancelled == expected_cancelled
        result_cancelled = apply_moves_to_ring(start, cancelled)
        assert result_original == result_cancelled


class TestSolverStateTracking:
    """Tests that solver properly tracks state through phases."""

    def test_ring_state_preserves_moves_history(self) -> None:
        initial = RingState(ring=list(range(1, 21)))
        after_one = RingState(ring=initial.ring, moves=initial.moves + ["L"])
        after_two = RingState(ring=after_one.ring, moves=after_one.moves + ["R"])
        assert after_two.moves == ["L", "R"]

    def test_solved_state_is_recognized(self) -> None:
        solved = list(range(1, 21))
        assert is_solved(solved)

    def test_rotation_of_solved_state_is_recognized(self) -> None:
        rotated = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        assert is_solved(rotated)


class TestFullSolve:
    """Tests for complete end-to-end solve pipeline."""

    @pytest.mark.parametrize(
        "scrambled",
        [
            [1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 6, 14, 15, 16, 17, 18, 19, 20, 7, 8],
            [1, 2, 3, 4, 5, 8, 9, 10, 6, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 7],
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 17, 19, 20],
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 20, 19, 18, 17],
            [20, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 17, 19],
            [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
        ],
    )
    def test_solve_returns_valid_replayable_moves(self, scrambled: list[int]) -> None:
        moves = solve_moves(scrambled)
        result = apply_moves_to_ring(scrambled, moves)
        solved = list(range(1, 21))
        assert is_solved(result)
        assert sorted(result) == sorted(solved)

    def test_solve_from_state_tracks_moves_correctly(self) -> None:
        scrambled = [1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 6, 14, 15, 16, 17, 18, 19, 20, 7, 8]
        initial_state = RingState(ring=scrambled)
        result_state = solve_from_state(initial_state)
        replayed = apply_moves_to_ring(scrambled, result_state.moves)
        assert replayed == result_state.ring
        assert is_solved(result_state.ring)

    def test_already_solved_state_returns_empty_moves(self) -> None:
        solved = list(range(1, 21))
        assert solve_moves(solved) == []

    def test_rotation_of_solved_state_requires_only_rotations(self) -> None:
        rotated = [18, 19, 20] + list(range(1, 18))
        moves = solve_moves(rotated)
        assert all(move in ["L", "R"] for move in moves)
        result = apply_moves_to_ring(rotated, moves)
        assert is_solved(result)


class TestWorstCasePerformance:
    """Tests for worst-case scenarios to ensure performance remains acceptable."""

    @pytest.mark.parametrize(
        "scrambled,description",
        [
            (
                [1, 2, 3, 4, 5, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6],
                "Beads 1-5 correct, rest reversed (user-specified worst case)",
            ),
            (
                [1, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2],
                "Only bead 1 correct, everything else reversed",
            ),
            (
                [1, 2, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3],
                "Beads 1-2 correct, everything else reversed",
            ),
            (
                [1, 11, 2, 12, 3, 13, 4, 14, 5, 15, 6, 16, 7, 17, 8, 18, 9, 19, 10, 20],
                "Interleaved halves",
            ),
        ],
    )
    def test_worst_case_solves_quickly(self, scrambled: list[int], description: str) -> None:
        start = time.time()
        moves = solve_moves(scrambled)
        elapsed = time.time() - start

        result = apply_moves_to_ring(scrambled, moves)
        assert is_solved(result), f"{description}: Solution failed"
        assert elapsed < 0.1, f"{description}: Took {elapsed:.4f}s (expected < 0.1s)"

    def test_seeded_random_generated_case_solves(self) -> None:
        """Use a deterministic random shuffle to cover a non-handpicked scramble."""
        rng = random.Random(20260511)
        scrambled = list(range(1, 21))
        while True:
            rng.shuffle(scrambled)
            if scrambled != list(range(1, 21)):
                break

        start = time.time()
        moves = solve_moves(scrambled)
        elapsed = time.time() - start

        result = apply_moves_to_ring(scrambled, moves)

        assert is_solved(result), "Seeded random case did not solve the ring"
        assert elapsed < 0.1, f"Seeded random case took {elapsed:.4f}s (expected < 0.1s)"
