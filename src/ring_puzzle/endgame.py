"""Endgame table generation and lookup for the ring puzzle.

Once the early-game solver (solver.py) has grown the consecutive run to
ENDGAME_RUN_LENGTH (16 beads), the remaining 4-bead configuration is solved
by table lookup.

There are exactly 4! = 24 distinct endgame configurations (all permutations of
the four remaining bead values). The table is generated once by a bidirectional
BFS over the 4-bead flip zone and stored in endgame.json. At solve time,
`solve_endgame` normalises the live ring into a canonical orientation, looks up
the stored move sequence, and replays it.

Normalisation
-------------
The ring is relabelled so the protected run starts at value 1 (cyclic shift of
labels), then physically rotated so the run occupies positions 0..15. The
4-bead suffix at positions 16..19 forms the lookup key.

Table entries require between 0 and 44 moves. The hardest endgame key is
(18, 20, 17, 19), which requires 44 moves.

Table generation
-----------------
`uv run endgame` generates the table by running 24 forward BFS searches sequentially against a
shared reverse BFS tree rooted at the solved state. The reverse tree is expanded lazily: before
each forward search processes depth f, the shared reverse tree is grown to depth f if needed, so
expansion work from one key is reused by subsequent keys. To guarantee optimality equivalent to a
fully interleaved search, each forward search only counts meetings with reverse nodes at depth ≤ f
(the "pretend" constraint). Solutions are saved to `endgame.json`.

Free-threaded Python is required to use multiple workers for parallel edge generation, thus
requiring Python 3.13+. The default is to use all but one CPU core, but this can be configured
with the N_WORKERS environment variable.
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from itertools import permutations
from pathlib import Path
from time import monotonic
from typing import TextIO

from .util import (
    ENDGAME_RUN_LENGTH,
    FLIP_SIZE,
    MoveList,
    Quartet,
    RingState,
    get_max_run,
    is_solved,
    normalize,
    rotate_shortest,
)

# Cannot use our early-game solver once the protected run is length 16, so we need a separate
# endgame table keyed by the 4 flipping beads.
ENDGAME_SIZE = 4

# In the normalized ring state, the target beads in the flipping zone are always 17, 18, 19, 20.
ENDGAME_VALUES = (17, 18, 19, 20)

# Legal raw moves that can be applied to the ring.
LEGAL_MOVES = ("L", "R", "F")

# Contains best known solutions for each endgame key as concrete move lists.
_TABLE_PATH = Path(__file__).with_name("endgame.json")

# In-memory cache for the generated endgame table to avoid recomputation on repeated runs.
_TABLE_CACHE: dict[Quartet, MoveList] | None = None


def _apply_move_to_ring(ring: list[int], move: str) -> list[int]:
    """Apply one legal move to a ring and return a new ring.

    Works on raw int lists, not RingState, and does not track moves or offsets.
    """
    if move == "L":
        return ring[1:] + ring[:1]
    if move == "R":
        return ring[-1:] + ring[:-1]
    if move == "F":
        new_ring = ring[:]
        new_ring[:FLIP_SIZE] = reversed(new_ring[:FLIP_SIZE])
        return new_ring
    raise ValueError(f"Unknown move: {move}")


def _apply_move_bytes(node: bytes, move: str) -> bytes:
    """Apply one legal move to a ring stored as bytes and return the result as bytes."""
    if move == "L":
        return node[1:] + node[:1]
    if move == "R":
        return node[-1:] + node[:-1]
    if move == "F":
        return bytes(reversed(node[:FLIP_SIZE])) + node[FLIP_SIZE:]
    raise ValueError(f"Unknown move: {move}")


def _apply_move_to_state(state: RingState, move: str) -> RingState:
    """Apply one legal move to a RingState and append the move history."""
    return RingState(
        ring=_apply_move_to_ring(state.ring, move),
        offset=state.offset,
        moves=state.moves + [move],
    )


def _apply_moves_to_ring(ring: list[int], moves: MoveList) -> list[int]:
    """Apply a sequence of legal moves to a ring and return the resulting ring."""
    state = ring[:]
    for move in moves:
        state = _apply_move_to_ring(state, move)
    return state


def _truncate_useless_rotations(start_ring: list[int], moves: MoveList) -> MoveList:
    """Trim a solution once the ring is solved up to rotation."""
    state = start_ring[:]
    for index, move in enumerate(moves, start=1):
        state = _apply_move_to_ring(state, move)
        # If the max run is the whole ring, the ring is solved.
        # Discard any remaining moves, which must be rotations that don't affect the solution.
        if is_solved(state):
            return moves[:index]
    return moves


def _canonical_view(ring: list[int]) -> tuple[list[int], int, int]:
    """Build the canonical view of a ring for endgame keying.

    Returns (anchored, run_length, run_start) where:
    - `anchored` is the normalized ring logically rotated so the protected run starts at index 0.
      Note normalization relabels beads via a cyclic shift so that the protected run starts with
      bead 1.
    - `run_length` is the length of the longest run of consecutive beads in the normalized ring.
    - `run_start` is the index in the normalized ring where the longest run starts.
    """
    normalized = normalize(ring)
    run_start, run_length, _ = get_max_run(normalized)
    anchored = normalized[run_start:] + normalized[:run_start]
    return anchored, run_length, run_start


def canonical_lookup_key(ring: list[int]) -> Quartet:
    """Build the canonical endgame key from a live ring.

    The key is formed from the last 4 beads in the canonical view, as the early-game solver
    can always solve down to a protected run of length 16. When solving the endgame, the ring
    is rotated into a canonical orientation where the protected run starts at index 0 and contains
    beads 1..16 (normalized), then an endgame move sequence is looked up based on the 4 remaining
    beads, which when canonicalized form our endgame key.

    Canonicalization is lookup-only: relabel values so the protected run starts at 1,
    then logically rotate so the run anchor is index 0.
    """
    anchored, run_length, _ = _canonical_view(ring)

    if run_length < ENDGAME_RUN_LENGTH:
        raise ValueError(
            f"Endgame lookup requires a protected run of at least {ENDGAME_RUN_LENGTH}."
        )

    prefix = tuple(anchored[:ENDGAME_RUN_LENGTH])
    expected_prefix = tuple(range(1, ENDGAME_RUN_LENGTH + 1))
    if prefix != expected_prefix:
        raise ValueError(f"Canonical endgame view does not fix positions 1..{ENDGAME_RUN_LENGTH}.")

    suffix = tuple(anchored[ENDGAME_RUN_LENGTH : ENDGAME_RUN_LENGTH + ENDGAME_SIZE])
    if set(suffix) != set(ENDGAME_VALUES):
        raise ValueError("Canonical endgame suffix must contain beads 17..20.")

    return suffix  # type: ignore[return-value]


def _representative_ring(key: Quartet) -> list[int]:
    """Construct the canonical representative ring for a key.

    This is always `1..16` followed by the key.
    """
    return list(range(1, ENDGAME_RUN_LENGTH + 1)) + list(key)


def _key_to_str(key: Quartet) -> str:
    """Convert a key tuple to a string for JSON serialization."""
    return ",".join(str(value) for value in key)


def _str_to_key(raw: str) -> Quartet:
    """Convert a string back to a key tuple."""
    parts = tuple(int(value) for value in raw.split(","))
    if len(parts) != ENDGAME_SIZE:
        raise ValueError(f"Invalid endgame key: {raw}")
    return parts  # type: ignore[return-value]


def _reconstruct_forward_path(
    meeting: bytes,
    forward_prev: dict[bytes, tuple[bytes | None, str | None]],
) -> MoveList:
    """Reconstruct a path from a forward start state to a meeting state.

    `forward_prev` maps each visited node in the forward search tree to its predecessor and the
    move that led to it, except for the root which is the starting node and maps to (None, None).
    """
    moves: MoveList = []
    node = meeting
    while True:
        parent, move = forward_prev[node]
        if parent is None:
            break
        assert move is not None
        moves.append(move)
        node = parent
    moves.reverse()
    return moves


def _reconstruct_reverse_tail(
    meeting: bytes,
    reverse_next: dict[bytes, tuple[bytes | None, str | None]],
) -> MoveList:
    """Reconstruct a path from a meeting state to the solved target state.

    `reverse_next` maps each visited node in the backward search tree to its successor and the
    move to reach it, except for the root which is the target node and maps to (None, None).
    """
    moves: MoveList = []
    node = meeting
    while True:
        nxt, move = reverse_next[node]
        if nxt is None:
            break
        assert move is not None
        moves.append(move)
        node = nxt
    return moves


def generate_endgame_table_interleaved(
    *,
    progress_stream: TextIO = sys.stderr,
    log_state_interval: int = 1_000_000,
    remaining_log_threshold: int = 4,
    n_workers: int | None = None,
) -> dict[Quartet, MoveList]:
    """Generate table by running 24 forward BFS searches sequentially against a shared reverse tree.

    The shared reverse BFS tree is rooted at the solved state and expanded lazily: before each
    forward search processes depth f, the reverse tree is grown to depth f if it has not been
    already. Because the reverse tree is shared across all 24 forward searches, expansion work
    from one key is reused by subsequent keys.

    Optimality guarantee — the "pretend" constraint
    ------------------------------------------------
    A meeting between forward node at depth fd and reverse node at depth rd is only counted when
    rd <= fd. This simulates what a fully interleaved search would have seen: in the original
    interleaved approach the reverse tree had been expanded to exactly fd layers by the time the
    forward tree was at depth fd. The constraint prevents "early" reverse hits (from prior keys'
    expansions) from biasing tie-breaking, guaranteeing results identical to the interleaved BFS.
    """
    ########################
    # INPUT VALIDATION
    ########################

    if log_state_interval < 1:
        raise ValueError("log_state_interval must be >= 1")
    if remaining_log_threshold < 0:
        raise ValueError("remaining_log_threshold must be >= 0")
    if n_workers is None:
        n_workers = max(1, (os.cpu_count() or 1) - 1)
    elif n_workers < 1:
        raise ValueError("n_workers must be >= 1 when provided")

    ########################
    # INITIALIZATION
    ########################

    # Each permutation of ENDGAME_VALUES is a key; we solve them one at a time.
    keys: list[Quartet] = sorted(permutations(ENDGAME_VALUES))  # type: ignore[arg-type]

    # Map each move to its inverse.
    inverse_move = {"L": "R", "R": "L", "F": "F"}

    # Accumulates solved keys and their move sequences.
    solved: dict[Quartet, MoveList] = {}

    # Record the start time for logging purposes.
    started_at = monotonic()

    ##############################
    # HELPER FUNCTIONS (CLOSURES)
    ##############################

    def reverse_edges_for_node(
        node: bytes, src_rank: int
    ) -> list[tuple[int, int, bytes, bytes, str]]:
        """Generate edges in the reverse direction (predecessor, move, node) for a given node.

        There are always 3 legal moves, and we apply the inverse move to get the predecessor in
        the reverse search.
        """
        edges: list[tuple[int, int, bytes, bytes, str]] = []

        for move_rank, move in enumerate(LEGAL_MOVES):
            predecessor = _apply_move_bytes(node, inverse_move[move])
            edges.append((src_rank, move_rank, predecessor, node, move))
        return edges

    def forward_edges_for_node(
        node: bytes, src_rank: int
    ) -> list[tuple[int, int, bytes, bytes, str]]:
        """Generate edges in the forward direction (node, move, successor) for a given node.

        There are always 3 legal moves, and we apply them directly to get the successor in the
        forward search.
        """
        edges: list[tuple[int, int, bytes, bytes, str]] = []
        for move_rank, move in enumerate(LEGAL_MOVES):
            nxt = _apply_move_bytes(node, move)
            edges.append((src_rank, move_rank, node, nxt, move))
        return edges

    #####################################################
    # INITIALIZATION (AFTER HELPER FUNCTION DEFINITIONS)
    #####################################################

    # There is a single target node in the reverse search, which is the representative ring for the
    # key 17, 18, 19, 20 representing the solved state.
    target_ring = bytes(_representative_ring(ENDGAME_VALUES))

    # `reverse_next` maps each visited node in the reverse search tree to its successor and the move
    # to reach it, except for the root which is the target node and maps to (None, None).
    reverse_next: dict[bytes, tuple[bytes | None, str | None]] = {target_ring: (None, None)}

    # `reverse_depth` maps each visited node in the reverse tree to its depth from target_ring.
    # Needed for optimal meeting detection and for enforcing the pretend constraint.
    reverse_depth: dict[bytes, int] = {target_ring: 0}

    # BFS frontier for the reverse search, initialized with the target node.
    reverse_frontier: set[bytes] = {target_ring}

    # How many layers the shared reverse tree has been expanded, and its total state count.
    reverse_max_depth = 0
    backward_states_seen = 1  # target_ring itself

    ####################################################
    # SEQUENTIAL FORWARD SEARCHES WITH SHARED REVERSE
    ####################################################

    with ThreadPoolExecutor(max_workers=n_workers) as executor:

        def expand_reverse_to(target_depth: int) -> None:
            """Grow the shared reverse tree to at least `target_depth` layers."""
            nonlocal reverse_frontier, reverse_max_depth, backward_states_seen

            while reverse_max_depth < target_depth and reverse_frontier:
                sorted_frontier = sorted(reverse_frontier)
                next_reverse_frontier: set[bytes] = set()

                if n_workers > 1 and len(sorted_frontier) > 1:
                    reverse_futures = [
                        executor.submit(reverse_edges_for_node, node, src_rank)
                        for src_rank, node in enumerate(sorted_frontier)
                    ]
                    reverse_edges = [edge for fut in reverse_futures for edge in fut.result()]
                else:
                    reverse_edges = [
                        edge
                        for src_rank, node in enumerate(sorted_frontier)
                        for edge in reverse_edges_for_node(node, src_rank)
                    ]

                # Sort for deterministic processing order, which affects tie-breaking.
                reverse_edges.sort(key=lambda item: (item[0], item[1]))

                for _, _, predecessor, node, move in reverse_edges:
                    if predecessor not in reverse_next:
                        reverse_next[predecessor] = (node, move)
                        reverse_depth[predecessor] = reverse_depth[node] + 1
                        next_reverse_frontier.add(predecessor)
                        backward_states_seen += 1

                reverse_frontier = next_reverse_frontier
                reverse_max_depth += 1

        for key in keys:
            start = bytes(_representative_ring(key))

            # If start is the target itself (forward depth 0 meets reverse depth 0), solved
            # trivially.
            if start == target_ring:
                solved[key] = []
                continue

            # `prev_map` records each visited forward node's predecessor and the move leading to it.
            # The root maps to (None, None).
            prev_map: dict[bytes, tuple[bytes | None, str | None]] = {start: (None, None)}
            # `depth_map` records each visited forward node's BFS depth from start.
            depth_map: dict[bytes, int] = {start: 0}
            frontier: set[bytes] = {start}
            forward_states_seen = 1

            # Track combined states seen at the last log point for threshold triggering.
            last_logged_seen: list[int] = [0]

            def maybe_log(forward_depth: int, *, force: bool = False) -> None:
                seen_now = forward_states_seen + backward_states_seen
                if force or (seen_now - last_logged_seen[0]) >= log_state_interval:
                    elapsed_s = monotonic() - started_at
                    remaining = [k for k in keys if k not in solved]
                    remaining_suffix = ""
                    if len(remaining) < remaining_log_threshold:
                        remaining_suffix = f" remaining={remaining}"
                    print(
                        (
                            f"key={key} forward_depth={forward_depth} "
                            f"elapsed_s={elapsed_s:.1f} "
                            f"forward_states_seen={forward_states_seen} "
                            f"backward_states_seen={backward_states_seen} "
                            f"solved_start_states={len(solved)}/{len(keys)}"
                            f"{remaining_suffix}"
                        ),
                        file=progress_stream,
                        flush=True,
                    )
                    last_logged_seen[0] = seen_now

            forward_depth = 0
            while True:
                forward_depth += 1

                # Ensure the reverse tree covers at least this depth before checking meetings,
                # mirroring the original interleaved approach where reverse expanded before forward.
                expand_reverse_to(forward_depth)

                sorted_frontier = sorted(frontier)
                next_frontier: set[bytes] = set()

                # Best meeting found at this layer: pick minimum forward_depth + reverse_depth.
                best_meeting: bytes | None = None
                best_meeting_cost = float("inf")

                if n_workers > 1 and len(sorted_frontier) > 1:
                    forward_futures = [
                        executor.submit(forward_edges_for_node, node, src_rank)
                        for src_rank, node in enumerate(sorted_frontier)
                    ]
                    forward_edges = [edge for fut in forward_futures for edge in fut.result()]
                else:
                    forward_edges = [
                        edge
                        for src_rank, node in enumerate(sorted_frontier)
                        for edge in forward_edges_for_node(node, src_rank)
                    ]

                # Sort for deterministic processing order, which affects tie-breaking.
                forward_edges.sort(key=lambda item: (item[0], item[1]))

                for _, _, node, nxt, move in forward_edges:
                    if nxt not in prev_map:
                        prev_map[nxt] = (node, move)
                        depth_map[nxt] = forward_depth
                        next_frontier.add(nxt)
                        forward_states_seen += 1

                    # Pretend constraint: only count reverse nodes at depth <= forward_depth.
                    # This reproduces the meeting detection of the original interleaved approach,
                    # where the reverse tree had at most forward_depth layers at this point.
                    if nxt in reverse_next and reverse_depth[nxt] <= forward_depth:
                        forward_d = depth_map[nxt]
                        reverse_d = reverse_depth[nxt]
                        total_cost = forward_d + reverse_d
                        if total_cost < best_meeting_cost:
                            best_meeting_cost = total_cost
                            best_meeting = nxt

                # Always emit at least one line per depth.
                maybe_log(forward_depth)

                if best_meeting is not None:
                    prefix = _reconstruct_forward_path(best_meeting, prev_map)
                    suffix = _reconstruct_reverse_tail(best_meeting, reverse_next)
                    solved[key] = _truncate_useless_rotations(
                        _representative_ring(key), prefix + suffix
                    )
                    maybe_log(forward_depth, force=True)
                    break

                frontier = next_frontier

                # If the frontier is empty and no meeting was found, the search space is exhausted,
                # which should never happen in a fully connected puzzle graph.
                if not frontier:
                    raise RuntimeError(
                        f"Forward search stalled for key {key} at depth {forward_depth}"
                    )

    return solved


def generate_endgame_table() -> dict[Quartet, MoveList]:
    """Generate the endgame table using optimal interleaved bidirectional BFS.

    Returns the shortest solution for each endgame key.
    """
    n_workers_str = os.getenv("N_WORKERS", default=None)
    if n_workers_str is not None:
        n_workers = int(n_workers_str)
    else:
        n_workers = (os.cpu_count() or 1) - 1

    # If n_workers (supplied or computed) is less than 1, default to 1 to avoid invalid thread
    # pool size.
    n_workers = max(n_workers, 1)

    return generate_endgame_table_interleaved(n_workers=n_workers)


def validate_endgame_table(table: dict[Quartet, MoveList]) -> None:
    """Validate that all solutions in the table actually solve their keys.

    This checks validity (solutions work) but not optimality (they may not be shortest).
    """
    for key, moves in table.items():
        start_ring = _representative_ring(key)
        result_ring = _apply_moves_to_ring(start_ring, moves)
        _, run_length, _ = get_max_run(result_ring)
        if run_length != len(result_ring):
            raise ValueError(
                f"Invalid solution for key {key}: moves {moves} result in run_length {run_length}, "
                f"not {len(result_ring)}"
            )


def load_endgame_table(validate: bool = True) -> dict[Quartet, MoveList]:
    """Load the precomputed endgame table from JSON.

    If the JSON is missing, generate it on the fly so solver usage stays functional.
    """
    global _TABLE_CACHE

    if _TABLE_CACHE is not None:
        return _TABLE_CACHE

    if _TABLE_PATH.exists():
        with _TABLE_PATH.open("r", encoding="utf-8") as f:
            raw: dict[str, MoveList] = json.load(f)
        table = {_str_to_key(key): moves for key, moves in raw.items()}
    else:
        table = generate_endgame_table()

    if validate:
        validate_endgame_table(table)

    _TABLE_CACHE = table
    return table


def write_endgame_table(path: Path | None = None) -> dict[Quartet, MoveList]:
    """Generate and write the hybrid canonical endgame table as JSON."""
    target_path = _TABLE_PATH if path is None else path
    table = generate_endgame_table()
    serializable = {_key_to_str(key): moves for key, moves in sorted(table.items())}

    with target_path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, sort_keys=True)
        f.write("\n")

    return table


def main() -> int:
    """CLI entrypoint for manually running long endgame table generation."""
    table = write_endgame_table()
    print(f"Wrote endgame table to {_TABLE_PATH} with {len(table)} entries.")
    print(f"Max path length: {max(len(path) for path in table.values())}")
    print(f"Min path length: {min(len(path) for path in table.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def lookup_endgame_moves(ring: list[int]) -> MoveList:
    """Lookup canonical endgame moves for a live ring.

    Validates that the returned moves actually solve the ring without checking
    for optimality (which would require expensive table regeneration).
    """
    key = canonical_lookup_key(ring)
    table = load_endgame_table(validate=True)
    moves = table[key][:]

    # Quick validation: apply moves and check the ring is solved
    test_ring = ring[:]
    for move in moves:
        test_ring = _apply_move_to_ring(test_ring, move)

    # Verify the result is solved (all beads in consecutive order, possibly rotated)
    _, run_length, _ = get_max_run(test_ring)
    if run_length != len(test_ring):
        raise RuntimeError(
            f"Endgame table lookup returned invalid moves for key {key}: "
            f"moves {moves} result in run_length {run_length}, not {len(test_ring)}"
        )

    return moves


def solve_endgame(state: RingState) -> RingState:
    """Solve the final endgame phase using canonical lookup moves.

    The ring is first rotated so the protected run anchor is physically at index 0.
    This aligns the live frame with the canonical representative frame used by lookup.
    """
    run_start, run_length, _ = get_max_run(state.ring)
    if run_length < ENDGAME_RUN_LENGTH:
        raise ValueError(
            f"Endgame solver requires a protected run of at least {ENDGAME_RUN_LENGTH}."
        )

    state = rotate_shortest(state, run_start)

    moves = lookup_endgame_moves(state.ring)
    for move in moves:
        state = _apply_move_to_state(state, move)

    final_length = get_max_run(state.ring)[1]
    if final_length != len(state.ring):
        raise RuntimeError("Endgame move translation failed to solve the ring up to rotation.")

    return state
