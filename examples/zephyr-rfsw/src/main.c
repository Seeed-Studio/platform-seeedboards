/*
 * Copyright (c) 2024 Seeed Technology Co.,Ltd
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>
#include <zephyr/devicetree.h>

LOG_MODULE_REGISTER(app, CONFIG_LOG_DEFAULT_LEVEL);

/* Devicetree node identifiers */
#define RFSW_REGULATOR_NODE DT_NODELABEL(rfsw_ctl)
#define SW0_NODE            DT_ALIAS(sw0)
#define LED0_NODE           DT_ALIAS(led0)

/* State variables */
static uint8_t onoff_flag = 0;
#ifdef CONFIG_DEFAULT_ANTENNA_EXTERNAL
static bool is_external_antenna = true;
#else
static bool is_external_antenna = false;
#endif

/* GPIO device specs */
/* Manually build gpio_dt_spec for rfsw_ctl */
static const struct gpio_dt_spec rfsw_gpio = {
	.port = DEVICE_DT_GET(DT_GPIO_CTLR(RFSW_REGULATOR_NODE, enable_gpios)),
	.pin = DT_GPIO_PIN(RFSW_REGULATOR_NODE, enable_gpios),
	.dt_flags = DT_GPIO_FLAGS(RFSW_REGULATOR_NODE, enable_gpios),
};
static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(SW0_NODE, gpios);
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);

/* Button callback data */
static struct gpio_callback button_cb_data;

/* Forward declarations */
void button_pressed(const struct device *dev, struct gpio_callback *cb, uint32_t pins);
void update_antenna_switch(void);

/* Function to update antenna switch and LED */
void update_antenna_switch(void)
{
    int ret;
    is_external_antenna = !is_external_antenna;

    if (is_external_antenna) {
        /* Switch to external antenna */
        LOG_INF("Switching to External Antenna");

        // To get a physical high level (Inactive state), we need to set the logic to '0'
        ret = gpio_pin_set_dt(&rfsw_gpio, 0); 
        if (ret < 0) {
            LOG_ERR("Error setting rfsw-ctl to physical HIGH: %d\n", ret);
        }

        // Turn on the LED (set 0 for on)
        ret = gpio_pin_set_dt(&led, 0); 
        if (ret < 0) {
            LOG_ERR("Error turning on LED: %d\n", ret);
        }

    } else {
        /* Switch back to ceramic antenna */
        LOG_INF("Switching to Ceramic Antenna");

        // To get a physical low level (Active state), we need to set the logic to '1'
        ret = gpio_pin_set_dt(&rfsw_gpio, 1); 
        if (ret < 0) {
            LOG_ERR("Error setting rfsw-ctl to physical LOW: %d\n", ret);
        }

        // Turn off the LED (set 1 for off)
        ret = gpio_pin_set_dt(&led, 1);
        if (ret < 0) {
            LOG_ERR("Error turning off LED: %d\n", ret);
        }
    }
}

/* Button pressed callback function */
void button_pressed(const struct device *dev, struct gpio_callback *cb,
                    uint32_t pins)
{
    update_antenna_switch();
}

int main(void)
{
    int ret;
    
    /* Check if GPIO devices are ready */
    if (!gpio_is_ready_dt(&rfsw_gpio)) {
        LOG_ERR("RF switch control GPIO not ready\n");
        return -1;
    }
    if (!gpio_is_ready_dt(&button)) {
        LOG_ERR("Button GPIO not ready\n");
        return -1;
    }
    if (!gpio_is_ready_dt(&led)) {
        LOG_ERR("LED GPIO not ready\n");
        return -1;
    }
    
    /* Configure GPIO pins */
    ret = gpio_pin_configure_dt(&rfsw_gpio, GPIO_OUTPUT);
    if (ret < 0) {
        LOG_ERR("Error configuring rfsw-ctl: %d\n", ret);
        return ret;
    }
    
    /* Configure LED as output, default off */
    ret = gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);
    if (ret < 0) {
        LOG_ERR("Error configuring LED: %d\n", ret);
        return ret;
    }

    /* Set initial LED state based on antenna selection */
    if (is_external_antenna) {
        // External antenna
        LOG_INF("Initial state: External Antenna");
        ret = gpio_pin_set_dt(&rfsw_gpio, 0);
        if (ret < 0) {
            LOG_ERR("Error setting rfsw-ctl to physical HIGH: %d\n", ret);
        }
        ret = gpio_pin_set_dt(&led, 0);  // Turn on LED
        if (ret < 0) {
            LOG_ERR("Error turning on LED: %d\n", ret);
        }
    } else {
        // Ceramic antenna
        LOG_INF("Initial state: Ceramic Antenna");
        ret = gpio_pin_set_dt(&rfsw_gpio, 1);
        if (ret < 0) {
            LOG_ERR("Error setting rfsw-ctl to physical LOW: %d\n", ret);
        }
        ret = gpio_pin_set_dt(&led, 1);  // Turn off LED
        if (ret < 0) {
            LOG_ERR("Error turning off LED: %d\n", ret);
        }
    }

    /* Configure button as input */
    ret = gpio_pin_configure_dt(&button, GPIO_INPUT);
    if (ret < 0) {
        LOG_ERR("Error configuring button: %d\n", ret);
        return ret;
    }

    /* Configure button interrupt */
    ret = gpio_pin_interrupt_configure_dt(&button, GPIO_INT_EDGE_TO_ACTIVE);
    if (ret < 0) {
        LOG_ERR("Error configuring button interrupt: %d\n", ret);
        return ret;
    }

    /* Initialize button callback */
    gpio_init_callback(&button_cb_data, button_pressed, BIT(button.pin));
    gpio_add_callback(button.port, &button_cb_data);

    LOG_INF("Antenna switch example started. Press SW0 to switch.\n");
    return 0;
}