/*
 * oc -- the outline compiler: runtime code generation. Source lines
 * 417-507, words 00404-00647. Plus the ss1 call site that runs the
 * generated code (lines 1214-1217, words 02526-02531).
 *
 * oc is a JIT in the ordinary C sense: it encodes PDP-1 instructions as
 * integers (LAC(&sx1), DPY(04000), ...), stores them through a cursor,
 * and the generated block is later entered through a code pointer. The
 * generated block's calling convention (enter by jmp, leave by jumping to
 * sq6) is declared on its C function type, outline_fn, in spacewar.h.
 *
 * Call: `jda oc` with AC = where to compile to, followed by a data word
 * holding the outline table address. Returns AC = next free word.
 */
#include "spacewar.h"

/* Macro variables; first used here, so macro1 allocates them first
   (03223 sx1, 03224 sy1, 03225 occ, 03226 oci, 03227 scm ...). */
word sx1, sy1, occ, oci, scm, ssm, csm, ssd, ssc, csn, ssn, scn, ssa, ssi;

#pragma pdp1 jda(oc, inline=table:data)
insn *oc(insn *to, const word *table);

insn *oc_to;                       /* the compile cursor; its cell is oc's entry word */
#pragma pdp1 overlay(oc_to, oc)

/* ocs: append the two-word swap (IO holds `rcl 9s`). */
#pragma pdp1 jsp(ocs)
void ocs(register insn w)          /* 00404 260411  ocs: dap ocz                         ok */
{
    *oc_to++ = w;                  /* 00405 330412 dio i oc ; 00406 440412 idx oc       ok */
    *oc_to++ = w;                  /* 00407 330412 dio i oc ; 00410 440412 idx oc       ok */
}                                  /* 00411 600411  ocz: jmp .  implicit last return     ok */

static word *ocg;                  /* outline table cursor, homed in `ocg: lio .` */
static insn *ocm, *ocn;            /* code addresses kept in standalone `jmp` words */
#pragma pdp1 homed(ocg)
#pragma pdp1 homed_word(ocm, jmp)
#pragma pdp1 homed_word(ocn, jmp)

