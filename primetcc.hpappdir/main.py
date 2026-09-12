"""
main.py —— primetcc（HP Prime 上的 TCC）计算器端启动器。

在计算器（MicroPython）上运行：
    >>> import main

流程：
  1. 从本文件读取 C 源码（PRIME-C-CODE 标记之间），或从
     `main.compile_file("test.c")` 指定的文件读取。
  2. 写入 C:\\DATA\\primetcc.hpappdir\\code.c
  3. 用 shellcode 加载器装载 puredoom 风格的 tcc.elf，并以配置
     {magic, argc, argv} 调用其入口，使 TCC 把
         code.c  ->  code.elf
     （如今在计算器上只编译用户源码；运行时
     hp_rt/hp_gfx/hp_input/hp_math/hp_string 已预编译为 rt_core.o，
     并与 rt_svc.o / rt_aeabi.o / rt_math.o 一起链接）。
  4. TCC 运行期间流式回显其 PRIMELOG 输出。
  5. 若产出了 code.elf，则加载并运行它（入口 hp_entry，纯透传到
     main()），并打印其 PRIMELOG 输出与返回值。code.elf 故意不在退出
     时释放：OS UI 线程随时可能阻塞在输入钩子里，释放会导致下次按键
     时计算器崩溃（已硬件验证）。

固件说明（HP Prime G1）：
  * 系统调用经 push{r0}; push{lr}; svc N（处理程序经压栈的 LR 返回）；
    同一约定见 DOOM/PureDOOM 移植。
  * 固件 API 表基址 0x307FBCAC（id 0x10037 = malloc，0x1003a = free）。
"""
import ustruct as struct
import uio
import hpprime

# 彩色控制台辅助（moreprint.py，用户提供）。在宿主 / moreprint 缺失时
# 退回普通 print，使一切仍可工作。
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
    """MicroPython 的 bytes.decode 可能不支持 errors= 参数。"""
    try:
        return b.decode("utf-8")
    except Exception:
        return "".join(chr(x) for x in b)

# ---------------------------------------------------------------------------
# 固件调试接口 + shellcode ELF 加载器（与 DOOM 移植相同）
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
        """读取 ELF 头，算出映像总大小（max p_vaddr+p_memsz）"""
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
        """把 TCC 为非 static 文件作用域变量引用生成的符号型重定位
        （R_ARM_ABS32=2 / REL32=3）转换为 R_ARM_RELATIVE（23），并把符号值
        折入 addend。

        计算器上的 shellcode 加载器（以及模拟器）只应用 R_ARM_RELATIVE；
        符号型条目会被静默跳过，于是保存 &global 的字面量保持为 0，首次
        访问即崩溃（现象：'int board[8];' 会让计算器重启，而
        'static int board[8];' 正常）。
        ARM ABS32：final = S + A。RELATIVE：final = base + word。
        把 S 折进该字（word += st_value）并切换类型，加载器就会恰好施加
        base + S + A。逐字节精确：只改写被触及的条目/字（code.elf 约
        200KB）。"""
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
                if rtype not in (2, 3):      # 仅 ABS32 / REL32
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
                    # 固件拒绝更新模式：重写整个文件
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
        """在已加载的映像中定位魔数字符串，按 4KB 分块读取 ELF
        （不整读文件；只用相对路径）。运行时地址 =
        base + p_vaddr + (magic_file_offset - p_offset)。"""
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
                # 以 7 字节重叠分块扫描，适配 8 字节魔数
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
        """在已加载的映像中定位 PRIMELOG 环。"""
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
        """上传 shellcode 加载器，然后把 ELF 载入 malloc 的缓冲。
        返回 (entry_point, log_ring_addr)。"""
        mem_size = ElfTools.get_elf_memory_size(filename)
        p_log("[*] ELF requires memory: {} bytes".format(mem_size))
        if mem_size == 0:
            return 0, 0
        self.loaded_elf_size = mem_size
        # 关键：固件 malloc 只保证 4 字节对齐，而映像包含用 LDRD/STRD
        # 访问的 8 字节对齐数据（栈顶、long long / double 全局变量）。
        # ARM926EJ-S 上非对齐双字访问会 trap，因此把映像基址对齐到 8
        # （保留原始指针供 free() 使用）。
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
            # MicroPython 无法打开 C:\... 绝对路径；传相对文件名
            # （与本文件里其它 uio.FileIO 同样的规则）
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
# PRIMELOG 流式回显
# ---------------------------------------------------------------------------
class LogReader:
    """把 C 侧的 PRIMELOG 环（魔数 "PRIMELOG"，int count，
    char data[RING]）流式回显到控制台。color_fn 选择文本颜色
    （p_log = 灰色信息，p_out = 蓝色用户输出）；classify 把 TCC
    编译器错误/警告行标为红/橙。"""
    def __init__(self, dbg, log_addr, color_fn=p_log, classify=False):
        self.dbg = dbg
        self.addr = log_addr
        self.local = 0
        self.ring = 32768
        self.pend = ""     # 彩色流式回显的部分行缓冲
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
            # 流式输出完整行并上色；部分行留待下次
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
# TCC 的配置（argc/argv），与 C 侧期望的结构相同：
#   struct hp_config { unsigned magic; int argc; char **argv;
#                      unsigned env_count; char **envs; }  magic = 0xD00BC760
# ---------------------------------------------------------------------------
CONFIG_MAGIC = 0xD00BC760
RING = 32768  # 必须与 hp_libc.h 的环大小一致

