/*
 * hp_icall.h —— 从 GCC 构建的运行时到 TCC 编译应用代码的防御性间接调用。
 *
 * TCC 生成的代码不保留 callee-saved 寄存器 r4-r11（与 hp_entry 必须在
 * 加载器边界上防御的是同一种 AAPCS 违例）。当 GCC 运行时调用一个 TCC
 * 函数指针（GUI 的 on_click 回调、qsort 比较器等）时，回调对寄存器的
 * 破坏会连累调用者：hp_gui_handle 曾在 `hit->on_click(...)` 之后立即
 * 崩溃，因为它的 `hit`（r4）变回了垃圾值。把每个这样的调用包进
 * hp_icall2：它在 blx 前后保存/恢复 r4-r11/ip/lr，因此回调破坏的一切
 * 都会在继续执行前被还原。
 */
#ifndef HP_ICALL_H
#define HP_ICALL_H

/* 调用 fn(a, b)；返回 fn 留在 r0 的内容 */
int hp_icall2(void *fn, unsigned a, unsigned b);

#endif /* HP_ICALL_H */
