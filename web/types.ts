export type Move = "L" | "R" | "F";
export type Ring = number[]; // 20 integers, 1–20

export interface RingState {
  ring: Ring;
  offset: number;
  moves: Move[];
}

/** Keys are "17,18,19,20" style strings; values are move sequences. */
export type EndgameTable = Record<string, Move[]>;

export interface SlotCoord {
  x: number;
  y: number;
}
