/*
 * hp_string.h -- string utilities for TCC-compiled programs on the HP Prime.
 *
 * Adds the common <string.h>/<stdlib.h> functions missing from hp_rt.c.
 * Self-contained plain C compiled on the calculator (link hp_string.c).
 * Use:  #include "hp_string.h"
 */
#ifndef HP_STRING_H
#define HP_STRING_H

#ifndef SIZE_T_DEFINED
#define SIZE_T_DEFINED
typedef unsigned int size_t;
#endif
#define NULL ((void *)0)

/* ---- search ---- */
char  *strchr(const char *s, int c);
char  *strrchr(const char *s, int c);
char  *strstr(const char *haystack, const char *needle);
char  *strpbrk(const char *s, const char *accept);
size_t strspn(const char *s, const char *accept);
size_t strcspn(const char *s, const char *reject);
void  *memchr(const void *s, int c, size_t n);

/* ---- copy / concat ---- */
char  *strncpy(char *dst, const char *src, size_t n);
char  *strcat(char *dst, const char *src);
char  *strncat(char *dst, const char *src, size_t n);
void  *memmove(void *dst, const void *src, size_t n);
size_t strlcpy(char *dst, const char *src, size_t n);
size_t strlcat(char *dst, const char *src, size_t n);

/* ---- case-insensitive compare ---- */
int    strcasecmp(const char *a, const char *b);
int    strncasecmp(const char *a, const char *b, size_t n);

/* ---- conversions ---- */
int    atoi(const char *s);
long   atol(const char *s);
long   strtol(const char *s, char **endptr, int base);
char  *itoa(int value, char *buf, int base);
char  *ltoa(long value, char *buf, int base);

/* ---- character case ---- */
int    toupper(int c);
int    tolower(int c);
void   str_toupper(char *s);
void   str_tolower(char *s);

/* ---- allocation (uses malloc from hp_rt.c) ---- */
char  *strdup(const char *s);
char  *strndup(const char *s, size_t n);

/* ---- misc ---- */
char  *strrev(char *s);           /* reverses in place, returns s */

/* ---- double formatting (soft-float; needs rt_aeabi.o) ----
 * ftoa/dtoa format a double as fixed-point text with rounding into
 * buf (>= 40 bytes); returns buf.  NaN -> "NaN", +-INF -> "INF"/"-INF",
 * values >= 1e19 -> ">1e19".  dec is clamped to 0..15. */
char  *ftoa(double d, char *buf, int dec);
char  *dtoa(double d, char *buf, int dec);    /* alias for ftoa */

/* ---- double parsing (the input side of ftoa) ---- */
double strtod(const char *s, char **endptr);  /* decimal + exponent, inf/nan */
double atof(const char *s);                   /* strtod(s, NULL) */

#endif /* HP_STRING_H */
