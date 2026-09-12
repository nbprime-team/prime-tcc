/*
 * hp_codec.h -- CRC32 / Adler-32 checksums + hex / base64 codecs.
 *
 * Small, dependency-free utilities for asset integrity and data exchange:
 *   unsigned c = hp_crc32(buf, n);        IEEE 802.3, reflected
 *   unsigned a = hp_adler32(buf, n);      zlib Adler-32
 *   int len = hp_hex_encode(dst, src, n); 2n lowercase hex chars
 *   int len = hp_b64_encode(dst, src, n); base64 with '=' padding
 *
 * hex/base64 decode return the decoded length, or -1 on invalid input.
 * hp_b64_encode writes dst[0..len) and terminates with NUL.
 * Compiled into rt_core.o; pure C, no firmware calls.
 */
#ifndef HP_CODEC_H
#define HP_CODEC_H

unsigned hp_crc32(const void *buf, unsigned len);   /* init 0xFFFFFFFF, xor-out */
unsigned hp_adler32(const void *buf, unsigned len); /* Adler-32 (mod 65521)     */

int hp_hex_encode(char *dst, const void *src, unsigned n);   /* -> 2n, NUL-terminated */
int hp_hex_decode(void *dst, const char *src, unsigned n);   /* n = hex chars; -> n/2, -1 on bad */

int hp_b64_encode(char *dst, const void *src, unsigned n);   /* -> encoded len, NUL-terminated */
int hp_b64_decode(void *dst, const char *src, unsigned n);   /* n = encoded len; -> bytes, -1 on bad */

#endif /* HP_CODEC_H */
