/* The outline compiler (source lines 398-507), Dan Edwards' fiddle to speed
 * up the spaceship display. Instead of interpreting a ship's outline table
 * every frame, the game compiles it once at the start into straight-line
 * code that draws the ship; the spaceship calc routine jumps into that code
 * each frame. Call: outline_compiler(code, outline) is `jda oc` with the
 * address to compile to in AC and the outline table's address in the word
 * after the call. It returns the first word after the compiled code.
 *
 * An outline word holds six 3-bit direction codes, read from the left:
 *   0  same as 1          4  in
 *   1  down               5  in and down
 *   2  out                6  store the current position, or restore it
 *   3  out and down       7  draw the other side, then return
 * "Down", "out" and "in" are relative to a ship standing on its tail. Each
 * step compiles code that moves the pen by the rotated step, exchanges x
 * and y with a swap (two `rcl 9s`) around the y step, waits for the display
 * and plots a dot. The 7 code ends the outline: the compiled code mirrors
 * the steps and runs again for the other side, then stores the final
 * position and returns to the spaceship calc routine at sq6.
 *
 * Runtime code generation is data writing: the compiled code is a sequence
 * of instruction words, each built by an insn constructor and stored
 * through the compile pointer. Nothing here executes it. */

/* The ship being drawn, as the spaceship calc routine leaves it for the
 * compiled outline: its position in dpy coordinates (the pen starts there
 * and ends at the tail) and the steps rotated to the ship's heading. */
POOL word ship_x SYM("sx1");
POOL word ship_y SYM("sy1");
POOL word sine_step SYM("ssn");         /* down: x += sin */
POOL word cosine_step SYM("scn");       /* down: y -= cos */
POOL word out_x SYM("scm");             /* out: x +=, in: x -= */
POOL word out_y SYM("ssm");             /* out: y +=, in: y -= */
POOL word out_down_x SYM("ssc");
POOL word out_down_y SYM("csm");        /* subtracted */
POOL word in_down_x SYM("csn");
POOL word in_down_y SYM("ssd");         /* subtracted */
POOL word saved_x;                      /* the position code 6 stores */
POOL word saved_y;

/* Where the compiled outline returns to, in the spaceship calc routine. */
BLOCK SYM("sq6") void outline_drawn(void);

POOL word codes_left;                   /* codes still to read in this outline word */
POOL word codes_rest;                   /* the outline word, rotated past the codes read */
HOMED const word *outline_word;         /* the outline word being read */

JDA SYM("oc") word *outline_compiler(word *code, INLINE const word *outline);

ENTRY_CELL(outline_compiler) word *code;    /* oc's entry word: where the next word goes */

/* Two jumps the 7 code compiles. Compiling sets each one's address, then
 * copies it into the code. */
insn start_over = I_JMP(&start_over);       /* back to the start of the outline */
insn to_other_side = I_JMP(&to_other_side); /* on the first pass, past the return */

/* Compile the instruction in IO twice. With `rcl 9s` in IO that is a swap,
 * which exchanges x in AC with y in IO in the compiled code. */
JSP void compile_twice(register insn half)
{
    *code++ = half;
    *code++ = half;
}

JDA SYM("oc") word *outline_compiler(word *code, INLINE const word *outline)
{
    register word bits;
    register insn swap_half;
    word direction;
    insn second;                        /* the instruction that moves y */

    outline_word = outline;
    *code++ = I_STF(5);                 /* flag 5: drawing the first side */
    start_over.addr = code;
    ARGS_DONE();
    *code++ = I_LAC(&ship_x);
    *code++ = I_LIO(&ship_y);
    clf(6);
next_word:
    codes_left = -6;
    bits = *home(outline_word);
next_code:
    direction = 0;
    rcl(direction, bits, 3);
    codes_rest = bits;
    swap_half = I_RCL(9);
    switch ((int)direction) {
    case 0:
    case 1: goto down;
    case 2: goto out;
    case 3: goto out_down;
    case 4: goto in;
    case 5: goto in_down;
    case 6: goto store_or_restore;
    case 7:
        *code++ = I_SZF(5);
        to_other_side.addr = code + 4;
        *code++ = to_other_side;
        *code++ = I_DAC(&ship_x);       /* both sides drawn: the tail position */
        *code++ = I_DIO(&ship_y);
        *code++ = I_JMP(outline_drawn);
        *code++ = I_CLF(5);             /* mirror the steps for the other side */
        *code++ = I_LAC(&out_x);
        *code++ = I_CMA;
        *code++ = I_DAC(&out_x);
        *code++ = I_LAC(&out_y);
        *code++ = I_CMA;
        *code++ = I_DAC(&out_y);
        *code++ = I_LAC(&out_down_y);   /* exchange out-and-down with in-and-down */
        *code++ = I_LIO(&in_down_y);
        *code++ = I_DAC(&in_down_y);
        *code++ = I_DIO(&out_down_y);
        *code++ = I_LAC(&out_down_x);
        *code++ = I_LIO(&in_down_x);
        *code++ = I_DAC(&in_down_x);
        *code++ = I_DIO(&out_down_x);
        *code++ = start_over;
        return code;
    }
    PLACE(start_over, to_other_side);

down:
    *code++ = I_ADD(&sine_step);
    compile_twice(swap_half);
    second = I_SUB(&cosine_step);
plot:
    *code++ = second;
    compile_twice(swap_half);
    *code++ = I_IOH;                    /* wait for the last dot */
    second = I_DPY_NOWAIT;              /* plot this one */
next:
    *code++ = second;
    bits = codes_rest;
    if (++codes_left < 0)
        goto next_code;
    ++outline_word;
    goto next_word;

out:
    *code++ = I_ADD(&out_x);
    compile_twice(swap_half);
    second = I_ADD(&out_y);
    goto plot;

out_down:
    *code++ = I_ADD(&out_down_x);
    compile_twice(swap_half);
    second = I_SUB(&out_down_y);
    goto plot;

in:
    *code++ = I_SUB(&out_x);
    compile_twice(swap_half);
    second = I_SUB(&out_y);
    goto plot;

in_down:
    *code++ = I_ADD(&in_down_x);
    compile_twice(swap_half);
    second = I_SUB(&in_down_y);
    goto plot;

store_or_restore:                       /* alternate, starting with store */
    if (flag(6))
        goto restore;
    stf(6);
    *code++ = I_DAC(&saved_x);
    second = I_DIO(&saved_y);
    goto next;
restore:
    clf(6);
    *code++ = I_LAC(&saved_x);
    second = I_LIO(&saved_y);
    goto next;
}
