/*
 * hp_input.c -- keyboard + touch input for TCC-compiled programs on the
 * HP Prime G1, DOOM-port style.
 *
 * Why a hook?  The firmware's get_event (svc 0x1003f) is *blocking* and
 * owned by the OS UI event loop: calling it directly from an app thread
 * blocks forever (verified on hardware: the demo froze on the first
 * poll).  The working PureDOOM port solves this by patching the firmware
 * API slot 0x307fbfa0 with an 8-byte trampoline:
 *
 *     slot[0] = 0xe51ff004            ; ldr pc, [pc, #-4]
 *     slot[1] = &hp_input_hook
 *
 * The OS UI loop calls get_event via that slot, so every input event
 * first goes through hp_input_hook() (running on the OS thread).  The
 * hook fetches the raw event with the real get_event (svc 0x1003f --
 * which does NOT dispatch through the patched slot, so no recursion)
 * and copies key/touch info into a small SPSC ring that the app thread
 * polls non-blocking.  Restore the slot (hp_input_remove) on exit so the
 * calculator UI works normally afterwards.
 *
 * Event layout (from PureDOOM's my_get_event_hook):
 *   ev->[4]  = 0x00100010 key / 15 touch / other = none
 *   key:  [28] = 16 down / 0x100000 up ;  [34] = u16 scan code
 *   touch: [24] = u16 count; item i at 28+12*i: [0]=u32 type,
 *          [4]=u16 (0=valid), [6]=u16 x, [8]=u16 y
 */
#include "hp_input.h"

/* firmware get_event API slot (svc 0x1003f), same one PureDOOM patches */
#define HP_FW_EVENT_SLOT 0x307fbfa0u

/* ---- firmware get_event (rt_svc.o) ---- */
unsigned hp_svc_get_event(unsigned ev);

/* ---- SPSC ring queue (hook writes head, app reads tail) ---- */
#define HP_Q_SIZE 64
struct hp_qitem {
    unsigned char  type;    /* 1 = key, 2 = touch */
    unsigned char  down;    /* key: 1 press, 0 release */
    unsigned short key;     /* key: physical scan code */
    unsigned short x, y;    /* touch: screen coords */
};
static struct hp_qitem g_q[HP_Q_SIZE];
static volatile int g_head;          /* write index (hook / OS thread) */
static volatile int g_tail;          /* read index (app thread) */
static volatile int g_hooked;        /* slot currently patched */

static unsigned char g_saved[16];    /* original slot bytes */

static int q_push(unsigned char type, unsigned char down,
                  unsigned short key, unsigned short x, unsigned short y)
{
    int h = g_head;
    int n = (h + 1) & (HP_Q_SIZE - 1);
    if (n == g_tail)
        return 0;                     /* queue full, drop */
    g_q[h].type = type;
    g_q[h].down = down;
    g_q[h].key = key;
    g_q[h].x = x;
    g_q[h].y = y;
    g_head = n;
    return 1;
}

/* called by the OS UI event loop (via the patched slot), OS thread */
static void hp_input_hook(void *ev)
{
    unsigned char *e = (unsigned char *)ev;
    unsigned type;
    int i, n;
    if (!g_hooked)
        return;
    hp_svc_get_event((unsigned)ev);          /* real get_event (BLOCKS) */
    /* the app thread may have removed the hook while we were blocked in
     * get_event; re-check before touching the queue / user memory */
    if (!g_hooked)
        return;
    type = *(unsigned *)(e + 4);
    if (type == 0x00100010u) {               /* key */
        unsigned sub = *(unsigned *)(e + 28);
        q_push(1, sub == 16u ? 1 : 0,
               *(unsigned short *)(e + 34), 0, 0);
    } else if (type == 15u) {                /* touch */
        n = *(unsigned short *)(e + 24);
        if (n > 8)
            n = 8;
        for (i = 0; i < n; i++) {
            unsigned char *p = e + 28 + 12 * i;
            if (*(unsigned short *)(p + 4) != 0)
                continue;                    /* invalid item */
            q_push(2, 0, 0,
                   *(unsigned short *)(p + 6), *(unsigned short *)(p + 8));
        }
    }
}

int hp_input_install(void)
{
    unsigned *slot = (unsigned *)HP_FW_EVENT_SLOT;
    int i;
    if (g_hooked)
        return 1;
    if (slot[0] == 0xe51ff004u)              /* already patched */
        return 0;
    for (i = 0; i < 16; i++)
        g_saved[i] = ((unsigned char *)slot)[i];
    slot[0] = 0xe51ff004u;                   /* ldr pc, [pc, #-4] */
    slot[1] = (unsigned)hp_input_hook;
    g_hooked = 1;
    g_head = 0;
    g_tail = 0;
    return 1;
}

void hp_input_remove(void)
{
    unsigned char *slot = (unsigned char *)HP_FW_EVENT_SLOT;
    int i;
    if (!g_hooked)
        return;
    for (i = 0; i < 16; i++)
        slot[i] = g_saved[i];
    g_hooked = 0;
}

int hp_poll_event(hp_event *ev)
{
    int t, n, i;
    unsigned char *e;
    if (!ev)
        return HP_EV_NONE;
    t = g_tail;
    if (t == g_head)
        return HP_EV_NONE;
    e = (unsigned char *)ev;
    for (i = 0; i < 128; i++)
        e[i] = 0;
    n = (t + 1) & (HP_Q_SIZE - 1);
    if (g_q[t].type == 1) {                  /* key */
        *(unsigned *)(e + 4) = 0x00100010u;
        *(unsigned *)(e + 28) = g_q[t].down ? 16u : 0x100000u;
        *(unsigned short *)(e + 34) = g_q[t].key;
    } else {                                 /* touch */
        *(unsigned *)(e + 4) = 15u;
        *(unsigned short *)(e + 24) = 1;
        *(unsigned *)(e + 28) = 1u;
        *(unsigned short *)(e + 34) = g_q[t].x;
        *(unsigned short *)(e + 36) = g_q[t].y;
    }
    g_tail = n;
    return g_q[t].type == 1 ? HP_EV_KEY : HP_EV_TOUCH;
}

int hp_event_key(const hp_event *ev)
{
    return *(unsigned short *)((char *)ev + 34);
}

int hp_event_key_down(const hp_event *ev)
{
    return *(unsigned *)((char *)ev + 28) == HP_EV_KEY_DOWN;
}

int hp_event_touch_count(const hp_event *ev)
{
    return *(unsigned short *)((char *)ev + 24);
}

int hp_event_touch(const hp_event *ev, int i, int *x, int *y)
{
    char *p = (char *)ev + 28 + 12 * i;
    if (*(unsigned short *)(p + 4) != 0)
        return 0;
    if (x)
        *x = *(unsigned short *)(p + 6);
    if (y)
        *y = *(unsigned short *)(p + 8);
    return *(unsigned *)p;
}
