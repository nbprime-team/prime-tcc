#!/usr/bin/env python3
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import harness

CODE = r'''
#include "prime.h"
#include "hp_math.h"
static union { double dv; unsigned long long uv; } cu;

static void show(const char *tag, double v) {
    cu.dv = v;
    printf("%s=%08x%08x\n", tag, (unsigned long)(cu.uv >> 32), (unsigned long)cu.uv, 0));
}
int main(void) {
    double x = 2.0;
    cu.dv = x;
    printf("x=%08x%08x\n", (unsigned long)(cu.uv >> 32), (unsigned long)cu.uv, 0), 0);
    cu.uv = 0x5FE6EB50C7B537A9ULL - (cu.uv >> 1);
    printf("seed=%08x%08x\n", (unsigned long)(cu.uv >> 32), (unsigned long)cu.uv, 0), 0);
    cu.dv = x * cu.dv;
    printf("xseed=%08x%08x\n", (unsigned long)(cu.uv >> 32), (unsigned long)cu.uv, 0), 0);
    show("sqrt2", hp_sqrt(2.0));
    show("loge", hp_log(2.718281828459045));
    show("pow210", hp_pow(2.0, 10.0));
    printf("SQDONE\n", 0, 0, 0, 0));
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
            r'C:\DATA\primetcc.hpappdir\hp_gfx.c',
            r'C:\DATA\primetcc.hpappdir\hp_input.c',
            r'C:\DATA\primetcc.hpappdir\hp_math.c',
            r'C:\DATA\primetcc.hpappdir\rt_svc.o',
            r'C:\DATA\primetcc.hpappdir\rt_aeabi.o']
    ret, out, emu = harness.run_elf(harness.TCC_ELF, argv, 'tcc', max_insn=2000000000)
    code_elf = os.path.join(HERE, 'fake_cdata', 'primetcc.hpappdir', 'code.elf')
    ret2, out2, emu2 = harness.run_elf(code_elf, [], 'user', max_insn=500000000)
    print(out2)
if __name__ == '__main__':
    main()
