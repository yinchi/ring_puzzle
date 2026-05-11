from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from heapq import heappop, heappush
from itertools import permutations
from pathlib import Path
from threading import Lock
from time import monotonic

from .solver import (
    ENDGAME_RUN_LENGTH,
    RingState,
    get_max_run,
    normalize,
    rotate_shortest,
)

ENDGAME_SIZE = 4
ENDGAME_VALUES = (17, 18, 19, 20)
SOLVED_ENDGAME_KEY = ENDGAME_VALUES
MOVE_ORDER = ("L", "R", "F")
CYCLE_SETUP_DEPTH = 6

_TABLE_PATH = Path(__file__).with_name("endgame.json")
_MACRO_REPORT_PATH = Path(__file__).with_name("endgame_macro_report.json")
_TABLE_CACHE: dict[tuple[int, int, int, int], list[str]] | None = None


def _apply_move_to_ring(ring: list[int], move: str) -> list[int]:
    """Apply one legal move to a ring and return a new ring."""
    if move == "L":
        return ring[1:] + ring[:1]
    if move == "R":
        return ring[-1:] + ring[:-1]
    if move == "F":
        new_ring = ring[:]
        new_ring[:4] = reversed(new_ring[:4])
        return new_ring
    raise ValueError(f"Unknown move: {move}")


def _apply_move_to_state(state: RingState, move: str) -> RingState:
    """Apply one legal move to a RingState and append the move history."""
    return RingState(
        ring=_apply_move_to_ring(state.ring, move),
        offset=state.offset,
        moves=state.moves + [move],
    )


def _apply_moves_to_ring(ring: list[int], moves: list[str]) -> list[int]:
    """Apply a sequence of legal moves to a ring and return the resulting ring."""
    state = ring[:]
    for move in moves:
        state = _apply_move_to_ring(state, move)
    return state


def _truncate_useless_rotations(
    start_ring: list[int], moves: list[str]
) -> list[str]:
    """Trim a solution once the ring is solved up to rotation."""
    state = start_ring[:]
    for index, move in enumerate(moves, start=1):
        state = _apply_move_to_ring(state, move)
        if get_max_run(state)[1] == len(state):
            return moves[:index]
    return moves


def _canonical_view(ring: list[int]) -> tuple[list[int], int, int]:
    """Return canonical normalized+anchored ring, run length, and run anchor in live indices."""
    normalized = normalize(ring)
    run_start, run_length, _ = get_max_run(normalized)
    anchored = normalized[run_start:] + normalized[:run_start]
    return anchored, run_length, run_start


def canonical_lookup_key(ring: list[int]) -> tuple[int, int, int, int]:
    """Build the canonical endgame key from a live ring.

    Canonicalization is lookup-only: relabel values so the protected run starts at 1,
    then logically rotate so the run anchor is index 0.
    """
    anchored, run_length, _ = _canonical_view(ring)

    if run_length < ENDGAME_RUN_LENGTH:
        raise ValueError("Endgame lookup requires a protected run of at least 16.")

    prefix = tuple(anchored[:ENDGAME_RUN_LENGTH])
    expected_prefix = tuple(range(1, ENDGAME_RUN_LENGTH + 1))
    if prefix != expected_prefix:
        raise ValueError("Canonical endgame view does not fix positions 1..16.")

    suffix = tuple(anchored[ENDGAME_RUN_LENGTH : ENDGAME_RUN_LENGTH + ENDGAME_SIZE])
    if set(suffix) != set(ENDGAME_VALUES):
        raise ValueError("Canonical endgame suffix must contain beads 17..20.")

    return suffix  # type: ignore[return-value]


def _representative_ring(key: tuple[int, int, int, int]) -> list[int]:
    """Construct the canonical representative ring for a key."""
    return list(range(1, ENDGAME_RUN_LENGTH + 1)) + list(key)


def _inverse_moves(moves: list[str]) -> list[str]:
    """Return inverse move sequence for legal move list."""
    inverse = {"L": "R", "R": "L", "F": "F"}
    return [inverse[move] for move in reversed(moves)]


def _moves_to_notation(moves: list[str]) -> str:
    """Convert move list to compact notation like L2 R3 F.
    
    Note: F is never repeated consecutively (F² = identity), so we omit the count.
    """
    if not moves:
        return "ε"
    result = []
    prev_move = None
    count = 0
    for move in moves:
        if move != prev_move:
            if prev_move is not None:
                if prev_move == "F":
                    result.append("F")
                else:
                    result.append(f"{prev_move}{count}")
            prev_move = move
            count = 1
        else:
            count += 1
    if prev_move is not None:
        if prev_move == "F":
            result.append("F")
        else:
            result.append(f"{prev_move}{count}")
    return " ".join(result)


