/*
 * pdp1.h -- the "PDP-1 C" dialect header (candidate 2).
 *
 * Two readers use this file.
 *   1. gcc, for `-fsyntax-only` (typing) and for the host reference model
 *      (see "Reference meaning" below).
 *   2. pdp1cc's front end, which preprocesses with gcc -E and then reads the
 *      _Pragma markers and typedef names defined here.  Nothing in this file
 *      is an assembler escape: every builtin has an ordinary-C meaning, and
 *      the compiler is free to pick any instruction sequence with that
 *      meaning (it picks by the rules in compiler.md, which are what make the
 *      output byte-identical).
 *
 * Reference meaning.  A `word` is an 18-bit ones' complement pattern held in
 * the low bits of a uint32_t.  On `word` operands the C operators mean the
 * PDP-1 operation, not the host operation:
 *     a + b  a - b  -a  ~a     w_add / w_sub / w_cma   (end-around carry,
 *                              ADD turns -0 into +0, SUB does not)
 *     a & b  a | b  a ^ b      bitwise on 18 bits
 *     a == b  a != b           raw 18-bit pattern equality (so -0 != +0)
 *     a < 0   a >= 0           sign bit (bit 17) set / clear
 *     a == 0  a != 0           raw pattern is 0 (so -0 is "not zero")
 *     a <= 0  a > 0            (sign set or zero) / its negation
 * Negative integer constants denote ones' complement (-n is ~n, so -041 is
 * 0777736); the front end folds them that way, gcc's host value is irrelevant.
 * Relational operators between two words are rejected by the front end: on
 * this machine they would have to be written as a subtraction plus a sign
 * test, and the author must say which one.
 * The host reference build (tools `pdp1ref`, a source-to-source pass over the
 * pycparser tree) rewrites those operators into the w_* functions below and
 * links the static-inline builtins in this file.  That build is the oracle for
 * the compiler test corpus.  It is a tool, not part of the product, and it
 * never reads the binary.
 */
#ifndef PDP1_H
#define PDP1_H

#include <stdint.h>

/* ---- types ------------------------------------------------------------- */

typedef uint32_t word;        /* 18-bit ones' complement cell, raw pattern   */
typedef word    *cptr;        /* pointer *homed in an instruction cell*: the
                                 cell is `<op> Y`; only Y (12 bits) is the
                                 pointer.  Writable only by dap-assignment
                                 and ++, so the opcode bits never change.    */
typedef word     inl_insn;    /* parameter that the caller supplies as ONE
                                 inline instruction word after the call; each
                                 read executes it (xct).                     */
typedef word     inl_data;    /* parameter supplied as one inline data word
                                 after the call; a read is `lac i link`.     */
typedef void   (*calc_fn)(void); /* jsp-convention routine address           */

#define SIGN   0400000u
#define MASK18 0777777u
#define NEG0   0777777u       /* -0 */

/* ---- annotations (pragma markers; the front end attaches them to the next
 *      declaration) ------------------------------------------------------- */

#define PDP1_PRAGMA_(x) _Pragma(#x)
#define PDP1_JDA   PDP1_PRAGMA_(pdp1 conv jda)   /* arg in AC -> entry cell  */
#define PDP1_JSP   PDP1_PRAGMA_(pdp1 conv jsp)   /* return address in AC     */
#define PDP1_XCT   PDP1_PRAGMA_(pdp1 conv xct)   /* body is ONE word; calls  */
                                                 /* are `xct`                */
#define PDP1_FRAGMENT   PDP1_PRAGMA_(pdp1 conv fragment) /* straight-line slice of a larger
                                  routine: no entry cell, no link, no return.
                                  Used for sub-function splice regions. */
#define PDP1_CONT   PDP1_PRAGMA_(pdp1 conv cont) /* entered by jmp, no link of its own;
                                  a call in tail position is `jmp`, and it
                                  runs inside its caller's dynamic context
                                  (shared exits, loop heads, sq6-style resume
                                  points).  Must be _Noreturn or end in a tail
                                  transfer. */
