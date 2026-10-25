#!/usr/bin/env python3
"""Trace calls into __aeabi_memmove/memcpy to find who writes ws[0].cur."""
import os
import struct
import sys

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOP, 'tests'))
os.chdir(os.path.join(TOP, 'tests'))

from emu_arm2 import ARMEmu, BASE, MASK  # noqa: E402
import harness  # noqa: E402

MEMMOVE = 0x3022C824
MEMCPY = 0x3022C774
WATCH = 0x302520A8

_orig_exec = ARMEmu.exec

def exec_traced(self, insn, addr):
    pc = addr
    if pc == MEMMOVE or pc == MEMCPY:
        r0 = self.regs[0]
        r1 = self.regs[1]
        r2 = self.regs[2]
        lr = self.regs[14]
        print('>>> %s dst=%08X src=%08X len=%d callerLR=%08X (src first word=%08X)'
              % ('memmove' if pc == MEMMOVE else 'memcpy ', r0, r1, r2, lr,
                 self.rd32(r1) if r1 else 0))
    return _orig_exec(self, insn, addr)

ARMEmu.exec = exec_traced

# build + run the gui case
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
inject = [('key', 0x5A, True), ('key', 0xB9, True),
          ('key', 0x33, True), ('key', 0x58, True),
          ('key', 0x5A, True), ('key', 0x0D, True),
          ('key', 0x4C, True), ('key', 0x53, True),
          ('key', 0x4D, True), ('key', 0x0D, True),
          ('key', 0x01, True)]
print('==> running code.elf ...')
ret2, out2, emu2 = harness.run_user(code_elf, inject=inject, max_insn=500000000)
print('exit =', ret2)
