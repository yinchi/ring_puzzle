import json
from itertools import permutations

from ring_puzzle.endgame import (
    ENDGAME_VALUES,
    _apply_moves_to_ring,
    _build_cycle_macro_catalog,
    _representative_ring,
    _decompose_macro_to_expansion,
    generate_macro_analysis_report,
)
from ring_puzzle.solver import get_max_run


def _key_to_str(key: tuple[int, int, int, int]) -> str:
    return ",".join(str(value) for value in key)


def test_generate_macro_analysis_report_replays_continuous_traces(tmp_path) -> None:
    report_path = tmp_path / "endgame_macro_report.json"
    macros = _build_cycle_macro_catalog(20)

    report = generate_macro_analysis_report(report_path)

    assert report_path.exists()
    on_disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert report == on_disk

    assert report["catalog_size"] >= report["pruned_catalog_size"] > 0

    entries = report["entries"]
    expected_keys = {
        _key_to_str(key) for key in permutations(ENDGAME_VALUES)
    }
    assert set(entries) == expected_keys

    for key_str in sorted(entries):
        entry = entries[key_str]
        macro_plan_text = entry["macro_plan"]
        macro_plan_tokens = [] if not macro_plan_text else macro_plan_text.split()
        rings_after_macros = entry["rings_after_macros"]

        key = tuple(int(part) for part in key_str.split(","))
        ring = _representative_ring(key)  # type: ignore[arg-type]
        continuous_moves: list[str] = []
        step_index = 0
        token_index = 0

        while token_index < len(macro_plan_tokens):
            rotation_moves: list[str] = []
            token = macro_plan_tokens[token_index]

            if token.startswith("L") or token.startswith("R"):
                rotation_dir = token[0]
                rotation_count = int(token[1:])
                rotation_moves = [rotation_dir] * rotation_count
                token_index += 1
                token = macro_plan_tokens[token_index]

            assert token.startswith("M")
            macro_index = int(token[1:])
            token_index += 1

            macro_moves = macros[macro_index]
            step_moves = rotation_moves + macro_moves

            ring = _apply_moves_to_ring(ring, step_moves)
            continuous_moves.extend(step_moves)
            assert ring == rings_after_macros[step_index]
            step_index += 1

        assert step_index == len(rings_after_macros)

        assert "".join(continuous_moves) == entry["full_moves"]
        assert len(continuous_moves) == entry["total_move_count"]
        assert ring[0] == entry["final_first_bead"]
        assert get_max_run(ring)[1] == len(ring)


def test_pruned_macro_expansions_are_valid(tmp_path) -> None:
    """Verify that pruned_macro_expansions are correctly decomposed and symbolic."""
    report_path = tmp_path / "endgame_macro_report.json"
    macros = _build_cycle_macro_catalog(20)

    report = generate_macro_analysis_report(report_path)

    assert "pruned_macro_expansions" in report
    assert "pruned_macro_strings" in report
    assert "used_macro_indices" in report

    expansions = report["pruned_macro_expansions"]
    strings = report["pruned_macro_strings"]
    indices = report["used_macro_indices"]

    assert len(expansions) == len(strings) == len(indices) == 8

    # Verify each expansion matches its macro string decomposition
    for i, (expansion, macro_str, macro_idx) in enumerate(zip(expansions, strings, indices)):
        macro_moves = list(macro_str)

        # Verify expansion is non-empty and contains only valid tokens
        assert expansion != "UNKNOWN", f"M{macro_idx} at position {i} failed to decompose"
        for token in expansion.split():
            # Token format: L/R followed by digits, F alone, or S followed by digit + optional '
            assert token[0] in "LRFS", f"Invalid token: {token}"
            if token[0] in "LR":
                assert token[1:].isdigit(), f"Invalid token: {token}"
            elif token[0] == "F":
                assert len(token) == 1, f"Invalid token: {token} (F should not have suffix)"
            else:  # S token
                assert (token[1:].isdigit() or token[1:-1].isdigit() and token[-1] == "'"), f"Invalid token: {token}"

        # Verify expansion matches the actual macro by decomposing again
        recomputed = _decompose_macro_to_expansion(macro_moves)
        assert recomputed == expansion, f"M{macro_idx}: expansion mismatch"

