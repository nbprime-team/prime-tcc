# primetcc API 速查

用户程序是 C 源码（写在 `main.py` 的两个 `PRIME-C-CODE` 标记之间，或拷到
`examples/` 单独编译），在计算器上用内置 TCC 编译，链接预编译的
`rt_core.o`（GCC 构建的运行时）。开头 `#include "prime.h"` 即可，其余按需
`#include "hp_xxx.h"`。

**通用约定**
- 屏幕 320×240，32 位色（`hp_color` = 0xRRGGBB），坐标原点在左上角。
- `printf` 是变参宏，**格式串后最多 8 个参数**，缺参补 0：
  `printf("x=%d y=%d\n", (unsigned long)x, (unsigned long)y);`
- 真机 `malloc` 只保证 4 字节对齐，别假设 8 对齐；内存总量有限
  （见 README「运行内存」）。
- 程序栈由运行时分配（默认 16KB），深递归/大局部数组注意别超。
- 退出方式：`main()` 返回，或在 gui 循环里按 ESC(0x01)/ON(0x83)。

---

## prime.h — 基础运行时

| 函数 | 用法 |
|---|---|
| `int hp_printf8(fmt, a0..a7)` | 最底层打印，8 个参数全给 |
| `int hp_sprintf8(buf, fmt, a0..a7)` | 格式化到缓冲区（printf 的缓冲区版） |
| `int puts(const char *s)` | 打印一行（自动换行） |
| `void prints(const char *s)` | 打印字符串（不换行） |
| `void printd(long v)` / `void printx(unsigned long v)` | 打印十进制 / 十六进制数 |
| `void __sleep(unsigned ms)` | 忙等毫秒数（给轮询循环一个节奏） |
| `void *malloc(n)` / `calloc(n, sz)` / `free(p)` | 堆分配（运行时自己的分配器） |
| `strlen/strcmp/strncmp/strcpy/memcpy/memset/memcmp` | 标准字符串/内存操作 |
| `void qsort(base, nmemb, size, cmp)` | 快排，`cmp` 由 TCC 编译也安全 |
| `void *bsearch(key, base, nmemb, size, cmp)` | 二分查找 |
| `int abs(int)` / `long labs(long)` | 绝对值 |
| `bool / true / false`（C99） | 内置支持：prime.h 已自动包含 `<stdbool.h>`，TCC 原生支持 `_Bool`（任意非零赋值会归一化为 1） |

示例：
```c
char b[64];
hp_sprintf8(b, "val=%d\n", 42, 0, 0, 0, 0, 0, 0);
prints(b);
puts("hello");
```

## hp_gfx.h — 绘图

| 函数 | 用法 |
|---|---|
| `int hp_gfx_init(void)` | 开屏初始化，返回 1 成功（main 里第一步） |
| `int hp_gfx_w()` / `hp_gfx_h()` | 屏幕宽高（320 / 240） |
| `void hp_pixel(x, y, c)` | 画一个像素 |
| `void hp_pixel_a(x, y, c, a)` | 带 alpha 混色的像素 |
| `hp_color hp_get_pixel(x, y)` | 读回像素颜色 |
| `void hp_clear(c)` | 全屏清为颜色 c |
| `void hp_fill_rect(x, y, w, h, c)` | 实心矩形 |
| `void hp_rect(x, y, w, h, c)` | 空心矩形边框 |
| `void hp_hline(x, y, w, c)` / `hp_vline(x, y, h, c)` | 横/竖线 |
| `void hp_line(x0,y0, x1,y1, c)` | 任意直线（Bresenham） |
| `void hp_circle(cx, cy, r, c)` / `hp_fill_circle(...)` | 空心/实心圆 |
| `void hp_triangle(...)` / `hp_fill_triangle(...)` | 空心/实心三角形 |
| `void hp_text(x, y, s, c)` / `hp_text_bg(x, y, s, fg, bg)` | 默认字体文本（带/不带背景） |
| `int hp_text_w(s)` | 文本像素宽度 |
| `hp_grob *hp_grob_new(w, h)` | 离屏画布（GROB），可先画好再整块上屏 |
| `void hp_grob_free(g)` | 释放 GROB |
| `void hp_grob_select(g)` | 把绘制目标切到 GROB（NULL = 屏幕） |
| `void hp_grob_blit(g, x, y)` | 把 GROB 整块拷贝到屏幕 (x,y) |
| `int hp_grob_w(g)` / `hp_grob_h(g)` | GROB 宽高 |

