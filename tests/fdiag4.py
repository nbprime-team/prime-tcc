#!/usr/bin/env python3
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import harness

CODE = r'''
#include "prime.h"
static union { double d; unsigned long long u; } cu;
int main(void) {
    double f = 4.794;
    double b = 4.0;
    double r1 = f - b;
    double r2 = f - 4.0;
    double r3 = 4.794 - 4.0;   /* folded by compiler? */
    cu.d = f;   printf("f=%08x%08x\n", (unsigned long)(cu.u>>32), (unsigned long)cu.u, 0, 0);
    cu.d = b;   printf("b=%08x%08x\n", (unsigned long)(cu.u>>32), (unsigned long)cu.u, 0, 0);
    cu.d = r1;  printf("r1=%08x%08x\n", (unsigned long)(cu.u>>32), (unsigned long)cu.u, 0, 0);
    cu.d = r2;  printf("r2=%08x%08x\n", (unsigned long)(cu.u>>32), (unsigned long)cu.u, 0, 0);
    cu.d = r3;  printf("r3=%08x%08x\n", (unsigned long)(cu.u>>32), (unsigned long)cu.u, 0, 0);
    printf("F4DONE\n", 0, 0, 0, 0);
    return 0;
}
'''
def main():
    harness.make_fake_fs()
    with open(os.path.join(HERE, 'fake_cdata', 'primetcc.hpappdir', 'code.c'), 'w') as f:
        f.write(CODE)
    argv = ['tcc', '-nostdlib', '-shared', '-Wl,-e,main',
            '-I', r'C:\DATA\primetcc.hpappdir',
            '-o', r'C:\DATA\primetcc.hpappdir\code.elf',
            r'C:\DATA\primetcc.hpappdir\code.c',
            r'C:\DATA\primetcc.hpappdir\hp_rt.c',
            r'C:\DATA\primetcc.hpappdir\rt_svc.o',
            r'C:\DATA\primetcc.hpappdir\rt_aeabi.o']
    ret, out, emu = harness.run_elf(harness.TCC_ELF, argv, 'tcc', max_insn=2000000000)
    code_elf = os.path.join(HERE, 'fake_cdata', 'primetcc.hpappdir', 'code.elf')
    ret2, out2, emu2 = harness.run_elf(code_elf, [], 'user', max_insn=500000000)
    print(out2)
if __name__ == '__main__':
    main()
