/* PRIME-C-CODE-BEGIN */
#include "prime.h"
#include "hp_gfx.h"
#include "hp_input.h"
#include "hp_math.h"
#include "hp_string.h"
#include "hp_gui.h"

/* ---- terminal-style calculator ----
 * Keyboard-driven expression calculator with a scrollable HISTORY, like
 * a REPL: every evaluation appends "> <expr>" and "= <result>" lines to
 * an on-screen history; UP/DOWN scroll it.  Rendered through hp_gui's
 * GROB back buffer (hp_gui_begin/end) so nothing flickers.
 *
 * Keys (both ASCII and matrix scan codes are accepted, see
 * hp_gui_key_char): digits/operators/( ) , ^ space type text; the
 * SIN/COS/TAN/LN/LOG keys insert their names, the x^2 key inserts
 * "sqrt(", EEX inserts "e"; ENTER evaluates, BACKSPACE deletes,
 * LEFT/RIGHT move the cursor, UP/DOWN scroll history, q/ESC/ON exit.
 * Every key press is echoed to the console as "KEY <code>" -- if a key
 * does not respond on your calculator, the console tells you the real
 * scan code and the table can be updated.
 *
 * Functions: sin cos tan ln log sqrt abs floor ceil exp pow(a,b), the
 * constants pi and e; operators + - * / % ^ (precedence, parentheses,
 * unary minus).  Console prints "CALC <expr>=<result>" per evaluation.
 */

#define EXPR_MAX 48
#define HIST_MAX 60
#define HIST_LEN 60
#define HIST_ROWS 8

static char g_expr[EXPR_MAX];
static char g_res[40];
static char g_hist[HIST_MAX][HIST_LEN];
static int  g_hist_n = 0;
static int  g_scroll = 0;         /* 0 = newest line */
static hp_gui_widget ws[4];
static int  g_exit = 0;

/* ---- history ring ---- */
static void hist_add(const char *s)
{
    int n = 0;
    while (s[n] && n < HIST_LEN - 1) n++;
    {
        int i;
        for (i = 0; i < n; i++)
            g_hist[g_hist_n % HIST_MAX][i] = s[i];
        g_hist[g_hist_n % HIST_MAX][n] = 0;
    }
    g_hist_n++;
    g_scroll = 0;                 /* jump to the newest line */
}

static const char *hist_get(int back)
{
    int idx = g_hist_n - 1 - back;
    if (idx < 0)
        return 0;
    return g_hist[idx % HIST_MAX];
}

/* ---- tiny expression evaluator: recursive descent ----
 *   expr  := term (('+'|'-') term)*
 *   term  := unary (('*'|'/'|'%') unary)*
 *   unary := '-' unary | power
 *   power := primary ('^' unary)?            (right associative)
 *   primary := number | ident | '(' expr ')'
 * NOTE: function dispatch uses a plain switch -- TCC's ARM backend
 * mis-compiles indirect calls through a pointer table when the argument
 * is a double (see README), so no function-pointer tables here.
 */
static const char *g_s;
static int g_i, g_err;

static void skip_ws(void) { while (g_s[g_i] == ' ') g_i++; }

static double eval_expr(void);
static double eval_unary(void);

