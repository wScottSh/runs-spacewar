/* corpus: entry=copy */
/* Copies a zero-ended table, word by word, into copy_area, twice each,
 * after flipping the bits the caller gives in AC and negating every other
 * word. The table's address is the word after the call. A read pointer
 * lives in the instruction that reads the table; the write pointer is a
 * pool word. `last` is an instruction word that loads the last word copied:
 * the copy points its address there. -0 marks the end of the copy. copy
 * runs it on two tables and returns the total count. */

RESERVE word copy_area[016];
POOL word *out;
POOL word copied;
POOL word total;
HOMED const word *in;
word last = I_LAC(&last);

word squares[5] = { 1, 4, 011, 020, 0 };
word primes[6] = { 2, 3, 5, 7, 013, 0 };

JDA word copy_table(word flip, INLINE const word *table);

/* Store the word in IO at the write pointer. */
JSP void put(register word w)
{
    *out++ = w;
}

JDA word copy_table(word flip, INLINE const word *table)
{
    word w;

    in = table;
    out = copy_area;
    copied = 0;
    clf(2);
    for (;;) {
        w = *home(in);
        if (w == 0) {
            register word end = MINUS_ZERO;
            put(end);
            return copied;
        }
        w = w ^ flip;
        if (flag(2))
            w = -w;
        register word copy = w;
        put(copy);
        ++copied;
        put(copy);
        last.addr = out;
        ++in;
        if (flag(2))
            clf(2);
        else
            stf(2);
    }
    PLACE(last);
}

JDA word copy(word x)
{
    word n = copy_table(x, squares);
    total = n;
    n = copy_table(x, primes);
    return n + total;
}
