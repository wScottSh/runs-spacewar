/* Reads octal inputs, calls ENTRY on each, prints the result word in octal
 * followed by the WATCH words. Built with -include pdp1.h -include prog.c. */
#include <cstdio>

int main() {
    unsigned v;
    while (std::scanf("%o", &v) == 1) {
        word r = ENTRY(word::bits(v));
        std::printf("%06o", r.v);
        WATCH
        std::printf("\n");
    }
    return 0;
}
