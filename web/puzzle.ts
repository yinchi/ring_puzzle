import type { Move, Ring, RingState } from "./types";

export const FLIP_SIZE = 4;
export const RING_SIZE = 20;
export const ENDGAME_RUN_LENGTH = RING_SIZE - FLIP_SIZE; // 16

const SOLVED_RING: Ring = Array.from({ length: RING_SIZE }, (_, i) => i + 1);

export function rotateLeft(ring: Ring, steps = 1): Ring {
  steps = ((steps % RING_SIZE) + RING_SIZE) % RING_SIZE;
  return [...ring.slice(steps), ...ring.slice(0, steps)];
}

export function rotateRight(ring: Ring, steps = 1): Ring {
  steps = ((steps % RING_SIZE) + RING_SIZE) % RING_SIZE;
  return [...ring.slice(RING_SIZE - steps), ...ring.slice(0, RING_SIZE - steps)];
}

export function flip(ring: Ring): Ring {
  return [...ring.slice(0, FLIP_SIZE).reverse(), ...ring.slice(FLIP_SIZE)];
}

export function isSolved(ring: Ring): boolean {
  for (let offset = 0; offset < RING_SIZE; offset++) {
    if (ring.every((v, i) => v === SOLVED_RING[(i + offset) % RING_SIZE])) return true;
  }
  return false;
}

export function newRandomGame(): Ring {
  const ring: Ring = Array.from({ length: RING_SIZE }, (_, i) => i + 1);
  for (let i = RING_SIZE - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [ring[i], ring[j]] = [ring[j], ring[i]];
  }
  return ring;
}

export function applyMove(ring: Ring, move: Move): Ring {
  if (move === "L") return rotateLeft(ring);
  if (move === "R") return rotateRight(ring);
  return flip(ring);
}

/**
 * Find the longest run of consecutive numbers in the ring.
 * Returns { startIdx, length, dist } where dist is the cyclic distance
 * from the end of the run to the next consecutive number (null if full ring).
 */
export function getMaxRun(ring: Ring): { startIdx: number; length: number; dist: number | null } {
  const n = ring.length;
  const doubled = [...ring, ...ring];
  let maxStart = 0;
  let maxLen = 1;

  for (let start = 0; start < n; start++) {
    let len = 1;
    while (len < n && ((doubled[start + len] - doubled[start + len - 1] + n) % n) === 1) {
      len++;
    }
    if (len > maxLen) {
      maxLen = len;
      maxStart = start;
    }
  }

  if (maxLen === n) return { startIdx: maxStart, length: maxLen, dist: null };

  const runHeadVal = ring[maxStart];
  const runTailVal = ((runHeadVal + maxLen - 2) % n) + 1;
  const nextConsec = (runTailVal % n) + 1;
  const runEnd = (maxStart + maxLen - 1) % n;
  let dist: number | null = null;
  for (let i = 0; i < n; i++) {
    if (ring[i] === nextConsec) {
      dist = ((i - runEnd) % n + n) % n;
      break;
    }
  }
  return { startIdx: maxStart, length: maxLen, dist };
}

/**
 * Normalize the ring: relabel beads so the longest run starts at value 1.
 */
export function normalize(ring: Ring): Ring {
  const { startIdx } = getMaxRun(ring);
  const offset = 1 - ring[startIdx];
  return ring.map((b) => ((b + offset - 1 + RING_SIZE) % RING_SIZE) + 1);
}

/** Build the canonical endgame key from a live ring as "a,b,c,d". */
export function canonicalLookupKey(ring: Ring): string {
  const normalized = normalize(ring);
  const { startIdx } = getMaxRun(normalized);
  const anchored = [...normalized.slice(startIdx), ...normalized.slice(0, startIdx)];
  const suffix = anchored.slice(ENDGAME_RUN_LENGTH, ENDGAME_RUN_LENGTH + FLIP_SIZE);
  return suffix.join(",");
}

// ---- RingState helpers (mirroring util.py) ----

export function stateRotateLeft(state: RingState, steps = 1): RingState {
  if (steps < 0) return stateRotateRight(state, -steps);
  steps = ((steps % RING_SIZE) + RING_SIZE) % RING_SIZE;
  if (steps === 0) return state;
  return {
    ring: rotateLeft(state.ring, steps),
    offset: state.offset,
    moves: [...state.moves, ...Array(steps).fill("L") as Move[]],
  };
}

export function stateRotateRight(state: RingState, steps = 1): RingState {
  if (steps < 0) return stateRotateLeft(state, -steps);
  steps = ((steps % RING_SIZE) + RING_SIZE) % RING_SIZE;
  if (steps === 0) return state;
  return {
    ring: rotateRight(state.ring, steps),
    offset: state.offset,
    moves: [...state.moves, ...Array(steps).fill("R") as Move[]],
  };
}

export function stateRotateShortest(state: RingState, leftSteps: number): RingState {
  const n = RING_SIZE;
  leftSteps = ((leftSteps % n) + n) % n;
  const rightSteps = (n - leftSteps) % n;
  if (leftSteps <= rightSteps) return stateRotateLeft(state, leftSteps);
  return stateRotateRight(state, rightSteps);
}

export function stateApplyMove(state: RingState, move: Move): RingState {
  return {
    ring: applyMove(state.ring, move),
    offset: state.offset,
    moves: [...state.moves, move],
  };
}
