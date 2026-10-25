/*
 * hp_gui.h -- minimal widget toolkit on top of hp_gfx + hp_fonts + hp_input.
 *
 * A deliberately tiny UI layer for demos/games: labels, buttons and a
 * single-line text EDIT widget, driven by touch OR the keyboard.  All
 * text is drawn with the runtime fonts (hp_fonts.h): Montserrat
 * (proportional) for labels/buttons, Unifont (monospace) for edit text.
 *
 * DOUBLE BUFFERING: wrap each frame in hp_gui_begin()/hp_gui_end() -- the
 * library keeps one lazily-allocated full-screen GROB, renders the whole
 * frame into it and blits once, so nothing flickers:
 *
 *     hp_gui_begin();            selects the internal back buffer, clears
 *     ...draw app content...     (also lands in the buffer)
 *     hp_gui_draw(ws, n);        widgets on top
 *     hp_gui_end();              one blit to the screen
 *
 *   char buf[32];
 *   hp_gui_widget ws[3];
 *   ws[0] = (hp_gui_widget)HP_GUI_LABEL_INIT(4, 2, "menu");
 *   ws[1] = (hp_gui_widget)HP_GUI_BUTTON_INIT(20, 40, 120, 26, "GO", 1, on_go, 0);
 *   ws[2] = (hp_gui_widget)HP_GUI_EDIT_INIT(20, 70, 280, 24, buf, sizeof buf);
 *   for (;;) {
 *       hp_gui_begin();
 *       hp_gui_draw(ws, 3);
 *       hp_gui_end();
 *       t = hp_poll_event(&ev);
 *       if (t) hp_gui_handle(ws, 3, t, &ev);
 *   }
 *
 * Edit keys while an edit is focused: the Prime's digit/operator keys
 * (see the scan-code table in hp_input.h), BACKSPACE, LEFT/RIGHT cursor,
 * ENTER fires the widget's on_click (returned as its id).  Multi-char
 * inserts (function names from the SIN/COS/... hard keys) are done by the
 * app via hp_gui_edit_insert().
 *
 * Compiled into rt_core.o.  Depends on hp_gfx.h / hp_fonts.h / hp_input.h.
 */
#ifndef HP_GUI_H
#define HP_GUI_H

#include "hp_gfx.h"
#include "hp_fonts.h"
#include "hp_input.h"

#ifndef NULL
#define NULL ((void *)0)
#endif

#define HP_GUI_LABEL  0
#define HP_GUI_BUTTON 1
#define HP_GUI_EDIT   2

struct hp_gui_widget;

typedef void (*hp_gui_cb)(struct hp_gui_widget *w, void *udata);

typedef struct hp_gui_widget {
    int x, y, w, h;            /* rect (label: w/h ignored) */
    const char *label;
    unsigned type;             /* HP_GUI_LABEL / BUTTON / EDIT */
    int id;                    /* user tag; returned by hp_gui_handle */
    int state;                 /* 0 idle, 1 focused, 2 pressed */
    hp_gui_cb on_click;        /* buttons: click; edit: ENTER */
    void *udata;
    /* edit widgets only */
    char *buf;                 /* caller-owned text buffer (NUL-terminated) */
    int buflen;                /* buffer capacity */
    int cur;                   /* cursor position (chars) */
} hp_gui_widget;

#define HP_GUI_LABEL_INIT(x, y, text) \
    { (x), (y), 0, 0, (text), HP_GUI_LABEL, 0, 0, 0, 0, 0, 0, 0 }
#define HP_GUI_BUTTON_INIT(x, y, w, h, text, id_, cb, ud) \
    { (x), (y), (w), (h), (text), HP_GUI_BUTTON, (id_), 0, (cb), (ud), 0, 0, 0 }
#define HP_GUI_EDIT_INIT(x, y, w, h, buf_, buflen_) \
    { (x), (y), (w), (h), 0, HP_GUI_EDIT, 0, 0, 0, 0, (buf_), (buflen_), 0 }

/* ---- double-buffered frame: begin/end wrap ALL drawing of a frame ----
 * begin() lazily allocates one full-screen back GROB (created once,
 * reused) and makes it the draw target; end() blits it to the screen.
 * The internal buffer also owns all widget text via the fonts. */
void hp_gui_begin(void);
void hp_gui_end(void);

/* draw all widgets onto the current draw target (call between begin/end,
 * or directly on the screen if the app does its own buffering) */
void hp_gui_draw(hp_gui_widget *ws, int n);

/* feed one event (etype = hp_poll_event()'s return: HP_EV_KEY / HP_EV_TOUCH);
 * returns the id of a button clicked or an edit's ENTER (or 0).
 * Touch: press inside a button presses it, release fires on_click; a tap
 * inside an edit focuses it.  Keys: UP/DOWN move focus between buttons
 * and edits, ENTER activates; a focused edit consumes printable Prime
 * keys, BACKSPACE and LEFT/RIGHT (cursor). */
int hp_gui_handle(hp_gui_widget *ws, int n, int etype, const hp_event *ev);

/* insert s into an edit widget at the cursor (returns chars inserted) */
int hp_gui_edit_insert(hp_gui_widget *w, const char *s);

/* Prime key scan code -> character (0 if unmapped).  Accepts BOTH the
 * matrix device ids (hp_input.h table) and plain ASCII codes for digits
 * and operators, so the same code works regardless of what the firmware
 * reports. */
char hp_gui_key_char(int k);

#endif /* HP_GUI_H */
