#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/display.h>
#include <zephyr/sys/printk.h>
#include <lvgl.h>
#include <math.h>
#include <stdio.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ---------- Globals for the watchface ---------- */
static lv_obj_t *hour_line, *min_line, *sec_line;
static lv_point_precise_t hour_pts[2], min_pts[2], sec_pts[2];
static lv_obj_t *ticks[12];
static lv_point_precise_t tick_pts[12][2];

static uint16_t scr_w, scr_h, cx, cy;
static uint16_t R_outer, R_hour, R_min, R_sec;

static inline void polar_to_xy(float deg, float r, lv_point_precise_t *out)
{
    float rad = deg * (float)(M_PI / 180.0);
    out->x = (lv_coord_t)(cx + r * cosf(rad));
    out->y = (lv_coord_t)(cy - r * sinf(rad)); /* screen +y is down */
}

static void wf_update(uint32_t secs)
{
    uint32_t s = secs % 60;
    uint32_t m = (secs / 60) % 60;
    uint32_t h = (secs / 3600) % 12;

    float sec_deg  = 90.0f - (s * 6.0f);
    float min_deg  = 90.0f - (m * 6.0f + s * 0.1f);
    float hour_deg = 90.0f - (h * 30.0f + m * 0.5f);

    hour_pts[0].x = cx; hour_pts[0].y = cy;
    polar_to_xy(hour_deg, (float)R_hour, &hour_pts[1]);
    lv_line_set_points(hour_line, hour_pts, 2);

    min_pts[0].x = cx; min_pts[0].y = cy;
    polar_to_xy(min_deg, (float)R_min, &min_pts[1]);
    lv_line_set_points(min_line, min_pts, 2);

    sec_pts[0].x = cx; sec_pts[0].y = cy;
    polar_to_xy(sec_deg, (float)R_sec, &sec_pts[1]);
    lv_line_set_points(sec_line, sec_pts, 2);
}

static void tick_cb(lv_timer_t *t)
{
    uint32_t *secs = (uint32_t *)lv_timer_get_user_data(t); /* v9 accessor */
    (*secs)++;
    wf_update(*secs);
}

int main(void)
{
    printk("WF: boot\n");

    /* --- 1) Raw display sanity fill (white) --- */
    const struct device *disp = DEVICE_DT_GET(DT_CHOSEN(zephyr_display));
    if (!device_is_ready(disp)) {
        printk("WF: display not ready\n");
        return -1;
    }
    display_blanking_off(disp);

    /* assume 240x240 RGB565; paint line-by-line so we don’t malloc big buffers */
    uint16_t line[240];
    for (int x = 0; x < 240; x++) line[x] = 0xFFFF; /* white in RGB565 */
    struct display_buffer_descriptor desc = {
        .width  = 240,
        .height = 1,
        .pitch  = 240,
        .buf_size = sizeof(line),
    };
    for (int y = 0; y < 240; y++) {
        (void)display_write(disp, 0, y, &desc, (const void *)line);
    }
    printk("WF: screen sanity-painted (white)\n");

    /* --- 2) LVGL watchface UI --- */
    lv_display_t *ld = lv_display_get_default();
    scr_w = lv_display_get_horizontal_resolution(ld);
    scr_h = lv_display_get_vertical_resolution(ld);
    cx = scr_w / 2;  cy = scr_h / 2;

    uint16_t pad = 10;
    R_outer = MIN(scr_w, scr_h) / 2 - pad;
    R_hour  = (uint16_t)(R_outer * 0.55f);
    R_min   = (uint16_t)(R_outer * 0.78f);
    R_sec   = (uint16_t)(R_outer * 0.85f);

    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x000000), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    lv_obj_t *lbl = lv_label_create(scr);
    lv_label_set_text(lbl, "Watchface");
    lv_obj_align(lbl, LV_ALIGN_CENTER, 0, 20);

    for (int i = 0; i < 12; i++) {
        float a  = 90.0f - (i * 30.0f);
        float r1 = (float)R_outer;
        float r2 = (float)R_outer - 10.0f;

        polar_to_xy(a, r1, &tick_pts[i][0]);
        polar_to_xy(a, r2, &tick_pts[i][1]);

        ticks[i] = lv_line_create(scr);
        lv_obj_set_style_line_width(ticks[i], 4, 0);
        lv_obj_set_style_line_color(ticks[i], lv_color_hex(0xFFFFFF), 0);
        lv_obj_set_style_line_rounded(ticks[i], true, 0);
        lv_line_set_points(ticks[i], tick_pts[i], 2);
    }

    hour_line = lv_line_create(scr);
    lv_obj_set_style_line_width(hour_line, 6, 0);
    lv_obj_set_style_line_color(hour_line, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_line_rounded(hour_line, true, 0);

    min_line = lv_line_create(scr);
    lv_obj_set_style_line_width(min_line, 4, 0);
    lv_obj_set_style_line_color(min_line, lv_color_hex(0xC0C0C0), 0);
    lv_obj_set_style_line_rounded(min_line, true, 0);

    sec_line = lv_line_create(scr);
    lv_obj_set_style_line_width(sec_line, 2, 0);
    lv_obj_set_style_line_color(sec_line, lv_color_hex(0xFF4444), 0);
    lv_obj_set_style_line_rounded(sec_line, true, 0);

    /* center cap */
    lv_obj_t *cap = lv_obj_create(scr);
    lv_obj_remove_style_all(cap);
    lv_obj_set_style_bg_color(cap, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_bg_opa(cap, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(cap, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_size(cap, 10, 10);
    lv_obj_set_pos(cap, cx - 5, cy - 5);

    static uint32_t secs;
    int hour, min, sec;
    sscanf(__TIME__, "%d:%d:%d", &hour, &min, &sec);
    secs = hour * 3600 + min * 60 + sec;

    wf_update(secs);
    (void)lv_timer_create(tick_cb, 1000, &secs);

    /* Force an immediate refresh once, in case the LVGL thread isn’t scheduled yet */
    lv_refr_now(NULL);

    printk("WF: lvgl ready (%ux%u)\n", scr_w, scr_h);

    /* --- 3) Guaranteed LVGL pumping (works even if CONFIG_LV_Z_* threads are off) --- */
    while (1) {
        lv_timer_handler();         /* process LVGL tasks & flush */
        k_msleep(5);
    }

    return 0;
}
