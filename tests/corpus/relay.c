/* corpus: entry=relay */
/* A relay station. relay(x) gets a reading from whichever reader the
 * pointer word `reader` names (a JSP routine), x's sign choosing it, and
 * keeps it if it is not negative (keep_positive returns past the word
 * after its call then). It adds the reading to one of the running totals,
 * picked by sense switch 1 and reached through a pointer held in the
 * instruction that adds it; the next two totals get the reading (through
 * IO) and x's low bits, through pointers built from the first. Then it
 * picks a stage by the reading's low bit and jumps to it through a pointer
 * held in the jump; with sense switch 2 it skips the stages. Every path
 * ends in finish, which returns the mark and the total. */

typedef word reader_fn(void) JSP;
typedef word stage_fn(void) BLOCK;

POOL reader_fn *reader;
POOL word reading;
POOL word kept;
word totals[5] = { 0, 0100, 0, 0, 0 };
word mark = 0;
extern word *total;
HOMED word *total;
HOMED word *copy_cell;
HOMED word *tag_cell;
HOMED word *note;
HOMED stage_fn *stage;

JSP word read_up(void)
{
    return reading + 1;
}

JSP word read_down(void)
{
    return -reading;
}

JDA SKIPS word keep_positive(word a)
{
    kept = a;
    if (a < 0)
        return a;
    skip_return();
    return kept;
}

BLOCK word route(void);
BLOCK word low_stage(void);
BLOCK word high_stage(void);
BLOCK word finish(void);

JDA word relay(word x)
{
    word r;
    register word copy;

    reading = x;
    if (x < 0)
        goto down;
    reader = read_up;
    goto read;
down:
    reader = read_down;
read:
    r = reader();
    r = keep_positive(r);
    reading = r;
    total = totals;
    if (sense(1))
        ++total;
    r = reading + *home(total);
    *total = r;
    copy_cell = 1 + total;
    copy = reading;
    *home(copy_cell) = copy;
    tag_cell = copy_cell + 1;
    home(tag_cell)->addr = x;
    return route();
}

BLOCK word route(void)
{
    word r = reading & 1;
    if (r == 0)
        goto low;
    stage = high_stage;
    goto go;
low:
    stage = low_stage;
go:
    if (sense(2))
        return finish();
    return (*home(stage))();
}

BLOCK word low_stage(void)
{
    note = totals + 4;
    *home(note) = reading >> 1;
    return finish();
}

BLOCK word high_stage(void)
{
    word m = MINUS_ZERO;
    mark = m ^ reading;
    return finish();
}

BLOCK word finish(void)
{
    if (0 == *total)
        mark = mark + 1;
    return mark + *total;
}
