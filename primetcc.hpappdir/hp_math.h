/*
 * hp_math.h -- simple math library for TCC-compiled programs on the HP Prime.
 *
 * Pure C implementations built on the soft-float runtime (rt_aeabi.o).
 * Target accuracy ~1e-8 (simple, compact — not full fdlibm).
 *
 * Usage:  #include "hp_math.h"   (link hp_math.c in the TCC command line)
 *
 * Printing doubles: the fixed-arg printf has no %f, so format with
 * ftoa/dtoa from hp_string.h and prints(buf) (hp_double_to_str below is
 * a legacy wrapper over ftoa -- same result, prefer ftoa/dtoa).
 */
#ifndef HP_MATH_H
#define HP_MATH_H

#define HP_PI   3.14159265358979323846
#define HP_2PI  6.28318530717958647692
#define HP_PI_2 1.57079632679489661923
#define HP_PI_4 0.78539816339744830962
#define HP_E    2.71828182845904523536
#define HP_LN2  0.69314718055994530942
#define HP_LN10 2.30258509299404568402

double hp_fabs(double x);
double hp_floor(double x);
double hp_ceil(double x);
double hp_trunc(double x);
double hp_round(double x);
double hp_fmod(double x, double y);
double hp_frexp(double x, int *e);
double hp_ldexp(double x, int e);
double hp_modf(double x, double *ip);

double hp_sqrt(double x);
double hp_exp(double x);
double hp_log(double x);
double hp_log10(double x);
double hp_pow(double x, double y);

double hp_sin(double x);
double hp_cos(double x);
double hp_tan(double x);
double hp_asin(double x);
double hp_acos(double x);
double hp_atan(double x);
double hp_atan2(double y, double x);

double hp_sinh(double x);
double hp_cosh(double x);
double hp_tanh(double x);

/* format a double into buf (e.g. "3.1416"); buf must hold >= 32 bytes */
void hp_double_to_str(char *buf, double d, int decimals);

#endif /* HP_MATH_H */
