/*
 * pdp1.h -- the "pdp1c" C dialect (candidate 3).
 *
 * One header, two readers:
 *   - gcc (or any C11 compiler) sees plain C: every builtin below has a C
 *     reference definition, so the dialect has a meaning independent of our
 *     compiler, and `gcc -std=c11 -fsyntax-only -include pdp1.h x.c` checks it.
 *   - pdp1cc (our compiler) defines __PDP1CC__, keeps the attributes, and
 *     treats the names in the "builtins" sections as operations it lowers.
 *
 * Dialect in one paragraph. Storage is chosen by the C storage class, never
 * guessed: an automatic `word` lives in AC, a `register word` lives in IO, an
 * uninitialized static/extern `word` is a Macro pool variable (`\x`), an
 * initialized static is a word placed in the code at its definition, and a
 * HOMED pointer lives in the address field of the instruction that
 * dereferences it through home(). Calling conventions are function
 * attributes (JSP, JDA, XCT, BLOCK). C `int` is compile-time only: loops over
 * `int` unroll, `int` parameters of static inline functions instantiate.
 * Operand order in C is instruction order: `a + b` is `lac a / add b`.
 */
#ifndef PDP1_H
#define PDP1_H

#include <stdint.h>
#include <stdbool.h>

#ifndef __PDP1CC__
#pragma GCC diagnostic ignored "-Wattributes"
#endif

/* ------------------------------------------------------------------ types */

/* An 18-bit ones' complement machine word. Arithmetic operators on `word`
 * mean PDP-1 arithmetic: + is `add` (end-around carry, -0 cleanup), - (binary)
 * is `sub`, unary - and ~ are both `cma`, >> is `sar`, << is `sal` (sign
 * kept), ^ & | are xor/and/ior. Comparisons are only against 0 and test the
 * sign bit / zero exactly as the skip group does (so MINUS_ZERO < 0 holds).
 * Under plain gcc the operators approximate this; the reference build runs
 * the C through `pdp1cc --normalize`, which rewrites every operator on `word`
 * to the w_* functions below, giving exact semantics natively. */
typedef int32_t word;

/* The 36-bit AC:IO pair. A `dword` local is the register pair itself:
 * .hi is AC, .lo is IO. Returned by JDA functions that leave two words. */
typedef struct dword { word hi, lo; } dword;

/* An instruction as a value: `bits` holds opcode, indirect bit, and any
 * non-address bits; `addr` is the 12-bit operand address (NULL = 0).
 * One machine word. Assigning to .addr is `dap`; reading the whole insn is
 * `lac`; storing it is `dac`. Constructors below are constant expressions,
 * so an insn constant becomes a Macro literal such as `(lac \sx1`. */
typedef struct insn { word bits; const volatile void *addr; } insn;

/* A code address carried in a word (address field significant). */
typedef word code;

/* A label exported from the function that defines it. Declare
 * `extern label_t sq6;` at file scope and write `sq6:` in exactly one
 * function; other code may take &sq6 (e.g. I_JMP(&sq6)) or jump(...) to it.
 * C keeps labels and objects in separate name spaces, so this is legal. */
typedef struct pdp1_label label_t;

#define SIGN        0400000
#define MINUS_ZERO  0777777
#define W_MASK      0777777

/* ----------------------------------------------- calling conventions */
/* JSP   `jsp f`; AC = return address; callee prologue `dap R`; return
 *       `jmp R` / exit cell `R, jmp .`. At most one parameter, which must be
 *       `register` (passed in IO). Result in AC (word) or AC:IO (dword).
 * JDA   `jda f`; first argument evaluated into AC, deposited by the hardware
 *       in f's entry word, which IS the parameter's storage. Prologue
 *       `dap R`. Extra parameters are inline words after the call site:
 *       BYNAME (caller emits `lac <operand>`; callee reads with `xct R`)
 *       or INLINE (caller emits the constant word; callee reads `lac i R`).
 *       Functions with inline parameters skip them on return (`idx R`).
 * XCT   the whole function is one instruction word, executed by `xct f`.
 *       Arguments and result in AC (word) or AC:IO (dword). Compile error if
 *       the body does not lower to exactly one word.
 * BLOCK no prologue; entered by `jmp f` with its one argument in AC. A JSP or
 *       JDA function whose body ends `return blk(...)` adopts blk's exit
 *       cell: its prologue patches blk's exit instead of having its own.
 *       A BLOCK with no return statement is a pure jump target. */
