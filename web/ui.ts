import type { Ring, SlotCoord } from "./types";

// ── Geometry constants ────────────────────────────────────────────────────────

const SVG_W = 700;
const SVG_H = 519;
const BEAD_D = 74;
const BEAD_R = BEAD_D / 2;
const SEMI_R = (6 * BEAD_D) / Math.PI;

const TRACK_CY = 315;
const TOP_Y = TRACK_CY - SEMI_R;
const BOT_Y = TRACK_CY + SEMI_R;

const LEFT_JX = SVG_W / 2 - 2 * BEAD_D;
const RIGHT_JX = SVG_W / 2 + 2 * BEAD_D;

const FLIP_CX = SVG_W / 2;
const FLIP_R = 2 * BEAD_D;

const INDENT_R = Math.round(FLIP_R * 0.2);
const INDENT_OFFSET = FLIP_R * 0.55; // further from track: gap ≈ 8 px

const TRACK_EXTRA = 10; // px the dark-gray band extends beyond bead outer edges

const SHIFT_DURATION = 500;
const FLIP_DURATION = 1000;

// Beads travel one slot (≈ BEAD_D px of arc) per step; cap their speed.
const MAX_BEAD_SPEED_PX_MS = 0.2; // px per ms
const RUN_STEP_DURATION = Math.round(BEAD_D / MAX_BEAD_SPEED_PX_MS);

// ── SVG path generators ───────────────────────────────────────────────────────

function racetrackPath(R: number): string {
	const ty = TRACK_CY - R;
	const by = TRACK_CY + R;
	return (
		`M ${LEFT_JX} ${ty} ` +
		`L ${RIGHT_JX} ${ty} ` +
		`A ${R} ${R} 0 0 1 ${RIGHT_JX} ${by} ` +
		`L ${LEFT_JX} ${by} ` +
		`A ${R} ${R} 0 0 1 ${LEFT_JX} ${ty} Z`
	);
}

function flipChannelPath(): string {
	const half = BEAD_R;
	const xh = Math.sqrt(FLIP_R * FLIP_R - half * half);
	return (
		`M ${FLIP_CX - xh} ${TOP_Y - half} ` +
		`L ${FLIP_CX + xh} ${TOP_Y - half} ` +
		`A ${FLIP_R} ${FLIP_R} 0 0 1 ${FLIP_CX + xh} ${TOP_Y + half} ` +
		`L ${FLIP_CX - xh} ${TOP_Y + half} ` +
		`A ${FLIP_R} ${FLIP_R} 0 0 1 ${FLIP_CX - xh} ${TOP_Y - half} Z`
	);
}

// ── Slot positions ────────────────────────────────────────────────────────────

function computeSlotPositions(): SlotCoord[] {
	const slots: SlotCoord[] = new Array(20);

	for (let i = 0; i < 4; i++) {
		slots[i] = { x: LEFT_JX + (i + 0.5) * BEAD_D, y: TOP_Y };
	}

	for (let i = 0; i < 6; i++) {
		const angle = -Math.PI / 2 + ((i + 0.5) * BEAD_D) / SEMI_R;
		slots[4 + i] = {
			x: RIGHT_JX + SEMI_R * Math.cos(angle),
			y: TRACK_CY + SEMI_R * Math.sin(angle),
		};
	}

	for (let i = 0; i < 4; i++) {
		slots[10 + i] = { x: RIGHT_JX - (i + 0.5) * BEAD_D, y: BOT_Y };
	}

	for (let i = 0; i < 6; i++) {
		const angle = Math.PI / 2 + ((i + 0.5) * BEAD_D) / SEMI_R;
		slots[14 + i] = {
			x: LEFT_JX + SEMI_R * Math.cos(angle),
			y: TRACK_CY + SEMI_R * Math.sin(angle),
		};
	}

	return slots;
}

export const SLOT_POSITIONS: SlotCoord[] = computeSlotPositions();

// ── SVG element factory ───────────────────────────────────────────────────────

