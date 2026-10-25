# emu_arm2.py -- ARMv5 (ARM state) interpreter for running the HP Prime
# port of TCC on the host.
#
# Extends the PrimeC emulator with the instructions that gcc/TCC code need:
#   LDRH/STRH/LDRSB/LDRSH, BX/BLX (reg), UMULL/SMULL/UMLAL/SMLAL, CLZ,
#   plus an SVC backend that emulates the HP Prime G1 firmware syscalls
#   against a host-side fake "C:\\DATA\\..." filesystem.
#
# The SVC convention matches the firmware: the handler pops the pushed LR
# (both words), result in r0.
import struct
import os

MASK = 0xFFFFFFFF
BASE = 0x30000000
MEM_SIZE = 32 * 1024 * 1024

# host dir that plays the role of C:\DATA\primetcc.hpappdir on the calculator
FAKE_ROOT = None

def ror(x, n):
    x &= MASK
    if n == 0:
        return x
    n &= 31
    return ((x >> n) | (x << (32 - n))) & MASK

def shifter_op(opnd, shift_type, shift, carry_in, regshift=False):
    v = opnd & MASK
    c = carry_in
    # NOTE regshift: for REGISTER-controlled shifts a shift amount of 0 is
    # a genuine no-op (C compilers rely on "x >> i" with i == 0 leaving x
    # unchanged).  The "0 means 32" quirk applies ONLY to the immediate
    # form, where a 5-bit field cannot encode 32.  Treating register-0 as
    # >>32 silently corrupted every variable-shift loop whose first
    # iteration shifts by 0 -- e.g. hp_fixmath's CORDIC gave pi/2 instead
    # of pi/4 for atan2(1,1) (see the 'fix'/'cordic' harness cases).
    if shift_type == 0:      # LSL
        if shift == 0:
            return v, c
        if shift >= 32:
            c = (v & 1) if shift == 32 else 0
            return 0, c
        c = (v >> (32 - shift)) & 1
        return (v << shift) & MASK, c
    elif shift_type == 1:    # LSR
        if regshift and shift == 0:
            return v, c
        if shift == 0:
            shift = 32
        if shift >= 32:
            c = (v >> 31) & 1 if shift == 32 else 0
            return 0, c
        c = (v >> (shift - 1)) & 1
        return (v >> shift) & MASK, c
    elif shift_type == 2:    # ASR
        if regshift and shift == 0:
            return v, c
        if shift == 0:
            shift = 32
        if shift >= 32:
            c = (v >> 31) & 1
            return (MASK if (v >> 31) & 1 else 0), c
        c = (v >> (shift - 1)) & 1
        if (v >> 31) & 1:
            return ((v >> shift) | ((MASK << (32 - shift)) & MASK)) & MASK, c
        return (v >> shift) & MASK, c
    else:
        if regshift and shift == 0:
            return v, c
        if shift == 0:
            return ((v >> 1) | (carry_in << 31)) & MASK, v & 1
        return ror(v, shift), ((v >> (shift - 1)) & 1)

def add_cv(a, b):
    r = (a + b) & MASK
    c = 1 if (a + b) > MASK else 0
    v = 1 if ((~(a ^ b)) & (a ^ r) & 0x80000000) else 0
    return r, c, v

def sub_cv(a, b):
    r = (a - b) & MASK
    c = 1 if a >= b else 0
    v = 1 if ((a ^ b) & (a ^ r) & 0x80000000) else 0
    return r, c, v

def u16(s):
    return struct.unpack('<H', s)[0]

