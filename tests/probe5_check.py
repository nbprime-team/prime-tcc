#!/usr/bin/env python3
# probe5_check.py -- emulator-side verification of the probe5 build.
# Mirrors what the calculator does: code.c exists in the appdir, main.py
# passes argv with the code.c path, the probe reads it back and logs sizes.
import os
import shutil
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
FAKE = os.path.join(HERE, 'fake_cdata', 'primetcc.hpappdir')

sys.path.insert(0, HERE)
import emu_arm2
from emu_arm2 import ARMEmu, BASE

emu_arm2.FAKE_ROOT = FAKE

# code.c with a known size (mimic the embedded hello/fib source)
CODE = '''#include "prime.h"

int fib(int n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }

int main(void) {
    printf("hello from TCC on HP Prime!\\n", 0, 0, 0, 0);
    printf("fib(15) = %d\\n", fib(15), 0, 0, 0);
    return fib(15) == 610 ? 0 : 1;
}
'''

def main():
    shutil.rmtree(os.path.join(HERE, 'fake_cdata'), ignore_errors=True)
    os.makedirs(FAKE, exist_ok=True)
    with open(os.path.join(FAKE, 'code.c'), 'w') as f:
        f.write(CODE)
    # reference files that exist on the calculator (copied via USB)
    for name in ('prime.h', 'hp_rt.c'):
        src = os.path.join(TOP, 'hp', 'prime.h') if name == 'prime.h' else os.path.join(TOP, 'rt', 'hp_rt.c')
        shutil.copy(src, os.path.join(FAKE, name))
    print('code.c size on disk:', len(CODE))

    elf = open(os.path.join(TOP, 'tcc.elf'), 'rb').read()
    emu = ARMEmu()
    entry = emu.load_elf(elf, BASE)
    log = emu.find_primerlog()
    if not log:
        print('PRIMELOG not found!')
        return 1
    print('entry 0x%08X log 0x%08X' % (entry, log))

    # argv identical to main.py's tcc_argv()
    argv = [
        'tcc', '-nostdlib', '-shared', '-Wl,-e,main',
        '-I', r'C:\DATA\primetcc.hpappdir',
        '-o', r'C:\DATA\primetcc.hpappdir\code.elf',
        r'C:\DATA\primetcc.hpappdir\code.c',
        r'C:\DATA\primetcc.hpappdir\hp_rt.c',
        r'C:\DATA\primetcc.hpappdir\rt_svc.o',
        r'C:\DATA\primetcc.hpappdir\rt_aeabi.o',
    ]
    addrs = []
    for s in argv:
        b = s.encode('latin1') + b'\x00'
        a = emu.fw.next_heap
        emu.mem[a - BASE:a - BASE + len(b)] = b
        emu.fw.next_heap = (a + len(b) + 3) & ~3
        addrs.append(a)
    arr = b''.join(struct.pack('<I', a) for a in addrs)
    arr_a = emu.fw.next_heap
    emu.mem[arr_a - BASE:arr_a - BASE + len(arr)] = arr
    emu.fw.next_heap = (arr_a + len(arr) + 3) & ~3
    cfg = struct.pack('<IIIII', 0xD00BC760, len(argv), arr_a, 0, 0)
    cfg_a = emu.fw.next_heap
    emu.mem[cfg_a - BASE:cfg_a - BASE + len(cfg)] = cfg
    emu.fw.next_heap = (cfg_a + len(cfg) + 3) & ~3

    t0 = time.time()
    ret = emu.run(entry, cfg_a)
    out = b''.join(emu.out).decode('latin1', 'replace')
    print('ran %.1fs, %d insn, return 0x%08X' % (time.time() - t0, emu.insn_count, ret))
    print('--- output ---')
    print(out)
    print('--- end ---')

    # check probe5.bin was written (control file)
    ctl = os.path.join(FAKE, 'probe5.bin')
    if os.path.exists(ctl):
        print('probe5.bin size on disk:', os.path.getsize(ctl))
    else:
        print('probe5.bin MISSING on disk')
    return 0 if ret == 0x5000 else 1

if __name__ == '__main__':
    sys.exit(main())
