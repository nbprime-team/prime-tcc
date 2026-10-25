/*
 * hp_input.h -- keyboard + touch input for TCC-compiled programs on the
 * HP Prime G1, via firmware get_event (svc 0x1003f).
 *
 * Event structure (verified against the PureDOOM port's my_get_event_hook):
 *   ev->[4]   = event type:  0x00100010 = key,  15 = touch,  else = none
 *   key:      ev->[28] = 16 (press) / 0x100000 (release);  ev->[34] = u16
 *             physical scan code (see HP_KEY_* below)
 *   touch:    ev->[24] = u16 item count (<= 8); each item i occupies 12
 *             bytes at ev->[28 + 12*i]:  [0] = u32 item type (1 = press /
 *             abs position, 2 = move, 8 = release), [4] = u16 (0 = valid),
 *             [6] = u16 x, [8] = u16 y
 *
 * Usage:
 *     hp_event ev;
 *     int t = hp_poll_event(&ev);
 *     if (t == HP_EV_KEY) { int k = hp_event_key(&ev); ... }
 *     if (t == HP_EV_TOUCH) { int x, y; hp_event_touch(&ev, 0, &x, &y); }
 */
#ifndef HP_INPUT_H
#define HP_INPUT_H

#define HP_EV_NONE   0
#define HP_EV_KEY    0x00100010
#define HP_EV_TOUCH  15

#define HP_EV_KEY_DOWN  16
#define HP_EV_KEY_UP    0x100000

#define HP_TOUCH_PRESS    1
#define HP_TOUCH_MOVE     2
#define HP_TOUCH_RELEASE  8

typedef struct hp_event {
    unsigned data[32];      /* 128 bytes, opaque (firmware fills it) */
} hp_event;

/* poll one event (non-blocking); returns HP_EV_KEY / HP_EV_TOUCH / 0.
 * Requires hp_input_install() first: input arrives via the RESIDENT
 * firmware get_event hook (inside tcc.elf), NOT by calling get_event
 * directly (it blocks on the OS UI thread). */
int hp_poll_event(hp_event *ev);

/* arm the resident get_event hook: force-patches the firmware API slot
 * 0x307fbfa0 to the hook inside tcc.elf and resets the shared queue.
 * Takes over an already-patched slot (from a previous run) instead of
 * refusing.  Call once at start.  Returns 1 on success, 0 if the shared
 * input state was not provided (entry must be hp_entry with r0 = state). */
int  hp_input_install(void);
/* restore the firmware slot (from the shared saved bytes) and disarm.
 * ALSO called automatically by hp_entry's teardown at exit.  The hook
 * itself stays resident in tcc.elf, so this is always safe. */
void hp_input_remove(void);
/* 1 while the hook is armed (a program is listening); 1 while the OS
 * thread is inside the hook's blocking get_event call. */
int  hp_input_hooked(void);
int  hp_input_busy(void);

/* key events */
int hp_event_key(const hp_event *ev);        /* physical scan code (the key id) */
int hp_event_key_down(const hp_event *ev);   /* 1 = press, 0 = release */

/* touch events */
int hp_event_touch_count(const hp_event *ev);
/* item type (HP_TOUCH_*) or 0; fills x/y (screen pixels) */
int hp_event_touch(const hp_event *ev, int i, int *x, int *y);

/* ---- physical scan codes (HP Prime G1 keyboard) --------------------------
 * Verified against the full scan-code table (matrix SCANCODE(row,col) ->
 * device key id, hardware-verified):
 *   (0,0)=on 0x83   (1,0)=eex 0x50   (1,1)=0 0x30   (1,2)=divide 0x54
 *   (1,3)=mul 0x58  (1,4)=minus 0xB7 (1,5)=add 0xB9  (1,6)=space 0x20
 *   (1,7)=left 0x02 (2,0)=backspace 0x0C (2,1)=define 0x44 (2,2)=units 0x43
 *   (2,3)=alpha 0xB6 (2,4)=ab/c 0x45 (2,5)=vars 0x41 (2,6)=sin 0x47
 *   (2,7)=toolbox 0x42 (3,0)=+/- 0x4D (3,1)=square 0x4C (3,2)=log 0x4B
 *   (3,3)=ln 0x4A (3,4)=tan 0x49 (3,5)=cos 0x48 (3,6)=shift 0x8B
 *   (3,7)=pow 0x46 (4,0)=num 0xB3 (4,1)=plot 0xB2 (4,2)=symb 0x91
 *   (4,3)=home (4,4)=apps 0xB1 (4,5)=down 0x05 (4,6)=esc 0x01
 *   (4,7)=bracket 0x4E (5,0)=9 0x53 (5,1)=cas 0xB5 (5,2)=menu 0x93
 *   (5,3)=view 0xB4 (5,4)=up 0x03 (5,5)=1 0x59 (5,6)=period 0xB8
 *   (5,7)=help 0x95 (6,0)=comma 0x4F (6,1)=8 0x52 (6,2)=7/Q 0x51
 *   (6,3)=6 0x57 (6,4)=5 0x56 (6,5)=4 0x55 (6,6)=3 0x33 (6,7)=2 0x5A
 *   (7,0)=enter 0x0D (7,1)=right 0x04
 * NOTE: the letter keys are the physical number/symbol keys (alpha layer),
 * e.g. 'q' is the 7/Q key = 0x51.
 */
#define HP_KEY_ESC       0x01
#define HP_KEY_LEFT      0x02
#define HP_KEY_UP        0x03
#define HP_KEY_RIGHT     0x04
#define HP_KEY_DOWN      0x05
#define HP_KEY_BACKSPACE 0x0C
#define HP_KEY_ENTER     0x0D
#define HP_KEY_SPACE     0x20
#define HP_KEY_ON        0x83   /* ON/Cancel */
#define HP_KEY_SHIFT     0x8B
#define HP_KEY_Q         0x51   /* 7/Q key: 'q' in alpha mode */
#define HP_KEY_F1        0x91   /* symb */
#define HP_KEY_F2        0xB2   /* plot */
#define HP_KEY_F3        0xB3   /* num  */
#define HP_KEY_F4        0xB4   /* view */
#define HP_KEY_F5        0xB5   /* cas  */
#define HP_KEY_F6        0x93   /* menu */
#define HP_KEY_APPS      0xB1
#define HP_KEY_HELP      0x95
#define HP_KEY_ALPHA     0xB6
#define HP_KEY_PLUSMINUS 0x4D
#define HP_KEY_X2        0x4C

#endif /* HP_INPUT_H */
