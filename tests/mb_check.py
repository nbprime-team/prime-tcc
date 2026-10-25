#!/usr/bin/env python3
# mb_check.py -- verify the FULL Mandelbrot demo render (no interrupt):
# compiles the PRIME-C-CODE demo with TCC, runs it to the instruction cap
# (the demo's final wait-loop spins forever without keys), then checks the
# output for MB_DONE and probes a few framebuffer pixels:
#   (217,120) c=-0.1 +0i  -> inside the cardioid  -> black (in set)
#   (171,120) c=-0.5 +0i  -> inside the cardioid  -> black
#   ( 23,120) c=-1.8 +0i  -> outside (tail)       -> colored
# Run: python3 tests/mb_check.py   (takes ~2-3 min: TCC compile + render)
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import emu_arm2
from emu_arm2 import ARMEmu, BASE
import harness
from harness import TCC_ELF, USER_BASE

emu_arm2.FAKE_ROOT = harness.FAKE


def demo_source():
    src = open(os.path.join(TOP, 'calc', 'main.py')).read()
    b = '/* PRIME-C-CODE-BEGIN */'
    e = '/* PRIME-C-CODE-END */'
    return src[src.rfind(b) + len(b):src.rfind(e)]


def main():
    harness.make_fake_fs()
    with open(os.path.join(harness.FAKE, 'code.c'), 'w') as f:
        f.write(demo_source())
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
    code_elf = os.path.join(harness.FAKE, 'code.elf')

    emu2 = ARMEmu()
    tcc = open(TCC_ELF, 'rb').read()
    emu2.load_elf(tcc, BASE)                       # resident hook service
    state = emu2.find_magic(b'PRIMEIN')
    code = open(code_elf, 'rb').read()
    entry = emu2.load_elf(code, USER_BASE)
    log = emu2.find_magic(b'PRIMELOG', USER_BASE)
    emu2.log_addr = log
    emu2.drained = emu2.rd32(log + 8)
    emu2.max_insn = 150000000                      # render + start of wait loop
    try:
        ret = emu2.run(entry, state, base=USER_BASE)
        print('[mb] completed, return', hex(ret))
    except RuntimeError as e:
        print('[mb] instruction cap hit (expected: final wait-loop):', e)
    out2 = b''.join(emu2.out).decode('latin1', 'replace')
    print('[mb] --- output (tail) ---')
    print(out2[-1200:])
    assert 'MB_DONE' in out2, 'full render did not complete!'

    fb = emu2.fw.fb_addr
    def px(x, y):
        o = fb + (y * 320 + x) * 4
        return struct.unpack('<I', emu2.mem[o - BASE:o - BASE + 4])[0]
    BLACK = 0xFF000000
    c_center = px(217, 120)     # c=-0.1  +0i : inside cardioid -> black
    c_deep   = px(171, 120)     # c=-0.5  +0i : inside cardioid -> black
    c_tail   = px(286, 177)     # c= 0.5+0.5i: outside           -> colored
    print('[mb] px(217,120)=%08x px(171,120)=%08x px(286,177)=%08x'
          % (c_center, c_deep, c_tail))
    assert c_center == BLACK, 'cardioid center should be black'
    assert c_deep == BLACK, 'deep interior should be black'
    assert c_tail != BLACK, 'exterior point should be colored'
    print('[mb] MB FULL RENDER CHECK PASS')


if __name__ == '__main__':
    main()
