/*
 * Tunable constant table (source lines 77-96, words 00006-00031) and two
 * xct call sites: md1 (line 733) and the torpedo launch velocity in sr2
 * (lines 1274-1286).
 *
 * The 1962 comment says every entry "is executed, and may be replaced by
 * jda or jsp". In C an executed entry is a function whose body is one
 * instruction; `#pragma pdp1 xct(f)` places that instruction at f and
 * makes calls `xct f`. Swapping the pragma for jda/jsp turns it into an
 * ordinary subroutine without touching any caller's C. Data entries are
 * plain initialized words.
 */
#include "spacewar.h"

#pragma pdp1 org(06)

#pragma pdp1 xct(tno)
word tno(void) { return -041; }          /* 00006 710041  law i 41   torps + 1        ok */
#pragma pdp1 xct(tvl)
word tvl(word v) { return v >> 4; }      /* 00007 675017  sar 4s     torpedo velocity  ok */
#pragma pdp1 xct(rlt)
word rlt(void) { return -020; }          /* 00010 710020  law i 20   reload time       ok */
#pragma pdp1 xct(tlf)
word tlf(void) { return -0140; }         /* 00011 710140  law i 140  torpedo life      ok */
word foo = -020000;                      /* 00012 757777  fuel supply (ones' compl.)   ok */
word maa = 010;                          /* 00013 000010  angular acceleration         ok */
#pragma pdp1 xct(sac)
word sac(word v) { return v >> 4; }      /* 00014 675017  sar 4s     ship acceleration ok */
word str = 1;                            /* 00015 000001  star capture radius          ok */
word me1 = 06000;                        /* 00016 006000  collision radius             ok */
word me2 = 03000;                        /* 00017 003000  me1 / 2                      ok */
word ddd = 0777777;                      /* 00020 777777  -0 (bit pattern)             ok */
#pragma pdp1 xct(the)
word the(word v) { return v >> 9; }      /* 00021 675777  sar 9s     space warpage     ok */
#pragma pdp1 xct(mhs)
word mhs(void) { return -010; }          /* 00022 710010  law i 10   hyperspace shots  ok */
#pragma pdp1 xct(hd1)
word hd1(void) { return -040; }          /* 00023 710040  law i 40                     ok */
#pragma pdp1 xct(hd2)
word hd2(void) { return -0100; }         /* 00024 710100  law i 100                    ok */
#pragma pdp1 xct(hd3)
word hd3(void) { return -0200; }         /* 00025 710200  law i 200                    ok */
#pragma pdp1 xct(hr1)
dword hr1(dword d) { return scl(d, 9); } /* 00026 667777  scl 9s                       ok */
#pragma pdp1 xct(hr2)
dword hr2(dword d) { return scl(d, 4); } /* 00027 667017  scl 4s                       ok */
word hur = 040000;                       /* 00030 040000  hyperspatial uncertainty     ok */
word ran = 0;                            /* 00031 000000  random number state          ok */

/* ---- call site 1: md1 (main loop restart delay), lines 733-735 ---- */
void md1_site(void)
{
    ntd = tlf() << 1;        /* 01530 100011 xct tlf ; 01531 665001 sal 1s ;
                                01532 243254 dac \ntd                              ok */
}

/* ---- call site 2: torpedo launch in sr2, lines 1274-1286 ---- */
static word *sr6;
#pragma pdp1 homed(sr6)
void sr2_site(void)
{
sr3: *sr3 = -tvl(sn) + *mdx; /* 02650 203267 lac \sn ; 02651 100007 xct tvl ;
                                02652 761000 cma ; 02653 413244 add i \mdx ;
                                02654 242654 sr3: dac .   homed, starts as `.`     ok */
sr4: *sr4 = tvl(cs) + *mdy;  /* 02655 203272 lac \cs ; 02656 100007 xct tvl ;
                                02657 413245 add i \mdy ; 02660 242660 sr4: dac .   ok */
     *ma1 = rlt();           /* 02661 100010 xct rlt ; 02662 251772 dac i ma1
                                (ma1 is homed in the main loop, so here: i ma1)    ok */
sr6: *sr6 = tlf();           /* 02663 100011 trf: xct tlf ; 02664 242664 sr6: dac . ok */
}

/*
 * Rules: X1 xct functions (definition = its single instruction, call =
 *   `xct f` with the argument already in AC, or AC:IO for dword); S1
 *   constant rules (-041 -> law i 41 inside an xct body is the same
 *   constant rule as anywhere else); H1/H2 homed pointer at its labeled
 *   statement vs `i host` elsewhere.
 * The md1_site / sr2_site wrappers exist only so this file parses alone;
 * in the real lift these statements sit inside ml0 and ss1.
 * Missing rules: none for these words. `trf` (a label nothing references)
 * is not reproduced as a symbol; extra or missing labels do not change the
 * .rim (checked: adding a label at line 318 left the sha256 unchanged).
 */