def _decompose_macro_to_expansion(macro: list[str]) -> str:
    """Decompose a macro into beta-sigma-beta' form returning full symbolic representation."""
    sigma2 = _sigma2_moves()
    sigma3 = _sigma3_moves()
    sigma3_inv = _inverse_moves(sigma3)

    sigmas = [
        (sigma2, "S2"),
        (sigma3, "S3"),
        (sigma3_inv, "S3'"),
    ]

    for sigma, sigma_name in sigmas:
        sigma_len = len(sigma)
        for i in range(len(macro) - sigma_len + 1):
            if macro[i : i + sigma_len] == sigma:
                beta_left = macro[:i]
                beta_right = macro[i + sigma_len :]

                expected_right = _inverse_moves(beta_left)
                if beta_right == expected_right:
                    left_notation = _moves_to_notation(beta_left)
                    beta_inv = _inverse_moves(beta_left)
                    right_notation = _moves_to_notation(beta_inv)
                    
                    # Format: "beta sigma beta'" or just "sigma" if beta is empty
                    if left_notation == "ε":
                        return sigma_name
                    else:
                        return f"{left_notation} {sigma_name} {right_notation}".strip()

    return "UNKNOWN"



def _generate_setup_sequences(max_depth: int) -> list[list[str]]:
    """Generate setup sequences β up to max depth for beta-sigma-beta^-1 macros."""
    if max_depth < 0:
        raise ValueError("max_depth must be >= 0")

    inverse = {"L": "R", "R": "L", "F": "F"}
    sequences: list[tuple[str, ...]] = [()]
    frontier: list[tuple[str, ...]] = [()]

    for _ in range(max_depth):
        next_frontier: list[tuple[str, ...]] = []
        for seq in frontier:
            for move in MOVE_ORDER:
                # Skip immediate canceling pairs like LR, RL, and FF.
                if seq and inverse[move] == seq[-1]:
                    continue
                candidate = seq + (move,)
                sequences.append(candidate)
                next_frontier.append(candidate)
        frontier = next_frontier

    return [list(seq) for seq in sequences]


def _minimize_macro_catalog(catalog: list[list[str]]) -> list[list[str]]:
    """Keep one shortest deterministic macro per directed 24-key transition."""
    best_by_edge: dict[
        tuple[tuple[int, int, int, int], tuple[int, int, int, int]], list[str]
    ] = {}
    for macro in catalog:
        for key in sorted(permutations(ENDGAME_VALUES)):
            representative = _representative_ring(key)
            moved = _apply_moves_to_ring(representative, macro)
            try:
                next_key = canonical_lookup_key(moved)
            except ValueError:
                continue
            edge = (key, next_key)
            incumbent = best_by_edge.get(edge)
            if incumbent is None or len(macro) < len(incumbent) or (
                len(macro) == len(incumbent) and tuple(macro) < tuple(incumbent)
            ):
                best_by_edge[edge] = macro

    minimized = sorted(
        {tuple(macro): macro for macro in best_by_edge.values()}.values(),
        key=lambda m: (len(m), tuple(m)),
    )
    return minimized


def _sigma2_moves() -> list[str]:
    """2-cycle macro from notes: (T R^-1)^17 -> (F L)^17 in our move symbols."""
    return ["F", "L"] * 17


def _sigma3_moves() -> list[str]:
    """3-cycle macro from notes: [R^-3, T]^2 translated to L/R/F moves."""
    return ["L", "L", "L", "F", "R", "R", "R", "F"] * 2


def _build_cycle_macro_catalog(
    ring_size: int,
    setup_depth: int = CYCLE_SETUP_DEPTH,
) -> list[list[str]]:
    """Build conjugated cycle macros by rotating around the ring.

    Each macro is a concrete legal move list that can be replayed directly on a ring.
    """
    sigma2 = _sigma2_moves()
    sigma3 = _sigma3_moves()
    sigma3_inv = _inverse_moves(sigma3)
    setup_sequences = _generate_setup_sequences(setup_depth)

    catalog: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    for shift in range(ring_size):
        rotate = ["L"] * shift
        unrotate = ["R"] * shift
        for core in (sigma2, sigma3, sigma3_inv):
            candidate = rotate + core + unrotate
            key = tuple(candidate)
            if key in seen:
                continue
            seen.add(key)
            catalog.append(candidate)

    for beta in setup_sequences:
        beta_inv = _inverse_moves(beta)
        for core in (sigma2, sigma3, sigma3_inv):
            candidate = beta + core + beta_inv
            key = tuple(candidate)
            if key in seen:
                continue
            seen.add(key)
            catalog.append(candidate)

    return _minimize_macro_catalog(catalog)