static double eval_primary(void)
{
    skip_ws();
    if (g_s[g_i] == '(') {
        double v;
        g_i++;
        v = eval_expr();
        skip_ws();
        if (g_s[g_i] == ')') g_i++;
        else g_err = 1;
        return v;
    }
    if ((g_s[g_i] >= '0' && g_s[g_i] <= '9') || g_s[g_i] == '.') {
        char *end;
        double v = strtod(g_s + g_i, &end);
        if (end == g_s + g_i) { g_err = 1; return 0; }
        g_i = (int)(end - g_s);
        return v;
    }
    if ((g_s[g_i] >= 'a' && g_s[g_i] <= 'z') ||
        (g_s[g_i] >= 'A' && g_s[g_i] <= 'Z')) {
        char name[8];
        int nl = 0, have_b = 0;
        double a, b = 0;
        while ((g_s[g_i] >= 'a' && g_s[g_i] <= 'z') ||
               (g_s[g_i] >= 'A' && g_s[g_i] <= 'Z')) {
            if (nl < 7) name[nl++] = g_s[g_i];
            g_i++;
        }
        name[nl] = 0;
        if (name[0] == 'p' && name[1] == 'i' && !name[2])
            return HP_PI;
        if (name[0] == 'e' && !name[1])
            return HP_E;
        skip_ws();
        if (g_s[g_i] != '(') { g_err = 1; return 0; }
        g_i++;
        a = eval_expr();
        skip_ws();
        if (g_s[g_i] == ',') {
            g_i++;
            b = eval_expr();
            have_b = 1;
            skip_ws();
        }
        if (g_s[g_i] == ')') g_i++;
        else g_err = 1;
        if (name[0] == 's' && name[1] == 'i' && name[2] == 'n' && !name[3])
            return hp_sin(a);
        if (name[0] == 'c' && name[1] == 'o' && name[2] == 's' && !name[3])
            return hp_cos(a);
        if (name[0] == 't' && name[1] == 'a' && name[2] == 'n' && !name[3])
            return hp_tan(a);
        if (name[0] == 'l' && name[1] == 'n' && !name[2])
            return hp_log(a);
        if (name[0] == 'l' && name[1] == 'o' && name[2] == 'g' && !name[3])
            return hp_log10(a);
        if (name[0] == 's' && name[1] == 'q' && name[2] == 'r' &&
            name[3] == 't' && !name[4])
            return hp_sqrt(a);
        if (name[0] == 'a' && name[1] == 'b' && name[2] == 's' && !name[3])
            return hp_fabs(a);
        if (name[0] == 'f' && name[1] == 'l' && name[2] == 'o' &&
            name[3] == 'o' && name[4] == 'r' && !name[5])
            return hp_floor(a);
        if (name[0] == 'c' && name[1] == 'e' && name[2] == 'i' &&
            name[3] == 'l' && !name[4])
            return hp_ceil(a);
        if (name[0] == 'e' && name[1] == 'x' && name[2] == 'p' && !name[3])
            return hp_exp(a);
        if (name[0] == 'p' && name[1] == 'o' && name[2] == 'w' && !name[3]) {
            if (have_b)
                return hp_pow(a, b);
            g_err = 1;
            return 0;
        }
        g_err = 1;
        return 0;
    }
    g_err = 1;
    return 0;
}

static double eval_power(void)
{
    double b = eval_primary();
    skip_ws();
    if (g_s[g_i] == '^') {
        g_i++;
        return hp_pow(b, eval_unary());
    }
    return b;
}

static double eval_unary(void)
{
    skip_ws();
    if (g_s[g_i] == '-') { g_i++; return -eval_unary(); }
    return eval_power();
}

static double eval_term(void)
{
    double v = eval_unary();
    for (;;) {
        char c;
        skip_ws();
        c = g_s[g_i];
        if (c == '*') { g_i++; v *= eval_unary(); }
        else if (c == '/') { g_i++; v /= eval_unary(); }
        else if (c == '%') { g_i++; v = hp_fmod(v, eval_unary()); }
        else break;
    }
    return v;
}

static double eval_expr(void)
{
    double v = eval_term();
    for (;;) {
        char c;
        skip_ws();
        c = g_s[g_i];
        if (c == '+') { g_i++; v += eval_term(); }
        else if (c == '-') { g_i++; v -= eval_term(); }
        else break;
    }
    return v;
}

static double calc_eval(const char *s, int *err)
{
    double v;
    g_s = s;
    g_i = 0;
    g_err = 0;
    v = eval_expr();
    skip_ws();
    if (g_s[g_i] != 0)
        g_err = 1;
    *err = g_err;
    return v;
}

/* ---- evaluation -> history + console ---- */
static void hist_line(char first, const char *rest)
{
    char line[HIST_LEN];
    char *p = line;
    int i = 0;
    *p++ = first;
    *p++ = ' ';
    while (rest[i] && p - line < HIST_LEN - 2) {
        *p++ = rest[i++];
    }
    *p = 0;
    hist_add(line);
}

