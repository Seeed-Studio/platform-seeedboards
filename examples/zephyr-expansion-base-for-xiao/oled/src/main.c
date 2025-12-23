#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/display/cfb.h>
#include <stdio.h>
#include <string.h>

#define LOG_LEVEL CONFIG_LOG_DEFAULT_LEVEL
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(main_app, LOG_LEVEL);

/**
 * @brief Initializes the display device.
 * @param[out] dev Pointer to the display device struct.
 * @return 0 on success, -1 on failure.
 */
static int display_init(const struct device **dev) {
    *dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_display));
    if (!device_is_ready(*dev)) {
        LOG_ERR("Device %s not ready", (*dev)->name);
        return -1;
    }

    if (display_set_pixel_format(*dev, PIXEL_FORMAT_MONO10) != 0) {
        if (display_set_pixel_format(*dev, PIXEL_FORMAT_MONO01) != 0) {
            LOG_ERR("Failed to set required pixel format");
            return -1;
        }
    }

    LOG_INF("Initialized %s", (*dev)->name);
    return 0;
}

/**
 * @brief Initializes the Compact Framebuffer (CFB) and display blanking.
 * @param dev Pointer to the display device struct.
 * @return 0 on success, -1 on failure.
 */
static int framebuffer_setup(const struct device *dev) {
    if (cfb_framebuffer_init(dev)) {
        LOG_ERR("Framebuffer initialization failed!");
        return -1;
    }
    cfb_framebuffer_clear(dev, true);
    display_blanking_off(dev);
    return 0;
}

/**
 * @brief Selects a suitable font for the display.
 * @param dev Pointer to the display device struct.
 * @param[out] font_width Pointer to store the width of the selected font.
 * @param[out] font_height Pointer to store the height of the selected font.
 * @return 0 on success, -1 if no suitable font is found.
 */
static int select_font(const struct device *dev, uint8_t *font_width, uint8_t *font_height) {
    int chosen_font_idx = -1;
    uint8_t current_font_width, current_font_height;

    for (int idx = 0; idx < 42; idx++) {
        if (cfb_get_font_size(dev, idx, &current_font_width, &current_font_height) == 0) {
            if (current_font_width == 8 && current_font_height == 8) {
                chosen_font_idx = idx;
                *font_width = current_font_width;
                *font_height = current_font_height;
                cfb_framebuffer_set_font(dev, chosen_font_idx);
                LOG_INF("Selected font idx: %d, width: %d, height: %d", chosen_font_idx, *font_width, *font_height);
                break;
            }
            if (chosen_font_idx == -1 && current_font_width > 0 && current_font_height > 0) {
                chosen_font_idx = idx;
                *font_width = current_font_width;
                *font_height = current_font_height;
                cfb_framebuffer_set_font(dev, chosen_font_idx);
                LOG_INF("Defaulting to font idx: %d, width: %d, height: %d", chosen_font_idx, *font_width, *font_height);
            }
        } else {
            break;
        }
    }

    if (chosen_font_idx == -1) {
        LOG_ERR("No suitable font found or loaded!");
        return -1;
    }
    return 0;
}

/**
 * @brief Prints a single line of text at specified row and column.
 * @param dev Pointer to the display device struct.
 * @param text The string to print.
 * @param row The row number (0-indexed) where the text should start.
 * @param col The column number (0-indexed) where the text should start.
 * @param font_width The width of the currently selected font in pixels.
 * @param font_height The height of the currently selected font in pixels.
 */
static void print_text_by_row_col(const struct device *dev, const char *text, int row, int col,
                                  uint8_t font_width, uint8_t font_height) {
    int pixel_x = col * font_width;
    int pixel_y = row * font_height;

    if (cfb_print(dev, text, pixel_x, pixel_y)) {
        LOG_ERR("Failed to print text: \"%s\" at row %d, col %d", text, row, col);
    }
}

int main(void) {
    const struct device *dev;
    uint8_t font_width = 0;
    uint8_t font_height = 0;
    uint16_t x_res, y_res;

    if (display_init(&dev) != 0) {
        return 0;
    }

    if (framebuffer_setup(dev) != 0) {
        return 0;
    }

    if (select_font(dev, &font_width, &font_height) != 0) {
        return 0;
    }

    x_res = cfb_get_display_parameter(dev, CFB_DISPLAY_WIDTH);
    y_res = cfb_get_display_parameter(dev, CFB_DISPLAY_HEIGHT);
    LOG_INF("Display resolution: %dx%d", x_res, y_res);
    cfb_set_kerning(dev, 0);

    while (1) {
        cfb_framebuffer_clear(dev, false);

        const char *line1_text = "nRF54L15";
        // Print line1 at row 1, column 2
        print_text_by_row_col(dev, line1_text, 1, 2, font_width, font_height);

        const char *line2_text = "Hello World";
        // Print line2 at row 2, column 1
        print_text_by_row_col(dev, line2_text, 2, 1, font_width, font_height);

        cfb_framebuffer_finalize(dev);
        k_sleep(K_MSEC(1000));
    }

    return 0;
}
