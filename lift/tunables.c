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

BLOCK void sequence_break(void)                /* at 3: ignore a sequence break */
{
    return flush_sequence_break();
}

START BLOCK void start(void)                   /* at 4: the usual start address, where the tape starts */
{
    return start_with_control_boxes();
}

BLOCK void start_test_word(void)               /* at 5: read the test word switches, not the control boxes */
{
    return start_with_test_word();
}

/* ------------------------------------- interesting and often changed constants */

XCT word torpedo_supply(void)                  /* tno: at 6, number of torpedoes + 1, negated */
{
    return -041;
}

XCT word torpedo_velocity(word heading)        /* tvl: at 7 */
{
    return heading >> 4;
}

XCT word torpedo_reload_time(void)             /* rlt: at 10 */
{
    return -020;
}

XCT word torpedo_life(void)                    /* tlf: at 11 */
{
    return -0140;
}

word fuel_supply = -020000;                    /* foo: at 12 */
word angular_acceleration = 010;               /* maa: at 13, spaceship angular acceleration */

XCT word spaceship_acceleration(word heading)  /* sac: at 14 */
{
    return heading >> 4;
}

word star_capture_radius = 1;                  /* str: at 15 */
word collision_radius = 06000;                 /* me1: at 16 */
word collision_radius_half = 03000;            /* me2: at 17 */

/* -0 compiles an outline for each ship; 0 shares one outline and leaves
 * room for ddt. */
word separate_outlines = MINUS_ZERO;           /* ddd: at 20 */

XCT word torpedo_space_warpage(word position)  /* the: at 21 */
{
    return position >> 9;
}

XCT word hyperspace_shots(void)                /* mhs: at 22, number of hyperspace jumps, negated */
{
    return -010;
}

XCT word time_before_breakout(void)            /* hd1: at 23, time in hyperspace before breakout */
{
    return -040;
}

XCT word breakout_time(void)                   /* hd2: at 24, time in hyperspace breakout */
{
    return -0100;
}

XCT word hyperfield_recharge_time(void)        /* hd3: at 25, time to recharge the hyperfield generators */
{
    return -0200;
}

/* The scale on the hyperspatial displacement of a random AC:IO pair. */
XCT dword hyperspatial_displacement(word high, register word low)  /* hr1: at 26 */
{
    scl(high, low, 9);
    return (dword){ high, low };
}

/* The scale on the hyperspatially induced velocity. */
XCT dword hyperspatial_velocity(word high, register word low)  /* hr2: at 27 */
{
    scl(high, low, 4);
    return (dword){ high, low };
}

word hyperspatial_uncertainty = 040000;        /* hur: at 30 */
word random_number = 0;                        /* ran: at 31, state of the random number generator */

/* ------------------------------------------------- control word routine
 * A place to build a private control word routine, entered by `jsp cwg`.
 * It leaves the control word in IO: in the high 4 bits rotate ccw, rotate
 * cw (both together: hyperspace), fire rocket and fire torpedo for one
 * ship, and the same in the low 4 bits for the other. Normally it reads the
 * control boxes. */

JSP io_word read_control_boxes(void);

AT(040) JSP io_word control_word_routine(void)  /* cwr: at 40 */
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
