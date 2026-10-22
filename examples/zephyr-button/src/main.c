#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>


LOG_MODULE_REGISTER(main_app, CONFIG_LOG_DEFAULT_LEVEL);

static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(DT_ALIAS(sw0), gpios); // Get the button device from the device tree alias
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios); // Get the led device from the device tree alias

int main(void)
{
    int ret;

    LOG_INF("Starting Zephyr button and led example...");

    /* Check if GPIO devices are ready */
    if (!gpio_is_ready_dt(&button)) {
        LOG_ERR("Button device %s is not ready", button.port->name);
        return -1;
    }

    if (!gpio_is_ready_dt(&led)) {
        LOG_ERR("LED device %s is not ready", led.port->name);
        return -1;
    }

    /* Configure button pin as input mode */
    ret = gpio_pin_configure_dt(&button, GPIO_INPUT);
    if (ret != 0) {
        LOG_ERR("Failed to configure %s pin %d (error %d)", button.port->name, button.pin, ret);
        return -1;
    }

    /* Configure led pin as output mode */
    ret = gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);
    if (ret != 0) {
        LOG_ERR("Failed to configure %s pin %d (error %d)", led.port->name, led.pin, ret);
        return -1;
    }

    LOG_INF("Press the button to toggle the led...");

    while (1) {
        /* Read button state */
        int button_state = gpio_pin_get_dt(&button);

        /* Check if read is successful */
        if (button_state < 0) {
            LOG_ERR("Error reading button pin: %d", button_state);
            return -1;
        }

        if (button_state == 0) { // Button pressed (ACTIVE_LOW)
            gpio_pin_set_dt(&led, 1); // Turn on led (high level)
        } else { // Button not pressed
            gpio_pin_set_dt(&led, 0); // Turn off led (low level)
        }

        k_msleep(10); /* Short delay to avoid busy looping */
    }
    return 0;
}
