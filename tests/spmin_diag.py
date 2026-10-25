#!/usr/bin/env python3
"""Track the minimum SP reached during the gui run (stack-overflow check)."""
import os
import sys

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOP, 'tests'))
os.chdir(os.path.join(TOP, 'tests'))

from emu_arm2 import ARMEmu  # noqa: E402
import harness  # noqa: E402

sp_min = [0xFFFFFFFF]
sp_min_pc = [0]

_orig_exec = ARMEmu.exec

def exec_traced(self, insn, addr):
    sp = self.regs[13]
    if sp < sp_min[0]:
        sp_min[0] = sp
        sp_min_pc[0] = addr
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
inject = [('key', 0x5A, True), ('key', 0xB9, True),
          ('key', 0x33, True), ('key', 0x58, True),
          ('key', 0x5A, True), ('key', 0x0D, True),
          ('key', 0x4C, True), ('key', 0x53, True),
          ('key', 0x4D, True), ('key', 0x0D, True),
          ('key', 0x01, True)]
print('==> running code.elf ...')
ret2, out2, emu2 = harness.run_user(code_elf, inject=inject, max_insn=500000000)
print('exit =', ret2)
print('min sp = %08X at pc=%08X' % (sp_min[0], sp_min_pc[0]))
print('stack top = 31004020, 16KB bottom = %08X' % (0x31004020 - 16384))
print('headroom = %d bytes' % (sp_min[0] - (0x31004020 - 16384)))