def _macro_neighbors_by_key(
    macros: list[list[str]],
) -> dict[tuple[int, int, int, int], list[tuple[tuple[int, int, int, int], int]]]:
    """Build key-graph neighbors as (next_key, macro_index)."""
    keys = sorted(permutations(ENDGAME_VALUES))
    neighbors: dict[tuple[int, int, int, int], list[tuple[tuple[int, int, int, int], int]]] = {
        key: [] for key in keys
    }

    for key in keys:
        representative = _representative_ring(key)
        candidate_by_next: dict[tuple[int, int, int, int], int] = {}
        for index, macro in enumerate(macros):
            moved = _apply_moves_to_ring(representative, macro)
            try:
                next_key = canonical_lookup_key(moved)
            except ValueError:
                continue

            incumbent = candidate_by_next.get(next_key)
            if incumbent is None:
                candidate_by_next[next_key] = index
                continue

            incumbent_macro = macros[incumbent]
            if len(macro) < len(incumbent_macro) or (
                len(macro) == len(incumbent_macro) and tuple(macro) < tuple(incumbent_macro)
            ):
                candidate_by_next[next_key] = index

        neighbors[key] = sorted(
            [(next_key, macro_index) for next_key, macro_index in candidate_by_next.items()],
            key=lambda item: (item[0], item[1]),
        )

    return neighbors


def generate_optimal_macro_paths(
    macros: list[list[str]] | None = None,
) -> dict[tuple[int, int, int, int], list[int]]:
    """Compute shortest per-key macro-index paths to solved key on the key graph."""
    if macros is None:
        macros = _build_cycle_macro_catalog(ENDGAME_RUN_LENGTH + ENDGAME_SIZE)

    keys = sorted(permutations(ENDGAME_VALUES))
    target = SOLVED_ENDGAME_KEY
    neighbors = _macro_neighbors_by_key(macros)

    paths: dict[tuple[int, int, int, int], list[int]] = {}
    for start in keys:
        if start == target:
            paths[start] = []
            continue

        dist: dict[tuple[int, int, int, int], int] = {start: 0}
        path_by_key: dict[tuple[int, int, int, int], list[int]] = {start: []}
        pq: list[tuple[int, tuple[int, int, int, int]]] = [(0, start)]
        found = False

        while pq:
            cost, node = heappop(pq)
            if cost != dist[node]:
                continue
            if node == target:
                found = True
                break

            for nxt, macro_index in neighbors[node]:
                macro_len = len(macros[macro_index])
                next_cost = cost + macro_len
                next_path = path_by_key[node] + [macro_index]
                incumbent = dist.get(nxt)
                if (
                    incumbent is None
                    or next_cost < incumbent
                    or (next_cost == incumbent and next_path < path_by_key[nxt])
                ):
                    dist[nxt] = next_cost
                    path_by_key[nxt] = next_path
                    heappush(pq, (next_cost, nxt))

        if not found:
            raise RuntimeError(f"No macro path found for key {start}.")

        paths[start] = path_by_key[target]

    return paths


def _pruned_macro_catalog_from_paths(
    macros: list[list[str]],
    paths: dict[tuple[int, int, int, int], list[int]],
) -> tuple[list[list[str]], list[int]]:
    """Return (pruned_catalog, used_indices) from optimal per-key macro paths."""
    used_indices = sorted({index for path in paths.values() for index in path})
    pruned_catalog = [macros[index] for index in used_indices]
    return pruned_catalog, used_indices


def _rotation_moves_for_left_steps(left_steps: int, ring_size: int) -> list[str]:
    """Return shortest concrete rotation move list for a net left rotation."""
    left_steps %= ring_size
    right_steps = (ring_size - left_steps) % ring_size
    if left_steps <= right_steps:
        return ["L"] * left_steps
    return ["R"] * right_steps


