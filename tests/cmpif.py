#!/usr/bin/env python3
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import harness
CODE = r'''
#include "prime.h"
static void t(const char *lab, int c) {
    prints(lab); prints(c ? "T" : "F"); prints("\n");
}
int main(void) {
    double a = 2.0, b = 0.0, c = 1.0;
    t("LT_", a <  b);   /* F */
    t("LE_", a <= b);   /* F */
    t("GT_", a >  b);   /* T */
    t("GE_", a >= b);   /* T */
    t("EQ_", a == b);   /* F */
    t("NE_", a != b);   /* T */
    t("LT2", c <  a);   /* T */
    t("GE2", c >= a);   /* F */
    if (a <= b) prints("IF_LE_TRUE\n"); else prints("IF_LE_FALSE\n");
    if (a > b) prints("IF_GT_TRUE\n"); else prints("IF_GT_FALSE\n");
    printf("CIFDONE\n", 0, 0, 0, 0);
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
