/*
 * stdbool.h -- C99 boolean support for TCC on the HP Prime.
 *
 * TCC itself understands _Bool natively; this header (per C99 7.16)
 * just provides the spellings every C99 program expects.  prime.h
 * includes it, so plain `bool b = true;` works out of the box.
 */
#ifndef _STDBOOL_H
#define _STDBOOL_H

#define bool  _Bool
#define true  1
#define false 0
#define __bool_true_false_are_defined 1

#endif /* _STDBOOL_H */