class Firmware:
    """Emulates the HP Prime G1 firmware syscalls used by the port."""

    def __init__(self, emu):
        self.emu = emu
        self.files = {}       # fw handle -> (host path, mode, pos)
        self.next_fh = 100
        self.heap = {}        # live allocations: addr -> size
        self.free = {}        # freed blocks: addr -> size (reusable)
        self.next_heap = 0x31000000  # heap area (within 32MB mem)
        self.heap_peak = 0x31000000  # highest next_heap ever reached
        self.heap_end = BASE + MEM_SIZE - 0x10000
        self.ev_queue = []    # get_event queue (inject_key / inject_touch)
        # scratch event struct for the OS hook simulation; must NOT overlap
        # the loaded images (tcc.elf at BASE, code.elf at BASE+0x200000 in
        # the harness) or the firmware heap (0x31000000)
        self.hook_ev = 0x30F00000

    def rd16(self, a):
        return u16(self.emu.mem[a - BASE:a - BASE + 2])

    def cstr16(self, a):
        """read UTF-16LE C string from emu memory"""
        out = []
        while True:
            c = self.rd16(a)
            if c == 0:
                break
            out.append(chr(c))
            a += 2
        return ''.join(out)

    def host_path(self, p):
        norm = p.replace('\\', '/').lower()
        if FAKE_ROOT and norm.startswith('c:/data/primetcc.hpappdir'):
            rel = p[len('c:\\data\\primetcc.hpappdir'):].replace('\\', '/')
            return FAKE_ROOT + rel
        if FAKE_ROOT and norm.startswith('c:/data/'):
            rel = p[len('c:\\data\\'):].replace('\\', '/')
            return os.path.dirname(FAKE_ROOT) + '/' + rel
        if FAKE_ROOT and not os.path.isabs(p.replace('\\', '/')):
            return FAKE_ROOT + '/' + p.replace('\\', '/')
        return p.replace('\\', '/')

    # ---- graphics: emulated 320x240 ARGB framebuffer (get_lcd) ----
    def setup_lcd(self):
        """allocate fb + lcd structs; layout matches gbemu's reading:
        get_lcd() -> P; Q=*(u32*)P; w=*(u16*)(Q+2); h=*(u16*)(Q+4);
        fb=*(u32*)(Q+16)."""
        w, h = 320, 240
        fb_size = w * h * 4
        self.fb_addr = BASE + MEM_SIZE - 0x20000 - fb_size
        emu = self.emu
        emu.mem[self.fb_addr - BASE:self.fb_addr - BASE + fb_size] = \
            b'\x00' * fb_size
        info = self.fb_addr - 0x40
        emu.wr16u(info + 0, 0)       # unknown/reserved
        emu.wr16u(info + 2, w)
        emu.wr16u(info + 4, h)
        emu.wr32(info + 8, 0)
        emu.wr32(info + 12, 0)
        emu.wr32(info + 16, self.fb_addr)
        out = info - 0x10
        emu.wr32(out, info)
        self.lcd_out = out

    # ---- input: emulated get_event (0x1003f) queue ----
    def inject_key(self, scan, down=True):
        self.ev_queue.append(('key', scan, down))

    def inject_touch(self, x, y, ttype=1):
        self.ev_queue.append(('touch', x, y, ttype))

    def os_poll_events(self, emu):
        """Simulate the OS UI thread polling input while the app sleeps:
        if the app patched the get_event slot with the DOOM-style
        trampoline, feed each injected event through the hook exactly as
        the OS would (call hook(ev) with a scratch event struct)."""
        slot = 0x307fbfa0
        if emu.rd32(slot) != 0xe51ff004:     # trampoline not installed
            return
        if not self.ev_queue:
            return
        hook = emu.rd32(slot + 4)
        if not hook:
            return
        ev = self.hook_ev
        saved = list(emu.regs)
        emu.regs[0] = ev
        emu.regs[14] = 0xFFFFFF00            # sentinel return address
        emu.regs[15] = hook
        guard = 0
        while emu.regs[15] != 0xFFFFFF00:
            addr = emu.regs[15]
            if addr < emu.base or addr >= emu.base + len(emu.mem) - 4:
                break
            insn = emu.rd32(addr)
            emu.regs[15] = (addr + 4) & MASK
            emu.exec(insn, addr)
            guard += 1
            if guard > 100000:
                break
        emu.regs[:] = saved

    # ---- syscalls (num, regs, emu) ----
    def call(self, num, r, emu):
        if num == 0x1003f:   # get_event(ev) -> fills event struct
            ev = r[0]
            for off in range(0, 128, 4):
                emu.wr32(ev + off, 0)
            if self.ev_queue:
                e = self.ev_queue.pop(0)
                if e[0] == 'key':
                    scan, down = e[1], e[2]
                    emu.wr32(ev + 4, 0x00100010)      # event type: key
                    emu.wr32(ev + 28, 16 if down else 0x100000)
                    emu.wr16u(ev + 34, scan)
                else:
                    x, y, tt = e[1], e[2], e[3]
                    emu.wr32(ev + 4, 15)              # event type: touch
                    emu.wr16u(ev + 24, 1)             # touch count
                    emu.wr32(ev + 28, tt)             # item type
                    emu.wr16u(ev + 32, 0)
                    emu.wr16u(ev + 34, x)
                    emu.wr16u(ev + 36, y)
            r[0] = 0
        elif num == 0x1008d:   # get_lcd -> struct ptr in r0
            if not hasattr(self, 'lcd_out'):
                self.setup_lcd()
            r[0] = self.lcd_out
        elif num == 0x1026f:   # fopen(path16, mode16)
            path = self.cstr16(r[0])
            mode = self.cstr16(r[1])
            hp = self.host_path(path)
            if 'w' in mode:
                with open(hp, 'wb'):
                    pass                  # create/truncate once at open
            elif 'a' in mode:
                with open(hp, 'ab'):
                    pass
            elif not os.path.exists(hp):
                if num == 0x1026f and b'prime.h' in path.encode('utf-16le'):
                    print('[fw] fopen FAIL:', repr(path), repr(mode), '->', hp)
                r[0] = 0                  # open failed (matches firmware)
                return
            fh = self.next_fh
            self.next_fh += 1
            self.files[fh] = [hp, mode, 0]
            r[0] = fh
        elif num == 0x100ca:  # fclose(fd)
            fh = r[0]
            self.files.pop(fh, None)
            r[0] = 0
        elif num == 0x100cf:  # fseek(fd, off, whence)
            fh, off, whence = r[0], r[1], r[2]
            f = self.files.get(fh)
            if f is None:
                r[0] = -1
            else:
                if whence == 0:
                    f[2] = off
                elif whence == 1:
                    f[2] += off
                else:
                    sz = os.path.getsize(f[0]) if os.path.exists(f[0]) else 0
                    f[2] = sz + off
                r[0] = f[2]
        elif num == 0x100d0:  # ftell(fd)
            fh = r[0]
            f = self.files.get(fh)
            r[0] = f[2] if f else -1
        elif num == 0x100d4:  # fread(buf, nmemb, size, fd)
            buf, size, fh = r[0], r[2], r[3]
            f = self.files.get(fh)
            if f is None or f[1][0] not in 'ra+':
                r[0] = 0
            else:
                with open(f[0], 'rb') as fh_:
                    fh_.seek(f[2])
                    data = fh_.read(size)
                self.emu.mem[buf - BASE:buf - BASE + len(data)] = data
                f[2] += len(data)
                r[0] = len(data)
        elif num == 0x100d7:  # fwrite(buf, nmemb, size, fd)
            buf, size, fh = r[0], r[2], r[3]
            f = self.files.get(fh)
            if f is None or f[1][0] not in 'wa+':
                r[0] = 0
            else:
                data = bytes(self.emu.mem[buf - BASE:buf - BASE + size])
                with open(f[0], 'r+b') as fh_:
                    fh_.seek(f[2])
                    fh_.write(data)
                f[2] += size
                r[0] = size
        elif num == 0x100cb:  # filesize(fd)
            fh = r[0]
            f = self.files.get(fh)
            r[0] = os.path.getsize(f[0]) if f and os.path.exists(f[0]) else -1
        elif num == 0x10037:  # malloc(n): reuse the smallest fitting freed
            n = (r[0] + 3) & ~3
            a = 0
            best = None
            for fa, fz in self.free.items():
                if fz >= n and (best is None or fz < self.free[best]):
                    best = fa
            if best is not None:
                a = best
                fz = self.free.pop(best)
                if fz > n:                      # split: keep the remainder
                    self.free[a + n] = fz - n
            else:
                a = self.next_heap
                if a + n > self.heap_end:
                    raise RuntimeError('firmware heap exhausted')
                self.next_heap = a + n
                if self.next_heap > self.heap_peak:
                    self.heap_peak = self.next_heap
            self.heap[a] = n
            r[0] = a
        elif num == 0x10038:  # calloc(n, sz)
            n = (r[0] * r[1] + 3) & ~3
            a = 0
            best = None
            for fa, fz in self.free.items():
                if fz >= n and (best is None or fz < self.free[best]):
                    best = fa
            if best is not None:
                a = best
                fz = self.free.pop(best)
                if fz > n:
                    self.free[a + n] = fz - n
            else:
                a = self.next_heap
                if a + n > self.heap_end:
                    raise RuntimeError('firmware heap exhausted')
                self.next_heap = a + n
                if self.next_heap > self.heap_peak:
                    self.heap_peak = self.next_heap
            self.heap[a] = n
            self.emu.mem[a - BASE:a - BASE + n] = b'\x00' * n
            r[0] = a
        elif num == 0x10039:  # realloc(p, n)
            p = r[0]
            n = (r[1] + 3) & ~3
            old = self.heap.get(p, 0) if p else 0
            if p == 0:
                a = 0
                best = None
                for fa, fz in self.free.items():
                    if fz >= n and (best is None or fz < self.free[best]):
                        best = fa
                if best is not None:
                    a = best
                    fz = self.free.pop(best)
                    if fz > n:
                        self.free[a + n] = fz - n
                else:
                    a = self.next_heap
                    if a + n > self.heap_end:
                        raise RuntimeError('firmware heap exhausted')
                    self.next_heap = a + n
                if self.next_heap > self.heap_peak:
                    self.heap_peak = self.next_heap
                self.heap[a] = n
            else:
                a = self.next_heap
                if a + n > self.heap_end:
                    raise RuntimeError('firmware heap exhausted')
                self.heap[a] = n
                self.next_heap = a + n
                if self.next_heap > self.heap_peak:
                    self.heap_peak = self.next_heap
                self.emu.mem[a - BASE:a - BASE + min(old, n)] = \
                    self.emu.mem[p - BASE:p - BASE + min(old, n)]
                if old:
                    self.free[p] = old
            r[0] = a
        elif num == 0x1003a:  # free(p): reclaim the top block, else free-list
            p = r[0]
            sz = self.heap.pop(p, 0)
            if sz:
                if p + sz == self.next_heap:
                    self.next_heap = p          # reclaim (bump allocator)
                else:
                    # merge with an adjacent free block, then store
                    if p + sz in self.free:      # merge with the next block
                        sz += self.free.pop(p + sz)
                    self.free[p] = sz
            r[0] = 0
        elif num == 0x10000:  # create_thread(fn, arg, stack)
            emu.threads.append(r[0])
            r[0] = 1          # fake thread handle
        elif num == 0x10008:  # os_sleep(ms): while the app sleeps, the OS
            self.os_poll_events(emu)   # UI loop polls input (through the hook)
            r[0] = 0
        elif num == 0x100a5:  # get_time
            r[0] = 1700000000
        elif num == 0x1008d:  # get_lcd
            r[0] = 0
        else:
            raise RuntimeError('unknown svc 0x%X' % num)


