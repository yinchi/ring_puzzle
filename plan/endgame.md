## Plan: Endgame Lookup Solver

Add a solver-side endgame phase that takes over once `extend_max_run` has grown a protected run to length 16 or more, normalizes the ring so the protected run is labeled `1..16` (or longer), and uses an exact shortest-path lookup over the canonical last four positions `17..20` to return legal moves for the autosolver to execute. Place the endgame-specific logic in `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/endgame.py` and store the generated lookup table in `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/endgame.json`. When the run length is greater than 16, some prefix of that 4-position suffix may already be solved, but the lookup still keys on all four positions. Keep this solver-local for now; do not wire the curses `a` command yet.

**Steps**
1. Define the boundary between the constructive solver and the endgame solver in `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/solver.py` around `extend_max_run`, `normalize`, `get_max_run`, and `RingState`.
   Capture the invariant explicitly: after repeated constructive steps, the solver may stop when the longest run is at least 16 and the canonical last four positions correspond to beads `17..20` after normalization. If the run has already grown to 17, 18, or 19, then the first 1, 2, or 3 of those positions are already solved, but lookup still uses the full 4-position suffix. `solver.py` should remain responsible for the constructive phase and for delegating to the endgame module, while preserving accumulated legal moves.
2. Add `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/endgame.py` as the dedicated implementation surface for endgame lookup.
   Move the canonical endgame helpers here: relabel values so the protected run starts at bead `1`, derive a canonical cyclic view anchored at `get_max_run(...)[0]`, define the canonical key for beads `17..20`, and load or validate the lookup table from `endgame.json`. These helpers must be lookup-only and must not append moves.
3. Generate `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/endgame.json` from a reverse BFS rooted at the canonical solved endgame view.
   Use a generator in `endgame.py` or a tightly coupled helper invoked from there to enumerate canonical states where positions `0..15` are fixed as `1..16` and positions `16..19` are the lookup window for beads `17..20`. Maintain a seen-state map keyed by the canonical four-position suffix so each reachable arrangement is enqueued once and the first discovered path is recorded as the shortest one. Persist the resulting shortest-path table as JSON so runtime lookup does not recompute BFS.
4. Add a public endgame API in `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/endgame.py` and a thin orchestration entrypoint in `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/solver.py`.
   Recommended shape: `endgame.py` exposes a function such as `solve_endgame(state: RingState) -> RingState` or `lookup_endgame_moves(ring: list[int]) -> list[str]`, while `solver.py` exposes an end-to-end function such as `solve_from_state(state: RingState) -> RingState` that repeatedly calls `extend_max_run` until the handoff point and then delegates to the endgame module.
5. Decide how canonical-view solutions are translated back onto the live state in `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/endgame.py`.
   Because `F` acts on positions, label normalization alone is not enough to replay a canonical solution on an arbitrarily rotated live ring. The endgame module should therefore track the run anchor returned by `get_max_run`, build a lookup-only logical rotation for the canonical key, and translate the canonical shortest solution back into the live frame using a deterministic legal-move wrapper. Add guards that reject states whose canonical view does not place beads `17..20` in the final four logical positions.
6. Add focused tests in `/home/yinchi/git_projects/ring_puzzle/tests/test_solver.py` and, if needed, `/home/yinchi/git_projects/ring_puzzle/tests/test_endgame.py`.
   Add table-coverage tests over all 24 permutations of beads `17,18,19,20` in the canonical last-four-position view with `1..16` fixed ahead of them. Assert that the end-to-end solver returns replayable legal moves that solve the ring up to rotation, that the loaded JSON table matches the expected shortest paths, and that run lengths 17, 18, and 19 still use all four suffix positions even when part of that suffix is already solved.
7. Add a regression test for the current handoff point.
   Replace or supplement the current `ValueError` expectation with tests that prove the constructive phase hands off cleanly once the ring has a run of at least 16 and that the combined solver completes the exact case now used as the endgame sentinel.
8. Leave UI integration explicitly out of scope for this change.
   Do not modify `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/__init__.py` beyond, at most, imports needed by tests. The output of this work should be a solver function that returns the full move list for the future autosolver command.

