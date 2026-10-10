/* corpus: entry=find */
/* A table of keys, ended by -0, and a parallel table of values. find(k)
 * returns the value stored with k, or -0 when k is missing, and counts the
 * misses. Two pointers walk the tables in step, each held in the address
 * of the instruction that reads through it. */

word keys[5] = { 5, 012, 077, 0123, MINUS_ZERO };
word values[4] = { 0500, 01200, 07700, 0321 };
HOMED const word *key_at = 0;
HOMED const word *value_at = 0;
word wanted = 0;
word misses = 0;

static inline word lookup(void)
{
    key_at = keys;
    value_at = values;
next:
    if (*home(key_at) == wanted)
        goto hit;
    ++value_at;
    if (I_LAC(++key_at) == I_LAC(keys + 4))
        return MINUS_ZERO;
    goto next;
hit:
    return *home(value_at);
}

JDA word find(word k)
{
    word v;

    wanted = k;
    v = lookup();
    if (v != MINUS_ZERO)
        return v;
    misses = misses + 1;
    return MINUS_ZERO;
}
