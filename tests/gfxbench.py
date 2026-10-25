#!/usr/bin/env python3
"""gfxbench.py -- measure the graphics library's cost on the emulator.

Writes a fixed draw workload to code.c, compiles it exactly the way the
calculator does (tcc.elf inside the emulator, linking rt_core.o etc.),
runs it, and reports the USER-RUN instruction count from emu.insn_count
(deterministic -- same code always yields the same count, so before/after
comparisons of library changes are exact).

Run:  python3 tests/gfxbench.py [bench|tri]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import harness
from harness import TCC_ELF, FAKE, run_elf, run_user, make_fake_fs

WORKLOAD = r'''
#include "prime.h"
#include "hp_gfx.h"

int main(void) {
    int i;
    hp_grob *g;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n", 0, 0, 0, 0); return 1; }
    /* each block sized so its cost stands out above noise */
    for (i = 0; i < 5; i++) hp_clear(HP_BLACK);
    printf("B1\n", 0, 0, 0, 0);
    for (i = 0; i < 20; i++) hp_fill_rect(20, 20, 140, 100, HP_RED);
    printf("B2\n", 0, 0, 0, 0);
    for (i = 0; i < 15; i++) hp_fill_circle(160, 120, 60, HP_GREEN);
    printf("B3\n", 0, 0, 0, 0);
    for (i = 0; i < 15; i++) {
        hp_line(0, 0, 319, 239, HP_WHITE);
        hp_line(319, 0, 0, 239, HP_BLUE);
    }
    printf("B4\n", 0, 0, 0, 0);
    for (i = 0; i < 50; i++) hp_text(5, 5, "HELLO WORLD 123", HP_CYAN);
    printf("B5\n", 0, 0, 0, 0);
    g = hp_grob_new(320, 240);
    if (g) {
        hp_grob_select(g);
        hp_fill_rect(0, 0, 320, 240, HP_GRAY);
        hp_grob_select(0);
        for (i = 0; i < 5; i++) hp_grob_blit(g, 0, 0);
        hp_grob_free(g);
    }
    printf("BENCH_DONE\n", 0, 0, 0, 0);
    return 0;
}
'''

TRIANGLE = r'''
#include "prime.h"
#include "hp_gfx.h"

int main(void) {
    int i;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n", 0, 0, 0, 0); return 1; }
    hp_clear(HP_BLACK);
    for (i = 0; i < 30; i++)
        hp_fill_triangle(10, 10, 200, 40, 90, 180, HP_RED);
    printf("TRI_DONE\n", 0, 0, 0, 0);
    return 0;
}
'''


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'bench'
    make_fake_fs()
    code = WORKLOAD if which == 'bench' else TRIANGLE
    with open(os.path.join(FAKE, 'code.c'), 'w') as f:
        f.write(code)
    argv = [
        'tcc',
        '-nostdlib', '-shared', '-Wl,-e,hp_entry',
        '-I', r'C:\DATA\primetcc.hpappdir',
        '-o', r'C:\DATA\primetcc.hpappdir\code.elf',
        r'C:\DATA\primetcc.hpappdir\code.c',
        r'C:\DATA\primetcc.hpappdir\rt_core.o',
        r'C:\DATA\primetcc.hpappdir\rt_svc.o',
        r'C:\DATA\primetcc.hpappdir\rt_aeabi.o',
        r'C:\DATA\primetcc.hpappdir\rt_math.o',
    ]
    print('==> compiling (%s)...' % which)
    ret, out, emu = run_elf(TCC_ELF, argv, 'tcc', max_insn=2000000000)
    code_elf = os.path.join(FAKE, 'code.elf')
    if not os.path.exists(code_elf):
        print('!! code.elf not produced')
        sys.exit(1)
    ret2, out2, emu2 = run_user(code_elf, max_insn=500000000)
    if 'BENCH_DONE' not in out2 and 'TRI_DONE' not in out2:
        print('!! bench did not finish')
        sys.exit(1)
    print('BENCH RESULT: exit=%s user-insn=%d' % (ret2, emu2.insn_count))


if __name__ == '__main__':
    main()
