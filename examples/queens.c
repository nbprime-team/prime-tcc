/*
 * queens.c —— primetcc 的八皇后演示（控制台版）
 *
 * 用回溯法求解经典的八皇后问题，并把全部 92 个解打印到控制台，每行
 * 一个，写法是第 1..8 行的列用字母 a..h 表示：
 *
 *   Q01 a e h f c g b d
 *   Q02 a f h c g d b e
 *   ...
 *   Q92 h d a c f b g e
 *   QUEENS total=92
 *   QUEENS_DONE
 *
 * 自行运行、打印并退出——无需按键（控制台输出保存在 PRIMELOG 环形
 * 缓冲中，直到 main.py 抽干它）。确定性的输出同时充当回归预期。
 */
#include "prime.h"

static int col[8];            /* col[r] = 第 r 行皇后的列 */
static int sols[92][8];       /* 全部解（行 0..7 -> 列 0..7） */
static int n_sols;

static int ok(int r, int c)
{
    int i, d;
    for (i = 0; i < r; i++) {
        d = col[i] - c;
        if (d == 0 || d == r - i || d == i - r)
            return 0;         /* 同列或同对角线 */
    }
    return 1;
}

static void solve(int r)
{
    int c, i;
    if (r == 8) {                         /* 8 行已全部放置 */
        if (n_sols < 92)
            for (i = 0; i < 8; i++)
                sols[n_sols][i] = col[i];
        n_sols++;
        return;
    }
    for (c = 0; c < 8; c++) {
        if (ok(r, c)) {
            col[r] = c;
            solve(r + 1);
        }
    }
}

static void print_sol(int n)
{
    char b[40];
    char *p = b;
    const int *s = sols[n - 1];
    int i;
    *p++ = 'Q';
    *p++ = (char)('0' + (n / 10) % 10);
    *p++ = (char)('0' + n % 10);
    *p++ = ' ';
    for (i = 0; i < 8; i++) {
        *p++ = (char)('a' + s[i]);        /* 列 0 -> 'a' ... 7 -> 'h' */
        if (i < 7)
            *p++ = ' ';
    }
    *p = 0;
    puts(b);
}

int main(void)
{
    int k;
    puts("QUEENS solve start");
    solve(0);
    for (k = 1; k <= n_sols && k <= 92; k++)
        print_sol(k);
    printf("QUEENS total=%d\n", (unsigned long)n_sols, 0, 0, 0, 0, 0, 0, 0);
    puts("QUEENS_DONE");
    return 0;
}
