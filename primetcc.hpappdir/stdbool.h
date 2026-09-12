/*
 * stdbool.h —— HP Prime 上 TCC 的 C99 布尔支持。
 *
 * TCC 本身原生支持 _Bool；本头文件（按 C99 7.16）只是提供每个 C99
 * 程序都期望的写法。prime.h 会包含它，因此直接写 `bool b = true;`
 * 即可开箱使用。
 */
#ifndef _STDBOOL_H
#define _STDBOOL_H

#define bool  _Bool
#define true  1
#define false 0
#define __bool_true_false_are_defined 1

#endif /* _STDBOOL_H */
