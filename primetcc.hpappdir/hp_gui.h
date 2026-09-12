/*
 * hp_gui.h —— 基于 hp_gfx + hp_fonts + hp_input 的最小控件工具包。
 *
 * 面向演示/游戏的极简 UI 层：标签、按钮和单行文本 EDIT 控件，由触摸
 * 或键盘驱动。所有文本用运行时字体绘制（hp_fonts.h）：标签/按钮用
 * Montserrat（比例），编辑文本用 Unifont（等宽）。
 *
 * 双缓冲：把每一帧包在 hp_gui_begin()/hp_gui_end() 中——本库持有一个
 * 惰性分配的全屏 GROB，把整帧渲染进去后一次 blit，因此不会闪烁：
 *
 *     hp_gui_begin();            选中内部后备缓冲并清屏
 *     ...绘制应用内容...          （也落在缓冲里）
 *     hp_gui_draw(ws, n);        控件绘制在最上层
 *     hp_gui_end();              一次 blit 到屏幕
 *
 *   char buf[32];
 *   hp_gui_widget ws[3];
 *   ws[0] = (hp_gui_widget)HP_GUI_LABEL_INIT(4, 2, "menu");
 *   ws[1] = (hp_gui_widget)HP_GUI_BUTTON_INIT(20, 40, 120, 26, "GO", 1, on_go, 0);
 *   ws[2] = (hp_gui_widget)HP_GUI_EDIT_INIT(20, 70, 280, 24, buf, sizeof buf);
 *   for (;;) {
 *       hp_gui_begin();
 *       hp_gui_draw(ws, 3);
 *       hp_gui_end();
 *       t = hp_poll_event(&ev);
 *       if (t) hp_gui_handle(ws, 3, t, &ev);
 *   }
 *
 * 编辑框获得焦点时的按键：Prime 的数字/运算符键（见 hp_input.h 的
 * 扫描码表）、BACKSPACE、LEFT/RIGHT 光标、ENTER 触发控件的 on_click
 * （该控件 id 由函数返回）。多字符插入（来自 SIN/COS/... 硬键的函数名）
 * 由应用通过 hp_gui_edit_insert() 完成。
 *
 * 编入 rt_core.o。依赖 hp_gfx.h / hp_fonts.h / hp_input.h。
 */
#ifndef HP_GUI_H
#define HP_GUI_H

#include "hp_gfx.h"
#include "hp_fonts.h"
#include "hp_input.h"

#ifndef NULL
#define NULL ((void *)0)
#endif

#define HP_GUI_LABEL  0
#define HP_GUI_BUTTON 1
#define HP_GUI_EDIT   2

struct hp_gui_widget;

typedef void (*hp_gui_cb)(struct hp_gui_widget *w, void *udata);

typedef struct hp_gui_widget {
    int x, y, w, h;            /* 矩形（标签忽略 w/h） */
    const char *label;
    unsigned type;             /* HP_GUI_LABEL / BUTTON / EDIT */
    int id;                    /* 用户标签；由 hp_gui_handle 返回 */
    int state;                 /* 0 空闲，1 聚焦，2 按下 */
    hp_gui_cb on_click;        /* 按钮：点击；编辑框：ENTER */
    void *udata;
    /* 仅编辑控件 */
    char *buf;                 /* 调用者持有的文本缓冲（NUL 结尾） */
    int buflen;                /* 缓冲容量 */
    int cur;                   /* 光标位置（字符） */
} hp_gui_widget;

#define HP_GUI_LABEL_INIT(x, y, text) \
    { (x), (y), 0, 0, (text), HP_GUI_LABEL, 0, 0, 0, 0, 0, 0, 0 }
#define HP_GUI_BUTTON_INIT(x, y, w, h, text, id_, cb, ud) \
    { (x), (y), (w), (h), (text), HP_GUI_BUTTON, (id_), 0, (cb), (ud), 0, 0, 0 }
#define HP_GUI_EDIT_INIT(x, y, w, h, buf_, buflen_) \
    { (x), (y), (w), (h), 0, HP_GUI_EDIT, 0, 0, 0, 0, (buf_), (buflen_), 0 }

/* ---- 双缓冲帧：begin/end 包住一帧的全部绘制 ----
 * begin() 惰性分配一个全屏后备 GROB（只创建一次，之后复用）并把它设为
 * 绘制目标；end() 将其 blit 到屏幕。该内部缓冲也通过字体承载所有控件
 * 文本。 */
void hp_gui_begin(void);
void hp_gui_end(void);

/* 把所有控件绘制到当前绘制目标（在 begin/end 之间调用；若应用自己做
 * 缓冲，也可直接画到屏幕） */
void hp_gui_draw(hp_gui_widget *ws, int n);

/* 喂入一个事件（etype = hp_poll_event() 的返回值：HP_EV_KEY /
 * HP_EV_TOUCH）；返回被点击按钮或编辑框 ENTER 的 id（否则 0）。
 * 触摸：在按钮内按下则按下该按钮，抬起触发 on_click；在编辑框内轻点
 * 使其聚焦。按键：UP/DOWN 在按钮与编辑框间移动焦点，ENTER 激活；
 * 聚焦的编辑框消费可打印的 Prime 键、BACKSPACE 和 LEFT/RIGHT（光标）。 */
int hp_gui_handle(hp_gui_widget *ws, int n, int etype, const hp_event *ev);

/* 在光标处向编辑控件插入 s（返回插入的字符数） */
int hp_gui_edit_insert(hp_gui_widget *w, const char *s);

/* Prime 键扫描码 -> 字符（0 表示未映射）。同时接受矩阵设备 id
 * （hp_input.h 表）和数字/运算符的纯 ASCII 码，因此无论固件报告哪种，
 * 同一份代码都能工作。 */
char hp_gui_key_char(int k);

#endif /* HP_GUI_H */