颜色常量：`HP_BLACK / HP_WHITE / HP_RED / HP_GREEN / HP_BLUE / HP_YELLOW /
HP_CYAN / HP_MAGENTA / HP_ORANGE / HP_GRAY`，自定义用 `HP_RGB(r,g,b)`。

示例：
```c
hp_gfx_init();
hp_clear(HP_BLACK);
hp_fill_rect(10, 10, 100, 50, HP_BLUE);
hp_text(20, 60, "hi", HP_GREEN);
```

## hp_fonts.h — 字体

| 函数 | 用法 |
|---|---|
| `hp_font *hp_font_mono(size)` | 等宽字体（Unifont），内置 12/16/24/32 |
| `hp_font *hp_font_prop(size)` | 比例字体（Montserrat），同字号集 |
| `int hp_font_h(f)` | 行高（像素） |
| `int hp_font_w(f, s)` | 字符串宽度（像素） |
| `int hp_font_advance(f, ch)` | 单字符步进宽度 |
| `void hp_font_draw(f, x, y, s, c)` | 画文本 |
| `void hp_font_draw_bg(f, x, y, s, c, bg)` | 带背景画文本 |

字号没有精确匹配时自动取最接近的内置字号。

## hp_input.h — 键盘与触摸

**必须先 `hp_input_install()`**，事件由驻留钩子（tcc.elf 里）转发，轮询取：

```c
int t = hp_poll_event(&ev);          /* 非阻塞；返回 HP_EV_KEY / HP_EV_TOUCH / 0 */
if (t == HP_EV_KEY && hp_event_key_down(&ev)) {
    int k = hp_event_key(&ev);       /* 物理扫描码，见 HP_KEY_* */
} else if (t == HP_EV_TOUCH) {
    int x, y;
    hp_event_touch(&ev, 0, &x, &y);  /* 触摸坐标（按下） */
}
```

| 函数 | 用法 |
|---|---|
| `int hp_input_install(void)` | 装钩子、接管输入；1 成功（main 里调用） |
| `void hp_input_remove(void)` | 退出前恢复固件输入槽（程序返回时自动调用） |
| `int hp_input_hooked(void)` | 钩子是否在位 |
| `int hp_input_busy(void)` | 钩子是否正被 OS 线程调用中 |
| `int hp_poll_event(ev)` | 取一个事件（非阻塞） |
| `int hp_event_key(ev)` / `hp_event_key_down(ev)` | 键值 / 按下(1)或抬起(0) |
| `int hp_event_touch_count(ev)` | 触点数量（0 = 抬起事件） |
| `int hp_event_touch(ev, i, &x, &y)` | 第 i 个触点坐标；返回动作类型 |

事件/常量：`HP_EV_NONE/KEY/TOUCH`、`HP_EV_KEY_DOWN/UP`、`HP_TOUCH_PRESS(1)/
MOVE(2)/RELEASE(8)`。
常用键：`HP_KEY_ESC 0x01、HP_KEY_LEFT/RIGHT/UP/DOWN 0x02..05、
HP_KEY_BACKSPACE 0x0C、HP_KEY_ENTER 0x0D、HP_KEY_SPACE 0x20、HP_KEY_ON 0x83、
HP_KEY_Q 0x51`（7/Q 键，注意 0x51 是数字 7，不是退出键）。
触摸按屏时：按下得 `HP_TOUCH_PRESS`，抬起时得到一个
`touch_count==0` 的事件（拖动事件已被运行时过滤）。

## hp_gui.h — 控件

小控件系统：编辑框 + 按钮 + 标签，配合触摸和键盘。

