#!/usr/bin/env python3
"""Diagnose who writes the grob pointer (0x31004020) into ws[0].cur.

Patches ALL write paths (wr8/wr16u/wr32/wr) to log any store whose
address range touches 0x302520A8, and dumps .bss after the run.
"""
import os
import shutil
import struct
import sys

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOP, 'tests'))
os.chdir(os.path.join(TOP, 'tests'))

from emu_arm2 import ARMEmu as Emu, BASE, MASK  # noqa: E402

FAKE = os.path.join(TOP, 'tests', 'fake_cdata', 'primetcc.hpappdir')
TCC_ELF = os.path.join(TOP, 'tcc.elf')

WATCH = 0x302520A8  # ws[0].cur

orig_wr8 = Emu.wr8
orig_wr16u = Emu.wr16u
orig_wr32 = Emu.wr32
orig_wr = Emu.wr

def hooked_wr8(self, a, v):
    if a == WATCH or (a & ~0) in range(WATCH - 8, WATCH + 8):
        print('[wr8]   %08X <- %02X pc=%08X' % (a, v & 0xFF, self.regs[15] - 4))
    return orig_wr8(self, a, v)

def hooked_wr16u(self, a, v):
    if a == WATCH or a == WATCH - 2 or a == WATCH + 2:
        print('[wr16]  %08X <- %04X pc=%08X' % (a, v & 0xFFFF, self.regs[15] - 4))
    return orig_wr16u(self, a, v)

def hooked_wr32(self, a, v):
    if (a & ~3) == WATCH or (a & ~3) in range(WATCH - 12, WATCH + 12):
        print('[wr32]  %08X <- %08X pc=%08X insn=%08X' % (a, v & MASK, self.regs[15] - 4, getattr(self, 'last_insn', 0)))
    return orig_wr32(self, a, v)

Emu.wr8 = hooked_wr8
Emu.wr16u = hooked_wr16u
Emu.wr32 = hooked_wr32

# The run_elf / run_user helpers live in harness.py -- replicate minimal flow.
import harness  # noqa: E402

# Build the gui test the same way harness does
test = 'gui'
with open(os.path.join(TOP, 'examples', 'gui.c')) as f:
    code = f.read()
with open(os.path.join(FAKE, 'code.c'), 'w') as f:
    f.write(code)

argv = [
    'tcc',
    '-nostdlib', '-shared', '-Wl,-e,hp_entry',
    '-I', r'C:\DATA\primetcc.hpappdir',
    '-o', r'C:\DATA\primetcc.hpappdir\code.elf',
    r'C:\DATA\primetcc.hpappdir\code.c',
    r'C:\DATA\primetcc.hpappdir\rt_core.o',
    r'C:\DATA\primetcc.hpappdir\rt_svc.o',
    r'C:\DATA\primetcc.hpappdir\rt_aeabi.o',
    r'C:\DATA\primetcc.hpappdir\rt_math.o',
]
print('==> compiling gui.c with TCC-on-ARM ...')
ret, out, emu = harness.run_elf(TCC_ELF, argv, 'tcc', max_insn=2000000000)
code_elf = os.path.join(FAKE, 'code.elf')
print('==> running code.elf ...')
inject = [('key', 0x5A, True), ('key', 0xB9, True),
          ('key', 0x33, True), ('key', 0x58, True),
          ('key', 0x5A, True), ('key', 0x0D, True),
          ('key', 0x4C, True), ('key', 0x53, True),
          ('key', 0x4D, True), ('key', 0x0D, True),
          ('key', 0x01, True)]
ret2, out2, emu2 = harness.run_user(code_elf, inject=inject, max_insn=500000000)
print('RESULT: user program exit code =', ret2)
print('---- output ----')
print(out2)
print('----------------')

if emu2 is not None:
    mem = emu2.mem
    for a in range(WATCH - 0x40, WATCH + 0x40, 4):
        v = struct.unpack_from('<I', mem, a - BASE)[0]
        print('mem[%08X] = %08X' % (a, v))
    # search the whole .bss-ish region for the grob pointer value
    grob = 0x31004020
    print('---- locations holding %08X ----' % grob)
    hits = 0
    for a in range(0x30249000, 0x30253000, 4):
        v = struct.unpack_from('<I', mem, a - BASE)[0]
        if v == grob:
            print('  %08X' % a)
            hits += 1
    print('(%d hits)' % hits)