#define JSP     __attribute__((pdp1_jsp))
#define JDA     __attribute__((pdp1_jda))
#define XCT     __attribute__((pdp1_xct))
#define BLOCK   __attribute__((pdp1_block))
#define BYNAME  __attribute__((pdp1_byname))
#define INLINE  __attribute__((pdp1_inline))

/* --------------------------------------------------- storage attributes */
/* HOMED: a pointer (or code address) whose storage is the address field of
 * an instruction. The instruction is the one site in the program written
 * `*home(p)` (or `home(c)` for a code target, see jump()). Every other use
 * reaches it through that cell: `*p` is `op i p`, `p = e` is `dap p`, `++p`
 * is `idx p`, `p` as a value is `lac p` (whole instruction word, so
 * comparisons against constants encode the home opcode: `++ml2 != &mtb[NOB]`
 * becomes `sas (lac mtb+30`). */
#define HOMED           __attribute__((pdp1_homed))
/* ENTRY_CELL(f): this file-scope object names JDA function f's entry word
 * (f's parameter storage). Lets one routine use another's entry word as
 * scratch (sin/cos) or reach a caller's working pointer (ocs uses oc's). */
#define ENTRY_CELL(f)   __attribute__((pdp1_entry_cell(f)))
/* POOL: a Macro pool variable (`\x`, allocated at `variables` in order of
 * first use). Required on extern declarations; a file-scope tentative
 * definition with no initializer (`word t1;`) is POOL implicitly. */
#define POOL            __attribute__((pdp1_pool))
/* AT(a): place this object or function at absolute address a (Macro `a/`). */
#define AT(a)           __attribute__((pdp1_at(a)))
/* NOPUNCH: placed in layout order but not punched (Macro `. n/`). */
#define NOPUNCH         __attribute__((pdp1_nopunch))
/* SYM("x"): Macro symbol for this C name when the C name differs or is
 * longer than 6 characters (only needed for names shared with unlifted text). */
#define SYM(s)          __attribute__((pdp1_sym(s)))
/* RESERVE(n): n unpunched words at this point in the layout. */
#define RESERVE_(n, l)  static word pdp1_reserve_##l[n] NOPUNCH
#define RESERVE_L(n, l) RESERVE_(n, l)
#define RESERVE(n)      RESERVE_L(n, __LINE__)

/* --------------------------------------------- layout and encoding hints */
/* Hints have identity reference meaning; they only select between
 * encodings with identical semantics. Each is counted by the honesty gate. */
#define home(p)     (p)          /* this deref/jump is p's storage cell        */
#define PLACE(...)  ((void)0)    /* emit these initialized static locals here  */
#define SKIPNOT(c)  (c)
#define RELOAD(x)   (x)          /* force a load the AC/IO tracker would elide */
#define ARGS_DONE() ((void)0)    /* emit the inline-argument skip (`idx R`)
                                    here instead of at the default point      */          /* negate c with the skip's i-bit, not by the
                                    complementary test (spa i vs sma)          */

/* REGION_BREAK(): file-scope marker; the splice build puts the code before
 * and after it into consecutive line ranges of the region's lift.toml entry. */
#define REGION_BREAK() _Static_assert(1, "pdp1 region break")

