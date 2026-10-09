# Main loop: C to listing words

Cursors: a `cptr` is a pointer whose home is an instruction cell. `HERE(p)`
places that cell in the code stream at this point and executes it as the access;
every other access to `*p` is indirect (`lac i p`). `p = q` is `dap p`, `++p` is
`idx p`, and a comparison against an address is `sas (op addr`, with op taken
from the cell the cursor homes. The cell is initialized `<op> .`.

## ml0 prefix (source 665-690, listing 01444-01467)

<!-- range 01444-01467 -->

| addr | word | lowered | origin (C statement, rule) |
|---|---|---|---|
| 01444 | 223070 | lio (-4000 | `IO = -04000;` IO assigned from a literal: always `lio (k` (S5, S2, A2) |
| 01445 | 323243 | dio \mtc | `mtc = IO;` store IO (S5). `\mtc` is the first variable-pool cell in layout order, hence 03243 (L3) |
| 01446 | 703476 | law mtb | `word *p = mtb;` address constant fits 12 bits, so `law` (S2). p is AC-resident (A1) |
| 01447 | 261703 | dap ml1 | `ml1 = p;` cursor assignment is `dap`, writes only the address field (S7) |
| 01450 | 403071 | add (nob | `p += NOB;` AC busy: add a pool literal (S3, L3) |
| 01451 | 261737 | dap mx1 | `mx1 = p;` |
| 01452 | 403071 | add (nob | dedup in the pool |
| 01453 | 261747 | dap my1 |  |
| 01454 | 403071 | add (nob |  |
| 01455 | 261772 | dap ma1 |  |
| 01456 | 403071 | add (nob |  |
| 01457 | 262006 | dap mb1 |  |
| 01460 | 403071 | add (nob |  |
| 01461 | 243244 | dac \mdx | `mdx = p;` pool pointer: plain `word *`, so `dac`, not `dap` (S7) |
| 01462 | 403071 | add (nob |  |
| 01463 | 243245 | dac \mdy |  |
| 01464 | 403071 | add (nob |  |
| 01465 | 262327 | dap mom | `mom` is a cursor (its cell is in ss1) |
| 01466 | 403072 | add (2 | `p += 2;` second literal, pool order follows first use (L3) |
| 01467 | 262343 | dap mth |  |

## Object loop (source 843-941, listing 01703-02051)

<!-- range 01703-02051 -->

| addr | word | lowered | origin (C statement, rule) |
|---|---|---|---|
| 01703 | 201703 | lac . | `w = HERE(ml1);` the cell `ml1` is placed here as a load; label ml1_top (L4) |
| 01704 | 650100 | sza i | `if (w == 0) goto mq1;` (S6) |
| 01705 | 602011 | jmp mq1 |  |
| 01706 | 663777 | rcl 9s | `(void)swap(w);` static inline `swap` = two `rcl 9s` (S8) |
| 01707 | 663777 | rcl 9s |  |
| 01710 | 443261 | idx \moc | `moc++;` statement context (S7) |
| 01711 | 642000 | spi | `if (IO < 0) goto mq4;` (S6) |
| 01712 | 602003 | jmp mq4 |  |
| 01713 | 700001 | law 1 | `ml2 = ml1 + 1;` one operand is a small immediate, so `law 1` goes first and the cell is added: `law k ; add m` beats `lac m ; add (k` because it uses no pool word (S3) |
| 01714 | 401703 | add ml1 | reads the whole cell word; the opcode bits are dropped by `dap` (S7) |
| 01715 | 261734 | dap ml2 | cursor assignment (S7) |
| 01716 | 700001 | law 1 | `mx2 = mx1 + 1;` |
| 01717 | 401737 | add mx1 |  |
| 01720 | 261740 | dap mx2 |  |
| 01721 | 700001 | law 1 | `my2 = my1 + 1;` |
| 01722 | 401747 | add my1 |  |
| 01723 | 261750 | dap my2 |  |
| 01724 | 700001 | law 1 | `ma2 = ma1 + 1;` |
| 01725 | 401772 | add ma1 |  |
| 01726 | 261773 | dap ma2 |  |
| 01727 | 700001 | law 1 | `mb2 = mb1 + 1;` |
| 01730 | 402006 | add mb1 |  |
| 01731 | 261766 | dap mb2 |  |
| 01732 | 201732 | lac . | `sp5 = (cptr)HERE(mot);` cell mot placed as a load (L4) |
| 01733 | 262530 | dap sp5 | assign to a cursor whose cell is in the ship code (S7) |
| 01734 | 201734 | lac . | `v = HERE(ml2);` label ml2_top |
| 01735 | 650500 | spq | `if (v <= 0) goto mq2;` skip when v > 0 (S6) |
| 01736 | 601774 | jmp mq2 |  |
| 01737 | 201737 | lac . | `d = HERE(mx1) - HERE(mx2);` mx1 cell as the load |
| 01740 | 421740 | sub . | mx2 cell as the subtract operand: opcode inferred from the operand position (L4) |
| 01741 | 640200 | spa | `if (d < 0) d = ~d;` |
| 01742 | 761000 | cma |  |
| 01743 | 243262 | dac \mt1 | `mt1 = d;` |
| 01744 | 420016 | sub me1 | `d -= me1;` AC cache: d is still in AC (S4) |
| 01745 | 640400 | sma | `if (d >= 0) goto mq2;` |
| 01746 | 601774 | jmp mq2 |  |
| 01747 | 201747 | lac . | `d = HERE(my1) - HERE(my2);` |
| 01750 | 421750 | sub . |  |
| 01751 | 640200 | spa | `if (d < 0) d = ~d;` |
| 01752 | 761000 | cma |  |
| 01753 | 420016 | sub me1 | `d -= me1;` |
| 01754 | 640400 | sma |  |
| 01755 | 601774 | jmp mq2 |  |
| 01756 | 403262 | add \mt1 | `d += mt1;` |
| 01757 | 420017 | sub me2 | `d -= me2;` |
| 01760 | 640400 | sma |  |
| 01761 | 601774 | jmp mq2 |  |
| 01762 | 203100 | lac (mex 400000 | `t = FN_ADDR(mex) + SIGN;` symbolic constant, address plus flag bit, pool literal (S2, L3) |
| 01763 | 251703 | dac i ml1 | `*ml1 = t;` store through cursor, indirect (S7) |
| 01764 | 251734 | dac i ml2 | `*ml2 = t;` |
| 01765 | 212006 | lac i mb1 | `*mb1 + HERE(mb2)`: left operand indirect through cursor (S7) |
| 01766 | 401766 | add . | mb2 cell as the add operand (L4) |
| 01767 | 761000 | cma | `~(...)` |
| 01770 | 675377 | sar 8s | `sar(.., 8)` (S8) |
| 01771 | 402777 | add (1 | `+ 1` (S3) |
| 01772 | 241772 | dac . | `HERE(ma1) = t;` |
| 01773 | 241773 | dac . | `HERE(ma2) = t;` |
| 01774 | 441740 | idx mx2 | label mq2; `mx2++;` (S7) |
| 01775 | 441750 | idx my2 |  |
| 01776 | 441773 | idx ma2 |  |
| 01777 | 441766 | idx mb2 |  |
| 02000 | 441734 | idx ml2 | `if (++ml2 != (cptr)(mtb + NOB)) goto ml2_top;` the increment leaves the new cell word in AC (S7) |
| 02001 | 523101 | sas (lac mtb nob | compare the whole cell word against a pool literal built from ml2's own opcode (`lac`, inferred from its HERE) and the bound (S11) |
| 02002 | 601734 | jmp ml2 | branch back to the cell (S6) |
| 02003 | 211703 | lac i ml1 | label mq4; `CALL_FN(*ml1);` indirect load (S7) |
| 02004 | 262005 | dap .+1 | indirect call: patch the next instruction (C7) |
| 02005 | 622005 | jsp . | the patched call; initial address is itself (C7) |
| 02006 | 202006 | lac . | `mtc = HERE(mb1) + mtc;` cell mb1 placed here as a load (L4) |
| 02007 | 403243 | add \mtc | (S3) |
| 02010 | 243243 | dac \mtc |  |
| 02011 | 441737 | idx mx1 | label mq1; cursor increments (S7) |
| 02012 | 441747 | idx my1 |  |
| 02013 | 441772 | idx ma1 |  |
| 02014 | 442006 | idx mb1 |  |
| 02015 | 443244 | idx \mdx | pool pointers: `mdx++` is the same `idx`; only the declaration differs |
| 02016 | 443245 | idx \mdy |  |
| 02017 | 442327 | idx mom |  |
| 02020 | 442343 | idx mth |  |
| 02021 | 443263 | idx \mas |  |
| 02022 | 443246 | idx \mfu |  |
| 02023 | 443247 | idx \mtr |  |
| 02024 | 441732 | idx mot |  |
| 02025 | 442577 | idx mco |  |
| 02026 | 443250 | idx \mh1 |  |
| 02027 | 443251 | idx \mh2 |  |
| 02030 | 443252 | idx \mh3 |  |
| 02031 | 443253 | idx \mh4 |  |
| 02032 | 441703 | idx ml1 | `if (++ml1 != (cptr)(mtb + NOB - 1)) goto ml1_top;` |
| 02033 | 523102 | sas (lac mtb nob-1 |  |
| 02034 | 601703 | jmp ml1 |  |
| 02035 | 211703 | lac i ml1 | `w = *ml1;` |
| 02036 | 650100 | sza i | `if (w == 0) goto mq3;` |
| 02037 | 602045 | jmp mq3 |  |
| 02040 | 262041 | dap .+1 | `CALL_FN(w);` AC cache: w is in AC, so no reload (S4, C7) |
| 02041 | 622041 | jsp . |  |
| 02042 | 212006 | lac i mb1 | `mtc = *mb1 + mtc;` |
| 02043 | 403243 | add \mtc |  |
| 02044 | 243243 | dac \mtc |  |
| 02045 | 621130 | jsp bck | label mq3; `bck();` jsp-convention call of a PDP1_JSP function (C2) |
| 02046 | 620650 | jsp blp | `blp();` |
| 02047 | 463243 | isp \mtc | label mq3w; `if (++mtc < 0) goto mq3w;` fused index-and-skip, branch taken when the result is negative (S6) |
| 02050 | 602047 | jmp .-1 | branch to mq3w, the `isp` just above (S6) |
| 02051 | 601444 | jmp ml0 | `ml0();` tail call of a PDP1_CONT function (C8) |

All 20 + 103 words reproduced.

Pool order inside the slice (L3): `(-4000` 03070, `(nob` 03071, `(2` 03072 come
from the ml0 prefix; `(mex 400000` 03100, `(lac mtb nob` 03101, `(lac mtb
nob-1` 03102 are first used at 01762, 02001, 02033, in that order; `(1` is the
sqt literal at 02777.

Variable order inside the slice (L3): `\mtc` 03243, `\mdx` 03244, `\mdy` 03245
from ml0; `\moc` 03261, `\mt1` 03262, `\mas` 03263 are numbered by the macro1
rule (first reference in emission order) and come out right only because the
compiler emits in layout order.

Where the C is weaker than the original: the `mq1` increment run is 17
statements the author wrote as 17 `idx` words. A struct-of-cursors with a loop
would be more readable but would change the code, so it is not the lift.