def _find_continuous_trace_for_macro_indices(
    start_ring: list[int],
    macro_indices: list[int],
    macros: list[list[str]],
) -> tuple[list[dict[str, object]], list[str], list[int]]:
    """Build a label-consistent physical trace by inserting rotations before each macro.

    Returns (step_records, flat_move_list, final_ring).
    """
    ring_size = len(start_ring)

    # tuple(ring) -> (total_rotation_cost, rotation_sequences_before_each_macro)
    frontier: dict[tuple[int, ...], tuple[int, list[list[str]]]] = {
        tuple(start_ring): (0, [])
    }

    for macro_index in macro_indices:
        macro = macros[macro_index]
        next_frontier: dict[tuple[int, ...], tuple[int, list[list[str]]]] = {}

        for ring_tuple, (rotation_cost, rotations_so_far) in frontier.items():
            ring = list(ring_tuple)
            for left_steps in range(ring_size):
                rotation = _rotation_moves_for_left_steps(left_steps, ring_size)
                rotated = _apply_moves_to_ring(ring, rotation)
                after_macro = _apply_moves_to_ring(rotated, macro)
                after_tuple = tuple(after_macro)

                candidate_cost = rotation_cost + len(rotation)
                candidate_rotations = rotations_so_far + [rotation]
                incumbent = next_frontier.get(after_tuple)
                if incumbent is None or (
                    candidate_cost < incumbent[0]
                    or (
                        candidate_cost == incumbent[0]
                        and candidate_rotations < incumbent[1]
                    )
                ):
                    next_frontier[after_tuple] = (candidate_cost, candidate_rotations)

        frontier = next_frontier

    solved_candidates: list[tuple[int, list[list[str]], tuple[int, ...]]] = []
    for ring_tuple, (rotation_cost, rotations) in frontier.items():
        if get_max_run(list(ring_tuple))[1] == ring_size:
            solved_candidates.append((rotation_cost, rotations, ring_tuple))

    if not solved_candidates:
        raise RuntimeError("Could not stitch a continuous trace for macro path.")

    solved_candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    _, chosen_rotations, final_ring_tuple = solved_candidates[0]

    step_records: list[dict[str, object]] = []
    flat_moves: list[str] = []
    ring = start_ring[:]

    for step_number, (macro_index, rotation) in enumerate(
        zip(macro_indices, chosen_rotations), start=1
    ):
        macro = macros[macro_index]
        after_rotation = _apply_moves_to_ring(ring, rotation)
        after_macro = _apply_moves_to_ring(after_rotation, macro)

        step_records.append(
            {
                "step": step_number,
                "macro_index": macro_index,
                "macro_moves": "".join(macro),
                "rotation_before_macro": "".join(rotation),
                "before_ring": ring,
                "after_rotation_ring": after_rotation,
                "after_macro_ring": after_macro,
                "max_run_after_macro": get_max_run(after_macro)[1],
            }
        )

        flat_moves.extend(rotation)
        flat_moves.extend(macro)
        ring = after_macro

    return step_records, flat_moves, list(final_ring_tuple)


def generate_macro_analysis_report(
    path: Path | None = None,
) -> dict[str, object]:
    """Build optimal macro paths, prune catalog, and emit continuous traces report."""
    target_path = _MACRO_REPORT_PATH if path is None else path
    ring_size = ENDGAME_RUN_LENGTH + ENDGAME_SIZE
    macros = _build_cycle_macro_catalog(ring_size)
    optimal_paths = generate_optimal_macro_paths(macros)
    pruned_catalog, used_indices = _pruned_macro_catalog_from_paths(macros, optimal_paths)

    # Verify pruning preserves all optimal solutions.
    index_remap = {old: new for new, old in enumerate(used_indices)}
    remapped_paths: dict[tuple[int, int, int, int], list[int]] = {
        key: [index_remap[index] for index in path]
        for key, path in optimal_paths.items()
    }
    pruned_paths = generate_optimal_macro_paths(pruned_catalog)
    if pruned_paths != remapped_paths:
        raise RuntimeError("Pruned macro catalog changed optimal macro paths.")

    entries: dict[str, object] = {}
    for key in sorted(permutations(ENDGAME_VALUES)):
        start_ring = _representative_ring(key)
        macro_indices = optimal_paths[key]
        steps, full_moves, final_ring = _find_continuous_trace_for_macro_indices(
            start_ring,
            macro_indices,
            macros,
        )

        macro_plan_tokens: list[str] = []
        rings_after_macros: list[list[int]] = []
        for step in steps:
            rotation = str(step["rotation_before_macro"])
            rotation_count = len(rotation)
            macro_index = int(step["macro_index"])
            if rotation_count > 0:
                macro_plan_tokens.append(f"{rotation[0]}{rotation_count}")
            macro_plan_tokens.append(f"M{macro_index}")
            rings_after_macros.append(list(step["after_macro_ring"]))

        entries[_key_to_str(key)] = {
            "total_move_count": len(full_moves),
            "full_moves": "".join(full_moves),
            "final_first_bead": final_ring[0],
            "macro_plan": " ".join(macro_plan_tokens),
            "rings_after_macros": rings_after_macros,
        }

    report: dict[str, object] = {
        "ring_size": ring_size,
        "endgame_values": list(ENDGAME_VALUES),
        "catalog_size": len(macros),
        "used_macro_indices": used_indices,
        "pruned_catalog_size": len(pruned_catalog),
        "pruned_macro_strings": ["".join(macro) for macro in pruned_catalog],
        "pruned_macro_expansions": [_decompose_macro_to_expansion(macro) for macro in pruned_catalog],
        "entries": entries,
    }

    with target_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")

    return report


