/* G6 fixture: C that is laid out more than once, next to words the same
 * constant makes elsewhere. tests/test_predict.py edits the constants in
 * the copies. */
word total = 0;

static inline void add_five(void)
{
    total = total + 5;
}

static inline void add_nine_twice(void)
{
    total = total + 9;
    total = total + 9;
}

JDA word twice(word a)
{
    total = a;
    add_five();
    add_five();
    for (int i = 0; i < 2; i++)
        total = total + 7;
    add_nine_twice();
    add_nine_twice();
    return total + 5 + 7;
}