#define PDP1_ORG(n)     PDP1_PRAGMA_(pdp1 org n)      /* assembler  n/       */
#define PDP1_RESERVE(n) PDP1_PRAGMA_(pdp1 reserve n)  /* assembler  . n/     */
#define PDP1_POOL()     PDP1_PRAGMA_(pdp1 pool)       /* `constants`         */
#define PDP1_VARS()     PDP1_PRAGMA_(pdp1 vars)       /* `variables`         */
#define PDP1_NOSPILL    PDP1_PRAGMA_(pdp1 nospill)    /* spill is an error   */
#define PDP1_UNROLL     PDP1_PRAGMA_(pdp1 unroll)     /* full unroll next for */
#define PDP1_AS(n)      PDP1_PRAGMA_(pdp1 symbol n)   /* Macro label differs from the C name
                                                         (C name would clash with libc) */

/* ---- machine registers ------------------------------------------------- */

extern word IO;               /* the IO register (global; AC is implicit)    */
word ANY(void);               /* an AC value the author does not care about:
                                 emits no code.  Reference value: 0.         */

/* ---- ones' complement arithmetic (reference definitions) --------------- */

static inline word w_add(word a, word b) {
    uint32_t s = a + b;
    if (s > MASK18) s = (s + 1) & MASK18;       /* end-around carry */
    if (s == MASK18) s = 0;                     /* ADD cleans up -0  */
    return s;
}
static inline word w_sub(word a, word b) {
    uint32_t t = a ^ MASK18, s = t + b;
    if (s > MASK18) s = (s + 1) & MASK18;
    return s ^ MASK18;                          /* SUB may yield -0  */
}
static inline word w_cma(word a) { return a ^ MASK18; }       /* = negate */
static inline word w_idx(word a) {                              /* idx/isp  */
    uint32_t s = a + 1;
    if (s >= MASK18) s = (s + 1) & MASK18;
    return s;
}

/* ---- shifts and rotates.  Count n is 1..9 per instruction; larger counts
 *      are split into 9s by the compiler (reference: any 1..17).  ral/rar,
 *      sal/sar act on AC only; rcl/rcr/scl/scr use AC:IO as one 36-bit word
 *      and leave the other half in IO; ril/rir/sil/sir act on IO only.    */

static inline word ral(word a, int n) { return ((a << n) | (a >> (18 - n))) & MASK18; }
static inline word rar(word a, int n) { return ((a >> n) | (a << (18 - n))) & MASK18; }
static inline word sal(word a, int n) {
    word t = (a & SIGN) ? MASK18 : 0;
    return (a & SIGN) | ((a << n) & 0377777) | (t >> (18 - n));
}
static inline word sar(word a, int n) {
    word t = (a & SIGN) ? MASK18 : 0;
    return ((a >> n) | (t << (18 - n))) & MASK18;
}
static inline word rcl(word a, int n) {
    word io = IO;
    IO = ((IO << n) | (a >> (18 - n))) & MASK18;
    return ((a << n) | (io >> (18 - n))) & MASK18;
}
static inline word rcr(word a, int n) {
    word io = IO;
    IO = ((IO >> n) | (a << (18 - n))) & MASK18;
    return ((a >> n) | (io << (18 - n))) & MASK18;
}
static inline word scl(word a, int n) {
    word t = (a & SIGN) ? MASK18 : 0, io = IO;
    IO = ((IO << n) | (t >> (18 - n))) & MASK18;
    return (a & SIGN) | ((a << n) & 0377777) | (io >> (18 - n));
}
static inline word scr(word a, int n) {
    word t = (a & SIGN) ? MASK18 : 0, io = IO;
    IO = ((IO >> n) | (a << (18 - n))) & MASK18;
    return ((a >> n) | (t << (18 - n))) & MASK18;
}
static inline word ril(word io, int n) { return ((io << n) | (io >> (18 - n))) & MASK18; }
static inline word rir(word io, int n) { return ((io >> n) | (io << (18 - n))) & MASK18; }

