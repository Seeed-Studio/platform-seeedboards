/* Blink the on-board user LED of the Seeed Studio XIAO ESP32-S31 Sense
 * using the shared BSP header. The yellow user LED is wired from 3V3
 * through a series resistor to GPIO23, so it lights while GPIO23 is
 * driven LOW.
 */

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"

#include "board.h"

static const char *TAG = "blink";

void app_main(void)
{
    ESP_LOGI(TAG, "XIAO ESP32-S31 Sense LED blink (GPIO%d, active %s)",
             BOARD_LED_GPIO, BOARD_LED_ACTIVE_LOW ? "low" : "high");

    gpio_reset_pin(BOARD_LED_GPIO);
    gpio_set_direction(BOARD_LED_GPIO, GPIO_MODE_OUTPUT);

    int level = 0; /* LOW = LED on */
    while (1) {
        gpio_set_level(BOARD_LED_GPIO, level);
        level = !level;
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}
