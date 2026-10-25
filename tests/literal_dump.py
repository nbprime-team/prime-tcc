#!/usr/bin/env python3
"""Dump the stack literal area + 0x31004020 to confirm the garbage source."""
import os
import struct
import sys

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOP, 'tests'))
os.chdir(os.path.join(TOP, 'tests'))

from emu_arm2 import ARMEmu, BASE, MASK  # noqa: E402
import harness  # noqa: E402

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
ret2, out2, emu2 = harness.run_user(code_elf, inject=inject, max_insn=500000000)

if emu2 is not None:
    mem = emu2.mem
    print('---- literal area on stack (0x31003E80..0x31004000) ----')
    for a in range(0x31003E80, 0x31004000, 4):
        v = struct.unpack_from('<I', mem, a - BASE)[0]
        if v:
            print('%08X: %08X' % (a, v))
    print('---- what is at 0x31004020 and around ----')
    for a in range(0x31004000, 0x31004100, 4):
        v = struct.unpack_from('<I', mem, a - BASE)[0]
        print('%08X: %08X' % (a, v))
    print('---- search for the UTF-16 path string ----')
    needle = b'C\x00:\x00\\\x00D\x00A\x00T\x00A\x00'
    idx = mem.find(needle)
    print('path UTF-16 at mem offset', hex(idx) if idx >= 0 else 'NOT FOUND')
    if idx >= 0:
        for a in range(BASE + idx - 16, BASE + idx + 64, 4):
            v = struct.unpack_from('<I', mem, a - BASE)[0]
            print('%08X: %08X' % (a, v))