const SVG_NS = "http://www.w3.org/2000/svg";
function svgEl<K extends keyof SVGElementTagNameMap>(tag: K): SVGElementTagNameMap[K] {
	return document.createElementNS(SVG_NS, tag) as SVGElementTagNameMap[K];
}

// ── Mutable refs ──────────────────────────────────────────────────────────────

let svgRoot: SVGSVGElement;
let flipperGroupEl: SVGGElement;
let indentEl: SVGCircleElement;
const beadEls: SVGGElement[] = []; // outer g — positioned by SVG transform
const beadInnerEls: SVGGElement[] = []; // inner g — counter-rotated during flip
let flipParity = 0; // 0 = indent above track, 1 = indent below

// ── Build SVG ─────────────────────────────────────────────────────────────────

export function buildSVG(container: HTMLElement): void {
	svgRoot = svgEl("svg");
	svgRoot.setAttribute("viewBox", `0 0 ${SVG_W} ${SVG_H}`);
	svgRoot.setAttribute("width", "100%");
	svgRoot.style.maxWidth = `${SVG_W}px`;
	svgRoot.style.display = "block";
	svgRoot.style.margin = "0 auto";

	// 1. Outer frame (light gray) — bottom layer, frames the entire mechanism
	const outerFrame = svgEl("path");
	outerFrame.setAttribute("d", racetrackPath(SEMI_R + BEAD_R + TRACK_EXTRA));
	outerFrame.setAttribute("fill", "#c8c8c8");
	svgRoot.appendChild(outerFrame);

	// 1b. Flip circle frame (light gray) — same extra width, not rotated
	const flipFrame = svgEl("circle");
	flipFrame.setAttribute("cx", String(FLIP_CX));
	flipFrame.setAttribute("cy", String(TOP_Y));
	flipFrame.setAttribute("r", String(FLIP_R + TRACK_EXTRA));
	flipFrame.setAttribute("fill", "#c8c8c8");
	svgRoot.appendChild(flipFrame);

	// 2. Dark gray track — original size, tangent to outer bead edges
	const outerTrack = svgEl("path");
	outerTrack.setAttribute("d", racetrackPath(SEMI_R + BEAD_R));
	outerTrack.setAttribute("fill", "#555");
	svgRoot.appendChild(outerTrack);

	// 3. Inner fill (light gray), tangent to inner bead edges
	const innerFill = svgEl("path");
	innerFill.setAttribute("d", racetrackPath(SEMI_R - BEAD_R));
	innerFill.setAttribute("fill", "#c8c8c8");
	svgRoot.appendChild(innerFill);

	// 3. Flipper group (purple disc + dark indent; rotates 180 on each flip)
	flipperGroupEl = svgEl("g");
	flipperGroupEl.id = "flipper-group";
	// Explicit px origin so bounding-box changes (when beads join) don't shift the pivot
	flipperGroupEl.style.setProperty("transform-origin", `${FLIP_CX}px ${TOP_Y}px`);
	flipperGroupEl.style.transform = "rotate(0deg)"; // always reset to 0 between flips

	const flipDisc = svgEl("circle");
	flipDisc.setAttribute("cx", String(FLIP_CX));
	flipDisc.setAttribute("cy", String(TOP_Y));
	flipDisc.setAttribute("r", String(FLIP_R));
	flipDisc.setAttribute("fill", "#7b5ea7");
	flipDisc.setAttribute("stroke", "#9b7ec8");
	flipDisc.setAttribute("stroke-width", "2");
	flipperGroupEl.appendChild(flipDisc);

	// Indent starts above track; cy toggled in animateFlip to track parity
	indentEl = svgEl("circle");
	indentEl.setAttribute("cx", String(FLIP_CX));
	indentEl.setAttribute("cy", String(TOP_Y - INDENT_OFFSET));
	indentEl.setAttribute("r", String(INDENT_R));
	indentEl.setAttribute("fill", "#624783");
	flipperGroupEl.appendChild(indentEl);

	// 4. Track channel through flip disc (dark purple) — inside group so it rotates too
	const channel = svgEl("path");
	channel.setAttribute("d", flipChannelPath());
	channel.setAttribute("fill", "#4a3068");
	channel.setAttribute("stroke", "#4a3068");
	channel.setAttribute("stroke-width", "2");
	flipperGroupEl.appendChild(channel);

	svgRoot.appendChild(flipperGroupEl);

	// 5 & 6. Beads: non-flip zone first, flip zone on top
	const renderOrder = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 0, 1, 2, 3];
	for (const slot of renderOrder) {
		const g = svgEl("g");
		g.setAttribute("class", "bead");
		g.dataset.slot = String(slot);
		const { x, y } = SLOT_POSITIONS[slot];
		g.setAttribute("transform", `translate(${x},${y})`);

		// Inner g — counter-rotated during flip so labels stay upright
		const inner = svgEl("g");
		inner.style.setProperty("transform-box", "fill-box");
		inner.style.setProperty("transform-origin", "50% 50%");

		const circle = svgEl("circle");
		circle.setAttribute("r", String(BEAD_R - 1));
		circle.setAttribute("fill", "#FFD700");
		circle.setAttribute("stroke", "none");

		const text = svgEl("text");
		text.setAttribute("text-anchor", "middle");
		text.setAttribute("dominant-baseline", "central");
		text.setAttribute("font-size", "27");
		text.setAttribute("font-weight", "bold");
		text.setAttribute("fill", "#222");
		text.setAttribute("pointer-events", "none");
		text.textContent = "?";

		inner.appendChild(circle);
		inner.appendChild(text);
		g.appendChild(inner);
		beadEls[slot] = g;
		beadInnerEls[slot] = inner;
		svgRoot.appendChild(g);
	}

	container.appendChild(svgRoot);
}

