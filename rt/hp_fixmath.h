/*
 * hp_fixmath.h -- Q16.16 fixed-point math for TCC programs on the HP Prime.
 *
 * The Prime G1 has no FPU: soft-float `double` is correct but slow, so
 * game/graphics hot loops should use fixed point.  This library provides
 * the core Q16.16 toolkit -- mul/div (64-bit intermediate), sqrt, sin/cos
 * (512-entry table + linear interpolation, ~1e-6), atan2 (CORDIC, ~3e-5)
 * -- plus conversions to/from int and double.
 *
 *   hp_fx r = hp_fx_mul(hp_fx_int(3), hp_fx_div(hp_fx_int(1), hp_fx_int(4)));
 *   hp_fx s = hp_fx_sin(hp_fx_mul(hp_fx_int(2), HP_FX_PI));   ~0
 *   hp_fx a = hp_fx_atan2(hp_fx_int(1), hp_fx_int(1));         pi/4
 *
 * 1.0 == HP_FX_ONE (65536).  All functions are pure C (TCC-compilable),
 * no global state, no firmware calls.  Compiled into rt_core.o.
 */
#ifndef HP_FIXMATH_H
#define HP_FIXMATH_H

typedef int hp_fx;                 /* Q16.16 signed fixed point */

#define HP_FX_ONE   65536
#define HP_FX_PI    205887         /* pi      * 65536 */
#define HP_FX_PI_2  102944         /* pi/2    * 65536 */
#define HP_FX_PI_4  51472          /* pi/4    * 65536 */
#define HP_FX_2PI   411775         /* 2pi     * 65536 */
#define HP_FX_E     178145         /* e       * 65536 */

/* conversions */
hp_fx   hp_fx_int(int v);          /* int -> fx                */
int     hp_fx_trunc(hp_fx x);      /* fx -> int (toward zero)  */
int     hp_fx_round(hp_fx x);      /* fx -> int (nearest)      */
double  hp_fx_to_double(hp_fx x);
hp_fx   hp_fx_from_double(double d);

/* arithmetic (mul/div use a 64-bit intermediate) */
hp_fx   hp_fx_neg(hp_fx a);
hp_fx   hp_fx_add(hp_fx a, hp_fx b);
hp_fx   hp_fx_sub(hp_fx a, hp_fx b);
hp_fx   hp_fx_mul(hp_fx a, hp_fx b);
hp_fx   hp_fx_div(hp_fx a, hp_fx b);
hp_fx   hp_fx_abs(hp_fx a);
hp_fx   hp_fx_lerp(hp_fx a, hp_fx b, hp_fx t);   /* a + (b-a)*t, t in [0,1] */

/* transcendental (radians) */
hp_fx   hp_fx_sqrt(hp_fx x);       /* x >= 0                   */
hp_fx   hp_fx_sin(hp_fx rad);
hp_fx   hp_fx_cos(hp_fx rad);
hp_fx   hp_fx_tan(hp_fx rad);      /* undefined near +-pi/2     */
hp_fx   hp_fx_atan2(hp_fx y, hp_fx x);   /* result in [-pi, pi] */

#endif /* HP_FIXMATH_H */
