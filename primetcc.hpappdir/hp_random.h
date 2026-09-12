/*
 * hp_random.h —— PCG32 随机数 + 确定性值噪声。
 *
 * 游戏与过程式图形需要小、快、质量尚可的 PRNG。PCG32（O'Neill）只需
 * 3 行、全周期、可通过统计检验；值噪声从整数坐标给出确定性平滑噪声
 * （无状态），适合地形/云/星场。
 *
 *   hp_rng r;  hp_rng_seed(&r, 12345);
 *   unsigned v = hp_rng_u32(&r);
 *   int d = hp_rng_range(&r, 1, 6);          骰子
 *   hp_fx n = hp_noise2_fx(hp_fx_int(3), hp_fx_int(4), 7);
 *
 * hp_random.h 为 hp_fx 辅助函数而包含 hp_fixmath.h。编入 rt_core.o；
 * 纯 C，无固件调用。
 */
#ifndef HP_RANDOM_H
#define HP_RANDOM_H

#include "hp_fixmath.h"

typedef struct hp_rng {
    unsigned long long state;   /* PCG32 状态 */
} hp_rng;

/* PCG32 */
void     hp_rng_seed(hp_rng *r, unsigned seed);
unsigned hp_rng_u32(hp_rng *r);                 /* [0, 2^32) */
int      hp_rng_range(hp_rng *r, int lo, int hi);   /* 闭区间 [lo, hi] */
hp_fx    hp_rng_fx(hp_rng *r);                  /* [0, 1) 的 Q16.16 */

/* 确定性值噪声（无状态；相同输入 -> 相同输出） */
unsigned hp_noise2_hash(int x, int y, unsigned seed);   /* 32 位哈希 */
hp_fx    hp_noise2_fx(hp_fx x, hp_fx y, unsigned seed); /* [0,1) 平滑 */

#endif /* HP_RANDOM_H */
