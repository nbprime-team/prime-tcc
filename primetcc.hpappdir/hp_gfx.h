/*
 * hp_gfx.h —— HP Prime G1 上 TCC 编译程序的图形库。
 *
 * HP Prime G1 的 LCD 为 320x240，32 位 ARGB 帧缓冲（alpha 字节被忽略）。
 * 访问方式（从可用的 gbemu 移植反推）：调用 get_lcd（svc 0x1008d）后，
 * r0 指向一个结构体，其首字又是另一个结构体：[2]=宽度(u16)、
 * [4]=高度(u16)、[16]=帧缓冲指针(u32)。像素为 32 位字 0x00RRGGBB
 * （像 gbemu 那样写入 0xFF000000 作为 alpha）。
 *
 * TCC 程序中的用法：
 *     #include "prime.h"
 *     #include "hp_gfx.h"
 *     ...
 *     if (hp_gfx_init()) {
 *         hp_clear(HP_BLACK);
 *         hp_text(10, 10, "Hello!", HP_GREEN);
 *     }
 *
 * hp_gfx.c 在计算器上与你的 code.c、hp_rt.c 一起编译（加入 TCC 命令行，
 * 见 main.py）。
 */
#ifndef HP_GFX_H
#define HP_GFX_H

#define HP_LCD_W 320
#define HP_LCD_H 240

/* 默认 5x8 字体单元（字体内嵌在 hp_gfx.c 中） */
#define HP_FONT_W 5
#define HP_FONT_H 8

typedef unsigned int hp_color;

/* 0x00RRGGBB 带 0xFF alpha（与 Prime 帧缓冲一致） */
#define HP_RGB(r, g, b) \
    (0xFF000000u | (((unsigned)(r) & 0xFFu) << 16) | \
     (((unsigned)(g) & 0xFFu) << 8) | ((unsigned)(b) & 0xFFu))

#define HP_BLACK    HP_RGB(0, 0, 0)
#define HP_WHITE    HP_RGB(255, 255, 255)
#define HP_RED      HP_RGB(255, 0, 0)
#define HP_GREEN    HP_RGB(0, 255, 0)
#define HP_BLUE     HP_RGB(0, 0, 255)
#define HP_YELLOW   HP_RGB(255, 255, 0)
#define HP_CYAN     HP_RGB(0, 255, 255)
#define HP_MAGENTA  HP_RGB(255, 0, 255)
#define HP_ORANGE   HP_RGB(255, 165, 0)
#define HP_GRAY     HP_RGB(128, 128, 128)

/* 绘制前调用一次；成功返回 1，get_lcd 失败返回 0 */
int  hp_gfx_init(void);
int  hp_gfx_w(void);              /* LCD 宽度（像素，320） */
int  hp_gfx_h(void);              /* LCD 高度（像素，240） */

/* 图元（坐标按当前绘制目标裁剪——屏幕或已选中的 GROB；越界直接丢弃，
 * 不报错）。热点路径直接写帧缓冲（行指针 + 展开的字存储，类似 gbemu
 * 的 lcd 渲染器），而不是逐像素调用辅助函数。 */
void hp_pixel(int x, int y, hp_color c);
/* alpha 混色像素：a 取 0..15（0 = 不改目标，15 = 等同 hp_pixel）。
 * 灰度字体渲染使用；对屏幕和已选中的 GROB 均有效（二者都是经 g_tgt
 * 访问的 32bpp ARGB）。 */
void hp_pixel_a(int x, int y, hp_color c, unsigned a);
hp_color hp_get_pixel(int x, int y);
void hp_clear(hp_color c);
void hp_fill_rect(int x, int y, int w, int h, hp_color c);
void hp_rect(int x, int y, int w, int h, hp_color c);   /* 边框 */
void hp_hline(int x, int y, int w, hp_color c);
void hp_vline(int x, int y, int h, hp_color c);
void hp_line(int x0, int y0, int x1, int y1, hp_color c);  /* Bresenham */
void hp_circle(int cx, int cy, int r, hp_color c);         /* 空心 */

