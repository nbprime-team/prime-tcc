#!/usr/bin/env python3
"""Host-side unit tests for calc/main.py's resident-TCC slot logic and the
RT_RET exit-code parser.

Runs WITHOUT a calculator: fake uio/ustruct/hpprime modules are injected
before importing main.py, PRIMETCC_NO_AUTORUN=1 stops the import-time
main() call, and all file traffic goes through an in-memory fake FS.

    python3 tests/test_main_slot.py
"""
import importlib.util
import os
import struct
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_PY = os.path.join(os.path.dirname(HERE), 'calc', 'main.py')


# ---- fake modules -------------------------------------------------------
class FakeFS:
    def __init__(self):
        self.files = {}

    def FileIO(self, name, mode='r'):
        return FakeFileIO(self, name, mode)

    def remove(self, name):
        if name in self.files:
            del self.files[name]
        else:
            raise OSError('no such file: ' + name)


class FakeFileIO:
    def __init__(self, fs, name, mode='r'):
        self.fs = fs
        self.name = name
        self.mode = mode
        if 'w' in mode or '+' in mode:
            self.data = bytearray(fs.files.get(name, b''))
        else:
            if name not in fs.files:
                raise OSError(2, 'No such file', name)
            self.data = bytearray(fs.files[name])
        self.pos = 0

    def read(self, n=-1):
        if n < 0:
            n = len(self.data) - self.pos
        b = bytes(self.data[self.pos:self.pos + n])
        self.pos += len(b)
        return b

    def write(self, b):
        self.data[self.pos:self.pos + len(b)] = b
        self.pos += len(b)

    def seek(self, off, whence=0):
        if whence == 0:
            self.pos = off
        elif whence == 1:
            self.pos += off
        elif whence == 2:
            self.pos = len(self.data) + off
        return self.pos

    def tell(self):
        return self.pos

    def close(self):
        if 'w' in self.mode or '+' in self.mode:
            self.fs.files[self.name] = bytes(self.data)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeDbg:
    """debug interface stub: read_mem returns what we planted."""
    def __init__(self):
        self.mem = {}

    def read_mem(self, addr, size):
        b = self.mem.get(addr, b'\x00' * size)
        return b[:size]


def install_fakes():
    uio = types.ModuleType('uio')
    uio.FileIO = FakeFS().FileIO            # fresh FS per import is fine here
    uio.remove = FakeFS().remove
    sys.modules['uio'] = uio

    ustruct = types.ModuleType('ustruct')
    for n in ('pack', 'pack_into', 'unpack', 'unpack_from', 'calcsize'):
        setattr(ustruct, n, getattr(struct, n))
    sys.modules['ustruct'] = ustruct

    hpprime = types.ModuleType('hpprime')
    hpprime.ticks = lambda: 0
    sys.modules['hpprime'] = hpprime


def load_main():
    spec = importlib.util.spec_from_file_location('calc_main', MAIN_PY)
    m = importlib.util.module_from_spec(spec)
    sys.modules['calc_main'] = m
    spec.loader.exec_module(m)
    return m


# ---- tests --------------------------------------------------------------
PASS = 0


def check(name, ok, detail=''):
    global PASS
    print('%s %-46s %s' % ('OK ' if ok else 'FAIL', name, detail))
    if not ok:
        PASS = 1


def test_rt_ret_parser(m):
    check('parse RT_RET:7', m._parse_rt_ret('x\nRT_RET:7\n') == 7)
    check('parse last RT_RET wins',
          m._parse_rt_ret('RT_RET:1\nRT_RET:2\n') == 2)
    check('parse no marker', m._parse_rt_ret('nothing here') is None)
    check('parse empty digits', m._parse_rt_ret('RT_RET:\n') is None)
    check('parse junk digits', m._parse_rt_ret('RT_RET:abc') is None)
    check('parse embedded', m._parse_rt_ret('aRT_RET:42b') == 42)


