/*
 * hp_icall.h -- defensive indirect calls from GCC-built runtime code into
 * TCC-compiled app code.
 *
 * TCC's generated code does not preserve the callee-saved registers
 * r4-r11 (same AAPCS violation hp_entry already had to defend the loader
 * boundary against).  When GCC runtime code calls a TCC function pointer
 * (a gui on_click callback, a qsort comparator, ...), the callback's
 * register carnage poisons the caller: hp_gui_handle crashed right after
 * `hit->on_click(...)` because its `hit` (r4) came back as garbage.
 * Wrap every such call in hp_icall2: it saves r4-r11/ip/lr around the
 * blx, so whatever the callback destroys is restored before we continue.
 */
#ifndef HP_ICALL_H
#define HP_ICALL_H

/* call fn(a, b); returns whatever fn left in r0 */
int hp_icall2(void *fn, unsigned a, unsigned b);

#endif /* HP_ICALL_H */
