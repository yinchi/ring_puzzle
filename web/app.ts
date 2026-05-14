import type { EndgameTable, Move, Ring } from "./types";
import { applyMove, isSolved, newRandomGame } from "./puzzle";
import { solveMoves } from "./solver";
import { buildSVG, renderBeads, animateShift, animateShiftRun, animateFlip } from "./ui";
import rawTable from "./endgame.json";

// ---- State ----

let ring: Ring = newRandomGame();
let endgameTable: EndgameTable = rawTable as EndgameTable;
let isAnimating = false;
let moveCount = 0;
let flipCount = 0;
let autoMoveCount = 0;
let autoFlipCount = 0;

// ---- DOM refs ----

const btnLeft = document.getElementById("btn-left") as HTMLButtonElement;
const btnRight = document.getElementById("btn-right") as HTMLButtonElement;
const btnFlip = document.getElementById("btn-flip") as HTMLButtonElement;
const btnNew = document.getElementById("btn-new") as HTMLButtonElement;
const btnAuto = document.getElementById("btn-auto") as HTMLButtonElement;
const statsEl = document.getElementById("stats") as HTMLElement;
const solvedBanner = document.getElementById("solved-banner") as HTMLElement;

// ---- Helpers ----

function updateButtonStates(): void {
  const solved = isSolved(ring);
  const disableMoves = solved || isAnimating;
  btnLeft.disabled = disableMoves;
  btnRight.disabled = disableMoves;
  btnFlip.disabled = disableMoves;
  btnAuto.disabled = disableMoves;
  btnNew.disabled = isAnimating;
}

function updateStats(): void {
  let text = `${moveCount} moves, ${flipCount} flips`;
  if (autoMoveCount > 0) {
    text += ` (auto: ${autoMoveCount} moves, ${autoFlipCount} flips)`;
  }
  statsEl.textContent = text;
  solvedBanner.hidden = !isSolved(ring);
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ---- Move handlers ----

async function doShift(dir: "L" | "R"): Promise<void> {
  if (isAnimating || isSolved(ring)) return;
  isAnimating = true;
  updateButtonStates();

  ring = applyMove(ring, dir);
  await animateShift(dir, ring);
  moveCount++;

  isAnimating = false;
  updateButtonStates();
  updateStats();
}

async function doFlip(): Promise<void> {
  if (isAnimating || isSolved(ring)) return;
  isAnimating = true;
  updateButtonStates();

  ring = applyMove(ring, "F");
  await animateFlip(ring);
  moveCount++;
  flipCount++;

  isAnimating = false;
  updateButtonStates();
  updateStats();
}

async function doNewGame(): Promise<void> {
  if (isAnimating) return;
  ring = newRandomGame();
  moveCount = 0;
  flipCount = 0;
  autoMoveCount = 0;
  autoFlipCount = 0;
  renderBeads(ring);
  updateButtonStates();
  updateStats();
}

async function doAutoSolve(): Promise<void> {
  if (isAnimating || isSolved(ring)) return;
  isAnimating = true;
  updateButtonStates();

  let moves: Move[];
  try {
    moves = solveMoves(ring, endgameTable);
  } catch (e) {
    console.error("Solver failed:", e);
    isAnimating = false;
    updateButtonStates();
    return;
  }

  let i = 0;
  while (i < moves.length) {
    const move = moves[i];
    if (move === "F") {
      ring = applyMove(ring, move);
      await animateFlip(ring);
      flipCount++;
      autoFlipCount++;
      moveCount++;
      autoMoveCount++;
      i++;
    } else {
      // Batch consecutive same-direction rotations into one smooth slide
      let j = i;
      while (j < moves.length && moves[j] === move) j++;
      const steps = j - i;
      for (let k = 0; k < steps; k++) ring = applyMove(ring, move);
      await animateShiftRun(move, steps, ring, () => {
        moveCount++;
        autoMoveCount++;
        updateStats();
      });
      i = j;
    }
    if (move !== "L" && move !== "R") updateStats();
    await sleep(50);
  }

  isAnimating = false;
  updateButtonStates();
  updateStats();
}

// ---- Keyboard ----

function attachKeyboard(): void {
  document.addEventListener("keydown", (e) => {
    if (e.repeat) return;
    switch (e.key) {
      case "ArrowLeft":
        e.preventDefault();
        doShift("L");
        break;
      case "ArrowRight":
        e.preventDefault();
        doShift("R");
        break;
      case "f":
      case "F":
        doFlip();
        break;
      case "n":
      case "N":
        doNewGame();
        break;
      case "a":
      case "A":
        doAutoSolve();
        break;
    }
  });
}

// ---- Buttons ----

function attachButtons(): void {
  btnLeft.addEventListener("click", () => doShift("L"));
  btnRight.addEventListener("click", () => doShift("R"));
  btnFlip.addEventListener("click", () => doFlip());
  btnNew.addEventListener("click", () => doNewGame());
  btnAuto.addEventListener("click", () => doAutoSolve());
}

// ---- Entry point ----

window.addEventListener("DOMContentLoaded", async () => {
  // Build SVG puzzle
  const container = document.getElementById("puzzle-container")!;
  buildSVG(container);

  // Initial render
  renderBeads(ring);
  updateButtonStates();
  updateStats();

  attachKeyboard();
  attachButtons();
});