```c
char buf[64];
hp_gui_widget ws[3];
ws[0] = (hp_gui_widget)HP_GUI_EDIT_INIT(4, 176, 312, 24, buf, sizeof buf);
ws[1] = (hp_gui_widget)HP_GUI_BUTTON_INIT(68, 206, 60, 24, "=", 2, btn_eval, 0);
ws[2] = (hp_gui_widget)HP_GUI_LABEL_INIT(4, 2, "title");
for (;;) {
    hp_gui_begin(); hp_gui_draw(ws, 3); hp_gui_end();   /* 双缓冲上屏 */
    t = hp_poll_event(&ev);
    if (t) hp_gui_handle(ws, 3, t, &ev);                /* 事件->控件 */
}
```

| 函数 | 用法 |
|---|---|
| `void hp_gui_begin()` / `hp_gui_end()` | 开始/结束一帧（内部 GROB 双缓冲，一次 blit） |
| `void hp_gui_draw(ws, n)` | 绘制全部控件 |
| `int hp_gui_handle(ws, n, etype, ev)` | 处理一帧事件；按钮点按返回其 id |
| `int hp_gui_edit_insert(w, s)` | 向编辑框插入字符串（函数名等） |
| `char hp_gui_key_char(k)` | 扫描码 → 字符（'0'-'9'、+ - * / 等） |

宏：`HP_GUI_LABEL_INIT(x,y,text)`、`HP_GUI_BUTTON_INIT(x,y,w,h,text,id,cb,ud)`、
`HP_GUI_EDIT_INIT(x,y,w,h,buf,buflen)`。回调签名
`void cb(hp_gui_widget *w, void *udata)`。按钮在“按下→抬起”后触发一次；
编辑框 ENTER 触发 `on_click`。

## hp_string.h — 字符串与转换

| 函数 | 用法 |
|---|---|
| `strchr/strrchr/strstr/strpbrk/strspn/strcspn/memchr` | 查找类 |
| `strncpy/strcat/strncat/memmove/strlcpy/strlcat` | 拷贝/拼接（lc 版带长度上限） |
| `strcasecmp/strncasecmp` | 忽略大小写比较 |
| `int atoi(s)` / `long atol(s)` | 字符串 → 整数 |
| `long strtol(s, &endptr, base)` | 任意进制转整数，endptr 可空 |
| `char *itoa(v, buf, base)` / `ltoa(v, buf, base)` | 整数 → 字符串 |
| `toupper/tolower/str_toupper/str_tolower` | 大小写 |
| `char *strdup(s)` / `strndup(s, n)` | 复制（malloc） |
| `char *strrev(s)` | 原地反转 |
| `char *ftoa(d, buf, dec)` | double → 字符串。**dec<0 = 自动模式**：整数无小数点（8 显示 "8"），小数去尾零，≥1e18 / <1e-15 转科学计数（"1e+20"）。dec≥0 = 固定 dec 位小数 |
| `char *dtoa(d, buf, dec)` | ftoa 别名 |
| `double strtod(s, &endptr)` / `atof(s)` | 字符串 → double（支持 e 指数、inf/nan） |

## hp_math.h — 数学（openlibm）

| 函数 | 用法 |
|---|---|
| `hp_fabs / hp_floor / hp_ceil / hp_trunc / hp_round` | 取整/绝对值类 |
| `hp_fmod(x, y)` | 浮点取余 |
| `hp_frexp(x, &e)` / `hp_ldexp(x, e)` / `hp_modf(x, &ip)` | 分解/合成 |
| `hp_sqrt / hp_exp / hp_log / hp_log10 / hp_pow` | 幂与对数 |
| `hp_sin / hp_cos / hp_tan / hp_asin / hp_acos / hp_atan / hp_atan2` | 三角函数（弧度） |
| `hp_sinh / hp_cosh / hp_tanh` | 双曲函数 |
| `void hp_double_to_str(buf, d, decimals)` | 旧版双精度转字符串（内部走 ftoa） |

全部是软浮点实现，真机可用（比硬件浮点慢，别在每帧循环里猛算）。

