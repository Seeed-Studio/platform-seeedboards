/* Blink the on-board user LED of the Seeed Studio XIAO ESP32-S31 Sense.
 *
 * The user LED (D3, yellow) is wired from 3V3 through a series resistor to
 * GPIO23, so it lights while GPIO23 is driven LOW.
 */

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"

static const char *TAG = "blink";

#define BLINK_GPIO GPIO_NUM_23

void app_main(void)
{
    ESP_LOGI(TAG, "XIAO ESP32-S31 Sense LED blink (GPIO%d, active low)", BLINK_GPIO);

    gpio_reset_pin(BLINK_GPIO);
    gpio_set_direction(BLINK_GPIO, GPIO_MODE_OUTPUT);

    int level = 0;
    while (1) {
        /* LOW = LED on */
        gpio_set_level(BLINK_GPIO, level);
        level = !level;
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}
