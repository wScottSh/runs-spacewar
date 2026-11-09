/*
 * sqt -- integer square root. Source lines 309-343, words 00246-00305.
 * Input binary point right of bit 17; answer binary point between bits 8 and 9.
 *
 * Trace format: each statement's comment lists the words swc emits, then
 * the oracle listing word at that address. "ok" = identical.
 */

static word sq1 = 0, sq2 = 0;  /* defined here, placed after sqt by `place` below */

#pragma pdp1 jda(sqt)
word sqt(word n)               /* 00246 000000  sqt, 0       entry word = home of n        ok */
                               /* 00247 260260  dap sqx      prologue: patch return slot    ok */
{
    dword r;                   /* the AC:IO pair: r.io holds the unconsumed input bits */
    word t;                    /* AC local */

    sq1 = -023;                /* 00250 710023  law i 23 ; 00251 240304 dac sq1              ok */
    sq2 = 0;                   /* 00252 340305  dzm sq2                                      ok */
    r.io = n;                  /* 00253 220246  lio sqt                                      ok */
    n = 0;                     /* 00254 340246  dzm sqt                                      ok */
    for (;;) {                 /* loop head sq3 = 00255 */
        if (++sq1 >= 0)        /* 00255 460304  isp sq1     isp has no inverse: layout L3    ok */
            return sq2;        /* 00256 600261  jmp .+3 ; 00257 200305 lac sq2               ok */
                               /* 00260 600260  sqx: jmp .  only return => it is the slot    ok */
        sq2 = sq2 << 1;        /* 00261 200305 lac sq2 ; 00262 665001 sal 1s ; 00263 240305 dac sq2  ok */
        r.ac = n;              /* 00264 200246  lac sqt                                      ok */
        r = rcl(r, 2);         /* 00265 663003  rcl 2s                                       ok */
        if (r.ac == 0)         /* 00266 650100  sza i       L1: skip(!c), jump               ok */
            continue;          /* 00267 600255  jmp sq3                                      ok */
        n = r.ac;              /* 00270 240246  dac sqt                                      ok */
        t = (sq2 << 1) + 1 - n;
                               /* 00271 200305 lac sq2 ; 00272 665001 sal 1s ;
                                  00273 402777 add (1 ; 00274 420246 sub sqt                 ok */
        if (t > 0)             /* 00275 640500  sma+sza-skip  skip(t <= 0)                   ok */
            continue;          /* 00276 600255  jmp sq3                                      ok */
        n = mag(t);            /* 00277 640200 spa ; 00300 761000 cma ; 00301 240246 dac sqt ok */
        ++sq2;                 /* 00302 440305  idx sq2                                      ok */
    }                          /* 00303 600255  jmp sq3     back edge                        ok */
}

#pragma pdp1 place(sq1, sq2)   /* 00304 000000  sq1, 0 ; 00305 000000  sq2, 0                ok */

/*
 * Rules exercised (compiler.md section numbers):
 *   C1 jda entry word + `dap slot` prologue; C3 return slot at the last return.
 *   S1 constants: -023 -> law i; 0 store -> dzm; 1 non-leading -> literal (1.
 *   S2 `++x` + `>= 0` test -> isp; S4 dword .io assignment from memory -> lio.
 *   F1 skip table; if-layouts L3 for a 2-word body under a skip with no
 *         inverse, L1 for a single jump with an invertible skip.
 *   R1 AC-local t; R2 the AC cache does NOT fire for `r.ac = n` because
 *      `dac sq2` left AC = sq2, not n.
 *   P4 storage placement: `place` puts sq1/sq2 after the code. (Without it
 *      they would sit where they are defined, before sqt.)
 * Literal pool: one occurrence, value 1 (pool word 02777, first seen here).
 * Missing rules: none for this region.
 */
