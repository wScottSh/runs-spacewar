/* Tunable constant table (source lines 77-96) and two xct call sites
 * (md1, lines 733-736; torpedo launch velocity, lines 1274-1282).
 * The table entries that are instructions are XCT routines: one-word
 * functions executed in place with `xct`. Replacing one with a longer body
 * is a compile error ("XCT body must be one word"); the original comment
 * says such entries "may be replaced by jda or jsp" -- in C, change the
 * attribute and the call sites follow. */
#include "spacewar.h"

AT(06)                                      /* 06 */
XCT word tno(void)        { return -041; }  /* number of torps + 1 */
XCT word tvl(word v)      { return v >> 4; }/* 07  torpedo velocity */
XCT word rlt(void)        { return -020; }  /* 10  torpedo reload time */
XCT word tlf(void)        { return -0140; } /* 11  torpedo life */
word foo = -020000;                         /* 12  fuel supply */
word maa = 010;                             /* 13  angular acceleration */
XCT word sac(word v)      { return v >> 4; }/* 14  spaceship acceleration */
word str = 1;                               /* 15  star capture radius */
word me1 = 06000;                           /* 16  collision "radius" */
word me2 = 03000;                           /* 17  above/2 */
word ddd = MINUS_ZERO;                      /* 20  0 to save space for ddt */
XCT word the(word v)      { return v >> 9; }/* 21  torpedo space warpage */
XCT word mhs(void)        { return -010; }  /* 22  hyperspace shots */
XCT word hd1(void)        { return -040; }  /* 23  time in hyperspace before breakout */
XCT word hd2(void)        { return -0100; } /* 24  breakout time */
XCT word hd3(void)        { return -0200; } /* 25  recharge time */
XCT dword hr1(dword p)    { scl(p.hi, p.lo, 9); return p; } /* 26 displacement scale */
XCT dword hr2(dword p)    { scl(p.hi, p.lo, 4); return p; } /* 27 induced velocity scale */
word hur = 040000;                          /* 30  hyperspatial uncertainty */
word ran = 0;                               /* 31  random number */

REGION_BREAK();

/* ---- call site 1: md1, inside the game-control BLOCK ml0 (lines 733-736) */
BLOCK SYM("ml1") void objloop(void);
extern word ntd POOL;

BLOCK void ml0_fragment(void)
{
    /* ... both ships out of torpedoes ... */
md1:
    ntd = tlf() << 1;                       /* restart delay is 2x torpedo life */
    objloop();                              /* BLOCK call: jmp */
}

REGION_BREAK();

/* ---- call site 2: torpedo launch velocity, inside ship calc (1274-1282) */
HOMED word *sr3, *sr4;                      /* homes below; set by `dap` above them */

BLOCK void ship_fragment(void)
{
    /* ... sr3 = &ndx[slot]; sr4 = &ndy[slot]; ... */
    *home(sr3) = -tvl(sn) + *mdx;           /* torpedo dx = ship dx - v*sin */
    *home(sr4) = tvl(cs) + *mdy;            /* torpedo dy = ship dy + v*cos */
    /* ... */
}
