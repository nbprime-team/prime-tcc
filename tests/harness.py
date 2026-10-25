#!/usr/bin/env python3
# harness.py -- host-side end-to-end test of the HP Prime TCC port.
#
# 1. Plays the calculator's C:\DATA\primetcc.hpappdir directory on the host.
# 2. Loads tcc.elf into the ARM emulator (same way the shellcode loader
#    does on the calculator), passes it a config with argc/argv so that
#    TCC compiles code.c (+ rt/hp_rt.c, rt_svc.o, rt_aeabi.o) into
#    code.elf with the exact command line main.py would use.
# 3. Loads code.elf into a fresh emulator, runs it, and prints its
#    PRIMELOG output and return value.
#
# Usage: python3 tests/harness.py [testname]
import os
import shutil
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
# PRIMETCC_FAKE lets parallel runs isolate their fake C:\DATA tree
# (shared fake_cdata corrupted concurrent batches).
FAKE = os.environ.get('PRIMETCC_FAKE') or \
    os.path.join(HERE, 'fake_cdata', 'primetcc.hpappdir')

sys.path.insert(0, HERE)
import emu_arm2
from emu_arm2 import ARMEmu, BASE

emu_arm2.FAKE_ROOT = FAKE

TCC_ELF = os.path.join(TOP, 'tcc.elf')


def make_fake_fs():
    # flat layout: the calculator does not support subdirectories
    shutil.rmtree(os.path.dirname(FAKE), ignore_errors=True)
    os.makedirs(FAKE, exist_ok=True)
    # only the user's code.c is TCC-compiled on the calc now; the runtime
    # is prebuilt (rt_core.o) and the headers stay for user #includes
    shutil.copy(os.path.join(TOP, 'rt', 'hp_gfx.h'), os.path.join(FAKE, 'hp_gfx.h'))
    shutil.copy(os.path.join(TOP, 'rt', 'hp_input.h'), os.path.join(FAKE, 'hp_input.h'))
    shutil.copy(os.path.join(TOP, 'rt', 'hp_math.h'), os.path.join(FAKE, 'hp_math.h'))
    shutil.copy(os.path.join(TOP, 'rt', 'hp_string.h'), os.path.join(FAKE, 'hp_string.h'))
    shutil.copy(os.path.join(TOP, 'rt', 'hp_fonts.h'), os.path.join(FAKE, 'hp_fonts.h'))
    shutil.copy(os.path.join(TOP, 'rt', 'hp_sys.h'), os.path.join(FAKE, 'hp_sys.h'))
    shutil.copy(os.path.join(TOP, 'rt', 'hp_fixmath.h'), os.path.join(FAKE, 'hp_fixmath.h'))
    shutil.copy(os.path.join(TOP, 'rt', 'hp_random.h'), os.path.join(FAKE, 'hp_random.h'))
    shutil.copy(os.path.join(TOP, 'rt', 'hp_codec.h'), os.path.join(FAKE, 'hp_codec.h'))
    shutil.copy(os.path.join(TOP, 'rt', 'hp_gui.h'), os.path.join(FAKE, 'hp_gui.h'))
    shutil.copy(os.path.join(TOP, 'rt_core.o'), os.path.join(FAKE, 'rt_core.o'))
    shutil.copy(os.path.join(TOP, 'rt_math.o'), os.path.join(FAKE, 'rt_math.o'))
    shutil.copy(os.path.join(TOP, 'rt_svc.o'), os.path.join(FAKE, 'rt_svc.o'))
    shutil.copy(os.path.join(TOP, 'rt_aeabi.o'), os.path.join(FAKE, 'rt_aeabi.o'))
    shutil.copy(os.path.join(TOP, 'hp', 'prime.h'), os.path.join(FAKE, 'prime.h'))
    shutil.copy(os.path.join(TOP, 'hp', 'stdbool.h'), os.path.join(FAKE, 'stdbool.h'))
    if os.environ.get('OLD_FLOW'):
        # pre-rt_core.o baseline: TCC compiles the runtime sources too
        for f in ('hp_rt.c', 'hp_gfx.c', 'hp_input.c', 'hp_math.c', 'hp_string.c',
                    'hp_fixmath.c', 'hp_random.c', 'hp_codec.c', 'hp_gui.c'):
            shutil.copy(os.path.join(TOP, 'rt', f), os.path.join(FAKE, f))


def write_config(emu, argv):
    """Build {magic, argc, argv, env_count=0, envs=0} in emu memory."""
    # strings
    addrs = []
    for s in argv:
        b = s.encode('latin1') + b'\x00'
        a = emu.fw.next_heap
        emu.mem[a - BASE:a - BASE + len(b)] = b
        emu.fw.next_heap = (a + len(b) + 3) & ~3
        addrs.append(a)
    # argv array
    arr = b''.join(struct.pack('<I', a) for a in addrs)
    arr_a = emu.fw.next_heap
    emu.mem[arr_a - BASE:arr_a - BASE + len(arr)] = arr
    emu.fw.next_heap = (arr_a + len(arr) + 3) & ~3
    # config
    cfg = struct.pack('<IIIII', 0xD00BC760, len(argv), arr_a, 0, 0)
    cfg_a = emu.fw.next_heap
    emu.mem[cfg_a - BASE:cfg_a - BASE + len(cfg)] = cfg
    emu.fw.next_heap = (cfg_a + len(cfg) + 3) & ~3
    return cfg_a


def run_elf(elf_path, argv, label, max_insn=None, inject=None):
    elf = open(elf_path, 'rb').read()
    emu = ARMEmu()
    if inject:
        for e in inject:
            if e[0] == 'key':
                emu.fw.inject_key(e[1], e[2])
            else:
                emu.fw.inject_touch(e[1], e[2], e[3])
    if max_insn:
        emu.max_insn = max_insn
    entry = emu.load_elf(elf, BASE)
    log = emu.find_primerlog()
    if not log:
        print('[%s] PRIMELOG ring not found!' % label)
        return None, None, emu
    cfg = write_config(emu, argv)
    t0 = time.time()
    ret = emu.run(entry, cfg)
    dt = time.time() - t0
    out = b''.join(emu.out).decode('latin1', 'replace')
    print('[%s] ran %.1fs, %d instructions, return 0x%08X' %
          (label, dt, emu.insn_count, ret))
    print('[%s] --- output ---' % label)
    print(out)
    print('[%s] --- end ---' % label)
    return ret, out, emu


USER_BASE = BASE + 0x200000   # code.elf lives here, next to resident tcc.elf


def run_user(elf_path, inject=None, max_insn=500000000):
    """Run a compiled code.elf the way the calculator does now: tcc.elf is
    loaded FIRST into the same emulator (it hosts the RESIDENT input hook
    service, found by the PRIMEIN magic) and code.elf runs with r0 = the
    PRIMEIN state address (hp_entry forwards it to hp_input.c)."""
    label = 'user'
    emu = ARMEmu()
    tcc = open(TCC_ELF, 'rb').read()
    emu.load_elf(tcc, BASE)                      # resident hook service
    state = emu.find_magic(b'PRIMEIN')
    if state is None:
        print('[%s] PRIMEIN input state not found in tcc.elf!' % label)
        return None, None, emu
    code = open(elf_path, 'rb').read()
    entry = emu.load_elf(code, USER_BASE)
    log = emu.find_magic(b'PRIMELOG', USER_BASE)
    if not log:
        print('[%s] PRIMELOG ring not found in code.elf!' % label)
        return None, None, emu
    emu.log_addr = log
    emu.drained = emu.rd32(log + 8)
    if inject:
        for e in inject:
            if e[0] == 'key':
                emu.fw.inject_key(e[1], e[2])
            else:
                emu.fw.inject_touch(e[1], e[2], e[3])
    if max_insn:
        emu.max_insn = max_insn
    t0 = time.time()
    ret = emu.run(entry, state, base=USER_BASE)
    dt = time.time() - t0
    out = b''.join(emu.out).decode('latin1', 'replace')
    print('[%s] ran %.1fs, %d instructions, return 0x%08X (state 0x%08X)' %
          (label, dt, emu.insn_count, ret, state))
    print('[%s] --- output ---' % label)
    print(out)
    print('[%s] --- end ---' % label)
    return ret, out, emu


