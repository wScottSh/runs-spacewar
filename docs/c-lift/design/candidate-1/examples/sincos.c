/*
 * sin / cos (Adams Associates). Source lines 195-254, words 00066-00155.
 * Argument: binary point right of bit 3, range +-2 pi. Answer: binary
 * point right of bit 0.
 */

#define PI_2   062210           /* pi/2 */
#define TWO_PI 0311040          /* 2 pi */

#pragma pdp1 jda(mpy, inline=b:exec)
dword mpy(word a, word b);      /* imp.c */

#pragma pdp1 jda(cos)
#pragma pdp1 jda(sin)
word cos(word th);
word sin(word th);

static word c;                  /* scratch for sin; its storage is cos's entry word */
#pragma pdp1 overlay(c, cos)

word cos(word th)               /* 00066 000000  cos, 0                                  ok */
{                               /* 00067 260142  dap csx   C4: every return is a tail
                                                           call to sin, so cos patches
                                                           sin's slot instead of owning one ok */
    return sin(PI_2 + th);      /* 00070 202767  lac (62210  leading const > 7777 -> literal ok
                                   00071 400066  add cos                                  ok
                                   00072 240074  dac sin   C4: arg into callee entry word  ok
                                   00073 600077  jmp .+4   enter sin after its prologue AND
                                                           after its `lac sin`: AC cache
                                                           says AC == sin's parameter      ok */
}

word sin(word th)               /* 00074 000000  sin, 0                                  ok */
{                               /* 00075 260142  dap csx                                  ok */
    word x, p, r;               /* AC locals (declared at the top: see compiler.md R1) */
    x = th;                     /* 00076 200074  lac sin                                  ok */
    if (x < 0)                  /* 00077 640200  spa       L2: one-word body             ok */
si1:    x += TWO_PI;            /* 00100 402770  add (311040                              ok */
    x -= PI_2;                  /* 00101 422767  sub (62210   pool dedup: same word as cos ok */
    if (x >= 0) goto si2;       /* 00102 640400 sma ; 00103 600143 jmp si2      L1        ok */
    x += PI_2;                  /* 00104 402767  add (62210                               ok */
si3:
    th = mpy(ral(x, 2), 0242763).ac;
                                /* 00105 661003 ral 2s ; 00106 170171 jda mpy ;
                                   00107 202771 lac (242763  exec operand: caller emits load ;
                                   00110 240074 dac sin                                   ok */
    c = mpy(th, th).ac;         /* 00111 170171 jda mpy  (AC cache: AC == th, no reload) ;
                                   00112 200074 lac sin ; 00113 240066 dac cos             ok */
    p = mpy(c, 0756103).ac + 0121312;
                                /* 00114 170171 jda mpy ; 00115 202772 lac (756103 ;
                                   00116 402773 add (121312                               ok */
    p = mpy(p, c).ac + 0532511; /* 00117 170171 ; 00120 200066 lac cos ; 00121 402774     ok */
    p = mpy(p, c).ac + 0144417; /* 00122 170171 ; 00123 200066 lac cos ; 00124 402775     ok */
    c = scl(mpy(p, th), 3).ac;  /* 00125 170171 ; 00126 200074 lac sin ;
                                   00127 667007 scl 3s ; 00130 240066 dac cos             ok */
    if ((c ^ th) < 0) {         /* 00131 060074 xor sin ; 00132 640400 sma ;
                                   00133 600141 jmp csx-1     L3: multi-statement body    ok */
        r = 0377777;            /* 00134 202776  lac (377777                              ok */
        if (th < 0) r = -r;     /* 00135 220074 lio sin  AC busy -> test via IO ;
                                   00136 642000 spi ; 00137 761000 cma                    ok */
        return r;               /* 00140 600142  jmp csx    not the last return           ok */
    }
    return c;                   /* 00141 200066 lac cos ; 00142 600142 csx: jmp .
                                                         last return hosts the slot      ok */
si2:
    x = -x + PI_2;              /* 00143 761000 cma ; 00144 402767 add (62210             ok */
    if (x >= 0) goto si3;       /* 00145 640400 sma ; 00146 600105 jmp si3                ok */
    x += PI_2;                  /* 00147 402767  add (62210                               ok */
    if (x >= 0) {               /* 00150 640200 spa ; 00151 600154 jmp .+3   L3           ok */
        x -= PI_2;              /* 00152 422767  sub (62210                               ok */
        goto si3;               /* 00153 600105  jmp si3                                  ok */
    }
    x -= PI_2;                  /* 00154 422767  sub (62210                               ok */
    goto si1;                   /* 00155 600100  jmp si1  x is live in AC on every edge   ok */
}

/*
 * 00066-00155: 56 words, all reproduced by the rules below.
 *   C1/C3 jda prologue and last-return slot; C4 shared-exit tail call (cos).
 *   C2 call to an exec-inline jda function: first arg in AC, operand as a
 *      one-word load after the jda (`lac (K`, `lac sin`, `lac cos`).
 *   R2 AC cache: `dac sin` then `mpy(th, ...)` needs no reload; the cos
 *      tail call enters past sin's `lac sin` for the same reason.
 *   R3 sign test of a memory operand while AC is live goes through IO.
 *   P3 overlay: c shares cos's entry word (cos is never active while sin
 *      uses c: cos's only exit is the tail call that enters sin).
 * Literal order: 62210 311040 242763 756103 121312 532511 144417 377777
 *   = pool words 02767..02776 in first-appearance order, as macro1 builds it.
 *   14 literal occurrences (pass-1 pool reservation counts every one).
 * Missing rules: none. Fragile point: entering sin "after its parameter
 * load" needs cos and sin in one compilation unit (one splice region).
 */
