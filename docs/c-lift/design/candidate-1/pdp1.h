/*
 * pdp1.h -- the PDP-1 C dialect (candidate 1).
 *
 * One header, three readers:
 *
 *   gcc -std=c11 -fsyntax-only -include pdp1.h f.c
 *       Syntax and type check. `word` is a plain int here; builtins have
 *       C reference bodies over the 18-bit representation.
 *
 *   g++ -std=c++14 -include pdp1.h f.c          (__cplusplus)
 *       Executable reference semantics. `word` becomes a class whose
 *       operators are 18-bit ones' complement, so a dialect program that
 *       does not touch hardware, code addresses or runtime-generated code
 *       runs natively and must agree with the same program compiled by
 *       swc and run in SIMH. This is the compiler's differential oracle.
 *
 *   swc (our compiler; cpp -DPDP1_COMPILER, then pycparser)
 *       Sees the same declarations. Builtins are recognized by name from
 *       the closed list PDP1_BUILTINS below; their bodies are ignored and
 *       replaced by the lowering rules in compiler.md.
 *
 * Dialect semantics that C syntax cannot carry by itself:
 *
 *   word      18-bit ones' complement. + and - use end-around carry
 *             (and `+` turns a -0 result into +0, as the hardware ADD does).
 *             Unary - and ~ are both "complement all 18 bits" (cma).
 *             >> n and << n are arithmetic shifts (sar/sal); they keep the sign.
 *             x < 0 is "sign bit set" (true for -0). x == 0 is "+0 only".
 *             x <= 0 is (sign set or +0); x > 0 is its negation.
 *             Octal literals are bit patterns (0756103 is a negative word,
 *             0777777 is -0). A C negative constant -n is the ones'
 *             complement of n (-041 is 0777736, what `law i 41` loads).
 *   pointers  12-bit addresses; every scalar and pointer is one word.
 *   auto `word` locals live in AC; `register word` locals live in IO;
 *             `dword` locals live in AC:IO. There is no spilling. If a
 *             register local's live range crosses an instruction that
 *             clobbers its register, swc rejects the program.
 *   file-scope objects with an initializer are punched where they are
 *             defined; without one they are Macro variables (\name),
 *             allocated by macro1 in order of first use in the emitted text.
 *
 * Attributes are written as `#pragma pdp1 ...` lines because cpp keeps
 * them, pycparser parses them, and gcc ignores them. The vocabulary is
 * closed; swc rejects any other pdp1 pragma:
 *
 *   org(A)                 next word goes at absolute address A
 *   reserve(N)             skip N unpunched words
 *   constants / variables  place the literal pool / Macro variable block
 *   jda(f [, inline=P:exec|data])
 *                          f is entered by jda: arg 1 arrives in AC and is
 *                          stored in f's entry word, which is the parameter's
 *                          home. P, if named, is an inline operand: the word
 *                          after the call. exec: the caller emits a one-word
 *                          load of P's argument and f reads P with xct.
 *                          data: the caller emits P's argument value and f
 *                          reads P with `lac i <link>`. f must call
 *                          consume(P) exactly once on every path to return.
 *   jsp(f) / jsp(T)        f (or every function of type T) is entered by
 *                          jsp; no stack, no arguments except a `register`
 *                          parameter, which arrives in IO.
 *   jmp(f) / jmp(T)        entered by plain jmp. With returns_to(T, L): the
 *                          callee returns by jumping to label L, which must
 *                          directly follow the call site and is exported.
 *   xct(f)                 f's body must lower to exactly one instruction;
 *                          that instruction is f, and calls are `xct f`.
 *   homed(p, ...)          pointer p lives in the address field of the
 *                          instruction that dereferences it in the statement
 *                          labeled `p:`. Elsewhere *p is `op i p`. Without an
 *                          initializer the host's address field starts as `.`.
 *   homed_word(p, OP)      p lives in the address field of a standalone
 *                          data word with opcode OP (e.g. jmp).
 *   place(x, ...)          emit the storage of these statics here.
 *   overlay(x, f)          x occupies f's entry word (lifetimes are disjoint;
 *                          swc checks f is not active while x is live).
 *   name(cid, "sym")       Macro symbol for a C identifier (e.g. "1sc").
 *   unroll                 the next `for` (constant trip count) is unrolled.
 */
#ifndef PDP1_H
#define PDP1_H

/* The dialect is freestanding: sin, cos, etc. are program names, not libm. */
#if defined(__GNUC__) && !defined(PDP1_COMPILER)
#pragma GCC diagnostic ignored "-Wbuiltin-declaration-mismatch"
#endif

