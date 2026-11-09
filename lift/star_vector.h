/* Two pool words (bx, by) that two routines use at different times of a
 * frame: the central star keeps the slope of its line in them, and the
 * spaceship calc routine the pull of the star's gravity on a ship. */
#ifndef STAR_VECTOR_H
#define STAR_VECTOR_H

POOL word star_vector_x;
POOL word star_vector_y;

#endif