def main():
    test = sys.argv[1] if len(sys.argv) > 1 else 'hello'
    make_fake_fs()

    tests = {
        'varg': r'''
#include "prime.h"
int main(void) {
    char buf[96];
    int ok = 1;
    /* 1..8 values after the format string (variadic printf macros) */
    printf("v1 %d\n", 1);
    printf("v2 %d %x\n", 2, 0x1F);
    printf("v3 %d %x %s\n", 3, 0x2F, "abc");
    printf("v4 %d %d %d %d\n", 4, 5, 6, 7);
    printf("v5 %d %d %d %d %d\n", 1, 2, 3, 4, 5);
    printf("v6 %d %d %d %d %d %d\n", 1, 2, 3, 4, 5, 6);
    printf("v7 %d %d %d %d %d %d %d\n", 1, 2, 3, 4, 5, 6, 7);
    printf("v8 %d %d %d %d %d %d %d %d\n", 1, 2, 3, 4, 5, 6, 7, 8);
    printf("neg %d %c %p\n", -42, 'Z', (unsigned long)buf);
    printf("w %04x %-4d| %+d\n", 15, 42, 7);
    ok = ok && sprintf(buf, "s1 %d+%d=%d", 10, 20, 30) > 0;
    printf("s %s\n", (unsigned long)buf);
    ok = ok && sprintf(buf, "s2 %x %c", 0xAB, 'Q') > 0;
    printf("s2 %s\n", (unsigned long)buf);
    /* backward-compat: OLD fixed-4-arg style with trailing zeros must
     * still work (it goes through the variadic macros unchanged) */
    sprintf(buf, "%s", (unsigned long)(ok ? "ok" : "FAIL"), 0, 0, 0);
    printf("legacy-s %s\n", (unsigned long)buf);
    sprintf(buf, "n=%lu max=%lx", 12345UL, 0xDEADUL, 0, 0);
    printf("legacy-n %s\n", (unsigned long)buf);
    printf("legacy-p %d %x\n", 7, 0x2A, 0, 0, 0, 0);
    printf("VARG %s\n", ok ? "OK" : "FAIL");
    return ok ? 0 : 1;
}
''',
        'varg2': r'''
#include "prime.h"
#define OBJ 42
#define DBL(x) ((x) * 2)
#define VA(...) (__VA_ARGS__)
int main(void) {
    printd(OBJ); prints("\n");
    printd(DBL(21)); prints("\n");
    printd(VA(7)); prints("\n");
    return 0;
}
''',
        'cordic': r'''
#include "prime.h"
#define FXK 65536
static const int atan_tbl[16] = { 51472, 30386, 16055, 8150, 4091, 2047,
                                  1024, 512, 256, 128, 64, 32, 16, 8, 4, 2 };
static int cordic(int y, int x)
{
    int z = 0, i;
    for (i = 0; i < 16; i++) {
        int d = (y >= 0) ? 1 : -1;
        int tx = x >> i;
        x += d * (y >> i);
        y -= d * tx;
        z += (d > 0) ? atan_tbl[i] : -atan_tbl[i];
    }
    return z;
}
int main(void) {
    int r = cordic(FXK, FXK);
    printf("CORDIC %d\n", r);
    return (r > 51000 && r < 52000) ? 0 : 1;
}
''',
        'fix': r'''
#include "prime.h"
#include "hp_fixmath.h"
static int near(hp_fx a, hp_fx b, hp_fx eps)
{
    hp_fx d = a - b;
    if (d < 0) d = -d;
    return d <= eps;
}
int main(void) {
    int ok = 1, i;
    hp_fx eps = 100;                        /* ~0.0015 */
    ok = ok && hp_fx_trunc(hp_fx_int(7)) == 7;
    ok = ok && hp_fx_round(hp_fx_from_double(3.25)) == 3;
    ok = ok && near(hp_fx_mul(hp_fx_int(3), hp_fx_int(4)), hp_fx_int(12), 0);
    ok = ok && near(hp_fx_div(hp_fx_int(7), hp_fx_int(2)),
                    hp_fx_from_double(3.5), 1);
    ok = ok && near(hp_fx_sqrt(hp_fx_int(4)), hp_fx_int(2), eps);
    ok = ok && near(hp_fx_sqrt(hp_fx_int(2)), hp_fx_from_double(1.4142), eps);
    ok = ok && near(hp_fx_sin(HP_FX_PI_2), hp_fx_int(1), eps);
    ok = ok && near(hp_fx_cos(0), hp_fx_int(1), eps);
    ok = ok && near(hp_fx_sin(HP_FX_PI), 0, eps);
    ok = ok && near(hp_fx_atan2(hp_fx_int(1), hp_fx_int(1)), HP_FX_PI_4, eps);
    ok = ok && near(hp_fx_atan2(hp_fx_int(-1), hp_fx_int(-1)),
                    -HP_FX_PI + HP_FX_PI_4, eps);
    ok = ok && hp_fx_trunc(hp_fx_atan2(hp_fx_int(-1), 0)) ==
               -hp_fx_trunc(HP_FX_PI_2);
    for (i = 0; i < 16; i++) {              /* sin^2 + cos^2 == 1 */
        hp_fx a = hp_fx_mul(hp_fx_int(i), HP_FX_PI_4);
        hp_fx s = hp_fx_sin(a), c = hp_fx_cos(a);
        ok = ok && near(hp_fx_add(hp_fx_mul(s, s), hp_fx_mul(c, c)),
                        hp_fx_int(1), 2 * eps);
    }
    printf("FIX %s\n", ok ? "OK" : "FAIL");
    return ok ? 0 : 1;
}
''',
        'rng': r'''
#include "prime.h"
#include "hp_random.h"
int main(void) {
    hp_rng r1, r2;
    int ok = 1, i, lo = 1000, hi = -1000;
    hp_fx n1, n2;
    hp_rng_seed(&r1, 42); hp_rng_seed(&r2, 42);
    ok = ok && hp_rng_u32(&r1) == hp_rng_u32(&r2);   /* deterministic */
    ok = ok && hp_rng_u32(&r1) == hp_rng_u32(&r2);
    hp_rng_seed(&r1, 1); hp_rng_seed(&r2, 2);
    ok = ok && hp_rng_u32(&r1) != hp_rng_u32(&r2);   /* seeds differ */
    hp_rng_seed(&r1, 99);
    for (i = 0; i < 200; i++) {
        int v = hp_rng_range(&r1, -5, 5);
        if (v < -5 || v > 5) ok = 0;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
    }
    ok = ok && lo <= -3 && hi >= 3;                  /* spread */
    n1 = hp_noise2_fx(hp_fx_int(3), hp_fx_int(4), 7);
    n2 = hp_noise2_fx(hp_fx_int(3), hp_fx_int(4), 7);
    ok = ok && n1 == n2 && n1 >= 0 && n1 < HP_FX_ONE;
    printf("RNG lo=%d hi=%d %s\n", lo, hi, ok ? "OK" : "FAIL");
    return ok ? 0 : 1;
}
''',
        'codec': r'''
#include "prime.h"
#include "hp_codec.h"
int main(void) {
    char buf[64];
    unsigned char dec[32];
    int ok = 1, n;
    ok = ok && hp_crc32("123456789", 9) == 0xCBF43926u;
    ok = ok && hp_adler32("Wikipedia", 9) == 0x11E60398u;
    n = hp_hex_encode(buf, "\x01\xAB\xFF", 3);
    ok = ok && n == 6 && strcmp(buf, "01abff") == 0;
    ok = ok && hp_hex_decode(dec, "01abff", 6) == 3 &&
          dec[0] == 1 && dec[1] == 0xAB && dec[2] == 0xFF;
    n = hp_b64_encode(buf, "hello", 5);
    ok = ok && n == 8 && strcmp(buf, "aGVsbG8=") == 0;
    ok = ok && hp_b64_decode(dec, "aGVsbG8=", 8) == 5 &&
          memcmp(dec, "hello", 5) == 0;
    ok = ok && hp_b64_encode(buf, "Man", 3) == 4 && strcmp(buf, "TWFu") == 0;
    ok = ok && hp_b64_decode(dec, "TWFu", 4) == 3 && memcmp(dec, "Man", 3) == 0;
    ok = ok && hp_b64_decode(dec, "aGVs!!", 8) == -1;   /* invalid char */
    ok = ok && hp_hex_decode(dec, "zz", 2) == -1;
    printf("CODEC %s\n", ok ? "OK" : "FAIL");
    return ok ? 0 : 1;
}
''',
        'libc': r'''
#include "prime.h"
#include "hp_string.h"
static int cmp_int(const void *a, const void *b)
{
    int x = *(const int *)a, y = *(const int *)b;
    return x < y ? -1 : (x > y ? 1 : 0);
}
int main(void) {
    char *end;
    double d;
    int ok = 1, i;
    int a[7] = { 5, 2, 8, 1, 9, 3, 7 };
    int key;
    d = strtod("3.25", &end);
    ok = ok && d > 3.2499 && d < 3.2501;
    ok = ok && strtod("-1e3", &end) == -1000.0;
    d = strtod("12.5e-2", &end);
    ok = ok && d > 0.12499 && d < 0.12501;
    ok = ok && strtod("  42abc", &end) == 42.0 && *end == 'a';
    ok = ok && strtod("xyz", &end) == 0.0 && *end == 'x';
    ok = ok && atof("0.5") == 0.5;
    ok = ok && strtod("inf", 0) > 1e100;   /* TCC parses 1e300 slightly
                                              differently than GCC: compare
                                              with a tolerant bound */
    qsort(a, 7, sizeof(int), cmp_int);
    for (i = 0; i < 6; i++) ok = ok && a[i] <= a[i + 1];
    ok = ok && a[0] == 1 && a[6] == 9;
    ok = ok && bsearch(a + 3, a, 7, sizeof(int), cmp_int) != 0;  /* 5 */
    key = 11;
    ok = ok && bsearch(&key, a, 7, sizeof(int), cmp_int) == 0;   /* absent */
    ok = ok && abs(-5) == 5 && labs(-123456L) == 123456L;
    printf("LIBC %s\n", ok ? "OK" : "FAIL");
    return ok ? 0 : 1;
}
''',
        'gfxtest': open(os.path.join(TOP, 'examples', 'gfxtest.c')).read(),
        'hello': r'''
#include "prime.h"
int fib(int n) { return n < 2 ? n : fib(n-1) + fib(n-2); }
int main(void) {
    printf("hello from TCC on HP Prime!\n");
    printf("fib(15) = %d\n", fib(15));
    return fib(15) == 610 ? 0 : 1;
}
''',
        'struct': r'''
#include "prime.h"
/* NOTE: TCC's ARM backend has no struct-by-value return (use pointers) */
struct point { int x, y; };
void mk(struct point *p, int x, int y) { p->x = x; p->y = y; }
int main(void) {
    struct point p;
    mk(&p, 3, 4);
    printf("point = (%d, %d)\n", p.x, p.y, 0, 0);
    return (p.x == 3 && p.y == 4) ? 0 : 1;
}
''',
        'str': r'''
#include "prime.h"
int main(void) {
    char buf[64];
    int i;
    sprintf(buf, "sum=%d", 1 + 2 + 3);
    printf("%s\n", (unsigned long)buf);
    for (i = 0; i < 5; i++) printx('A' + i);
    prints("\n");
    return 0;
}
''',
        'float': r'''
#include "prime.h"
double f(double x) { return x * 2.5 + 1.0; }
float  h(float x)  { return x * 0.5f + 1.0f; }
int main(void) {
    double d = f(3.0);      /* 3.0*2.5+1.0 = 8.5 */
    float  y = h(4.0f);     /* 4.0*0.5+1.0 = 3.0 */
    int    k = (int)d;      /* double -> int conversion */
    if (d > 8.4 && d < 8.6 && y > 2.9f && y < 3.1f && k == 8) {
        prints("FLOAT OK\n");
        return 0;
    }
    prints("FLOAT BAD\n");
    return 1;
}
''',
        'ball': r'''
/* PRIME-C-CODE-BEGIN */
#include "prime.h"
#include "hp_gfx.h"
#include "hp_input.h"

static void show_hex(int x, int y, unsigned v, hp_color c)
{
    char buf[3];
    buf[0] = "0123456789ABCDEF"[(v >> 4) & 15];
    buf[1] = "0123456789ABCDEF"[v & 15];
    buf[2] = 0;
    hp_text(x, y, buf, c);
}

int main(void) {
    hp_event ev;
    hp_grob *bg;
    int x = 160, y = 120, vx = 3, vy = 2;
    int w, h, key = 0, keydown = 0, frames = 0, nkeys = 0, t;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n"); return 1; }
    if (!hp_input_install()) { printf("INPUT HOOK FAIL\n"); return 1; }
    w = hp_gfx_w(); h = hp_gfx_h();
    bg = hp_grob_new(w, h);
    if (!bg) { printf("GROB FAIL\n"); hp_input_remove(); return 1; }
    printf("BALL start %dx%d\n", w, h);
    printf("TW %d\n", hp_text_w("KEY:"));   /* expect 24 */
    for (;;) {
        hp_grob_select(bg);
        hp_clear(HP_BLACK);
        hp_fill_circle(x, y, 8, HP_ORANGE);
        hp_text(4, 2, "KEY:", HP_WHITE);
        show_hex(4 + hp_text_w("KEY:"), 2, key, keydown ? HP_GREEN : HP_GRAY);
        hp_text(4, 26, "q/ESC/ON TO EXIT", HP_CYAN);
        hp_grob_select(NULL);
        hp_grob_blit(bg, 0, 0);
        t = hp_poll_event(&ev);
        if (t == HP_EV_KEY) {
            key = hp_event_key(&ev);
            keydown = hp_event_key_down(&ev);
            nkeys++;
            printf("KEY %02x %d\n", key, keydown);
            if (keydown && (key == 0x51 || key == 0x01 || key == 0x83)) {
                printf("KEY_TOTAL %d\n", nkeys);
                hp_input_remove();
                printf("SLOT %08x\n", *(unsigned *)0x307fbfa0);
                printf("BALL_DONE %d\n", frames);
                hp_grob_free(bg);
                return 0;
            }
        } else if (t == HP_EV_TOUCH) {
            int tx = 0, ty = 0, n = hp_event_touch_count(&ev), k;
            for (k = 0; k < n && k < 4; k++) {
                if (hp_event_touch(&ev, k, &tx, &ty))
                    printf("TOUCH %d %d\n", tx, ty);
            }
        }
        x += vx; y += vy;
        if (x < 8 || x > w - 8) vx = -vx;
        if (y < 8 || y > h - 8) vy = -vy;
        frames++;
        __sleep(16);
    }
}
/* PRIME-C-CODE-END */
''',
        'math': r'''
#include "prime.h"
#include "hp_gfx.h"
#include "hp_input.h"
#include "hp_math.h"
#include "hp_string.h"

static void pd(const char *label, double v, int dec)
{
    char b[40];
    prints(label);
    ftoa(v, b, dec);
    prints(b);
    prints("\n");
}

int main(void) {
    hp_event ev;
    hp_grob *bg;
    int w, h, x, key, frames = 0, t;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n"); return 1; }
    if (!hp_input_install()) { printf("INPUT HOOK FAIL\n"); return 1; }
    w = hp_gfx_w(); h = hp_gfx_h();
    bg = hp_grob_new(w, h);
    if (!bg) { printf("GROB FAIL\n"); hp_input_remove(); return 1; }

    /* draw a sine wave into the back buffer */
    hp_grob_select(bg);
    hp_clear(HP_BLACK);
    hp_text(4, 2, "TCC MATH LIB", HP_WHITE);
    hp_hline(0, 120, w, HP_GRAY);
    hp_vline(160, 0, h, HP_GRAY);
    for (x = 0; x < w; x++) {
        double v = hp_sin((double)(x - 160) / 40.0);
        int y = 120 - (int)(v * 80.0);
        hp_pixel(x, y, HP_GREEN);
    }
    hp_grob_select(NULL);
    hp_grob_blit(bg, 0, 0);

    pd("sin(0.5)=", hp_sin(0.5), 5);
    pd("cos(0.5)=", hp_cos(0.5), 5);
    pd("sqrt(2)=", hp_sqrt(2.0), 6);
    pd("exp(1)=", hp_exp(1.0), 6);
    pd("log(e)=", hp_log(HP_E), 6);
    pd("pow(2,10)=", hp_pow(2.0, 10.0), 1);
    pd("atan2(1,1)=", hp_atan2(1.0, 1.0), 6);
    pd("fabs(-3.5)=", hp_fabs(-3.5), 1);
    pd("floor(2.7)=", hp_floor(2.7), 1);
    pd("fmod(7,3)=", hp_fmod(7.0, 3.0), 3);
    /* ---- string library demo ---- */
    {
        char sb[80];
        char buf[16];
        prints("STR ");
        strcpy(sb, "tcc"); strcat(sb, "+prime");
        prints(sb); prints(" ");
        itoa(2024, buf, 10); prints(buf); prints(" ");
        itoa(255, buf, 16); prints("0x"); prints(buf); prints(" ");
        prints(strstr("hello world", "world") ? "find " : "nofind ");
        prints(strcasecmp("AbC", "aBc") == 0 ? "eq " : "ne ");
        prints(strrev(sb)); prints("\n");
    }
    printf("MATH_DONE\n", 0, 0, 0, 0);

    for (;;) {
        t = hp_poll_event(&ev);
        if (t == HP_EV_KEY) {
            key = hp_event_key(&ev);
            if (hp_event_key_down(&ev)) {
                printf("KEY %02x %d\n", key, 1, 0, 0);
                if (key == 0x51 || key == 0x01 || key == 0x83) {
                    hp_input_remove();
                    hp_grob_free(bg);
                    printf("MATH_EXIT %d\n", frames, 0, 0, 0);
                    return 0;
                }
            }
        }
        frames++;
        __sleep(16);
    }
}
''',
        'rt': r'''
/* new runtime API check: ftoa/dtoa + hp_event_key id + hook teardown */
#include "prime.h"
#include "hp_input.h"
#include "hp_string.h"

int main(void) {
    hp_event ev;
    char b[40];
    int t, key;
    if (!hp_input_install()) { printf("HOOK FAIL\n", 0, 0, 0, 0); return 1; }
    prints("FTOA ");
    ftoa(3.14159265, b, 2); prints(b); prints(" ");
    ftoa(-0.5, b, 1); prints(b); prints(" ");
    ftoa(0.0, b, 3); prints(b); prints(" ");
    ftoa(12345.6789, b, 2); prints(b); prints(" ");
    ftoa(2.0 / 3.0, b, 6); prints(b); prints("\n");
    prints("DTOA ");
    dtoa(100.0, b, 0); prints(b); prints("\n");
    for (;;) {
        t = hp_poll_event(&ev);
        if (t == HP_EV_KEY) {
            key = hp_event_key(&ev);
            if (hp_event_key_down(&ev)) {
                printf("KEYID %02x\n", key, 0, 0, 0);
                if (key == 0x51) {
                    hp_input_remove();
                    return 0;
                }
            }
        }
        __sleep(16);
    }
}
''',
        'mathcut': r'''
/* 用户裁剪版: fmod 的 pd 及之后全部删除（无事件循环、无 return）*/
#include "prime.h"
#include "hp_gfx.h"
#include "hp_input.h"
#include "hp_math.h"
#include "hp_string.h"

static void pd(const char *label, double v, int dec) {
    char b[40];
    prints(label);
    ftoa(v, b, dec);
    prints(b);
    prints("\n");
}

int main(void) {
    hp_event ev;
    hp_grob *bg;
    int w, h, x, key, frames = 0, t;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n"); return 1; }
    if (!hp_input_install()) { printf("INPUT HOOK FAIL\n"); return 1; }
    w = hp_gfx_w(); h = hp_gfx_h();
    bg = hp_grob_new(w, h);
    if (!bg) { printf("GROB FAIL\n"); hp_input_remove(); return 1; }

    hp_grob_select(bg);
    hp_clear(HP_BLACK);
    hp_text(4, 2, "TCC MATH LIB", HP_WHITE);
    hp_hline(0, 120, w, HP_GRAY);
    hp_vline(160, 0, h, HP_GRAY);
    for (x = 0; x < w; x++) {
        double v = hp_sin((double)(x - 160) / 40.0);
        int y = 120 - (int)(v * 80.0);
        hp_pixel(x, y, HP_GREEN);
    }
    hp_grob_select(NULL);
    hp_grob_blit(bg, 0, 0);

    pd("sin(0.5)=", hp_sin(0.5), 5);
    pd("cos(0.5)=", hp_cos(0.5), 5);
    pd("sqrt(2)=", hp_sqrt(2.0), 6);
    pd("exp(1)=", hp_exp(1.0), 6);
    pd("log(e)=", hp_log(HP_E), 6);
    pd("pow(2,10)=", hp_pow(2.0, 10.0), 1);
    pd("atan2(1,1)=", hp_atan2(1.0, 1.0), 6);
    pd("fabs(-3.5)=", hp_fabs(-3.5), 1);
    pd("floor(2.7)=", hp_floor(2.7), 1);
}
''',
        'd': r'''
/* 测试 D: 纯 double 算术 */
#include "prime.h"
#include "hp_gfx.h"
#include "hp_input.h"
int main(void) {
    hp_event ev;
    double v;
    int key, t;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n"); return 1; }
    if (!hp_input_install()) { printf("HOOK FAIL\n", 0, 0, 0, 0); return 1; }
    v = 2.0 * 3.0 + 1.0;
    printf("ARITH %d\n", (int)v, 0, 0, 0);
    for (;;) {
        t = hp_poll_event(&ev);
        if (t == HP_EV_KEY) {
            key = hp_event_key(&ev);
            if (hp_event_key_down(&ev)) {
                printf("KEY %02x\n", key, 0, 0, 0);
                if (key == 0x51) {
                    hp_input_remove();
                    printf("EXIT_OK\n", 0, 0, 0, 0);
                    return 0;
                }
            }
        }
        __sleep(16);
    }
}
''',
        'gfx': r'''
#include "prime.h"
#include "hp_gfx.h"
int main(void) {
    hp_grob *g;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n"); return 1; }
    printf("GFX %dx%d\n", hp_gfx_w(), hp_gfx_h(), 0, 0);
    hp_clear(HP_BLACK);
    hp_fill_rect(10, 10, 60, 40, HP_RED);
    hp_rect(80, 10, 60, 40, HP_GREEN);
    hp_line(10, 200, 200, 100, HP_BLUE);
    hp_circle(250, 120, 50, HP_YELLOW);
    hp_text(10, 220, "TCC ON HP PRIME!", HP_WHITE);
    /* new: filled + outline triangle in the bottom-right free area */
    hp_fill_triangle(220, 230, 310, 230, 265, 185, HP_CYAN);
    hp_triangle(220, 230, 310, 230, 265, 185, HP_MAGENTA);
    /* new: GROB dims via accessors, draw into it, blit (5,100) */
    g = hp_grob_new(100, 50);
    if (!g) { printf("GROB FAIL\n"); return 1; }
    printf("GROBDIM %dx%d\n", hp_grob_w(g), hp_grob_h(g), 0, 0);
    hp_grob_select(g);
    hp_clear(HP_BLACK);
    hp_fill_rect(5, 5, 10, 10, HP_RED);
    hp_grob_select(NULL);
    hp_grob_blit(g, 5, 100);
    hp_grob_free(g);
    printf("GFX pixel20x20=%x pixel0x0=%x\n",
           hp_get_pixel(20, 20), hp_get_pixel(0, 0), 0, 0);
    printf("GFX_DONE\n", 0, 0, 0, 0);
    return 0;
}
''',
        'ret': r'''
#include "prime.h"
int main(void) {
    printf("RET_TEST\n", 0, 0, 0, 0);
    return 7;   /* nonzero: exercises the RT_RET real-exit-code channel */
}
''',
        'sys': r'''
#include "prime.h"
#include "hp_sys.h"
int main(void) {
    void *p;
    p = hp_sys_malloc(1024);
    if (!p) { printf("SYS_MALLOC_FAIL\n", 0, 0, 0, 0); return 1; }
    printf("SYS_MALLOC=ok\n", 0, 0, 0, 0);
    hp_sys_free(p);
    printf("SYS_MAXALLOC=%lu\n", hp_sys_max_alloc(), 0, 0, 0);
    printf("SYS_LCD=%lx\n", hp_sys_get_lcd(), 0, 0, 0);
    printf("SYS_DONE\n", 0, 0, 0, 0);
    return 0;
}
''',
        'font': r'''
#include "prime.h"
#include "hp_gfx.h"
#include "hp_input.h"
#include "hp_fonts.h"

static void ptag(const char *tag, hp_font *f, const char *s, hp_color c)
{
    char b[48];
    prints(tag);
    prints(" w=");
    printd(hp_font_w(f, s));
    prints(" h=");
    printd(hp_font_h(f));
    prints(" asc=");
    printd(f->ascent);
    prints("\n");
}

int main(void) {
    hp_event ev;
    hp_font *pf, *mf;
    hp_grob *g;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n"); return 1; }
    if (!hp_input_install()) { printf("INPUT HOOK FAIL\n"); return 1; }
    hp_clear(HP_BLACK);

    /* widths must match fontgen2.py's expected values */
    pf = hp_font_prop(16);
    mf = hp_font_mono(16);
    ptag("prop16", pf, "Hello, World!", HP_WHITE);
    ptag("mono16", mf, "Hello, World!", HP_GREEN);
    ptag("prop12", hp_font_prop(12), "Hello, World!", HP_GRAY);
    ptag("mono12", hp_font_mono(12), "Hello, World!", HP_GRAY);
    ptag("prop24", hp_font_prop(24), "Hello, World!", HP_GRAY);
    ptag("mono24", hp_font_mono(24), "Hello, World!", HP_GRAY);
    ptag("prop32", hp_font_prop(32), "Hello, World!", HP_GRAY);
    ptag("mono32", hp_font_mono(32), "Hello, World!", HP_GRAY);
    ptag("prop16-iii", hp_font_prop(16), "iii", HP_GRAY);
    ptag("mono16-iii", hp_font_mono(16), "iii", HP_GRAY);

    /* screen specimen: prop and mono at every size */
    hp_font_draw(pf, 5, 5, "Hello, World!", HP_WHITE);
    hp_font_draw(mf, 5, 5 + pf->line_h + 2, "Hello, World!", HP_GREEN);
    hp_font_draw(hp_font_prop(12), 5, 60, "Montserrat 12px abcABC", HP_CYAN);
    hp_font_draw(hp_font_mono(12), 5, 78, "Unifont 12px abcABC", HP_ORANGE);
    hp_font_draw(hp_font_prop(24), 5, 100, "Montserrat 24", HP_YELLOW);
    hp_font_draw(hp_font_mono(24), 5, 136, "Unifont 24", HP_RED);
    hp_font_draw(hp_font_prop(32), 5, 168, "M 32", HP_MAGENTA);
    hp_font_draw(hp_font_mono(32), 5, 210, "U 32", HP_BLUE);

    /* GROB: draw both fonts into an off-screen buffer, blit it */
    g = hp_grob_new(220, 64);
    if (!g) { printf("GROB FAIL\n"); return 1; }
    hp_grob_select(g);
    hp_clear(HP_BLACK);
    hp_font_draw(hp_font_prop(24), 2, 2, "GROB prop 24", HP_CYAN);
    hp_font_draw(hp_font_mono(16), 2, 34, "GROB mono 16", HP_YELLOW);
    hp_grob_select(NULL);
    hp_grob_blit(g, 30, 244);
    hp_grob_free(g);

    printf("FONT_DONE\n", 0, 0, 0, 0);
    for (;;) {
        int t = hp_poll_event(&ev);
        if (t == HP_EV_KEY) {
            int key = hp_event_key(&ev);
            printf("KEY %02x\n", key, 0, 0, 0);
            if (hp_event_key_down(&ev) && (key == 0x51 || key == 0x01 || key == 0x83)) {
                hp_input_remove();
                printf("FONT_EXIT\n", 0, 0, 0, 0);
                return 0;
            }
        }
        __sleep(16);
    }
}
''',
    # blit API smoke test: self-verifies via hp_get_pixel and prints
    'blit': r'''
#include "prime.h"
#include "hp_gfx.h"

static unsigned img[16];        /* 4x4 checker red/blue */
static unsigned spr[16];        /* 4x4 green, magenta = transparent */

int main(void) {
    int i, fails = 0;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n", 0, 0, 0, 0); return 1; }
    for (i = 0; i < 16; i++)
        img[i] = (((i & 1) ^ ((i >> 2) & 1)) ? HP_BLUE : HP_RED);
    for (i = 0; i < 16; i++)
        spr[i] = (((i % 5) == 0) ? HP_MAGENTA : HP_GREEN);

    /* opaque blit */
    hp_clear(HP_WHITE);
    hp_blit(img, 4, 4, 10, 10);
    if (hp_get_pixel(10, 10) != HP_RED)  fails++;
    if (hp_get_pixel(11, 10) != HP_BLUE) fails++;
    if (hp_get_pixel(13, 13) != HP_RED)  fails++;

    /* clipped blit (negative origin) */
    hp_blit(img, 4, 4, -2, -2);
    if (hp_get_pixel(0, 0) != HP_RED)  fails++;
    if (hp_get_pixel(1, 0) != HP_BLUE) fails++;

    /* colorkey blit: magenta skipped */
    hp_clear(HP_WHITE);
    hp_blit_key(spr, 4, 4, 20, 20, HP_MAGENTA);
    if (hp_get_pixel(20, 20) != HP_WHITE) fails++;
    if (hp_get_pixel(21, 20) != HP_GREEN) fails++;
    if (hp_get_pixel(23, 21) != HP_GREEN) fails++;

    /* scaled 2x blit (opaque) */
    hp_clear(HP_WHITE);
    hp_blit_scaled(img, 4, 4, 30, 30, 8, 8, 0);
    if (hp_get_pixel(30, 30) != HP_RED)  fails++;
    if (hp_get_pixel(31, 30) != HP_RED)  fails++;
    if (hp_get_pixel(32, 30) != HP_BLUE) fails++;
    if (hp_get_pixel(33, 30) != HP_BLUE) fails++;

    /* scaled 2x2 shrink with colorkey: key pixels drop out of the
     * weighted average, so the cell becomes the average of the
     * non-key sources (green), not the white background */
    hp_clear(HP_WHITE);
    hp_blit_scaled(spr, 4, 4, 50, 50, 2, 2, HP_MAGENTA);
    if (hp_get_pixel(50, 50) != HP_GREEN) fails++;
    if (hp_get_pixel(51, 50) != HP_GREEN) fails++;

    /* downscale quality: checker 4x4 -> 2x2 cell = average of
     * red+blue+blue+red = (127,0,127) +-1 */
    hp_clear(HP_WHITE);
    hp_blit_scaled(img, 4, 4, 60, 60, 2, 2, 0);
    {
        unsigned c = hp_get_pixel(60, 60);
        int r = (int)((c >> 16) & 0xFF);
        int g = (int)((c >> 8) & 0xFF);
        int b = (int)(c & 0xFF);
        if (r < 126 || r > 128 || g > 1 || b < 126 || b > 128)
            fails++;
        printf("BLIT avg %02x %02x %02x\n",
               (unsigned long)r, (unsigned long)g, (unsigned long)b);
    }

    /* upscale smoothness: 2x2 (row0 red, row1 blue) -> 5x5 -- a dest
     * cell straddling the red/blue boundary must be a blend (~127,0,~127),
     * not a hard nearest-neighbour step */
    {
        static unsigned two[4];     /* row0: R R, row1: B B */
        two[0] = two[1] = HP_RED;
        two[2] = two[3] = HP_BLUE;
        hp_blit_scaled(two, 2, 2, 70, 70, 5, 5, 0);
        {
            unsigned c = hp_get_pixel(72, 72);
            int r = (int)((c >> 16) & 0xFF);
            int b2 = (int)(c & 0xFF);
            if (r < 120 || r > 135 || b2 < 120 || b2 > 135) fails++;
            printf("BLIT blend %02x %02x\n",
                   (unsigned long)r, (unsigned long)b2);
        }
    }

    printf("BLIT fails=%d\n", (unsigned long)fails, 0, 0, 0, 0);
    printf("BLIT_DONE\n", 0, 0, 0, 0);
    return 0;
}
''',
    # touch pipeline probe: prints every polled event; asserts the hook
    # enqueue (press+release only), the count-0 release synthesis and
    # coordinate fidelity end to end
    'touchprobe': r'''
#include "prime.h"
#include "hp_input.h"

int main(void) {
    hp_event ev;
    int rel = 0;
    if (!hp_input_install()) { printf("INSTALL FAIL\n", 0, 0, 0, 0); return 1; }
    printf("PROBE GO\n", 0, 0, 0, 0);
    for (;;) {
        int t = hp_poll_event(&ev);
        if (t == HP_EV_KEY && hp_event_key_down(&ev)) {
            int k = hp_event_key(&ev);
            printf("K %02x\n", (unsigned long)k, 0, 0, 0);
            if (k == 0x01) break;
        } else if (t == HP_EV_TOUCH) {
            int cnt = hp_event_touch_count(&ev);
            int x = 0, y = 0, act = 0;
            if (cnt > 0)
                act = hp_event_touch(&ev, 0, &x, &y);
            printf("T c=%d a=%d x=%d y=%d\n",
                   (unsigned long)cnt, (unsigned long)act,
                   (unsigned long)x, (unsigned long)y);
            if (cnt == 0 && ++rel >= 2)
                break;
        }
        __sleep(10);
    }
    hp_input_remove();
    printf("PROBE DONE\n", 0, 0, 0, 0);
    return 0;
}
''',
    }
    if test != 'tri' and test != 'gui' and test != 'queens' \
            and test != 'queens2' and test not in tests:
        print('unknown test', test)
        sys.exit(2)
    if test == 'tri':
        # the standalone example doubles as the regression case -- run
        # examples/tri.c verbatim (PRIME-C-CODE markers are just comments)
        with open(os.path.join(TOP, 'examples', 'tri.c')) as f:
            code = f.read()
    elif test == 'gui':
        with open(os.path.join(TOP, 'examples', 'gui.c')) as f:
            code = f.read()
    elif test == 'queens':
        with open(os.path.join(TOP, 'examples', 'queens.c')) as f:
            code = f.read()
    elif test == 'queens2':
        with open(os.path.join(TOP, 'examples', 'queens2.c')) as f:
            code = f.read()
    else:
        code = tests[test]
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
    if os.environ.get('OLD_FLOW'):
        argv = [
            'tcc',
            '-nostdlib', '-shared', '-Wl,-e,main',
            '-I', r'C:\DATA\primetcc.hpappdir',
            '-o', r'C:\DATA\primetcc.hpappdir\code.elf',
            r'C:\DATA\primetcc.hpappdir\code.c',
            r'C:\DATA\primetcc.hpappdir\hp_rt.c',
            r'C:\DATA\primetcc.hpappdir\hp_gfx.c',
            r'C:\DATA\primetcc.hpappdir\hp_input.c',
            r'C:\DATA\primetcc.hpappdir\hp_math.c',
            r'C:\DATA\primetcc.hpappdir\hp_string.c',
            r'C:\DATA\primetcc.hpappdir\rt_svc.o',
            r'C:\DATA\primetcc.hpappdir\rt_aeabi.o',
            r'C:\DATA\primetcc.hpappdir\rt_math.o',
        ]
    print('==> compiling with TCC-on-ARM (this may take a while)...')
    ret, out, emu = run_elf(TCC_ELF, argv, 'tcc', max_insn=2000000000)

    code_elf = os.path.join(FAKE, 'code.elf')
    if not os.path.exists(code_elf):
        print('!! code.elf was not produced; TCC failed')
        sys.exit(1)
    print('==> code.elf produced (%d bytes); running it...' %
          os.path.getsize(code_elf))
    inject = None
    if test == 'touchprobe':
        # two press/release pairs; the second release ends the probe
        inject = [('touch', 98, 218, 1), ('touch', 98, 218, 8),
                  ('touch', 160, 218, 1), ('touch', 160, 218, 8)]
    elif test in ('ball', 'rt', 'd', 'font', 'tri', 'gfxtest'):
        inject = [('key', 0x0D, True), ('key', 0x03, True), ('key', 0x51, True)]
    if test == 'gui':
        # calculator: type "2+3*2", ENTER (-> CALC 2+3*2=8), then the
        # sqrt key (inserts "sqrt("), 9, ')', ENTER (-> CALC sqrt(9)=3),
        # then type "2*3" and tap the "=" BUTTON (-> CALC 2*3=6: proves
        # the touch pipeline press->release fires on-screen widgets),
        # then tap the EXIT button (-> GUI_DONE via touch, not a key)
        inject = [('key', 0x5A, True), ('key', 0xB9, True),
                  ('key', 0x33, True), ('key', 0x58, True),
                  ('key', 0x5A, True), ('key', 0x0D, True),
                  ('key', 0x4C, True), ('key', 0x53, True),
                  ('key', 0x4D, True), ('key', 0x0D, True),
                  ('key', 0x5A, True), ('key', 0x58, True),
                  ('key', 0x33, True),
                  ('touch', 98, 218, 1),    # press "=" (68..127, 206..230)
                  ('touch', 98, 218, 8),    # release -> button fires
                  ('touch', 160, 218, 1),   # press "EXIT" (132..191)
                  ('touch', 160, 218, 8)]   # release -> GUI_DONE
    if test == 'math':
        inject = [('key', 0x51, True)]
    ret2, out2, emu2 = run_user(code_elf, inject=inject, max_insn=500000000)
    print('RESULT: user program exit code =', ret2)

    # ---- ret test: nonzero exit code must arrive via hp_entry's RT_RET ----
    if test == 'ret' and emu2 is not None:
        ok_all = ret2 == 7 and 'RET_TEST' in out2 and 'RT_RET:7' in out2
        print('ret check emu-return-7          %s' %
              ('OK' if ret2 == 7 else 'FAIL'))
        print('ret check out-has RT_RET:7      %s' %
              ('OK' if 'RT_RET:7' in out2 else 'FAIL'))
        print('ret check out-has RET_TEST      %s' %
              ('OK' if 'RET_TEST' in out2 else 'FAIL'))
        sys.exit(0 if ok_all else 1)

    # ---- font test: text widths + metrics must match fontgen2.py ----
    if test == 'font' and emu2 is not None:
        expect = {
            'prop16': ('Hello, World!', 101, 21, 16),
            'mono16': ('Hello, World!', 130, 19, 15),
            'prop12': ('Hello, World!', 77, 16, 12),
            'mono12': ('Hello, World!', 104, 15, 12),
            'prop24': ('Hello, World!', 152, 31, 24),
            'mono24': ('Hello, World!', 195, 29, 23),
            'prop32': ('Hello, World!', 206, 40, 31),
            'mono32': ('Hello, World!', 247, 38, 30),
            'prop16-iii': ('iii', 12, 21, 16),
            'mono16-iii': ('iii', 30, 19, 15),
        }
        ok_all = 'FONT_DONE' in out2 and 'FONT_EXIT' in out2 and 'KEY 51' in out2
        import re as _re
        for tag, (txt, ew, eh, easc) in expect.items():
            m = _re.search(r'%s w=(\d+) h=(\d+) asc=(\d+)' % tag, out2)
            if not m:
                ok_all = False
                print('font check %-12s %s' % (tag, 'FAIL (no line)'))
                continue
            w, h, asc = int(m.group(1)), int(m.group(2)), int(m.group(3))
            ok = (w, h, asc) == (ew, eh, easc)
            ok_all = ok_all and ok
            print('font check %-12s %s (w=%d h=%d asc=%d, want %s)'
                  % (tag, 'OK' if ok else 'FAIL', w, h, asc, (ew, eh, easc)))
        # grayscale-AA era: glyphs blend toward the text color, so exact
        # color matches no longer hold -- count LIT pixels (any channel
        # clearly above the black background) instead.
        BLACK = 0xFF000000
        fb = emu2.fw.fb_addr
        n_lit = n_cyanish = n_black = 0
        for y in range(240):
            row = emu2.mem[fb - BASE + y * 320 * 4: fb - BASE + (y + 1) * 320 * 4]
            for x in range(320):
                v = struct.unpack('<I', row[x * 4:x * 4 + 4])[0]
                r, g, b = (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF
                if v == BLACK:
                    n_black += 1
                if max(r, g, b) >= 96:
                    n_lit += 1
                # cyan-ish at any shade: G and B strong vs R
                if g >= 96 and b >= 96 and g > r + 32:
                    n_cyanish += 1
        ok_all = ok_all and n_lit > 200 and n_cyanish > 100
        print('font check screen-lit-px>200    %s (%d)' %
              ('OK' if n_lit > 200 else 'FAIL', n_lit))
        print('font check grob-blit-cyan>100   %s (%d)' %
              ('OK' if n_cyanish > 100 else 'FAIL', n_cyanish))
        # dump the framebuffer for a visual check
        try:
            from PIL import Image as _Image
            raw = bytearray()
            for y in range(240):
                row = emu2.mem[fb - BASE + y * 320 * 4: fb - BASE + (y + 1) * 320 * 4]
                for x in range(320):
                    v = struct.unpack('<I', row[x * 4:x * 4 + 4])[0]
                    raw += bytes(((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF))
            img = _Image.frombytes('RGB', (320, 240), bytes(raw))
            img.save('/tmp/hp_font_test.png')
            print('font check fb dumped to /tmp/hp_font_test.png')
        except Exception as e:
            print('font check fb dump skipped:', e)
        sys.exit(0 if ok_all else 1)

    # ---- sys test: hp_sys memory / heap / lcd ----
    if test == 'sys' and emu2 is not None:
        ok_all = (ret2 == 0 and 'SYS_DONE' in out2
                  and 'SYS_MALLOC=ok' in out2
                  and 'SYS_MAXALLOC=' in out2
                  and 'SYS_LCD=' in out2)
        print('sys check malloc/free           %s' %
              ('OK' if 'SYS_MALLOC=ok' in out2 else 'FAIL'))
        print('sys check max_alloc present     %s' %
              ('OK' if 'SYS_MAXALLOC=' in out2 else 'FAIL'))
        print('sys check get_lcd present       %s' %
              ('OK' if 'SYS_LCD=' in out2 else 'FAIL'))
        sys.exit(0 if ok_all else 1)

    # ---- rt test: no framebuffer (no get_lcd), just needle checks ----
    if test == 'rt' and emu2 is not None:
        needles = ('FTOA 3.14 -0.5 0.000 12345.68 0.666667',
                  'DTOA 100',
                  'KEYID 0d', 'KEYID 03', 'KEYID 51')
        ok_all = ret2 == 0
        slot_restored = emu2.rd32(0x307fbfa0) != 0xe51ff004
        ok_all = ok_all and slot_restored
        print('fb check slot-restored          %s' %
              ('OK' if slot_restored else 'FAIL'))
        for needle in needles:
            ok = needle in out2
            ok_all = ok_all and ok
            print('fb check out-has %-18s %s' % (repr(needle), 'OK' if ok else 'FAIL'))
        sys.exit(0 if ok_all else 1)

    # ---- framebuffer verification (gfx / ball tests) ----
    # ---- queens2: eight queens digit format (non-static global) ----
    if test == 'queens2' and emu2 is not None:
        checks = {
            'solve start': 'QUEENS2 solve start' in out2,
            'total=92': 'QUEENS2 total=92' in out2,
            'done marker': 'QUEENS2_DONE' in out2,
            'Q01 0 4 7 5 2 6 1 3': 'Q01 0 4 7 5 2 6 1 3' in out2,
            'Q46 3 7 4 2 0 6 1 5': 'Q46 3 7 4 2 0 6 1 5' in out2,
            'Q92 7 3 0 2 5 1 6 4': 'Q92 7 3 0 2 5 1 6 4' in out2,
            'no Q93 (exactly 92)': 'Q93' not in out2,
            'all 92 lines present': all(
                ('Q%02d ' % k) in out2 for k in range(1, 93)),
        }
        for name, ok in checks.items():
            print('queens2 check %-24s %s' % (name, 'OK' if ok else 'FAIL'))
        sys.exit(0 if all(checks.values()) and ret2 == 0 else 1)

    # ---- queens: eight queens console demo (self-exiting) ----
    if test == 'queens' and emu2 is not None:
        checks = {
            'solve start': 'QUEENS solve start' in out2,
            'total=92': 'QUEENS total=92' in out2,
            'done marker': 'QUEENS_DONE' in out2,
            'Q01 a e h f c g b d': 'Q01 a e h f c g b d' in out2,
            'Q02 a f h c g d b e': 'Q02 a f h c g d b e' in out2,
            'Q46 d h e c a g b f': 'Q46 d h e c a g b f' in out2,
            'Q92 h d a c f b g e': 'Q92 h d a c f b g e' in out2,
            'no Q93 (exactly 92)': 'Q93' not in out2,
            'all 92 lines present': all(
                ('Q%02d ' % k) in out2 for k in range(1, 93)),
        }
        for name, ok in checks.items():
            print('queens check %-24s %s' % (name, 'OK' if ok else 'FAIL'))
        sys.exit(0 if all(checks.values()) and ret2 == 0 else 1)

    # ---- blit: pixel-array blit API ------------------------------------
    if test == 'blit' and emu2 is not None:
        checks = {
            'no failures': 'BLIT fails=0' in out2,
            'done marker': 'BLIT_DONE' in out2,
            'no gfx fail': 'GFX INIT FAIL' not in out2,
            'downscale avg': 'BLIT avg 7f 00 7f' in out2,
            'upscale blend': 'BLIT blend 7f 7f' in out2,
        }
        for name, ok in checks.items():
            print('blit check %-14s %s' % (name, 'OK' if ok else 'FAIL'))
        sys.exit(0 if all(checks.values()) and ret2 == 0 else 1)

    # ---- touchprobe: event pipeline fidelity (no framebuffer use) ----
    if test == 'touchprobe' and emu2 is not None:
        checks = {
            'probe go': 'PROBE GO' in out2,
            'probe press1': 'T c=1 a=1 x=98 y=218' in out2,
            'probe release1': 'T c=0' in out2,
            'probe press2': 'T c=1 a=1 x=160 y=218' in out2,
            'probe done': 'PROBE DONE' in out2,
        }
        for name, ok in checks.items():
            print('probe check %-18s %s' % (name, 'OK' if ok else 'FAIL'))
        sys.exit(0 if all(checks.values()) and ret2 == 0 else 1)

    if test in ('gfx', 'ball', 'math', 'tri', 'gfxtest', 'gui') and emu2 is not None and hasattr(emu2.fw, 'fb_addr'):
        fb = emu2.fw.fb_addr
        W, H = 320, 240

        def px(x, y):
            o = fb + (y * W + x) * 4
            return struct.unpack('<I', emu2.mem[o - BASE:o - BASE + 4])[0]

        def count(color):
            n = 0
            mem = emu2.mem
            fb0 = fb - BASE
            for y in range(H):
                row = mem[fb0 + y * W * 4:fb0 + (y + 1) * W * 4]
                for x in range(W):
                    if row[x * 4:x * 4 + 4] == struct.pack('<I', color):
                        n += 1
            return n

        BLACK = 0xFF000000
        RED = 0xFFFF0000
        GREEN = 0xFF00FF00
        YELLOW = 0xFFFFFF00
        WHITE = 0xFFFFFFFF
        BLUE = 0xFF0000FF
        CYAN = 0xFF00FFFF
        MAGENTA = 0xFFFF00FF
        if test == 'gfx':
            checks = {
                'clear(0,0)=black': px(0, 0) == BLACK,
                'fill(20,20)=red': px(20, 20) == RED,
                'rect(85,10)=green': px(85, 10) == GREEN,
                'circle(300,120)=yellow': px(300, 120) == YELLOW,
                'blue line px>50': count(BLUE) > 50,
                'yellow circle px>100': count(YELLOW) > 100,
                'white text px>10': count(WHITE) > 10,
                'tri interior=cyan': px(265, 215) == CYAN,
                'tri edge=magenta': px(265, 230) == MAGENTA,
                'grob dims printed': 'GROBDIM 100x50' in out2,
                'grob blit red px': px(12, 108) == RED,
            }
            for name, ok in checks.items():
                print('fb check %-24s %s' % (name, 'OK' if ok else 'FAIL'))
            ok_all = all(checks.values()) and ret2 == 0
        elif test == 'tri':
            orange = 0xFFFFA500   # fan fill triangles
            yellow = 0xFFFFFF00   # triangle inside the blitted GROB
            checks = {
                'fan orange px>300': count(orange) > 300,
                'big tri vertex=magenta': px(160, 60) == MAGENTA,
                'grob tri yellow': px(160, 160) == yellow,
                'grob dims printed': 'GROB 120x60 target 320x240' in out2,
            }
            for name, ok in checks.items():
                print('fb check %-24s %s' % (name, 'OK' if ok else 'FAIL'))
            ok_all = all(checks.values()) and ret2 == 0
        elif test == 'gfxtest':
            checks = {
                'gfxtest fillrect=blue': px(50, 31) == BLUE,
                'gfxtest filltri=orange': px(60, 78) == 0xFFFFA500,
                'gfxtest grob red blit': px(240, 131) == RED,
                'out-has GFXTEST 15/15': 'GFXTEST 15/15' in out2,
            }
            for name, ok in checks.items():
                print('fb check %-24s %s' % (name, 'OK' if ok else 'FAIL'))
            ok_all = all(checks.values()) and ret2 == 0
        elif test == 'gui':
            checks = {
                'calc 2+3*2=8': '2+3*2=8' in out2,
                'calc sqrt(9)=3': 'sqrt(9)=3' in out2,
                'calc 2*3=6 (via = button touch)': '2*3=6' in out2,
                'exit via EXIT button touch': 'GUI_DONE' in out2,
            }
            for name, ok in checks.items():
                print('gui check %-20s %s' % (name, 'OK' if ok else 'FAIL'))
            ok_all = all(checks.values()) and ret2 == 0
        elif test == 'math':
            green = 0xFF00FF00
            n_wave = count(green)
            print('fb check sine-wave-px>50       %s (%d)' %
                  ('OK' if n_wave > 50 else 'FAIL', n_wave))
            needles = ('sin(0.5)=0.47943', 'cos(0.5)=0.87758', 'sqrt(2)=1.414214',
                      'exp(1)=2.718282', 'log(e)=1.000000', 'pow(2,10)=1024.0',
                      'atan2(1,1)=0.785398',
                      'fabs(-3.5)=3.5', 'floor(2.7)=2.0', 'fmod(7,3)=1.000',
                      'STR tcc+prime 2024 0xff find eq emirp+cct',  # strlib demo
                      'MATH_DONE', 'KEY 51 1', 'MATH_EXIT')
            ok_all = ret2 == 0 and n_wave > 50
            for needle in needles:
                ok = needle in out2
                ok_all = ok_all and ok
                print('fb check out-has %-22s %s' % (repr(needle), 'OK' if ok else 'FAIL'))
        else:  # ball
            orange = 0xFFFFA500  # HP_ORANGE = RGB(255,165,0)
            n_ball = count(orange)
            print('fb check ball-orange-px>100     %s (%d)' %
                  ('OK' if n_ball > 100 else 'FAIL', n_ball))
            needles = ('BALL start 320x240', 'TW 24', 'KEY 0d 1', 'KEY 03 1', 'KEY 51 1',
                      'KEY_TOTAL 3', 'BALL_DONE 3', 'SLOT e52d0004')
            ok_all = ret2 == 0 and n_ball > 100
            slot_restored = emu2.rd32(0x307fbfa0) != 0xe51ff004
            ok_all = ok_all and slot_restored
            print('fb check slot-restored          %s' %
                  ('OK' if slot_restored else 'FAIL'))
            for needle in needles:
                ok = needle in out2
                ok_all = ok_all and ok
                print('fb check out-has %-18s %s' % (repr(needle), 'OK' if ok else 'FAIL'))
        sys.exit(0 if ok_all else 1)
    sys.exit(0 if ret2 == 0 else 1)


if __name__ == '__main__':
    main()
