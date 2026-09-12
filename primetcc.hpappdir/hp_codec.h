/*
 * hp_codec.h —— CRC32 / Adler-32 校验 + hex / base64 编解码。
 *
 * 用于资源完整性与数据交换的小型、无依赖工具：
 *   unsigned c = hp_crc32(buf, n);        IEEE 802.3，反射
 *   unsigned a = hp_adler32(buf, n);      zlib Adler-32
 *   int len = hp_hex_encode(dst, src, n); 2n 个小写十六进制字符
 *   int len = hp_b64_encode(dst, src, n); 带 '=' 填充的 base64
 *
 * hex/base64 解码返回解码后长度，输入非法返回 -1。
 * hp_b64_encode 写出 dst[0..len) 并以 NUL 结尾。
 * 编入 rt_core.o；纯 C，无固件调用。
 */
#ifndef HP_CODEC_H
#define HP_CODEC_H

unsigned hp_crc32(const void *buf, unsigned len);   /* 初值 0xFFFFFFFF，输出异或 */
unsigned hp_adler32(const void *buf, unsigned len); /* Adler-32（mod 65521）    */

int hp_hex_encode(char *dst, const void *src, unsigned n);   /* -> 2n，NUL 结尾 */
int hp_hex_decode(void *dst, const char *src, unsigned n);   /* n = hex 字符数；-> n/2，非法 -1 */

int hp_b64_encode(char *dst, const void *src, unsigned n);   /* -> 编码长度，NUL 结尾 */
int hp_b64_decode(void *dst, const char *src, unsigned n);   /* n = 编码长度；-> 字节数，非法 -1 */

#endif /* HP_CODEC_H */
