#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>


LOG_MODULE_REGISTER(main_app, CONFIG_LOG_DEFAULT_LEVEL);

static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(DT_ALIAS(sw1), gpios); // Get the button device from the device tree alias
static const struct gpio_dt_spec relay = GPIO_DT_SPEC_GET(DT_ALIAS(relay0), gpios); // Get the relay device from the device tree alias

int main(void)
{
    int ret;

    LOG_INF("Starting Zephyr button and relay example...");

    /* Check if GPIO devices are ready */
    if (!gpio_is_ready_dt(&button)) {
        LOG_ERR("Button device %s is not ready", button.port->name);
        return -1;
    }

    if (!gpio_is_ready_dt(&relay)) {
        LOG_ERR("Relay device %s is not ready", relay.port->name);
        return -1;
    }

    /* Configure button pin as input mode */
    ret = gpio_pin_configure_dt(&button, GPIO_INPUT);
    if (ret != 0) {
        LOG_ERR("Failed to configure %s pin %d (error %d)", button.port->name, button.pin, ret);
        return -1;
    }

    /* Configure relay pin as output mode */
    ret = gpio_pin_configure_dt(&relay, GPIO_OUTPUT_ACTIVE);
    if (ret != 0) {
        LOG_ERR("Failed to configure %s pin %d (error %d)", relay.port->name, relay.pin, ret);
        return -1;
    }

    LOG_INF("Press the button to toggle the relay...");

    while (1) {
        /* Read button state */
        int button_state = gpio_pin_get_dt(&button);

        /* Check if read is successful */
        if (button_state < 0) {
            LOG_ERR("Error reading button pin: %d", button_state);
            return -1;
        }

        if (button_state == 0) { // Button pressed (ACTIVE_LOW)
            gpio_pin_set_dt(&relay, 1); // Turn on relay (high level)
        } else { // Button not pressed
            gpio_pin_set_dt(&relay, 0); // Turn off relay (low level)
        }

        k_msleep(10); /* Short delay to avoid busy looping */
    }
    return 0;
}
