import curses
import random

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

Moves: {20}
(<-) (f)lip (->) (a)uto (n)ew (q)uit
"""

# Just the flippable portion of the ring, which we highlight in red.
FMT_RING_RED = """{0:02d} {1:02d} {2:02d} {3:02d}"""


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

    while True:
        solved = is_solved(ring)

        stdscr.clear()

        # Print the whole ring and the puzzle status
        stdscr.addstr(FMT_RING.format(*ring, moves))

        # Re-print the flippable portion of the ring in red
        stdscr.addstr(
            0, 6, FMT_RING_RED.format(*ring[:FLIP_SIZE]), curses.color_pair(1)
        )

        if solved:
            stdscr.addstr(
                7, 0, f"Solved in {moves} moves!", curses.A_BOLD | curses.color_pair(1)
            )

        # Refresh the screen to show the updates
        stdscr.refresh()

        # get user input
        key = stdscr.getch()
        if key == ord("q"):
            break
        elif key == curses.KEY_LEFT and not solved:
            # Rotate the ring to the left
            ring = ring[1:] + ring[:1]
            moves += 1
        elif key == curses.KEY_RIGHT and not solved:
            # Rotate the ring to the right
            ring = ring[-1:] + ring[:-1]
            moves += 1
        elif key == ord("f") and not solved:
            # Flip the first FLIP_SIZE elements of the ring
            ring[:FLIP_SIZE] = reversed(ring[:FLIP_SIZE])
            moves += 1
        elif key == ord("n"):
            ring = random.sample(range(1, RING_SIZE + 1), RING_SIZE)
            moves = 0
        elif key == ord("a") and not solved:
            # TODO: Implement auto-solve feature when 'a' is pressed.
            pass


def main() -> None:
    """Wrap the program in curses.wrapper to ensure proper initialization and cleanup."""
    curses.wrapper(program)
