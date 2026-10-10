/* corpus: entry=tally inputs=777771..777777 */
/* Sorts the words of a table into four buckets by their two high bits and
 * logs, for each word, the instruction that counts it: `idx bucket`. The
 * negated word count comes in AC and the table's address in the word after
 * the call. The table is read through a pointer held in the instruction
 * that reads it, into IO. Flag 4 records a word in the top bucket; then the
 * call returns that bucket's count, else the low bucket's. tally runs two
 * tables. */

RESERVE word log_area[6];
POOL word *next_log;
POOL word left;
POOL word first;
HOMED const word *at;
word low = 0;
word mid = 0;
word high = 0;
word top = 0;
word count_one = I_IDX(&low);

word sample[6] = { 0100000, 0300000, 0500000, 0700000, 0200001, 0400002 };
word falling[6] = { 0777770, 0600000, 0400000, 0377777, 0123456, 0 };

JDA word tally_table(word n, INLINE const word *table)
{
    register word w;
    word k;

    at = table;
    next_log = log_area;
    left = n;
    clf(4);
next:
    w = *home(at);
    k = 0;
    rcl(k, w, 2);
    switch ((int)k) {
    case 0: goto in_low;
    case 1: goto in_mid;
    case 2: goto in_high;
    case 3:
        ++top;
        count_one.addr = &top;
        stf(4);
        goto logged;
    }
in_low:
    ++low;
    count_one.addr = &low;
    goto logged;
in_mid:
    ++mid;
    count_one.addr = &mid;
    goto logged;
in_high:
    ++high;
    count_one.addr = &high;
logged:
    *next_log++ = count_one;
    ++at;
    if (++left < 0)
        goto next;
    if (flag(4))
        return top;
    return low;
    PLACE(count_one);
}

JDA word tally(word n)
{
    word a = tally_table(n, sample);
    first = a;
    return tally_table(n, falling);
}
