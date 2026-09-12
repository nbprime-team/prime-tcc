/*
 * hp_image.h —— HP Prime G1 上 TCC 编译程序的图像加载。
 *
 * 把 PNG 文件（或原始 PNG 字节）解码为 ARGB 像素缓冲，然后用与 GROB
 * 相同的图元绘制：
 *
 *     hp_image *img = hp_image_load_png("test.png");
 *     if (img) {
 *         hp_image_draw_scaled(img, 10, 10, 160, 120);  // 适配，保持宽高比
 *         hp_image_free(img);
 *     }
 *
 * 支持的 PNG 子集（限制已记录）：
 *   - 8 位色彩类型 0（灰度）、2（RGB）、3（调色板）、4（灰度+alpha）、
 *     6（RGBA）；16 位与隔行（Adam7）PNG 被拒绝
 *   - tRNS 调色板 alpha 与图像自身 alpha 通道被忽略（一切按不透明绘制；
 *     需要透明请用 hp_image_draw_key）
 *   - 不校验 CRC（仅供显示的解码器）
 *
 * 解码器内置 zlib inflate；整个解码逐行流式进行，因此内存峰值约为
 * 文件 + w*h*4 + 32KB LZ 窗口。hp_image.c 编入 rt_core.o（随运行时部署）。
 */
#ifndef HP_IMAGE_H
#define HP_IMAGE_H

typedef struct hp_image {
    int w, h;
    unsigned *px;               /* w*h 个 ARGB 像素（0xFF alpha） */
} hp_image;

/* 解码 PNG 文件（ASCII 路径，内部转 UTF-16）；
 * 任何错误返回 NULL（并打印简短诊断） */
hp_image *hp_image_load_png(const char *ascii_path);

/* 解码原始 PNG 字节（例如内嵌数组） */
hp_image *hp_image_load_png_mem(const unsigned char *data, unsigned len);

void hp_image_free(hp_image *img);
int  hp_image_w(const hp_image *img);   /* 宽度，NULL 时为 0 */
int  hp_image_h(const hp_image *img);   /* 高度，NULL 时为 0 */

/* 绘制辅助（hp_blit / hp_blit_scaled 的薄包装；px 数组是公开的，
 * 因此 hp_blit(img->px, ...) 也可直接用） */
void hp_image_draw(hp_image *img, int x, int y);
void hp_image_draw_key(hp_image *img, int x, int y, hp_color key);
void hp_image_draw_scaled(hp_image *img, int x, int y, int dw, int dh);

#endif /* HP_IMAGE_H */
