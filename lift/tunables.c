/* The start of the program (source lines 67-116): the start vectors, the
 * table of "interesting and often changed constants", the control word
 * routine slot and the sequence break flush.
 *
 * The constants sit low in core so an operator could change them from the
 * console switches between games. Most entries are instructions that the
 * game executes in place with xct (the source notes they "may be replaced
 * by jda or jsp"), so each of those is a one-instruction XCT function. The
 * rest are words the game reads. */

/* ------------------------------------------------------- sequence break
 * On a sequence break the machine saves AC in word 0, the program counter
 * in word 1 and IO in word 2, then executes the instruction in word 3. */

typedef void resume_point(word ac, register word io) BLOCK;

AT(0) RESERVE word break_ac;
RESERVE resume_point *break_pc;
RESERVE word break_io;

BLOCK void flush_sequence_break(void);
BLOCK SYM("a40") void start_with_control_boxes(void);
BLOCK SYM("a1") void start_with_test_word(void);

/* ---------------------------------------------------------- start vectors */

BLOCK void sequence_break(void)         /* 3: ignore a sequence break */
{
    return flush_sequence_break();
}

BLOCK void start(void)                  /* 4: the usual start address */
{
    return start_with_control_boxes();
}

BLOCK void start_test_word(void)        /* 5: read the test word switches, not the control boxes */
{
    return start_with_test_word();
}

/* ------------------------------------- interesting and often changed constants */

XCT SYM("tno") word torpedo_supply(void)         /* 6: number of torpedoes + 1, negated */
{
    return -041;
}

XCT SYM("tvl") word torpedo_velocity(word v)     /* 7 */
{
    return v >> 4;
}

XCT SYM("rlt") word torpedo_reload_time(void)    /* 10 */
{
    return -020;
}

XCT SYM("tlf") word torpedo_life(void)           /* 11 */
{
    return -0140;
}

word fuel_supply SYM("foo") = -020000;           /* 12 */
word angular_acceleration SYM("maa") = 010;      /* 13: spaceship angular acceleration */

XCT SYM("sac") word spaceship_acceleration(word v)   /* 14 */
{
    return v >> 4;
}

word star_capture_radius SYM("str") = 1;         /* 15 */
word collision_radius SYM("me1") = 06000;        /* 16 */
word collision_radius_half SYM("me2") = 03000;   /* 17 */

/* 20: -0 compiles an outline for each ship; 0 shares one outline and
 * leaves room for ddt. */
word separate_outlines SYM("ddd") = MINUS_ZERO;

XCT SYM("the") word torpedo_space_warpage(word v)    /* 21 */
{
    return v >> 9;
}

XCT SYM("mhs") word hyperspace_shots(void)       /* 22: number of hyperspace jumps, negated */
{
    return -010;
}

XCT SYM("hd1") word time_before_breakout(void)   /* 23: time in hyperspace before breakout */
{
    return -040;
}

XCT SYM("hd2") word breakout_time(void)          /* 24: time in hyperspace breakout */
{
    return -0100;
}

XCT SYM("hd3") word hyperfield_recharge_time(void)   /* 25: time to recharge the hyperfield generators */
{
    return -0200;
}

/* 26: scale on the hyperspatial displacement of a random AC:IO pair */
XCT SYM("hr1") dword hyperspatial_displacement(word hi, register word lo)
{
    scl(hi, lo, 9);
    return (dword){ hi, lo };
}

/* 27: scale on the hyperspatially induced velocity */
XCT SYM("hr2") dword hyperspatial_velocity(word hi, register word lo)
{
    scl(hi, lo, 4);
    return (dword){ hi, lo };
}

word hyperspatial_uncertainty SYM("hur") = 040000;   /* 30 */
word random_number SYM("ran") = 0;               /* 31: state of the random number generator */

/* ------------------------------------------------- control word routine
 * A place to build a private control word routine, entered by `jsp cwg`.
 * It leaves the control word in IO: in the high 4 bits rotate ccw, rotate
 * cw (both together: hyperspace), fire rocket and fire torpedo for one
 * ship, and the same in the low 4 bits for the other. Normally it reads the
 * control boxes. */

JSP SYM("mg1") io_word read_control_boxes(register word io);

AT(040) JSP SYM("cwr") io_word control_word_routine(register word io)
{
    return read_control_boxes(io);
}

RESERVE word control_word_space[020];

/* ------------------------------------------------- sequence break flush
 * Clears the typewriter, leaves sequence break mode, and resumes the
 * interrupted program with its AC and IO. */

BLOCK void flush_sequence_break(void)
{
    tyi();
    register word io = break_io;
    word ac = break_ac;
    lsm();
    return break_pc(ac, io);
}
