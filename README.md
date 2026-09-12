# primeTCC

#### TCC (TinyCC) 移植到 HP Prime G1 计算器

> ⚠️ **AI 生成 / 辅助创作：DeepSeek V4.1 Flash**（本次修订；原文由项目作者撰写）

运行在 **HP Prime G1** 上的 **TinyCC** 0.9.27 移植：TCC 本体交叉编译为单文件 ELF，
由计算器上的 MicroPython 加载器装入内存运行，把用户 C 源码编译成 ARM ELF
（`code.elf`）再加载执行，输出经 PRIMELOG 环形缓冲回显。

## ⚠️ 当前状态：不可构建

源码已按 `Makefile` 期望归位到 `hp/`、`rt/`、`calc/`，但**上游从未提交 TCC 源码
与其余运行时实现**，`make all` 必然失败：

```text
make: *** 没有规则可制作目标“obj/tcc.o”，由“tcc.elf” 需求。 停止。
```

**缺失清单、源码疑误标记、补全步骤、待决策 → 全部集中在 [STATUS.md](STATUS.md)。**

## 目录结构

```text
prime-tcc/
├── README.md / STATUS.md / API.md / API_ABI_CONTRACT.md / LICENSE
├── Makefile                    构建（主机侧交叉编译）
├── hp/                         TCC 本体的 Prime 侧支撑
│   ├── prime.h  stdbool.h      [已就位] 用户程序头文件
│   ├── hp_libc.h/.c  hp_vsnprintf.c  hp_svc.s  include/   [缺失]
├── rt/                         用户程序运行时（预编译进 rt_core.o）
│   ├── [已就位] 5 个 .c：hp_rt/hp_gfx/hp_input/hp_math/hp_string
│   ├── [已就位] 12 个头：hp_gfx/input/math/string/fonts/sys/fixmath/
│   │            random/codec/gui/icall/image
│   └── [缺失]   hp_fonts.c hp_fonts_data.c hp_sys.c hp_fixmath.c
│                hp_random.c hp_codec.c hp_gui.c hp_icall.c hp_image.c
│                hp_input_svc.c/.h rt_svc.s rt_softfloat.c openlibm/
├── calc/main.py                [已就位] 计算器端加载器
├── src/tinycc-mob/             [缺失] TCC 源码（含移植补丁）
├── tests/                      [缺失] harness.py / emu_arm2.py / restart_check.py
├── examples/                   独立示例（8 个 .c）
├── primetcc.hpappdir/          部署目录（tcc.elf、rt_*.o、main.py、*、hp_*.h、
│                               icon.png、primetcc.hpapp*、code.c/elf…）
├── rt_core.o / rt_math.o / rt_svc.o / rt_aeabi.o   预编译产物
└── tcc.elf                     TCC 编译器本体（预编译）
```

## 构建

```bash
source ../toolchain/scripts/env.sh   # 提供包装层与 TOOLCHAIN_ROOT
make all                             # 需先补齐 STATUS.md §2 的源码
```

`tcc.elf` 形状：ELF32 `ET_DYN`(PIE)、文本+数据+128KB 栈、156 条 `R_ARM_RELATIVE`
重定位，与 Prime shellcode loader 兼容。

对 TCC 源码的移植补丁（补齐后适用）：

1. `tcc.h`：`HP_PRIME` 启用反斜杠/盘符感知的路径处理（`IS_DIRSEP`/`IS_ABSPATH`）；
2. `arm-gen.c`：`o()` 参数类型 `uint32_t`→`unsigned int`；
3. `arm-link.c`：`R_ARM_V4BX` 归入 `NO_GOTPLT_ENTRY`；
4. `tccrun.c`：sigaction 赋值加类型转换。

## 安装到计算器

把 `primetcc.hpappdir/` 拷入计算器 `C:\DATA\`，在 Python 应用中 `import main`
（或按**清除**金刚键自动运行）。目录内平铺 `tcc.elf`、`main.py`、`rt_*.o`、
`prime.h`、`hp_*.h`；`code.c`/`code.elf` 在运行时生成，`tcc.slot` 记录常驻 TCC 地址。

## 已知限制

- **TCC 自身用 -O0 构建**：`tcc.o` 在 -O1/-O2 下预定义阶段报
  `struct/union/enum already defined`；
- **结构体不能按值传参/返回**：TCC-ARM 的 struct-by-value 有缺陷，一律用指针；
- **TCC-ARM 无原生浮点**：软浮点运行时正确，但不识别 `1.5f` 之类常量细节；
- **禁用尾调用优化**：`rt_core.o` 用 `-fno-optimize-sibling-calls`；尾调用配合固件
  SVC 的返回机制（svc 从栈弹 lr）会让执行流错乱；
- **回调必须走 `hp_icall2`**：TCC 生成的代码不保留 r4–r11（AAPCS 违例），
  GCC 运行时调用 TCC 函数指针前须经 `hp_icall2` 保存/恢复寄存器——
  详见 [API_ABI_CONTRACT.md](API_ABI_CONTRACT.md) §2。

## 测试

示例在 `examples/`（清单见 [examples/readme.md](examples/readme.md)）。真机崩溃排查：

- **PRIMELOG**：`main.py` 彩色回显，崩溃重启后 TCC 阶段输出持久化在 `tcc.log`；
- **crash.log 分层**：demo 写 S1–S21，`hp_entry` 退出写 E1，`main.py` 收尾写 M1–M4；
  重启后再 `import main` 会显示 `last crash.log step`。

## 固件接口

> ⚠️ **本小节不完整**：上游原文在「运行内存」处中断（仅剩 "Prime内存管理是💩。"），
> 关于"每轮编译+运行后自由内存减少约 0.71MB"的成因与规避**尚无记录**。补全需
> `rt/hp_rt.c` 的分配器与 `calc/main.py` 的释放流程。在补齐前**不臆造机制**。

## 相关文档

| 文件 | 内容 |
|---|---|
| [STATUS.md](STATUS.md) | **未完成集中**：缺失源码、源码疑误、补全步骤、待决策 |
| [API_ABI_CONTRACT.md](API_ABI_CONTRACT.md) | TCC 与 PC gcc 的 C API/ABI 统一契约与实测验证 |
| [API.md](API.md) | 用户程序 API 速查 |
| [examples/readme.md](examples/readme.md) | 示例清单与验证顺序 |
| [../toolchain/README.md](../toolchain/README.md) | 交叉工具链 |
| [../toolchain/examples/api-probe/](../toolchain/examples/api-probe/) | 接口示例：API/ABI 探针 |