static void do_eval(void)
{
    int err = 0;
    double v;
    char expr[HIST_LEN];
    int i;
    if (!g_expr[0])
        return;
    for (i = 0; g_expr[i] && i < HIST_LEN - 1; i++)
        expr[i] = g_expr[i];
    expr[i] = 0;
    v = calc_eval(expr, &err);
    if (err) {
        hist_line('E', expr);            /* "E <expr>" = error line */
        prints("CALC ERR ");
        prints(expr);
        prints("\n");
        g_expr[0] = 0;
        ws[0].cur = 0;
        return;
    }
    ftoa(v, g_res, -1);                  /* AUTO: 8 -> "8", 0.5 -> "0.5",
                                          * 1e20 -> "1e+20" (no padding) */
    hist_line('>', expr);
    hist_line('=', g_res);
    printf("CALC %s=%s\n", (unsigned long)expr, (unsigned long)g_res);
    g_expr[0] = 0;                       /* successful eval clears input */
    ws[0].cur = 0;
}

/* ---- buttons ---- */
static void btn_clear(hp_gui_widget *w, void *ud)
{
    g_expr[0] = 0;
    ws[0].cur = 0;
    g_scroll = 0;
    (void)w; (void)ud;
}

static void btn_eval(hp_gui_widget *w, void *ud)
{
    do_eval();
    (void)w; (void)ud;
}

static void btn_exit(hp_gui_widget *w, void *ud)
{
    g_exit = 1;
    (void)w; (void)ud;
}

/* dedicated function keys insert their names into the input */
static const char *func_insert(int k)
{
    switch (k) {
    case 0x47: return "sin(";   /* sin key   */
    case 0x48: return "cos(";   /* cos key   */
    case 0x49: return "tan(";   /* tan key   */
    case 0x4A: return "ln(";    /* ln key    */
    case 0x4B: return "log(";   /* log key   */
    case 0x4C: return "sqrt(";  /* x^2 key   */
    case 0x50: return "e";      /* EEX key   */
    }
    return 0;
}

static void draw_history(void)
{
    int start, end, k, y;
    /* terminal layout: oldest line at the TOP, newest at the bottom, so
     * each block reads "> expr" above "= result".  g_scroll shifts the
     * window back in time (UP = older). */
    end = g_hist_n - g_scroll;
    start = end - HIST_ROWS;
    if (start < 0)
        start = 0;
    y = 18;
    for (k = start; k < end; k++) {
        const char *ln = g_hist[k % HIST_MAX];
        hp_color col = HP_WHITE;
        if (ln[0] == '=')
            col = HP_GREEN;
        else if (ln[0] == 'E')
            col = HP_RED;
        hp_font_draw(hp_font_mono(16), 4, y, ln, col);
        y += 19;
    }
}