// ── Render ────────────────────────────────────────────────────────────────────

export function renderBeads(ring: Ring): void {
	for (let slot = 0; slot < 20; slot++) {
		const text = beadEls[slot].querySelector("text")!;
		text.textContent = String(ring[slot]);
	}
}

// ── Animation helpers ─────────────────────────────────────────────────────────

function waitTransitionEnd(el: Element): Promise<void> {
	return new Promise((resolve) => {
		el.addEventListener("transitionend", () => resolve(), { once: true });
	});
}

function setBeadTranslate(slot: number, x: number, y: number, transition: string): void {
	const g = beadEls[slot];
	g.style.transition = transition;
	g.setAttribute("transform", `translate(${x},${y})`);
}

function resetBeadTranslate(slot: number): void {
	const g = beadEls[slot];
	g.style.transition = "none";
	const { x, y } = SLOT_POSITIONS[slot];
	g.setAttribute("transform", `translate(${x},${y})`);
}

// ── Animate shift ─────────────────────────────────────────────────────────────

/**
 * Animate `steps` consecutive same-direction rotations, one slot at a time,
 * but with easing split across the run (ease-in → linear → ease-out) so the
 * whole sequence reads as one smooth motion without per-step deceleration.
 */
export async function animateShiftRun(
	direction: "L" | "R",
	steps: number,
	ring: Ring,
	onStep?: () => void,
): Promise<void> {
	// Apply all ring mutations up front; we'll re-render only at the very end
	// (ring is already in its final state when passed in)
	const delta = direction === "L" ? -1 : 1;

	// We need the intermediate ring states to render at each step,
	// but since ring is final we reconstruct from SLOT_POSITIONS only.
	// Track current logical positions of each bead (indices into SLOT_POSITIONS).
	const pos = Array.from({ length: 20 }, (_, i) => i); // pos[slot] = current visual slot

	for (let step = 0; step < steps; step++) {
		const isFirst = step === 0;
		const isLast = step === steps - 1;
		const easing =
			steps === 1 ? "ease-in-out" : isFirst ? "ease-in" : isLast ? "ease-out" : "linear";
		const duration = steps === 1 ? SHIFT_DURATION : RUN_STEP_DURATION;
		const transition = `transform ${duration}ms ${easing}`;

		for (let slot = 0; slot < 20; slot++) {
			const target = (((pos[slot] + delta) % 20) + 20) % 20;
			const { x, y } = SLOT_POSITIONS[target];
			setBeadTranslate(slot, x, y, transition);
			pos[slot] = target;
		}

		await waitTransitionEnd(beadEls[0]);
		onStep?.();

		if (!isLast) {
			// Snap each bead to its current visual slot before the next step
			for (let slot = 0; slot < 20; slot++) {
				const g = beadEls[slot];
				g.style.transition = "none";
				const { x, y } = SLOT_POSITIONS[pos[slot]];
				g.setAttribute("transform", `translate(${x},${y})`);
			}
		}
	}

	for (let slot = 0; slot < 20; slot++) resetBeadTranslate(slot);
	renderBeads(ring);
}

