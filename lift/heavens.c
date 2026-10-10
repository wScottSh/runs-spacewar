/* The heavens (source lines 510-621, 629-653 and 1373-1866): the central
 * star, and Peter Samson's Expensive Planetarium, the background of real
 * stars that drifts slowly across the screen.
 *
 * The central star (the "sun") is a short line drawn from the center of the
 * screen in a random direction, then mirrored through the center. A new
 * direction and length every frame make it spin and flicker.
 *
 * The Expensive Planetarium shows the stars of a catalog, in four
 * magnitudes, through a window one screen wide that moves slowly right to
 * left across the sky. It draws every other frame, and moves the window one
 * step every 16 of those. */

#include "random.h"
#include "star_vector.h"

/* ---------------------------------------------------------- central star */

/* The slope of the star's line: how far each dot moves along x and along
 * y. Each is the sign and the three bits just below a display coordinate,
 * so a dot moves less than one point. */
#define slope_x star_vector_x
#define slope_y star_vector_y

#define SLOPE_BITS 0400340      /* the source writes it `add 340` */

JSP void star_line(void);

JSP void central_star(void)  /* blp */
{
    word slope;

    if (sense(6))               /* sense switch 6 turns the star off */
        return;
    slope = next_random();
    slope = rar(slope, 9) & SLOPE_BITS;
    if (slope < 0)
        slope = slope ^ 0377777;    /* a proper ones' complement negative number */
    slope_x = slope;
    slope = ral(random_number, 4) & SLOPE_BITS;
    if (slope < 0)
        slope = slope ^ 0377777;
    slope_y = slope;
    star_line();
    ioh();                      /* wait for the last dot */
}

/* One dot of the star's line (the `starp` macro): move the pen by the
 * slope, wait for the last dot, plot this one. Only AC adds, so y is
 * exchanged into AC to step it, and back. */
static inline dword line_step(word x, register word y)
{
    x = x + slope_x;
    rcl(x, y, 18);              /* exchange: x holds y, y holds x */
    x = x + slope_y;
    rcl(x, y, 18);              /* and back */
    ioh();
    dpy_nowait(x, y);
    return (dword){ x, y };
}

/* Where the line starts, held in the jump into the line (Duff's device):
 * entering at case k draws 16 - k dots. */
HOMED word line_dots_skipped;

/* Draw the line out from the center, 9 to 16 dots long, then the same
 * line mirrored through the center. Flag 6 says the mirror is drawn. */
JSP void star_line(void)
{
    word skipped;
    dword pen;

    skipped = next_random() >> 14;      /* -7..7 */
    if (skipped < 0)
        skipped = -skipped;
    line_dots_skipped = skipped;
    pen.hi = 0, pen.lo = 0, clf(6);     /* the pen at the center */
    dpy_nowait(pen.hi, pen.lo);
    for (;;) {
        switch ((int)line_dots_skipped) {
        case 0: pen = line_step(pen.hi, pen.lo);
        case 1: pen = line_step(pen.hi, pen.lo);
        case 2: pen = line_step(pen.hi, pen.lo);
        case 3: pen = line_step(pen.hi, pen.lo);
        case 4: pen = line_step(pen.hi, pen.lo);
        case 5: pen = line_step(pen.hi, pen.lo);
        case 6: pen = line_step(pen.hi, pen.lo);
        case 7:
            for (int i = 0; i < 9; i++)
                pen = line_step(pen.hi, pen.lo);
        }
        if (flag(6))
            return;
        stf(6);                         /* mirror the end of the line through the center */
        pen.hi = -pen.hi;
        rcl(pen.hi, pen.lo, 18);
        pen.hi = -pen.hi;
        rcl(pen.hi, pen.lo, 18);
    }
}

/* ------------------------------------------------- Expensive Planetarium */

/* The star catalog (lift/star_catalog.c): four tables of stars, one per magnitude. */
extern word first_magnitude[2 * 9];
extern word second_magnitude[2 * 9];
extern word third_magnitude[2 * 81];
extern word fourth_magnitude[2 * 370];

extern word right_margin;       /* the sky's x at the right edge of the screen */

