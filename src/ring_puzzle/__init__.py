import curses
import random

from .solver import solve_moves
from .util import FLIP_SIZE, RING_SIZE, is_solved

#    20 01 02 03 04 05
#  19                  06
# 18                    07
# 17                    08
#  16                  09
#    15 14 13 12 11 10
FMT_RING = """\
   {19:02d} {0:02d} {1:02d} {2:02d} {3:02d} {4:02d}
 {18:02d}                  {5:02d}
{17:02d}                    {6:02d}
{16:02d}                    {7:02d}
 {15:02d}                  {8:02d}
   {14:02d} {13:02d} {12:02d} {11:02d} {10:02d} {9:02d}
"""

# Just the flippable portion of the ring, which we highlight in red.
FMT_RING_RED = """{0:02d} {1:02d} {2:02d} {3:02d}"""

# Delay between auto-solve steps in milliseconds.
AUTO_SOLVE_DELAY_MS = 150

# Padding (rows, columns) applied to the entire display.
PAD_TOP = 1
PAD_LEFT = 3

# Extra horizontal indent applied to ring rows only.
INDENT = 3

# Fixed display strings.
_OBJECTIVE = "Objective: arrange 1-20 in clockwise ascending order"
_LEGEND = "(<-) (f)lip (->) (a)uto (n)ew (q)uit"
_RING_LINE_WIDTH = 24  # width of the widest formatted line in FMT_RING

# Minimum terminal dimensions: top pad + objective + blank + 6 ring rows + blank + status + legend.
MIN_ROWS = PAD_TOP + 11
MIN_COLS = max(
    PAD_LEFT + len(_OBJECTIVE),
    PAD_LEFT + INDENT + _RING_LINE_WIDTH,
    PAD_LEFT + len(_LEGEND),
)


def _draw(
    stdscr: curses.window,
    ring: list[int],
    moves: int,
    auto_moves: int,
    solved: bool,
    autosolving: bool = False,
) -> None:
    """Redraw the full puzzle display."""
    # Row offsets: objective line, blank, then the ring (6 rows), blank, status, legend.
    ring_row = PAD_TOP + 2  # objective + blank line above the ring
    stdscr.clear()
    stdscr.addstr(PAD_TOP, PAD_LEFT, _OBJECTIVE)
    for i, line in enumerate(FMT_RING.format(*ring).splitlines()):
        stdscr.addstr(ring_row + i, PAD_LEFT + INDENT, line)
    stdscr.addstr(ring_row, PAD_LEFT + INDENT + 6, FMT_RING_RED.format(*ring[:FLIP_SIZE]), curses.color_pair(1))

    suffix = f" ({auto_moves} auto)" if auto_moves else ""
    if solved:
        stdscr.addstr(
            ring_row + 7, PAD_LEFT, f"Solved in {moves} moves!{suffix}", curses.A_BOLD | curses.color_pair(1)
        )
        if not autosolving:
            stdscr.addstr(ring_row + 8, PAD_LEFT, "(n)ew (q)uit")
    else:
        stdscr.addstr(ring_row + 7, PAD_LEFT, f"Moves: {moves}{suffix}")
        if not autosolving:
            stdscr.addstr(ring_row + 8, PAD_LEFT, _LEGEND)

    stdscr.refresh()


def program(stdscr: curses.window) -> None:
    """Main program loop, run inside curses.wrapper."""
    curses.start_color()
    curses.use_default_colors()
    # Hide the cursor.
    curses.curs_set(0)

    # Define a color pair (index 1) for red text on the default background.
    curses.init_pair(1, curses.COLOR_RED, -1)

    ring = random.sample(range(1, RING_SIZE + 1), RING_SIZE)
    moves = 0
    auto_moves = 0

    while True:
        rows, cols = stdscr.getmaxyx()
        if rows < MIN_ROWS or cols < MIN_COLS:
            stdscr.clear()
            try:
                stdscr.addstr(0, 0, "Terminal too small! Resize or q to quit.")
            except curses.error:
                pass
            stdscr.refresh()
            key = stdscr.getch()
            if key == ord("q"):
                break
            continue

        solved = is_solved(ring)
        _draw(stdscr, ring, moves, auto_moves, solved)

        # get user input
        key = stdscr.getch()
        if key == ord("q"):
            break
        elif key == curses.KEY_LEFT and not solved:
            ring = ring[1:] + ring[:1]
            moves += 1
        elif key == curses.KEY_RIGHT and not solved:
            ring = ring[-1:] + ring[:-1]
            moves += 1
        elif key == ord("f") and not solved:
            ring[:FLIP_SIZE] = reversed(ring[:FLIP_SIZE])
            moves += 1
        elif key == ord("n"):
            ring = random.sample(range(1, RING_SIZE + 1), RING_SIZE)
            moves = 0
            auto_moves = 0
        elif key == ord("a") and not solved:
            solution = solve_moves(ring[:])
            for move in solution:
                if move == "L":
                    ring = ring[1:] + ring[:1]
                elif move == "R":
                    ring = ring[-1:] + ring[:-1]
                elif move == "F":
                    ring[:FLIP_SIZE] = reversed(ring[:FLIP_SIZE])
                moves += 1
                auto_moves += 1
                _draw(stdscr, ring, moves, auto_moves, is_solved(ring), autosolving=True)
                curses.napms(AUTO_SOLVE_DELAY_MS)


def main() -> None:
    """Wrap the program in curses.wrapper to ensure proper initialization and cleanup."""
    curses.wrapper(program)
