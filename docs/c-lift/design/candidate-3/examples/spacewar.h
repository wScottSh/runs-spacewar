/* spacewar.h -- shared declarations for the lifted regions (examples only).
 * Each region's .c includes this; definitions live in the region that owns
 * the storage. An `extern` here with no definition anywhere in lifted C is a
 * symbol still defined by unlifted Macro text (splice build). */
#ifndef SPACEWAR_H
#define SPACEWAR_H

#define NOB 030                     /* colliding objects */

/* ---- tunables (region tunables.c, at 06..031); all are XCT routines or data */
XCT word tno(void);                 /* number of torps + 1 (negative count) */
XCT word tvl(word v);               /* torpedo velocity scale */
XCT word rlt(void);                 /* torpedo reload time */
XCT word tlf(void);                 /* torpedo life */
extern word foo, maa, str, me1, me2, ddd, hur, ran;
XCT word sac(word v);
XCT word the(word v);
XCT word mhs(void);
XCT word hd1(void), hd2(void), hd3(void);
XCT dword hr1(dword p), hr2(dword p);

/* ---- object table: struct-of-arrays after the patch space, never punched */
extern word mtb[NOB];               /* calc routine word: CODE(f) | NOCOLLIDE */
extern word nx1[NOB], ny1[NOB], na1[NOB], nb1[NOB], ndx[NOB], ndy[NOB];
extern word nom[2], nth[2], nfu[2], ntr[2];
extern code not[2];                 /* start of each ship's compiled outline */
extern word nco[2], nh1[2], nh2[2], nh3[2], nh4[2];
extern insn nnn[];                  /* compiled outline code goes here */
#define NOCOLLIDE SIGN

/* ---- the main loop's walking pointers, homed in its instructions */
extern HOMED word *ml1, *ml2, *mx1, *mx2, *my1, *my2;
extern HOMED word *ma1, *ma2, *mb1, *mb2, *mom, *mth, *mco;
extern HOMED code *mot;
extern HOMED code sp5;              /* `sp5, jmp .` in the ship routine */
extern label_t sq6;                 /* where compiled outline code returns */

/* ---- pool variables (`\x`): addresses assigned by first use in the text */
extern word *mdx POOL, *mdy POOL, *mas POOL, *mfu POOL, *mtr POOL;
extern word *mh1 POOL, *mh2 POOL, *mh3 POOL, *mh4 POOL;
extern word mtc POOL, moc POOL, mt1 POOL, ntd POOL, sn POOL, cs POOL;
extern word sx1 POOL, sy1 POOL, ssn POOL, scn POOL, scm POOL, ssm POOL;
extern word csm POOL, ssd POOL, ssc POOL, csn POOL, ssa POOL, ssi POOL;

/* ---- routines defined elsewhere */
JSP void mex(void);
JSP void bck(void);
JSP void blp(void);
BLOCK void ml0(void);
JDA dword mpy(word a, BYNAME word b);

#endif
