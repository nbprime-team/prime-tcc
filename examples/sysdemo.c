/* PRIME-C-CODE-BEGIN */
#include "prime.h"
#include "hp_gfx.h"
#include "hp_input.h"
#include "hp_sys.h"
#include "hp_fonts.h"

/* ---- 系统库测试面板 ----
 * 运行 hp_sys 各函数（内存 / 堆 / lcd / 调试设备），并用自定义字体把
 * 结果显示在 LCD 上：标签用 Montserrat（比例），数值用 Cascadia Code
 * （等宽）。
 * 每一步都先向控制台打印一个 Sx 标记，因此若设备在测试中途重启，
 * 崩溃闸门能显示究竟是哪个调用挂掉。
 * ENTER (0x0D) 重跑面板；q (0x51) / ON (0x83) / ESC (0x01) 退出。
 * 这是 calc/main.py 的 PRIME-C-CODE 段内嵌的默认演示。
 */

#define SYS_KEY_Q   HP_KEY_Q
#define SYS_KEY_ON  HP_KEY_ON
#define SYS_KEY_ESC HP_KEY_ESC
#define SYS_KEY_RUN HP_KEY_ENTER

static int sys_is_exit(int key)
{
    return key == SYS_KEY_Q || key == SYS_KEY_ON || key == SYS_KEY_ESC;
}

/* 步骤标记：打印到控制台，同时持久化到 crash.log（控制台在重启后
 * 丢失；crash.log 会保留）。每次都先用 "wb+" 重新打开（固件 fopen
 * 只接受 "rb"/"wb+"）并立即关闭以刷出写入——这样 crash.log 始终保存
 * 最后一个完成的步骤，崩溃闸门会在下一次运行时显示它。 */
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

/* 一行：Montserrat 16 标签 + SCP 16 数值，绘制到 LCD，同时回显到
 * 控制台，以便跨多次运行观察内存数值（heap_free / max_alloc 每轮运行
 * 下降约 0.7MB——固件分配器不归还编译工作集；见 README“运行内存”） */
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
                break;                 /* 重跑面板 */
        }
    }
}
/* PRIME-C-CODE-END */