def generate_cycle_based_table() -> dict[tuple[int, int, int, int], list[str]]:
    """Generate a cycle-macro-based endgame table as concrete legal move lists.

    This uses conjugates of sigma2/sigma3 macros, projected through canonical keying,
    and solves on the 24-key graph with Dijkstra.
    """
    keys = sorted(permutations(ENDGAME_VALUES))
    ring_size = ENDGAME_RUN_LENGTH + ENDGAME_SIZE
    macros = _build_cycle_macro_catalog(ring_size)

    neighbors: dict[
        tuple[int, int, int, int],
        list[tuple[tuple[int, int, int, int], list[str]]],
    ] = {key: [] for key in keys}

    for key in keys:
        representative = _representative_ring(key)
        candidate_by_next_key: dict[tuple[int, int, int, int], list[str]] = {}

        for macro in macros:
            moved = _apply_moves_to_ring(representative, macro)
            try:
                next_key = canonical_lookup_key(moved)
            except ValueError:
                continue

            current_best = candidate_by_next_key.get(next_key)
            if current_best is None or len(macro) < len(current_best):
                candidate_by_next_key[next_key] = macro

        neighbors[key] = [
            (next_key, macro)
            for next_key, macro in sorted(
                candidate_by_next_key.items(), key=lambda item: (item[0], len(item[1]))
            )
        ]

    target = SOLVED_ENDGAME_KEY
    table: dict[tuple[int, int, int, int], list[str]] = {}
    target_ring = _representative_ring(target)

    for start in keys:
        if start == target:
            table[start] = []
            continue

        dist: dict[tuple[int, int, int, int], int] = {start: 0}
        path: dict[tuple[int, int, int, int], list[str]] = {start: []}
        pq: list[tuple[int, tuple[int, int, int, int]]] = [(0, start)]

        found = False
        while pq:
            cost, node = heappop(pq)
            if cost != dist[node]:
                continue
            if node == target:
                found = True
                break

            for nxt, macro in neighbors[node]:
                next_cost = cost + len(macro)
                next_path = path[node] + macro
                if (
                    nxt not in dist
                    or next_cost < dist[nxt]
                    or (next_cost == dist[nxt] and next_path < path[nxt])
                ):
                    dist[nxt] = next_cost
                    path[nxt] = next_path
                    heappush(pq, (next_cost, nxt))

        if not found:
            table[start] = _truncate_useless_rotations(
                _representative_ring(start),
                _shortest_path_bidirectional_ring(representative, target_ring),
            )
            continue

        table[start] = _truncate_useless_rotations(_representative_ring(start), path[target])

    return table


def generate_hybrid_endgame_table(
    search_table: dict[tuple[int, int, int, int], list[str]],
    cycle_table: dict[tuple[int, int, int, int], list[str]],
) -> dict[tuple[int, int, int, int], list[str]]:
    """Choose the shorter solution per key between search and cycle tables."""
    if set(search_table) != set(cycle_table):
        raise ValueError("Search and cycle tables must cover the same keys.")

    hybrid: dict[tuple[int, int, int, int], list[str]] = {}
    for key in sorted(search_table):
        search_moves = search_table[key]
        cycle_moves = cycle_table[key]
        representative = _representative_ring(key)
        search_moves = _truncate_useless_rotations(representative, search_moves)
        cycle_moves = _truncate_useless_rotations(representative, cycle_moves)
        if len(cycle_moves) < len(search_moves):
            hybrid[key] = cycle_moves
        else:
            hybrid[key] = search_moves
    return hybrid


def _key_to_str(key: tuple[int, int, int, int]) -> str:
    return ",".join(str(value) for value in key)


def _str_to_key(raw: str) -> tuple[int, int, int, int]:
    parts = tuple(int(value) for value in raw.split(","))
    if len(parts) != ENDGAME_SIZE:
        raise ValueError(f"Invalid endgame key: {raw}")
    return parts  # type: ignore[return-value]


