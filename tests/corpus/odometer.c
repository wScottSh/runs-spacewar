/* corpus: entry=drive */
/* A trip odometer. The tape starts the program at `reset_trip`, which
 * zeroes the trip count and waits on a halt; continuing resets it again.
 * drive(d) adds the distance d to the total and to the trip, and returns
 * the trip. */

word total = 0;
word trip = 0;

START BLOCK void reset_trip(void)
{
reset:
    trip = 0;
    register word shown = trip;
    halt(total, shown);
    goto reset;
}

JDA word drive(word d)
{
    total = d + total;
    trip = d + trip;
    return trip;
}