/* 三角形：空心（3 条 Bresenham 边）与实心（扫描线 + 整数边插值，
 * 退化三角形塌缩为线/点）。 */
void hp_triangle(int x0, int y0, int x1, int y1, int x2, int y2, hp_color c);
void hp_fill_triangle(int x0, int y0, int x1, int y1,
                      int x2, int y2, hp_color c);

/* 文本：5x8 固定字体，每字符步进 6 像素 */
void hp_text(int x, int y, const char *s, hp_color c);
void hp_text_bg(int x, int y, const char *s, hp_color fg, hp_color bg);
int  hp_text_w(const char *s);    /* 像素宽度 */

/* 实心形状 */
void hp_fill_circle(int cx, int cy, int r, hp_color c);

/* ---- 原始像素数组 blit ------------------------------------------------
 * pix 是行优先的 w*h ARGB 数组（左上优先），绘制到当前绘制目标
 * （屏幕或已选中的 GROB）的 (x, y)。裁剪方式与其他图元一致。
 *
 *   hp_blit(pix, w, h, x, y)                  不透明拷贝
 *   hp_blit_key(pix, w, h, x, y, key)         像素 == key 的跳过
 *   hp_blit_scaled(pix, w, h, x, y, dw, dh, key)
 *       重采样为 dw x dh 后绘制；key == 0 表示不透明（HP_RGB 像素的
 *       alpha 恒为 0xFF，故 0 永不匹配）。质量：可分离面积滤波——
 *       放大用线性插值，缩小用盒式平均（无锯齿）。key 像素不参与
 *       加权平均；一个采样单元全是 key 时保持透明。 */
void hp_blit(const unsigned *pix, int w, int h, int x, int y);
void hp_blit_key(const unsigned *pix, int w, int h, int x, int y,
                 hp_color key);
void hp_blit_scaled(const unsigned *pix, int w, int h,
                    int x, int y, int dw, int dh, hp_color key);

/* ---- GROB 图层缓冲（类似 HP Prime 的 GROB） ----------------------------
 * 离屏位图，可用同样的图元绘制，然后一次性 blit 到当前绘制目标——
 * 双缓冲，无闪烁。
 *
 *   hp_grob *g = hp_grob_new(320, 240);   // 全屏后备缓冲
 *   hp_grob_select(g);                    // 绘制到 g（NULL = 屏幕）
 *   hp_clear(HP_BLACK); hp_fill_circle(...); hp_text(...);
 *   hp_grob_select(NULL);                 // 回到屏幕
 *   hp_grob_blit(g, 0, 0);                // 一次 blit -> 屏幕
 *   hp_grob_free(g);
 */
typedef struct hp_grob {
    int w, h;
    unsigned *px;            /* w*h 个 ARGB 像素 */
} hp_grob;

hp_grob *hp_grob_new(int w, int h);
void     hp_grob_free(hp_grob *g);
void     hp_grob_select(hp_grob *g);      /* 绘制目标；NULL = 屏幕 */
void     hp_grob_blit(hp_grob *g, int x, int y);
/* 把 g 拷贝到当前绘制目标（屏幕或已选中的 GROB——GROB 到 GROB 的
 * 拷贝可用）。裁剪方式与其他图元一致；不支持把 GROB blit 到自身。 */

/* GROB 几何（g 为 NULL 时返回 0）——优先用这些访问器，而不是从 TCC
 * 代码里直接读 g->w/g->h（与 hp_get_input_state 同样的访问器纪律）。 */
int  hp_grob_w(const hp_grob *g);  /* 宽度（像素） */
int  hp_grob_h(const hp_grob *g);  /* 高度（像素） */

/* 当前绘制目标尺寸（屏幕或已选中的 GROB） */
int  hp_target_w(void);
int  hp_target_h(void);

#endif /* HP_GFX_H */
