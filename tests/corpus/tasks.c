/* corpus: entry=round */
/* A round of tasks from a task table after the code. Each entry is the
 * address of a JSP task with the sign bit set when the task is paused, or
 * 0 for a free slot. round(v) clears the table and fills three slots
 * (pausing the first task when v is negative), then for each slot moves the entry into IO to test the
 * pause bit, and calls a running task through the entry's address; it
 * counts the running tasks that have a free slot after them. A task reads
 * a sensor through `sensor`, a pool word holding the address of one of two
 * sensor routines, each returning its reading in IO; the test word's low
 * bit picks which. The round's total is shown on the console lights with
 * v, and a total that is not negative counts as settled. Then it is
 * routed: 0 straight to the end, negative totals negated, others halved.
 * Returns the routed total. */

#define SLOTS 4
#define PAUSED ((word)0400000)

typedef void task(void) JSP;
typedef io_word sensor_routine(void) JSP;
typedef word step(word v) BLOCK;

extern word tasks[SLOTS + 1];
POOL word scratch;
POOL word total;
POOL word reading;
POOL word slots_left;
POOL word free_after;
POOL word settled;                  /* rounds whose total was not negative */
POOL sensor_routine *sensor;
HOMED word *slot;
HOMED word *following;
HOMED word *wiping = 0;
RESERVE step *next;
word result = 0;

JSP io_word read_scratch(void)
{
    register word r = scratch;
    return r;
}

JSP io_word read_switches(void)
{
    word t = lat();
    register word r = SWAP(t);
    return r;
}

JSP void add_reading(void)
{
    register word r = ((sensor_routine *)sensor)();
    reading = r;
    total = reading + total;
}

JSP void count_up(void)
{
    ++total;
}

BLOCK word steer(word v);
BLOCK word done(word v);

JDA word round(word v)
{
    scratch = v;
    total = 0;
    sensor = read_scratch;
    if ((lat() & 1) == 0)
        goto filled;
    sensor = read_switches;
filled:
    wiping = tasks;
wipe:
    *home(wiping) = 0;
    if (I_DZM(++wiping) != I_DZM(tasks + SLOTS))
        goto wipe;
    tasks[0] = add_reading;
    if (v >= 0)
        goto first_runs;
    tasks[0] = add_reading | PAUSED;
first_runs:
    tasks[1] = count_up | PAUSED;
    tasks[2] = count_up;
    slot = tasks;
    slots_left = -SLOTS;
each:
    {
        word entry = *home(slot);
        if (entry == 0)
            goto next_slot;
        register word e = SWAP(entry);
        if (e < 0)
            goto next_slot;
    }
    following = 1 + slot;
    ((task *)*slot)();
    if (*home(following) != 0)
        goto next_slot;
    ++free_after;
next_slot:
    ++slot;
    if (++slots_left < 0)
        goto each;
    word t = total;
    register word shown = scratch;
    halt(t, shown);
    if (SKIPNOT(t >= 0))
        ++settled;
    t = total;
    if (t == 0)
        return done(t);
    next = steer;
    t = total;
    return next(t);
}

BLOCK word negate(word v);
BLOCK word halve(word v);

/* Several ways on, one way back: each of steer's ends returns through done. */
BLOCK word steer(word v)
{
    if (v < 0)
        return negate(v);
    return halve(v);
}

BLOCK word negate(word v)
{
    v = -v;
    return done(v);
}

BLOCK word halve(word v)
{
    v = v >> 1;
    return done(v);
}

BLOCK word done(word v)
{
    result = v;
    return v;
}

CONSTANTS();
VARIABLES();
RESERVE word tasks[SLOTS + 1];
