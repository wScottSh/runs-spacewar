/* The control word: four bits per ship, from the left rotate ccw, rotate
 * cw (both: hyperspace), fire rocket and fire torpedo, ship 1's in the
 * high four bits and ship 2's in the low four.
 *
 * A control word getter is a routine entered by `jsp` that leaves the
 * control word in IO. Game control picks the getter at the start (the
 * control boxes, or the test word switches) and each spaceship calls it
 * every frame through control_word_getter. */
#ifndef CONTROL_WORD_H
#define CONTROL_WORD_H

typedef io_word control_word_reader(void) JSP;
extern POOL control_word_reader *control_word_getter;  /* cwg */

#endif
