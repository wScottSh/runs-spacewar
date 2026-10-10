/* The outlines of the spaceships (source lines 1336-1356), the input of
 * the outline compiler. Each word holds six 3-bit direction codes, read
 * from the left, that trace one side of the ship from its nose down to its
 * tail; the 7 code ends the outline. Five spare words after each outline
 * leave room to make it longer. */

word needle_outline[8] SYM("ot1") = {       /* spaceship 1, the needle */
    0111131,
    0111111,
    0111111,
    0111163,
    0311111,
    0146111,
    0111114,
    0700000,
};
RESERVE word needle_spare[5];

word wedge_outline[8] SYM("ot2") = {        /* spaceship 2, the wedge */
    0013113,
    0113111,
    0116313,
    0131111,
    0161151,
    0111633,
    0365114,
    0700000,
};
RESERVE word wedge_spare[5];