# 机上调隔离开关：为 False 时 code.elf 以 input state = 0 运行，
# hp_input_install() 失败，钩子永不装配。若在此模式下计算器自身的按键
# 仍不工作，说明 OS 输入循环被早前一次损坏的构建卡住了，需要硬重启
# （拔电池 / 复位孔）——没有软件能解开它。
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
# 真实退出码上报：无论 main() 返回什么，固件调试接口都报告 2；
# 因此 hp_entry 把真值以 "RT_RET:<n>" 写入 PRIMELOG 环，我们在此解析。
# ---------------------------------------------------------------------------
def _parse_rt_ret(text):
    """取出 hp_entry 以 RT_RET:<n> 记录的真实退出码。"""
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
# 常驻 TCC（tcc.slot）：把 ~675KB 的 tcc.elf 映像 + shellcode 加载器在多次
# 运行间保留在固件内存中，使反复的“编译+运行”不再抖动固件堆（README 中
# 的“跑 5-9 次后崩溃”正是这种抖动：每次运行在小的共享堆上
# malloc/free 约 900KB）。
#
# 槽文件（20 字节，<IIIII）：loader_addr, base, size, entry_point, log_addr。
# 重启或堆复用会使常驻映像失效，因此复用前我们校验 shellcode 加载器的
# 第一条指令、base 处的 ELF 魔数，以及常驻映像大小与磁盘上的 tcc.elf
# 一致（重新部署后大小不同的 tcc.elf 绝不能被跳过——例如带常驻钩子的
# 构建比上一个大了 3KB）。
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
    """复用上一次运行的常驻 tcc.elf，或返回 None 表示重新加载
    （随后保存槽）。"""
    try:
        with uio.FileIO(TCC_SLOT, "rb") as f:
            b = f.read(20)
    except Exception:
        return None                      # 尚无槽：首次运行
    try:
        if len(b) < 20:
            return None
        la, base, size, entry, log_addr = struct.unpack("<IIIII", b)
        if min(la, base, entry, log_addr) < 0x30000000:
            return None
        if size != _tcc_file_size():     # 磁盘上的 tcc.elf 大小已变
            return None
        if dbg.read_mem(la, 4) != b"\x0b\x00\x00\xea":  # b +0x2c (loader)
            return None
        if dbg.read_mem(base, 4) != b"\x7fELF":          # ELF magic
            return None
        loader.loader_addr = la
        loader.loaded_elf_raw = 0       # 不要释放外部指针
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
    """删除 tcc.slot：下次运行会重新分配并重新加载 tcc.elf。
    （旧的常驻映像会留在固件内存里直到计算器复位——删槽只是阻止它
    再被复用。）"""
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


