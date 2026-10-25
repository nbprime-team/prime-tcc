#!/usr/bin/env python3
"""measure_tcc_size.py -- measure how much memory the on-calculator TCC
uses to compile a C program, and extrapolate the max source size for a
given free-heap budget.

Generates synthetic C programs of increasing size, compiles each with the
ARM TCC on the emulator (same argv as the calculator), and records:
  src_bytes   -- user source size
  heap_peak   -- TCC's peak firmware-heap usage during the compile
                 (the emulator tracks the highest next_heap ever reached)
  elf_bytes   -- code.elf size (runtime + user code)
Run: python3 tests/measure_tcc_size.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import emu_arm2
from emu_arm2 import ARMEmu, BASE
import harness

emu_arm2.FAKE_ROOT = harness.FAKE
from harness import TCC_ELF, USER_BASE


def gen_source(nfuncs):
    """nfuncs functions, each ~1KB of arithmetic code -> ~nfuncs KB source."""
    parts = ['#include "prime.h"', 'static int f0(int x) { return x * 3 + 1; }']
    for i in range(1, nfuncs):
        prev = 'f%d' % (i - 1)
        parts.append(
            'static int f%d(int x) { int a = %d; int b = x + a;\n'
            '    b = b * 7 + (a >> 2) - (b >> 3) + (x << 1);\n'
            '    b = (b ^ a) + (b >> 1) - (x * 5) + (a << 2) + %d;\n'
            '    return %s(b) + %s(b >> 1); }\n'
            % (i, i * 7919 % 1000, i * 131 % 997, prev, prev))
    parts.append('int main(void) { return f%d(42); }\n' % (nfuncs - 1))
    return '\n'.join(parts)


def measure(nfuncs):
    harness.make_fake_fs()
    code = gen_source(nfuncs)
    src = os.path.join(harness.FAKE, 'code.c')
    with open(src, 'w') as f:
        f.write(code)
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
    ret, out, emu = harness.run_elf(TCC_ELF, argv, 'tcc', max_insn=4000000000)
    if not os.path.exists(os.path.join(harness.FAKE, 'code.elf')):
        print('  compile FAILED')
        return None
    elf = os.path.getsize(os.path.join(harness.FAKE, 'code.elf'))
    peak = emu.fw.heap_peak - 0x31000000
    return len(code), peak, elf, emu.insn_count


def main():
    print('%-8s %12s %12s %10s %14s' %
          ('src KB', 'src bytes', 'heap peak', 'elf KB', 'insns'))
    results = []
    for nfuncs in (2, 10, 40, 100, 200, 400):
        r = measure(nfuncs)
        if r is None:
            continue
        src, peak, elf, insn = r
        results.append(r)
        print('%-8d %12d %12d %10d %14d' %
              (src // 1024, src, peak, elf // 1024, insn))
    # linear fit (no numpy): peak = fixed + a*src + b*elf
    n = len(results)
    sx = sum(r[0] for r in results)
    se = sum(r[2] for r in results)
    sy = sum(r[1] for r in results)
    sxx = sum(r[0] * r[0] for r in results)
    see = sum(r[2] * r[2] for r in results)
    sxe = sum(r[0] * r[2] for r in results)
    sxy = sum(r[0] * r[1] for r in results)
    sey = sum(r[2] * r[1] for r in results)
    det = n * (sxx * see - sxe * sxe) - sx * (sx * see - sxe * se) + \
          se * (sx * sxe - sxx * se)
    # solve the normal equations via Cramer's rule
    m = [[n, sx, se], [sx, sxx, sxe], [se, sxe, see]]
    rhs = [sy, sxy, sey]

    def det3(mm):
        return (mm[0][0] * (mm[1][1] * mm[2][2] - mm[1][2] * mm[2][1])
                - mm[0][1] * (mm[1][0] * mm[2][2] - mm[1][2] * mm[2][0])
                + mm[0][2] * (mm[1][0] * mm[2][1] - mm[1][1] * mm[2][0]))
    d0 = det3(m)
    m1 = [rhs, m[1], m[2]]
    m2 = [m[0], rhs, m[2]]
    m3 = [m[0], m[1], rhs]
    fixed = det3(m1) / d0
    a = det3(m2) / d0
    b = det3(m3) / d0
    print('\nfit: peak = %.0f + %.4f*src + %.4f*elf' % (fixed, a, b))
    print('per 1KB of source  -> +%.1f KB heap' % (a * 1024))
    print('per 1KB of output  -> +%.1f KB heap' % (b * 1024))
    # extrapolate for heap budgets (device free heap = hp_sys_max_alloc)
    for heap_mb in (2, 4, 6, 8, 10):
        budget = heap_mb * 1024 * 1024 - fixed
        best = 0
        for src_kb in range(100, 6000, 50):
            elf_est = 245 * 1024 + src_kb * 1024
            need = fixed + a * src_kb * 1024 + b * elf_est
            if need <= budget:
                best = src_kb
        print('heap %dMB: max user source ~= %d KB (code.elf ~%d KB)'
              % (heap_mb, best, 245 + best))


if __name__ == '__main__':
    main()
