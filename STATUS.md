# prime-tcc 状态与未完成事项

> ⚠️ **AI 生成 / 辅助创作：DeepSeek V4.1 Flash**（未人工审查）

本文件是 `prime-tcc` **未完成事项的唯一集中处**：缺失源码、源码疑误、补全步骤、待决策。
（已合并原先分散的 `STATUS.md`、`STATUS.md`、`STATUS.md` 与四个目录级 `MISSING.md`。）

跨平台的 API/ABI 约定见 [API_ABI_CONTRACT.md](API_ABI_CONTRACT.md)。

## 1. 状态

**不可构建**：`make all` 报 `没有规则可制作目标“obj/tcc.o”`。

| | |
|---|---|
| 已就位 | `hp/`（`prime.h`、`stdbool.h`）；`rt/`（5 个 `.c` + 12 个头）；`calc/main.py`；`examples/`（8 个 `.c`）；`rt_*.o`、`tcc.elf`；`primetcc.hpappdir/`（部署快照） |
| 缺失 | 见 §2 |
| 根因 | 上游 git 历史从未提交这些源码（`git log --all -- src` 无输出，HEAD 仅 18 个文件） |

## 2. 缺失源码（阻塞，需上游提供）

**全工作区（含 `nbprime/`）都不存在**——已逐个 `find` 核实。

| 缺失 | 被谁引用 |
|---|---|
| `src/tinycc-mob/`（整目录：`tcc.c`、`configure` 等） | `TCCSRC` → `obj/tcc.o` |
| `hp/hp_libc.c`、`hp/hp_libc.h`、`hp/hp_vsnprintf.c`、`hp/hp_svc.s` | `HP_OBJS` |
| `hp/include/`（TCC 编译用桩头文件） | `CFLAGS -I$(TOPDIR)/hp/include` |
| `rt/hp_fonts.c`、`rt/hp_fonts_data.c`、`rt/hp_sys.c`、`rt/hp_fixmath.c`、`rt/hp_random.c`、`rt/hp_codec.c`、`rt/hp_gui.c` | `RT_CORE_SRCS` |
| `rt/hp_icall.c`、`rt/hp_image.c` | `RT_CORE_SRCS`（头 `hp_icall.h`/`hp_image.h` 已就位） |
| `rt/hp_input_svc.c/.h` | 编入 `tcc.elf` |
| `rt/rt_svc.s`、`rt/rt_softfloat.c` | `rt_svc.o` / `rt_aeabi.o` |
| `rt/openlibm/`（整目录，27 个 `.c`） | `OLM_SRCS` → `rt_math.o` |
| `tests/harness.py`、`tests/emu_arm2.py`、`tests/restart_check.py` | `make test` |

> 现有 `rt/*.c` 是**旧版**，与较新的 `*.h` 不一致（如 `hp_gfx.c` 未实现 `hp_blend`）。
> 补齐时以头文件契约为准。

## 3. 源码疑误（**已标记，未修改**）

按约定只记录、不改逻辑。复核命令均在 `prime-tcc/` 下执行。

| # | 位置 | 现象 |
|---|---|---|
| A1 | `hp/prime.h` 声明 `hp_printf8`；`rt/hp_rt.c:195` 只定义 4 参 `printf` | 变参宏派发目标无实现 → `grep -rn hp_printf8 rt/*.c` 无输出 |
| A2 | `rt/hp_gfx.h` 声明 `hp_pixel_a`/`hp_triangle`/`hp_fill_triangle`/`hp_grob_w`/`hp_grob_h`/`hp_target_w`/`hp_target_h`/`hp_blit*` | `hp_gfx.c` 实现数为 0 |
| A3 | `rt/hp_string.h` 声明 `ftoa`/`dtoa`/`strtod`/`atof` | `hp_string.c` 实现数为 0 |
| A4 | `Makefile` 用 `-Wl,-e,hp_entry` | `hp_entry`、`g_hp_input` 全仓零出现 |
| B1 | `malloc` 对齐 | `API.md` 说 4 字节；`rt/hp_rt.c:257` 是 `(raw+15)&~7`（8 字节） |
| B2 | `ftoa` 的 `dec` | `rt/hp_string.h:68` 说 clamp 0..15；`API.md:169` 说 `dec<0` 为自动模式 |
| B3 | 等宽字体名 | `rt/hp_fonts.h:6` 说 Cascadia Code；同文件 `:44` 与 `API.md:83` 说 Unifont |
| B4 | `stdbool.h` | **本轮已随上游更新补齐**（`hp/stdbool.h` 已就位）✅ |
| C1 | `NULL` 在 `hp/prime.h`、`rt/hp_string.h`、`rt/hp_gui.h` 三处重复定义 | 替换文本相同，合法；仅登记 |
| D1 | 示例 `printf` 实参个数不一（`hello.c` 0–1 个、`queens.c` 满 8 个） | 宏派发可接受；仅登记 |

> 派生自上游的 **`prime-tcc/README.md`「固件接口」小节**在原文中就中断了（只有一句
> "Prime内存管理是💩。"），内容缺失，**未臆造**，待补齐源码与实测后恢复。

## 4. 补全后如何验证（8 步，每步记录真实输出）

1. 取得 §2 全部源码，落到对应路径；
2. `source ../toolchain/scripts/env.sh` → `make -C ../toolchain verify`（应 21/21）；
3. `make src/tinycc-mob/config.h`（调用 `configure --cpu=arm`）；
4. `make rt_svc.o rt_aeabi.o`；
5. `make tcc.elf`（检查 ELF 为 `ET_DYN`、含 `R_ARM_RELATIVE`）；
6. `make rt_core.o rt_math.o`；
7. `make test`（需 `tests/harness.py`）；
8. `make deploy`（生成 `../primetcc.hpappdir/`）。

## 5. 待决策

| 事项 | 说明 |
|---|---|
| `rt/*.c` 与 `*.h` 的历史不一致 | 补齐上游实现后按 §3 逐条核对 |
| `primetcc.hpappdir/` 的角色 | 现为部署产物快照（含 `icon.png`、`primetcc.hpapp*`）；与源码由 `make deploy` 关联 |
| host shim | 若需 PC 端**运行**（非仅编译）用户代码，需 `hp_*` 的 PC 实现；本轮按约定未做 |