def _reconstruct_bidirectional_path(
    meeting: tuple[int, ...],
    forward_prev: dict[tuple[int, ...], tuple[tuple[int, ...] | None, str | None]],
    backward_next: dict[tuple[int, ...], tuple[tuple[int, ...] | None, str | None]],
) -> list[str]:
    """Reconstruct path from start to target using predecessor/next maps."""
    moves: list[str] = []

    node = meeting
    left_half: list[str] = []
    while True:
        parent, move = forward_prev[node]
        if parent is None:
            break
        assert move is not None
        left_half.append(move)
        node = parent
    left_half.reverse()
    moves.extend(left_half)

    node = meeting
    while True:
        nxt, move = backward_next[node]
        if nxt is None:
            break
        assert move is not None
        moves.append(move)
        node = nxt

    return moves


def _reconstruct_forward_path(
    meeting: tuple[int, ...],
    forward_prev: dict[tuple[int, ...], tuple[tuple[int, ...] | None, str | None]],
) -> list[str]:
    """Reconstruct a path from a forward start state to a meeting state."""
    moves: list[str] = []
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
    meeting: tuple[int, ...],
    reverse_next: dict[tuple[int, ...], tuple[tuple[int, ...] | None, str | None]],
) -> list[str]:
    """Reconstruct a path from a meeting state to the solved target state."""
    moves: list[str] = []
    node = meeting
    while True:
        nxt, move = reverse_next[node]
        if nxt is None:
            break
        assert move is not None
        moves.append(move)
        node = nxt
    return moves


def _shortest_path_bidirectional_ring(
    start_ring: list[int],
    target_ring: list[int],
) -> list[str]:
    """Find a deterministic shortest path between concrete rings via bidirectional BFS."""
    start = tuple(start_ring)
    target = tuple(target_ring)

    if start == target:
        return []

    inverse_move = {"L": "R", "R": "L", "F": "F"}

    forward_prev: dict[tuple[int, ...], tuple[tuple[int, ...] | None, str | None]] = {
        start: (None, None)
    }
    backward_next: dict[tuple[int, ...], tuple[tuple[int, ...] | None, str | None]] = {
        target: (None, None)
    }

    forward_frontier = {start}
    backward_frontier = {target}

    while forward_frontier and backward_frontier:
        if len(forward_frontier) <= len(backward_frontier):
            next_frontier: set[tuple[int, ...]] = set()
            for node in sorted(forward_frontier):
                node_list = list(node)
                for move in MOVE_ORDER:
                    nxt_list = _apply_move_to_ring(node_list, move)
                    nxt = tuple(nxt_list)
                    if nxt not in forward_prev:
                        forward_prev[nxt] = (node, move)
                        next_frontier.add(nxt)
                    if nxt in backward_next:
                        return _reconstruct_bidirectional_path(nxt, forward_prev, backward_next)
            forward_frontier = next_frontier
        else:
            next_frontier = set()
            for node in sorted(backward_frontier):
                node_list = list(node)
                for move in MOVE_ORDER:
                    prev_list = _apply_move_to_ring(node_list, move)
                    prev = tuple(prev_list)
                    forward_move = inverse_move[move]
                    if prev not in backward_next:
                        backward_next[prev] = (node, forward_move)
                        next_frontier.add(prev)
                    if prev in forward_prev:
                        return _reconstruct_bidirectional_path(prev, forward_prev, backward_next)
            backward_frontier = next_frontier

    raise RuntimeError("No path found between representative endgame rings.")