class ARMEmu:
    def __init__(self, base=BASE, mem_size=MEM_SIZE):
        self.base = base
        self.mem = bytearray(mem_size)
        self.regs = [0] * 16
        self.n = self.z = self.c = self.v = 0
        self.pc = 0
        self.insn_count = 0
        self.max_insn = 1000000000
        # 8-byte aligned entry SP: tcc.elf's _start does NOT realign SP and
        # works on the device, so the debug interface hands the entry an
        # 8-aligned SP.  LDRD/STRD alignment is still checked during exec,
        # so real-device unaligned accesses are caught regardless.
        self.sp = base + mem_size - 0x4000
        self.halt_addr = 0xDEAD0000
        self.fw = Firmware(self)
        # firmware get_event slot "original" content: a stub that performs
        # svc 0x1003f.  The input hook copies these 16 bytes as its
        # trampoline and blx's into them, so they must be executable and
        # must call the emulated get_event (the SVC handler pops the
        # pushed r0/lr and returns to the hook).  The first word is NOT
        # 0xe51ff004 so the harness's "slot restored" check stays valid.
        slot = 0x307fbfa0
        for off, word in enumerate((0xe52d0004, 0xe52de004, 0xef01003f, 0)):
            self.wr32(slot + 4 * off, word)
        self.out = []          # PRIMELOG contents collected during run
        self.log_addr = None
        self.threads = []      # firmware threads queued via svc 0x10000

    def _i(self, a):
        return a - self.base

    def rd8(self, a):
        return self.mem[self._i(a)]

    def wr8(self, a, v):
        self.mem[self._i(a)] = v & 0xFF

    def rd16u(self, a):
        return struct.unpack_from('<H', self.mem, self._i(a))[0]

    def wr16u(self, a, v):
        struct.pack_into('<H', self.mem, self._i(a), v & 0xFFFF)

    def rd32(self, a):
        return struct.unpack_from('<I', self.mem, self._i(a))[0]

    def wr32(self, a, v):
        if getattr(self, 'watch', None) and (a & ~3) == self.watch:
            print('[watch] wr32 %08X <- %08X at pc=%08X insn=%08X' % (a, v & MASK, self.regs[15] - 4, self.last_insn))
        if a < self.base or a >= self.base + len(self.mem):
            raise RuntimeError('wr32 out of range: 0x%08X pc=0x%08X' %
                               (a, self.regs[15] - 4))
        struct.pack_into('<I', self.mem, self._i(a), v & MASK)

    def rd(self, a, size):
        if size == 1:
            return self.rd8(a)
        return self.rd32(a)

    def wr(self, a, size, v):
        if size == 1:
            self.wr8(a, v)
        else:
            self.wr32(a, v)

    # ---------- ELF load: mimic the on-calc shellcode loader ----------
    def load_elf(self, elf, base):
        e_phoff = struct.unpack_from('<I', elf, 28)[0]
        e_phentsize = struct.unpack_from('<H', elf, 42)[0]
        e_phnum = struct.unpack_from('<H', elf, 44)[0]
        e_entry = struct.unpack_from('<I', elf, 24)[0]
        dyn_off = None
        for i in range(e_phnum):
            ph = elf[e_phoff + i * e_phentsize: e_phoff + (i + 1) * e_phentsize]
            p_type, p_off, p_vaddr, _p_paddr, p_filesz, p_memsz = \
                struct.unpack_from('<IIIIII', ph, 0)
            if p_type == 1:  # PT_LOAD
                dst = base + p_vaddr
                self.mem[self._i(dst):self._i(dst) + p_filesz] = \
                    elf[p_off:p_off + p_filesz]
                for j in range(p_filesz, p_memsz):
                    self.mem[self._i(dst) + j] = 0
            elif p_type == 2:  # PT_DYNAMIC
                dyn_off = base + p_vaddr
        rel_idx = relsz = symtab = syment = None
        d = dyn_off
        while True:
            tag, val = struct.unpack_from('<II', self.mem, self._i(d))
            if tag == 17:
                rel_idx = val
            elif tag == 18:
                relsz = val
            elif tag == 6:
                symtab = val
            elif tag == 11:
                syment = val
            elif tag == 0:
                break
            d += 8
        if rel_idx is not None:
            n = relsz // 8
            for i in range(n):
                r_off, r_info = struct.unpack_from('<II', self.mem,
                                                   self._i(base + rel_idx + i * 8))
                if (r_info & 0xFF) == 23:  # R_ARM_RELATIVE
                    addend = self.rd32(base + r_off)
                    self.wr32(base + r_off, (base + addend) & MASK)
                elif (r_info & 0xFF) in (2, 3) and (r_info >> 8) \
                        and symtab is not None:
                    # R_ARM_ABS32/REL32 against a symbol: the on-calc fix
                    # (ElfTools.patch_shared_relocs in main.py) rewrites
                    # these before load; mirror it here so programs with
                    # non-static globals behave the same on both paths.
                    st = symtab + (r_info >> 8) * (syment or 16) + 4
                    st_value = self.rd32(base + st)
                    addend = self.rd32(base + r_off)
                    self.wr32(base + r_off,
                              (base + addend + st_value) & MASK)
        return e_entry

    # ---------- condition codes ----------
    def cond_ok(self, cond):
        n, z, c, v = self.n, self.z, self.c, self.v
        return {
            0x0: z, 0x1: not z, 0x2: c, 0x3: not c,
            0x4: n, 0x5: not n, 0x6: v, 0x7: not v,
            0x8: c and not z, 0x9: not c or z,
            0xA: n == v, 0xB: n != v,
            0xC: not z and n == v, 0xD: z or n != v,
            0xE: True, 0xF: True,
        }[cond]

    def set_flags(self, r, c, v):
        r &= MASK
        self.n = 1 if (r >> 31) & 1 else 0
        self.z = 1 if r == 0 else 0
        self.c = 1 if c else 0
        self.v = 1 if v else 0

    # ---------- core ----------
    def run(self, entry, config_addr=0, base=None):
        if base is None:
            base = self.base
        self.regs[15] = base + entry
        self.regs[13] = self.sp
        self.regs[14] = self.halt_addr
        self.regs[0] = config_addr
        self.regs[1] = 0
        while True:
            if self.insn_count > self.max_insn:
                raise RuntimeError('instruction cap exceeded')
            self.insn_count += 1
            addr = self.regs[15]
            if addr == self.halt_addr:
                if self.threads:
                    fn = self.threads.pop(0)
                    self.regs[14] = self.halt_addr  # thread return ends it
                    self.regs[15] = fn
                    continue
                break
            if addr < self.base or addr >= self.base + len(self.mem) - 4:
                raise RuntimeError('PC out of memory: 0x%08X' % addr)
            insn = self.rd32(addr)
            self.regs[15] = (addr + 4) & MASK
            self.last_insn = insn
            try:
                self.exec(insn, addr)
            except Exception as e:
                raise RuntimeError('CRASH at PC=%08X insn=%08X (%s)' % (addr, insn, e))
            # drain PRIMELOG if present (ring is 32 KB, handle wrap)
            if self.log_addr:
                cnt = self.rd32(self.log_addr + 8)
                if cnt > self.drained:
                    n = cnt - self.drained
                    rsz = 32768
                    pos = self.drained % rsz
                    take = min(n, rsz - pos)
                    base = self._i(self.log_addr + 12)
                    chunk = bytes(self.mem[base + pos: base + pos + take])
                    if n > take:
                        chunk += bytes(self.mem[base: base + (n - take)])
                    self.out.append(chunk)
                    self.drained = cnt
        return self.regs[0] & MASK

    def find_primerlog(self):
        """locate the PRIMELOG ring by scanning the loaded image"""
        idx = self.mem.find(b'PRIMELOG')
        if idx < 0:
            return None
        self.log_addr = self.base + idx
        self.drained = self.rd32(self.log_addr + 8)
        return self.log_addr

    def find_magic(self, magic, base=None):
        """locate an 8-byte magic string in the loaded image (or in a
        region starting at `base`), returning its absolute address."""
        if base is None:
            idx = self.mem.find(magic)
        else:
            idx = self.mem.find(magic, base - self.base)
        if idx < 0:
            return None
        return self.base + idx

    def exec(self, insn, addr):
        cond = (insn >> 28) & 0xF
        if not self.cond_ok(cond):
            return
        if (insn & 0x0F000000) == 0x0E000000:          # CDP/MRC/MCR/LDC/STC
            # coprocessor ops: the emulated memory model is coherent, so
            # cache-maintenance MCRs (used by the input hook to flush the
            # real device's I-cache) are no-ops here
            return
        if (insn & 0x0F000000) == 0x0F000000:          # SVC
            self.fw.call(insn & 0xFFFFFF, self.regs, self)
            sp = self.regs[13]
            ret_lr = self.rd32(sp)
            self.regs[13] = (sp + 8) & MASK
            self.regs[15] = ret_lr
            return
        if (insn & 0x0E000000) == 0x0A000000:          # B / BL
            off = insn & 0xFFFFFF
            if off & 0x800000:
                off -= 0x1000000
            link = (insn >> 24) & 1
            if link:
                self.regs[14] = (addr + 4) & MASK
            self.regs[15] = (addr + 8 + (off << 2)) & MASK
            return
        if (insn & 0x0E000000) == 0x08000000:          # LDM / STM
            self.ldm_stm(insn)
            return
        if (insn & 0x0F8000F0) == 0x00800090:          # UMULL/SMULL/UMLAL/SMLAL
            self.long_mul(insn)
            return
        if (insn & 0x0FC000F0) == 0x00000090:          # MUL / MLA
            rd, rs, rm = (insn >> 16) & 0xF, (insn >> 8) & 0xF, insn & 0xF
            r = (self.regs[rm] * self.regs[rs]) & MASK
            if insn & 0x00200000:
                r = (r + self.regs[(insn >> 12) & 0xF]) & MASK
            self.regs[rd] = r
            if insn & (1 << 20):
                self.set_flags(r, self.c, 0)
            return
        if (insn & 0x0E5000F0) == 0x004000D0:          # LDRD
            self.ldrd_strd(insn, addr, True)
            return
        if (insn & 0x0E5000F0) == 0x004000F0:          # STRD
            self.ldrd_strd(insn, addr, False)
            return
        if (insn & 0x0E000090) == 0x00000090:          # LDRH/STRH/LDRSB/LDRSH
            self.halfword(insn, addr)
            return
        if (insn & 0x0FB00FF0) == 0x01000090:          # SWP/SWPB
            raise RuntimeError('SWP not supported at 0x%08X' % addr)
        if (insn & 0x0FFFFFF0) == 0x012FFF10:          # BX
            rm = insn & 0xF
            self.regs[15] = self.regs[rm] & ~1
            return
        if (insn & 0x0FFFFFF0) == 0x012FFF30:          # BLX (reg)
            rm = insn & 0xF
            self.regs[14] = (addr + 4) & MASK
            self.regs[15] = self.regs[rm] & ~1
            return
        if (insn & 0x0FFF0FF0) == 0x016F0F10:          # CLZ (mask out Rd/Rm: 0x016F..F1..)
            rm = insn & 0xF
            rd = (insn >> 12) & 0xF
            v = self.regs[rm]
            c = 0
            while (v & 0x80000000) == 0 and c < 32:
                v = (v << 1) & MASK
                c += 1
            self.regs[rd] = c
            return
        if (insn & 0x0C000000) == 0x04000000:          # LDR / STR
            self.ldr_str(insn, addr)
            return
        if (insn & 0x0C000000) == 0x00000000:          # data processing
            self.data_proc(insn, addr)
            return
        raise RuntimeError('unhandled instruction 0x%08X at 0x%08X' % (insn, addr))

    def halfword(self, insn, addr):
        l = (insn >> 20) & 1
        p = (insn >> 24) & 1
        u = (insn >> 23) & 1
        w = (insn >> 21) & 1
        i = (insn >> 22) & 1
        s = (insn >> 6) & 1
        h = (insn >> 5) & 1
        rn = (insn >> 16) & 0xF
        rd = (insn >> 12) & 0xF
        if i:
            off = ((insn >> 8) & 0xF) << 4 | (insn & 0xF)
        else:
            off = self.regs[insn & 0xF]
        base = (addr + 8) if rn == 15 else self.regs[rn]
        a = (base + off if u else base - off) & MASK   # ARM addresses wrap at 32 bits
        if p == 0:
            a = base
        if l:
            if s == 0 and h == 1:      # LDRH
                v = self.rd16u(a)
            elif s == 1 and h == 0:    # LDRSB
                v = self.rd8(a)
                if v & 0x80:
                    v -= 0x100
            elif s == 1 and h == 1:    # LDRSH
                v = self.rd16u(a)
                if v & 0x8000:
                    v -= 0x10000
            else:
                raise RuntimeError('bad LDR variant at 0x%08X' % addr)
            self.regs[rd] = v & MASK
        else:
            if s == 0 and h == 1:      # STRH
                self.wr16u(a, self.regs[rd])
            elif s == 1 and h == 0:    # LDRD (ARMv5TE: L bit inverted)
                self.regs[rd] = self.rd32(a)
                self.regs[rd + 1] = self.rd32(a + 4)
            elif s == 1 and h == 1:    # STRD (ARMv5TE: L bit inverted)
                self.wr32(a, self.regs[rd])
                self.wr32(a + 4, self.regs[rd + 1])
            else:
                raise RuntimeError('bad STR variant at 0x%08X' % addr)
        if w or p == 0:
            self.regs[rn] = (base + off if u else base - off) & MASK

    def long_mul(self, insn):
        u = (insn >> 22) & 1
        a = (insn >> 21) & 1
        rdlo = (insn >> 12) & 0xF
        rdhi = (insn >> 16) & 0xF
        rs = (insn >> 8) & 0xF
        rm = insn & 0xF
        x = self.regs[rm]
        y = self.regs[rs]
        # NOTE: registers are stored as unsigned 32-bit ints -- SMULL/SMLAL
        # must SIGN-EXTEND the operands before multiplying, otherwise the
        # high half of a negative product comes out wrong.  This silently
        # corrupted every signed 64-bit multiply (e.g. hp_fill_triangle's
        # edge interpolation painted full-width rows) while UMULL worked.
        if u:
            sx = x - ((x & 0x80000000) << 1)
            sy = y - ((y & 0x80000000) << 1)
            prod = (sx * sy) & 0xFFFFFFFFFFFFFFFF
        else:
            prod = (x & MASK) * (y & MASK)
        lo = prod & MASK
        hi = (prod >> 32) & MASK
        if a:
            acc = (hi << 32 | lo) + ((self.regs[rdhi] << 32) | self.regs[rdlo])
            lo = acc & MASK
            hi = (acc >> 32) & MASK
        self.regs[rdlo] = lo
        self.regs[rdhi] = hi
        if insn & (1 << 20):
            self.set_flags(lo | hi, self.c, 0)

    def data_proc(self, insn, addr):
        op = (insn >> 21) & 0xF
        s = (insn >> 20) & 1
        rn = (insn >> 16) & 0xF
        rd = (insn >> 12) & 0xF
        carry_in = self.c
        if insn & (1 << 25):
            opnd = ror(insn & 0xFF, 2 * ((insn >> 8) & 0xF))
            c_out = carry_in
        else:
            rm = insn & 0xF
            if insn & (1 << 4):
                rs = (insn >> 8) & 0xF
                shift_type = (insn >> 5) & 3
                amt = self.regs[rs] & 0xFF
                opnd, c_out = shifter_op(self.regs[rm], shift_type, amt,
                                         carry_in, True)
            else:
                shift_type = (insn >> 5) & 3
                amt = (insn >> 7) & 0x1F
                opnd, c_out = shifter_op(self.regs[rm], shift_type, amt, carry_in)
        a = (addr + 8) if rn == 15 else self.regs[rn]  # PC reads as addr+8
        res = 0
        c = c_out
        v = 0
        if op == 0:
            res = a & opnd
        elif op == 1:
            res = a ^ opnd
        elif op == 2:
            res, c, v = sub_cv(a, opnd)
        elif op == 3:
            res, c, v = sub_cv(opnd, a)
        elif op == 4:
            res, c, v = add_cv(a, opnd)
        elif op == 5:
            res, c, v = add_cv(a, opnd + carry_in)
        elif op == 6:
            res, c, v = sub_cv(a, opnd + (1 - carry_in))
        elif op == 7:
            res, c, v = sub_cv(opnd, a + (1 - carry_in))
        elif op == 8:
            res = a & opnd
        elif op == 9:
            res = a ^ opnd
        elif op == 10:
            res, c, v = sub_cv(a, opnd)
        elif op == 11:
            res, c, v = add_cv(a, opnd)
        elif op == 12:
            res = a | opnd
        elif op == 13:
            res = opnd
        elif op == 14:
            res = a & (MASK ^ opnd)
        elif op == 15:
            res = MASK ^ opnd
        res &= MASK
        if s or op in (8, 9, 10, 11):
            self.set_flags(res, c, v)
        if op not in (8, 9, 10, 11):
            self.regs[rd] = res
            if rd == 15:
                self.regs[15] = res & ~3

    def ldrd_strd(self, insn, addr, is_load):
        """LDRD/STRD (immediate-offset form).  These access an 8-byte pair
        and REQUIRE 8-byte alignment on ARM926EJ-S: an unaligned access
        raises a data abort (the calculator reboots).  Emulate that: the
        real debug interface hands code.elf a 4-aligned SP, so any GCC
        LDRD/STRD on the stack with a misaligned frame faults on device."""
        p = (insn >> 24) & 1
        u = (insn >> 23) & 1
        w = (insn >> 21) & 1
        rn = (insn >> 16) & 0xF
        rt = (insn >> 12) & 0xF
        imm = (((insn >> 8) & 0xF) << 4) | (insn & 0xF)
        off = imm if u else -imm
        base = (addr + 8) if rn == 15 else self.regs[rn]
        ea = base if not p else (base + off) & MASK
        if ea % 8 != 0:
            raise RuntimeError(
                'unaligned LDRD/STRD: pc=0x%08X insn=%08X ea=0x%08X' %
                (addr, insn, ea))
        if is_load:
            self.regs[rt] = self.rd32(ea)
            self.regs[rt + 1] = self.rd32(ea + 4)
        else:
            self.wr32(ea, self.regs[rt])
            self.wr32(ea + 4, self.regs[rt + 1])
        if w:
            self.regs[rn] = (base + off) & MASK

    def ldr_str(self, insn, addr):
        l = (insn >> 20) & 1
        b = (insn >> 22) & 1
        p = (insn >> 24) & 1
        u = (insn >> 23) & 1
        w = (insn >> 21) & 1
        i = (insn >> 25) & 1
        rn = (insn >> 16) & 0xF
        rd = (insn >> 12) & 0xF
        if i:
            rm = insn & 0xF
            shift_type = (insn >> 5) & 3
            amt = (insn >> 7) & 0x1F
            off, _ = shifter_op(self.regs[rm], shift_type, amt, self.c)
        else:
            off = insn & 0xFFF
        base = (addr + 8) if rn == 15 else self.regs[rn]
        a = (base + off if u else base - off) & MASK   # ARM addresses wrap at 32 bits
        if p == 0:
            a = base
        size = 1 if b else 4
        if l:
            v = self.rd(a, size)
            self.regs[rd] = v
        else:
            self.wr(a, size, self.regs[rd])
        if w or p == 0:
            self.regs[rn] = (base + off if u else base - off) & MASK

    def ldm_stm(self, insn):
        l = (insn >> 20) & 1
        p = (insn >> 24) & 1
        u = (insn >> 23) & 1
        w = (insn >> 21) & 1
        rn = (insn >> 16) & 0xF
        reglist = insn & 0xFFFF
        addr = self.regs[rn]
        regs = []
        if u:
            for r in range(16):
                if reglist & (1 << r):
                    regs.append(r)
        else:
            for r in range(15, -1, -1):
                if reglist & (1 << r):
                    regs.append(r)
        for r in regs:
            if p:
                addr = (addr + 4) & MASK if u else (addr - 4) & MASK
            if l:
                self.regs[r] = self.rd32(addr)
            else:
                self.wr32(addr, self.regs[r])
            if not p:
                addr = (addr + 4) & MASK if u else (addr - 4) & MASK
        if w:
            self.regs[rn] = addr
        if l and (reglist & 0x8000):
            self.regs[15] = self.regs[15] & ~1
