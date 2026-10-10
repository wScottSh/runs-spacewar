/* reject: one instruction shifts 1..9 places */
/* `rcl 9s` is the longest shift one instruction makes. */

word step = I_RCL(10);
