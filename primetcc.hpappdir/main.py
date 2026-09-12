"""
main.py -- HP Prime calculator launcher for primetcc (TCC on the HP Prime).

Run on the calculator (MicroPython):
    >>> import main

Flow:
  1. Reads the C source from this file (between PRIME-C-CODE markers) or from
     a file given as `main.compile_file("test.c")`.
  2. Writes it to C:\\DATA\\primetcc.hpappdir\\code.c
  3. Loads puredoom-style tcc.elf with the shellcode loader and calls its
     entry point with a config {magic, argc, argv} so TCC compiles
         code.c  ->  code.elf
     (only the user source is compiled on the calculator now; the runtime
     hp_rt/hp_gfx/hp_input/hp_math/hp_string is prebuilt as rt_core.o and
     linked together with rt_svc.o / rt_aeabi.o / rt_math.o).
  4. Streams TCC's PRIMELOG output while it runs.
  5. If code.elf was produced, loads and runs it (entry hp_entry, a pure
     passthrough to main()) and prints its PRIMELOG output and return
     value.  code.elf is deliberately NOT freed on exit: the OS UI thread
     can be blocked inside the input hook at any moment, and freeing would
     crash the calculator on the next keypress (verified on hardware).

Firmware notes (HP Prime G1):
  * syscalls go through push{r0}; push{lr}; svc N (the handler returns via
    the pushed LR); see the DOOM/PureDOOM port for the same convention.
  * firmware API table base 0x307FBCAC (id 0x10037 = malloc, 0x1003a = free).
"""
import ustruct as struct
import uio
import hpprime

# colored console helpers (moreprint.py, user-provided).  On hosts / when
# moreprint is missing, fall back to plain print so everything still works.
try:
    from moreprint import p_log, p_warning, p_error, p_pass, p_out
except Exception:
    def p_log(text):
        print(text)
    def p_warning(text):
        print(text)
    def p_error(text):
        print(text)
    def p_pass(text):
        print(text)
    def p_out(text):
        print(text)


def decode_bytes(b):
    """MicroPython bytes.decode may not support the errors= argument."""
    try:
        return b.decode("utf-8")
    except Exception:
        return "".join(chr(x) for x in b)

# ---------------------------------------------------------------------------
# firmware debug interface + shellcode ELF loader (same as the DOOM port)
# ---------------------------------------------------------------------------
class PrimeDebug:
    def __init__(self, filename="debug"):
        try:
            self.f = uio.FileIO("debug")
        except Exception:
            self.f = open(filename, "rb")
        p_log("[+] Debug interface opened.")

    def close(self):
        if self.f:
            self.f.close()

    def write_mem(self, addr, val):
        self.f.write(struct.pack("<III", 1, addr, val))

    def read_mem(self, addr, size):
        self.f.write(struct.pack("<III", 0, addr, 0))
        return self.f.read(size)

    def call(self, func_addr, *args):
        arg_count = len(args)
        fmt = "<III" + "I" * arg_count
        buf = bytearray(struct.calcsize(fmt))
        struct.pack_into(fmt, buf, 0, 2, func_addr, arg_count, *args)
        self.f.write(buf)
        return struct.unpack_from("<I", buf, 0)[0]

    def write_mem_bytes(self, addr, data):
        pad_len = (4 - (len(data) % 4)) % 4
        data += b"\x00" * pad_len
        for i in range(0, len(data), 4):
            val = struct.unpack("<I", data[i:i + 4])[0]
            self.write_mem(addr + i, val)


BASE = 0x307FBCAC

def get_addr(int_id):
    return BASE + 0xC * (int_id - 0x10000)

ADDR_MALLOC = get_addr(0x10037)
ADDR_FREE = get_addr(0x1003A)