/* ------------------------------------------------------------------ */
/* 18-bit representation helpers: the single source of truth for the   */
/* reference meaning of every builtin and (in C++) every operator.     */
/* ------------------------------------------------------------------ */

#define PDP1_DMASK 0777777u
#define PDP1_SIGN  0400000u
#define PDP1_AMASK 07777u

typedef unsigned pdp1_bits;            /* low 18 bits significant */

static inline pdp1_bits pdp1_eac(unsigned long v)     /* end-around carry */
{ return (pdp1_bits)((v > PDP1_DMASK) ? ((v + 1) & PDP1_DMASK) : v); }

static inline pdp1_bits pdp1_add(pdp1_bits a, pdp1_bits b)   /* ADD */
{ pdp1_bits r = pdp1_eac((unsigned long)a + b); return r == PDP1_DMASK ? 0 : r; }

static inline pdp1_bits pdp1_sub(pdp1_bits a, pdp1_bits b)   /* SUB */
{ return pdp1_eac((unsigned long)(a ^ PDP1_DMASK) + b) ^ PDP1_DMASK; }

static inline pdp1_bits pdp1_cma(pdp1_bits a) { return a ^ PDP1_DMASK; }

static inline pdp1_bits pdp1_sar(pdp1_bits a, int n)   /* SAR n */
{ pdp1_bits t = (a & PDP1_SIGN) ? PDP1_DMASK : 0;
  return ((a >> n) | (t << (18 - n))) & PDP1_DMASK; }

static inline pdp1_bits pdp1_sal(pdp1_bits a, int n)   /* SAL n */
{ pdp1_bits t = (a & PDP1_SIGN) ? PDP1_DMASK : 0;
  return (a & PDP1_SIGN) | ((a << n) & 0377777u) | (t >> (18 - n)); }

static inline pdp1_bits pdp1_rot(pdp1_bits a, int n)   /* RAL n (left) */
{ return ((a << n) | (a >> (18 - n))) & PDP1_DMASK; }

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

#ifndef __cplusplus
typedef int word;                      /* syntax/type mode: see header comment */
#else
struct word {                          /* executable reference mode */
    pdp1_bits v;
    word() : v(0) {}
    word(int i) : v((pdp1_bits)(i < 0 ? (pdp1_bits)(~(unsigned)(-i)) : (unsigned)i) & PDP1_DMASK) {}
    static word bitsw(pdp1_bits b) { word w; w.v = b & PDP1_DMASK; return w; }
    friend word operator+(word a, word b) { return bitsw(pdp1_add(a.v, b.v)); }
    friend word operator-(word a, word b) { return bitsw(pdp1_sub(a.v, b.v)); }
    friend word operator-(word a)         { return bitsw(pdp1_cma(a.v)); }
    friend word operator~(word a)         { return bitsw(pdp1_cma(a.v)); }
    friend word operator&(word a, word b) { return bitsw(a.v & b.v); }
    friend word operator|(word a, word b) { return bitsw(a.v | b.v); }
    friend word operator^(word a, word b) { return bitsw(a.v ^ b.v); }
    friend word operator>>(word a, int n) { return bitsw(pdp1_sar(a.v, n)); }
    friend word operator<<(word a, int n) { return bitsw(pdp1_sal(a.v, n)); }
    friend bool operator<(word a, int z)  { (void)z; return (a.v & PDP1_SIGN) != 0; }   /* only "< 0" */
    friend bool operator>=(word a, int z) { (void)z; return (a.v & PDP1_SIGN) == 0; }
    friend bool operator<=(word a, int z) { (void)z; return (a.v & PDP1_SIGN) || a.v == 0; }
    friend bool operator>(word a, int z)  { return !(a <= z); }
    friend bool operator==(word a, word b){ return a.v == b.v; }
    friend bool operator!=(word a, word b){ return a.v != b.v; }
    word &operator+=(word b) { return *this = *this + b; }
    word &operator-=(word b) { return *this = *this - b; }
    word &operator++()       { v = pdp1_eac((unsigned long)v + 1); if (v == PDP1_DMASK) v = 0; return *this; } /* IDX */
};
#endif

/* The AC:IO pair as one 36-bit value. In swc a dword local IS the pair. */
typedef struct { word ac, io; } dword;

/* An instruction word used as data (runtime code generation, tables). */
typedef word insn;

/* Code addresses that are not C functions (exported labels). */
typedef struct pdp1_code code;

