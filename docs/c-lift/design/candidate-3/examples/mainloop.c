/* Object loop of the main control routine (source lines 843-941):
 * for each object, call its calc routine; for each later object, test for
 * collision and replace both calc routines with the explosion. Then the
 * last object, the background, the central star, and burn the rest of the
 * frame.
 *
 * The walking pointers live in the address fields of the instructions that
 * dereference them (HOMED); `*home(p)` marks that instruction. Every other
 * `*p` goes indirect through it. */
#include "spacewar.h"

HOMED word *ml1, *ml2, *mx1, *mx2, *my1, *my2, *ma1, *ma2, *mb1, *mb2;
HOMED code *mot;

BLOCK SYM("ml1") void objloop(void)     /* entered by jmp ml1 from ml0 */
{
    do {
        word w = *home(ml1);            /* this object's calc routine */
        if (w == 0)
            goto mq1;                   /* slot empty */
        register word ctl = w;          /* AC -> IO */
        ++moc;
        if (ctl < 0)
            goto mq4;                   /* does not collide */
        ml2 = 1 + ml1;                  /* compare with every later object */
        mx2 = 1 + mx1;
        my2 = 1 + my1;
        ma2 = 1 + ma1;
        mb2 = 1 + mb1;
        sp5 = *home(mot);               /* this ship's compiled outline */
        do {
            word w2 = *home(ml2);
            if (w2 <= 0)
                continue;               /* empty, or cannot collide */
            word d = *home(mx1) - *home(mx2);
            if (d < 0)
                d = -d;
            mt1 = d;
            if (d - me1 >= 0)
                continue;               /* |dx| >= epsilon */
            d = *home(my1) - *home(my2);
            if (d < 0)
                d = -d;
            d -= me1;
            if (d >= 0)
                continue;               /* |dy| >= epsilon */
            if (d + mt1 - me2 >= 0)
                continue;               /* outside the diamond */
            *ml1 = CODE(mex) | NOCOLLIDE;   /* both explode */
            *ml2 = CODE(mex) | NOCOLLIDE;
            word t = -(*mb1 + *home(mb2));
            t = (t >> 8) + 1;           /* duration of explosion */
            *home(ma1) = t;
            *home(ma2) = t;
        } while (++mx2, ++my2, ++ma2, ++mb2, ++ml2 != &mtb[NOB]);
mq4:
        call(*ml1);                     /* calc and display this object */
        mtc = *home(mb1) + mtc;         /* charge its instruction count */
mq1:
        ++mx1; ++my1; ++ma1; ++mb1; ++mdx; ++mdy; ++mom; ++mth; ++mas;
        ++mfu; ++mtr; ++mot; ++mco; ++mh1; ++mh2; ++mh3; ++mh4;
    } while (++ml1 != &mtb[NOB - 1]);

    word w = *ml1;                      /* last object: display only */
    if (w != 0) {
        call(w);
        mtc = *mb1 + mtc;
    }
    bck();                              /* stars of the heavens */
    blp();                              /* the massive star */
    while (++mtc < 0)
        ;                               /* burn the rest of the frame */
    ml0();
}