/* multiply step: AC is the partial product, IO the multiplier; result is the
 * new AC, IO shifts.  `mus(ac, m)` == the MUL instruction without hardware
 * multiply.  Seventeen steps give a 34-bit product. */
static inline word mus(word ac, word m) {
    if (IO & 1) ac = ac + m;
    if (ac > MASK18) ac = (ac + 1) & MASK18;
    IO = (IO >> 1) | ((ac & 1) << 17);
    return ac >> 1;
}

static inline word swap(word a) { return rcl(rcl(a, 9), 9); }   /* macro `swap` */

/* indirect call: AC holds the routine address (jsp convention).  Lowers to
 * `dap .+1 ; jsp .`  (rule C7).                                              */
#define CALL_FN(w) (((calc_fn)(uintptr_t)(w))())

/* ---- control, flags, switches ------------------------------------------ */

void nop(void);               /* opr                                        */
int  flag(int n);             /* program flag n set?    (szf n skips if not)*/
void stf(int n);              /* set flag n                                 */
void clf(int n);              /* clear flag n                               */
int  sense_switch(int n);     /* sense switch n set?   (szs n skips if not) */

/* ---- cells, entries, symbolic constants -------------------------------- */

word *__here_cell(cptr);      /* internal: the lvalue "the cell, executed here" */
/* HERE(p): the cell that homes cursor p is placed *at this point in the code
 * stream* and is executed as the operand access.  Its opcode is the one the
 * surrounding expression needs (load -> lac, `-` operand -> sub, assignment
 * target -> dac, IO target -> lio, ...).  Exactly one HERE(p) per cursor.
 * Reference meaning: *p, with p the current pointer value.                  */
#define HERE(p)  (*__here_cell(p))
void __cell_here(cptr *, const char *);
/* CELL_HERE(p, "jmp"): place p's cell here as plain storage, initial word
 * `jmp .`; it is never executed in place.                                   */
#define CELL_HERE(p, mnemonic) __cell_here(&(p), mnemonic)
/* CELL_WORD(p): the cell's whole 18-bit word (opcode | Y) as data.          */
#define CELL_WORD(p) (*(word *)&(p))

word *__entry_cell(void (*)(void));
/* ENTRY(f): lvalue for f's entry word (where `jda f` stored its argument).
 * Inside f, parameter 0 *is* this word.  Elsewhere it is ordinary storage.  */
#define ENTRY(f)     (*__entry_cell((void (*)(void))(f)))
#define ENTRY_PTR(f) (*(word **)__entry_cell((void (*)(void))(f)))
#define FN_ADDR(f)   ((word)(uintptr_t)(f))

/* inline-argument epilogue helper: advance the link past n inline words.
 * Reference meaning: link += n.  Lowers to `idx <link>` n times.            */
void skip_inline(int n);

/* ---- instruction words as data (all symbolic; macro1 does the arithmetic)  */
#define PDP1_INSN(op, y) ((word)(((word)(op) << 13) | ((word)(uintptr_t)(y) & 07777u)))
#define I_LAC(y)  PDP1_INSN(010, y)
#define I_LIO(y)  PDP1_INSN(011, y)
#define I_DAC(y)  PDP1_INSN(012, y)
#define I_DIO(y)  PDP1_INSN(015, y)
#define I_ADD(y)  PDP1_INSN(020, y)
#define I_SUB(y)  PDP1_INSN(021, y)
#define I_JMP(y)  PDP1_INSN(030, y)
#define I_STF(n)  ((word)(0760010u | (n)))
#define I_CLF(n)  ((word)(0760000u | (n)))
#define I_SZF(n)  ((word)(0640000u | (n)))
#define I_RCL(n)  ((word)(0663000u | ((1u << (n)) - 1u)))
#define I_CMA     ((word)0761000u)
#define I_IOH     ((word)0730000u)
#define I_DPY_NW  ((word)0724007u)     /* dpy-4000 = iot 7, wait bit cleared */

#endif /* PDP1_H */
