
#include "prime.h"
#include "hp_input.h"

/* key-echo panel for the restart check: ENTER re-runs, q exits.
 * (main.py's embedded example is now a bare stub by user request, so
 * this check carries its own program instead of parsing main.py.) */
static void panel(void) {
    printf("SYS_DONE\\n", 0, 0, 0, 0);
}

int main(void) {
    hp_event ev;
    if (!hp_input_install()) { printf("INSTALL FAIL\\n", 0, 0, 0, 0); return 1; }
    panel();
    for (;;) {
        int t = hp_poll_event(&ev);
        if (t == HP_EV_KEY && hp_event_key_down(&ev)) {
            int k = hp_event_key(&ev);
            printf("KEY %02x\\n", (unsigned long)k, 0, 0, 0);
            if (k == 0x0D)
                panel();
            if (k == 0x51)
                break;
        }
        __sleep(10);
    }
    hp_input_remove();
    printf("SYS_EXIT\\n", 0, 0, 0, 0);
    printf("RT_EXIT ok\\n", 0, 0, 0, 0);
    return 0;
}
