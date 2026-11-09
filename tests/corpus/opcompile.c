/* corpus: entry=run native=run:run_by_hand */
/* A compiler for a word of six 3-bit operation codes, read from the left,
 * and a routine that compiles x and jumps into the compiled code with x in
 * AC. The codes: 0 ends the program, 1 adds one, 2 complements, 3 adds the
 * step, 4 rotates left one place, 5 subtracts one, 6 flips the mask bits,
 * 7 keeps only the mask bits. The compiled code ends with a jump to finish,
 * which returns from run. run_by_hand does the same computation directly:
 * it is what the native build runs for run, since nothing there executes
 * generated code. It works in `result`, the word finish stores, so both
 * leave the same words behind. */

typedef word compiled(word v) BLOCK;

RESERVE word code_area[7];
RESERVE compiled *entry;
POOL word *cursor;
POOL word codes_left;
word one = 1;
word step = 0123;
word mask = 0525252;
word result = 0;

BLOCK word finish(word v);

JDA word compile(word program)
{
    register word bits = program;
    word op;

    cursor = code_area;
    codes_left = -6;
next:
    op = 0;
    rcl(op, bits, 3);
    switch ((int)op) {
    case 0: goto done;
    case 1: goto add_one;
    case 2: goto complement;
    case 3: goto add_step;
    case 4: goto rotate;
    case 5: goto sub_one;
    case 6: goto flip;
    case 7:
        *cursor++ = I_AND(&mask);
        goto again;
    }
add_one:
    *cursor++ = I_ADD(&one);
    goto again;
complement:
    *cursor++ = I_CMA;
    goto again;
add_step:
    *cursor++ = I_ADD(&step);
    goto again;
rotate:
    *cursor++ = I_RAL(1);
    goto again;
sub_one:
    *cursor++ = I_SUB(&one);
    goto again;
flip:
    *cursor++ = I_XOR(&mask);
again:
    if (++codes_left < 0)
        goto next;
done:
    *cursor++ = I_JMP(finish);
    return codes_left;
}

JDA word run(word x)
{
    word v = x;
    if (v == 0)
        return finish(v);           /* nothing to compile */
    compile(v);
    entry = (compiled *)code_area;
    v = x;
    return entry(v);
}

JDA word run_by_hand(word x)
{
    word v = x;
    word op;

    if (v == 0)
        return finish(v);
    compile(v);
    entry = (compiled *)code_area;
    result = x;
    register word bits = x;
    codes_left = -6;
next:
    op = 0;
    rcl(op, bits, 3);
    switch ((int)op) {
    case 0: goto done;
    case 1: goto add_one;
    case 2: goto complement;
    case 3: goto add_step;
    case 4: goto rotate;
    case 5: goto sub_one;
    case 6: goto flip;
    case 7:
        result = result & mask;
        goto again;
    }
add_one:
    result = result + one;
    goto again;
complement:
    result = -result;
    goto again;
add_step:
    result = result + step;
    goto again;
rotate:
    result = ral(result, 1);
    goto again;
sub_one:
    result = result - one;
    goto again;
flip:
    result = result ^ mask;
again:
    if (++codes_left < 0)
        goto next;
done:
    return finish(result);
}

BLOCK word finish(word v)
{
    result = v;
    return v;
}
