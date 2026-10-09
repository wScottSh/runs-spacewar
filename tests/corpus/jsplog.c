/* corpus: entry=tally */
/* record, entered by jsp, logs the word in IO and counts calls. log_value
 * forwards to it. tally logs x and then its complement, and returns the
 * count. */

JSP void record(register word w);
JSP void log_value(register word w);

extern word last, calls;

JSP void record(register word w)
{
    last = w;
    ++calls;
}

JSP void log_value(register word w)
{
    return record(w);
}

JDA word tally(word x)
{
    register word w = x;
    record(w);
    word n = -x;
    register word v = n;
    log_value(v);
    return calls;
}

word last = 0;
word calls = 0;
