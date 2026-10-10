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
BLOCK void start_with_control_boxes(void);
BLOCK void start_with_test_word(void);

/* ---------------------------------------------------------- start vectors */

BLOCK void sequence_break(void)         /* 3: ignore a sequence break */
{
    return flush_sequence_break();
}

START BLOCK void start(void)            /* 4: the usual start address, where the tape starts */
{
    return start_with_control_boxes();
}

BLOCK void start_test_word(void)        /* 5: read the test word switches, not the control boxes */
{
    return start_with_test_word();
}

/* ------------------------------------- interesting and often changed constants */

XCT word torpedo_supply(void)         /* tno: 6: number of torpedoes + 1, negated */
{
    return -041;
}

XCT word torpedo_velocity(word v)     /* tvl: 7 */
{
    return v >> 4;
}

XCT word torpedo_reload_time(void)    /* rlt: 10 */
{
    return -020;
}

XCT word torpedo_life(void)           /* tlf: 11 */
{
    return -0140;
}

word fuel_supply = -020000;           /* foo: 12 */
word angular_acceleration = 010;      /* maa: 13: spaceship angular acceleration */

XCT word spaceship_acceleration(word v)   /* sac: 14 */
{
    return v >> 4;
}

word star_capture_radius = 1;         /* str: 15 */
word collision_radius = 06000;        /* me1: 16 */
word collision_radius_half = 03000;   /* me2: 17 */

/* 20: -0 compiles an outline for each ship; 0 shares one outline and
 * leaves room for ddt. */
word separate_outlines = MINUS_ZERO;  /* ddd */

XCT word torpedo_space_warpage(word v)    /* the: 21 */
{
    return v >> 9;
}

XCT word hyperspace_shots(void)       /* mhs: 22: number of hyperspace jumps, negated */
{
    return -010;
}

XCT word time_before_breakout(void)   /* hd1: 23: time in hyperspace before breakout */
{
    return -040;
}

XCT word breakout_time(void)          /* hd2: 24: time in hyperspace breakout */
{
    return -0100;
}

XCT word hyperfield_recharge_time(void)   /* hd3: 25: time to recharge the hyperfield generators */
{
    return -0200;
}

/* 26: scale on the hyperspatial displacement of a random AC:IO pair */
XCT dword hyperspatial_displacement(word hi, register word lo)  /* hr1 */
{
    scl(hi, lo, 9);
    return (dword){ hi, lo };
}

/* 27: scale on the hyperspatially induced velocity */
XCT dword hyperspatial_velocity(word hi, register word lo)  /* hr2 */
{
    scl(hi, lo, 4);
    return (dword){ hi, lo };
}

word hyperspatial_uncertainty = 040000;   /* hur: 30 */
word random_number = 0;               /* ran: 31: state of the random number generator */

/* ------------------------------------------------- control word routine
 * A place to build a private control word routine, entered by `jsp cwg`.
 * It leaves the control word in IO: in the high 4 bits rotate ccw, rotate
 * cw (both together: hyperspace), fire rocket and fire torpedo for one
 * ship, and the same in the low 4 bits for the other. Normally it reads the
 * control boxes. */

JSP io_word read_control_boxes(void);

AT(040) JSP io_word control_word_routine(void)  /* cwr */
{
    return read_control_boxes();
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
