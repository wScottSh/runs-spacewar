/*
 * Main loop: object loop ml1..mq1, the indirect calc-routine call, and the
 * tail through mq3. Source lines 843-941, words 01703-02051.
 *
 * Every m* cursor is a pointer homed in the address field of the
 * instruction that dereferences it in the statement carrying its label.
 * The cursors walk the parallel arrays of mtb in lockstep.
 */
#include "spacewar.h"

#pragma pdp1 jmp(mloop)
_Noreturn void mloop(void)      /* entry = 01703 (ml1). Macro's `jmp ml1` lands here. */
{
    word ady, t;                /* AC locals */
    register word w;            /* IO local */

    do {
ml1:    if (*ml1 == 0)          /* 01703 201703 ml1: lac .  host, starts as `.` ;
                                   01704 650100 sza i                                  ok */
            goto mq1;           /* 01705 602011 jmp mq1                                ok */
        w = *ml1;               /* AC cache hit (AC == *ml1): implicit AC->IO = swap
                                   01706 663777 rcl 9s ; 01707 663777 rcl 9s           ok */
        ++moc;                  /* 01710 443261 idx \moc   (IO untouched)              ok */
        if (w < 0) goto mq4;    /* 01711 642000 spi ; 01712 602003 jmp mq4  L1 on IO   ok */
        ml2 = 1 + ml1;          /* 01713 700001 law 1 ; 01714 401703 add ml1 ;
                                   01715 261734 dap ml2   leading 1 -> law; homed
                                   rvalue = host word; store to homed -> dap          ok */
        mx2 = 1 + mx1;          /* 01716 700001 ; 01717 401737 add mx1 ; 01720 261740  ok */
        my2 = 1 + my1;          /* 01721 700001 ; 01722 401747 ; 01723 261750          ok */
        ma2 = 1 + ma1;          /* 01724 700001 ; 01725 401772 ; 01726 261773          ok */
        mb2 = 1 + mb1;          /* 01727 700001 ; 01730 402006 ; 01731 261766          ok */
mot:    sp5 = (outline_fn *)*mot;
                                /* 01732 201732 mot: lac . ; 01733 262530 dap sp5
                                   (sp5 is homed in ss1's `sp5, jmp .`)                ok */
        do {
ml2:        if (*ml2 <= 0)      /* 01734 201734 ml2: lac . ; 01735 650500 spq          ok */
                goto mq2;       /* 01736 601774 jmp mq2                                ok */
mx1: mx2:   mt1 = mag(*mx1 - *mx2);
                                /* 01737 201737 mx1: lac . ; 01740 421740 mx2: sub . ;
                                   01741 640200 spa ; 01742 761000 cma ;
                                   01743 243262 dac \mt1                               ok */
            if (mt1 - me1 >= 0) /* AC cache: AC == mt1.  01744 420016 sub me1 ;
                                   01745 640400 sma                                    ok */
                goto mq2;       /* 01746 601774                                        ok */
my1: my2:   ady = mag(*my1 - *my2) - me1;
                                /* 01747 201747 ; 01750 421750 ; 01751 640200 ;
                                   01752 761000 ; 01753 420016 sub me1                 ok */
            if (ady >= 0)       /* 01754 640400 sma                                    ok */
                goto mq2;       /* 01755 601774                                        ok */
            if (ady + mt1 - me2 >= 0)
                                /* 01756 403262 add \mt1 ; 01757 420017 sub me2 ;
                                   01760 640400 sma                                    ok */
                goto mq2;       /* 01761 601774                                        ok */
            *ml1 = NOCOLLIDE(mex);
                                /* 01762 203100 lac (mex 400000 ; 01763 251703 dac i ml1 ok */
            *ml2 = *ml1;        /* AC cache: AC == value just stored.
                                   01764 251734 dac i ml2                              ok */
mb2:        t = (-(*mb1 + *mb2) >> 8) + 1;
                                /* 01765 212006 lac i mb1 ; 01766 401766 mb2: add . ;
                                   01767 761000 cma ; 01770 675377 sar 8s ;
                                   01771 402777 add (1                                 ok */
ma1:        *ma1 = t;           /* 01772 241772 ma1: dac .                             ok */
ma2:        *ma2 = t;           /* 01773 241773 ma2: dac .                             ok */
mq2:        ++mx2; ++my2; ++ma2; ++mb2;
                                /* 01774 441740 ; 01775 441750 ; 01776 441773 ;
                                   01777 441766   idx each                             ok */
        } while (++ml2 != &mtb.calc[NOB]);
                                /* 02000 441734 idx ml2 ; 02001 523101 sas (lac mtb+30 ;
                                   02002 601734 jmp ml2
                                   H3: AC after idx is the host word, so the bound is
                                   compared as host-opcode | address                  ok */
mq4:    AS_FN(calc_fn, *ml1)(); /* 02003 211703 lac i ml1 ; 02004 262005 dap .+1 ;
                                   02005 622005 jsp .    C5 call through a word        ok */
mb1:    mtc = *mb1 + mtc;       /* 02006 202006 mb1: lac . ; 02007 403243 add \mtc ;
                                   02010 243243 dac \mtc                               ok */
mq1:    ++mx1; ++my1; ++ma1; ++mb1; ++mdx; ++mdy; ++mom; ++mth; ++mas;
        ++mfu; ++mtr; ++mot; ++mco; ++mh1; ++mh2; ++mh3; ++mh4;
                                /* 02011-02031: idx mx1 my1 ma1 mb1 \mdx \mdy mom mth
                                   \mas \mfu \mtr mot mco \mh1 \mh2 \mh3 \mh4
                                   (441737 441747 441772 442006 443244 443245 442327
                                    442343 443263 443246 443247 441732 442577 443250
                                    443251 443252 443253)                              ok */
    } while (++ml1 != &mtb.calc[NOB - 1]);
                                /* 02032 441703 idx ml1 ; 02033 523102 sas (lac mtb+27 ;
                                   02034 601703 jmp ml1                                ok */
    if (*ml1 != 0) {            /* 02035 211703 lac i ml1 ; 02036 650100 sza i ;
                                   02037 602045 jmp mq3   L3                           ok */
        AS_FN(calc_fn, *ml1)(); /* AC cache: AC == *ml1, no reload.
                                   02040 262041 dap .+1 ; 02041 622041 jsp .           ok */
        mtc = *mb1 + mtc;       /* 02042 212006 lac i mb1 ; 02043 403243 ; 02044 243243 ok */
    }
mq3:
    bck();                      /* 02045 621130 jsp bck  ("background")                ok */
    blp();                      /* 02046 620650 jsp blp                                ok */
    do {} while (++mtc < 0);    /* 02047 463243 isp \mtc ; 02050 602047 jmp .-1       ok */
    ml0();                      /* 02051 601444 jmp ml0  call to a jmp-ABI function    ok */
}

/*
 * 01703-02051: 103 words reproduced.
 * Literal occurrences in order: (lac mtb+30, (mex+400000, (1 (dedups to
 *   02777, first seen in sqt), (lac mtb+27.
 * Variable first-uses that fall in this region (\moc, \mt1, \mas) get their
 *   addresses from macro1's first-appearance rule; swc never assigns them.
 * Rules: H1 homed host at labeled statement (two labels on one statement
 *   home two pointers in the same expression); H2 `op i host` elsewhere;
 *   H3 homed rvalue is the host word (law 1 / add ml1 / dap; sas against
 *   `(lac bound`); R2 AC cache across a skip+jmp fall-through; R4 implicit
 *   AC->IO = swap; if layouts L1/L3; O2 do-while = body, then cond via skip+jmp;
 *   C5 call through a word; C6 call of a jmp-ABI function = `jmp f`.
 * Missing rules: none for these words.
 * Note: `mas` is incremented but never initialized anywhere in the source;
 *   the C keeps that faithfully (\mas is a dangling cursor).
 */
