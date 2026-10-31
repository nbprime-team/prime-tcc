# tcc 0.9 包

- 入口：`bin/tcc.elf`（由 `prebuilt/tcc.elf` 提供）
- 运行时：`prebuilt/rt_core.o`、`rt_svc.o`、`rt_aeabi.o`、`rt_math.o`
- 头文件：`../toolchain/sdk/include/`
- 打包：在 nb-package-index 里用 `tools/pack.py` 生成 `sys/` 或 bundle；
  release 也提供 `primetcc.hpappdir.zip` 作为自包含形态。
