/* mainloop.c -- source lines 663-690 (ml0 pointer set-up, first half) and
 * 843-941 (the object loop, collision scan, indirect calc call).
 * Listing 01444-01467 and 01703-02051.
 *
 * Objects live in parallel columns of mtb, NOB entries each.  A *cursor*
 * (cptr) walks one column.  Its home is an instruction cell: the code stream
 * both holds the pointer (in the cell's address field) and uses it
 * (HERE(p) executes the cell).  ++p is `idx p`; p = q is `dap p`.           */
#include "../pdp1.h"

#define NOB 030
extern word mtb[];                       /* label only; storage after patch space */

/* cursors whose HERE site is in this file */
cptr ml1, ml2, mx1, mx2, my1, my2, ma1, ma2, mb1, mb2, mot;
/* cursors whose HERE site is elsewhere (ss1 and the ship code) */
extern cptr mom, mth, mco, sp5;
/* variable-pool pointers (plain `word *`, dac/idx, no opcode) */
extern word *mdx, *mdy, *mas, *mfu, *mtr, *mh1, *mh2, *mh3, *mh4;
extern word moc, mt1, mtc;               /* variable-pool words                   */
extern word me1, me2;                    /* tunables, tunables.c                  */

PDP1_JSP void mex(void);
PDP1_JSP void bck(void);                 /* the `background` macro is `jsp bck`  */
PDP1_JSP void blp(void);
PDP1_CONT _Noreturn void ml0(void);

/* ---- ml0: set up the column cursors (first half) ------------------------ */

PDP1_FRAGMENT void ml0_setup(void)
{
    IO = -04000;                         /* load \mtc,-4000 : lio (-4000 ; dio \mtc */
    mtc = IO;
    word *p = mtb;                       /* law mtb                                 */
    ml1 = p;                             /* dap ml1                                 */
    p += NOB;  mx1 = p;                  /* add (nob ; dap mx1                      */
    p += NOB;  my1 = p;
    p += NOB;  ma1 = p;
    p += NOB;  mb1 = p;
    p += NOB;  mdx = p;                  /* add (nob ; dac \mdx  (pool pointer: dac) */
    p += NOB;  mdy = p;
    p += NOB;  mom = p;
    p += 2;    mth = p;                  /* add (2 ; dap mth                        */
}

/* ---- the object loop ----------------------------------------------------- */

PDP1_CONT _Noreturn void object_loop(void)
{
    word w, v, d, t;

ml1_top:
    w = HERE(ml1);                       /* ml1: lac .   first control word        */
    if (w == 0) goto mq1;                /* sza i ; jmp mq1   inactive             */
    (void)swap(w);                       /* rcl 9s ; rcl 9s                        */
    moc++;                               /* idx \moc                               */
    if (IO < 0) goto mq4;                /* spi ; jmp mq4   sign: does not collide */
    ml2 = ml1 + 1;                       /* law 1 ; add ml1 ; dap ml2              */
    mx2 = mx1 + 1;
    my2 = my1 + 1;
    ma2 = ma1 + 1;
    mb2 = mb1 + 1;
    sp5 = (cptr)(uintptr_t)HERE(mot);             /* mot: lac . ; dap sp5                   */

ml2_top:
    v = HERE(ml2);                       /* ml2: lac .   second control word       */
    if (v <= 0) goto mq2;                /* spq ; jmp mq2   can it collide?        */
    d = HERE(mx1) - HERE(mx2);           /* mx1: lac . ; mx2: sub .                */
    if (d < 0) d = ~d;                   /* spa ; cma                              */
    mt1 = d;                             /* dac \mt1                               */
    d -= me1;                            /* sub me1                                */
    if (d >= 0) goto mq2;                /* sma ; jmp mq2                          */
    d = HERE(my1) - HERE(my2);
    if (d < 0) d = ~d;
    d -= me1;
    if (d >= 0) goto mq2;
    d += mt1;                            /* add \mt1                               */
    d -= me2;                            /* sub me2                                */
    if (d >= 0) goto mq2;
    t = FN_ADDR(mex) + SIGN;             /* lac (mex 400000   yes: EXPLODE         */
    *ml1 = t;                            /* dac i ml1                              */
    *ml2 = t;                            /* dac i ml2                              */
    t = sar(~(*mb1 + HERE(mb2)), 8) + 1; /* lac i mb1 ; mb2: add . ; cma ; sar 8s ; add (1 */
    HERE(ma1) = t;                       /* ma1: dac .                             */
    HERE(ma2) = t;                       /* ma2: dac .                             */
mq2:
    mx2++;  my2++;  ma2++;  mb2++;       /* idx mx2 ; idx my2 ; idx ma2 ; idx mb2  */
    if (++ml2 != (cptr)(mtb + NOB)) goto ml2_top;   /* index ml2,(lac mtb nob,ml2   */

mq4:
    CALL_FN(*ml1);                       /* lac i ml1 ; dap .+1 ; jsp .            */
    mtc = HERE(mb1) + mtc;               /* mb1: lac . ; add \mtc ; dac \mtc       */
mq1:
    mx1++;  my1++;  ma1++;  mb1++;       /* idx mx1 .. idx mb1   (cursors)         */
    mdx++;  mdy++;                       /* idx \mdx ; idx \mdy  (pool pointers)   */
    mom++;  mth++;
    mas++;  mfu++;  mtr++;
    mot++;  mco++;
    mh1++;  mh2++;  mh3++;  mh4++;
    if (++ml1 != (cptr)(mtb + NOB - 1)) goto ml1_top; /* index ml1,(lac mtb nob-1,ml1 */
    w = *ml1;                            /* lac i ml1   display and compute last   */
    if (w == 0) goto mq3;                /* sza i ; jmp mq3                        */
    CALL_FN(w);                          /* dap .+1 ; jsp .   (AC still holds w)   */
    mtc = *mb1 + mtc;                    /* lac i mb1 ; add \mtc ; dac \mtc        */
mq3:
    bck();                               /* jsp bck                                */
    blp();                               /* jsp blp                                */
mq3w:
    if (++mtc < 0) goto mq3w;            /* count \mtc,. : isp \mtc ; jmp .        */
    ml0();                               /* jmp ml0                                */
}
