# primetcc 状态

> ⚠️ AI 生成 / 辅助创作：DeepSeek V4.1 Flash（未人工审查）

本文件是 `prime-tcc` **未完成事项的唯一集中处**。

## 1. 构建状态

| 目标 | 状态 |
|---|---|
| `make`（`prebuilt/tcc.elf`、`rt_core.o`、`rt_math.o`、`rt_svc.o`、`rt_aeabi.o`） | ✅ 可构建 |
| `make runtime`（只构建用户程序运行时，不需要 TCC 源码） | ✅ 可构建 |
| `make deploy`（把产物与头拷入 `primetcc.hpappdir/`） | ✅ 可用 |
| `make host`（host 侧 TCC，实验用） | 未验证 |
| `make test` | 已收入 `tests/`（`harness.py`、`emu_arm2.py`、`restart_check.py` 等 33 个）；需仿真环境 |

**构成**（运行时与头文件**全部取自 `toolchain/sdk/`，本仓库不保留副本**）：

| 部分 | 来源 |
|---|---|
| TCC 源码 | `src/tinycc-mob/`（`configure` 生成 `config.h`） |
| TCC 自身运行时 | `toolchain/sdk/platform/hp_svc.s`（crt0 + SVC）、`src/hp_libc.c`、`src/hp_vsnprintf.c`、`src/hp_input_svc.c` |
| 用户程序运行时 | `toolchain/sdk/src/hp_*.c`（见 `Makefile` 的 `RT_CORE_SRCS`） |
| 数学库 | `toolchain/sdk/src/openlibm/`（编译期经 `OLM_RENAMES` 重命名为 `hp_sin`/`hp_cos`/…） |
| 软浮点 / AEABI | `toolchain/sdk/src/rt_softfloat.c` + 从 libgcc 提取的 `_aeabi_*` / `_div*` |

## 2. 待办

| 项 | 说明 |
|---|---|
| 真机验证 | 在计算器上运行 `tcc.elf`，编译并运行一个用户 `code.c`，确认端到端可用 |
| `B1` malloc 对齐 | `toolchain/sdk/src/hp_rt.c` 按 **8 字节**对齐；`API.md` 写的是 4 字节 —— 以哪边为准待确认 |
| `make host` | host 侧 TCC 目标未验证 |
| `make test` | 依赖 `tests/`（模拟器/harness），当前未提供 |

## 3. 约定

1. **运行时与头文件的唯一权威源是 `toolchain/sdk/`**；`prime-tcc` 只放 TCC 自身源码与部署脚本，
   构建时直接引用该目录（见 `Makefile` 的 `SDK` 变量）。
2. `primetcc.hpappdir/` 是**纯构建产物，整体不入库**（`.gitignore` 已忽略整目录）：
   - 包内每个文件都有仓库内的源：`tcc.elf`、`rt_*.o` 来自 `prebuilt/`；`main.py`、
     `moreprint.py`、`icon.png`、`primetcc.hpapp*` 来自 `calc/`；`prime.h`、`stdbool.h`、
     `hp_*.h` 来自 `toolchain/sdk/include/`；
   - 重建：`make deploy`；现成的完整包见 GitHub Release `v1`（`primetcc.hpappdir.zip`）。
3. ABI 与契约约定见 `API_ABI_CONTRACT.md`；用户可见 API 见 `API.md`。
