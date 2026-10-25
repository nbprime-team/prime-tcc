/*
 * hp_string.c -- string utilities (see hp_string.h).
 * Self-contained plain C, TCC-compilable on the calculator.
 */
#include "hp_string.h"

/* ---- memory helpers (extern from hp_rt.c) ---- */
extern size_t strlen(const char *s);
extern int    strcmp(const char *a, const char *b);
extern int    strncmp(const char *a, const char *b, size_t n);
extern char  *strcpy(char *d, const char *s);
extern void  *memcpy(void *d, const void *s, size_t n);
extern void  *memset(void *d, int c, size_t n);
extern void  *malloc(size_t n);
extern void   free(void *p);

/* ---- search ---- */

char *strchr(const char *s, int c)
{
    while (*s) {
        if (*s == (char)c)
            return (char *)s;
        s++;
    }
    return c == 0 ? (char *)s : NULL;
}

char *strrchr(const char *s, int c)
{
    const char *last = NULL;
    while (*s) {
        if (*s == (char)c)
            last = s;
        s++;
    }
    if (c == 0)
        return (char *)s;
    return (char *)last;
}

char *strstr(const char *hay, const char *needle)
{
    size_t nlen, i;
    if (!*needle)
        return (char *)hay;
    nlen = strlen(needle);
    while (*hay) {
        if (*hay == *needle) {
            for (i = 1; i < nlen; i++)
                if (hay[i] != needle[i])
                    break;
            if (i == nlen)
                return (char *)hay;
        }
        hay++;
    }
    return NULL;
}

char *strpbrk(const char *s, const char *accept)
{
    while (*s) {
        const char *a = accept;
        while (*a) {
            if (*a == *s)
                return (char *)s;
            a++;
        }
        s++;
    }
    return NULL;
}

size_t strspn(const char *s, const char *accept)
{
    size_t n = 0;
    while (s[n]) {
        const char *a = accept;
        while (*a && *a != s[n])
            a++;
        if (!*a)
            break;
        n++;
    }
    return n;
}

size_t strcspn(const char *s, const char *reject)
{
    size_t n = 0;
    while (s[n]) {
        const char *a = reject;
        while (*a && *a != s[n])
            a++;
        if (*a)
            break;
        n++;
    }
    return n;
}

void *memchr(const void *s, int c, size_t n)
{
    const unsigned char *p = s;
    while (n--) {
        if (*p == (unsigned char)c)
            return (void *)p;
        p++;
    }
    return NULL;
}

/* ---- copy / concat ---- */

char *strncpy(char *dst, const char *src, size_t n)
{
    size_t i = 0;
    while (i < n && src[i]) {
        dst[i] = src[i];
        i++;
    }
    while (i < n)
        dst[i++] = 0;
    return dst;
}

char *strcat(char *dst, const char *src)
{
    char *d = dst + strlen(dst);
    while (*src)
        *d++ = *src++;
    *d = 0;
    return dst;
}

char *strncat(char *dst, const char *src, size_t n)
{
    char *d = dst + strlen(dst);
    while (n-- && *src)
        *d++ = *src++;
    *d = 0;
    return dst;
}

void *memmove(void *dst, const void *src, size_t n)
{
    unsigned char *d = dst;
    const unsigned char *s = src;
    if (d < s) {
        while (n--)
            *d++ = *s++;
    } else if (d > s) {
        d += n;
        s += n;
        while (n--)
            *--d = *--s;
    }
    return dst;
}

size_t strlcpy(char *dst, const char *src, size_t n)
{
    size_t len = strlen(src);
    if (n) {
        size_t k = len < n - 1 ? len : n - 1;
        memcpy(dst, src, k);
        dst[k] = 0;
    }
    return len;
}

size_t strlcat(char *dst, const char *src, size_t n)
{
    size_t dlen = strlen(dst);
    size_t slen = strlen(src);
    if (dlen >= n)
        return n + slen;
    if (slen >= n - dlen)
        slen = n - dlen - 1;
    memcpy(dst + dlen, src, slen);
    dst[dlen + slen] = 0;
    return dlen + strlen(src);
}

/* ---- case-insensitive compare ---- */

int strcasecmp(const char *a, const char *b)
{
    unsigned char ca, cb;
    while (*a && *b) {
        ca = *a; cb = *b;
        if (ca >= 'A' && ca <= 'Z') ca += 32;
        if (cb >= 'A' && cb <= 'Z') cb += 32;
        if (ca != cb)
            return ca - cb;
        a++; b++;
    }
    ca = *a; cb = *b;
    if (ca >= 'A' && ca <= 'Z') ca += 32;
    if (cb >= 'A' && cb <= 'Z') cb += 32;
    return ca - cb;
}

