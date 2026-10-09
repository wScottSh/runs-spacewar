/*
 * spacewar.h -- declarations shared by the lifted regions.
 *
 * Anything a region references but does not define lives here. While a
 * region is still Macro text, its symbols are declared here and swc emits
 * plain references to them; when the region is lifted, its .c file
 * becomes the definition and nothing else changes.
 */
#ifndef SPACEWAR_H
#define SPACEWAR_H

#define NOB 030                 /* number of colliding objects */

/* The object table: parallel arrays, uninitialized, after patch space.
   Field offsets are the nx1/ny1/... equates of the original. */
struct objtab {
    word  calc[NOB];   /* calc routine address; sign bit: does not collide; 0: empty */
    word  x[NOB];
    word  y[NOB];
    word  count[NOB];  /* life of explosion or torpedo */
    word  ninst[NOB];  /* instructions the calc routine takes */
    word  dx[NOB];
    word  dy[NOB];
    word  om[2];       /* angular velocity (ships only) */
    word  th[2];       /* angle */
    word  fu[2];       /* fuel */
    word  tr[2];       /* torpedoes remaining */
    insn *ot[2];       /* compiled outline code */
    word  co[2];       /* previous control word */
    word  h1[2], h2[2], h3[2], h4[2];   /* hyperspace state */
};
extern struct objtab mtb;
#define nnn ((insn *)(&mtb + 1))   /* first free word after the table */

/* Pointers that live in instruction address fields. The host statement
   is the one labeled with the pointer's name (main loop, ss1, sr2...). */
#pragma pdp1 homed(ml1, ml2, mx1, mx2, my1, my2, ma1, ma2, mb1, mb2)
#pragma pdp1 homed(mot, mom, mth, mco, sr3, sr4)
extern word *ml1, *ml2, *mx1, *mx2, *my1, *my2, *ma1, *ma2, *mb1, *mb2;
extern word *mom, *mth, *mco, *sr3, *sr4;
extern insn **mot;

/* Macro variables (\name): uninitialized file-scope definitions. */
word mtc, moc, mt1, ntd, sn, cs;
word *mdx, *mdy, *mas, *mfu, *mtr, *mh1, *mh2, *mh3, *mh4;

/* Calc routines: entered by jsp from the object loop. */
typedef void calc_fn(void);
#pragma pdp1 jsp(calc_fn)
calc_fn ss1, ss2, tcr, hp1, hp3, mex;

/* Display routines. */
#pragma pdp1 jsp(bck)
#pragma pdp1 jsp(blp)
void bck(void);       /* background stars ("background" macro) */
void blp(void);       /* central star */

/* Runtime-generated outline code: entered by jmp from ss1 (sp5), returns
   by jumping to sq6, the instruction right after the call. */
typedef void outline_fn(void);
#pragma pdp1 jmp(outline_fn) returns_to(outline_fn, sq6)
#pragma pdp1 homed(sp5)
extern outline_fn *sp5;
extern code sq6;

/* Tunable constants (examples/tunables.c). */
word tno(void);
word tvl(word v);
word tlf(void);
extern word me1, me2;

/* Main loop entry: never returns, entered by jmp. */
#pragma pdp1 jmp(ml0)
_Noreturn void ml0(void);

#endif