/* ------------------------------------------------ word arithmetic (exact) */
static inline word w_norm(int64_t v) { return (word)(v & W_MASK); }
static inline word w_add(word a, word b) {          /* add: pdp1_cpu.c 020 */
    int64_t r = (int64_t)a + b;
    if (r > W_MASK) r = (r + 1) & W_MASK;
    return r == W_MASK ? 0 : (word)r;
}
static inline word w_neg(word a) { return a ^ W_MASK; }       /* cma */
static inline word w_sub(word a, word b) {          /* sub: pdp1_cpu.c 021 */
    int64_t r = (int64_t)(a ^ W_MASK) + b;
    if (r > W_MASK) r = (r + 1) & W_MASK;
    return (word)(r ^ W_MASK);
}
static inline bool w_lt0(word a) { return (a & SIGN) != 0; }  /* sma */
static inline bool w_eq0(word a) { return a == 0; }           /* sza */
static inline word w_sar(word a, int n) {           /* sar ns */
    while (n--) a = (a >> 1) | (a & SIGN);
    return a;
}
static inline word w_sal(word a, int n) {           /* sal ns */
    while (n--) a = (a & SIGN) | ((a << 1) & 0377777) | ((a & SIGN) ? 1 : 0);
    return a;
}
static inline word w_idx(word *p) {                 /* idx: -0 skipped */
    word r = (*p + 1) & W_MASK;
    if (r == W_MASK) r = 0;
    return *p = r;
}

/* -------------------------------------------------- shifts and rotates */
/* Single-register rotates/shifts take and return a value. Pair operations
 * take two lvalues: the first must be AC-resident, the second IO-resident;
 * the compiler rejects anything else (no hidden moves). n is a compile-time
 * int; the compiler splits n into 9s chunks (18 -> two `rcr 9s`). */
static inline word ral(word a, int n) { while (n--) a = ((a << 1) | (a >> 17)) & W_MASK; return a; }
static inline word rar(word a, int n) { while (n--) a = ((a >> 1) | ((a & 1) << 17)) & W_MASK; return a; }
#define ril(v, n) ral((v), (n))      /* IO-resident operand */
#define rir(v, n) rar((v), (n))
#define sir(v, n) w_sar((v), (n))

static inline dword pdp1_rcl(dword p, int n) {
    while (n--) { word c = (p.hi >> 17) & 1;
        p.hi = ((p.hi << 1) | ((p.lo >> 17) & 1)) & W_MASK;
        p.lo = ((p.lo << 1) | c) & W_MASK; }
    return p;
}
static inline dword pdp1_rcr(dword p, int n) {
    while (n--) { word c = p.lo & 1;
        p.lo = ((p.lo >> 1) | ((p.hi & 1) << 17)) & W_MASK;
        p.hi = ((p.hi >> 1) | (c << 17)) & W_MASK; }
    return p;
}
static inline dword pdp1_scl(dword p, int n) {
    while (n--) { word s = p.hi & SIGN;
        p.hi = s | ((p.hi << 1) & 0377777) | ((p.lo >> 17) & 1);
        p.lo = ((p.lo << 1) | (s ? 1 : 0)) & W_MASK; }
    return p;
}
static inline dword pdp1_scr(dword p, int n) {
    while (n--) { word s = p.hi & SIGN;
        p.lo = ((p.lo >> 1) | ((p.hi & 1) << 17)) & W_MASK;
        p.hi = s | (p.hi >> 1); }
    return p;
}
/* multiply step `mus m` (pdp1_cpu.c 026, no MDV option) */
static inline dword pdp1_mus(dword p, word m) {
    int64_t ac = p.hi;
    if (p.lo & 1) { ac += m; if (ac > W_MASK) ac = (ac + 1) & W_MASK; }
    p.lo = (word)(((p.lo >> 1) | ((ac & 1) << 17)) & W_MASK);
    p.hi = (word)(ac >> 1);
    return p;
}
/* divide step `dis m` (pdp1_cpu.c 027) */
static inline dword pdp1_dis(dword p, word m) {
    word t = (p.hi >> 17) & 1;
    int64_t ac = ((p.hi << 1) | ((p.lo >> 17) & 1)) & W_MASK;
    p.lo = ((p.lo << 1) | (t ^ 1)) & W_MASK;
    ac = (p.lo & 1) ? ac + (m ^ W_MASK) : ac + m + 1;
    if (ac > W_MASK) ac = (ac + 1) & W_MASK;
    if (ac == W_MASK) ac = 0;
    p.hi = (word)ac;
    return p;
}
#define PAIR_OP(f, h, l, x) do { dword p_ = f((dword){ (h), (l) }, (x)); \
                                 (h) = p_.hi; (l) = p_.lo; } while (0)
