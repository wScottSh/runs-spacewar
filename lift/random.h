/* The random number generator (the `random` macro), shared by every routine
 * that draws on it: the central star, explosions, hyperspace and the
 * spaceships. */
#ifndef RANDOM_H
#define RANDOM_H

extern word random_number;  /* ran */

/* The next value of random_number, also left in AC. */
static inline word next_random(void)
{
    random_number = (rar(random_number, 1) ^ 0355670) + 0355670;
    return random_number;
}

#endif