## hp_sys.h — 系统服务（SVC）

| 函数 | 用法 |
|---|---|
| `void *hp_sys_malloc(n)` / `calloc` / `realloc` / `free` | **固件**堆分配（和运行时 malloc 不同池，见 README） |
| `unsigned long hp_sys_max_alloc()` | 当前最大可分配块（诊断用） |
| `unsigned long hp_sys_heap_free()` | 堆剩余粗估 |
| `void hp_sys_sleep(ms)` | SVC 睡眠 |
| `unsigned long hp_sys_get_lcd()` | LCD 结构指针（底层） |
| `int hp_sys_get_event(ev)` | **阻塞**取事件（钩子未装时用） |
| `int hp_sys_thread_create(fn, arg, ...)` | 建线程（慎用） |
| `int hp_sys_debug_open()` | 调试通道 |
| `unsigned hp_sys_fopen(path, mode)` | 打开文件（ASCII 路径；模式 "rb"/"wb+"） |
| `hp_sys_fclose / fread / fwrite / fseek / ftell / filesize` | 文件读写（全部返回无符号） |

真机文件系统为 `C:\DATA\...`；运行时诊断写 `crash.log` 即用这些函数。

## hp_fixmath.h — 定点数（Q16.16）

| 函数 | 用法 |
|---|---|
| `hp_fx_int(v)` / `hp_fx_trunc(x)` / `hp_fx_round(x)` | 整数 ↔ 定点 |
| `hp_fx_from_double(d)` / `hp_fx_to_double(x)` | double ↔ 定点 |
| `hp_fx_neg/add/sub/mul/div/abs` | 基本运算 |
| `hp_fx_lerp(a, b, t)` | 线性插值，t ∈ [0,1] |
| `hp_fx_sqrt / hp_fx_sin / hp_fx_cos / hp_fx_tan / hp_fx_atan2` | 定点数学（无软浮点开销，动画/游戏用） |

`hp_fx` 是 int（16.16 定标），1.0 = 0x10000。例：
```c
hp_fx x = hp_fx_int(2);
hp_fx y = hp_fx_mul(x, x);   /* y = 4.0 */
```

## hp_random.h — 随机数与噪声

| 函数 | 用法 |
|---|---|
| `void hp_rng_seed(r, seed)` | 播种 |
| `unsigned hp_rng_u32(r)` | [0, 2^32) 均匀随机 |
| `int hp_rng_range(r, lo, hi)` | [lo, hi] 闭区间整数 |
| `hp_fx hp_rng_fx(r)` | [0, 1) 定点随机 |
| `unsigned hp_noise2_hash(x, y, seed)` | 2D 整数哈希 |
| `hp_fx hp_noise2_fx(x, y, seed)` | 2D 平滑噪声 [0,1)（值噪声，做地形/云） |

示例：`hp_rng r; hp_rng_seed(&r, 12345); int d = hp_rng_range(&r, 1, 6);`

## hp_codec.h — 编码/校验

| 函数 | 用法 |
|---|---|
| `unsigned hp_crc32(buf, len)` | CRC32（初值 0xFFFFFFFF，结果异或输出） |
| `unsigned hp_adler32(buf, len)` | Adler-32 |
| `int hp_hex_encode(dst, src, n)` | 二进制 → 十六进制字符串（2n 字符 + NUL） |
| `int hp_hex_decode(dst, src, n)` | 十六进制 → 二进制（n 个字符 → n/2 字节；非法返回 -1） |
| `int hp_b64_encode(dst, src, n)` | Base64 编码 |
| `int hp_b64_decode(dst, src, n)` | Base64 解码（n = 编码串长度；非法返回 -1） |

---

### 最小程序

```c
#include "prime.h"
#include "hp_gfx.h"

int main(void) {
    int i;
    if (!hp_gfx_init()) return 1;
    hp_clear(HP_BLACK);
    for (i = 0; i < 200; i += 10)
        hp_line(10, 200, 300, 200 - i, HP_GREEN);
    hp_text(10, 10, "hello primetcc", HP_WHITE);
    return 0;
}
```
