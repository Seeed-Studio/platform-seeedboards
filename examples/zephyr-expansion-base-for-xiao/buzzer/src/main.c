#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/pwm.h>
#include <zephyr/sys/printk.h>

/*
 * Get button and buzzer device nodes via devicetree alias
 */
#define SW1_NODE    DT_ALIAS(sw1)
#if !DT_NODE_HAS_STATUS(SW1_NODE, okay)
#error "Unsupported board: sw1 devicetree alias is not defined"
#endif

#define BUZZER_NODE DT_ALIAS(buzzer)
#if !DT_NODE_HAS_STATUS(BUZZER_NODE, okay)
#error "Unsupported board: buzzer devicetree alias is not defined"
#endif

/* Define buzzer frequency and duty cycle */
#define BUZZER_FREQUENCY_HZ 1000 // Buzzer frequency 1000Hz (adjustable)
#define BUZZER_PERIOD_NSEC  (NSEC_PER_SEC / BUZZER_FREQUENCY_HZ) // Period (nanoseconds)
#define BUZZER_DUTY_CYCLE_PERCENT 50 // 50% duty cycle
#define BUZZER_PULSE_NSEC   (BUZZER_PERIOD_NSEC * BUZZER_DUTY_CYCLE_PERCENT / 100) // Pulse width (nanoseconds)

static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(SW1_NODE, gpios);
static const struct pwm_dt_spec buzzer = PWM_DT_SPEC_GET(BUZZER_NODE);

int main(void)
{
    int ret;
    bool is_on = false; // Track buzzer state to avoid redundant calls

    printk("Buzzer example started\n");

    /* 1. Check and initialize button */
    if (!gpio_is_ready_dt(&button)) {
        printk("Error: button device is not ready\n");
        return 0;
    }
    ret = gpio_pin_configure_dt(&button, GPIO_INPUT);
    if (ret != 0) {
        printk("Error %d: failed to configure button pin\n", ret);
        return 0;
    }

    /* 2. Check and initialize buzzer (PWM device) */
    if (!pwm_is_ready_dt(&buzzer)) {
        printk("Error: PWM device is not ready\n");
        return 0;
    }

    printk("Press SW0 to activate the buzzer.\n");

    /* 3. Main loop: poll button state and control buzzer */
    while (1) {
        if (gpio_pin_get_dt(&button)) { // Button pressed
            if (!is_on) {
                printk("Button pressed, starting buzzer...\n");
                // Use pwm_set_dt to set PWM
                ret = pwm_set_dt(&buzzer, BUZZER_PERIOD_NSEC, BUZZER_PULSE_NSEC);
                if (ret) {
                    printk("Error %d: failed to set PWM pulse\n", ret);
                }
                is_on = true;
            }
        } else { // Button released
            if (is_on) {
                // printk("Button released, stopping buzzer...\n"); // Uncomment to see log
                // Use pwm_set_dt with pulse width 0 to stop sound
                ret = pwm_set_dt(&buzzer, BUZZER_PERIOD_NSEC, 0);
                if (ret) {
                    printk("Error %d: failed to stop PWM pulse\n", ret);
                }
                is_on = false;
            }
        }

        k_msleep(20); // Reduce CPU usage
    }

    return 0;
}