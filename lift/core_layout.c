/* Core after the code (source lines 1357-1366): the literal constants, the
 * pool words, the patch space and the object table (lift/object_table.h). */

#include "object_table.h"

/* ------------------------------------------- after the code: core layout */

CONSTANTS();                        /* the literal constants */
VARIABLES();                        /* the pool words */
RESERVE word patch_space[0200];
RESERVE word object_table[TABLE_WORDS];  /* mtb */
