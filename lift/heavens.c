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

extern word random_number SYM("ran");

/* The random number generator (the `random` macro): the next value of
 * random_number, also left in AC. */
static inline word next_random(void)
{
    random_number = (rar(random_number, 1) ^ 0355670) + 0355670;
    return random_number;
}

/* ---------------------------------------------------------- central star */

/* The slope of the star's line: how far each dot moves along x and along
 * y. Each is the sign and the three bits just below a display coordinate,
 * so a dot moves less than one point. */
POOL word slope_x SYM("bx");
POOL word slope_y SYM("by");

#define SLOPE_BITS 0400340      /* the source writes it `add 340` */

JSP void star_line(void);

JSP SYM("blp") void central_star(void)
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

REGION_BREAK();

/* ------------------------------------------------- Expensive Planetarium */

/* The star catalog, below: four tables of stars, one per magnitude. */
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
JSP SYM("bck") void expensive_planetarium(void)
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

REGION_BREAK();

/* ------------------------------------------------------- the star catalog
 * Stars by Peter Samson for Spacewar 2b. STAR(x, y) is a star at right
 * ascension x, in 1/8192 of a turn, and declination y, in display points:
 * the table holds 8192 - x, so stars of increasing x run right to left,
 * and y in the high bits of its word, where the display reads it. Each
 * star's comment is its catalog number, constellation and name. */
#define STAR(x, y) 8192 - (x), (y) * 256

AT(06077) word first_magnitude[2 * 9] = {
    STAR(1537,  371),     /* 87 Taur, Aldebaran */
    STAR(1762, -189),     /* 19 Orio, Rigel */
    STAR(1990,  168),     /* 58 Orio, Betelgeuze */
    STAR(2280, -377),     /* 9 CMaj, Sirius */
    STAR(2583,  125),     /* 10 CMin, Procyon */
    STAR(3431,  283),     /* 32 Leon, Regulus */
    STAR(4551, -242),     /* 67 Virg, Spica */
    STAR(4842,  448),     /* 16 Boot, Arcturus */
    STAR(6747,  196),     /* 53 Aqil, Altair */
};

word second_magnitude[2 * 9] = {
    STAR(1819,  143),     /* 24 Orio, Bellatrix */
    STAR(1884,  -29),     /* 46 Orio */
    STAR(1910,  -46),     /* 50 Orio */
    STAR(1951, -221),     /* 53 Orio */
    STAR(2152, -407),     /* 2 CMaj */
    STAR(2230,  375),     /* 24 Gemi */
    STAR(3201, -187),     /* 30 Hyda, Alphard */
    STAR(4005,  344),     /* 94 Leon, Denebola */
    STAR(5975,  288),     /* 55 Ophi */
};