export async function animateShift(direction: "L" | "R", ring: Ring): Promise<void> {
	const transition = `transform ${SHIFT_DURATION}ms ease-in-out`;
	const delta = direction === "L" ? -1 : 1;

	for (let slot = 0; slot < 20; slot++) {
		const target = (((slot + delta) % 20) + 20) % 20;
		const { x, y } = SLOT_POSITIONS[target];
		setBeadTranslate(slot, x, y, transition);
	}

	await waitTransitionEnd(beadEls[0]);

	for (let slot = 0; slot < 20; slot++) resetBeadTranslate(slot);
	renderBeads(ring);
}

// ── Animate flip ──────────────────────────────────────────────────────────────

export async function animateFlip(ring: Ring): Promise<void> {
	// The group is always at rotate(0deg) between flips, so there is no
	// position jump when beads are re-parented into it.
	for (let slot = 0; slot < 4; slot++) {
		flipperGroupEl.appendChild(beadEls[slot]);
	}

	// Set a clear start state for all transitions
	for (let slot = 0; slot < 4; slot++) {
		beadInnerEls[slot].style.transition = "none";
		beadInnerEls[slot].style.transform = "rotate(0deg)";
	}
	flipperGroupEl.style.transition = "none";
	flipperGroupEl.style.transform = "rotate(0deg)";
	void flipperGroupEl.getBoundingClientRect(); // flush

	// Animate: group 0->180, inner gs 0->-180 so labels stay upright
	const t = `transform ${FLIP_DURATION}ms ease-in-out`;
	flipperGroupEl.style.transition = t;
	flipperGroupEl.style.transform = "rotate(180deg)";
	for (let slot = 0; slot < 4; slot++) {
		beadInnerEls[slot].style.transition = t;
		beadInnerEls[slot].style.transform = "rotate(-180deg)";
	}

	await waitTransitionEnd(flipperGroupEl);

	// Sync block (one browser render):
	//  1. Snap group back to rotate(0deg) — always, every flip
	//  2. Toggle indent cy to reflect parity
	//  3. Clear inner-g counter-rotations
	//  4. Update bead labels
	//  5. Snap beads to canonical slots, re-parent to svgRoot
	flipperGroupEl.style.transition = "none";
	flipperGroupEl.style.transform = "rotate(0deg)";

	flipParity = 1 - flipParity;
	indentEl.setAttribute(
		"cy",
		String(flipParity === 1 ? TOP_Y + INDENT_OFFSET : TOP_Y - INDENT_OFFSET),
	);

	for (let slot = 0; slot < 4; slot++) {
		beadInnerEls[slot].style.transition = "none";
		beadInnerEls[slot].style.transform = "";
	}
	renderBeads(ring);
	for (let slot = 0; slot < 4; slot++) {
		const g = beadEls[slot];
		g.style.transition = "none";
		const { x, y } = SLOT_POSITIONS[slot];
		g.setAttribute("transform", `translate(${x},${y})`);
		svgRoot.appendChild(g);
	}
}