#define rcl(h, l, n)  PAIR_OP(pdp1_rcl, h, l, n)   /* rcl ns (AC:IO)         */
#define rcr(h, l, n)  PAIR_OP(pdp1_rcr, h, l, n)   /* rcr ns                 */
#define scl(h, l, n)  PAIR_OP(pdp1_scl, h, l, n)   /* scl ns                 */
#define scr(h, l, n)  PAIR_OP(pdp1_scr, h, l, n)   /* scr ns                 */
#define mus(h, l, m)  PAIR_OP(pdp1_mus, h, l, m)   /* mus m                  */
#define dis(h, l, m)  PAIR_OP(pdp1_dis, h, l, m)   /* dis m                  */

/* ----------------------------------------------------- control transfer */
/* The host side of the reference build supplies these: it keeps a map from
 * 12-bit addresses to C functions/labels (built from the compiler's symbol
 * output), so `call` and `jump` have meaning without an interpreter of the
 * Spacewar binary. */
extern word pdp1_code_of(void (*f)(void));
extern void pdp1_call(word routine);
extern _Noreturn void pdp1_jump(code target);
/* Address of a routine as a word (`law f`, `(f 400000`). */
#define CODE(f)   pdp1_code_of((void (*)(void))(f))
/* Call the JSP routine named by w's address field (flag bits ignored).
 * Lowers to `jsp i v` when w is a variable, else `<w> / dap .+1 / jsp .`. */
#define call(w)   pdp1_call(w)
/* Transfer control to a code address (a HOMED `code` cell written home(c)
 * at the jump site: `c, jmp .`). Control comes back only through an exported
 * label that the target jumps to. Used for runtime-generated code. */
#define jump(c)   pdp1_jump(c)

/* Reference meaning of generated code: executing an insn buffer is defined
 * by pdp1_exec, a specification covering exactly the opcodes the I_*
 * constructors can build. It is never compiled into the PDP-1 binary. */
extern void pdp1_exec(const insn *start);

/* ------------------------------------------------ instruction constants */
#define INSN(b, a)       ((insn){ (b), (a) })
#define SHIFT_N(n)       ((1 << (n)) - 1)          /* 1s..9s count field */
#define I_LAC(p)         INSN(0200000, (p))
#define I_LIO(p)         INSN(0220000, (p))
#define I_DAC(p)         INSN(0240000, (p))
#define I_DIO(p)         INSN(0320000, (p))
#define I_ADD(p)         INSN(0400000, (p))
#define I_SUB(p)         INSN(0420000, (p))
#define I_JMP(p)         INSN(0600000, (p))
#define I_STF(n)         INSN(0760010 | (n), 0)
#define I_CLF(n)         INSN(0760000 | (n), 0)
#define I_SZF(n)         INSN(0640000 | (n), 0)
#define I_CMA            INSN(0761000, 0)
#define I_IOH            INSN(0730000, 0)
#define I_RCL(n)         INSN(0663000 | SHIFT_N(n), 0)
#define I_DPY_NOWAIT     INSN(0730007 - 04000, 0)  /* `dpy-4000` */

/* ------------------------------------------------------------ hardware */
/* Machine state for the reference build. */
extern word pdp1_pf;             /* program flags 1..6  */
extern word pdp1_ss;             /* sense switches 1..6 */
extern word pdp1_tw;             /* test word           */
static inline void stf(int n)  { pdp1_pf |=  (1 << (6 - n)); }      /* stf n  */
static inline void clf(int n)  { pdp1_pf &= ~(1 << (6 - n)); }      /* clf n  */
static inline bool flag(int n) { return (pdp1_pf >> (6 - n)) & 1; } /* szf    */
static inline bool sense(int n){ return (pdp1_ss >> (6 - n)) & 1; } /* szs n0 */
static inline word lat(void)   { return pdp1_tw; }                  /* lat    */
extern void hlt(void);                                              /* hlt    */
extern void ioh(void);           /* wait for I/O completion: `ioh`          */
extern void dpy(word x, word y); /* display point: x in AC, y in IO          */
extern word cwi(void);           /* read control boxes into IO: `cli/iot 11` */

#endif /* PDP1_H */
