/* corpus: entry=regulate */
/* A thermostat with four sensors in a table. regulate(v) points the sensor
 * cursor at sensor v & 3, reads it with a JSP routine that leaves the
 * reading in IO, and reads the manual override from the control boxes
 * (none pressed when no boxes are attached). It returns the heat to call
 * for: the setpoint less the reading, none when that is negative or the
 * override is held. The tape starts the program at `power_up`, which shows
 * the setpoint on the console lights. */

extern HOMED word *sensor;      /* its home is in read_sensor, below */

word readings[4] = { 0310, 0144, 0620, 0 };
word setpoint = 0400;
word last_reading = 0;
POOL word chosen;

JSP io_word read_sensor(void)
{
    register word t = *home(sensor);
    return t;
}

JSP io_word manual_override(void)
{
    register word held = 0;
    held = control_boxes();
    return held;
}

START BLOCK void power_up(void)
{
show:
    register word none = 0;
    halt(setpoint, none);
    goto show;
}

JDA word regulate(word v)
{
    chosen = v & 3;
    word *at = readings;
    at = at + chosen;
    sensor = at;
    register word t = read_sensor();
    last_reading = t;
    register word held = manual_override();
    word heat;
    if (held < 0)
        goto off;
    heat = setpoint - last_reading;
    if (heat < 0)
off:    heat = 0;
    return heat;
}

word *sensor;                   /* HOMED by the declaration above */