**Relevant files**
- `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/solver.py` — keep `normalize`, `get_max_run`, `extend_max_run`, `shift_left1`, `shift_left2`, `shift_left3`, and `RingState`; add the end-to-end orchestration entrypoint and delegation into `endgame.py`.
- `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/endgame.py` — new dedicated endgame module for canonicalization, JSON loading, reverse-BFS generation logic, and translation of canonical solutions back to live legal moves.
- `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/endgame.json` — generated shortest-path lookup table committed as data for runtime loading.
- `/home/yinchi/git_projects/ring_puzzle/tests/test_solver.py` — retain constructive-phase coverage and end-to-end handoff tests.
- `/home/yinchi/git_projects/ring_puzzle/tests/test_endgame.py` — optional focused tests for canonicalization, JSON loading, lookup coverage, and optimality if splitting tests improves clarity.
- `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/__init__.py` — note as intentionally excluded from behavior changes for now; future consumer of the solver API.
- `/home/yinchi/git_projects/ring_puzzle/README.md` — optional small documentation update after implementation to describe the new endgame module and generated table artifact.

**Verification**
1. Add an exhaustive test that iterates over all 24 permutations of beads `17,18,19,20` in the canonical endgame view with `1..16` ahead of them, calls the new solver entrypoint, replays the returned moves with the existing `apply_moves` helper, and asserts the result is solved up to rotation.
2. Add at least one deterministic end-to-end test from a nontrivial scrambled 20-bead ring that exercises repeated `extend_max_run` handoffs into the endgame solver, replays the full returned move list, and asserts the final ring is solved up to rotation.
3. Assert optimality in the canonical view by checking that `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/endgame.json` stores shortest-path data for each reachable arrangement of the four-position suffix, then separately verify that the live-state solver translates those canonical solutions into replayable legal moves without changing the solved outcome.
4. Add normalization tests that start from rotated or relabeled states with run lengths 16, 17, 18, and 19 and prove they map to the expected canonical lookup key before solving.
5. Add a consistency test or regeneration check that the JSON artifact loaded by `endgame.py` matches the BFS generation logic used to produce it.
6. During implementation, run the full pytest suite after each substantive completed phase so regressions are caught immediately; in the current project that should be cheap enough to prefer certainty over narrower targeting.
7. Use narrower file-scoped reruns such as `uv run pytest tests/test_solver.py` or `uv run pytest tests/test_endgame.py` only as an optional faster loop while debugging, then rerun the full suite at the next checkpoint and at the end.

**Decisions**
- Included: solver-local end-to-end move generation through the constructive phase plus exact lookup over the canonical four-position suffix containing beads `17..20`.
- Excluded: wiring the curses `a` command or adding interactive playback in the UI.
- Endgame-specific logic lives in `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/endgame.py`, while the generated lookup table is stored in `/home/yinchi/git_projects/ring_puzzle/src/ring_puzzle/endgame.json` and loaded at runtime.
- Optimal means minimum count of legal moves `L`, `R`, and `F` in the canonical endgame frame.
- Recommended implementation strategy is reverse BFS from the canonical solved endgame state so the JSON table and its optimality proof are derived together.
- Recommended canonicalization rule is two-stage and lookup-only: relabel values so the protected run starts at `1`, then anchor the cyclic view at the run start reported by `get_max_run`. This logical rotation is not recorded as a legal move.
- When the run length exceeds 16, lookup still uses all four canonical suffix positions `17..20`; the reachable state set is just a smaller subset because some leading suffix positions are already solved.

**Further Considerations**
1. If reverse BFS reveals more than one shortest solution for a suffix arrangement, keep the first deterministic sequence discovered and document the traversal order so tests remain stable.
2. If the constructive phase can occasionally reach a run length greater than 16 before handoff, ensure the canonical key builder accepts any protected run `1..k` with `k >= 16` and still uses the full four-position suffix `17..20` as the lookup state.
3. If any of the 24 suffix arrangements are unreachable under the protected-run invariant, capture that explicitly in tests rather than silently assuming full coverage.
4. Broader reverse-BFS caching is a separate scope choice: if we also retain reached states that do not match the canonical `1..16` plus four-position suffix pattern, then the solver may be able to hand off earlier whenever the current normalized ring matches that cache. That should be treated as an optional extension only after measuring the reachable-state count and defining a broader canonical key, because it changes the project from a strict 4-bead endgame table into a more general near-solved pattern database.