class ElfTools:
    @staticmethod
    def get_elf_memory_size(filename):
        """read the ELF header, compute the total image size (max p_vaddr+p_memsz)"""
        required_size = 0
        try:
            with uio.FileIO(filename, "rb") as f:
                ehdr = f.read(52)
                if len(ehdr) < 52 or ehdr[0:4] != b"\x7fELF":
                    p_error("[-] Invalid ELF header")
                    return 0
                e_phoff = struct.unpack_from("<I", ehdr, 28)[0]
                e_phentsize = struct.unpack_from("<H", ehdr, 42)[0]
                e_phnum = struct.unpack_from("<H", ehdr, 44)[0]
                f.seek(e_phoff)
                for i in range(e_phnum):
                    ph = f.read(e_phentsize)
                    p_type = struct.unpack_from("<I", ph, 0)[0]
                    p_vaddr = struct.unpack_from("<I", ph, 8)[0]
                    p_memsz = struct.unpack_from("<I", ph, 20)[0]
                    if p_type == 1:
                        end = p_vaddr + p_memsz
                        if end > required_size:
                            required_size = end
        except Exception as e:
            p_error("[-] Error parsing ELF: " + str(e))
            return 0
        return (required_size + 3) & ~3

    @staticmethod
    def patch_shared_relocs(filename):
        """Convert symbol-based relocations (R_ARM_ABS32=2 / REL32=3) that
        TCC emits for references to NON-static file-scope variables into
        R_ARM_RELATIVE (23) with the symbol value folded into the addend.

        The on-calc shellcode loader (and the emulator) only applies
        R_ARM_RELATIVE; symbol-based entries are skipped silently, so the
        literal holding &global stays 0 and the first access crashes
        (seen as: 'int board[8];' rebooted the calc while
        'static int board[8];' ran fine).
        ARM ABS32: final = S + A.  RELATIVE: final = base + word.
        Folding S into the word (word += st_value) and switching the type
        makes the loader apply exactly base + S + A.  Byte-precise: only
        touched entries/words are rewritten (code.elf is ~200KB)."""
        try:
            with uio.FileIO(filename, "rb") as f:
                ehdr = f.read(52)
                if len(ehdr) < 52 or ehdr[0:4] != b"\x7fELF":
                    return 0
                e_phoff = struct.unpack_from("<I", ehdr, 28)[0]
                e_phentsize = struct.unpack_from("<H", ehdr, 42)[0]
                e_phnum = struct.unpack_from("<H", ehdr, 44)[0]
                loads = []
                dyn_off = None
                f.seek(e_phoff)
                for _ in range(e_phnum):
                    ph = f.read(e_phentsize)
                    p_type = struct.unpack_from("<I", ph, 0)[0]
                    p_off = struct.unpack_from("<I", ph, 4)[0]
                    p_vaddr = struct.unpack_from("<I", ph, 8)[0]
                    p_filesz = struct.unpack_from("<I", ph, 16)[0]
                    p_memsz = struct.unpack_from("<I", ph, 20)[0]
                    if p_type == 1:
                        loads.append((p_vaddr, p_off, p_memsz))
                    elif p_type == 2:
                        dyn_off = p_off
                if dyn_off is None:
                    return 0
                f.seek(dyn_off)
                dyn = f.read(256)
                tags = {}
                for j in range(0, len(dyn) - 7, 8):
                    tag, val = struct.unpack_from("<II", dyn, j)
                    if tag == 0:
                        break
                    tags[tag] = val
                if 17 not in tags or 18 not in tags or 6 not in tags:
                    return 0            # DT_REL / DT_RELSZ / DT_SYMTAB
                rel_off, rel_sz = tags[17], tags[18]
                sym_off = tags[6]
                syment = tags.get(11, 16)
        except Exception as e:
            p_warning("[!] reloc scan failed: " + str(e))
            return 0

        def vma2file(v):
            for p_vaddr, p_off, p_memsz in loads:
                if p_vaddr <= v < p_vaddr + p_memsz:
                    return v - p_vaddr + p_off
            return None

        patched = 0
        updates = []
        try:
            with uio.FileIO(filename, "rb") as f:
                f.seek(rel_off)
                rel = f.read(rel_sz)
            for i in range(rel_sz // 8):
                r_off, r_info = struct.unpack_from("<II", rel, i * 8)
                rtype = r_info & 0xFF
                idx = r_info >> 8
                if rtype == 23 or idx == 0:
                    continue
                if rtype not in (2, 3):      # ABS32 / REL32 only
                    p_warning("[!] unhandled reloc type %d at 0x%06X"
                              % (rtype, r_off))
                    continue
                with uio.FileIO(filename, "rb") as f:
                    f.seek(sym_off + idx * syment + 4)
                    st_value = struct.unpack("<I", f.read(4))[0]
                wpos = vma2file(r_off)
                if wpos is None:
                    continue
                with uio.FileIO(filename, "rb") as f:
                    f.seek(wpos)
                    word = struct.unpack("<I", f.read(4))[0]
                updates.append((rel_off + i * 8,
                                struct.pack("<II", r_off,
                                            (r_info & 0xFFFFFF00) | 23)))
                updates.append((wpos,
                                struct.pack("<I",
                                            (word + st_value) & 0xFFFFFFFF)))
                patched += 1
            if patched:
                try:
                    with uio.FileIO(filename, "r+b") as f:
                        for pos, blob in updates:
                            f.seek(pos)
                            f.write(blob)
                except Exception:
                    # firmware refuses update mode: rewrite the whole file
                    with uio.FileIO(filename, "rb") as f:
                        buf = bytearray(f.read())
                    for pos, blob in updates:
                        buf[pos:pos + len(blob)] = blob
                    with uio.FileIO(filename, "wb") as f:
                        f.write(buf)
        except Exception as e:
            p_error("[-] reloc patch failed: " + str(e))
            return 0
        if patched:
            p_log("[*] fixed %d global-symbol reference(s) "
                  "(ABS32 -> RELATIVE)" % patched)
        return patched

    @staticmethod
    def find_magic_addr(filename, magic, loaded_base):
        """locate a magic string inside the loaded image, reading the ELF
        in 4KB chunks (no full-file read; relative path only).  Runtime
        address = base + p_vaddr + (magic_file_offset - p_offset)."""
        try:
            with uio.FileIO(filename, "rb") as f:
                ehdr = f.read(52)
                if len(ehdr) < 52 or ehdr[0:4] != b"\x7fELF":
                    return 0
                e_phoff = struct.unpack_from("<I", ehdr, 28)[0]
                e_phentsize = struct.unpack_from("<H", ehdr, 42)[0]
                e_phnum = struct.unpack_from("<H", ehdr, 44)[0]
                f.seek(e_phoff)
                segs = []
                for i in range(e_phnum):
                    ph = f.read(e_phentsize)
                    if len(ph) < e_phentsize:
                        break
                    p_type = struct.unpack_from("<I", ph, 0)[0]
                    if p_type == 1:
                        segs.append((struct.unpack_from("<I", ph, 4)[0],
                                     struct.unpack_from("<I", ph, 8)[0],
                                     struct.unpack_from("<I", ph, 16)[0]))
                # chunked scan with a 7-byte overlap for the 8-byte magic
                f.seek(0)
                pos = 0
                carry = b""
                while True:
                    chunk = f.read(4096)
                    if not chunk:
                        return 0
                    window = carry + chunk
                    base_pos = pos - len(carry)
                    idx = window.find(magic)
                    if idx >= 0:
                        abs_off = base_pos + idx
                        for (p_off, p_vaddr, p_filesz) in segs:
                            if p_off <= abs_off < p_off + p_filesz:
                                return loaded_base + p_vaddr + (abs_off - p_off)
                        return 0
                    carry = window[-7:]
                    pos += len(chunk)
        except Exception as e:
            p_error("[-] find_magic: " + str(e))
            return 0

    @staticmethod
    def find_primerlog_addr(filename, loaded_base):
        """locate the PRIMELOG ring inside the loaded image."""
        return ElfTools.find_magic_addr(filename, b"PRIMELOG", loaded_base)
class ShellcodeElfLoader:
    def __init__(self, dbg):
        self.dbg = dbg
        self.loader_addr = 0
        self.loaded_elf_base = 0
        self.loaded_elf_raw = 0
        self.loaded_elf_size = 0
        self.entry_point = 0
        self.loader_code = b'\x0b\x00\x00\xea\x04\x00-\xe5\x04\xe0-\xe5o\x02\x01\xef\x04\x00-\xe5\x04\xe0-\xe5\xca\x00\x01\xef\x04\x00-\xe5\x04\xe0-\xe5\xd4\x00\x01\xef\x04\x00-\xe5\x04\xe0-\xe5\xcf\x00\x01\xefh2\x9f\xe5\xf0O-\xe9\x030\x8f\xe0\x00 \xa0\xe1\x01`\xa0\xe1\x03\x00\x93\xe8d\xd0M\xe2\x04\x00\x8d\xe5\xb8\x10\xcd\xe1\x02\x00\xa0\xe1\x04\x10\x8d\xe2\xe7\xff\xff\xeb\x00@P\xe2s\x00\x00\n\x040\xa0\xe1\x01 \xa0\xe34\x10\xa0\xe3,\x00\x8d\xe2\xe6\xff\xff\xeb\x01\x00P\xe3j\x00\x00\x1a\xbc"\xdd\xe1\x142\x9f\xe5\x03\x00R\xe1f\x00\x00\x1aH\x10\x9d\xe5\x00 \xa0\xe3\x04\x00\xa0\xe1\xdf\xff\xff\xeb\xb85\xdd\xe1\x00\x00S\xe3x\x00\x00\n\x00P\xa0\xe3\x05p\xa0\xe1\x0c\xa0\x8d\xe2\x04\x00\x00\xea\xb85\xdd\xe1\x02\x00[\xe3\x14p\x9d\x05\x05\x00S\xe1\x19\x00\x00\xda\x040\xa0\xe1\x01 \xa0\xe3 \x10\xa0\xe3\n\x00\xa0\xe1\xcb\xff\xff\xeb\x0c\xb0\x9d\xe5\x01P\x85\xe2\x01\x00[\xe3\xf1\xff\xff\x1a\x1c0\x9d\xe5\x14\x80\x9d\xe5H\x90\x9d\xe5\x00\x00S\xe3\x08\x80\x86\xe0\x85\x92\x89\xe0K\x00\x00\x1a  \x9d\xe5\x03\x00R\xe1U\x00\x00\x8a\t\x10\xa0\xe1\x00 \xa0\xe3\x04\x00\xa0\xe1\xbc\xff\xff\xeb\xb85\xdd\xe1\x05\x00S\xe1\xe5\xff\xff\xca\x04\x00\xa0\xe1\xb1\xff\xff\xeb\x00\x00W\xe3/\x00\x00\n\x070\x96\xe7\x07p\x86\xe0\x00\x00S\xe3+\x00\x00\n\x00 \xa0\xe3\x08\xc0\xa0\xe3\x02\x00\xa0\xe1\x02\xe0\xa0\xe1\x11\x00S\xe3\x04\xe0\x97\x05\x04\x00\x00\n\x12\x00S\xe3\x04\x00\x97\x05\x01\x00\x00\n\x13\x00S\xe3\x04\xc0\x97\x05\x080\xb7\xe5\x01 \x82\xe2\x00\x00S\xe3d\x00R\x13\x01\x10\xa0\x13\x00\x10\xa0\x03\xf0\xff\xff\x1a\x00\x00^\xe3\x00\x00P\x13\x15\x00\x00\n\x00\x00\\\xe3\x08\xc0\xa0\x03\x0c\x00P\xe1\x11\x00\x00:\x0c\x00@\xe0\x00\x00\\\xe1\x01\x10\x81\xe2\xfb\xff\xff\x9a\x00\x00Q\xe3\x0b\x00\x00\n\x81\x11\x86\xe0\x0e0\x86\xe0\x0e\x10\x81\xe0\x04 \xd3\xe5\x080\x83\xe2\x17\x00R\xe3\x08\x00\x13\x05\x00 \x96\x07\x02 \x86\x00\x00 \x86\x07\x01\x00S\xe1\xf6\xff\xff\x1a\x000\xa0\xe3~\xff\x17\xee\xfd\xff\xff\x1a\x9a?\x07\xee\x15?\x07\xeeD0\x9d\xe5\x03\x00\x86\xe0d\xd0\x8d\xe2\xf0\x8f\xbd\xe8\x04\x00\xa0\xe1t\xff\xff\xeb\x00\x00\xa0\xe3d\xd0\x8d\xe2\xf0\x8f\xbd\xe8\x10\x10\x9d\xe5\x00 \xa0\xe3\x04\x00\xa0\xe1s\xff\xff\xeb\x1c \x9d\xe5\x040\xa0\xe1\x0b\x10\xa0\xe1\x08\x00\xa0\xe1k\xff\xff\xeb\x1c0\x9d\xe5  \x9d\xe5\x03\x00R\xe1\xa9\xff\xff\x9a\x030\x88\xe0\x02\x80\x88\xe0\x00 \xa0\xe3\x01 \xc3\xe4\x08\x00S\xe1\xfc\xff\xff\x1a\xa2\xff\xff\xea\x04\x00\xa0\xe1[\xff\xff\xeb\xda\xff\xff\xeah\x02\x00\x00\x7fE\x00\x00r\x00b\x00\x00\x00'

    def upload_loader(self):
        size = len(self.loader_code)
        if size == 0:
            p_error("[!] loader_code is empty!")
            return False
        p_log("[*] Allocating loader shellcode ({} bytes)...".format(size))
        self.loader_addr = self.dbg.call(ADDR_MALLOC, (size + 3) & ~3)
        if self.loader_addr == 0:
            p_error("[-] Malloc failed for loader")
            return False
        self.dbg.write_mem_bytes(self.loader_addr, self.loader_code)
        return True

    def load_elf(self, filename):
        """upload the shellcode loader, then load the ELF into a malloc'd buffer.
        Returns (entry_point, log_ring_addr)."""
        mem_size = ElfTools.get_elf_memory_size(filename)
        p_log("[*] ELF requires memory: {} bytes".format(mem_size))
        if mem_size == 0:
            return 0, 0
        self.loaded_elf_size = mem_size
        # CRITICAL: the firmware malloc only guarantees 4-byte alignment, but
        # the image contains 8-byte-aligned data (the stack top, long long /
        # double globals) accessed with LDRD/STRD.  Unaligned double-word
        # access traps on the ARM926EJ-S, so align the image base to 8
        # (keep the raw pointer for free()).
        raw = self.dbg.call(ADDR_MALLOC, mem_size + 16)
        if raw == 0:
            p_error("[-] Target malloc failed")
            return 0, 0
        self.loaded_elf_raw = raw
        self.loaded_elf_base = (raw + 15) & ~7
        p_log("[*] Allocated Target Memory at: 0x{:08X} (raw 0x{:08X}, 8-aligned)".format(
            self.loaded_elf_base, raw))
        if self.loaded_elf_base == 0:
            p_error("[-] Target malloc failed")
            return 0, 0
        path_bytes = str_to_utf16le_bytes("C:\\DATA\\primetcc.hpappdir\\" + filename)
        path_addr = self.dbg.call(ADDR_MALLOC, len(path_bytes))
        self.dbg.write_mem_bytes(path_addr, path_bytes)
        try:
            self.entry_point = self.dbg.call(self.loader_addr, path_addr,
                                             self.loaded_elf_base)
            p_log("[+] Shellcode returned Entry Point: 0x{:08X}".format(self.entry_point))
            if self.entry_point == 0 or self.entry_point < 0x30000000:
                p_error("[-] Loading failed")
                return 0, 0
            # MicroPython cannot open C:\... absolute paths; pass the
            # relative filename (same rule as every other uio.FileIO here)
            log_addr = ElfTools.find_primerlog_addr(filename, self.loaded_elf_base)
            p_log("[+] PRIMELOG ring at: 0x{:08X}".format(log_addr))
            return self.entry_point, log_addr
        finally:
            if path_addr:
                self.dbg.call(ADDR_FREE, path_addr)

    def unload(self):
        if self.loaded_elf_raw:
            self.dbg.call(ADDR_FREE, self.loaded_elf_raw)
            self.loaded_elf_raw = 0
            self.loaded_elf_base = 0
        if self.loader_addr:
            self.dbg.call(ADDR_FREE, self.loader_addr)
            self.loader_addr = 0


def str_to_utf16le_bytes(s):
    res = bytearray()
    for ch in s:
        val = ord(ch)
        res.append(val & 0xFF)
        res.append((val >> 8) & 0xFF)
    res.append(0)
    res.append(0)
    return bytes(res)


# ---------------------------------------------------------------------------
# PRIMELOG streaming
# ---------------------------------------------------------------------------
class LogReader:
    """streams the C side's PRIMELOG ring (magic "PRIMELOG", int count,
    char data[RING]) back to the console.  color_fn selects the text color
    (p_log = gray info, p_out = blue user output); classify turns TCC
    compiler error/warning lines red/orange."""
    def __init__(self, dbg, log_addr, color_fn=p_log, classify=False):
        self.dbg = dbg
        self.addr = log_addr
        self.local = 0
        self.ring = 32768
        self.pend = ""     # partial line buffer for colored streaming
        self.color_fn = color_fn
        self.classify = classify

    def process(self):
        if not self.addr:
            return
        head = struct.unpack("<I", self.dbg.read_mem(self.addr + 8, 4))[0]
        if head > self.local:
            n = head - self.local
            pos = self.local % self.ring
            take = min(n, self.ring - pos)
            chunk = self.dbg.read_mem(self.addr + 12 + pos, take)
            if n > take:
                chunk += self.dbg.read_mem(self.addr + 12, n - take)
            txt = None
            try:
                txt = chunk.decode("utf-8", "ignore")
            except Exception:
                txt = str(chunk)
            # stream complete lines, colored; keep partials for later
            self.pend += txt
            while "\n" in self.pend:
                line, self.pend = self.pend.split("\n", 1)
                if not line:
                    continue
                try:
                    if self.classify:
                        low = line.lower()
                        if "error" in low:
                            p_error(line)
                        elif "warning" in low:
                            p_warning(line)
                        else:
                            self.color_fn(line)
                    else:
                        self.color_fn(line)
                except Exception:
                    print(line)
            self.local = head
            return txt
        return None


# ---------------------------------------------------------------------------
# config (argc/argv) for TCC, same struct the C side expects:
#   struct hp_config { unsigned magic; int argc; char **argv;
#                      unsigned env_count; char **envs; }  magic = 0xD00BC760
# ---------------------------------------------------------------------------
CONFIG_MAGIC = 0xD00BC760
RING = 32768  # must match hp_libc.h's ring size

# Isolation switch for on-device debugging: when False, code.elf runs with
# input state = 0, so hp_input_install() fails and the hook is NEVER
# installed.  If the calculator's OWN keys still do not work in this mode,
# the OS input loop is stuck from an earlier broken build and needs a HARD
# reboot (battery pull / back reset hole) -- no software can unstick it.
INPUT_ENABLE = True

class ConfigBuilder:
    def __init__(self, dbg):
        self.dbg = dbg
        self.allocations = []

    def _str(self, s):
        b = s.encode("utf-8") + b"\x00"
        size = (len(b) + 3) & ~3
        addr = self.dbg.call(ADDR_MALLOC, size)
        self.dbg.write_mem_bytes(addr, b)
        self.allocations.append(addr)
        return addr

    def build(self, argv):
        ptrs = [self._str(a) for a in argv]
        arr = b"".join(struct.pack("<I", p) for p in ptrs)
        arr_addr = self.dbg.call(ADDR_MALLOC, len(arr))
        self.dbg.write_mem_bytes(arr_addr, arr)
        self.allocations.append(arr_addr)
        cfg = struct.pack("<IIIII", CONFIG_MAGIC, len(argv), arr_addr, 0, 0)
        cfg_addr = self.dbg.call(ADDR_MALLOC, len(cfg))
        self.dbg.write_mem_bytes(cfg_addr, cfg)
        self.allocations.append(cfg_addr)
        return cfg_addr

    def free_all(self):
        for a in reversed(self.allocations):
            self.dbg.call(ADDR_FREE, a)
        self.allocations = []


# ---------------------------------------------------------------------------
# real exit-code reporting: the firmware debug interface reports 2 for the
# user program's entry no matter what main() returns, so hp_entry logs the
# real value as "RT_RET:<n>" in the PRIMELOG ring and we parse it here.
# ---------------------------------------------------------------------------
def _parse_rt_ret(text):
    """extract the real exit code that hp_entry logged as RT_RET:<n>."""
    i = text.rfind("RT_RET:")
    if i < 0:
        return None
    j = i + len("RT_RET:")
    num = ""
    while j < len(text) and text[j].isdigit():
        num += text[j]
        j += 1
    try:
        return int(num) if num else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# resident TCC (tcc.slot): keep the ~675KB tcc.elf image + shellcode loader
# in firmware memory across runs so repeated compile+run cycles stop churning
# the firmware heap (the README's "crash after 5-9 runs" was exactly that
# churn: ~900KB malloc/free per run on a small shared heap).
#
# Slot file (20 bytes, <IIIII): loader_addr, base, size, entry_point, log_addr.
# A reboot or heap reuse invalidates the resident image, so before reusing
# we verify the shellcode loader's first instruction, the ELF magic at the
# base, AND that the resident image size matches the tcc.elf on disk
# (a re-deployed tcc.elf of a different size must never be skipped --
# e.g. the resident-hook build is 3KB larger than the previous one).
# ---------------------------------------------------------------------------
TCC_SLOT = "tcc.slot"


def _tcc_file_size():
    try:
        with uio.FileIO("tcc.elf", "rb") as f:
            f.seek(0, 2)
            return f.tell()
    except Exception:
        return 0


def _slot_load(dbg, loader):
    """reuse a resident tcc.elf from a previous run, or return None to
    load it fresh (and then save the slot)."""
    try:
        with uio.FileIO(TCC_SLOT, "rb") as f:
            b = f.read(20)
    except Exception:
        return None                      # no slot yet: first run
    try:
        if len(b) < 20:
            return None
        la, base, size, entry, log_addr = struct.unpack("<IIIII", b)
        if min(la, base, entry, log_addr) < 0x30000000:
            return None
        if size != _tcc_file_size():     # tcc.elf on disk changed size
            return None
        if dbg.read_mem(la, 4) != b"\x0b\x00\x00\xea":  # b +0x2c (loader)
            return None
        if dbg.read_mem(base, 4) != b"\x7fELF":          # ELF magic
            return None
        loader.loader_addr = la
        loader.loaded_elf_raw = 0       # do not free a foreign pointer
        loader.loaded_elf_base = base
        loader.loaded_elf_size = size
        loader.entry_point = entry
        p_log("[+] reusing resident tcc.elf at 0x{:08X} (tcc.slot)".format(base))
        return entry, log_addr
    except Exception as e:
        p_warning("[!] tcc.slot unusable (%r); reloading tcc.elf" % (e,))
        return None


def _slot_save(loader, log_addr):
    try:
        b = struct.pack("<IIIII", loader.loader_addr, loader.loaded_elf_base,
                        loader.loaded_elf_size, loader.entry_point, log_addr)
        with uio.FileIO(TCC_SLOT, "wb") as f:
            f.write(b)
        p_log("[+] tcc.slot saved (tcc.elf stays resident)")
    except Exception as e:
        p_warning("[!] could not write tcc.slot: %r" % (e,))


def reset_tcc():
    """drop tcc.slot: the next run re-allocates and reloads tcc.elf.
    (The old resident image stays in firmware memory until the calculator
    is reset -- deleting the slot only stops it from being reused.)"""
    try:
        import os as _os
        _os.remove(TCC_SLOT)
    except Exception:
        try:
            uio.remove(TCC_SLOT)
        except Exception:
            p_log("[!] no tcc.slot to remove")
            return
    p_log("[+] tcc.slot removed; next run reloads tcc.elf")


# The C runtime writes its diagnostics to the ABSOLUTE app-dir path
# (rt/hp_rt.c diag_log: C:\DATA\primetcc.hpappdir\crash.log).  On the real
# calculator the MicroPython app's CWD is the PARENT (C:\DATA), so plain
# relative names ("crash.log") silently hit a different, nonexistent file
# and the stale logs were never cleared/read/appended.  Always do both
# spellings; prefer the absolute one.
TRACE_DIR = "C:\\DATA\\primetcc.hpappdir"


def _remove_file(name):
    for p in (TRACE_DIR + "\\" + name, name):
        try:
            import os as _os
            _os.remove(p)
        except Exception:
            try:
                uio.remove(p)
            except Exception:
                pass


def _append_trace(line):
    """Durably append one marker line to crash.log.  The C runtime's
    diag_log trails every step there; these M-markers record that the
    MicroPython side regained control after the program.  'ab' is tried
    first; firmware that rejects it falls back to read+rewrite."""
    for path in (TRACE_DIR + "\\crash.log", "crash.log"):
        try:
            with uio.FileIO(path, "ab") as f:
                f.write(line)
            return
        except Exception:
            pass
    try:
        with uio.FileIO(TRACE_DIR + "\\crash.log", "rb") as f:
            old = f.read()
        with uio.FileIO(TRACE_DIR + "\\crash.log", "wb") as f:
            f.write(old + line)
    except Exception:
        pass


def _clear_trace_files():
    """A fully successful run leaves stage.txt / tcc.log / crash.log with
    stale content; the NEXT run would otherwise display it as a bogus
    'previous crash trace' even though nothing crashed.  Only cleared on
    a clean, complete run -- a crash/reboot leaves them for diagnosis."""
    _remove_file("stage.txt")
    _remove_file("tcc.log")
    _remove_file("crash.log")


def _read_any(name):
    """read a trace file, trying the runtime's absolute app-dir path first
    (the C runtime writes there) and the relative name as a fallback."""
    for p in (TRACE_DIR + "\\" + name, name):
        try:
            with uio.FileIO(p, "rb") as f:
                return f.read()
        except Exception:
            pass
    return b""


def _trace_logs_exist():
    """read the stale trace files from a previous (unfinished) run and show
    them.  Returns True if any of them has content."""
    have = False
    st = _read_any("stage.txt")
    if st:
        have = True
        p_log("--- previous stage marker: %s ---" % decode_bytes(st).strip())
    prev = _read_any("tcc.log")
    if prev:
        have = True
        p_warning("--- previous tcc.log (crash trace) ---")
        p_warning(decode_bytes(prev))
        p_log("--- end previous log ---")
    # crash.log: the C runtime (diag_log) trails each completed step here
    # DURABLY (rewritten + closed per line); main.py only APPENDS its M1..M4
    # markers, so a crash+reboot shows both the trail AND where it died.
    # ("wb" here would truncate the runtime's trail -- seen on device as
    # nothing but "M4 dbg-closed".)
    cr = _read_any("crash.log")
    if cr:
        have = True
        p_warning("--- last crash.log step: %s ---" %
                  decode_bytes(cr).strip())
    return have


def _handle_stale_logs():
    """Crash gate: if a previous run left trace logs, STOP before compiling
    and let the user read them -- recompiling the same crashing program
    would crash again and overwrite/refresh the logs, making them
    unreadable.  The user answers y (delete logs, compile) or anything
    else (keep logs, do NOT compile).  Returns True to proceed, False to
    abort the run."""
    if not _trace_logs_exist():
        return True
    p_warning("[!] The previous run did not finish cleanly; the program")
    p_warning("    will NOT be recompiled until the trace logs are cleared.")
    try:
        ans = input("[?] Delete trace logs and compile? [y/N]: ")
    except Exception:
        ans = ""
    if ans.strip().lower().startswith("y"):
        _remove_file("stage.txt")
        _remove_file("tcc.log")
        _remove_file("crash.log")
        p_pass("[+] trace logs deleted; compiling now")
        return True
    p_log("[-] trace logs kept; not compiling.  Fix the program, re-run,")
    p_log("    and answer y to clear the logs (the logs stay readable).")
    return False



# ---------------------------------------------------------------------------
# the TCC command line used on the calculator
# ---------------------------------------------------------------------------
def tcc_argv():
    return [
        "tcc",
        "-nostdlib", "-shared", "-Wl,-e,hp_entry",
        "-I", "C:\\DATA\\primetcc.hpappdir",
        "-o", "C:\\DATA\\primetcc.hpappdir\\code.elf",
        "C:\\DATA\\primetcc.hpappdir\\code.c",
        "C:\\DATA\\primetcc.hpappdir\\rt_core.o",
        "C:\\DATA\\primetcc.hpappdir\\rt_svc.o",
        "C:\\DATA\\primetcc.hpappdir\\rt_aeabi.o",
        "C:\\DATA\\primetcc.hpappdir\\rt_math.o",
    ]


def compile_and_run(source_text=None, source_file=None):
    """compile source (text or file) with TCC on the calculator and run it."""
    p_log("--- primetcc: TCC on HP Prime ---")

    # if a previous run crashed, its stage marker + log were persisted
    if not _handle_stale_logs():
        return

    dbg = None
    loader = None
    cfg_b = None
    _run_ok = False
    _prog_ok = False   # the user program itself ran to completion
    STEP = "init"
    try:
        STEP = "debug interface"
        dbg = PrimeDebug()

        # 1. write the C source to code.c
        # NOTE: MicroPython file access uses RELATIVE paths (the Python app's
        # cwd is the app folder).  Only paths handed to the shellcode loader
        # use the absolute C:\\DATA\\... form (firmware fopen).
        if source_text is not None:
            code = source_text
        elif source_file is not None:
            with uio.FileIO(source_file, "rb") as f:
                code = decode_bytes(f.read())
        else:
            # read the markers from this file
            try:
                with uio.FileIO("main.py", "rb") as f:
                    txt = decode_bytes(f.read())
            except Exception:
                txt = ""
            # NOTE: use rfind, not find!  The marker strings also appear in
            # this very function's source (the txt.find calls below), so
            # find() matched those and produced a 31-byte garbage code.c
            # (verified on hardware: code.c was '")\n...end = txt.find("').
            # rfind picks the real markers at the end of this file.
            start = txt.rfind("/* PRIME-C-CODE-BEGIN */")
            end = txt.rfind("/* PRIME-C-CODE-END */")
            if start < 0 or end < 0:
                p_error("[-] no PRIME-C-CODE markers found")
                return
            code = txt[start + len("/* PRIME-C-CODE-BEGIN */"):end]
        with uio.FileIO("code.c", "wb") as f:
            f.write(code.encode("utf-8"))

        p_log("[*] source written to code.c")
        # remove any stale code.elf from a previous run so a failed
        # compile can never run the old program
        try:
            import os as _os
            _os.remove("code.elf")
        except Exception:
            try:
                uio.remove("code.elf")
            except Exception:
                pass
        STEP = "load tcc.elf"

        # 2. load TCC itself -- resident across runs when tcc.slot is valid
        loader = ShellcodeElfLoader(dbg)
        slot = _slot_load(dbg, loader)
        if slot is not None:
            entry, log_addr = slot
        else:
            if not loader.upload_loader():
                return
            entry, log_addr = loader.load_elf("tcc.elf")
            if not entry:
                p_error("[-] failed to load tcc.elf")
                return
            _slot_save(loader, log_addr)

        # 3. run TCC with the compile command line, streaming its log
        STEP = "run TCC"
        cfg_b = ConfigBuilder(dbg)
        cfg_addr = cfg_b.build(tcc_argv())
        p_log("[*] starting TCC...")
        # entry returns immediately; TCC runs on a firmware thread and
        # main.py polls the PRIMELOG ring until it sees TCC_DONE:<code>
        ret = dbg.call(entry, cfg_addr, 0)
        p_log("[+] entry returned: 0x{:08X}".format(ret))
        reader = LogReader(dbg, log_addr, color_fn=p_log, classify=True)
        t0 = hpprime.ticks()
        exit_code = None
        text = ""
        p_log("[*] streaming TCC output...")
        while True:
            chunk = reader.process()
            if chunk:
                text += chunk
                i = text.find("TCC_DONE:")
                if i >= 0:
                    rest = text[i + len("TCC_DONE:"):]
                    num = ""
                    for c in rest:
                        if c.isdigit():
                            num += c
                        else:
                            break
                    try:
                        exit_code = int(num) if num else 0
                    except Exception:
                        exit_code = 0
                    break
            if hpprime.ticks() - t0 > 120000:
                p_warning("\n[!] timeout waiting for TCC")
                break
            t = hpprime.ticks()
            while hpprime.ticks() - t < 20:
                pass
        if reader.pend.strip():
            try:
                reader.color_fn(reader.pend)
            except Exception:
                print(reader.pend)
        fin = "\n[+] TCC finished, exit code: {}".format(exit_code)
        if exit_code == 0:
            p_pass(fin)
        else:
            p_error(fin)
        if cfg_b:
            cfg_b.free_all()

        # 4. if the compile failed, STOP here (never run a stale program)
        if exit_code is None:
            p_error("[-] TCC did not finish (timeout); aborting")
            return
        if exit_code != 0:
            p_error("[-] compilation failed; not running any program")
            return
        try:
            with uio.FileIO("code.elf", "rb") as f:
                f.read(4)
            exists = True
        except Exception:
            exists = False
        if not exists:
            p_error("[-] code.elf was not produced; TCC failed")
            return
        # TCC emits R_ARM_ABS32 for references to non-static globals, which
        # the shellcode loader cannot resolve -- the first access crashed.
        # Fold the symbol values in and switch to R_ARM_RELATIVE instead.
        ElfTools.patch_shared_relocs("code.elf")

        STEP = "load code.elf"
        loader2 = ShellcodeElfLoader(dbg)
        if not loader2.upload_loader():
            return
        entry2, log_addr2 = loader2.load_elf("code.elf")
        if not entry2:
            p_error("[-] failed to load code.elf")
            return
        # locate the RESIDENT input-hook state inside tcc.elf ("PRIMEIN");
        # code.elf's hp_entry receives its address in r0 and hp_input.c
        # drives the shared queue from it.  Without it, input install fails.
        state_addr = ElfTools.find_magic_addr("tcc.elf", b"PRIMEIN",
                                              loader.loaded_elf_base)
        if state_addr == 0:
            p_error("[-] PRIMEIN input state not found in tcc.elf; "
                    "cannot install input hook")
            return
        if not INPUT_ENABLE:
            p_warning("[!] INPUT_ENABLE=False: running WITHOUT the input "
                      "hook (isolation test -- calc keys must still work)")
            state_addr = 0
        STEP = "run user program"
        p_log("[*] running user program (input state 0x{:08X})..."
              .format(state_addr))
        reader2 = LogReader(dbg, log_addr2, color_fn=p_out, classify=False)
        ret2 = dbg.call(entry2, state_addr, 0)
        # M0: Python regained control -- if this line is MISSING from
        # crash.log after a reboot, the crash happened between hp_entry's
        # 'bx lr' and here (firmware-side), never in the code below.
        _prog_ok = True     # dbg.call returned: the program completed
        _append_trace(b"M0 python-regained r0=0x%08X\n" % (ret2 & 0xFFFFFFFF))
        # drain the log ring fully (the ring lives inside code.elf)
        tail = ""
        for _ in range(16):
            chunk = reader2.process()
            if chunk:
                tail += chunk
            else:
                break
        if reader2.pend.strip():
            try:
                reader2.color_fn(reader2.pend)
            except Exception:
                print(reader2.pend)
        tail += reader2.pend
        # the debug interface reports 2 for ANY program; the real exit code
        # arrives via hp_entry's RT_RET:<n> log line
        real_ret = _parse_rt_ret(tail)
        if real_ret is not None:
            retline = "\n[+] user program returned: {} (RT_RET; debug interface said 0x{:08X})".format(
                real_ret, ret2)
            ok_code = real_ret
        else:
            retline = "\n[+] user program returned: 0x{:08X} (debug interface; no RT_RET seen)".format(ret2)
            ok_code = ret2
        if ok_code == 0:
            p_pass(retline)
        else:
            p_error(retline)
        # The input hook is RESIDENT in tcc.elf, so code.elf is ALWAYS safe
        # to free -- no leak-keep path, no in-flight-hook race anymore.
        try:
            loader2.unload()
            p_log("[+] code.elf freed (resident input hook)")
        except Exception as e:
            p_warning("[!] unload failed: %r" % (e,))
        _run_ok = True            # full success: clear stale trace files

    except KeyboardInterrupt:
        p_warning("\n[!] Interrupted")
    except Exception as e:
        p_error("[!!] error at step '%s': %r (type %s)" % (STEP, e, type(e).__name__))
        try:
            import sys as _sys
            _sys.print_exception(e)
        except Exception:
            pass
    finally:
        if not _prog_ok:
            _append_trace(b"M1 entering-finally\n")
        if cfg_b is not None:
            try:
                cfg_b.free_all()
            except Exception:
                pass
        if not _prog_ok:
            _append_trace(b"M2 cfg-freed\n")
        # tcc.elf is deliberately kept RESIDENT (tcc.slot) so repeated runs
        # don't churn the firmware heap; nothing to unload here.
        if not _prog_ok:
            _append_trace(b"M3 tcc-kept-resident\n")
        if dbg is not None:
            try:
                dbg.close()
            except Exception:
                pass
        if not _prog_ok:
            _append_trace(b"M4 dbg-closed\n")
        # LAST: on a fully successful run, drop the stale stage/tcc/crash
        # logs so the NEXT run does not show a bogus "previous crash trace"
        # (a crash/reboot leaves them for diagnosis).
        if _run_ok:
            _clear_trace_files()
        elif _prog_ok:
            _remove_file("crash.log")   # program finished; no crash to keep
        p_pass("--- done ---")


# ---------------------------------------------------------------------------
# default program: edit the C source between the markers
# ---------------------------------------------------------------------------
def main():
    # clear the PPL terminal so every run starts from a clean console
    # (PPL print() with no arguments wipes the terminal output area)
    try:
        hpprime.eval('print()')
    except Exception:
        pass
    compile_and_run()


# Autorun on `import main` (the calculator Python app has no __main__).
# PRIMETCC_NO_AUTORUN=1 skips it so host-side tests can import the helpers
# (the calculator has no os.environ, so the try/except keeps autorun on).
_AUTORUN = True
try:
    import os as _os0
    if _os0.environ.get("PRIMETCC_NO_AUTORUN"):
        _AUTORUN = False
except Exception:
    pass

if _AUTORUN:
    main()

"""







/* PRIME-C-CODE-BEGIN */
#include "prime.h"

/* Write your program here, then run this Python app.
 * (Full demos live on the host under examples/: gui, ball, mandel, ...) */

int main(void) {
    return 0;
}
/* PRIME-C-CODE-END */







"""
