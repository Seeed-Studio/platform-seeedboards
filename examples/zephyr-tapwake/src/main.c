#include <stdio.h>
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/sys/util.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

/* Use DT_ALIAS to get the nodes */
static const struct i2c_dt_spec imu_i2c = I2C_DT_SPEC_GET(DT_ALIAS(imu0));
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);
static const struct gpio_dt_spec imu_int = GPIO_DT_SPEC_GET(DT_NODELABEL(lsm6ds3tr_c), irq_gpios);

/* Register addresses */
#define LSM6DS3TR_C_CTRL1_XL 0x10
#define LSM6DS3TR_C_TAP_SRC 0x1C
#define LSM6DS3TR_C_TAP_CFG 0x58
#define LSM6DS3TR_C_TAP_THS_6D 0x59
#define LSM6DS3TR_C_INT_DUR2 0x5A
#define LSM6DS3TR_C_WAKE_UP_THS 0x5B
#define LSM6DS3TR_C_MD1_CFG 0x5E

/* Register bit definitions and configuration values */
#define LSM6DS3TR_C_ACCEL_ODR_104HZ (0x40)

#define LSM6DS3TR_C_TAP_CFG_INT_ENABLE BIT(7)
#define LSM6DS3TR_C_TAP_CFG_TAP_X_EN BIT(3)
#define LSM6DS3TR_C_TAP_CFG_TAP_Y_EN BIT(2)
#define LSM6DS3TR_C_TAP_CFG_TAP_Z_EN BIT(1)
#define LSM6DS3TR_C_TAP_CFG_LATCH_INT BIT(0)

#define LSM6DS3TR_C_TAP_CONFIG (LSM6DS3TR_C_TAP_CFG_INT_ENABLE | \
                                LSM6DS3TR_C_TAP_CFG_TAP_X_EN |   \
                                LSM6DS3TR_C_TAP_CFG_TAP_Y_EN |   \
                                LSM6DS3TR_C_TAP_CFG_TAP_Z_EN |   \
                                LSM6DS3TR_C_TAP_CFG_LATCH_INT)

#define LSM6DS3TR_C_TAP_THRESHOLD (0x0A)  /* Adjust sensitivity as needed */
#define LSM6DS3TR_C_TAP_TIMING (0x80)
#define LSM6DS3TR_C_WAKE_UP_THS_SINGLE_DOUBLE_EN BIT(7)
#define LSM6DS3TR_C_MD1_CFG_INT1_SINGLE_TAP_EN BIT(6)
#define LSM6DS3TR_C_INT1_ROUTING (LSM6DS3TR_C_MD1_CFG_INT1_SINGLE_TAP_EN)

#define DOUBLE_TAP_WINDOW_MS 500

/* Forward declarations */
static void imu_work_handler(struct k_work *work);
static void led_off_work_handler(struct k_work *work);
static void tap_timer_expiry_function(struct k_timer *timer_id);

/* Work items and timers */
static K_WORK_DEFINE(imu_work, imu_work_handler);
static K_WORK_DELAYABLE_DEFINE(led_off_work, led_off_work_handler);
static K_TIMER_DEFINE(tap_timer, tap_timer_expiry_function, NULL);

/* GPIO callback struct for the IMU interrupt pin */
static struct gpio_callback imu_cb_data;

/* Helper to flash the LED */
static void trigger_led_flash(void)
{
    gpio_pin_set_dt(&led, 1);
    k_work_schedule(&led_off_work, K_MSEC(150));
}

/* Called by timer when the double-tap window expires */
static void tap_timer_expiry_function(struct k_timer *timer_id)
{
    LOG_INF("Single tap event detected!");
    trigger_led_flash();
}

/* Work handler to process IMU interrupt in thread context */
static void imu_work_handler(struct k_work *work)
{
    /* An interrupt means a tap occurred. Check timer to classify it. */
    if (k_timer_remaining_get(&tap_timer) > 0)
    {
        /* Timer is running: this is the second tap of a double tap */
        k_timer_stop(&tap_timer);
        LOG_INF("Double tap event detected!");
        trigger_led_flash();
    }
    else
    {
        /* Timer is not running: this is the first tap. Start the window. */
        k_timer_start(&tap_timer, K_MSEC(DOUBLE_TAP_WINDOW_MS), K_NO_WAIT);
    }

    /* Reading TAP_SRC is still good practice to clear the latched interrupt */
    uint8_t tap_src;
    i2c_reg_read_byte_dt(&imu_i2c, LSM6DS3TR_C_TAP_SRC, &tap_src);
}