int strncasecmp(const char *a, const char *b, size_t n)
{
    size_t i = 0;
    unsigned char ca, cb;
    for (i = 0; i < n; i++) {
        ca = (unsigned char)a[i];
        cb = (unsigned char)b[i];
        if (ca >= 'A' && ca <= 'Z') ca += 32;
        if (cb >= 'A' && cb <= 'Z') cb += 32;
        if (ca != cb)
            return ca - cb;
        if (ca == 0)
            return 0;
    }
    return 0;
}

/* ---- conversions ---- */

static long strtol_base(const char *s, char **endptr, int base, int sign_ok)
{
    long v = 0;
    int neg = 0, any = 0, c;

    while (*s == ' ' || *s == '\t' || *s == '\n' ||
           *s == '\r' || *s == '\v' || *s == '\f')
        s++;
    if (sign_ok && (*s == '+' || *s == '-')) {
        neg = *s == '-';
        s++;
    }
    if (base == 0) {
        base = 10;
        if (*s == '0') {
            s++;
            if (*s == 'x' || *s == 'X') { base = 16; s++; }
            else base = 8;
        }
    } else if (base == 16 && *s == '0' && (s[1] == 'x' || s[1] == 'X')) {
        s += 2;
    }
    for (;;) {
        c = (unsigned char)*s;
        if (c >= '0' && c <= '9') c -= '0';
        else if (c >= 'a' && c <= 'f') c -= 'a' - 10;
        else if (c >= 'A' && c <= 'F') c -= 'A' - 10;
        else break;
        if (c >= base)
            break;
        v = v * base + c;
        any = 1;
        s++;
    }
    if (endptr)
        *endptr = (char *)(any ? s : s);
    return neg ? -v : v;
}

int atoi(const char *s)
{
    return (int)strtol_base(s, NULL, 10, 1);
}

long atol(const char *s)
{
    return strtol_base(s, NULL, 10, 1);
}

long strtol(const char *s, char **endptr, int base)
{
    return strtol_base(s, endptr, base, 1);
}

char *itoa(int value, char *buf, int base)
{
    char tmp[24];
    unsigned long v;
    int i = 0, neg = 0;
    char *start = buf;
    if (base == 10 && value < 0) {
        neg = 1;
        v = (unsigned long)(-(long)value);
    } else {
        v = (unsigned long)value;
    }
    if (v == 0)
        tmp[i++] = '0';
    while (v) {
        int d = v % (unsigned)base;
        tmp[i++] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
        v /= (unsigned)base;
    }
    if (neg)
        tmp[i++] = '-';
    while (i)
        *buf++ = tmp[--i];
    *buf = 0;
    return start;
}

char *ltoa(long value, char *buf, int base)
{
    char tmp[40];
    unsigned long v;
    int i = 0, neg = 0;
    if (base == 10 && value < 0) {
        neg = 1;
        v = (unsigned long)(-(long)value);
    } else {
        v = (unsigned long)value;
    }
    if (v == 0)
        tmp[i++] = '0';
    while (v) {
        int d = v % (unsigned)base;
        tmp[i++] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
        v /= (unsigned)base;
    }
    if (neg)
        tmp[i++] = '-';
    while (i)
        *buf++ = tmp[--i];
    *buf = 0;
    return buf;
}

/* ---- character case ---- */

int toupper(int c)
{
    return (c >= 'a' && c <= 'z') ? c - 32 : c;
}

int tolower(int c)
{
    return (c >= 'A' && c <= 'Z') ? c + 32 : c;
}

void str_toupper(char *s)
{
    while (*s) { *s = toupper(*s); s++; }
}

void str_tolower(char *s)
{
    while (*s) { *s = tolower(*s); s++; }
}

/* ---- allocation ---- */

char *strdup(const char *s)
{
    size_t n = strlen(s) + 1;
    char *p = malloc(n);
    if (p)
        memcpy(p, s, n);
    return p;
}

char *strndup(const char *s, size_t n)
{
    size_t k = 0;
    char *p;
    while (k < n && s[k])
        k++;
    p = malloc(k + 1);
    if (p) {
        memcpy(p, s, k);
        p[k] = 0;
    }
    return p;
}

/* ---- misc ---- */

char *strrev(char *s)
{
    size_t i = 0, j = strlen(s);
    while (i < j) {
        char c = s[i];
        s[i] = s[--j];
        s[j] = c;
        i++;
    }
    return s;
}
