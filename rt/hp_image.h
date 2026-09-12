/*
 * hp_image.h -- image loading for TCC-compiled programs on the HP Prime G1.
 *
 * Loads PNG files (or raw PNG bytes) into an ARGB pixel buffer, then
 * draws them with the same primitives as GROBs:
 *
 *     hp_image *img = hp_image_load_png("test.png");
 *     if (img) {
 *         hp_image_draw_scaled(img, 10, 10, 160, 120);  // fit, aspect kept
 *         hp_image_free(img);
 *     }
 *
 * Supported PNG subset (documented limits):
 *   - 8-bit color types 0 (gray), 2 (RGB), 3 (palette), 4 (gray+alpha),
 *     6 (RGBA);  16-bit and interlaced (Adam7) PNGs are rejected
 *   - tRNS palette alpha and the image's own alpha channel are ignored
 *     (everything draws opaque; use hp_image_draw_key for transparency)
 *   - CRC values are not verified (display-only decoder)
 *
 * The decoder is a built-in zlib inflate; the whole decode streams
 * row-by-row, so memory peaks at file + w*h*4 + 32KB LZ window.
 * hp_image.c is compiled into rt_core.o (deployed with the runtime).
 */
#ifndef HP_IMAGE_H
#define HP_IMAGE_H

typedef struct hp_image {
    int w, h;
    unsigned *px;               /* w*h ARGB pixels (0xFF alpha) */
} hp_image;

/* decode a PNG file (ASCII path, converted to UTF-16 internally);
 * returns NULL on any error (a short diagnostic is printed) */
hp_image *hp_image_load_png(const char *ascii_path);

/* decode raw PNG bytes (e.g. an embedded array) */
hp_image *hp_image_load_png_mem(const unsigned char *data, unsigned len);

void hp_image_free(hp_image *img);
int  hp_image_w(const hp_image *img);   /* width, 0 if NULL */
int  hp_image_h(const hp_image *img);   /* height, 0 if NULL */

/* draw helpers (thin wrappers over hp_blit / hp_blit_scaled; the px
 * array is public, so hp_blit(img->px, ...) works directly too) */
void hp_image_draw(hp_image *img, int x, int y);
void hp_image_draw_key(hp_image *img, int x, int y, hp_color key);
void hp_image_draw_scaled(hp_image *img, int x, int y, int dw, int dh);

#endif /* HP_IMAGE_H */
