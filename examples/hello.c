/* PRIME-C-CODE-BEGIN */
#include "prime.h"

/* ---- hello 演示 ----
 * 最小的端到端示例：HP Prime 控制台上的递归 + printf。
 * 是 tests/harness.py 中 'hello' 用例的基准。
 * 设备上编译：tcc examples/hello.c -run   （经 calc/main.py）
 */

int fib(int n) { return n < 2 ? n : fib(n-1) + fib(n-2); }

int main(void) {
    printf("hello from TCC on HP Prime!\n");
    printf("fib(15) = %d\n", fib(15));
    return fib(15) == 610 ? 0 : 1;
}
/* PRIME-C-CODE-END */
