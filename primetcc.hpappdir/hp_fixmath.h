/*
 * hp_fixmath.h —— HP Prime 上 TCC 程序的 Q16.16 定点数学。
 *
 * Prime G1 没有 FPU：软浮点 `double` 正确但慢，因此游戏/图形热循环应
 * 用定点。本库提供核心 Q16.16 工具——mul/div（64 位中间量）、sqrt、
 * sin/cos（512 项表 + 线性插值，约 1e-6）、atan2（CORDIC，约 3e-5）
 * ——以及 int/double 的双向转换。
 *
 *   hp_fx r = hp_fx_mul(hp_fx_int(3), hp_fx_div(hp_fx_int(1), hp_fx_int(4)));
 *   hp_fx s = hp_fx_sin(hp_fx_mul(hp_fx_int(2), HP_FX_PI));   ~0
 *   hp_fx a = hp_fx_atan2(hp_fx_int(1), hp_fx_int(1));         pi/4
 *
 * 1.0 == HP_FX_ONE (65536)。全部为纯 C（可被 TCC 编译），无全局状态、
 * 无固件调用。编入 rt_core.o。
 */
#ifndef HP_FIXMATH_H
#define HP_FIXMATH_H

typedef int hp_fx;                 /* Q16.16 有符号定点 */

#define HP_FX_ONE   65536
#define HP_FX_PI    205887         /* pi      * 65536 */
#define HP_FX_PI_2  102944         /* pi/2    * 65536 */
#define HP_FX_PI_4  51472          /* pi/4    * 65536 */
#define HP_FX_2PI   411775         /* 2pi     * 65536 */
#define HP_FX_E     178145         /* e       * 65536 */

/* 转换 */
hp_fx   hp_fx_int(int v);          /* int -> fx                */
int     hp_fx_trunc(hp_fx x);      /* fx -> int（向零取整）    */
int     hp_fx_round(hp_fx x);      /* fx -> int（最近取整）    */
double  hp_fx_to_double(hp_fx x);
hp_fx   hp_fx_from_double(double d);

/* 运算（mul/div 使用 64 位中间量） */
hp_fx   hp_fx_neg(hp_fx a);
hp_fx   hp_fx_add(hp_fx a, hp_fx b);
hp_fx   hp_fx_sub(hp_fx a, hp_fx b);
hp_fx   hp_fx_mul(hp_fx a, hp_fx b);
hp_fx   hp_fx_div(hp_fx a, hp_fx b);
hp_fx   hp_fx_abs(hp_fx a);
hp_fx   hp_fx_lerp(hp_fx a, hp_fx b, hp_fx t);   /* a + (b-a)*t，t ∈ [0,1] */

/* 超越函数（弧度） */
hp_fx   hp_fx_sqrt(hp_fx x);       /* x >= 0                   */
hp_fx   hp_fx_sin(hp_fx rad);
hp_fx   hp_fx_cos(hp_fx rad);
hp_fx   hp_fx_tan(hp_fx rad);      /* 在 +-pi/2 附近无定义      */
hp_fx   hp_fx_atan2(hp_fx y, hp_fx x);   /* 结果在 [-pi, pi] */

#endif /* HP_FIXMATH_H */
