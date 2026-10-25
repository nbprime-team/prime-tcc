#!/usr/bin/env python3
"""Trace the last N executed PCs before the crash at 0x30226176."""
import os
import sys

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOP, 'tests'))
os.chdir(os.path.join(TOP, 'tests'))

from emu_arm2 import ARMEmu  # noqa: E402
import harness  # noqa: E402

trace = []
MAX = 400
jumps = []
J = 120

_orig_exec = ARMEmu.exec

def exec_traced(self, insn, addr):
    trace.append((addr, insn, self.regs[14]))
    if len(trace) > MAX:
        trace.pop(0)
    # detect branches / returns / jumps
    cond = (insn >> 28) & 0xF
    op = insn & 0x0FFFFFFF
    is_jump = False
    if (op & 0x0FFFF000) == 0x012FFF10:      # bx / blx reg
        is_jump = True
    elif (op & 0x0FFFFFF0) == 0x012FFF30:    # blx reg (alternate encoding)
        is_jump = True
    elif (op & 0x0E000000) == 0x0A000000:    # b / bl
        is_jump = True
    elif (op & 0x0FFFF000) == 0x049FF000:    # ldr pc, [..]
        is_jump = True
    elif (insn & 0x0E108000) == 0x00808000:  # ldr pc with reg
        is_jump = True
    elif (op & 0x0FFFF000) == 0x08BD0000:    # pop {.., pc}
        is_jump = True
    if is_jump:
        jumps.append((addr, insn, self.regs[15], self.regs[14]))
        if len(jumps) > J:
            jumps.pop(0)
    return _orig_exec(self, insn, addr)

ARMEmu.exec = exec_traced

FAKE = os.path.join(TOP, 'tests', 'fake_cdata', 'primetcc.hpappdir')
TCC_ELF = os.path.join(TOP, 'tcc.elf')
with open(os.path.join(TOP, 'examples', 'gui.c')) as f:
    code = f.read()
with open(os.path.join(FAKE, 'code.c'), 'w') as f:
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
print('==> compiling gui.c ...')
ret, out, emu = harness.run_elf(TCC_ELF, argv, 'tcc', max_insn=2000000000)
code_elf = os.path.join(FAKE, 'code.elf')
inject = [('key', 0x01, True)]  # ESC only, minimal
print('==> running code.elf ...')
try:
    ret2, out2, emu2 = harness.run_user(code_elf, inject=inject, max_insn=500000000)
    print('exit =', ret2)
except Exception as e:
    print('CRASH:', e)
    print('---- last %d executed instructions ----' % len(trace))
    for pc, insn, lr in trace[-40:]:
        print('%08X: %08X  lr=%08X' % (pc, insn, lr))
    print('---- last %d jumps ----' % len(jumps))
    for pc, insn, target, lr in jumps[-30:]:
        print('%08X: %08X  -> target=%08X lr=%08X' % (pc, insn, target, lr))