word third_magnitude[2 * 81] = {
    STAR(  46,  333),     /* 88 Pegs, Algenib */
    STAR( 362, -244),     /* 31 Ceti */
    STAR( 490,  338),     /* 99 Pisc */
    STAR( 566, -375),     /* 52 Ceti */
    STAR( 621,  462),     /* 6 Arie */
    STAR( 764,  -78),     /* 68 Ceti, Mira */
    STAR( 900,   64),     /* 86 Ceti */
    STAR(1007,   84),     /* 92 Ceti */
    STAR(1243, -230),     /* 23 Erid */
    STAR(1328, -314),     /* 34 Erid */
    STAR(1495,  432),     /* 74 Taur */
    STAR(1496,  356),     /* 78 Taur */
    STAR(1618,  154),     /* 1 Orio */
    STAR(1644,   52),     /* 8 Orio */
    STAR(1723, -119),     /* 67 Erid */
    STAR(1755, -371),     /* 5 Leps */
    STAR(1779, -158),     /* 20 Orio */
    STAR(1817,  -57),     /* 28 Orio */
    STAR(1843, -474),     /* 9 Leps */
    STAR(1860,   -8),     /* 34 Orio */
    STAR(1868, -407),     /* 11 Leps */
    STAR(1875,  225),     /* 39 Orio */
    STAR(1880, -136),     /* 44 Orio */
    STAR(1887,  480),     /* 123 Taur */
    STAR(1948, -338),     /* 14 Leps */
    STAR(2274,  296),     /* 31 Gemi */
    STAR(2460,  380),     /* 54 Gemi */
    STAR(2470,  504),     /* 55 Gemi */
    STAR(2513,  193),     /* 3 CMin */
    STAR(2967,  154),     /* 11 Hyda */
    STAR(3016,  144),     /* 16 Hyda */
    STAR(3424,  393),     /* 30 Leon */
    STAR(3496,  463),     /* 41 Leon, Algieba */
    STAR(3668, -357),     /* nu Hyda */
    STAR(3805,  479),     /* 68 Leon */
    STAR(3806,  364),     /* 10 Leon */
    STAR(4124, -502),     /* 2 Corv */
    STAR(4157, -387),     /* 4 Corv */
    STAR(4236, -363),     /* 7 Corv */
    STAR(4304,  -21),     /* 29 Virg */
    STAR(4384,   90),     /* 43 Virg */
    STAR(4421,  262),     /* 47 Virg */
    STAR(4606,   -2),     /* 79 Virg */
    STAR(4721,  430),     /* 8 Boot */
    STAR(5037, -356),     /* 9 Libr */
    STAR(5186, -205),     /* 27 Libr */
    STAR(5344,  153),     /* 24 Serp */
    STAR(5357,  358),     /* 28 Serp */
    STAR(5373,  -71),     /* 32 Serp */
    STAR(5430, -508),     /* 7 Scor */
    STAR(5459, -445),     /* 8 Scor */
    STAR(5513,  -78),     /* 1 Ophi */
    STAR(5536, -101),     /* 2 Ophi */
    STAR(5609,  494),     /* 27 Herc */
    STAR(5641, -236),     /* 13 Ophi */
    STAR(5828, -355),     /* 35 Ophi */
    STAR(5860,  330),     /* 64 Herc */
    STAR(5984, -349),     /* 55 Serp */
    STAR(6047,   63),     /* 62 Ophi */
    STAR(6107, -222),     /* 64 Ophi */
    STAR(6159,  217),     /* 72 Ophi */
    STAR(6236,  -66),     /* 58 Serp */
    STAR(6439, -483),     /* 37 Sgtr */
    STAR(6490,  312),     /* 17 Aqil */
    STAR(6491, -115),     /* 16 Aqil */
    STAR(6507, -482),     /* 41 Sgtr */
    STAR(6602,   66),     /* 30 Aqil */
    STAR(6721,  236),     /* 50 Aqil */
    STAR(6794,  437),     /* 12 Sgte */
    STAR(6862,  -25),     /* 65 Aqil */
    STAR(6914, -344),     /* 9 Capr */
    STAR(7014,  324),     /* 6 Dlph */
    STAR(7318, -137),     /* 22 Aqar */
    STAR(7391,  214),     /* 8 Pegs */
    STAR(7404, -377),     /* 49 Capr */
    STAR(7513,  -18),     /* 34 Aqar */
    STAR(7539,  130),     /* 26 Pegs */
    STAR(7644,  -12),     /* 55 Aqar */
    STAR(7717,  235),     /* 42 Pegs */
    STAR(7790, -372),     /* 76 Aqar */
    STAR(7849,  334),     /* 54 Pegs, Markab */
};