# C 运行时把诊断写到应用目录的绝对路径
# （rt/hp_rt.c 的 diag_log：C:\DATA\primetcc.hpappdir\crash.log）。真机上
# MicroPython 应用的 CWD 是父目录（C:\DATA），因此纯相对名（"crash.log"）
# 会静默命中另一个不存在的文件，导致旧日志从未被清理/读取/追加。
# 两种写法都做；优先绝对路径。
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
    """向 crash.log 持久追加一行标记。C 运行时的 diag_log 会把每一步
    追加到那里；这些 M 标记记录 MicroPython 侧在程序之后重新获得控制权。
    先尝试 'ab'；固件若拒绝则退回读+重写。"""
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
    """一次完全成功的运行会让 stage.txt / tcc.log / crash.log 留下陈旧
    内容；否则下一次运行会把它当成子虚乌有的“上次崩溃痕迹”展示，哪怕
    什么都没崩。仅在干净、完整的一次运行后清理——崩溃/重启会把它们
    留下供诊断。"""
    _remove_file("stage.txt")
    _remove_file("tcc.log")
    _remove_file("crash.log")


def _read_any(name):
    """读取一个 trace 文件，先试运行时写入的应用目录绝对路径
    （C 运行时写在那里），回退到相对名。"""
    for p in (TRACE_DIR + "\\" + name, name):
        try:
            with uio.FileIO(p, "rb") as f:
                return f.read()
        except Exception:
            pass
    return b""


def _trace_logs_exist():
    """读取上一次（未完成）运行留下的 trace 文件并展示。
    任一文件有内容则返回 True。"""
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
    # crash.log：C 运行时（diag_log）把每个完成的步骤持久追加到这里
    # （逐行重写并关闭）；main.py 只追加自己的 M1..M4 标记，因此崩溃+重启
    # 后能同时看到运行轨迹和崩溃位置。
    # （这里用 "wb" 会截断运行时留下的轨迹——真机上只见到 "M4 dbg-closed"。）
    cr = _read_any("crash.log")
    if cr:
        have = True
        p_warning("--- last crash.log step: %s ---" %
                  decode_bytes(cr).strip())
    return have


