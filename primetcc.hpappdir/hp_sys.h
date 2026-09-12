/*
 * hp_sys.h —— HP Prime G1 上 TCC 编译程序的系统库。
 *
 * 固件接口：SVC 桩表位于 0x307FBCAC，每项 12 字节，约定为
 * push{r0}; push{lr}; svc N。此处只暴露已确认的服务；电池 / RTC /
 * 运行时间需要硬件探测，故意不提供。
 */
#ifndef HP_SYS_H
#define HP_SYS_H

/* size_t：与 prime.h / hp_string.h 共用同一 guard。 */
#ifndef PRIME_SIZE_T_DEFINED
#define PRIME_SIZE_T_DEFINED
#define SIZE_T_DEFINED
#if defined(__SIZE_TYPE__)
typedef __SIZE_TYPE__ size_t;
#else
typedef unsigned int size_t;
#endif
#endif

/* ---- 内存（svc 0x10037-0x1003A：固件堆） ---- */
void  *hp_sys_malloc(size_t n);
void  *hp_sys_calloc(size_t n, size_t sz);
void  *hp_sys_realloc(void *p, size_t n);
void   hp_sys_free(void *p);
unsigned long hp_sys_max_alloc(void);       /* 能容纳的最大单块
                                               （安全的 alloc/free 二分探测） */
unsigned long hp_sys_heap_free(void);       /* 堆剩余粗估
                                               （= hp_sys_max_alloc） */

/* ---- 系统（已确认的 SVC） ---- */
void          hp_sys_sleep(unsigned ms);          /* svc 0x10008 */
unsigned long hp_sys_get_lcd(void);               /* svc 0x1008D：LCD 结构指针 */
int           hp_sys_get_event(unsigned ev);      /* svc 0x1003F：阻塞 */
int           hp_sys_thread_create(unsigned fn, unsigned arg,
                                   unsigned stack);/* svc 0x10000 */

/* ---- 调试设备 ---- */
/* fopen("debug") -> 固件句柄 0xDEADC0DE（main.py 使用的读/写/调用接口；
 * 见 DOOM.hpappdir 的 PrimeDebug）。 */
int hp_sys_debug_open(void);

/* ---- 文件 IO（svc 0x1026F / 0x100CA-0x100D7）；ASCII 路径内部转为
 * UTF-16LE（固件要求 UTF-16 路径）。模式直接透传：用 "rb" / "wb+"
 * （固件只接受这两种模式）。 */
unsigned hp_sys_fopen(const char *ascii_path, const char *ascii_mode);
unsigned hp_sys_fclose(unsigned fd);
unsigned hp_sys_fread(unsigned buf, unsigned n, unsigned size, unsigned fd);
unsigned hp_sys_fwrite(unsigned buf, unsigned n, unsigned size, unsigned fd);
unsigned hp_sys_fseek(unsigned fd, unsigned off, unsigned whence);
unsigned hp_sys_ftell(unsigned fd);
unsigned hp_sys_filesize(unsigned fd);

#endif /* HP_SYS_H */
