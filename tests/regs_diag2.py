#!/usr/bin/env python3
"""Check whether TCC-compiled main() clobbers hp_entry's callee-saved
r4-r7 (which hold the debug-SP save pair, input state, stack top, and
main's return value).  If r7 is clobbered, hp_entry's teardown
'mov sp, r7; pop {ip,lr}; bx lr' jumps to garbage -> reboot on device.
Runs the exact gui scenario (calc then ESC) and inspects regs at the
teardown 'mov sp, r7' (0x3022CC4C) vs the entry save (0x3022CC14)."""
import os
import sys

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOP, 'tests'))
os.chdir(os.path.join(TOP, 'tests'))

from emu_arm2 import ARMEmu  # noqa: E402
import harness  # noqa: E402

SAVE_PC = 0x3022CC14   # push {ip,lr} done, r7 = A-8
TEAR_PC = 0x3022CC4C   # mov sp, r7 (before pop)
MAIN_RET_PC = 0x3022CC38  # after bl main, r5 = main() ret

state = {'saved_r7': None}

_orig_exec = ARMEmu.exec

def exec_traced(self, insn, addr):
    if addr == SAVE_PC:
        state['saved_r7'] = self.regs[7]
        state['saved_r4'] = self.regs[4]
        state['saved_r6'] = self.regs[6]
    elif addr == MAIN_RET_PC:
        state['main_ret'] = self.regs[0]
        state['r4_after_main'] = self.regs[4]
        state['r5_after_main'] = self.regs[5]
        state['r6_after_main'] = self.regs[6]
        state['r7_after_main'] = self.regs[7]
    elif addr == TEAR_PC:
        print('>>> teardown: r7=%08X (saved A-8=%08X) match=%s'
              % (self.regs[7], state.get('saved_r7'),
                 self.regs[7] == state.get('saved_r7')))
        print('>>>            r5=%08X (main ret=%s) r4=%08X (saved=%s) r6=%08X (saved=%s)'
              % (self.regs[5], state.get('main_ret'), self.regs[4],
                 state.get('saved_r4'), self.regs[6], state.get('saved_r6')))
        if state.get('r7_after_main') is not None:
            print('>>> right after main: r7=%08X r4=%08X r6=%08X'
                  % (state['r7_after_main'], state['r4_after_main'],
                     state['r6_after_main']))
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
inject = [('key', 0x01, True)]  # ESC only, no calc
print('==> running code.elf ...')
ret2, out2, emu2 = harness.run_user(code_elf, inject=inject, max_insn=500000000)
print('exit =', ret2)
print('RT_RET ok in out:', 'RT_RET:0' in out2)
print('GUI_DONE ok in out:', 'GUI_DONE' in out2)
