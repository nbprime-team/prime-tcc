# prime-tcc 示例目录

> ⚠️ **AI 生成 / 辅助创作：DeepSeek V4.1 Flash**（未人工审查）

这些是**用计算器上的 TCC 编译的用户程序**（普通 C 源码，不是主机侧 GCC 工程），
由 `calc/main.py` 编译并运行。

## ⚠️ 当前不可编译

头文件已就位（`toolchain/sdk/` 下的 `prime.h`、`stdbool.h` 与 `hp_*.h`），但运行时**实现**与
`calc/main.py` 的依赖大量缺失，因此示例无法构建——见 [../STATUS.md](../STATUS.md)。

## 清单

| 文件 | 类型 | 依赖头文件 | 交互 / 关键输出 |
|---|---|---|---|
| `hello.c` | 控制台 | `prime.h` | 无交互；编译链最小闭环 |
| `queens.c` | 控制台 | `prime.h` | 八皇后全部 92 解；输出 `QUEENS total=92` |
| `ball.c` | 图形动画 | `prime.h` `hp_gfx.h` `hp_input.h` | 双缓冲弹球；`q`/ESC/ON 退出 |
| `tri.c` | 图形演示 | `prime.h` `hp_gfx.h` `hp_input.h` `hp_math.h` | 三角形 / GROB 图元 |
| `mandelbrot.c` | 图形应用 | `prime.h` `hp_gfx.h` `hp_input.h` `hp_sys.h` | 定点整数 Mandelbrot；方向键平移、`+`/`-` 缩放 |
| `gfxtest.c` | 自检面板 | `prime.h` `hp_gfx.h` `hp_input.h` `hp_fonts.h` `hp_string.h` | 逐图元回读校验；输出 `GFXTEST <pass>/<total>` |
| `sysdemo.c` | 自检面板 | `prime.h` `hp_gfx.h` `hp_input.h` `hp_sys.h` `hp_fonts.h` | 内存/堆/LCD 接口；逐步打印 `Sx` |
| `calculator.c` | 交互应用 | `prime.h` `hp_gfx.h` `hp_input.h` `hp_math.h` `hp_string.h` `hp_gui.h` | 表达式计算器 + HISTORY |

`hello.c` / `ball.c` 同时是 `tests/harness.py` 对应用例的基准。

## 运行

在计算器上由 TCC 编译运行（不经主机侧 GCC）：

```text
tcc examples/hello.c -run        # 由 calc/main.py 驱动
```

主机侧验证需 `tests/harness.py`（缺失）：`cd .. && make test`。

**验证顺序建议**：`hello.c` → `queens.c`（输出可精确断言）→ `ball.c`/`tri.c`
（图形）→ `mandelbrot.c` → `gfxtest.c` → `sysdemo.c` → `calculator.c`。

## 注意

- 稳定性依赖目标固件版本与工具链（G1 + 固件 20250915）；
- 失败时先区分"工具链问题"（[../../toolchain/README.md](../../toolchain/README.md)）
  与"源码缺失"（[../STATUS.md](../STATUS.md)）；
- 不把 `nbprime/` 的历史内容当作活跃示例。
