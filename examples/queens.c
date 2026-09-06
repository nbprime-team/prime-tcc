/*
 * queens.c -- eight queens demo for primetcc (console edition)
 *
 * Solves the classic 8-queens puzzle by backtracking and prints ALL 92
 * solutions to the console, one per line, as the columns of rows 1..8
 * written as the letters a..h:
 *
 *   Q01 a e h f c g b d
 *   Q02 a f h c g d b e
 *   ...
 *   Q92 h d a c f b g e
 *   QUEENS total=92
 *   QUEENS_DONE
 *
 * Runs, prints and exits on its own -- no keys needed (the console output
 * is kept in the PRIMELOG ring, so it survives until main.py drains it).
 * Deterministic output doubles as the regression expectation.
 */
#include "prime.h"

static int col[8];            /* col[r] = column of the queen in row r */
static int sols[92][8];       /* all solutions (rows 0..7 -> columns 0..7) */
static int n_sols;

static int ok(int r, int c)
{
    int i, d;
    for (i = 0; i < r; i++) {
        d = col[i] - c;
        if (d == 0 || d == r - i || d == i - r)
            return 0;         /* same column or same diagonal */
    }
    return 1;
}

static void solve(int r)
{
    int c, i;
    if (r == 8) {                         /* all 8 rows placed */
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
        *p++ = (char)('a' + s[i]);        /* column 0 -> 'a' ... 7 -> 'h' */
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
