# TCC 与 PC gcc 的 C API/ABI 统一契约

> ⚠️ **AI 生成 / 辅助创作：DeepSeek V4.1 Flash**（LCD 已人工审查，请联系 SQY 二次审查）

本文件定义**同一份用户 C 代码**在两种环境下必须遵守的统一约定：

- **目标环境（ARM）**：HP Prime G1 上的 TCC（或交叉 gcc）编译、运行；
- **主机环境（PC）**：宿主 gcc 编译（按约定**只编译、不链接运行**，见 §6）。

## 1. 权威契约来源

用户侧 API 的唯一权威定义在

[C 核心库：`toolchain/sdk/`](../toolchain/sdk/)：

| 文件 | 内容 |
|---|---|
| [`../toolchain/sdk/include/prime.h`](../toolchain/sdk/include/prime.h) | 基础运行时：输出、内存、字符串、`qsort/bsearch` |
| [`../toolchain/sdk/include/hp_gfx.h`](../toolchain/sdk/include/hp_gfx.h) | 绘图（framebuffer、图元、文本、GROB） |
| [`../toolchain/sdk/include/hp_input.h`](../toolchain/sdk/include/hp_input.h) | 键盘/触摸事件与输入钩子 |
| [`../toolchain/sdk/include/hp_math.h`](../toolchain/sdk/include/hp_math.h) | openlibm 数学函数 |
| [`../toolchain/sdk/include/hp_string.h`](../toolchain/sdk/include/hp_string.h) | 字符串/转换 |
| [`../toolchain/sdk/include/hp_fonts.h`](../toolchain/sdk/include/hp_fonts.h) | 字体与字形 |
| [`../toolchain/sdk/include/hp_gui.h`](../toolchain/sdk/include/hp_gui.h) | 控件与帧缓冲 GUI |
| [`../toolchain/sdk/include/hp_fixmath.h`](../toolchain/sdk/include/hp_fixmath.h) | Q16.16 定点数学 |
| [`../toolchain/sdk/include/hp_random.h`](../toolchain/sdk/include/hp_random.h) | PCG32 随机数与噪声 |
| [`../toolchain/sdk/include/hp_codec.h`](../toolchain/sdk/include/hp_codec.h) | CRC32/Adler32、hex/base64 |
| [`../toolchain/sdk/include/hp_sys.h`](../toolchain/sdk/include/hp_sys.h) | 固件 SVC 封装（内存/文件/LCD/事件） |
| [`../toolchain/sdk/include/hp_icall.h`](../toolchain/sdk/include/hp_icall.h) | `hp_icall2`：GCC 运行时安全回调 TCC 函数（见 §2） |
| [`../toolchain/sdk/include/hp_image.h`](../toolchain/sdk/include/hp_image.h) | PNG 图像加载/绘制（`hp_image_load_png` 等） |

## 2. 目标环境（TCC-ARM）的硬约束

这些约束**来自实现**（见各头文件注释与 [README.md](README.md)），不是风格偏好：

| 约束 | 原因 |
|---|---|
| **无 AAPCS 变参** | TCC 的 ARM 后端不生成 `va_start`；故 `printf`/`sprintf` 是 **C99 变参宏**，按实参个数派发到定参函数 `hp_printf8`/`hp_sprintf8`（格式串后 **1..8 个值**，缺参补 0） |
| **无 `%f`** | 格式化浮点要用 `ftoa`/`dtoa`（`hp_string.h`） |
| **结构体不能按值传参/返回** | TCC-ARM 的 struct-by-value 有缺陷，一律用指针 |
| **ILP32、软浮点** | `int`/`long`/指针 4 字节；`-mfloat-abi=soft`，无 FPU |
| **`malloc` 8 字节对齐** | libgcc 的 `__aeabi_*` 会用 `LDRD/STRD`，ARM926EJ-S 非对齐访问会 fault |
| **禁用尾调用优化** | 运行时需以 `-fno-optimize-sibling-calls` 编译 |
| **TCC 代码不保留 r4–r11** | TCC 生成的代码违反 AAPCS，不会恢复 callee-saved 寄存器。GCC 运行时回调 TCC 函数（GUI `on_click`、`qsort` 比较器等）时，调用者的寄存器会被破坏——**必须经 `hp_icall2`** 包裹（`hp_icall.h`：在 `blx` 前后保存/恢复 r4–r11/ip/lr） |

