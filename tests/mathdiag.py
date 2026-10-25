#!/usr/bin/env python3
# mathdiag.py -- emulator diagnostic: print intermediate math values
import os, shutil, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
FAKE = os.path.join(HERE, 'fake_cdata', 'primetcc.hpappdir')
sys.path.insert(0, HERE)
import harness
from emu_arm2 import ARMEmu, BASE

CODE = r'''
#include "prime.h"
#include "hp_math.h"
union { double d; unsigned long long u; } cu;

int main(void) {
    int e;
    double m = hp_frexp(2.718281828459045, &e);
    cu.d = m;
    printf("frexp e=%d\n", e, 0, 0, 0);
    printf("frexp m_hi=%08x m_lo=%08x\n", (unsigned long)(cu.u >> 32),
           (unsigned long)cu.u, 0, 0);
    cu.d = 2.718281828459045;
    printf("x_hi=%08x x_lo=%08x\n", (unsigned long)(cu.u >> 32),
           (unsigned long)cu.u, 0, 0);
    /* magic seed test */
    cu.u = 0x5FE6EB50C7B537A9ULL - (cu.u >> 1);
    printf("seed_hi=%08x seed_lo=%08x\n", (unsigned long)(cu.u >> 32),
           (unsigned long)cu.u, 0, 0);
    /* formatter test with a literal */
    { char b[40]; hp_double_to_str(b, 0.7853981633974483, 6); prints(b); prints("\n"); }
    { char b[40]; hp_double_to_str(b, hp_atan2(1.0, 1.0), 6); prints(b); prints("\n"); }
    { char b[40]; hp_double_to_str(b, hp_log(2.718281828459045), 6); prints(b); prints("\n"); }
    { char b[40]; hp_double_to_str(b, hp_sqrt(2.0), 6); prints(b); prints("\n"); }
    printf("DIAG_DONE\n", 0, 0, 0, 0);
    return 0;
}
'''
def main():
    harness.make_fake_fs()
    with open(os.path.join(FAKE, 'code.c'), 'w') as f:
        f.write(CODE)
    argv = [
        'tcc', '-nostdlib', '-shared', '-Wl,-e,main',
        '-I', r'C:\DATA\primetcc.hpappdir',
        '-o', r'C:\DATA\primetcc.hpappdir\code.elf',
        r'C:\DATA\primetcc.hpappdir\code.c',
        r'C:\DATA\primetcc.hpappdir\hp_rt.c',
        r'C:\DATA\primetcc.hpappdir\hp_gfx.c',
        r'C:\DATA\primetcc.hpappdir\hp_input.c',
        r'C:\DATA\primetcc.hpappdir\hp_math.c',
        r'C:\DATA\primetcc.hpappdir\rt_svc.o',
        r'C:\DATA\primetcc.hpappdir\rt_aeabi.o',
    ]
    ret, out, emu = harness.run_elf(harness.TCC_ELF, argv, 'tcc', max_insn=2000000000)
    code_elf = os.path.join(FAKE, 'code.elf')
    ret2, out2, emu2 = harness.run_elf(code_elf, [], 'user', max_insn=500000000)
    print('--- user output ---')
    print(out2)

if __name__ == '__main__':
    main()
