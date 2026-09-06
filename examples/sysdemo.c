/* PRIME-C-CODE-BEGIN */
#include "prime.h"
#include "hp_gfx.h"
#include "hp_input.h"
#include "hp_sys.h"
#include "hp_fonts.h"

/* ---- system-library test panel ----
 * Runs the hp_sys functions (memory / heap / lcd / debug device)
 * and draws the results on the LCD with the custom fonts: Montserrat
 * (proportional) for labels, Cascadia Code (monospace) for values.
 * Every step prints an Sx marker to the console FIRST, so if the device
 * reboots mid-test, the crash gate shows exactly which call died.
 * ENTER (0x0D) re-runs the panel; q (0x51) / ON (0x83) / ESC (0x01) exit.
 * This is the default demo embedded in calc/main.py's PRIME-C-CODE section.
 */

#define SYS_KEY_Q   HP_KEY_Q
#define SYS_KEY_ON  HP_KEY_ON
#define SYS_KEY_ESC HP_KEY_ESC
#define SYS_KEY_RUN HP_KEY_ENTER

static int sys_is_exit(int key)
{
    return key == SYS_KEY_Q || key == SYS_KEY_ON || key == SYS_KEY_ESC;
}

/* step marker: print to the console AND persist to crash.log (the console
 * is lost on reboot; crash.log survives).  Reopen with "wb+" every time
 * (the firmware fopen accepts only "rb"/"wb+") and close immediately so
 * the write is flushed -- crash.log then always holds the LAST completed
 * step, which the crash gate displays on the next run. */
static void sys_mark(const char *s)
{
    unsigned fd;
    unsigned n = 0;
    printf("%s\n", (unsigned long)s, 0, 0, 0);
    fd = hp_sys_fopen("crash.log", "wb+");
    if (fd) {
        while (s[n]) n++;
        hp_sys_fwrite((unsigned)(unsigned long)s, 1, n, fd);
        hp_sys_fclose(fd);
    }
}

/* one row: Montserrat 16 label + SCP 16 value, drawn on the LCD AND
 * echoed to the console so memory figures can be watched across runs
 * (heap_free / max_alloc decline ~0.7MB per run -- firmware allocator
 * does not return the compile working set; see README "运行内存") */
static void sys_row(int y, const char *label, const char *value)
{
    hp_font_draw(hp_font_prop(16), 8, y, label, HP_CYAN);
    hp_font_draw(hp_font_mono(16), 150, y, value, HP_WHITE);
    printf("%s=%s\n", (unsigned long)label, (unsigned long)value);
}

static void sys_panel(void)
{
    char b[48];
    void *p;
    int y = 50;

    hp_clear(HP_BLACK);
    hp_font_draw(hp_font_prop(24), 8, 6, "primetcc SYS test", HP_YELLOW);
    hp_font_draw(hp_font_prop(12), 8, 38,
                 "ENTER=rerun  q/ON/ESC=exit", HP_GRAY);

    sys_mark("S1 malloc");
    p = hp_sys_malloc(1024);
    sprintf(b, "%s", (unsigned long)(p ? "ok" : "FAIL"), 0, 0, 0);
    sys_row(y, "malloc", b); y += 21;
    if (p) hp_sys_free(p);

    sys_mark("S2 calloc");
    p = hp_sys_calloc(16, 64);
    sprintf(b, "%s", (unsigned long)(p ? "ok" : "FAIL"), 0, 0, 0);
    sys_row(y, "calloc", b); y += 21;
    if (p) hp_sys_free(p);

    sys_mark("S3 realloc");
    p = hp_sys_malloc(64);
    if (p)
        p = hp_sys_realloc(p, 256);
    sprintf(b, "%s", (unsigned long)(p ? "ok" : "FAIL"), 0, 0, 0);
    sys_row(y, "realloc", b); y += 21;
    if (p) hp_sys_free(p);

    sys_mark("S4 max_alloc");
    sprintf(b, "%lu", hp_sys_max_alloc(), 0, 0, 0);
    sys_row(y, "max_alloc", b); y += 21;

    sys_mark("S5 heap_free");
    sprintf(b, "%lu", hp_sys_heap_free(), 0, 0, 0);
    sys_row(y, "heap_free", b); y += 21;

    sys_mark("S6 get_lcd");
    sprintf(b, "%lx", hp_sys_get_lcd(), 0, 0, 0);
    sys_row(y, "get_lcd", b); y += 21;

    sys_mark("S7 debug_open");
    sprintf(b, "%lx", (unsigned long)hp_sys_debug_open(), 0, 0, 0);
    sys_row(y, "debug", b); y += 21;

    sys_mark("SYS_DONE");
}

int main(void) {
    hp_event ev;
    int key, t;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n", 0, 0, 0, 0); return 1; }
    if (!hp_input_install()) { printf("INPUT HOOK FAIL\n", 0, 0, 0, 0); return 1; }
    for (;;) {
        sys_panel();
        for (;;) {
            __sleep(16);
            t = hp_poll_event(&ev);
            if (t != HP_EV_KEY || !hp_event_key_down(&ev))
                continue;
            key = hp_event_key(&ev);
            printf("KEY %02x\n", key, 0, 0, 0);
            if (sys_is_exit(key)) {
                hp_input_remove();
                printf("SYS_EXIT\n", 0, 0, 0, 0);
                return 0;
            }
            if (key == SYS_KEY_RUN)
                break;                 /* re-run the panel */
        }
    }
}
/* PRIME-C-CODE-END */
