#!/usr/bin/env python3
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import harness

CODE = r'''
#include "prime.h"
int main(void) {
    /* direct d2iz tests */
    printf("t1=%d\n", (int)7.94, 0, 0, 0);
    printf("t2=%d\n", (int)0.4794, 0, 0, 0);
    printf("t3=%d\n", (int)8.5, 0, 0, 0);
    /* loop-scope int decl with double init */
    { double f = 0.4794255; int i;
      for (i = 0; i < 3; i++) {
          f *= 10.0;
          int digit = (int)f;
          printf("d%d=%d\n", i, digit, 0, 0);
          f -= (double)digit;
      }
    }
    printf("FDONE\n", 0, 0, 0, 0);
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