/* ISR: only submits work to a thread. Non-blocking and fast. */
static void gpio_interrupt_handler(const struct device *port, struct gpio_callback *cb,
                                   gpio_port_pins_t pins)
{
    k_work_submit(&imu_work);
}

static void led_off_work_handler(struct k_work *work)
{
    gpio_pin_set_dt(&led, 0);
}

static int setup_gpio_interrupt(void)
{
    if (!gpio_is_ready_dt(&imu_int))
    {
        LOG_ERR("IMU interrupt pin not ready.");
        return -ENODEV;
    }

    int ret = gpio_pin_configure_dt(&imu_int, GPIO_INPUT);
    if (ret)
    {
        LOG_ERR("Error configuring interrupt pin: %d", ret);
        return ret;
    }

    ret = gpio_pin_interrupt_configure_dt(&imu_int, GPIO_INT_EDGE_TO_ACTIVE);
    if (ret)
    {
        LOG_ERR("Error configuring interrupt: %d", ret);
        return ret;
    }

    gpio_init_callback(&imu_cb_data, gpio_interrupt_handler, BIT(imu_int.pin));
    gpio_add_callback(imu_int.port, &imu_cb_data);

    LOG_INF("GPIO interrupt configured on %s, pin %d", imu_int.port->name, imu_int.pin);
    return 0;
}

static int configure_lsm6ds3_tap(void)
{
    int ret = 0;

    /* Enable accelerometer */
    ret = i2c_reg_write_byte_dt(&imu_i2c, LSM6DS3TR_C_CTRL1_XL, LSM6DS3TR_C_ACCEL_ODR_104HZ);
    if (ret)
    {
        return ret;
    }
    k_msleep(20);

    /* Enable interrupts, latch them, and enable tap on all axes */
    ret = i2c_reg_write_byte_dt(&imu_i2c, LSM6DS3TR_C_TAP_CFG, LSM6DS3TR_C_TAP_CONFIG);
    if (ret)
    {
        return ret;
    }

    /* Set tap threshold */
    ret = i2c_reg_write_byte_dt(&imu_i2c, LSM6DS3TR_C_TAP_THS_6D, LSM6DS3TR_C_TAP_THRESHOLD);
    if (ret)
    {
        return ret;
    }

    /* Set tap timing parameters (DUR field is ignored in single-tap only mode) */
    ret = i2c_reg_write_byte_dt(&imu_i2c, LSM6DS3TR_C_INT_DUR2, LSM6DS3TR_C_TAP_TIMING);
    if (ret)
    {
        return ret;
    }

    /* Configure for single-tap ONLY by clearing the SINGLE_DOUBLE_TAP bit */
    ret = i2c_reg_update_byte_dt(&imu_i2c, LSM6DS3TR_C_WAKE_UP_THS,
                                 LSM6DS3TR_C_WAKE_UP_THS_SINGLE_DOUBLE_EN,
                                 0);
    if (ret)
    {
        return ret;
    }

    /* Route ONLY single tap interrupt to INT1 */
    ret = i2c_reg_write_byte_dt(&imu_i2c, LSM6DS3TR_C_MD1_CFG, LSM6DS3TR_C_INT1_ROUTING);
    if (ret)
    {
        return ret;
    }

    LOG_INF("LSM6DS3TR-C tap detection configured for single-tap events.");
    return 0;
}

int main(void)
{
    if (!i2c_is_ready_dt(&imu_i2c))
    {
        LOG_ERR("I2C bus for IMU not ready.");
        return 0;
    }

    if (!gpio_is_ready_dt(&led))
    {
        LOG_ERR("LED device not found!");
        return 0;
    }
    gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);

    LOG_INF("Blinking LED to indicate startup...");
    gpio_pin_set_dt(&led, 1);
    k_msleep(500);
    gpio_pin_set_dt(&led, 0);

    if (configure_lsm6ds3_tap() != 0)
    {
        LOG_ERR("Failed to configure IMU for tap detection.");
        return 0;
    }

    if (setup_gpio_interrupt() != 0)
    {
        LOG_ERR("Failed to set up GPIO interrupt.");
        return 0;
    }

    LOG_INF("Setup complete. Entering sleep mode.");
    LOG_INF("Tap the board to wake it up.");

    while (1)
    {
        k_sleep(K_FOREVER);
    }

    return 0;
}