/*
 * Copyright (c) 2019 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#include <inttypes.h>
#include <stdio.h>

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/hwinfo.h>
#include <zephyr/kernel.h>
#include <zephyr/pm/device.h>
#include <zephyr/sys/poweroff.h>
#include <zephyr/sys/util.h>

static const struct gpio_dt_spec sw0 = GPIO_DT_SPEC_GET(DT_ALIAS(sw0), gpios);

#if defined(CONFIG_BOARD_XIAO_NRF54LM20A)

static int print_reset_cause(uint32_t reset_cause)
{
	uint32_t supported;
	int rc;

	rc = hwinfo_get_supported_reset_cause(&supported);
	if (rc < 0 || !(reset_cause & supported)) {
		printf("Reset cause not supported: 0x%08" PRIX32 "\n", reset_cause);
		return -ENOTSUP;
	}
	printf("hwinfo_get_supported_reset_cause() ok, supported: 0x%08" PRIX32 "\n", supported);

	printf("Raw reset cause: 0x%08" PRIX32 "\n", reset_cause);

	if (reset_cause & RESET_DEBUG) {
		printf("Reset by debugger.\n");
	} else if (reset_cause & RESET_CLOCK) {
		printf("Wakeup from System OFF by GRTC.\n");
	} else if (reset_cause & RESET_LOW_POWER_WAKE) {
		printf("Wakeup from System OFF by GPIO.\n");
	} else {
		printf("Other wake up cause 0x%08" PRIX32 ".\n", reset_cause);
	}

	return 0;
}

#else /* nrf54l15 */

void print_reset_cause(void)
{
	uint32_t reset_cause;

	hwinfo_get_reset_cause(&reset_cause);
	if (reset_cause & RESET_DEBUG) {
		printf("Reset by debugger.\n");
	} else if (reset_cause & RESET_CLOCK) {
		printf("Wakeup from System OFF by GRTC.\n");
	} else  {
		printf("Other wake up cause 0x%08X.\n", reset_cause);
	}
}

#endif

int main(void)
{
	int rc;
	const struct device *const cons = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));

	if (!device_is_ready(cons)) {
		printf("%s: device not ready.\n", cons->name);
		return 0;
	}

#if defined(CONFIG_BOARD_XIAO_NRF54LM20A)
	printf("\n=== %s system off demo start ===\n", CONFIG_BOARD);

	uint32_t reset_cause;

	rc = hwinfo_get_reset_cause(&reset_cause);
	if (rc < 0) {
		printf("Could not read reset cause (rc=%d)\n", rc);
		return 0;
	}
	printf("hwinfo_get_reset_cause() ok, cause: 0x%08" PRIX32 "\n", reset_cause);

	rc = print_reset_cause(reset_cause);
	printf("print_reset_cause() returned: %d\n", rc);
#else
	printf("\n%s system off demo\n", CONFIG_BOARD);
	print_reset_cause();
#endif

	/* configure sw0 as input, interrupt as level active to allow wake-up */
	rc = gpio_pin_configure_dt(&sw0, GPIO_INPUT);
	if (rc < 0) {
		printf("Could not configure sw0 GPIO (%d)\n", rc);
		return 0;
	}

#if defined(CONFIG_BOARD_XIAO_NRF54LM20A)
	rc = gpio_pin_interrupt_configure_dt(&sw0, GPIO_INT_LEVEL_ACTIVE);
#else
	rc = gpio_pin_interrupt_configure_dt(&sw0, GPIO_INT_LEVEL_LOW);
#endif
	if (rc < 0) {
		printf("Could not configure sw0 GPIO interrupt (%d)\n", rc);
		return 0;
	}

	printf("Entering system off; press sw0 to restart\n");

	rc = pm_device_action_run(cons, PM_DEVICE_ACTION_SUSPEND);
	if (rc < 0) {
		printf("Could not suspend console (%d)\n", rc);
		return 0;
	}

	rc = hwinfo_clear_reset_cause();
	if (rc < 0) {
		printf("Could not clear reset cause (rc=%d)\n", rc);
		return 0;
	}

	sys_poweroff();

	return 0;
}
