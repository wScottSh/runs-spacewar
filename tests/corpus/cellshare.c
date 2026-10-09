/* corpus: entry=after,reread */
/* Storage the machine shares. after reads bump's entry word, which the call
 * filled and bump then advanced. reread reads its by-name word, rewrites the
 * word it names, and reads it again: the second read sees the new value. */

JDA word bump(word v);
JDA word after(word x);
JDA word twice(word a, BYNAME word b);
JDA word reread(word x);

ENTRY_CELL(bump) word bumped;

extern word shared, seen;

JDA word bump(word v)
{
    v = v + 1;
    return v;
}

JDA word after(word x)
{
    bump(x);
    return bumped;
}

JDA word twice(word a, BYNAME word b)
{
    word s = b;
    s = s + a;
    shared = s;
    word t = b;
    seen = t;
    return shared;
}

JDA word reread(word x)
{
    return twice(x, shared);
}

word shared = 0;
word seen = 0;
