/* PRIME-C-CODE-BEGIN */
#include "prime.h"

/* ---- hello demo ----
 * Smallest end-to-end example: recursion + printf on the HP Prime
 * console.  Source of truth for tests/harness.py's 'hello' case.
 * Compile on-device:  tcc examples/hello.c -run   (via calc/main.py)
 */

int fib(int n) { return n < 2 ? n : fib(n-1) + fib(n-2); }

int main(void) {
    printf("hello from TCC on HP Prime!\n");
    printf("fib(15) = %d\n", fib(15));
    return fib(15) == 610 ? 0 : 1;
}
/* PRIME-C-CODE-END */