int main(void)
{
    hp_event ev;
    int t;
    if (!hp_gfx_init()) { printf("GFX INIT FAIL\n", 0, 0, 0, 0); return 1; }
    if (!hp_input_install()) { printf("INPUT HOOK FAIL\n", 0, 0, 0, 0); return 1; }

    g_expr[0] = 0;
    ws[0] = (hp_gui_widget)HP_GUI_EDIT_INIT(4, 176, 312, 24, g_expr, EXPR_MAX);
    ws[1] = (hp_gui_widget)HP_GUI_BUTTON_INIT(4, 206, 60, 24, "C", 1, btn_clear, 0);
    ws[2] = (hp_gui_widget)HP_GUI_BUTTON_INIT(68, 206, 60, 24, "=", 2, btn_eval, 0);
    ws[3] = (hp_gui_widget)HP_GUI_BUTTON_INIT(132, 206, 60, 24, "EXIT", 3, btn_exit, 0);
    ws[0].on_click = btn_eval;           /* ENTER on the edit evaluates */
    ws[0].state = 1;                     /* input always focused */

    printf("CALC start\n", 0, 0, 0, 0);
    for (;;) {
        hp_gui_begin();                  /* GROB back buffer: no flicker */
        hp_font_draw(hp_font_prop(16), 4, 2, "PRIMETCC CALC", HP_WHITE);
        if (g_hist_n == 0)
            hp_font_draw(hp_font_mono(16), 4, 18,
                         "TYPE; ENTER EVAL; UP/DN HIST; ESC/ON EXIT",
                         HP_GRAY);
        draw_history();
        hp_gui_draw(ws, 4);
        hp_gui_end();

        t = hp_poll_event(&ev);
        if (t == HP_EV_KEY && hp_event_key_down(&ev)) {
            int k = hp_event_key(&ev);
            /* echo the raw code: if a key does not respond on your
             * calculator, the console reports what it really sends */
            printf("KEY %02x\n", (unsigned long)k, 0, 0, 0);
            /* exit = ESC / ON only.  NOTE: do NOT add 0x51 here -- the
             * 7/Q key reports 0x51 and is the digit 7 on the Prime. */
            if (k == 0x01 || k == 0x1B || k == 0x83) {
                hp_input_remove();
                printf("GUI_DONE\n", 0, 0, 0, 0);
                return 0;
            }
            if (k == HP_KEY_UP) {
                if (g_scroll < g_hist_n - HIST_ROWS)
                    g_scroll++;
            } else if (k == HP_KEY_DOWN) {
                if (g_scroll > 0)
                    g_scroll--;
            } else if (k == HP_KEY_BACKSPACE) {
                int i;
                if (ws[0].cur > 0) {
                    for (i = ws[0].cur; g_expr[i]; i++)
                        g_expr[i - 1] = g_expr[i];
                    g_expr[i - 1] = 0;
                    ws[0].cur--;
                }
            } else if (k == HP_KEY_LEFT) {
                if (ws[0].cur > 0) ws[0].cur--;
            } else if (k == HP_KEY_RIGHT) {
                if (g_expr[ws[0].cur]) ws[0].cur++;
            } else if (k == HP_KEY_ENTER) {
                printf("DIAG cur=%d buf=%x buflen=%d x=%d\n",
                       (unsigned long)ws[0].cur, (unsigned long)ws[0].buf,
                       (unsigned long)ws[0].buflen, (unsigned long)ws[0].x);
                printf("DIAG2 y=%d w=%d h=%d t=%d st=%d\n",
                       (unsigned long)ws[0].y, (unsigned long)ws[0].w,
                       (unsigned long)ws[0].h, (unsigned long)ws[0].type,
                       (unsigned long)ws[0].state);
                printf("DIAG3 ws=%x gexpr=%x hist=%x gres=%x scroll=%x\n",
                       (unsigned long)&ws[0], (unsigned long)g_expr,
                       (unsigned long)&g_hist[0], (unsigned long)&g_res,
                       (unsigned long)&g_scroll);
                do_eval();
            } else {
                const char *ins = func_insert(k);
                if (ins) {
                    hp_gui_edit_insert(&ws[0], ins);
                } else {
                    char c = hp_gui_key_char(k);
                    if (c)
                        hp_gui_edit_insert(&ws[0], &c);
                }
            }
        } else if (t == HP_EV_TOUCH) {
            /* console echo: if a tap still lands nowhere on the real
             * calculator, this line shows the coordinates the firmware
             * actually reported (survives ESC-exit via PRIMELOG) */
            if (hp_event_touch_count(&ev) > 0) {
                int tx = 0, ty = 0;
                hp_event_touch(&ev, 0, &tx, &ty);
                printf("TOUCH x=%d y=%d\n",
                       (unsigned long)tx, (unsigned long)ty, 0, 0);
            } else {
                printf("TOUCH release\n", 0, 0, 0, 0);
            }
            hp_gui_handle(ws, 4, t, &ev);
            /* terminal style: keep the input focused.  NEVER reset the
             * button states here -- hp_gui_handle marks the pressed
             * button (state=2) on press and fires it on release through
             * exactly that state; zeroing it after the press is why the
             * on-screen buttons could never fire. */
            ws[0].state = 1;
        }
        if (g_exit) {
            hp_input_remove();
            printf("GUI_DONE\n", 0, 0, 0, 0);
            return 0;
        }
        __sleep(16);
    }
}
/* PRIME-C-CODE-END */
