# primeTCC
#### TCC (TinyCC) 移植到 HP Prime G1 计算器

本文件夹**并不**能直接安装到计算器，请查看[/examples](/examples)

在 **HP Prime G1**上运行的**TinyCC** 0.9.27 移植。TCC 本体交叉编译为单文件 ELF，由计算器上 MicroPython 加载器（shellcode）装入内存运行；在计算器上把用户 C 源码编译成ARM ELF（`code.elf`），再用同一个加载器运行它，输出通过 PRIMELOG 环形缓冲回显。

只有用户的 `code.c` 在计算器上编译；运行时预编译成 **`rt_core.o`**。

## 目录

```
primetcc/
├── API.md
├── Makefile            构建（主机侧交叉编译）
├── hp/
│   ├── hp_libc.h       迷你 C 运行库声明
│   ├── hp_libc.c       文件IO/内存/字符串/exit… 全部走固件 SVC
│   ├── hp_vsnprintf.c  vsnprintf 核心
│   ├── hp_svc.s        SVC 包装 (push{r0};push{lr};svc N) + setjmp/longjmp + crt0
│   ├── prime.h         用户程序头文件（TCC 编译的用户代码用）
│   └── include/        给 TCC 源码编译用的桩头文件 (stdio.h 等, 遮蔽 newlib)
├── rt/                 用户程序运行时源码（预编译进 rt_core.o）
│   ├── hp_rt.c         printf→PRIMELOG、malloc/free、mem/str、hp_entry 入口、
│   │                   g_hp_input（PRIMEIN 状态地址）
│   ├── hp_gfx.c/h      图形库（GROB 双缓冲、图元、5x8 字体）
│   ├── hp_input.c/h    键盘+触摸客户端（共享队列读写、槽位接管/恢复、看门狗）
│   ├── hp_input_svc.c/h 常驻输入钩子服务——**编入 tcc.elf**，槽位永远指向它
│   ├── hp_math.c/h     数学库声明（实现主体在 openlibm 的 rt_math.o）
│   ├── hp_string.c/h   字符串库（含 ftoa/dtoa 浮点格式化）
│   └── openlibm/       BSD 数学库源码（预编译成 rt_math.o, 1e-16 精度）
├── rt_core.o           预编译运行时（Makefile 生成）
├── rt_math.o           预编译数学库（openlibm, hp_* 改名）
├── rt_svc.o            用户程序的固件 SVC 包装（预编译）
├── rt_aeabi.o          libgcc 除法/软浮点辅助（预编译）
├── calc/
│   └── main.py         计算器端加载器源文件（部署版见 ../primetcc.hpappdir/）
├── tests/
│   ├── emu_arm2.py     ARMv5 解释器 + 固件 SVC 模拟（主机侧验证）
│   ├── harness.py      端到端测试（TCC 编译→加载→运行→比对输出）
│   └── restart_check.py 多轮连续运行按键可达性回归
├── src/tinycc-mob/     TCC 源码（打了少量移植补丁）
└── ../primetcc.hpappdir/   产物
```

## 安装到计算器

将`primetcc.hpappdir`使用连接软件传输至计算器，或者放入`C:\DATA\`

```
C:\DATA\primetcc.hpappdir\
├── tcc.elf        TCC 编译器本体
├── main.py        加载器（写源码→调 TCC→加载运行产物→安全释放）
├── prime.h        用户程序头文件
├── hp_gfx.h / hp_input.h / hp_math.h / hp_string.h   用户程序头文件
├── rt_core.o      预编译运行时（hp_rt+hp_gfx+hp_input+hp_math+hp_string）
├── rt_math.o      预编译数学库（openlibm）
├── rt_svc.o       固件 SVC 包装（预编译）
└── rt_aeabi.o     libgcc 除法/软浮点辅助（预编译）
```

`code.c`、`code.elf` 在运行 main.py 时于计算器上生成，`tcc.slot` 记录常驻TCC 的地址，同样平铺在 `primetcc.hpappdir\` 下。

在计算器的 Python 应用里运行：

```python
import main
```

或者点击**清除**金刚键自动运行。

## 构建

需要 `arm-none-eabi-gcc`
Ubuntu: `apt install gcc-arm-none-eabi
binutils-arm-none-eabi libnewlib-arm-none-eabi`

```sh
make tcc.elf rt_core.o rt_math.o rt_svc.o rt_aeabi.o   # 全部产物
```

重新生成部署目录：

```sh
make deploy    # 重建全部产物并拷贝到 ../primetcc.hpappdir/
```

tcc.elf 形状：ELF32 ET_DYN (PIE)、文本+数据+128KB 栈、156 条
`R_ARM_RELATIVE` 重定位——与现有 Prime shellcode loader 完全兼容。

对 TCC 源码的移植补丁：
1. `tcc.h`：`HP_PRIME` 宏启用反斜杠/盘符感知的路径处理（`IS_DIRSEP`/`IS_ABSPATH`）。
2. `arm-gen.c`：`o()` 参数类型`uint32_t`→`unsigned int`。
3. `arm-link.c`：`R_ARM_V4BX` 归入`NO_GOTPLT_ENTRY`。
4. `tccrun.c`：sigaction 赋值加类型转换。


## 已知限制

- **TCC 自身用 -O0 构建**：tcc.o 在 -O1/-O2 下表现异常（预定义阶段报 `struct/union/enum already defined`
- **结构体不能按值返回/传参**：TCC-ARM 的 struct-by-value return 有缺陷，用指针。
- **TCC-ARM 无原生浮点**：用户代码里的 double/float 运算经软浮点运行时正确执行，但 TCC 不识别 `1.5f` 后缀等浮点常量语法细节。
- **GCC 尾调用优化禁用**：rt_core.o 用 `-fno-optimize-sibling-calls` 编译。尾调用（`b func`）配合固件 SVC 的返回机制（svc 从栈弹 lr）会让执行流错乱、落入数据区崩溃重启

## 测试

独立示例集中在 `examples/`：`hello.c`、`ball.c`、`sysdemo.c`、`mandelbrot.c`

真机崩溃排查工具：
- **PRIMELOG**：main.py 彩色回显；崩溃重启后 TCC 阶段的输出持久化在 `tcc.log`。
- **crash.log 分层**：demo 关键步骤写 crash.log（S1–S21），hp_entry 退出写 E1，main.py 收尾写 M1–M4——崩溃重启后再次 `import main` 会显示 `last crash.log step`，精确定位崩溃层。

## 固件接口（HP Prime G1）

### 运行内存：为什么每轮编译+运行后自由内存减少 ~0.71MB

Prime内存管理是💩。
