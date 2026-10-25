#!/usr/bin/env python3
# restart_check.py -- verify the RESIDENT input hook keeps keys flowing
# across repeated runs in ONE emulator.
#
# The real-device bug this guards: after a run exits, the NEXT run must
# still receive keys -- and a hung/leaked run must never leave the OS
# input path pointing at freed code.elf (the old design freed code.elf
# with a hook call still in flight; the OS thread woke in reused memory
# and input died permanently).  The hook now lives RESIDENT in tcc.elf,
# so code.elf is always safe to free and the slot is always re-armable.
#
# Models the calculator exactly: tcc.elf (hosting the PRIMEIN hook
# service) is loaded first, code.elf runs with r0 = the PRIMEIN state
# address (hp_entry forwards it to hp_input.c), then code.elf is
# reloaded at the same base for run 2 -- the state survives in tcc.elf.
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
FAKE = os.path.join(HERE, 'fake_cdata', 'primetcc.hpappdir')

sys.path.insert(0, HERE)
import emu_arm2
from emu_arm2 import ARMEmu, BASE

emu_arm2.FAKE_ROOT = FAKE

import harness
from harness import TCC_ELF, USER_BASE


DEMO = r'''
#include "prime.h"
#include "hp_input.h"

/* key-echo panel for the restart check: ENTER re-runs, q exits.
 * (main.py's embedded example is now a bare stub by user request, so
 * this check carries its own program instead of parsing main.py.) */
static void panel(void) {
    printf("SYS_DONE\\n", 0, 0, 0, 0);
}

int main(void) {
    hp_event ev;
    if (!hp_input_install()) { printf("INSTALL FAIL\\n", 0, 0, 0, 0); return 1; }
    panel();
    for (;;) {
        int t = hp_poll_event(&ev);
        if (t == HP_EV_KEY && hp_event_key_down(&ev)) {
            int k = hp_event_key(&ev);
            printf("KEY %02x\\n", (unsigned long)k, 0, 0, 0);
            if (k == 0x0D)
                panel();
            if (k == 0x51)
                break;
        }
        __sleep(10);
    }
    hp_input_remove();
    printf("SYS_EXIT\\n", 0, 0, 0, 0);
    printf("RT_EXIT ok\\n", 0, 0, 0, 0);
    return 0;
}
'''


def demo_source():
    return DEMO


def make_fake_fs():
    shutil.rmtree(os.path.join(HERE, 'fake_cdata'), ignore_errors=True)
    os.makedirs(FAKE, exist_ok=True)
    with open(os.path.join(FAKE, 'code.c'), 'w') as f:
        f.write(demo_source())
    for name in ('hp_gfx.h', 'hp_input.h', 'hp_math.h', 'hp_string.h',
                 'hp_fonts.h', 'hp_sys.h'):
        shutil.copy(os.path.join(TOP, 'rt', name), os.path.join(FAKE, name))
    for name in ('rt_core.o', 'rt_math.o', 'rt_svc.o', 'rt_aeabi.o'):
        shutil.copy(os.path.join(TOP, name), os.path.join(FAKE, name))
    shutil.copy(os.path.join(TOP, 'hp', 'prime.h'), os.path.join(FAKE, 'prime.h'))


def compile_with_tcc():
    """compile code.c -> code.elf with the exact deployed command line."""
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
    ret, out, emu = harness.run_elf(TCC_ELF, argv, 'tcc', max_insn=2000000000)
    return os.path.join(FAKE, 'code.elf')


def run_once(emu, elf_bytes, keys, state):
    """load code.elf into the existing emulator (state already resident in
    tcc.elf), inject keys, run, return output."""
    entry = emu.load_elf(elf_bytes, USER_BASE)
    log = emu.find_magic(b'PRIMELOG', USER_BASE)
    emu.log_addr = log
    emu.drained = emu.rd32(log + 8)
    emu.fw.ev_queue = []          # fresh queue for this run
    for scan, down in keys:
        emu.fw.inject_key(scan, down)
    emu.out = []
    ret = emu.run(entry, state, base=USER_BASE)
    out = b''.join(emu.out).decode('latin1', 'replace')
    return ret, out


def main():
    make_fake_fs()
    code_elf = compile_with_tcc()
    elf = open(code_elf, 'rb').read()
    print('code.elf:', len(elf), 'bytes')

    emu = ARMEmu()
    tcc = open(TCC_ELF, 'rb').read()
    emu.load_elf(tcc, BASE)                       # resident hook service
    state = emu.find_magic(b'PRIMEIN')
    assert state is not None, 'PRIMEIN state not found in tcc.elf!'
    print('PRIMEIN input state at 0x%08X' % state)

    # run 1: ENTER (re-runs the panel), then q(0x51) exits the loop
    ret1, out1 = run_once(emu, elf, [(0x0D, True), (0x51, True), (0x51, True)], state)
    print('--- run 1 ---')
    print(out1)
    assert 'SYS_DONE' in out1, 'run 1: sys panel did not run!'
    assert 'KEY 0d' in out1, 'run 1: ENTER key not delivered!'
    assert 'KEY 51' in out1, 'run 1: q key not delivered!'
    assert 'SYS_EXIT' in out1, 'run 1: q did not exit the loop!'
    assert 'RT_EXIT ok' in out1, 'run 1 teardown not clean!'
    print('run 1 OK: keys delivered, panel re-ran, exited, slot restored')

    # run 2: UP (ignored), q exits -- keys must still arrive
    ret2, out2 = run_once(emu, elf, [(0x03, True), (0x51, True), (0x51, True)], state)
    print('--- run 2 ---')
    print(out2)
    assert 'KEY 03' in out2, 'RUN 2: UP key NOT delivered (bug reproduced!)'
    assert 'KEY 51' in out2 and 'SYS_EXIT' in out2, 'run 2 exit failed'
    assert 'RT_EXIT ok' in out2, 'run 2 teardown not clean!'
    print('run 2 OK: keys delivered again (resident hook survives)')
    print('RESTART TEST PASS')


if __name__ == '__main__':
    main()
