/*
 * hp_string.h —— HP Prime 上 TCC 编译程序的字符串工具。
 *
 * 补充 hp_rt.c 缺失的常见 <string.h>/<stdlib.h> 函数。
 * 自包含的纯 C，在计算器上编译（链接 hp_string.c）。
 * 用法：#include "hp_string.h"
 */
#ifndef HP_STRING_H
#define HP_STRING_H

/* size_t：与 prime.h 共用同一 guard，避免两个头同时被包含时重复定义。 */
#ifndef PRIME_SIZE_T_DEFINED
#define PRIME_SIZE_T_DEFINED
#define SIZE_T_DEFINED
#if defined(__SIZE_TYPE__)
typedef __SIZE_TYPE__ size_t;
#else
typedef unsigned int size_t;
#endif
#endif
#define NULL ((void *)0)

/* ---- 查找 ---- */
char  *strchr(const char *s, int c);
char  *strrchr(const char *s, int c);
char  *strstr(const char *haystack, const char *needle);
char  *strpbrk(const char *s, const char *accept);
size_t strspn(const char *s, const char *accept);
size_t strcspn(const char *s, const char *reject);
void  *memchr(const void *s, int c, size_t n);

/* ---- 拷贝 / 拼接 ---- */
char  *strncpy(char *dst, const char *src, size_t n);
char  *strcat(char *dst, const char *src);
char  *strncat(char *dst, const char *src, size_t n);
void  *memmove(void *dst, const void *src, size_t n);
size_t strlcpy(char *dst, const char *src, size_t n);
size_t strlcat(char *dst, const char *src, size_t n);

/* ---- 忽略大小写比较 ---- */
int    strcasecmp(const char *a, const char *b);
int    strncasecmp(const char *a, const char *b, size_t n);

/* ---- 转换 ---- */
int    atoi(const char *s);
long   atol(const char *s);
long   strtol(const char *s, char **endptr, int base);
char  *itoa(int value, char *buf, int base);
char  *ltoa(long value, char *buf, int base);

/* ---- 字符大小写 ---- */
int    toupper(int c);
int    tolower(int c);
void   str_toupper(char *s);
void   str_tolower(char *s);

/* ---- 分配（使用 hp_rt.c 的 malloc） ---- */
char  *strdup(const char *s);
char  *strndup(const char *s, size_t n);

/* ---- 杂项 ---- */
char  *strrev(char *s);           /* 原地反转，返回 s */

/* ---- double 格式化（软浮点；需要 rt_aeabi.o）----
 * ftoa/dtoa 把 double 按定点文本四舍五入写入 buf（>= 40 字节），返回
 * buf。NaN -> "NaN"，+-INF -> "INF"/"-INF"，>= 1e19 -> ">1e19"。
 * dec 被钳制到 0..15。 */
char  *ftoa(double d, char *buf, int dec);
char  *dtoa(double d, char *buf, int dec);    /* ftoa 的别名 */

/* ---- double 解析（ftoa 的输入侧） ---- */
double strtod(const char *s, char **endptr);  /* 十进制 + 指数，inf/nan */
double atof(const char *s);                   /* strtod(s, NULL) */

#endif /* HP_STRING_H */
