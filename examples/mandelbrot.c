/* PRIME-C-CODE-BEGIN */
#include "prime.h"
#include "hp_gfx.h"
#include "hp_input.h"
#include "hp_sys.h"

/* ---- interactive Mandelbrot set renderer (fixed-point, pure int) ----
 * Arrows (0x02/0x03/0x04/0x05) pan the view; '+' (0xB9) zooms in,
 * '-' (0xB7) zooms out; q (0x51) / ON (0x83) / ESC (0x01) cancel the
 * current redraw, or exit when idle.  The viewport is clamped so the
 * center stays within one initial range of the origin and the range
 * stays in [R0/128, 4*R0].  MB_SCALE = 4096 (12 fractional bits). */

#define MB_MAXITER 128
#define MB_SCALE   4096            /* 1.0 == 4096 (12 fractional bits) */
#define MB_XMIN0   (-8192)         /* -2.0 */
#define MB_XMAX0   3277            /* 0.8  */
#define MB_YMIN0   (-4300)         /* -1.05 */
#define MB_YMAX0   4300            /* +1.05 */
#define MB_RX0     (MB_XMAX0 - MB_XMIN0)             /* 2.8 */
#define MB_RY0     (MB_YMAX0 - MB_YMIN0)             /* 2.1 */
#define MB_MINR    (MB_RX0 / 128)                    /* zoom-in limit */
#define MB_MAXR    (4 * MB_RX0)                      /* zoom-out limit */
/* cancel keys: physical scan codes verified against the hardware table
 * (see hp_input.h): q = 7/Q key, ON = 0x83, ESC = 0x01 */
#define MB_KEY_Q   HP_KEY_Q
#define MB_KEY_ON  HP_KEY_ON
#define MB_KEY_ESC HP_KEY_ESC
#define MB_KEY_ADD 0xB9            /* '+' (add) */
#define MB_KEY_SUB 0xB7            /* '-' (minus) */

static int mb_xmin, mb_xmax, mb_ymin, mb_ymax;   /* current viewport */

static int mb_is_cancel(int key)
{
    return key == MB_KEY_Q || key == MB_KEY_ON || key == MB_KEY_ESC;
}

/* color by iteration count: black = in the set, else a 7-band palette */
static hp_color mb_color(unsigned it)
{
    static const hp_color pal[7] = {
        HP_BLUE, HP_CYAN, HP_GREEN, HP_YELLOW, HP_ORANGE, HP_RED, HP_MAGENTA
    };
    if (it >= MB_MAXITER)
        return HP_BLACK;
    return pal[(it * 7u) / MB_MAXITER];
}

/* escape-time iteration for one pixel (fixed point, current viewport) */
static unsigned mb_iter(int px, int py, int w, int h)
{
    int cr = mb_xmin + (int)(((long)(mb_xmax - mb_xmin) * px) / w);
    int ci = mb_ymin + (int)(((long)(mb_ymax - mb_ymin) * py) / h);
    int zr = 0, zi = 0;
    unsigned it = 0;
    while (it < MB_MAXITER) {
        int zr2 = (zr * zr) >> 12;      /* / MB_SCALE */
        int zi2 = (zi * zi) >> 12;
        if (zr2 + zi2 > (4 << 12))      /* |z|^2 > 4: escaped */
            break;
        zi = ((zr * zi) >> 11) + ci;    /* 2*zr*zi (+MB_SCALE) */
        zr = zr2 - zi2 + cr;
        it++;
    }
    return it;
}

/* clamp: center within +/- one initial range of the origin; range bounded */
static void mb_clamp(void)
{
    int xr = mb_xmax - mb_xmin, yr = mb_ymax - mb_ymin;
    int cx = mb_xmin + xr / 2, cy = mb_ymin + yr / 2;
    int ccx = (MB_XMIN0 + MB_XMAX0) / 2;
    int ccy = (MB_YMIN0 + MB_YMAX0) / 2;
    if (xr < MB_MINR) xr = MB_MINR;
    if (xr > MB_MAXR) xr = MB_MAXR;
    if (yr < MB_MINR / 2) yr = MB_MINR / 2;
    if (yr > 2 * MB_RY0)  yr = 2 * MB_RY0;
    if (cx < ccx - MB_RX0) cx = ccx - MB_RX0;
    if (cx > ccx + MB_RX0) cx = ccx + MB_RX0;
    if (cy < ccy - MB_RY0) cy = ccy - MB_RY0;
    if (cy > ccy + MB_RY0) cy = ccy + MB_RY0;
    mb_xmin = cx - xr / 2;
    mb_xmax = mb_xmin + xr;
    mb_ymin = cy - yr / 2;
    mb_ymax = mb_ymin + yr;
}