def test_slot(m):
    fs = FakeFS()
    m.uio = sys.modules['uio']  # not used; keep import surface stable
    # point main's uio at our fake FS: main.py uses module-global uio
    # -> patch the module attribute with a bound fake FS
    m.uio.FileIO = fs.FileIO
    m.uio.remove = fs.remove

    dbg = FakeDbg()
    LA = 0x31001000
    BASE = 0x31010000
    SIZE = 866008            # must match fs.files['tcc.elf'] length
    ENTRY = 0x3101B4C0
    LOG = 0x3101C000
    dbg.mem[LA] = b'\x0b\x00\x00\xea' + b'\x00' * 12
    dbg.mem[BASE] = b'\x7fELF' + b'\x00' * 12
    fs.files['tcc.elf'] = b'\x00' * SIZE

    # 1. no slot -> load fresh
    loader = m.ShellcodeElfLoader(dbg)
    check('slot: missing file -> None', m._slot_load(dbg, loader) is None)

    # 2. valid slot -> reuse
    fs.files[m.TCC_SLOT] = struct.pack('<IIIII', LA, BASE, SIZE, ENTRY, LOG)
    got = m._slot_load(dbg, loader)
    check('slot: valid slot reused', got == (ENTRY, LOG))
    check('slot: loader attrs set',
          loader.loader_addr == LA and loader.loaded_elf_base == BASE
          and loader.loaded_elf_size == SIZE)

    # 3. stale ELF magic (reboot) -> None
    dbg.mem[BASE] = b'\x00' * 16
    loader2 = m.ShellcodeElfLoader(dbg)
    check('slot: stale ELF magic -> None', m._slot_load(dbg, loader2) is None)

    # 4. stale loader magic -> None
    dbg.mem[BASE] = b'\x7fELF' + b'\x00' * 12
    dbg.mem[LA] = b'\xde\xad\xbe\xef' + b'\x00' * 12
    loader3 = m.ShellcodeElfLoader(dbg)
    check('slot: stale loader magic -> None', m._slot_load(dbg, loader3) is None)

    # 5. garbage / short slot -> None
    fs.files[m.TCC_SLOT] = b'\x00' * 8
    loader4 = m.ShellcodeElfLoader(dbg)
    check('slot: short slot -> None', m._slot_load(dbg, loader4) is None)

    # 6. low addresses rejected
    fs.files[m.TCC_SLOT] = struct.pack('<IIIII', 1, 2, 3, 4, 5)
    loader5 = m.ShellcodeElfLoader(dbg)
    check('slot: low addresses -> None', m._slot_load(dbg, loader5) is None)

    # 7. size mismatch (tcc.elf redeployed) -> None
    fs.files[m.TCC_SLOT] = struct.pack('<IIIII', LA, BASE, SIZE + 4096, ENTRY, LOG)
    dbg.mem[LA] = b'\x0b\x00\x00\xea' + b'\x00' * 12
    dbg.mem[BASE] = b'\x7fELF' + b'\x00' * 12
    loader7 = m.ShellcodeElfLoader(dbg)
    check('slot: size mismatch -> None', m._slot_load(dbg, loader7) is None)

    # 8. _slot_save writes 20 bytes
    fs.files[m.TCC_SLOT] = struct.pack('<IIIII', LA, BASE, SIZE, ENTRY, LOG)
    loader6 = m.ShellcodeElfLoader(dbg)
    loader6.loader_addr = LA
    loader6.loaded_elf_base = BASE
    loader6.loaded_elf_size = SIZE
    loader6.entry_point = ENTRY
    m._slot_save(loader6, LOG)
    check('slot: save writes 20 bytes',
          fs.files.get(m.TCC_SLOT) == struct.pack('<IIIII', LA, BASE, SIZE, ENTRY, LOG))

    # 9. reset_tcc drops the slot
    m.reset_tcc()
    check('slot: reset_tcc removes file', m.TCC_SLOT not in fs.files)
    m.reset_tcc()   # second call: no file -> graceful


def test_clear_trace(m):
    fs = FakeFS()
    m.uio.FileIO = fs.FileIO
    m.uio.remove = fs.remove
    for name in ('stage.txt', 'tcc.log', 'crash.log'):
        fs.files[name] = b'stale content from a previous run'
    m._clear_trace_files()
    check('clear: removes stale stage.txt/tcc.log/crash.log',
          all(n not in fs.files for n in ('stage.txt', 'tcc.log', 'crash.log')))
    m._clear_trace_files()          # nothing left -> must be graceful
    check('clear: second call graceful', True)


def test_stale_logs_gate(m):
    fs = FakeFS()
    m.uio.FileIO = fs.FileIO
    m.uio.remove = fs.remove

    # no logs -> proceed
    check('gate: no logs -> proceed', m._handle_stale_logs() is True)

    # logs present, user answers y -> deleted, proceed
    for name in ('stage.txt', 'tcc.log', 'crash.log'):
        fs.files[name] = b'crash trace'
    m.input = lambda p: 'y'
    check('gate: logs + y -> proceed', m._handle_stale_logs() is True)
    check('gate: logs + y -> deleted',
          all(n not in fs.files for n in ('stage.txt', 'tcc.log', 'crash.log')))

    # logs present, user answers n -> kept, abort
    for name in ('stage.txt', 'tcc.log', 'crash.log'):
        fs.files[name] = b'crash trace'
    m.input = lambda p: 'n'
    check('gate: logs + n -> abort', m._handle_stale_logs() is False)
    check('gate: logs + n -> kept',
          all(n in fs.files for n in ('stage.txt', 'tcc.log', 'crash.log')))

    # logs present, input() raises (no interactive console) -> abort, kept
    m.input = lambda p: (_ for _ in ()).throw(OSError('no input'))
    check('gate: logs + input-fail -> abort', m._handle_stale_logs() is False)
    check('gate: logs + input-fail -> kept', 'tcc.log' in fs.files)

    # empty log files -> treated as no logs
    for name in ('stage.txt', 'tcc.log', 'crash.log'):
        fs.files[name] = b''
    check('gate: empty logs -> proceed', m._handle_stale_logs() is True)

    # _trace_logs_exist: detects content
    fs.files['tcc.log'] = b'boom'
    check('gate: detect tcc.log content', m._trace_logs_exist() is True)
    del fs.files['tcc.log']
    check('gate: detect none', m._trace_logs_exist() is False)


def main():
    install_fakes()
    m = load_main()
    print('imported calc/main.py (autorun skipped: PRIMETCC_NO_AUTORUN)')
    test_rt_ret_parser(m)
    test_slot(m)
    test_clear_trace(m)
    test_stale_logs_gate(m)
    print('PASS' if PASS == 0 else 'FAIL')
    sys.exit(PASS)


if __name__ == '__main__':
    main()