/* ------------------------------------------------------------------ */
/* Builtins. Each has a C reference body. swc lowers them by rule.      */
/* ------------------------------------------------------------------ */

#define PDP1_BUILTINS \
    mag rcl rcr scl scr ral rar ril rir sil sir swap swapr mus dis consume \
    dpy ioh iot11 lat tyi sense flag stf clf hlt addr_of AS_FN \
    LAC LIO DAC DIO DAP ADD SUB JMP XCT STF CLF SZF RCL CMA IOH DPY

#ifndef __cplusplus
#define W(x)   ((pdp1_bits)(x) & PDP1_DMASK)
#define MKW(b) ((word)(b))
#else
#define W(x)   ((x).v)
#define MKW(b) word::bitsw(b)
#endif

/* mag(x): magnitude. Lowers to `spa; cma` after x is in AC. */
static inline word mag(word x) { return (W(x) & PDP1_SIGN) ? MKW(pdp1_cma(W(x))) : x; }

/* Shifts and rotates on one register. n is 1..9 per instruction; swc
   splits larger counts into 9s chunks followed by the remainder. */
static inline word ral(word x, int n) { return MKW(pdp1_rot(W(x), n)); }           /* ral ns */
static inline word rar(word x, int n) { return MKW(pdp1_rot(W(x), 18 - n)); }      /* rar ns */
static inline word ril(word x, int n) { return ral(x, n); }   /* same, on IO: ril ns */
static inline word rir(word x, int n) { return rar(x, n); }   /* same, on IO: rir ns */
static inline word sil(word x, int n) { return MKW(pdp1_sal(W(x), n)); }           /* sil ns */
static inline word sir(word x, int n) { return MKW(pdp1_sar(W(x), n)); }           /* sir ns */

/* 36-bit combined rotates and shifts of AC:IO (ac is the high half). */
static inline dword rcl(dword d, int n)                                          /* rcl ns */
{ pdp1_bits a = W(d.ac), i = W(d.io); dword r;
  r.ac = MKW(((a << n) | (i >> (18 - n))) & PDP1_DMASK);
  r.io = MKW(((i << n) | (a >> (18 - n))) & PDP1_DMASK); return r; }
static inline dword rcr(dword d, int n)                                          /* rcr ns */
{ pdp1_bits a = W(d.ac), i = W(d.io); dword r;
  r.io = MKW(((i >> n) | (a << (18 - n))) & PDP1_DMASK);
  r.ac = MKW(((a >> n) | (i << (18 - n))) & PDP1_DMASK); return r; }
static inline dword scl(dword d, int n)                                          /* scl ns */
{ pdp1_bits a = W(d.ac), i = W(d.io), t = (a & PDP1_SIGN) ? PDP1_DMASK : 0; dword r;
  r.ac = MKW((a & PDP1_SIGN) | ((a << n) & 0377777u) | (i >> (18 - n)));
  r.io = MKW(((i << n) | (t >> (18 - n))) & PDP1_DMASK); return r; }
static inline dword scr(dword d, int n)                                          /* scr ns */
{ pdp1_bits a = W(d.ac), i = W(d.io), t = (a & PDP1_SIGN) ? PDP1_DMASK : 0; dword r;
  r.io = MKW(((i >> n) | (a << (18 - n))) & PDP1_DMASK);
  r.ac = MKW(((a >> n) | (t << (18 - n))) & PDP1_DMASK); return r; }

/* Exchanging AC and IO. The machine has no transfer instruction; an
   18-place rotation of the 36-bit pair is the exchange. There are two
   encodings with identical meaning, and the program uses both (its own
   `swap` macro rotates left, the BBN routines rotate right), so the
   dialect names both and the author's choice is visible in the C:
     swap(d)   -> rcl 9s ; rcl 9s
     swapr(d)  -> rcr 9s ; rcr 9s
   An implicit AC->IO or IO->AC move (assigning an AC value to a register
   local or to .io, or using an IO value where AC is needed) lowers to
   swap(); swc never invents a memory temporary for it. */
static inline dword swap(dword d)  { dword r; r.ac = d.io; r.io = d.ac; return r; }
static inline dword swapr(dword d) { return swap(d); }

/* mus(d, m): multiply step (software multiply, pdp1_cpu.c case 026). */
static inline dword mus(dword d, word m)
{ pdp1_bits a = W(d.ac), i = W(d.io); dword r;
  if (i & 1) a = pdp1_eac((unsigned long)a + W(m));
  r.io = MKW((i >> 1) | ((a & 1) << 17)); r.ac = MKW(a >> 1); return r; }

