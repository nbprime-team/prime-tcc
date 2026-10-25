/*
 * hp_sys.h -- system library for TCC-compiled programs on the HP Prime G1.
 *
 * Firmware interface per SYSLIB_README.md / README.md (workspace root):
 * the SVC stub table sits at 0x307FBCAC with 12 bytes per service and the
 * convention push{r0}; push{lr}; svc N.  Only CONFIRMED services are
 * exposed here; battery / RTC / uptime need hardware probing (marked in
 * SYSLIB_README.md) and are intentionally omitted.
 */
#ifndef HP_SYS_H
#define HP_SYS_H

typedef unsigned int size_t;

/* ---- memory (svc 0x10037-0x1003A: the firmware heap) ---- */
void  *hp_sys_malloc(size_t n);
void  *hp_sys_calloc(size_t n, size_t sz);
void  *hp_sys_realloc(void *p, size_t n);
void   hp_sys_free(void *p);
unsigned long hp_sys_max_alloc(void);       /* largest single block that fits
                                               (safe binary probe: alloc/free) */
unsigned long hp_sys_heap_free(void);       /* coarse free-heap estimate
                                               (= hp_sys_max_alloc) */

/* ---- system (confirmed SVCs) ---- */
void          hp_sys_sleep(unsigned ms);          /* svc 0x10008 */
unsigned long hp_sys_get_lcd(void);               /* svc 0x1008D: LCD struct ptr */
int           hp_sys_get_event(unsigned ev);      /* svc 0x1003F: blocking */
int           hp_sys_thread_create(unsigned fn, unsigned arg,
                                   unsigned stack);/* svc 0x10000 */

/* ---- debug device ---- */
/* fopen("debug") -> firmware handle 0xDEADC0DE (the read/write/call
 * interface main.py uses; see DOOM.hpappdir PrimeDebug). */
int hp_sys_debug_open(void);

/* ---- file IO (svc 0x1026F / 0x100CA-0x100D7); ASCII paths are converted
 * to UTF-16LE internally (the firmware requires UTF-16 paths).  Modes are
 * passed through: use "rb" / "wb+" (the only modes the firmware accepts). */
unsigned hp_sys_fopen(const char *ascii_path, const char *ascii_mode);
unsigned hp_sys_fclose(unsigned fd);
unsigned hp_sys_fread(unsigned buf, unsigned n, unsigned size, unsigned fd);
unsigned hp_sys_fwrite(unsigned buf, unsigned n, unsigned size, unsigned fd);
unsigned hp_sys_fseek(unsigned fd, unsigned off, unsigned whence);
unsigned hp_sys_ftell(unsigned fd);
unsigned hp_sys_filesize(unsigned fd);

#endif /* HP_SYS_H */