def generate_endgame_table_interleaved(
    *,
    progress_stream: object = sys.stderr,
    log_state_interval: int = 1_000_000,
    remaining_log_threshold: int = 4,
    max_workers: int | None = None,
) -> dict[tuple[int, int, int, int], list[str]]:
    """Generate table by interleaving all starts with one reverse BFS tree.

    This intentionally favors visibility over speed: it advances one reverse layer and
    one forward layer (for every unsolved start key) per depth, logging progress.
    """
    if log_state_interval < 1:
        raise ValueError("log_state_interval must be >= 1")
    if remaining_log_threshold < 0:
        raise ValueError("remaining_log_threshold must be >= 0")
    if max_workers is not None and max_workers < 1:
        raise ValueError("max_workers must be >= 1 when provided")

    keys = sorted(permutations(ENDGAME_VALUES))
    target_ring = tuple(_representative_ring(SOLVED_ENDGAME_KEY))

    inverse_move = {"L": "R", "R": "L", "F": "F"}

    reverse_next: dict[tuple[int, ...], tuple[tuple[int, ...] | None, str | None]] = {
        target_ring: (None, None)
    }
    reverse_frontier: set[tuple[int, ...]] = {target_ring}

    forward_prev_by_key: dict[
        tuple[int, int, int, int],
        dict[tuple[int, ...], tuple[tuple[int, ...] | None, str | None]],
    ] = {}
    forward_frontier_by_key: dict[tuple[int, int, int, int], set[tuple[int, ...]]] = {}
    solved: dict[tuple[int, int, int, int], list[str]] = {}

    all_seen: set[tuple[int, ...]] = {target_ring}
    seen_lock = Lock()
    total_states_seen = 1
    last_logged_seen = total_states_seen
    started_at = monotonic()

    def add_seen_if_new(state: tuple[int, ...]) -> bool:
        """Atomically add a state to seen set and increment shared counter once."""
        nonlocal total_states_seen
        with seen_lock:
            if state in all_seen:
                return False
            all_seen.add(state)
            total_states_seen += 1
            return True

    def get_total_states_seen() -> int:
        with seen_lock:
            return total_states_seen

    def maybe_log(depth: int, *, force_depth: bool = False) -> None:
        nonlocal last_logged_seen
        seen_now = get_total_states_seen()
        if force_depth or (seen_now - last_logged_seen) >= log_state_interval:
            elapsed_s = monotonic() - started_at
            remaining = [key for key in keys if key not in solved]
            remaining_suffix = ""
            if len(remaining) < remaining_log_threshold:
                remaining_suffix = f" remaining={remaining}"
            print(
                (
                    f"depth={depth} "
                    f"elapsed_s={elapsed_s:.1f} "
                    f"total_states_seen={seen_now} "
                    f"solved_start_states={len(solved)}/{len(keys)}"
                    f"{remaining_suffix}"
                ),
                file=progress_stream,
                flush=True,
            )
            last_logged_seen = seen_now

    if max_workers is None:
        workers = max(1, (os.cpu_count() or 1) - 1)
    else:
        workers = max_workers

    inverse_move = {"L": "R", "R": "L", "F": "F"}

    def reverse_edges_for_node(
        node: tuple[int, ...], src_rank: int
    ) -> list[tuple[int, int, tuple[int, ...], tuple[int, ...], str]]:
        node_list = list(node)
        edges: list[tuple[int, int, tuple[int, ...], tuple[int, ...], str]] = []
        for move_rank, move in enumerate(MOVE_ORDER):
            predecessor_list = _apply_move_to_ring(node_list, inverse_move[move])
            predecessor = tuple(predecessor_list)
            edges.append((src_rank, move_rank, predecessor, node, move))
        return edges

    def forward_edges_for_node(
        node: tuple[int, ...], src_rank: int
    ) -> list[tuple[int, int, tuple[int, ...], tuple[int, ...], str]]:
        node_list = list(node)
        edges: list[tuple[int, int, tuple[int, ...], tuple[int, ...], str]] = []
        for move_rank, move in enumerate(MOVE_ORDER):
            nxt_list = _apply_move_to_ring(node_list, move)
            nxt = tuple(nxt_list)
            edges.append((src_rank, move_rank, node, nxt, move))
        return edges

    for key in keys:
        start = tuple(_representative_ring(key))
        forward_prev_by_key[key] = {start: (None, None)}
        forward_frontier_by_key[key] = {start}
        add_seen_if_new(start)

        if start in reverse_next:
            solved[key] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        depth = 0
        while len(solved) < len(keys):
            depth += 1

            next_reverse_frontier: set[tuple[int, ...]] = set()
            sorted_reverse_frontier = sorted(reverse_frontier)

            if workers > 1 and len(sorted_reverse_frontier) > 1:
                reverse_futures = [
                    executor.submit(reverse_edges_for_node, node, src_rank)
                    for src_rank, node in enumerate(sorted_reverse_frontier)
                ]
                reverse_edges = [edge for fut in reverse_futures for edge in fut.result()]
            else:
                reverse_edges = [
                    edge
                    for src_rank, node in enumerate(sorted_reverse_frontier)
                    for edge in reverse_edges_for_node(node, src_rank)
                ]

            reverse_edges.sort(key=lambda item: (item[0], item[1]))
            for _, _, predecessor, node, move in reverse_edges:
                if predecessor in reverse_next:
                    continue

                reverse_next[predecessor] = (node, move)
                next_reverse_frontier.add(predecessor)
                if add_seen_if_new(predecessor):
                    maybe_log(depth)

            reverse_frontier = next_reverse_frontier

            for key in keys:
                if key in solved:
                    continue

                prev_map = forward_prev_by_key[key]
                frontier = forward_frontier_by_key[key]
                next_frontier: set[tuple[int, ...]] = set()
                found_meeting: tuple[int, ...] | None = None

                sorted_frontier = sorted(frontier)
                if workers > 1 and len(sorted_frontier) > 1:
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

                forward_edges.sort(key=lambda item: (item[0], item[1]))
                for _, _, node, nxt, move in forward_edges:
                    if nxt not in prev_map:
                        prev_map[nxt] = (node, move)
                        next_frontier.add(nxt)
                        if add_seen_if_new(nxt):
                            maybe_log(depth)

                    if nxt in reverse_next:
                        found_meeting = nxt
                        break

                if found_meeting is not None:
                    prefix = _reconstruct_forward_path(found_meeting, prev_map)
                    suffix = _reconstruct_reverse_tail(found_meeting, reverse_next)
                    solved[key] = _truncate_useless_rotations(
                        _representative_ring(key), prefix + suffix
                    )
                    forward_frontier_by_key[key] = set()
                else:
                    forward_frontier_by_key[key] = next_frontier

            # Always emit at least one line for each completed depth.
            maybe_log(depth, force_depth=True)

            if not reverse_frontier and all(
                not forward_frontier_by_key[key] for key in keys if key not in solved
            ):
                unresolved = [key for key in keys if key not in solved]
                raise RuntimeError(f"Interleaved search stalled. Unresolved start keys: {unresolved}")

    return solved


