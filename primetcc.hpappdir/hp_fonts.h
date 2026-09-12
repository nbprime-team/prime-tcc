/*
 * hp_fonts.h —— HP Prime 图形库的字体 API：两个字族，带逐字形度量，
 * 可绘制到屏幕或已选中的 GROB（每次绘制都经 hp_pixel，作用于当前 grob）。
 *
 *   mono —— Cascadia Code Light（OFL-1.1，wght=350），固定宽度单元
 *   prop —— Montserrat（OFL-1.1），比例步进，逐字号字重：
 *           12px wght=450，16px+ Regular
 *
 * 二者都是预光栅化的 4 位灰度（alpha 覆盖，16 级）位图，尺寸
 * 12/16/24/32 px（hp_fonts_data.c，由 tools/fontgen2.py 生成）；绘制
 * 经 hp_pixel_a 做 alpha 混色。hp_font_mono/prop 选取最接近的预渲染
 * 字号。
 *
 * 坐标约定：hp_font_draw(f, x, y, s, c) 把 (x,y) 视为行盒左上角
 * （同 hp_text）；基线位于 y + f->ascent。hp_font_w 返回笔步进
 * （各字形步进之和），hp_font_h 返回行高。
 */
#ifndef HP_FONTS_H
#define HP_FONTS_H

#include "hp_gfx.h"            /* hp_color */

typedef struct hp_glyph {
    unsigned char w, h;        /* 位图宽/高（像素；0 = 无墨） */
    signed char   xoff;        /* 位图左边缘相对笔 x 的偏移 */
    signed char   yoff;        /* 位图顶行相对行顶 y 的偏移 */
    unsigned char adv;         /* 步进宽度（像素） */
    unsigned short bits;       /* 在字体位图池中的字节偏移 */
} hp_glyph;

typedef struct hp_font {
    unsigned char size;        /* 名义字号（像素） */
    unsigned char line_h;      /* 行高（像素，ascent + descent） */
    signed char   ascent;      /* 基线相对行顶的偏移 */
    unsigned char first;       /* 首个字形字符码 */
    unsigned char last;        /* 末个字形字符码 */
    const hp_glyph *glyphs;    /* (last-first+1) 项，索引 = ch-first */
    const unsigned char *bits; /* 打包的 1 位位图（逐行，LSB 优先） */
} hp_font;

/* 字体句柄：最接近的预渲染字号；永不返回 NULL */
hp_font *hp_font_mono(int size);       /* Unifont（等宽） */
hp_font *hp_font_prop(int size);       /* Montserrat（比例） */

/* 访问生成的表（hp_fonts_data.c），索引 0..3。
 * 用函数而非全局变量：TCC 的 ARM 链接器无法为非 static 全局变量重定位
 * GOT 访问（见 hp_fonts_data.c）。 */
const hp_font *hp_font_prop_data(int i);
const hp_font *hp_font_mono_data(int i);

/* 度量 */
int hp_font_h(const hp_font *f);                /* 行高（像素） */
int hp_font_w(const hp_font *f, const char *s); /* 文本宽度（像素） */
int hp_font_advance(const hp_font *f, int ch);  /* 单字符步进（像素） */

/* 绘制到当前目标（屏幕或已选中的 GROB） */
void hp_font_draw(const hp_font *f, int x, int y, const char *s, hp_color c);
void hp_font_draw_bg(const hp_font *f, int x, int y, const char *s,
                     hp_color fg, hp_color bg);

#endif /* HP_FONTS_H */
