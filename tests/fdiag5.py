#!/usr/bin/env python3
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import harness

CODE = r'''
#include "prime.h"
static union { double d; unsigned long long u; } cu;
static void show(const char *tag, double v) {
    cu.d = v;
    printf("%s=%08x%08x\n", tag, (unsigned long)(cu.u>>32), (unsigned long)cu.u, 0);
}
int main(void) {
    double a = 5.0, b = 4.0, c = 4.794, d = 0.5;
    show("add54", a + b);      /* 9.0  = 0x4022000000000000 */
    show("sub54", a - b);      /* 1.0  = 0x3FF0000000000000 */
    show("sub4794", c - b);    /* 0.794 */
    show("mul5", a * d);       /* 2.5  = 0x4004000000000000 */
    show("div5", a / d);       /* 10.0 = 0x4024000000000000 */
    show("cmp", a < b ? 1.0 : 0.0);
    printf("F5DONE\n", 0, 0, 0, 0);
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
