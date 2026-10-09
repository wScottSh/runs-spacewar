# Tunable table and two xct call sites

Table: source 77-96, listing 00006-00031. `PDP1_ORG(6)` is `6/` (L1). The
entries that are operations are `PDP1_XCT` functions; entries that are data
are initialized words. An xct function's body must lower to exactly one word
that is not a transfer (sema check C9); anything else is a compile error, so
"may be replaced by jda or jsp" is a different C function plus a different
call site, never a silent change.

<!-- range 00006-00031 -->

| addr | word | lowered | origin (C statement, rule) |
|---|---|---|---|
| 00006 | 710041 | law i 41 | `PDP1_XCT word tno(void) { return -041; }` one word, no entry, no link (C9, S2) |
| 00007 | 675017 | sar 4s | `tvl(word a) { return sar(a, 4); }` (C9, S8) |
| 00010 | 710020 | law i 20 | rlt |
| 00011 | 710140 | law i 140 | tlf |
| 00012 | 757777 | 757777 | `word foo = -020000;` in-stream data; negative constant is ones' complement (L1) |
| 00013 | 000010 | 10 | maa |
| 00014 | 675017 | sar 4s | sac |
| 00015 | 000001 | 1 | str |
| 00016 | 006000 | 6000 | me1 |
| 00017 | 003000 | 3000 | me2 |
| 00020 | 777777 | 777777 | `ddd = NEG0` |
| 00021 | 675777 | sar 9s | the |
| 00022 | 710010 | law i 10 | mhs |
| 00023 | 710040 | law i 40 | hd1 |
| 00024 | 710100 | law i 100 | hd2 |
| 00025 | 710200 | law i 200 | hd3 |
| 00026 | 667777 | scl 9s | hr1 |
| 00027 | 667017 | scl 4s | hr2 |
| 00030 | 040000 | 40000 | hur |
| 00031 | 000000 | 0 | ran |

## Call site 1: torpedo launch (source 1273-1285, listing 02650-02664)

<!-- range 02650-02664 -->

| addr | word | lowered | origin (C statement, rule) |
|---|---|---|---|
| 02650 | 203267 | lac \sn | `HERE(sr3) = -tvl(sn) + *mdx;` arg of an xct function goes to AC first (C9, S1). `\sn` is a variable-pool cell (L2, L3) |
| 02651 | 100007 | xct tvl | call of a `PDP1_XCT` function (C9) |
| 02652 | 761000 | cma | unary minus (S3) |
| 02653 | 413244 | add i \mdx | `+ *mdx`: `mdx` is a pool pointer, deref is indirect addressing (S1) |
| 02654 | 242654 | dac . | `HERE(sr3) =`: the cell is placed here with the opcode the context wants, a store (L4). It was given its address by an earlier `dap sr3` |
| 02655 | 203272 | lac \cs | `HERE(sr4) = tvl(cs) + *mdy;` |
| 02656 | 100007 | xct tvl | (C9) |
| 02657 | 413245 | add i \mdy | (S1, S3) |
| 02660 | 242660 | dac . | sr4 cell (L4) |
| 02661 | 100010 | xct rlt | `*ma1 = rlt();` (C9) |
| 02662 | 251772 | dac i ma1 | store through the cursor `ma1`: indirect, not in place (S7) |
| 02663 | 100011 | xct tlf | label trf; `HERE(sr6) = tlf();` |
| 02664 | 242664 | dac . | sr6 cell (L4) |

## Call site 2: game start (source 816-818, listing 01655-01657)

<!-- range 01655-01657 -->

| addr | word | lowered | origin (C statement, rule) |
|---|---|---|---|
| 01655 | 100006 | xct tno | `ntr[1] = ntr[0] = tno();` value goes to AC (C9) |
| 01656 | 243754 | dac ntr | inner assignment first: `ntr[0]` (S5). `ntr` is an assembler address symbol, constant index folds to `ntr` (S1) |
| 01657 | 243755 | dac ntr+1 | outer assignment `ntr[1]`; AC still holds the value (S4, S5) |

All 20 + 13 + 3 words reproduced. Weakest point: `ntr` is a *symbol* defined
by the original's `ntr=nfu 2` chain, not a C object; the C needs the mtb
struct view (see compiler.md, open problem 5) for the same fact to be a
declaration. Here it is an `extern` array and the layout is taken on trust.
