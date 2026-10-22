#include <zephyr/kernel.h>
#include <zephyr/drivers/pwm.h>
#include <zephyr/logging/log.h>

// Register log module
LOG_MODULE_REGISTER(pwm_fade_example, CONFIG_LOG_DEFAULT_LEVEL);

// Define PWM period as 1 millisecond (1,000,000 nanoseconds)
// This corresponds to a 1 kHz PWM frequency
#define PWM_PERIOD_NS 1000000UL // Use UL to ensure unsigned long

// Get the PWM LED device defined in the device tree
static const struct pwm_dt_spec led = PWM_DT_SPEC_GET(DT_ALIAS(pwm_led));

int main(void)
{
    int ret;
    uint32_t duty_ns; // PWM duty cycle (in nanoseconds)

    LOG_INF("Starting Zephyr LED fade example...");

    // Check if PWM device is ready
    if (!device_is_ready(led.dev)) {
        LOG_ERR("Error: PWM device %s is not ready", led.dev->name);
        return 0;
    }

    LOG_INF("PWM Period set to %lu ns (1kHz frequency)", PWM_PERIOD_NS);

    while (1) {
        // Fade in from minimum to maximum
        for (int fadeValue = 0; fadeValue <= 255; fadeValue += 3) {
            // Calculate duty cycle (nanoseconds): map Arduino's 0-255 to PWM_PERIOD_NS range
            duty_ns = (PWM_PERIOD_NS * fadeValue) / 255U;

            // Set PWM duty cycle. First parameter is period, second is duty cycle.
            ret = pwm_set_dt(&led, PWM_PERIOD_NS, duty_ns);
            if (ret < 0) {
                LOG_ERR("Error %d: failed to set PWM duty cycle", ret);
                return 0;
            }
            k_msleep(30); // Wait 30 milliseconds
        }

        // Fade out from maximum to minimum
        for (int fadeValue = 255; fadeValue >= 0; fadeValue -= 3) {
            // Calculate duty cycle
            duty_ns = (PWM_PERIOD_NS * fadeValue) / 255U;

            // Set PWM duty cycle
            ret = pwm_set_dt(&led, PWM_PERIOD_NS, duty_ns);
            if (ret < 0) {
                LOG_ERR("Error %d: failed to set PWM duty cycle", ret);
                return 0;
            }
            k_msleep(30); // Wait 30 milliseconds
        }
    }
    return 0;
}