word fourth_magnitude[2 * 370] = {
    STAR(   1, -143),     /* 33 Pisc */
    STAR(  54,  447),     /* 89 Pegs */
    STAR(  54, -443),     /* 7 Ceti */
    STAR(  82, -214),     /* 8 Ceti */
    STAR( 223, -254),     /* 17 Ceti */
    STAR( 248,  160),     /* 63 Pisc */
    STAR( 273,  -38),     /* 20 Ceti */
    STAR( 329,  167),     /* 71 Pisc */
    STAR( 376,  467),     /* 84 Pisc */
    STAR( 450, -198),     /* 45 Ceti */
    STAR( 548,  113),     /* 106 Pisc */
    STAR( 570,  197),     /* 110 Pisc */
    STAR( 595, -255),     /* 53 Ceti */
    STAR( 606, -247),     /* 55 Ceti */
    STAR( 615,  428),     /* 5 Arie */
    STAR( 617,   61),     /* 14 Pisc */
    STAR( 656, -491),     /* 59 Ceti */
    STAR( 665,   52),     /* 113 Pisc */
    STAR( 727,  191),     /* 65 Ceti */
    STAR( 803, -290),     /* 72 Ceti */
    STAR( 813,  182),     /* 73 Ceti */
    STAR( 838, -357),     /* 76 Ceti */
    STAR( 878,   -2),     /* 82 Ceti */
    STAR( 907, -340),     /* 89 Ceti */
    STAR( 908,  221),     /* 87 Ceti */
    STAR( 913, -432),     /* 1 Erid */
    STAR( 947, -487),     /* 2 Erid */
    STAR( 976, -212),     /* 3 Erid */
    STAR( 992,  194),     /* 91 Ceti */
    STAR(1058,  440),     /* 57 Arie */
    STAR(1076,  470),     /* 58 Arie */
    STAR(1087, -209),     /* 13 Erid */
    STAR(1104,   68),     /* 96 Ceti */
    STAR(1110, -503),     /* 16 Erid */
    STAR(1135,  198),     /* 1 Taur */
    STAR(1148,  214),     /* 2 Taur */
    STAR(1168,  287),     /* 5 Taur */
    STAR(1170, -123),     /* 17 Erid */
    STAR(1185, -223),     /* 18 Erid */
    STAR(1191, -500),     /* 19 Erid */
    STAR(1205,    2),     /* 10 Taur */
    STAR(1260, -283),     /* 26 Erid */
    STAR(1304,  -74),     /* 32 Erid */
    STAR(1338,  278),     /* 35 Taur */
    STAR(1353,  130),     /* 38 Taur */
    STAR(1358,  497),     /* 37 Taur */
    STAR(1405, -162),     /* 38 Erid */
    STAR(1414,  205),     /* 47 Taur */
    STAR(1423,  197),     /* 49 Taur */
    STAR(1426, -178),     /* 40 Erid */
    STAR(1430,  463),     /* 50 Taur */
    STAR(1446,  350),     /* 54 Taur */
    STAR(1463,  394),     /* 61 Taur */
    STAR(1470,  392),     /* 64 Taur */
    STAR(1476,  502),     /* 65 Taur */
    STAR(1477,  403),     /* 68 Taur */
    STAR(1483,  350),     /* 71 Taur */
    STAR(1485,  330),     /* 73 Taur */
    STAR(1495,  358),     /* 77 Taur */
    STAR(1507,  364),     /*  */
    STAR(1518,   -6),     /* 45 Erid */
    STAR(1526,  333),     /* 86 Taur */
    STAR(1537,  226),     /* 88 Taur */
    STAR(1544,  -81),     /* 48 Erid */
    STAR(1551,  280),     /* 90 Taur */
    STAR(1556,  358),     /* 92 Taur */
    STAR(1557, -330),     /* 53 Erid */
    STAR(1571, -452),     /* 54 Erid */
    STAR(1596,  -78),     /* 57 Erid */
    STAR(1622,  199),     /* 2 Orio */
    STAR(1626,  124),     /* 3 Orio */
    STAR(1638, -128),     /* 61 Erid */
    STAR(1646,  228),     /* 7 Orio */
    STAR(1654,  304),     /* 9 Orio */
    STAR(1669,   36),     /* 10 Orio */
    STAR(1680, -289),     /* 64 Erid */
    STAR(1687, -167),     /* 65 Erid */
    STAR(1690, -460),     /*  */
    STAR(1690,  488),     /* 102 Taur */
    STAR(1700,  347),     /* 11 Orio */
    STAR(1729,  352),     /* 15 Orio */
    STAR(1732, -202),     /* 69 Erid */
    STAR(1750, -273),     /* 3 Leps */
    STAR(1753,   63),     /* 17 Orio */
    STAR(1756, -297),     /* 4 Leps */
    STAR(1792, -302),     /* 6 Leps */
    STAR(1799, -486),     /*  */
    STAR(1801,  -11),     /* 22 Orio */
    STAR(1807,   79),     /* 23 Orio */
    STAR(1816, -180),     /* 29 Orio */
    STAR(1818,   40),     /* 25 Orio */
    STAR(1830,  497),     /* 114 Taur */
    STAR(1830,   69),     /* 30 Orio */
    STAR(1851,  134),     /* 32 Orio */
    STAR(1857,  421),     /* 119 Taur */
    STAR(1861, -168),     /* 36 Orio */
    STAR(1874,  214),     /* 37 Orio */
    STAR(1878, -138),     /*  */
    STAR(1880, -112),     /* 42 Orio */
    STAR(1885,  210),     /* 40 Orio */
    STAR(1899,  -60),     /* 48 Orio */
    STAR(1900,   93),     /* 47 Orio */
    STAR(1900, -165),     /* 49 Orio */
    STAR(1909,  375),     /* 126 Taur */
    STAR(1936, -511),     /* 13 Leps */
    STAR(1957,  287),     /* 134 Taur */
    STAR(1974, -475),     /* 15 Leps */
    STAR(1982,  461),     /* 54 Orio */
    STAR(2002, -323),     /* 16 Leps */
    STAR(2020,  -70),     /*  */
    STAR(2030,  220),     /* 61 Orio */
    STAR(2032, -241),     /* 3 Mono */
    STAR(2037,  458),     /* 62 Orio */
    STAR(2057, -340),     /* 18 Leps */
    STAR(2059,  336),     /* 67 Orio */
    STAR(2084,  368),     /* 69 Orio */
    STAR(2084,  324),     /* 70 Orio */
    STAR(2105, -142),     /* 5 Mono */
    STAR(2112, -311),     /*  */
    STAR(2153,  106),     /* 8 Mono */
    STAR(2179,  462),     /* 18 Gemi */
    STAR(2179, -107),     /* 10 Mono */
    STAR(2184, -159),     /* 11 Mono */
    STAR(2204,  168),     /* 13 Mono */
    STAR(2232, -436),     /* 7 CMaj */
    STAR(2239, -413),     /* 8 CMaj */
    STAR(2245, -320),     /*  */
    STAR(2250,  227),     /* 15 Mono */
    STAR(2266,  303),     /* 30 Gemi */
    STAR(2291,   57),     /* 18 Mono */
    STAR(2327,  303),     /* 38 Gemi */
    STAR(2328, -457),     /* 15 CMaj */
    STAR(2330, -271),     /* 14 CMaj */
    STAR(2340, -456),     /* 19 CMaj */
    STAR(2342, -385),     /* 20 CMaj */
    STAR(2378,  -93),     /* 19 Mono */
    STAR(2379,  471),     /* 43 Gemi */
    STAR(2385, -352),     /* 23 CMaj */
    STAR(2428,   -8),     /* 22 Mono */
    STAR(2491, -429),     /*  */
    STAR(2519,  208),     /* 4 CMin */
    STAR(2527,  278),     /* 6 CMin */
    STAR(2559, -503),     /*  */
    STAR(2597, -212),     /* 26 Mono */
    STAR(2704, -412),     /*  */
    STAR(2709,  -25),     /* 28 Mono */
    STAR(2714,   60),     /*  */
    STAR(2751,  -61),     /* 29 Mono */
    STAR(2757, -431),     /* 16 Pupp */
    STAR(2768, -288),     /* 19 Pupp */
    STAR(2794,  216),     /* 17 Canc */
    STAR(2848,  -82),     /*  */
    STAR(2915,  138),     /* 4 Hyda */
    STAR(2921,   84),     /* 5 Hyda */
    STAR(2942, -355),     /* 9 Hyda */
    STAR(2944,  497),     /* 43 Canc */
    STAR(2947,   85),     /* 7 Hyda */
    STAR(2951, -156),     /*  */
    STAR(2953,  421),     /* 47 Canc */
    STAR(2968, -300),     /* 12 Hyda */
    STAR(2976,  141),     /* 13 Hyda */
    STAR(3032,  279),     /* 65 Canc */
    STAR(3124,   62),     /* 22 Hyda */
    STAR(3157, -263),     /* 26 Hyda */
    STAR(3161, -208),     /* 27 Hyda */
    STAR(3209,  -53),     /* 31 Hyda */
    STAR(3225,  -17),     /* 32 Hyda */
    STAR(3261,  116),     /*  */
    STAR(3270,  -16),     /* 35 Hyda */
    STAR(3274, -316),     /* 38 Hyda */
    STAR(3276,  236),     /* 14 Leon */
    STAR(3338, -327),     /* 39 Hyda */
    STAR(3385,  194),     /* 29 Leon */
    STAR(3415, -286),     /* 40 Hyda */
    STAR(3428,  239),     /* 31 Leon */
    STAR(3429,    3),     /* 15 Sext */
    STAR(3446, -270),     /* 41 Hyda */
    STAR(3495,  455),     /* 40 Leon */
    STAR(3534, -372),     /* 42 Hyda */
    STAR(3557,   -3),     /* 30 Sext */
    STAR(3570,  223),     /* 47 Leon */
    STAR(3726, -404),     /* al Crat */
    STAR(3736,  -44),     /* 61 Leon */
    STAR(3738,  471),     /* 60 Leon */
    STAR(3754,  179),     /* 63 Leon */
    STAR(3793, -507),     /* 11 Crat */
    STAR(3821,  -71),     /* 74 Leon */
    STAR(3836, -324),     /* 12 Crat */
    STAR(3846,  150),     /* 77 Leon */
    STAR(3861,  252),     /* 78 Leon */
    STAR(3868, -390),     /* 15 Crat */
    STAR(3935, -211),     /* 21 Crat */
    STAR(3936,   -6),     /* 91 Leon */
    STAR(3981, -405),     /* 27 Crat */
    STAR(3986,  161),     /* 3 Virg */
    STAR(3998,  473),     /* 93 Leon */
    STAR(4013,   53),     /* 5 Virg */
    STAR(4072,  163),     /* 8 Virg */
    STAR(4097,  211),     /* 9 Virg */
    STAR(4180,   -3),     /* 15 Virg */
    STAR(4185,  418),     /* 11 Coma */
    STAR(4249, -356),     /* 8 Corv */
    STAR(4290, -170),     /* 26 Virg */
    STAR(4305,  245),     /* 30 Virg */
    STAR(4376, -205),     /* 40 Virg */
    STAR(4403,  409),     /* 36 Coma */
    STAR(4465, -114),     /* 51 Virg */
    STAR(4466,  411),     /* 42 Coma */
    STAR(4512, -404),     /* 61 Virg */
    STAR(4563, -352),     /* 69 Virg */
    STAR(4590, -131),     /* 74 Virg */
    STAR(4603,   95),     /* 78 Virg */
    STAR(4679,  409),     /* 4 Boot */
    STAR(4691,  371),     /* 5 Boot */
    STAR(4759,   46),     /* 93 Virg */
    STAR(4820,   66),     /*  */
    STAR(4822, -223),     /* 98 Virg */
    STAR(4840, -126),     /* 99 Virg */
    STAR(4857, -294),     /* 100 Virg */
    STAR(4864,  382),     /* 20 Boot */
    STAR(4910,  -41),     /* 105 Virg */
    STAR(4984,  383),     /* 29 Boot */
    STAR(4986,  322),     /* 30 Boot */
    STAR(4994, -119),     /* 107 Virg */
    STAR(5009,  396),     /* 35 Boot */
    STAR(5013,   53),     /* 109 Virg */
    STAR(5045,  444),     /* 37 Boot */
    STAR(5074,  -90),     /* 16 Libr */
    STAR(5108,   57),     /* 110 Virg */
    STAR(5157, -442),     /* 24 Libr */
    STAR(5283, -221),     /* 37 Libr */
    STAR(5290, -329),     /* 38 Libr */
    STAR(5291,  247),     /* 13 Serp */
    STAR(5326, -440),     /* 43 Libr */
    STAR(5331,  455),     /* 21 Serp */
    STAR(5357,  175),     /* 27 Serp */
    STAR(5372,  420),     /* 35 Serp */
    STAR(5381,  109),     /* 37 Serp */
    STAR(5387,  484),     /* 38 Serp */
    STAR(5394, -374),     /* 46 Libr */
    STAR(5415,  364),     /* 41 Serp */
    STAR(5419, -318),     /* 48 Libr */
    STAR(5455, -253),     /* xi Scor */
    STAR(5467, -464),     /* 9 Scor */
    STAR(5470, -469),     /* 10 Scor */
    STAR(5497, -437),     /* 14 Scor */
    STAR(5499, -223),     /* 15 Scor */
    STAR(5558,   29),     /* 50 Serp */
    STAR(5561,  441),     /* 20 Herc */
    STAR(5565, -451),     /* 4 Ophi */
    STAR(5580,  325),     /* 24 Herc */
    STAR(5582, -415),     /* 7 Ophi */
    STAR(5589, -186),     /* 3 Ophi */
    STAR(5606, -373),     /* 8 Ophi */
    STAR(5609,   50),     /* 10 Ophi */
    STAR(5610, -484),     /* 9 Ophi */
    STAR(5620,  266),     /* 29 Herc */
    STAR(5713, -241),     /* 20 Ophi */
    STAR(5742,  235),     /* 25 Ophi */
    STAR(5763,  217),     /* 27 Ophi */
    STAR(5807,  293),     /* 60 Herc */
    STAR(5868,   -8),     /* 41 Ophi */
    STAR(5888, -478),     /* 40 Ophi */
    STAR(5889, -290),     /* 53 Serp */
    STAR(5924, -114),     /*  */
    STAR(5925,   96),     /* 49 Ophi */
    STAR(5987, -183),     /* 57 Ophi */
    STAR(6006, -292),     /* 56 Serp */
    STAR(6016, -492),     /* 58 Ophi */
    STAR(6117,  -84),     /* 57 Serp */
    STAR(6117,   99),     /* 66 Ophi */
    STAR(6119,  381),     /* 93 Herc */
    STAR(6119,   67),     /* 67 Ophi */
    STAR(6125,   30),     /* 68 Ophi */
    STAR(6146,   57),     /* 70 Ophi */
    STAR(6158,  198),     /* 71 Ophi */
    STAR(6170,  473),     /* 102 Herc */
    STAR(6188, -480),     /* 13 Sgtr */
    STAR(6234,   76),     /* 74 Ophi */
    STAR(6235,  499),     /* 106 Herc */
    STAR(6247, -204),     /* xi Scut */
    STAR(6254, -469),     /* 21 Sgtr */
    STAR(6255,  494),     /* 109 Herc */
    STAR(6278, -333),     /* ga Scut */
    STAR(6313, -189),     /* al Scut */
    STAR(6379,  465),     /* 110 Herc */
    STAR(6382, -110),     /* be Scut */
    STAR(6386,  411),     /* 111 Herc */
    STAR(6436,   93),     /* 63 Serp */
    STAR(6457,  340),     /* 13 Aqil */
    STAR(6465, -134),     /* 12 Aqil */
    STAR(6478, -498),     /* 39 Sgtr */
    STAR(6553,  483),     /* 1 Vulp */
    STAR(6576, -410),     /* 44 Sgtr */
    STAR(6576, -368),     /* 46 Sgtr */
    STAR(6607,    3),     /* 32 Aqil */
    STAR(6651,  163),     /* 38 Aqil */
    STAR(6657,  445),     /* 9 Vulp */
    STAR(6665,  -35),     /* 41 Aqil */
    STAR(6688,  405),     /* 5 Sgte */
    STAR(6693,  393),     /* 6 Sgte */
    STAR(6730,  416),     /* 7 Sgte */
    STAR(6739,  430),     /* 8 Sgte */
    STAR(6755,   17),     /* 55 Aqil */
    STAR(6766,  187),     /* 59 Aqil */
    STAR(6772,  140),     /* 60 Aqil */
    STAR(6882,  339),     /* 67 Aqil */
    STAR(6896, -292),     /* 5 Capr */
    STAR(6898, -292),     /* 6 Capr */
    STAR(6913, -297),     /* 8 Capr */
    STAR(6958, -413),     /* 11 Capr */
    STAR(6988,  250),     /* 2 Dlph */
    STAR(7001,  326),     /* 4 Dlph */
    STAR(7015,  -33),     /* 71 Aqil */
    STAR(7020,  475),     /* 29 Vulp */
    STAR(7026,  354),     /* 9 Dlph */
    STAR(7047,  335),     /* 11 Dlph */
    STAR(7066,  359),     /* 12 Dlph */
    STAR(7067, -225),     /* 2 Aqar */
    STAR(7068, -123),     /* 3 Aqar */
    STAR(7096, -213),     /* 6 Aqar */
    STAR(7161, -461),     /* 22 Capr */
    STAR(7170, -401),     /* 23 Capr */
    STAR(7192, -268),     /* 13 Aqar */
    STAR(7199,  222),     /* 5 Equl */
    STAR(7223,  219),     /* 7 Equl */
    STAR(7230,  110),     /* 8 Equl */
    STAR(7263, -393),     /* 32 Capr */
    STAR(7267,  441),     /* 1 Pegs */
    STAR(7299, -506),     /* 36 Capr */
    STAR(7347, -453),     /* 39 Capr */
    STAR(7353, -189),     /* 23 Aqar */
    STAR(7365, -390),     /* 40 Capr */
    STAR(7379, -440),     /* 43 Capr */
    STAR(7394,  384),     /* 9 Pegs */
    STAR(7499,  -60),     /* 31 Aqar */
    STAR(7513,  104),     /* 22 Pegs */
    STAR(7515, -327),     /* 33 Aqar */
    STAR(7575, -189),     /* 43 Aqar */
    STAR(7603,  -43),     /* 48 Aqar */
    STAR(7604,  266),     /* 31 Pegs */
    STAR(7624,   20),     /* 52 Aqar */
    STAR(7639,   96),     /* 35 Pegs */
    STAR(7654, -255),     /* 57 Aqar */
    STAR(7681,  -14),     /* 62 Aqar */
    STAR(7727, -440),     /* 66 Aqar */
    STAR(7747,  266),     /* 46 Pegs */
    STAR(7761, -321),     /* 71 Aqar */
    STAR(7779, -185),     /* 73 Aqar */
    STAR(7795,  189),     /* 50 Pegs */
    STAR(7844,   75),     /* 4 Pisc */
    STAR(7862,  202),     /* 55 Pegs */
    STAR(7874, -494),     /* 88 Aqar */
    STAR(7903, -150),     /* 90 Aqar */
    STAR(7911, -219),     /* 91 Aqar */
    STAR(7919,   62),     /* 6 Pisc */
    STAR(7923, -222),     /* 93 Aqar */
    STAR(7952, -470),     /* 98 Aqar */
    STAR(7969, -482),     /* 99 Aqar */
    STAR(7975,   16),     /* 8 Pisc */
    STAR(7981,  133),     /* 10 Pisc */
    STAR(7988,  278),     /* 70 Pegs */
    STAR(8010, -489),     /* 101 Aqar */
    STAR(8049,  116),     /* 17 Pisc */
    STAR(8059, -418),     /* 104 Aqar */
    STAR(8061,   28),     /* 18 Pisc */
    STAR(8064, -344),     /* 105 Aqar */
    STAR(8159,  144),     /* 28 Pisc */
    STAR(8174, -149),     /* 30 Pisc */
    STAR(8188, -407),     /* 2 Ceti */
};
