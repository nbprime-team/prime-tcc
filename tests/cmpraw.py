#!/usr/bin/env python3
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import harness
CODE = r'''
#include "prime.h"
int __aeabi_dcmpgt(double, double);
int __aeabi_dcmplt(double, double);
int __aeabi_dcmple(double, double);
int __aeabi_dcmpge(double, double);
int __aeabi_dcmpeq(double, double);
int main(void) {
    printf("gt=%d\n", __aeabi_dcmpgt(2.0, 0.0), 0, 0, 0);   /* 1 */
    printf("lt=%d\n", __aeabi_dcmplt(2.0, 0.0), 0, 0, 0);   /* 0 */
    printf("le=%d\n", __aeabi_dcmple(2.0, 0.0), 0, 0, 0);   /* 0 */
    printf("ge=%d\n", __aeabi_dcmpge(2.0, 0.0), 0, 0, 0);   /* 1 */
    printf("eq=%d\n", __aeabi_dcmpeq(2.0, 0.0), 0, 0, 0);   /* 0 */
    printf("CRAW\n", 0, 0, 0, 0);
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
