/*
 * hp_input.h —— HP Prime G1 上 TCC 编译程序的键盘 + 触摸输入，经由
 * 固件 get_event（svc 0x1003f）。
 *
 * 事件结构（对照 PureDOOM 移植的 my_get_event_hook 核实）：
 *   ev->[4]   = 事件类型：0x00100010 = 按键，15 = 触摸，其它 = 无
 *   key:      ev->[28] = 16（按下）/ 0x100000（抬起）；ev->[34] = u16
 *             物理扫描码（见下方 HP_KEY_*）
 *   touch:    ev->[24] = u16 触点数量（<= 8）；第 i 个触点占 12 字节，
 *             位于 ev->[28 + 12*i]：[0] = u32 触点类型（1 = 按下/绝对
 *             位置，2 = 移动，8 = 抬起），[4] = u16（0 = 有效），
 *             [6] = u16 x，[8] = u16 y
 *
 * 用法：
 *     hp_event ev;
 *     int t = hp_poll_event(&ev);
 *     if (t == HP_EV_KEY) { int k = hp_event_key(&ev); ... }
 *     if (t == HP_EV_TOUCH) { int x, y; hp_event_touch(&ev, 0, &x, &y); }
 */
#ifndef HP_INPUT_H
#define HP_INPUT_H

#define HP_EV_NONE   0
#define HP_EV_KEY    0x00100010
#define HP_EV_TOUCH  15

#define HP_EV_KEY_DOWN  16
#define HP_EV_KEY_UP    0x100000

#define HP_TOUCH_PRESS    1
#define HP_TOUCH_MOVE     2
#define HP_TOUCH_RELEASE  8

typedef struct hp_event {
    unsigned data[32];      /* 128 字节，不透明（由固件填充） */
} hp_event;

/* 轮询一个事件（非阻塞）；返回 HP_EV_KEY / HP_EV_TOUCH / 0。
 * 必须先调用 hp_input_install()：输入经固件 get_event 钩子（常驻于
 * tcc.elf）到达，而不是直接调用 get_event（它会在 OS UI 线程上阻塞）。 */
int hp_poll_event(hp_event *ev);

/* 装配常驻的 get_event 钩子：把固件 API 槽 0x307fbfa0 强制改为
 * tcc.elf 内的钩子，并复位共享队列。若槽已被（上一次运行）打过补丁，
 * 则接管而不是拒绝。开始时调用一次。成功返回 1；共享输入状态未提供
 * 时返回 0（入口必须是 hp_entry，且 r0 = 状态指针）。 */
int  hp_input_install(void);
/* 从共享的已保存字节还原固件槽并解除装配。
 * hp_entry 退出时的清理流程也会自动调用它。钩子本身常驻于 tcc.elf，
 * 因此该操作始终安全。 */
void hp_input_remove(void);
/* 钩子已装配时为 1（有程序在监听）；OS 线程正处于钩子的阻塞
 * get_event 调用中时为 1。 */
int  hp_input_hooked(void);
int  hp_input_busy(void);

/* 按键事件 */
int hp_event_key(const hp_event *ev);        /* 物理扫描码（即键 id） */
int hp_event_key_down(const hp_event *ev);   /* 1 = 按下，0 = 抬起 */

/* 触摸事件 */
int hp_event_touch_count(const hp_event *ev);
/* 触点类型（HP_TOUCH_*）或 0；填充 x/y（屏幕像素） */
int hp_event_touch(const hp_event *ev, int i, int *x, int *y);

/* ---- 物理扫描码（HP Prime G1 键盘）------------------------------------
 * 对照完整扫描码表核实（矩阵 SCANCODE(row,col) -> 设备键 id，已硬件
 * 验证）：
 *   (0,0)=on 0x83   (1,0)=eex 0x50   (1,1)=0 0x30   (1,2)=divide 0x54
 *   (1,3)=mul 0x58  (1,4)=minus 0xB7 (1,5)=add 0xB9  (1,6)=space 0x20
 *   (1,7)=left 0x02 (2,0)=backspace 0x0C (2,1)=define 0x44 (2,2)=units 0x43
 *   (2,3)=alpha 0xB6 (2,4)=ab/c 0x45 (2,5)=vars 0x41 (2,6)=sin 0x47
 *   (2,7)=toolbox 0x42 (3,0)=+/- 0x4D (3,1)=square 0x4C (3,2)=log 0x4B
 *   (3,3)=ln 0x4A (3,4)=tan 0x49 (3,5)=cos 0x48 (3,6)=shift 0x8B
 *   (3,7)=pow 0x46 (4,0)=num 0xB3 (4,1)=plot 0xB2 (4,2)=symb 0x91
 *   (4,3)=home (4,4)=apps 0xB1 (4,5)=down 0x05 (4,6)=esc 0x01
 *   (4,7)=bracket 0x4E (5,0)=9 0x53 (5,1)=cas 0xB5 (5,2)=menu 0x93
 *   (5,3)=view 0xB4 (5,4)=up 0x03 (5,5)=1 0x59 (5,6)=period 0xB8
 *   (5,7)=help 0x95 (6,0)=comma 0x4F (6,1)=8 0x52 (6,2)=7/Q 0x51
 *   (6,3)=6 0x57 (6,4)=5 0x56 (6,5)=4 0x55 (6,6)=3 0x33 (6,7)=2 0x5A
 *   (7,0)=enter 0x0D (7,1)=right 0x04
 * 注意：字母键就是物理的数字/符号键（alpha 层），例如 'q' 是 7/Q 键
 * = 0x51。
 */
#define HP_KEY_ESC       0x01
#define HP_KEY_LEFT      0x02
#define HP_KEY_UP        0x03
#define HP_KEY_RIGHT     0x04
#define HP_KEY_DOWN      0x05
#define HP_KEY_BACKSPACE 0x0C
#define HP_KEY_ENTER     0x0D
#define HP_KEY_SPACE     0x20
#define HP_KEY_ON        0x83   /* ON/Cancel */
#define HP_KEY_SHIFT     0x8B
#define HP_KEY_Q         0x51   /* 7/Q 键：alpha 模式下为 'q' */
#define HP_KEY_F1        0x91   /* symb */
#define HP_KEY_F2        0xB2   /* plot */
#define HP_KEY_F3        0xB3   /* num  */
#define HP_KEY_F4        0xB4   /* view */
#define HP_KEY_F5        0xB5   /* cas  */
#define HP_KEY_F6        0x93   /* menu */
#define HP_KEY_APPS      0xB1
#define HP_KEY_HELP      0x95
#define HP_KEY_ALPHA     0xB6
#define HP_KEY_PLUSMINUS 0x4D
#define HP_KEY_X2        0x4C

#endif /* HP_INPUT_H */
