#!/usr/bin/env python3
"""gfxbreakdown.py -- per-workload-block instruction counts.

Runs the same compile+flow as gfxbench.py but records emu.insn_count at
every PRIMELOG flush, so the B1..B5 marker lines give an exact
per-block instruction delta.  Deterministic.
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
    printf("B0\n", 0, 0, 0, 0);
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
    printf("END\n", 0, 0, 0, 0);
    return 0;
}
'''


def main():
    make_fake_fs()
    with open(os.path.join(FAKE, 'code.c'), 'w') as f:
        f.write(WORKLOAD)
    argv = [
        'tcc', '-nostdlib', '-shared', '-Wl,-e,hp_entry',
        '-I', r'C:\DATA\primetcc.hpappdir',
        '-o', r'C:\DATA\primetcc.hpappdir\code.elf',
        r'C:\DATA\primetcc.hpappdir\code.c',
        r'C:\DATA\primetcc.hpappdir\rt_core.o',
        r'C:\DATA\primetcc.hpappdir\rt_svc.o',
        r'C:\DATA\primetcc.hpappdir\rt_aeabi.o',
        r'C:\DATA\primetcc.hpappdir\rt_math.o',
    ]
    ret, out, emu = run_elf(TCC_ELF, argv, 'tcc', max_insn=2000000000)
    code_elf = os.path.join(FAKE, 'code.elf')
    # replicate run_user() but install an insn-counting list BEFORE run,
    # since run_user builds its own emulator internally
    import struct
    from emu_arm2 import ARMEmu
    from harness import BASE, USER_BASE

    class OutSpy(list):
        def __init__(self):
            super().__init__()
            self.marks = []

        def append(self, chunk):
            self.marks.append((emu2.insn_count, bytes(chunk)))
            list.append(self, chunk)

    emu2 = ARMEmu()
    tcc = open(TCC_ELF, 'rb').read()
    emu2.load_elf(tcc, BASE)
    state = emu2.find_magic(b'PRIMEIN')
    assert state is not None, 'PRIMEIN not found'
    entry = emu2.load_elf(open(code_elf, 'rb').read(), USER_BASE)
    log = emu2.find_magic(b'PRIMELOG', USER_BASE)
    assert log is not None, 'PRIMELOG not found'
    emu2.log_addr = log
    emu2.drained = emu2.rd32(log + 8)
    emu2.max_insn = 500000000
    spy = OutSpy()
    emu2.out = spy
    ret2 = emu2.run(entry, state, base=USER_BASE)
    print('=== block breakdown (insn_count at each flush) ===')
    for cnt, chunk in spy.marks:
        s = chunk.decode('latin1', 'replace').strip()
        for line in s.splitlines():
            if line.startswith(('B', 'END')):
                print('%12d  %s' % (cnt, line))
    print('total=%d exit=%s' % (emu2.insn_count, hex(ret2)))


if __name__ == '__main__':
    main()
