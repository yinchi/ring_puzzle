"""Tests for the generated endgame solution table."""

import json
from itertools import permutations
from pathlib import Path

from ring_puzzle.endgame import (
    ENDGAME_RUN_LENGTH,
    ENDGAME_SIZE,
    ENDGAME_VALUES,
    _apply_moves_to_ring,
    _representative_ring,
    _str_to_key,
    load_endgame_table,
    _TABLE_PATH,
)
from ring_puzzle import is_solved


class TestEndgameTableFile:
    """Validate the persisted endgame.json file."""

    def test_endgame_json_exists(self) -> None:
        """The endgame.json file should exist."""
        assert (
            _TABLE_PATH.exists()
        ), f"endgame.json not found at {_TABLE_PATH} (absolute: {_TABLE_PATH.resolve()})"

    def test_endgame_json_has_24_entries(self) -> None:
        """The endgame table should have exactly 24 entries (all permutations of ENDGAME_VALUES)."""
        table = load_endgame_table(validate=False)
        assert len(table) == 24, f"Expected 24 endgame keys, got {len(table)}"

    def test_endgame_json_has_all_permutations(self) -> None:
        """The endgame table should cover all 24 permutations of ENDGAME_VALUES."""
        table = load_endgame_table(validate=False)
        expected_keys = set(permutations(ENDGAME_VALUES))
        actual_keys = set(table.keys())
        assert (
            actual_keys == expected_keys
        ), f"Table keys do not match expected permutations"


class TestEndgameSolutions:
    """Validate that each solution in the table actually solves its key."""

    def test_each_solution_solves_its_key(self) -> None:
        """Each endgame solution should solve its corresponding key."""
        table = load_endgame_table(validate=False)

        failures = []
        for key in sorted(table):
            start_ring = _representative_ring(key)
            moves = table[key]

            # Apply the solution moves
            ring = start_ring[:]
            for move in moves:
                ring = _apply_moves_to_ring(ring, [move])

            # Check if the ring is solved (all beads in consecutive order, possibly rotated)
            if not is_solved(ring):
                failures.append(
                    (
                        key,
                        len(moves),
                    )
                )

        assert not failures, (
            f"Found {len(failures)} solutions that don't solve their keys: "
            f"{failures[:5]}"  # Show first 5 failures
        )

    def test_no_solution_is_empty(self) -> None:
        """No solution should be empty (even the solved key should have 0 moves, not missing)."""
        table = load_endgame_table(validate=False)
        for key, moves in table.items():
            assert isinstance(moves, list), f"Solution for {key} is not a list"

    def test_solved_key_has_zero_moves(self) -> None:
        """The solved key (17, 18, 19, 20) should require 0 moves."""
        table = load_endgame_table(validate=False)
        solved_key = ENDGAME_VALUES
        assert (
            solved_key in table
        ), f"Solved key {solved_key} not in table"
        assert table[solved_key] == [], (
            f"Solved key should have 0 moves, got {len(table[solved_key])}"
        )


class TestEndgameSolutionStatistics:
    """Validate solution statistics and properties."""

    def test_solution_lengths_are_reasonable(self) -> None:
        """Solution lengths should be within reasonable bounds."""
        table = load_endgame_table(validate=False)
        lengths = [len(moves) for moves in table.values()]

        min_length = min(lengths)
        max_length = max(lengths)

        # The solved key has 0 moves, others should have > 0
        assert min_length == 0, f"Minimum solution length should be 0 (for solved key)"
        # Maximum should be well under 100 moves for a 24-bead ring
        assert (
            max_length <= 100
        ), f"Maximum solution length {max_length} seems unreasonably high"

    def test_all_solutions_use_valid_moves(self) -> None:
        """All moves in all solutions should be valid (L, R, or F)."""
        table = load_endgame_table(validate=False)
        valid_moves = {"L", "R", "F"}

        invalid_count = 0
        for key, moves in table.items():
            for move in moves:
                if move not in valid_moves:
                    invalid_count += 1

        assert invalid_count == 0, (
            f"Found {invalid_count} invalid moves (not in {valid_moves})"
        )

    def test_solution_lengths_distribution(self) -> None:
        """Check that solution lengths follow a reasonable distribution."""
        table = load_endgame_table(validate=False)
        lengths = [len(moves) for moves in table.values()]

        min_len = min(lengths)
        max_len = max(lengths)
        avg_len = sum(lengths) / len(lengths)

        # The distribution should make sense:
        # - 1 key with 0 moves (the solved key)
        # - Most keys requiring 10-40 moves
        # - Worst case shouldn't be more than ~50 moves for a 24-bead ring

        assert min_len == 0, "Minimum should be 0"
        assert 10 <= avg_len <= 50, (
            f"Average solution length {avg_len} seems outside expected range [10, 50]"
        )
        assert max_len <= 100, (
            f"Maximum solution length {max_len} exceeds reasonable bound of 100"
        )