def generate_endgame_table() -> dict[tuple[int, int, int, int], list[str]]:
    """Generate a hybrid endgame table from search and cycle-based constructions."""
    search_table = generate_endgame_table_interleaved()
    cycle_table = generate_cycle_based_table()
    return generate_hybrid_endgame_table(search_table, cycle_table)


def validate_endgame_table(table: dict[tuple[int, int, int, int], list[str]]) -> None:
    """Validate that the table matches the current bidirectional-BFS generator."""
    regenerated = generate_endgame_table()
    if table != regenerated:
        raise ValueError("Loaded endgame table does not match generated bidirectional-BFS table.")


def load_endgame_table(validate: bool = True) -> dict[tuple[int, int, int, int], list[str]]:
    """Load the precomputed endgame table from JSON.

    If the JSON is missing, generate it on the fly so solver usage stays functional.
    """
    global _TABLE_CACHE

    if _TABLE_CACHE is not None:
        return _TABLE_CACHE

    if _TABLE_PATH.exists():
        with _TABLE_PATH.open("r", encoding="utf-8") as f:
            raw: dict[str, list[str]] = json.load(f)
        table = {_str_to_key(key): moves for key, moves in raw.items()}
    else:
        table = generate_endgame_table()

    if validate:
        validate_endgame_table(table)

    _TABLE_CACHE = table
    return table


def write_endgame_table(path: Path | None = None) -> dict[tuple[int, int, int, int], list[str]]:
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
    report = generate_macro_analysis_report()
    print(
        "Wrote macro analysis report to "
        f"{_MACRO_REPORT_PATH} "
        f"(catalog={report['catalog_size']}, pruned={report['pruned_catalog_size']})."
    )

    table = write_endgame_table()
    print(f"Wrote hybrid table to {_TABLE_PATH} with {len(table)} entries.")
    print(f"Max path length: {max(len(path) for path in table.values())}")
    print(f"Min path length: {min(len(path) for path in table.values())}")
    return 0


def main_macro_report() -> int:
    """CLI entrypoint for macro analysis only (no table generation)."""
    report = generate_macro_analysis_report()
    print(
        "Wrote macro analysis report to "
        f"{_MACRO_REPORT_PATH} "
        f"(catalog={report['catalog_size']}, pruned={report['pruned_catalog_size']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def lookup_endgame_moves(ring: list[int]) -> list[str]:
    """Lookup canonical endgame moves for a live ring.
    
    Validates that the returned moves actually solve the ring without checking
    for optimality (which would require expensive table regeneration).
    """
    key = canonical_lookup_key(ring)
    table = load_endgame_table(validate=False)
    moves = table[key][:]
    
    # Quick validation: apply moves and check the ring is solved
    test_ring = ring[:]
    for move in moves:
        test_ring = _apply_move_to_ring(test_ring, move)
    
    # Verify the result is solved (all beads in consecutive order, possibly rotated)
    from .solver import get_max_run
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
        raise ValueError("Endgame solver requires a protected run of at least 16.")

    state = rotate_shortest(state, run_start)

    moves = lookup_endgame_moves(state.ring)
    for move in moves:
        state = _apply_move_to_state(state, move)

    final_length = get_max_run(state.ring)[1]
    if final_length != len(state.ring):
        raise RuntimeError("Endgame move translation failed to solve the ring up to rotation.")

    return state
