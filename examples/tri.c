/* PRIME-C-CODE-BEGIN */
#include "prime.h"
#include "hp_gfx.h"
#include "hp_input.h"
#include "hp_math.h"

/* ---- triangle + GROB geometry demo ----
 * Showcases the primetcc graphics additions:
 *   hp_triangle / hp_fill_triangle (outline + scanline fill)
 *   hp_grob_w / hp_grob_h (GROB dimensions), hp_target_w / hp_target_h
 * A fan of small filled triangles exercises the fast fill path (each is a
 * handful of clipped row fills), then a GROB is sized, drawn into with the
 * same primitives and blitted to the screen.
 * q (0x51) / ESC (0x01) / ON (0x83) exit.
 */

#define TWO_PI 6.283185307179586

static void fan(int cx, int cy, int r, int n, hp_color c)
{
    int i;
    for (i = 0; i < n; i++) {
        double a = TWO_PI * i / n;
        double b = TWO_PI * (i + 1) / n;
        hp_fill_triangle(
            cx + (int)(r * 0.45 * hp_cos(a)), cy + (int)(r * 0.45 * hp_sin(a)),
            cx + (int)(r * hp_cos(a)),         cy + (int)(r * hp_sin(a)),
            cx + (int)(r * hp_cos(b)),         cy + (int)(r * hp_sin(b)), c);
    }
}

int main(void) {
    hp_event ev;
    hp_grob *g;
    int t, key;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n"); return 1; }
    if (!hp_input_install()) { printf("INPUT HOOK FAIL\n"); return 1; }
    hp_clear(HP_BLACK);

    /* filled + outlined triangle pair (top-left) */
    hp_fill_triangle(20, 90, 140, 90, 80, 20, HP_BLUE);
    hp_triangle(20, 90, 140, 90, 80, 20, HP_CYAN);

    /* fan of small filled triangles (fast fill path demo) */
    fan(160, 120, 55, 24, HP_ORANGE);

    /* big outline triangle on top */
    hp_triangle(300, 200, 20, 200, 160, 60, HP_MAGENTA);

    /* GROB: query size, draw into it, blit (same primitives work there) */
    g = hp_grob_new(120, 60);
    if (!g) { printf("GROB FAIL\n"); return 1; }
    printf("GROB %dx%d target %dx%d\n",
           hp_grob_w(g), hp_grob_h(g), hp_target_w(), hp_target_h());
    hp_grob_select(g);
    hp_clear(HP_GRAY);
    hp_fill_triangle(60, 55, 115, 5, 5, 5, HP_YELLOW);
    hp_rect(2, 2, hp_grob_w(g) - 4, hp_grob_h(g) - 4, HP_WHITE);
    hp_text(10, 28, "GROB", HP_BLACK);
    hp_grob_select(NULL);
    hp_grob_blit(g, 100, 130);
    hp_grob_free(g);

    hp_text(4, 2, "TRIANGLE + GROB DEMO", HP_WHITE);
    hp_text(4, 228, "q/ESC/ON TO EXIT", HP_CYAN);
    printf("TRI_DONE\n");

    for (;;) {
        t = hp_poll_event(&ev);
        if (t == HP_EV_KEY) {
            key = hp_event_key(&ev);
            if (hp_event_key_down(&ev) &&
                (key == 0x51 || key == 0x01 || key == 0x83)) {
                hp_input_remove();
                printf("TRI_EXIT\n");
                return 0;
            }
        }
        __sleep(16);
    }
}
/* PRIME-C-CODE-END */