def _handle_stale_logs():
    """崩溃闸门：若上一次运行留下了 trace 日志，在编译前停下，让用户
    先读它们——重新编译同一个会崩溃的程序会再次崩溃并覆盖/刷新日志，
    使其无法阅读。用户答 y（删除日志并编译）或其它（保留日志，不编译）。
    返回 True 表示继续，False 表示放弃本次运行。"""
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
# 计算器上使用的 TCC 命令行
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
    """用计算器上的 TCC 编译源码（文本或文件）并运行。"""
    p_log("--- primetcc: TCC on HP Prime ---")

    # 若上一次运行崩溃，其阶段标记 + 日志会被持久留下
    if not _handle_stale_logs():
        return

    dbg = None
    loader = None
    cfg_b = None
    _run_ok = False
    _prog_ok = False   # 用户程序本身是否完整跑完
    STEP = "init"
    try:
        STEP = "debug interface"
        dbg = PrimeDebug()

        # 1. 把 C 源码写入 code.c
        # 注意：MicroPython 的文件访问使用相对路径（Python 应用的 cwd 是
        # 应用文件夹）。只有递给 shellcode 加载器的路径才用绝对的
        # C:\\DATA\\... 形式（固件 fopen）。
        if source_text is not None:
            code = source_text
        elif source_file is not None:
            with uio.FileIO(source_file, "rb") as f:
                code = decode_bytes(f.read())
        else:
            # 从本文件读取标记段
            try:
                with uio.FileIO("main.py", "rb") as f:
                    txt = decode_bytes(f.read())
            except Exception:
                txt = ""
            # 注意：必须用 rfind，不能用 find！标记字符串也出现在这个函数
            # 自己的源码里（下面的 txt.find 调用），所以 find() 会匹配到
            # 它们并产生 31 字节的垃圾 code.c
            # （已硬件验证：code.c 变成 '")\n...end = txt.find("'）。
            # rfind 会选中本文件末尾的真正标记。
            start = txt.rfind("/* PRIME-C-CODE-BEGIN */")
            end = txt.rfind("/* PRIME-C-CODE-END */")
            if start < 0 or end < 0:
                p_error("[-] no PRIME-C-CODE markers found")
                return
            code = txt[start + len("/* PRIME-C-CODE-BEGIN */"):end]
        with uio.FileIO("code.c", "wb") as f:
            f.write(code.encode("utf-8"))

        p_log("[*] source written to code.c")
        # 删除上一次运行遗留的 code.elf，使失败的编译
        # 绝不会运行到旧程序
        try:
            import os as _os
            _os.remove("code.elf")
        except Exception:
            try:
                uio.remove("code.elf")
            except Exception:
                pass
        STEP = "load tcc.elf"

        # 2. 加载 TCC 本体——tcc.slot 有效时跨运行常驻
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

        # 3. 用编译命令行运行 TCC，并流式回显其日志
        STEP = "run TCC"
        cfg_b = ConfigBuilder(dbg)
        cfg_addr = cfg_b.build(tcc_argv())
        p_log("[*] starting TCC...")
        # 入口立即返回；TCC 在固件线程上运行，
        # main.py 轮询 PRIMELOG 环直到看到 TCC_DONE:<code>
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

        # 4. 若编译失败，就停在这里（绝不运行陈旧的程序）
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
        # TCC 对非 static 全局变量的引用会发出 R_ARM_ABS32，shellcode
        # 加载器无法解析——首次访问就崩溃。把符号值折入，改换
        # R_ARM_RELATIVE。
        ElfTools.patch_shared_relocs("code.elf")

        STEP = "load code.elf"
        loader2 = ShellcodeElfLoader(dbg)
        if not loader2.upload_loader():
            return
        entry2, log_addr2 = loader2.load_elf("code.elf")
        if not entry2:
            p_error("[-] failed to load code.elf")
            return
        # 在 tcc.elf 中定位常驻输入钩子状态（"PRIMEIN"）；
        # code.elf 的 hp_entry 在 r0 收到其地址，hp_input.c 据此驱动共享
        # 队列。没有它，输入装配会失败。
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
        # M0：Python 重新获得控制权——若重启后 crash.log 中缺少这行，
        # 说明崩溃发生在 hp_entry 的 'bx lr' 与这里之间（固件侧），
        # 而不是下面的代码。
        _prog_ok = True     # dbg.call 已返回：程序完整跑完
        _append_trace(b"M0 python-regained r0=0x%08X\n" % (ret2 & 0xFFFFFFFF))
        # 把日志环抽干（环位于 code.elf 内）
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
        # 调试接口对任意程序都报告 2；真实退出码
        # 经 hp_entry 的 RT_RET:<n> 日志行传来
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
        # 输入钩子常驻在 tcc.elf 中，因此 code.elf 总是可以安全释放——
        # 不再有泄漏保留路径，也没有钩子在途的竞态。
        try:
            loader2.unload()
            p_log("[+] code.elf freed (resident input hook)")
        except Exception as e:
            p_warning("[!] unload failed: %r" % (e,))
        _run_ok = True            # 完全成功：清理陈旧的 trace 文件

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
        # tcc.elf 故意保持常驻（tcc.slot），使反复运行
        # 不再抖动固件堆；这里无需卸载。
        if not _prog_ok:
            _append_trace(b"M3 tcc-kept-resident\n")
        if dbg is not None:
            try:
                dbg.close()
            except Exception:
                pass
        if not _prog_ok:
            _append_trace(b"M4 dbg-closed\n")
        # 最后：完全成功的一次运行后，丢弃陈旧的 stage/tcc/crash
        # 日志，使下一次运行不显示子虚乌有的“上次崩溃痕迹”
        # （崩溃/重启会把它们留下供诊断）。
        if _run_ok:
            _clear_trace_files()
        elif _prog_ok:
            _remove_file("crash.log")   # 程序已结束；没有崩溃需要保留
        p_pass("--- done ---")


# ---------------------------------------------------------------------------
# 默认程序：在标记之间编辑 C 源码
# ---------------------------------------------------------------------------
def main():
    # 清空 PPL 终端，使每次运行都从干净的控制台开始
    # （无参数的 PPL print() 会抹掉终端输出区）
    try:
        hpprime.eval('print()')
    except Exception:
        pass
    compile_and_run()


# `import main` 时自动运行（计算器的 Python 应用没有 __main__）。
# PRIMETCC_NO_AUTORUN=1 可跳过，供宿主侧测试导入这些辅助函数
# （计算器没有 os.environ，故用 try/except 保持自动运行开启）。
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

/* 在这里写你的程序，然后运行这个 Python 应用。
 * （完整演示在宿主的 examples/ 下：gui、ball、mandel、...） */

int main(void) {
    return 0;
}
/* PRIME-C-CODE-END */







"""
