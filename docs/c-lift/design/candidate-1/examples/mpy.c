/*
 * imp / mpy (BBN multiply). Source lines 260-301, words 00156-00245.
 * Call: first factor in AC, `jda mpy` (or imp), then a one-word load of
 * the second factor. mpy returns 34 bits and 2 signs in AC:IO; imp returns
 * the low 17 bits and sign in AC.
 *
 * The second factor is an exec inline operand: the callee reads it by
 * executing the caller's load through its link (`xct`). The link cell is
 * homed in the first instruction that reads the operand, so that read is
 * `xct <return address>` itself (rule C2).
 */

#pragma pdp1 jda(mpy, inline=b:exec)
#pragma pdp1 jda(imp, inline=b:exec)
dword mpy(word a, word b);

word imp(word a, word b)        /* 00156 000000  imp, 0                                 ok */
{                               /* 00157 260160  dap im1   link = first exec read        ok */
    dword p = mpy(b, a);        /* 00160 100000  im1: xct  first read of b IS the link;
                                                 placeholder address 0 (C2)              ok
                                   00161 170171  jda mpy                                  ok
                                   00162 200156  lac imp   operand a = imp's entry word   ok */
    consume(b);                 /* 00163 440160  idx im1   AC dead (p.ac unused)         ok */
    p.io = rir(p.io, 1);        /* 00164 672001  rir 1s    computed in IO               ok */
    return swapr(p).ac;         /* 00165 673777  rcr 9s ; 00166 673777 rcr 9s           ok
                                   00167 610160  jmp i im1 exec-link return              ok */
}

word mp2 = 0;                   /* 00170 000000  mp2, 0  initialized file scope: here     ok */

dword mpy(word a, word b)       /* 00171 000000  mpy, 0                                 ok */
{                               /* 00172 260200  dap mp1                                 ok */
    dword p;
    p.ac = mag(a);              /* 00173 200171 lac mpy ; 00174 640200 spa ;
                                   00175 761000 cma                                     ok */
    p = swapr(p);               /* 00176 673777 rcr 9s ; 00177 673777 rcr 9s  p.io=|a| ok */
    mp2 = mag(b);               /* 00200 100000 mp1: xct  (link home) ; 00201 640200 spa ;
                                   00202 761000 cma ; 00203 240170 dac mp2              ok */
    p.ac = 0;                   /* 00204 760200  cla                                     ok */
#pragma pdp1 unroll
    for (int k = 0; k < 021; k++)   /* Macro "repeat 21" is octal: 17 steps */
        p = mus(p, mp2);        /* 00205-00225 540170  mus mp2  x021 (17 words)            ok */
    mp2 = p.ac;                 /* 00226 240170  dac mp2                                 ok */
    if ((b ^ a) < 0) {          /* 00227 100200 xct mp1  second read of b ;
                                   00230 060171 xor mpy ; 00231 640400 sma ;
                                   00232 600243 jmp mp3    L3                            ok */
        p.ac = mp2;             /* 00233 200170  lac mp2  (AC cache invalid: xor clobbered) ok */
        p.ac = -p.ac;           /* 00234 761000  cma                                     ok */
        p = swapr(p);           /* 00235 673777 ; 00236 673777  rcr 9s x2                ok */
        p.ac = -p.ac;           /* 00237 761000  cma                                     ok */
        p = swapr(p);           /* 00240 673777 ; 00241 673777  36-bit negate done       ok */
        mp2 = p.ac;             /* 00242 240170  dac mp2                                 ok */
    }
    consume(b);                 /* 00243 440200  mp3: idx mp1  join point, AC dead      ok */
    p.ac = mp2;                 /* 00244 200170  lac mp2                                 ok */
    return p;                   /* 00245 610200  jmp i mp1                               ok */
}

/*
 * 00156-00245: 56 words reproduced.
 *   C2 exec inline operand: callee side (link homed in first xct read,
 *      later reads `xct link`, return `jmp i link`) and caller side (imp
 *      calling mpy: `jda mpy` + one-word load `lac imp`).
 *   consume(b) -> `idx link` exactly where written. swc checks AC is dead
 *      there, b is not read afterwards, and every path to return passes one.
 *   R4 AC<->IO exchange: the BBN code rotates right, so the C says swapr
 *      (`rcr 9s` x2); Spacewar's own code says swap (`rcl 9s` x2). Same
 *      meaning, two encodings, chosen in the C rather than guessed.
 *   O3 unroll: `#pragma pdp1 unroll` + constant trip count (octal 021 = 17).
 *   Placeholders: the exec link starts as `xct` with address 0 (C2), unlike
 *   jmp return slots which start as `jmp .` (C3). Both are calling-
 *   convention constants, not per-site choices.
 * Missing rules: none, but `consume` placement is explicit in the C rather
 * than derived (imp bumps right after the call, mpy at the join, oc after
 * an unrelated store; no single scheduling rule matches all three).
 */
