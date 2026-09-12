/*
 * hp_math.h —— HP Prime 上 TCC 编译程序的简单数学库。
 *
 * 基于软浮点运行时（rt_aeabi.o）的纯 C 实现。
 * 目标精度约 1e-8（简单紧凑，非完整 fdlibm）。
 *
 * 用法：#include "hp_math.h"（TCC 命令行里链接 hp_math.c）
 *
 * 打印 double：定参 printf 没有 %f，改用 hp_string.h 的 ftoa/dtoa
 * 格式化后再 prints(buf)（下面的 hp_double_to_str 是 ftoa 的旧包装，
 * 结果相同，优先用 ftoa/dtoa）。
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

/* 把 double 格式化进 buf（如 "3.1416"）；buf 至少 32 字节 */
void hp_double_to_str(char *buf, double d, int decimals);

#endif /* HP_MATH_H */
