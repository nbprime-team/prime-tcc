/*
 * hp_random.h -- PCG32 random numbers + deterministic value noise.
 *
 * Games and procedural graphics need a small, fast, decent PRNG.
 * PCG32 (O'Neill) is 3 lines, full-period, and passes statistical tests;
 * value noise gives deterministic smooth noise from integer coordinates
 * (no state), useful for terrain/clouds/starfields.
 *
 *   hp_rng r;  hp_rng_seed(&r, 12345);
 *   unsigned v = hp_rng_u32(&r);
 *   int d = hp_rng_range(&r, 1, 6);          dice
 *   hp_fx n = hp_noise2_fx(hp_fx_int(3), hp_fx_int(4), 7);
 *
 * hp_random.h includes hp_fixmath.h for the hp_fx helpers.  Compiled into
 * rt_core.o; pure C, no firmware calls.
 */
#ifndef HP_RANDOM_H
#define HP_RANDOM_H

#include "hp_fixmath.h"

typedef struct hp_rng {
    unsigned long long state;   /* PCG32 state */
} hp_rng;

/* PCG32 */
void     hp_rng_seed(hp_rng *r, unsigned seed);
unsigned hp_rng_u32(hp_rng *r);                 /* [0, 2^32) */
int      hp_rng_range(hp_rng *r, int lo, int hi);   /* inclusive [lo, hi] */
hp_fx    hp_rng_fx(hp_rng *r);                  /* [0, 1) in Q16.16 */

/* deterministic value noise (no state; same inputs -> same output) */
unsigned hp_noise2_hash(int x, int y, unsigned seed);   /* 32-bit hash */
hp_fx    hp_noise2_fx(hp_fx x, hp_fx y, unsigned seed); /* [0,1) smooth */

#endif /* HP_RANDOM_H */
