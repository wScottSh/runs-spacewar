/* corpus: entry=post */
/* A ledger of four accounts, kept as three tables stacked in one block
 * after the code, the literal constants and the pool words: balances,
 * limits and counts, with a spare word at the end. post(v) adds v to every
 * balance through cursors that walk the tables together: one held in the
 * instruction that adds to a balance, one in the instruction that stores
 * it, one in the instruction that subtracts the limit, and a pool word for
 * the counts. An account at or over its limit counts a posting, and the
 * words after each balance are summed. v = 0 wipes the counts first.
 * The first call sets the limits. Returns the last balance plus the
 * first count. */

#define ACCOUNTS 4
extern word ledger[3 * ACCOUNTS + 1];
#define BALANCES (ledger)
#define LIMITS (BALANCES + ACCOUNTS)
#define COUNTS (LIMITS + ACCOUNTS)

HOMED word *balance;
HOMED word *stored;
HOMED word *limit;
HOMED word *next_balance;
HOMED word *wiping = 0;
POOL word *count;
POOL word accounts_left;
POOL word lead;                     /* the sum of the word after each balance */

JDA word post(word v)
{
    if (LIMITS[0] == 0) {
        word l = 0100;
        LIMITS[0] = l;
        l = -l;
        LIMITS[1] = l;
        LIMITS[2] = 07000;
        LIMITS[3] = 0377;
    }
    if (v != 0)
        goto walk;
    wiping = COUNTS;
wipe:
    *home(wiping) = 0;
    if (I_DZM(++wiping) != I_DZM(COUNTS + ACCOUNTS))
        goto wipe;
walk:
    word *at = BALANCES;
    balance = at;
    stored = at;
    at = at + ACCOUNTS;
    limit = at;
    at = at + ACCOUNTS;
    count = at;
    accounts_left = -ACCOUNTS;
account:
    next_balance = 1 + balance;
    word b = v + *home(balance);
    *home(stored) = b;
    word d = b - *home(limit);
    if (SKIPNOT(d < 0))
        goto under;
    ++*count;
under:
    lead = *home(next_balance) + lead;
    ++balance;
    ++stored;
    ++limit;
    ++count;
    if (++accounts_left < 0)
        goto account;
    return BALANCES[ACCOUNTS - 1] + COUNTS[0];
}

CONSTANTS();
VARIABLES();
RESERVE word ledger[3 * ACCOUNTS + 1];
