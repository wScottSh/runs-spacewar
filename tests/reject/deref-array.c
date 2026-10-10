/* reject: an array's name is its address, not a pointer word */
/* `dac i a` would store through the word a[0] holds, where C stores into a[0]. */

word a[2] = { 0, 0 };

JDA word f(word x)
{
    *a = x;
    return x;
}
