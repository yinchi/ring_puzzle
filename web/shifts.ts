/**
 * Shift macros — direct port of shifts.py.
 * Each function takes a RingState, applies a compound move sequence to
 * reposition a target bead without disturbing the protected run, and
 * returns the updated state.
 */

import type { RingState } from "./types";
import { stateApplyMove } from "./puzzle";

/** Move target bead A from position 3 → 0. Moves: F */
export function shiftLeft3(state: RingState): RingState {
  const r = state.ring.slice();
  [r[0], r[1], r[2], r[3]] = [state.ring[3], state.ring[2], state.ring[1], state.ring[0]];
  return { ring: r, offset: state.offset, moves: [...state.moves, "F"] };
}

/** Move target bead A from position 2 → 0. Moves: L F R F */
export function shiftLeft2(state: RingState): RingState {
  const r = state.ring.slice();
  const s = state.ring;
  r[0] = s[2]; r[1] = s[3]; r[2] = s[4]; r[3] = s[0]; r[4] = s[1];
  return {
    ring: r,
    offset: state.offset,
    moves: [...state.moves, "L", "F", "R", "F"],
  };
}

/** Move target bead A from position 1 → 0. Moves: F L F R F */
export function shiftLeft1(state: RingState): RingState {
  const r = state.ring.slice();
  const s = state.ring;
  r[0] = s[1]; r[1] = s[0]; r[2] = s[4]; r[3] = s[3]; r[4] = s[2];
  return {
    ring: r,
    offset: state.offset,
    moves: [...state.moves, "F", "L", "F", "R", "F"],
  };
}

/** Move target bead A from position 0 → 3. Moves: F */
export function shiftRight3(state: RingState): RingState {
  const r = state.ring.slice();
  [r[0], r[1], r[2], r[3]] = [state.ring[3], state.ring[2], state.ring[1], state.ring[0]];
  return { ring: r, offset: state.offset, moves: [...state.moves, "F"] };
}

/** Move target bead P from position 1 → 3. Moves: R F L F */
export function shiftRight2(state: RingState): RingState {
  const r = state.ring.slice();
  const s = state.ring;
  const last = s[s.length - 1];
  r[0] = s[3]; r[1] = last; r[2] = s[0]; r[3] = s[1];
  r[r.length - 1] = s[2];
  return {
    ring: r,
    offset: state.offset,
    moves: [...state.moves, "R", "F", "L", "F"],
  };
}

/** Move target bead P from position 2 → 3. Moves: F R F L F */
export function shiftRight1(state: RingState): RingState {
  const r = state.ring.slice();
  const s = state.ring;
  const last = s[s.length - 1];
  r[1] = last; r[2] = s[3]; r[3] = s[2];
  r[r.length - 1] = s[1];
  return {
    ring: r,
    offset: state.offset,
    moves: [...state.moves, "F", "R", "F", "L", "F"],
  };
}
