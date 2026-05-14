/**
 * Two-phase solver — port of solver.py + endgame lookup from endgame.py.
 * BFS table generation is omitted; we only load the precomputed endgame.json.
 */

import type { EndgameTable, Move, RingState } from "./types";
import {
  ENDGAME_RUN_LENGTH,
  FLIP_SIZE,
  RING_SIZE,
  canonicalLookupKey,
  getMaxRun,
  isSolved,
  stateApplyMove,
  stateRotateShortest,
} from "./puzzle";
import {
  shiftLeft1,
  shiftLeft2,
  shiftLeft3,
  shiftRight1,
  shiftRight2,
  shiftRight3,
} from "./shifts";

// ---- Endgame ----

function lookupEndgameMoves(ring: number[], table: EndgameTable): Move[] {
  const key = canonicalLookupKey(ring);
  const moves = table[key];
  if (!moves) throw new Error(`No endgame entry for key: ${key}`);
  return moves as Move[];
}

function solveEndgame(state: RingState, table: EndgameTable): RingState {
  const { startIdx, length } = getMaxRun(state.ring);
  if (length < ENDGAME_RUN_LENGTH) {
    throw new Error(`Endgame requires run ≥ ${ENDGAME_RUN_LENGTH}, got ${length}`);
  }
  // Rotate run to index 0
  state = stateRotateShortest(state, startIdx);

  const moves = lookupEndgameMoves(state.ring, table);
  for (const move of moves) {
    state = stateApplyMove(state, move);
  }
  return state;
}

// ---- Early-game ----

function extendTail(state: RingState): RingState {
  const n = RING_SIZE;
  const { startIdx: startIndex0, length: origLen } = getMaxRun(state.ring);
  if (origLen === n) throw new Error("Ring is already solved.");

  const runHeadVal = state.ring[startIndex0];
  const runTailVal = ((runHeadVal + origLen - 2) % n) + 1;
  const appendVal = (runTailVal % n) + 1;
  const prependVal = ((runHeadVal - 2 + n) % n) + 1;
  const unsolvedLen = n - origLen;

  while (true) {
    const runHeadPos = state.ring.indexOf(runHeadVal);
    const runTailPos = (runHeadPos + origLen - 1) % n;

    // Termination checks
    if (state.ring[(runTailPos + 1) % n] === appendVal) return state;
    if (state.ring[(runHeadPos - 1 + n) % n] === prependVal) return state;

    const targetPos = state.ring.indexOf(appendVal);
    const dist = ((targetPos - runTailPos) % n + n) % n;

    if (dist >= FLIP_SIZE) {
      state = stateRotateShortest(state, ((targetPos - 3) % n + n) % n);
      state = shiftLeft3(state);
    } else if (dist === 3) {
      if (unsolvedLen < 5) throw new Error("Cannot extend tail safely.");
      state = stateRotateShortest(state, ((targetPos - 2) % n + n) % n);
      state = shiftLeft2(state);
    } else if (dist === 2) {
      if (unsolvedLen < 5) throw new Error("Cannot extend tail safely.");
      state = stateRotateShortest(state, ((targetPos - 1) % n + n) % n);
      state = shiftLeft1(state);
    } else {
      throw new Error(`Unexpected dist in extendTail: ${dist}`);
    }
  }
}

function extendHead(state: RingState): RingState {
  const n = RING_SIZE;
  const { startIdx: startIndex0, length: origLen } = getMaxRun(state.ring);
  if (origLen === n) throw new Error("Ring is already solved.");

  const runHeadVal = state.ring[startIndex0];
  const predVal = ((runHeadVal - 2 + n) % n) + 1;
  const runTailVal = ((runHeadVal + origLen - 2) % n) + 1;
  const tailNextVal = (runTailVal % n) + 1;
  const unsolvedLen = n - origLen;

  while (true) {
    const runHeadPos = state.ring.indexOf(runHeadVal);
    const runTailPos = (runHeadPos + origLen - 1) % n;

    // Termination checks
    if (state.ring[(runHeadPos - 1 + n) % n] === predVal) return state;
    if (state.ring[(runTailPos + 1) % n] === tailNextVal) return state;

    const predPos = state.ring.indexOf(predVal);
    const distHead = ((runHeadPos - predPos) % n + n) % n;

    if (distHead >= FLIP_SIZE) {
      state = stateRotateShortest(state, (predPos % n + n) % n);
      state = shiftRight3(state);
    } else if (distHead === 3) {
      if (unsolvedLen < 5) throw new Error("Cannot extend head safely.");
      state = stateRotateShortest(state, ((predPos - 1) % n + n) % n);
      state = shiftRight2(state);
    } else if (distHead === 2) {
      if (unsolvedLen < 5) throw new Error("Cannot extend head safely.");
      state = stateRotateShortest(state, ((predPos - 2) % n + n) % n);
      state = shiftRight1(state);
    } else {
      throw new Error(`Unexpected distHead in extendHead: ${distHead}`);
    }
  }
}

function twoEndedExtend(state: RingState): RingState {
  let tailState: RingState | null = null;
  let headState: RingState | null = null;

  try { tailState = extendTail(state); } catch { /* ok */ }
  try { headState = extendHead(state); } catch { /* ok */ }

  if (!tailState && !headState) throw new Error("Cannot extend run at either end.");

  const tailCost = tailState ? tailState.moves.length - state.moves.length : Infinity;
  const headCost = headState ? headState.moves.length - state.moves.length : Infinity;

  return tailCost <= headCost ? tailState! : headState!;
}

function cancelOppositeRotations(moves: Move[]): Move[] {
  const out: Move[] = [];
  let i = 0;
  while (i < moves.length) {
    if (
      i < moves.length - 1 &&
      ((moves[i] === "L" && moves[i + 1] === "R") ||
        (moves[i] === "R" && moves[i + 1] === "L"))
    ) {
      i += 2;
    } else {
      out.push(moves[i++]);
    }
  }
  return out;
}

// ---- Public API ----

export function solveFromState(state: RingState, table: EndgameTable): RingState {
  while (true) {
    const { length } = getMaxRun(state.ring);
    if (isSolved(state.ring)) return state;
    if (length >= ENDGAME_RUN_LENGTH) return solveEndgame(state, table);
    state = twoEndedExtend(state);
  }
}

export function solveMoves(ring: number[], table: EndgameTable): Move[] {
  const state: RingState = { ring: ring.slice(), offset: 0, moves: [] };
  const solved = solveFromState(state, table);
  return cancelOppositeRotations(solved.moves);
}
