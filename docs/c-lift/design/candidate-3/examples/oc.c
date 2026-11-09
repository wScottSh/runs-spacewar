/* Outline compiler (source lines 417-507): compiles a ship outline table
 * into straight-line PDP-1 code at run time. Call: oc(dst, ot) with dst in
 * AC (`jda oc`) and the table address as the inline word after the call.
 * Returns the next free address in AC.
 *
 * Each outline word holds six 3-bit codes. Codes 0-6 emit "step the pen and
 * plot" sequences; code 7 ends the outline and emits the mirror-image pass.
 * The emitted code returns to the ship routine at the exported label sq6.
 *
 * Runtime code generation in C: instructions are `insn` values built by
 * constant constructors (each becomes a Macro literal); writing them through
 * a pointer is plain data writing; the ship routine later transfers control
 * with jump(sp5). Patching a jump target is assignment to `.addr` (dap). */
#include "spacewar.h"

ENTRY_CELL(oc) insn *ocp;           /* oc's entry word: the output pointer */
static word occ;                    /* POOL: codes left in this table word */
static word oci;                    /* POOL: the rest of this table word */
HOMED const word *ocg;              /* home: `lio .` reading the table */

/* Store w twice: the two halves of a `swap` (rcl 9s / rcl 9s). */
JSP void ocs(register insn w)
{
    *ocp++ = w;
    *ocp++ = w;
}

/* plinst + jsp ocs + second instruction, shared by codes 2-5 (comtab) */
#define COMTAB(a, b) *ocp++ = (a); ocs(sw); w = (b); goto oce

JDA insn *oc(insn *dst, INLINE const word *ot)
{
    static insn ocm = { 0600000, &ocm };    /* `jmp .`: loop back to body start */
    static insn ocn = { 0600000, &ocn };    /* `jmp .`: skip over the move */
    register word bits;
    register insn sw;
    insn w;

    ocp = dst;                      /* same cell: no code */
    ocg = ot;
    *ocp++ = I_STF(5);
    ocm.addr = ocp;
    ARGS_DONE();                    /* return past the inline word from here */
    *ocp++ = I_LAC(&sx1);
    *ocp++ = I_LIO(&sy1);
    clf(6);
ocj:
    occ = -6;
    bits = *home(ocg);
och: {
        word code = 0;
        rcl(code, bits, 3);         /* next 3-bit code into AC */
        oci = bits;
        sw = I_RCL(9);
        switch (code) {
        case 0:
        case 1: goto oc1;
        case 2: goto oc2;
        case 3: goto oc3;
        case 4: goto oc4;
        case 5: goto oc5;
        case 6: goto oc6;
        case 7:                     /* end of outline: emit the mirror pass */
            *ocp++ = I_SZF(5);
            ocn.addr = ocp + 4;
            *ocp++ = ocn;
            *ocp++ = I_DAC(&sx1);
            *ocp++ = I_DIO(&sy1);
            *ocp++ = I_JMP(&sq6);
            *ocp++ = I_CLF(5);
            *ocp++ = I_LAC(&scm);
            *ocp++ = I_CMA;
            *ocp++ = I_DAC(&scm);
            *ocp++ = I_LAC(&ssm);
            *ocp++ = I_CMA;
            *ocp++ = I_DAC(&ssm);
            *ocp++ = I_LAC(&csm);
            *ocp++ = I_LIO(&ssd);
            *ocp++ = I_DAC(&ssd);
            *ocp++ = I_DIO(&csm);
            *ocp++ = I_LAC(&ssc);
            *ocp++ = I_LIO(&csn);
            *ocp++ = I_DAC(&csn);
            *ocp++ = I_DIO(&ssc);
            *ocp++ = ocm;
            return ocp;
        }
    }
    PLACE(ocm, ocn);

oc1:                                /* codes 0, 1: step (ssn, -scn) */
    *ocp++ = I_ADD(&ssn);
    ocs(sw);
    w = I_SUB(&scn);
oce:
    *ocp++ = w;
    ocs(sw);
    *ocp++ = I_IOH;
    w = I_DPY_NOWAIT;
ocd:
    *ocp++ = w;
    bits = oci;
    if (++occ < 0)
        goto och;
    ++ocg;
    goto ocj;

oc2: COMTAB(I_ADD(&scm), I_ADD(&ssm));
oc3: COMTAB(I_ADD(&ssc), I_SUB(&csm));
oc4: COMTAB(I_SUB(&scm), I_SUB(&ssm));
oc5: COMTAB(I_ADD(&csn), I_SUB(&ssd));

oc6:                                /* code 6: save or restore the pen */
    if (flag(6))
        goto oc9;
    stf(6);
    *ocp++ = I_DAC(&ssa);
    w = I_DIO(&ssi);
    goto ocd;
oc9:
    clf(6);
    *ocp++ = I_LAC(&ssa);
    w = I_LIO(&ssi);
    goto ocd;
}
