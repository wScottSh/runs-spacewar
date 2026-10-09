/* reject: an XCT function must lower to exactly one word, not 2 */
/* xct executes one word in place; a second word would never run. */

XCT word bump(word v)
{
    v = v + 1;
    return v >> 1;
}