/* The display of the stars of one magnitude (the `dislis` macro), a
 * function laid out in place for each magnitude: MAGNITUDE(m, stars,
 * count, intensity) defines display_magnitude_m for the count stars of the
 * table stars, plotted at the intensity (3 is the brightest).
 *
 * The sky is 020000 wide and wraps around; a table runs right to left. The
 * window is the screen's width, 02000, left of right_margin, which moves
 * left. A scan starts at the cursor and plots each star in the window. It
 * stops at the first star outside the window once it has plotted one, or
 * when it has gone all the way round. A star outside the window before any
 * is plotted moves the cursor past it, so later scans skip it; flag 5 says
 * a star was plotted this frame. */
#define MAGNITUDE(m, stars, count, intensity)                                   \
HOMED const word *star_x##m = 0;        /* the x of the star looked at */       \
HOMED const word *star_y##m = 0;        /* its y */                             \
const word *cursor##m = stars;          /* the first star to look at */         \
insn scan_start##m = I_LIO(0);          /* `lio` the star this scan began at */ \
                                                                                \
static inline void display_magnitude_##m(void)                                  \
{                                                                               \
    word x;                                                                     \
    register word y;                                                            \
                                                                                \
    clf(5);                                                                     \
    scan_start##m.addr = cursor##m;                                             \
    star_x##m = cursor##m;                                                      \
    star_y##m = cursor##m;                                                      \
    ++star_y##m;                                                                \
next_star:                                                                      \
    x = *home(star_x##m) - right_margin;                                        \
    if (x >= 0)                                                                 \
        goto right_of_window;                                                   \
    x = x + 02000;                      /* from the window's left edge */       \
left_edge:                                                                      \
    if (x <= 0)                                                                 \
        goto outside_window;                                                    \
    x = (x - 01000) << 8;               /* to a display coordinate */           \
    y = *home(star_y##m);                                                       \
    dpy(x, y, intensity);                                                       \
    stf(5);                                                                     \
advance:                                                                        \
    if (I_LIO(++star_y##m) == I_LIO(stars + 2 * (count)))                       \
        goto wrap;                                                              \
    if (I_LIO(star_y##m) == scan_start##m)                                      \
        goto done;                      /* all the way round */                 \
    star_x##m = star_y##m;                                                      \
    ++star_y##m;                                                                \
    goto next_star;                                                             \
                                                                                \
right_of_window:                        /* round the sky, then test again */    \
    x = x + (02000 - 020000);                                                   \
    goto left_edge;                                                             \
                                                                                \
outside_window:                                                                 \
    if (flag(5))                                                                \
done:   return;                         /* past the window's stars */           \
    ++cursor##m;                        /* none plotted yet: the next scan */   \
    ++cursor##m;                        /* starts after this star */            \
    if (cursor##m != stars + 2 * (count))                                       \
        goto advance;                                                           \
    cursor##m = stars;                                                          \
    goto advance;                                                               \
                                                                                \
wrap:                                   /* past the last star: the first */     \
    if (I_LIO(stars) == scan_start##m)                                          \
        goto done;                                                              \
    star_x##m = stars;                                                          \
    star_y##m = stars + 1;                                                      \
    goto next_star;                                                             \
    PLACE(scan_start##m, cursor##m);                                            \
}

MAGNITUDE(1, first_magnitude, 9, 3)
MAGNITUDE(2, second_magnitude, 9, 2)
MAGNITUDE(3, third_magnitude, 81, 1)
MAGNITUDE(4, fourth_magnitude, 370, 0)

extern word alternate_frames;
extern word window_steps;

/* The Expensive Planetarium, called each frame (the `background` macro). */
JSP void expensive_planetarium(void)  /* bck */
{
    word margin;

    if (sense(4))               /* sense switch 4 turns the heavens off */
        return;
    if (++alternate_frames < 0)
finished:
        return;
    alternate_frames = -2;
    display_magnitude_1();
    display_magnitude_2();
    display_magnitude_3();
    display_magnitude_4();
    if (++window_steps < 0)
        goto finished;
    window_steps = -020;
    margin = -1 + right_margin;         /* move the window one step left */
    if (margin < 0)
        margin = margin + 020000;
    right_margin = margin;
    goto finished;
}

word alternate_frames = 0;      /* counts up to draw every other frame */
word window_steps = 0;          /* counts up to move the window every 16th */
word right_margin = 010000;