insn *oc(insn *to, const word *table)
                                   /* 00412 000000  oc, 0                                ok */
{                                  /* 00413 260554  dap ocx  data-operand link = slot    ok */
    dword d;                       /* d.io: outline bits, then the `rcl 9s` for ocs */
    insn w;                        /* AC local: the word about to be appended */

    oc_to = to;                    /* same cell (overlay): self-copy, no code           ok */
    ocg = (word *)table;           /* 00414 210554 lac i ocx  read data operand ;
                                      00415 260434 dap ocg                              ok */
    *oc_to++ = STF(5);             /* 00416 203000 lac (stf 5 ; 00417 250412 dac i oc ;
                                      00420 440412 idx oc                               ok */
    ocm = oc_to;                   /* 00421 260555 dap ocm  AC cache: idx left oc_to   ok */
    consume(table);                /* 00422 440554 idx ocx                              ok */
    *oc_to++ = LAC(&sx1);          /* 00423 203001 ; 00424 250412 ; 00425 440412        ok */
    *oc_to++ = LIO(&sy1);          /* 00426 203002 ; 00427 250412 ; 00430 440412        ok */
    clf(6);                        /* 00431 760006 clf 6                                ok */
    for (;;) {
        occ = -6;                  /* 00432 710006 ocj: law i 6 ; 00433 243225 dac \occ ok */
ocg:    d.io = *ocg;               /* 00434 220434 ocg: lio .                           ok */
        do {
            d.ac = 0;              /* 00435 760200 och: cla                             ok */
            d = rcl(d, 3);         /* 00436 663007 rcl 3s                               ok */
            oci = d.io;            /* 00437 323226 dio \oci                             ok */
            d.io = RCL(9);         /* 00440 223003 lio (rcl 9s                          ok */
            switch (d.ac) {        /* W1 dense 0..7, no default:
                                      00441 403004 add (.+3 ; 00442 260443 dap .+1 ;
                                      00443 600443 jmp .                                ok */
            case 0: ;              /* 00444 760000 opr   empty case pads its slot       ok */
            case 1: goto oc1;      /* 00445 600557                                      ok */
            case 2: goto oc2;      /* 00446 600602                                      ok */
            case 3: goto oc3;      /* 00447 600610                                      ok */
            case 4: goto oc4;      /* 00450 600616                                      ok */
            case 5: goto oc5;      /* 00451 600624                                      ok */
            case 6: goto oc6;      /* 00452 600632                                      ok */
            case 7:                /* last case: its body starts in its slot (00453) */
                *oc_to++ = SZF(5);        /* 00453 203005 ; 00454 250412 ; 00455 440412 ok */
                ocn = oc_to + 4;          /* 00456 403006 add (4 ; 00457 260556 dap ocn ok */
                *oc_to++ = JMP(ocn);      /* H4: JMP(p), p homed in a jmp word, is that
                                             word: 00460 200556 lac ocn ; 00461 ; 00462 ok */
                *oc_to++ = DAC(&sx1);     /* 00463 203007 ...                           ok */
                *oc_to++ = DIO(&sy1);     /* 00466 203010 ...                           ok */
                *oc_to++ = JMP(&sq6);     /* 00471 203011  (jmp sq6 = 602531            ok */
                *oc_to++ = CLF(5);        /* 00474 203012                               ok */
                *oc_to++ = LAC(&scm);     /* 00477 203013                               ok */
                *oc_to++ = CMA;           /* 00502 203014                               ok */
                *oc_to++ = DAC(&scm);     /* 00505 203015                               ok */
                *oc_to++ = LAC(&ssm);     /* 00510 203016                               ok */
                *oc_to++ = CMA;           /* 00513 203014  same pool word as 00502      ok */
                *oc_to++ = DAC(&ssm);     /* 00516 203017                               ok */
                *oc_to++ = LAC(&csm);     /* 00521 203020                               ok */
                *oc_to++ = LIO(&ssd);     /* 00524 203021                               ok */
                *oc_to++ = DAC(&ssd);     /* 00527 203022                               ok */
                *oc_to++ = DIO(&csm);     /* 00532 203023                               ok */
                *oc_to++ = LAC(&ssc);     /* 00535 203024                               ok */
                *oc_to++ = LIO(&csn);     /* 00540 203025                               ok */
                *oc_to++ = DAC(&csn);     /* 00543 203026                               ok */
                *oc_to++ = DIO(&ssc);     /* 00546 203027                               ok */
                *oc_to++ = JMP(ocm);      /* 00551 200555 lac ocm ; 00552 ; 00553       ok */
                return oc_to;             /* 00554 600554 ocx: jmp .  AC == oc_to       ok */
            }
#pragma pdp1 place(ocm, ocn)
                                   /* 00555 600555 ocm: jmp . ; 00556 600556 ocn: jmp . ok */
oc1:        *oc_to++ = ADD(&ssn);  /* 00557 203030 ; 00560 250412 ; 00561 440412        ok */
            ocs(d.io);             /* 00562 620404 jsp ocs  (IO already d.io)           ok */
            w = SUB(&scn);         /* 00563 203031 lac (sub \scn                        ok */
oce:        *oc_to++ = w;          /* 00564 250412 oce: dac i oc ; 00565 440412 idx oc  ok */
            ocs(d.io);             /* 00566 620404 jsp ocs  (ocs preserves IO)          ok */
            *oc_to++ = IOH;        /* 00567 203032 ; 00570 ; 00571                      ok */
            w = DPY(04000);        /* 00572 203033 lac (dpy-4000                        ok */
ocd:        *oc_to++ = w;          /* 00573 250412 ocd: dac i oc ; 00574 440412         ok */
            d.io = oci;            /* 00575 223226 lio \oci                             ok */
        } while (++occ < 0);       /* 00576 463225 isp \occ ; 00577 600435 jmp och      ok */
        ++ocg;                     /* 00600 440434 idx ocg                              ok */
    }                              /* 00601 600432 jmp ocj                              ok */

oc2: *oc_to++ = ADD(&scm); ocs(d.io); w = ADD(&ssm); goto oce;
                                   /* 00602 203034 ; 00603 250412 ; 00604 440412 ;
                                      00605 620404 ; 00606 203035 ; 00607 600564        ok */
oc3: *oc_to++ = ADD(&ssc); ocs(d.io); w = SUB(&csm); goto oce;
                                   /* 00610-00615 (203036 ... 203037 600564)            ok */
oc4: *oc_to++ = SUB(&scm); ocs(d.io); w = SUB(&ssm); goto oce;
                                   /* 00616-00623 (203040 ... 203041 600564)            ok */
oc5: *oc_to++ = ADD(&csn); ocs(d.io); w = SUB(&ssd); goto oce;
                                   /* 00624-00631 (203042 ... 203043 600564)            ok */
oc6: if (flag(6)) goto oc9;        /* 00632 640006 szf 6 ; 00633 600642 jmp oc9         ok */
     stf(6);                       /* 00634 760016                                      ok */
     *oc_to++ = DAC(&ssa);         /* 00635 203044 ; 00636 ; 00637                      ok */
     w = DIO(&ssi);                /* 00640 203045                                      ok */
     goto ocd;                     /* 00641 600573                                      ok */
oc9: clf(6);                       /* 00642 760006                                      ok */
     *oc_to++ = LAC(&ssa);         /* 00643 203046 ; 00644 ; 00645                      ok */
     w = LIO(&ssi);                /* 00646 203047                                      ok */
     goto ocd;                     /* 00647 600573                                      ok */
}

/* ---- the call site in ss1 that runs the generated block ---- */
void ss1_display_fragment(void)
{
    dpy(0, 0, 04000);              /* 02526 764200 cla cli-opr  (two register zeroings
                                      from one call merge into one operate word) ;
                                      02527 724007 dpy-4000                             ok */
sp5: (*sp5)();                     /* 02530 602530 sp5: jmp .   jmp ABI: the call IS
                                      the host of the code pointer sp5                 ok */
sq6: ioh();                        /* 02531 730000 sq6: ioh   exported return label     ok */
}

/*
 * 00404-00647: 164 words reproduced; 02526-02531 reproduced.
 * Literal occurrences: 41, in first-appearance order 03000..03047 (pool
 *   dedup makes the second (cma share 03014).
 * Rules: C1 jda, C3 slot, data inline operand (`lac i slot`, consume ->
 *   `idx slot`); C7 jsp with a register (IO) parameter; P3 overlay + self-
 *   copy elimination; H1 homed; H4 homed_word + host-word identity; P4
 *   place; W1 dense switch -> dispatch; R2 AC cache (idx leaves the new
 *   cursor in AC); interprocedural clobber summary (ocs keeps IO).
 * Missing / weak:
 *   - `case 0: ;` (empty case -> `opr`) versus `case 0: case 1:` (both
 *     slots `jmp oc1`) is a real distinction in the rule, but it is
 *     subtle to a reader.
 *   - `place(ocm, ocn)` is a layout directive. C has no other way to say
 *     "these two data words sit between the return and oc1".
 *   - oc_to = to is dropped because both names are one cell; the
 *     reference C needs it, the binary does not. swc proves it is a
 *     self-copy rather than trusting the author.
 */