/* dis(d, m): divide step (pdp1_cpu.c case 027, software path). */
static inline dword dis(dword d, word m)
{ pdp1_bits a = W(d.ac), i = W(d.io), t = a >> 17; dword r;
  a = ((a << 1) | (i >> 17)) & PDP1_DMASK;
  i = ((i << 1) | (t ^ 1)) & PDP1_DMASK;
  a = pdp1_eac((unsigned long)a + ((i & 1) ? (W(m) ^ PDP1_DMASK) : W(m) + 1));
  if (a == PDP1_DMASK) a = 0;
  r.ac = MKW(a); r.io = MKW(i); return r; }

/* consume(p): the inline operand p has been read for the last time.
   Reference meaning: nothing (operands are by value in C), like va_end.
   Lowering: `idx <link>`, which makes the return skip the operand word.
   swc checks: exactly once per path, no read of p afterwards, AC dead. */
#define consume(p) ((void)(p))

/* ------------------------------------------------------------------ */
/* Hardware. Reference bodies act on a small host-side machine model.   */
/* ------------------------------------------------------------------ */

struct pdp1_hw {
    pdp1_bits test_word, sense_switches, flags, control;
    void (*point)(word x, word y, int intensity);
};
extern struct pdp1_hw pdp1_hw;

static inline void dpy(word x, word y, int i)            /* AC=x, IO=y; dpy-i */
{ if (pdp1_hw.point) pdp1_hw.point(x, y, i); }
static inline void ioh(void) {}                           /* wait for i/o done: ioh */
static inline word iot11(void) { return MKW(pdp1_hw.control); } /* cli; iot 11 -> IO */
static inline word lat(void) { return MKW(pdp1_hw.test_word); }  /* lat */
static inline word tyi(void) { return 0; }                /* tyi -> IO */
static inline int  sense(int n) { return (pdp1_hw.sense_switches >> (6 - n)) & 1; } /* szs n0 */
static inline int  flag(int n)  { return (pdp1_hw.flags >> (6 - n)) & 1; }          /* szf n */
static inline void stf(int n)   { pdp1_hw.flags |=  (1u << (6 - n)); }               /* stf n */
static inline void clf(int n)   { pdp1_hw.flags &= ~(1u << (6 - n)); }               /* clf n */
void hlt(void);                                           /* hlt (continue resumes) */

/* ------------------------------------------------------------------ */
/* Addresses and instruction encodings (runtime code generation).       */
/* A JIT in C encodes instructions as integers, stores them, and jumps  */
/* to them; this dialect does the same with PDP-1 encodings. Natively   */
/* the address part is a placeholder: host addresses are not PDP-1 ones.*/
/* ------------------------------------------------------------------ */

#define addr_of(p)  ((word)((unsigned long)(p) & PDP1_AMASK))   /* 12-bit address */
#define AS_FN(T, w) ((T *)(unsigned long)(w))                  /* call through a word */

#define PDP1_MRI(op, p) ((insn)((op) << 12 | addr_of(p)))      /* memory-reference */
#define LAC(p) PDP1_MRI(020, p)     /* lac p */
#define LIO(p) PDP1_MRI(022, p)     /* lio p */
#define DAC(p) PDP1_MRI(024, p)     /* dac p */
#define DAP(p) PDP1_MRI(026, p)     /* dap p */
#define DIO(p) PDP1_MRI(032, p)     /* dio p */
#define ADD(p) PDP1_MRI(040, p)     /* add p */
#define SUB(p) PDP1_MRI(042, p)     /* sub p */
#define XCT(p) PDP1_MRI(010, p)     /* xct p */
#define JMP(p) PDP1_MRI(060, p)     /* jmp p */
#define STF(n) ((insn)(0760010 | (n)))   /* stf n */
#define CLF(n) ((insn)(0760000 | (n)))   /* clf n */
#define SZF(n) ((insn)(0640000 | (n)))   /* szf n */
#define RCL(n) ((insn)(0663000 | ((1 << (n)) - 1)))   /* rcl ns */
#define CMA    ((insn)0761000)           /* cma */
#define IOH    ((insn)0730000)           /* ioh */
#define DPY(i) ((insn)(0730007 - (i)))   /* dpy-i, e.g. DPY(04000) */

#define NOCOLLIDE(f) (addr_of(f) | 0400000)   /* object-table "does not collide" flag */

#endif /* PDP1_H */
