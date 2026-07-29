/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 crystal MCO output test.
 *
 * MCO1 PH2-BOOT0: LSE 32.768 kHz
 * MCO2 PA9/D6:    HSE 48 MHz
 */

#include <stdbool.h>
#include <stdint.h>

#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

#include <stm32_backup_domain.h>
#include <stm32_ll_bus.h>
#include <stm32_ll_gpio.h>
#include <stm32_ll_rcc.h>

#define LED0_NODE DT_ALIAS(led0)

#define HSE_READY_TIMEOUT_MS 100U
#define LSE_READY_TIMEOUT_MS 10000U
#define HEARTBEAT_OK_MS 500U
#define HEARTBEAT_FAULT_MS 100U

static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);

static bool wait_for_hse_ready(uint32_t timeout_ms)
{
	int64_t deadline = k_uptime_get() + timeout_ms;

	while (k_uptime_get() <= deadline) {
		if (LL_RCC_HSE_IsReady()) {
			return true;
		}
		k_msleep(1);
	}

	return LL_RCC_HSE_IsReady();
}

static bool wait_for_lse_ready(uint32_t timeout_ms)
{
	int64_t deadline = k_uptime_get() + timeout_ms;

	while (k_uptime_get() <= deadline) {
		if (LL_RCC_LSE_IsReady()) {
			return true;
		}
		k_msleep(10);
	}

	return LL_RCC_LSE_IsReady();
}

static bool start_hse(void)
{
	if (!LL_RCC_HSE_IsReady()) {
		LL_RCC_HSE_DisableBypass();
		LL_RCC_HSE_Enable();
	}

	return wait_for_hse_ready(HSE_READY_TIMEOUT_MS);
}

static bool start_lse(void)
{
	bool ready;

	stm32_backup_domain_enable_access();

	if (!LL_RCC_LSE_IsReady()) {
		LL_RCC_LSE_DisableBypass();
		LL_RCC_LSE_SetDriveCapability(LL_RCC_LSEDRIVE_MEDIUMHIGH);
		LL_RCC_LSE_Enable();
	}

	ready = wait_for_lse_ready(LSE_READY_TIMEOUT_MS);
	stm32_backup_domain_disable_access();

	return ready;
}

static void configure_mco_pin(GPIO_TypeDef *gpio, uint32_t pin)
{
	LL_GPIO_SetPinMode(gpio, pin, LL_GPIO_MODE_ALTERNATE);
	LL_GPIO_SetPinOutputType(gpio, pin, LL_GPIO_OUTPUT_PUSHPULL);
	LL_GPIO_SetPinPull(gpio, pin, LL_GPIO_PULL_NO);
	LL_GPIO_SetPinSpeed(gpio, pin, LL_GPIO_SPEED_FREQ_VERY_HIGH);

	if (pin < LL_GPIO_PIN_8) {
		LL_GPIO_SetAFPin_0_7(gpio, pin, LL_GPIO_AF_0);
	} else {
		LL_GPIO_SetAFPin_8_15(gpio, pin, LL_GPIO_AF_0);
	}
}

static void configure_mco_outputs(void)
{
	LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_GPIOA);
	LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_GPIOH);

	configure_mco_pin(GPIOH, LL_GPIO_PIN_2);
	configure_mco_pin(GPIOA, LL_GPIO_PIN_9);

	LL_RCC_ConfigMCO(LL_RCC_MCO1SOURCE_LSE, LL_RCC_MCO1_PRESCALER_1);
	LL_RCC_ConfigMCO(LL_RCC_MCO2SOURCE_HSE, LL_RCC_MCO2_PRESCALER_1);
}

static void configure_heartbeat(void)
{
	if (!gpio_is_ready_dt(&led)) {
		return;
	}

	(void)gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
}

int main(void)
{
	bool hse_ready;
	bool lse_ready;
	uint32_t blink_ms;

	configure_heartbeat();

	hse_ready = start_hse();
	lse_ready = start_lse();

	if (hse_ready && lse_ready) {
		configure_mco_outputs();
		blink_ms = HEARTBEAT_OK_MS;
	} else {
		blink_ms = HEARTBEAT_FAULT_MS;
	}

	while (true) {
		if (gpio_is_ready_dt(&led)) {
			(void)gpio_pin_toggle_dt(&led);
		}
		k_msleep(blink_ms);
	}
}
