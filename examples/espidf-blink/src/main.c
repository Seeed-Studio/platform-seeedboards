/* ESP-IDF blink -- CI smoke for the espidf framework path.
 *
 * Blinks a GPIO. LED_GPIO follows the arduino-blink example's fallback
 * convention (some XIAO variants do not define an onboard LED); override
 * per env via build_flags if a visible LED is wanted on a given board.
 */

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"

#ifndef LED_GPIO
#define LED_GPIO 2
#endif

static void blink_task(void *arg)
{
    gpio_reset_pin(LED_GPIO);
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);
    for (;;) {
        gpio_set_level(LED_GPIO, 1);
        vTaskDelay(pdMS_TO_TICKS(1000));
        gpio_set_level(LED_GPIO, 0);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

void app_main(void)
{
    xTaskCreate(blink_task, "blink", 2048, NULL, 5, NULL);
}
