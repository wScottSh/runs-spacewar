/* tunables.c -- source lines 72-96 (listing 00006-00031) plus two xct sites.
 *
 * Every entry of the table is one word at a fixed address.  An entry that is
 * an *operation* is a PDP1_XCT function: its body must lower to exactly one
 * non-transfer word, it gets no entry cell and no link, and every call site
 * lowers to `xct <entry>` with the argument (if any) in AC.  An entry that is
 * *data* is an initialized word.  Swapping an entry between the two is a
 * one-line C edit, which is the "may be replaced by jda or jsp" remark in the
 * original comment (a jda/jsp replacement would be a different call
 * convention and is written as an ordinary function with a different caller;
 * see compiler.md "xct cells").                                              */
#include "../pdp1.h"

PDP1_ORG(6)
PDP1_XCT word tno(void)       { return -041; }       /* 6   law i 41   torps+1   */
PDP1_XCT word tvl(word a)     { return sar(a, 4); }  /* 7   sar 4s     velocity  */
PDP1_XCT word rlt(void)       { return -020; }       /* 10  law i 20   reload    */
PDP1_XCT word tlf(void)       { return -0140; }      /* 11  law i 140  life      */
word foo = -020000;                                  /* 12  fuel                 */
word maa = 010;                                      /* 13  angular accel        */
PDP1_XCT word sac(word a)     { return sar(a, 4); }  /* 14  sar 4s     accel     */
word str = 1;                                        /* 15  star radius          */
word me1 = 06000;                                    /* 16  collision radius     */
word me2 = 03000;                                    /* 17  above/2              */
word ddd = NEG0;                                     /* 20  -0                   */
PDP1_XCT word the(word a)     { return sar(a, 9); }  /* 21  sar 9s     warpage   */
PDP1_XCT word mhs(void)       { return -010; }       /* 22  law i 10   hyper shots */
PDP1_XCT word hd1(void)       { return -040; }       /* 23  law i 40             */
PDP1_XCT word hd2(void)       { return -0100; }      /* 24  law i 100            */
PDP1_XCT word hd3(void)       { return -0200; }      /* 25  law i 200            */
PDP1_XCT word hr1(word a)     { return scl(a, 9); }  /* 26  scl 9s               */
PDP1_XCT word hr2(word a)     { return scl(a, 4); }  /* 27  scl 4s               */
word hur = 040000;                                   /* 30                       */
word ran = 0;                                        /* 31                       */

/* ---- call site 1: torpedo launch, source 1273-1285, listing 02650-02664 --- */

extern word sn, cs;                  /* variable-pool cells \sn, \cs            */
extern word *mdx, *mdy;              /* variable-pool pointers into mtb columns */
extern cptr ma1, sr3, sr4, sr6;      /* sr3/sr4/sr6: `dac .` cells, homed here  */

PDP1_FRAGMENT void launch_slice(void)
{
    HERE(sr3) = -tvl(sn) + *mdx;     /* lac \sn ; xct tvl ; cma ; add i \mdx ; sr3: dac . */
    HERE(sr4) = tvl(cs) + *mdy;      /* lac \cs ; xct tvl ; add i \mdy ; sr4: dac .       */
    *ma1 = rlt();                    /* xct rlt ; dac i ma1                                */
trf:
    HERE(sr6) = tlf();               /* xct tlf ; sr6: dac .                               */
}

/* ---- call site 2: game start, source 816-818, listing 01655-01657 --------- */

extern word ntr[2];                  /* torps remaining, one per ship           */

PDP1_FRAGMENT void a2_slice(void)
{
    ntr[1] = ntr[0] = tno();         /* xct tno ; dac ntr ; dac ntr+1           */
}
