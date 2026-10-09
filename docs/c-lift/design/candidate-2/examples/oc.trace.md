# oc: C to listing words (source 417-507, listing 00404-00647)

Runtime code generation is ordinary stores. The instruction constants
`I_LAC(&sx1)` and friends are symbolic: the compiler keeps them as a Macro
expression (`lac \sx1`) and macro1 does the arithmetic and the pool.
`PLINST` is a C macro, as `plinst` was a Macro macro. Order of first use makes
both the pool (03000..03047 here) and the variable cells (03223..03240) come
out as in the oracle; see compiler.md L3.

<!-- range 00404-00647 -->

| addr | word | lowered | origin (C statement, rule) |
|---|---|---|---|
| 00404 | 260411 | dap ocz | ocs, a jsp routine: prologue stores the return address (C2) |
| 00405 | 330412 | dio i oc | `*ENTRY_PTR(oc)++ = IO;` IO stored through the pointer (S5, S7) |
| 00406 | 440412 | idx oc |  |
| 00407 | 330412 | dio i oc | second `*ENTRY_PTR(oc)++ = IO;` |
| 00410 | 440412 | idx oc |  |
| 00411 | 600411 | jmp . | return cell ocz; ocs has no `return`, so it is emitted at the end of the body (C3) |
| 00412 | 000000 | 0 | oc entry cell = param `where` (C1) |
| 00413 | 260554 | dap ocx | prologue: link cell `ocx`, placed after the last return (C1, C3) |
| 00414 | 210554 | lac i ocx | `ocg = (cptr)(uintptr_t)table;` read of an `inl_data` parameter is an indirect load through the link (C4) |
| 00415 | 260434 | dap ocg | assign to cursor ocg (S7) |
| 00416 | 203000 | lac (stf 5 | `PLINST(I_STF(5));` load the instruction constant (S2, L3) |
| 00417 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00420 | 440412 | idx oc | post-increment (S7) |
| 00421 | 260555 | dap ocm | `ocm = (cptr)where;` AC cache holds `where` after the `idx` (S4, S7) |
| 00422 | 440554 | idx ocx | `skip_inline(1);` (C4) |
| 00423 | 203001 | lac (lac \sx1 | `PLINST(I_LAC(&sx1));` load the instruction constant (S2, L3) |
| 00424 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00425 | 440412 | idx oc | post-increment (S7) |
| 00426 | 203002 | lac (lio \sy1 | `PLINST(I_LIO(&sy1));` load the instruction constant (S2, L3) |
| 00427 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00430 | 440412 | idx oc | post-increment (S7) |
| 00431 | 760006 | clf 6 | `clf(6);` builtin, one word |
| 00432 | 710006 | law i 6 | label ocj; `occ = -6;` (S2) |
| 00433 | 243225 | dac \occ |  |
| 00434 | 220434 | lio . | `IO = HERE(ocg);` cell ocg placed here as a load into IO (L4, A2) |
| 00435 | 760200 | cla | label och; `t = rcl(0, 3);` constant 0 into AC is `cla` (S2) |
| 00436 | 663007 | rcl 3s |  |
| 00437 | 323226 | dio \oci | `oci = IO;` |
| 00440 | 223003 | lio (rcl 9s | `IO = I_RCL(9);` (S5) |
| 00441 | 403004 | add (. 3 | `switch (t)`: dense cases 0..7 -> dispatch head; table base is the address three words on (S9, L3) |
| 00442 | 260443 | dap .+1 | patch the next word (S9) |
| 00443 | 600443 | jmp . | the patched jump (S9) |
| 00444 | 760000 | opr | table slot 0: `case 0: nop();` one-word case body *is* the slot (S9) |
| 00445 | 600557 | jmp oc1 | slot 1: `case 1: goto oc1;` case 0 falls through into it, as in C (S9) |
| 00446 | 600602 | jmp oc2 | slot 2 |
| 00447 | 600610 | jmp oc3 | slot 3 |
| 00450 | 600616 | jmp oc4 | slot 4 |
| 00451 | 600624 | jmp oc5 | slot 5 |
| 00452 | 600632 | jmp oc6 | slot 6 |
| 00453 | 203005 | lac (szf 5 | `PLINST(I_SZF(5));` load the instruction constant (S2, L3) |
| 00454 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00455 | 440412 | idx oc | post-increment (S7) |
| 00456 | 403006 | add (4 | `ocn = (cptr)(where + 4);` AC cache holds `where` (S4, S3) |
| 00457 | 260556 | dap ocn |  |
| 00460 | 200556 | lac ocn | `PLINST(CELL_WORD(ocn));` the whole cell word is data (S1) |
| 00461 | 250412 | dac i oc |  |
| 00462 | 440412 | idx oc |  |
| 00463 | 203007 | lac (dac \sx1 | `PLINST(I_DAC(&sx1));` load the instruction constant (S2, L3) |
| 00464 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00465 | 440412 | idx oc | post-increment (S7) |
| 00466 | 203010 | lac (dio \sy1 | `PLINST(I_DIO(&sy1));` load the instruction constant (S2, L3) |
| 00467 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00470 | 440412 | idx oc | post-increment (S7) |
| 00471 | 203011 | lac (jmp sq6 | `PLINST(I_JMP(FN_ADDR(sq6)));` load the instruction constant (S2, L3) |
| 00472 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00473 | 440412 | idx oc | post-increment (S7) |
| 00474 | 203012 | lac (clf 5 | `PLINST(I_CLF(5));` load the instruction constant (S2, L3) |
| 00475 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00476 | 440412 | idx oc | post-increment (S7) |
| 00477 | 203013 | lac (lac \scm | `PLINST(I_LAC(&scm));` load the instruction constant (S2, L3) |
| 00500 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00501 | 440412 | idx oc | post-increment (S7) |
| 00502 | 203014 | lac (cma | `PLINST(I_CMA);` load the instruction constant (S2, L3) |
| 00503 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00504 | 440412 | idx oc | post-increment (S7) |
| 00505 | 203015 | lac (dac \scm | `PLINST(I_DAC(&scm));` load the instruction constant (S2, L3) |
| 00506 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00507 | 440412 | idx oc | post-increment (S7) |
| 00510 | 203016 | lac (lac \ssm | `PLINST(I_LAC(&ssm));` load the instruction constant (S2, L3) |
| 00511 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00512 | 440412 | idx oc | post-increment (S7) |
| 00513 | 203014 | lac (cma | `PLINST(I_CMA);` load the instruction constant (S2, L3) |
| 00514 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00515 | 440412 | idx oc | post-increment (S7) |
| 00516 | 203017 | lac (dac \ssm | `PLINST(I_DAC(&ssm));` load the instruction constant (S2, L3) |
| 00517 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00520 | 440412 | idx oc | post-increment (S7) |
| 00521 | 203020 | lac (lac \csm | `PLINST(I_LAC(&csm));` load the instruction constant (S2, L3) |
| 00522 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00523 | 440412 | idx oc | post-increment (S7) |
| 00524 | 203021 | lac (lio \ssd | `PLINST(I_LIO(&ssd));` load the instruction constant (S2, L3) |
| 00525 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00526 | 440412 | idx oc | post-increment (S7) |
| 00527 | 203022 | lac (dac \ssd | `PLINST(I_DAC(&ssd));` load the instruction constant (S2, L3) |
| 00530 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00531 | 440412 | idx oc | post-increment (S7) |
| 00532 | 203023 | lac (dio \csm | `PLINST(I_DIO(&csm));` load the instruction constant (S2, L3) |
| 00533 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00534 | 440412 | idx oc | post-increment (S7) |
| 00535 | 203024 | lac (lac \ssc | `PLINST(I_LAC(&ssc));` load the instruction constant (S2, L3) |
| 00536 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00537 | 440412 | idx oc | post-increment (S7) |
| 00540 | 203025 | lac (lio \csn | `PLINST(I_LIO(&csn));` load the instruction constant (S2, L3) |
| 00541 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00542 | 440412 | idx oc | post-increment (S7) |
| 00543 | 203026 | lac (dac \csn | `PLINST(I_DAC(&csn));` load the instruction constant (S2, L3) |
| 00544 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00545 | 440412 | idx oc | post-increment (S7) |
| 00546 | 203027 | lac (dio \ssc | `PLINST(I_DIO(&ssc));` load the instruction constant (S2, L3) |
| 00547 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00550 | 440412 | idx oc | post-increment (S7) |
| 00551 | 200555 | lac ocm | `PLINST(CELL_WORD(ocm));` |
| 00552 | 250412 | dac i oc |  |
| 00553 | 440412 | idx oc |  |
| 00554 | 600554 | jmp . | `return;` -> return cell ocx, after the textually last return (C3, C5) |
| 00555 | 600555 | jmp . | `CELL_HERE(ocm, "jmp");` plain storage cell (L4) |
| 00556 | 600556 | jmp . | `CELL_HERE(ocn, "jmp");` |
| 00557 | 203030 | lac (add \ssn | `PLINST(I_ADD(&ssn));` load the instruction constant (S2, L3) |
| 00560 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00561 | 440412 | idx oc | post-increment (S7) |
| 00562 | 620404 | jsp ocs | label oc1; `ocs();` jsp-convention call (C2) |
| 00563 | 203031 | lac (sub \scn | `t = I_SUB(&scn);` t is AC-resident and flows into the label below (A1) |
| 00564 | 250412 | dac i oc | label oce; `*where++ = t;` (S7) |
| 00565 | 440412 | idx oc |  |
| 00566 | 620404 | jsp ocs | `ocs();` |
| 00567 | 203032 | lac (ioh | `PLINST(I_IOH);` load the instruction constant (S2, L3) |
| 00570 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00571 | 440412 | idx oc | post-increment (S7) |
| 00572 | 203033 | lac (dpy-4000 | `t = I_DPY_NW;` |
| 00573 | 250412 | dac i oc | label ocd; `*where++ = t;` |
| 00574 | 440412 | idx oc |  |
| 00575 | 223226 | lio \oci | `IO = oci;` |
| 00576 | 463225 | isp \occ | `if (++occ < 0) goto och;` (S6) |
| 00577 | 600435 | jmp och |  |
| 00600 | 440434 | idx ocg | `ocg++;` (S7) |
| 00601 | 600432 | jmp ocj | `goto ocj;` |
| 00602 | 203034 | lac (add \scm | label oc2; `COMTAB(..)`: `PLINST(A)` (S2) |
| 00603 | 250412 | dac i oc |  |
| 00604 | 440412 | idx oc |  |
| 00605 | 620404 | jsp ocs | `ocs();` |
| 00606 | 203035 | lac (add \ssm | `t = B;` |
| 00607 | 600564 | jmp oce | `goto oce;` |
| 00610 | 203036 | lac (add \ssc | label oc3; `COMTAB(..)`: `PLINST(A)` (S2) |
| 00611 | 250412 | dac i oc |  |
| 00612 | 440412 | idx oc |  |
| 00613 | 620404 | jsp ocs | `ocs();` |
| 00614 | 203037 | lac (sub \csm | `t = B;` |
| 00615 | 600564 | jmp oce | `goto oce;` |
| 00616 | 203040 | lac (sub \scm | label oc4; `COMTAB(..)`: `PLINST(A)` (S2) |
| 00617 | 250412 | dac i oc |  |
| 00620 | 440412 | idx oc |  |
| 00621 | 620404 | jsp ocs | `ocs();` |
| 00622 | 203041 | lac (sub \ssm | `t = B;` |
| 00623 | 600564 | jmp oce | `goto oce;` |
| 00624 | 203042 | lac (add \csn | label oc5; `COMTAB(..)`: `PLINST(A)` (S2) |
| 00625 | 250412 | dac i oc |  |
| 00626 | 440412 | idx oc |  |
| 00627 | 620404 | jsp ocs | `ocs();` |
| 00630 | 203043 | lac (sub \ssd | `t = B;` |
| 00631 | 600564 | jmp oce | `goto oce;` |
| 00632 | 640006 | szf 6 | label oc6; `if (flag(6)) goto oc9;` (S6) |
| 00633 | 600642 | jmp oc9 |  |
| 00634 | 760016 | stf 6 | `stf(6);` |
| 00635 | 203044 | lac (dac \ssa | `PLINST(I_DAC(&ssa));` load the instruction constant (S2, L3) |
| 00636 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00637 | 440412 | idx oc | post-increment (S7) |
| 00640 | 203045 | lac (dio \ssi | `t = I_DIO(&ssi);` |
| 00641 | 600573 | jmp ocd | `goto ocd;` |
| 00642 | 760006 | clf 6 | label oc9; `clf(6);` |
| 00643 | 203046 | lac (lac \ssa | `PLINST(I_LAC(&ssa));` load the instruction constant (S2, L3) |
| 00644 | 250412 | dac i oc | store through the pointer cell `where`, which is oc's entry cell (S7) |
| 00645 | 440412 | idx oc | post-increment (S7) |
| 00646 | 203047 | lac (lio \ssi | `t = I_LIO(&ssi);` |
| 00647 | 600573 | jmp ocd | `goto ocd;` |

All 164 words reproduced.

Rules the slice needed that the other examples did not: S9 (dense switch to a
dispatch table whose slots are the one-word case bodies, last case following
the table) and L4 `CELL_HERE` (a cell used only as data). What is only
argued, not demonstrated by the hash: `sq6`. See compiler.md open problem 2.
