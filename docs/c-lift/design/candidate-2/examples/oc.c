/* oc.c -- source lines 398-507, the outline compiler (runtime code generation).
 * Listing 00404-00643.
 *
 * oc writes instruction words into memory.  In C that is a store through a
 * word pointer; the words are instruction constants (I_* macros), and the
 * pointer is the routine's own entry cell, so ocs (a second routine) can keep
 * writing through the same pointer.  The generated code is entered through
 * the cursor sp5 (mainloop.c) and returns by jumping to sq6.                 */
#include "../pdp1.h"

/* variable-pool cells, in order of first use in this file */
extern word sx1, sy1, occ, oci, scm, ssm, csm, ssd, ssc, csn, ssn, scn, ssa, ssi;

PDP1_CONT _Noreturn void sq6(void);      /* resume point after the ship's `sp5: jmp .`
                                            (see compiler.md, open problem 2)       */

cptr ocg, ocm, ocn;                      /* ocg: homed by HERE below; ocm, ocn: plain
                                            `jmp .` storage cells (CELL_HERE)       */

PDP1_JDA void oc(word *where, inl_data table);   /* ac = where; next word = table */

/* ocs: append two copies of IO (the `swap` instruction, set up by oc) */
PDP1_JSP void ocs(void)
{
    *ENTRY_PTR(oc)++ = IO;               /* dio i oc ; idx oc */
    *ENTRY_PTR(oc)++ = IO;               /* dio i oc ; idx oc */
}

#define PLINST(x)    (*where++ = (x))    /* lac X ; dac i oc ; idx oc            */
#define COMTAB(A, B) do { PLINST(A); ocs(); t = (B); goto oce; } while (0)

PDP1_JDA void oc(word *where, inl_data table)    /* entry cell 00412 is `where`    */
{
    word t;                              /* the AC value that flows into oce / ocd */

    ocg = (cptr)(uintptr_t)table;        /* lac i ocx ; dap ocg   (inline data arg) */
    PLINST(I_STF(5));
    ocm = (cptr)where;                   /* dap ocm   (AC still = where)           */
    skip_inline(1);                      /* idx ocx                                 */
ock:
    PLINST(I_LAC(&sx1));
    PLINST(I_LIO(&sy1));
    clf(6);                              /* clf 6                                   */
ocj:
    occ = -6;                            /* setup \occ,6 : law i 6 ; dac \occ       */
    IO = HERE(ocg);                      /* ocg: lio .   next outline table word    */
och:
    t = rcl(0, 3);                       /* cla ; rcl 3s : top 3 bits -> AC          */
    oci = IO;                            /* dio \oci                                 */
    IO = I_RCL(9);                       /* lio (rcl 9s                              */
    switch (t) {                         /* dispatch: add (. 3 ; dap . 1 ; jmp .     */
    case 0: nop();                       /* opr -- falls into case 1's table slot    */
    case 1: goto oc1;
    case 2: goto oc2;
    case 3: goto oc3;
    case 4: goto oc4;
    case 5: goto oc5;
    case 6: goto oc6;
    case 7:                              /* last case: body follows the table       */
        PLINST(I_SZF(5));
        ocn = (cptr)(where + 4);         /* add (4 ; dap ocn                         */
        PLINST(CELL_WORD(ocn));          /* lac ocn ; dac i oc ; idx oc              */
        PLINST(I_DAC(&sx1));
        PLINST(I_DIO(&sy1));
        PLINST(I_JMP(FN_ADDR(sq6)));
        PLINST(I_CLF(5));
        PLINST(I_LAC(&scm));  PLINST(I_CMA);  PLINST(I_DAC(&scm));
        PLINST(I_LAC(&ssm));  PLINST(I_CMA);  PLINST(I_DAC(&ssm));
        PLINST(I_LAC(&csm));  PLINST(I_LIO(&ssd));  PLINST(I_DAC(&ssd));  PLINST(I_DIO(&csm));
        PLINST(I_LAC(&ssc));  PLINST(I_LIO(&csn));  PLINST(I_DAC(&csn));  PLINST(I_DIO(&ssc));
        PLINST(CELL_WORD(ocm));
        return;                          /* return cell `ocx: jmp .` is emitted here */
    }
    CELL_HERE(ocm, "jmp");               /* ocm, jmp .                               */
    CELL_HERE(ocn, "jmp");               /* ocn, jmp .                               */

oc1:
    PLINST(I_ADD(&ssn));
    ocs();                               /* jsp ocs                                  */
    t = I_SUB(&scn);                     /* lac (sub \scn                            */
oce:
    *where++ = t;                        /* dac i oc ; idx oc                        */
    ocs();
    PLINST(I_IOH);
    t = I_DPY_NW;                        /* lac (dpy-4000                            */
ocd:
    *where++ = t;
    IO = oci;                            /* lio \oci                                 */
    if (++occ < 0) goto och;             /* count \occ,och : isp \occ ; jmp och      */
    ocg++;                               /* idx ocg                                  */
    goto ocj;

oc2: COMTAB(I_ADD(&scm), I_ADD(&ssm));
oc3: COMTAB(I_ADD(&ssc), I_SUB(&csm));
oc4: COMTAB(I_SUB(&scm), I_SUB(&ssm));
oc5: COMTAB(I_ADD(&csn), I_SUB(&ssd));

oc6:
    if (flag(6)) goto oc9;               /* szf 6 ; jmp oc9                          */
    stf(6);
    PLINST(I_DAC(&ssa));
    t = I_DIO(&ssi);                     /* lac (dio \ssi                            */
    goto ocd;
oc9:
    clf(6);
    PLINST(I_LAC(&ssa));
    t = I_LIO(&ssi);
    goto ocd;
}
