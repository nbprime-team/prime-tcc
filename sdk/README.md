# prime-tcc SDK —— 用户程序构建件

> ⚠️ **AI 生成 / 辅助创作：DeepSeek V4.1 Flash**（未人工审查）

应用（`app-collection/` 下的工程）构建 Prime 用户程序所需的最小构件。
**这是唯一权威源**——应用目录内**不应**再出现同名副本（此前每个应用各存一份，
内容已经开始漂移）。

| 文件 | 用途 |
|---|---|
| `prime_dyn.ld` | 用户程序链接脚本（ELF32 PIE/DYN，`ENTRY(main)`） |
| `prime_input.S` | 输入钩子 trampoline（特权 memcpy / cache-flush） |
| `hook_abi.md` | 输入钩子 ABI 说明 |
| [`../hp/prime.h`](../hp/prime.h) | 用户程序头文件（含 `stdbool.h` 包含） |
| [`../hp/stdbool.h`](../hp/stdbool.h) | C99 布尔 |

## 应用侧用法

```make
SDK ?= ../../../prime-tcc            # 从 app-collection/{examples,staging}/<app>/ 出发

CFLAGS  += -I$(SDK)/hp
LDFLAGS += -Wl,-T,$(SDK)/sdk/prime_dyn.ld

prime_input.o: $(SDK)/sdk/prime_input.S
	$(CC) $(CFLAGS) -c -o $@ $<
```

## 维护约定

1. 修改这些文件即影响所有应用，需重新验证各工程构建；
2. 历史差异：`prime_input.S` 曾在两个应用中各存一份，**只差一行注释**——
   现以本目录版本为准；
3. 头文件契约与 ABI 约定见 [../API_ABI_CONTRACT.md](../API_ABI_CONTRACT.md)。