## 3. 主机环境（PC gcc）的差异

| 维度 | ARM（TCC/gcc） | PC（x86-64 gcc） |
|---|---|---|
| 数据模型 | ILP32 | **LP64**（`size_t`/指针 8 字节） |
| 变参 | 无（宏派发） | 原生 `va_list` |
| 浮点 | 软浮点 | 硬件 FPU |
| libc | 无（`freestanding`） | 有（`<stdlib.h>`/`<string.h>` 已声明同名函数） |

## 4. 统一手段

### 4.1 `size_t` 跟随宿主编译器

`size_t` 统一由宿主编译器决定，三个头共用同一 guard：

```c
#ifndef PRIME_SIZE_T_DEFINED
#define PRIME_SIZE_T_DEFINED
#define SIZE_T_DEFINED
#if defined(__SIZE_TYPE__)
typedef __SIZE_TYPE__ size_t;
#else
typedef unsigned int size_t;
#endif
#endif
```

- 三个头（`prime.h`、`hp_string.h`、`hp_sys.h`）共用同一 guard 宏
  （`PRIME_SIZE_T_DEFINED`），任一头先被包含都不会重复定义；
- 同时保留旧宏 `SIZE_T_DEFINED` 以兼容既有代码；
- **ARM 侧**：`__SIZE_TYPE__` 在 ARM 32 位目标上就是 `unsigned int`；
- **PC 侧**：`size_t` 与内建类型一致（64 位），不产生
  `-Wbuiltin-declaration-mismatch`。

> 这是为"统一 API/ABI"所做的**平台适配**；`#define NULL ((void *)0)`
> 保持不变（重复定义相同替换属于合法情形）。

### 4.2 用户代码应遵守的规则

为让同一份源码在两个平台都正确，用户代码必须：

1. 只用本文 §1 的头文件提供的 API，不直接 `#include <stdio.h>` 等标准头；
2. 不用变参函数指针（`int (*)(const char *, ...)`）——改用 `hp_printf8` 直接调用；
3. 不按值传递/返回结构体；
4. 不依赖 `long`/指针的宽度，需要定宽时用 API 已有类型（`hp_color`=32 位、
   `hp_fx`=32 位定点）；
5. 不假设 `size_t` 宽度（PC 与 ARM 不同）；
6. 浮点格式化走 `ftoa`/`dtoa`。

## 5. 双向验证（实测）

探针文件包含 §1 的全部 13 个头文件，并调用其中若干 API（`printf`/`sprintf`
宏派发、`hp_clear`、`hp_pixel`、`strlen`）：

```bash
# 主机
gcc -c -I toolchain/sdk/include probe.c -o probe_pc.o            # → 0 警告

# 目标
arm-none-eabi-gcc -c -mcpu=arm926ej-s -marm -mfloat-abi=soft -ffreestanding \
    -I toolchain/sdk/include probe.c -o probe_arm.o              # → 通过
```

| 验证项 | 结果 |
|---|---|
| PC gcc 编译 | **通过，0 警告** |
| ARM gcc 编译 | 通过 |
| 可复现的接口示例 | [../toolchain/examples/api-probe/](../toolchain/examples/api-probe/)（`make check`） |

## 6. 未覆盖

- **PC 端没有 `hp_*` 实现**：不新写 host shim，因此主机侧**只能编译、不能链接
  运行**；`gcc probe.c` 会在链接阶段报未定义符号，属预期；
- **ARM 侧实现大量缺失**：`hp_fonts.c`/`hp_sys.c`/`hp_gui.c`/`hp_fixmath.c`/
  `hp_random.c`/`hp_codec.c`/`hp_icall.c`/`hp_entry` 等不存在，
  `rt_core.o` 无法重建，详见 [STATUS.md](STATUS.md)；
- **TCC 编译器本身未改动**（无源码）；
- 头文件与实现的历史不一致点**只标记、不修改**，见 [STATUS.md](STATUS.md)。