static void mb_pan(int fx, int fy)      /* fx/fy in percent of the range */
{
    int xr = mb_xmax - mb_xmin, yr = mb_ymax - mb_ymin;
    mb_xmin += (long)xr * fx / 100;
    mb_xmax += (long)xr * fx / 100;
    mb_ymin += (long)yr * fy / 100;
    mb_ymax += (long)yr * fy / 100;
    mb_clamp();
}

static void mb_zoom(int in)             /* 1 = in (x4/5), 0 = out (x5/4) */
{
    int xr = mb_xmax - mb_xmin, yr = mb_ymax - mb_ymin;
    int cx = mb_xmin + xr / 2, cy = mb_ymin + yr / 2;
    if (in) { xr = xr * 4 / 5; yr = yr * 4 / 5; }
    else    { xr = xr * 5 / 4; yr = yr * 5 / 4; }
    mb_xmin = cx - xr / 2;
    mb_ymin = cy - yr / 2;
    mb_xmax = mb_xmin + xr;
    mb_ymax = mb_ymin + yr;
    mb_clamp();
}

/* redraw the current viewport; returns 1 if interrupted, 0 when done */
static int mb_redraw(void)
{
    hp_event ev;
    int w, h, x, y;
    unsigned total = 0;
    w = hp_gfx_w(); h = hp_gfx_h();
    hp_clear(HP_BLACK);
    for (y = 0; y < h; y++) {
        /* interrupt check every 4 rows: q / ON / ESC cancels the draw */
        if ((y & 3) == 0) {
            __sleep(2);                 /* yield: OS input thread feeds hook */
            if (hp_poll_event(&ev) == HP_EV_KEY && hp_event_key_down(&ev)) {
                int key = hp_event_key(&ev);
                printf("KEY %02x\n", key, 0, 0, 0);
                if (mb_is_cancel(key)) return 1;
            }
        }
        for (x = 0; x < w; x++) {
            hp_pixel(x, y, mb_color(mb_iter(x, y, w, h)));
            total++;
        }
        if ((y & 15) == 0)
            printf("MB row %d\n", y, 0, 0, 0);
    }
    return 0;
}

int main(void) {
    hp_event ev;
    int key, t;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n", 0, 0, 0, 0); return 1; }
    if (!hp_input_install()) { printf("INPUT HOOK FAIL\n", 0, 0, 0, 0); return 1; }
    hp_clear(HP_BLACK);
    printf("MB start %dx%d\n", hp_gfx_w(), hp_gfx_h(), 0, 0);
    /* NOTE: no hp_sys_time()/hp_sys_max_alloc() here -- they were the
     * first candidates for the on-device reboot before the image appeared
     * (svc 0x100A5 and multi-hundred-KB malloc/free probes are not fully
     * hardware-verified yet).  The draw/loop below is the proven surface. */
    mb_xmin = MB_XMIN0; mb_xmax = MB_XMAX0;
    mb_ymin = MB_YMIN0; mb_ymax = MB_YMAX0;

    for (;;) {
        if (mb_redraw()) {
            printf("MB_CANCEL\n", 0, 0, 0, 0);
        } else {
            printf("MB_DONE\n", 0, 0, 0, 0);
        }
        hp_text(4, 2, "MANDELBROT  arrows=move +-=zoom q/ON/ESC=exit",
                HP_WHITE);

        /* interactive loop: adjust the viewport, then redraw */
        for (;;) {
            __sleep(16);
            t = hp_poll_event(&ev);
            if (t != HP_EV_KEY || !hp_event_key_down(&ev))
                continue;
            key = hp_event_key(&ev);
            printf("KEY %02x\n", key, 0, 0, 0);
            if (mb_is_cancel(key)) {
                hp_input_remove();
                printf("MB_EXIT\n", 0, 0, 0, 0);
                return 0;
            }
            if (key == HP_KEY_LEFT)  { mb_pan(-10, 0); break; }
            if (key == HP_KEY_RIGHT) { mb_pan(10, 0);  break; }
            if (key == HP_KEY_UP)    { mb_pan(0, -10); break; }
            if (key == HP_KEY_DOWN)  { mb_pan(0, 10);  break; }
            if (key == MB_KEY_ADD)   { mb_zoom(1);     break; }
            if (key == MB_KEY_SUB)   { mb_zoom(0);     break; }
        }
    }
}
/* PRIME-C-CODE-END */
