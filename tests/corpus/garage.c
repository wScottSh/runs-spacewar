/* corpus: entry=park */
/* A garage of six bays in three parallel rows: the parked car's routine
 * word (0 when the bay is free), its plate and its meter. park(v) parks a
 * car in the first free bay: the bay gets the address of `ticket`, the
 * plate v (passed through IO), and the meter v's low twelve bits over
 * all-ones with sense switch 1 on, over what it held otherwise. The
 * pointers to the new car's plate and meter are held in the instructions
 * that store them, built from the bay pointer. Then a car leaves: with
 * sense switch 2 the one in the first bay, otherwise the one just parked,
 * so a bay is always free when the next car comes. Returns the word of the
 * bay found. */

#define BAYS 6
#define PAID ((word)0)

word garage[3 * BAYS] = {
    0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0,
    -1, 0777, 0, 0, 0, 012345,
};
extern word *meter;
HOMED word *bay;
HOMED word *plate;
HOMED word *meter;
HOMED word *leaving;
POOL word found;

JSP void ticket(void)
{
}

JDA word park(word v)
{
    register word p = v;

    bay = garage;
look:
    if (*home(bay) == 0)
        goto free;
    if (I_LAC(++bay) != I_LAC(garage + BAYS))
        goto look;
    for (;;)
        hlt();                      /* no free bay */
free:
    *bay = ticket | PAID;
    plate = BAYS + bay;
    *home(plate) = p;
    meter = plate + BAYS;
    if (sense(1))
        *meter = MINUS_ZERO;
    home(meter)->addr = v;
    found = *bay;
    if (sense(2))
        goto first;
    leaving = bay;
    goto leave;
first:
    leaving = garage;
leave:
    if (0 == *leaving)
        goto done;
    *home(leaving) = 0;
done:
    return found;
}
