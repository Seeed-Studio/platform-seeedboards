/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 low-power STOP test.
 */

#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/usb/udc.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include <cmsis_core.h>
#include <stm32_ll_bus.h>
#include <stm32_ll_cortex.h>
#include <stm32_ll_exti.h>
#include <stm32_ll_gpio.h>
#include <stm32_ll_pwr.h>
#include <stm32_ll_usart.h>

#define LED0_NODE DT_ALIAS(led0)
#define CAN_PHY_NODE DT_NODELABEL(can_phy0)
#define PREPARE_SECONDS 5
#define EXT_FLASH_CMD_DEEP_POWER_DOWN 0xb9U
#define EXT_FLASH_TDP_US 10U

#define EXT_FLASH_CS_PORT GPIOB
#define EXT_FLASH_CS_PIN LL_GPIO_PIN_10
#define EXT_FLASH_CLK_PORT GPIOB
#define EXT_FLASH_CLK_PIN LL_GPIO_PIN_2
#define EXT_FLASH_IO0_PORT GPIOB
#define EXT_FLASH_IO0_PIN LL_GPIO_PIN_1
#define EXT_FLASH_IO1_PORT GPIOA
#define EXT_FLASH_IO1_PIN LL_GPIO_PIN_5
#define EXT_FLASH_IO2_PORT GPIOA
#define EXT_FLASH_IO2_PIN LL_GPIO_PIN_7
#define EXT_FLASH_IO3_PORT GPIOA
#define EXT_FLASH_IO3_PIN LL_GPIO_PIN_6

#ifndef LOW_POWER_STOP_MODE
#define LOW_POWER_STOP_MODE LL_PWR_STOP1_MODE
#endif

#if LOW_POWER_STOP_MODE == LL_PWR_STOP0_MODE
#define LOW_POWER_STOP_NAME "STOP0"
#else
#define LOW_POWER_STOP_NAME "STOP1"
#endif

static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);

#if DT_NODE_HAS_PROP(CAN_PHY_NODE, standby_gpios)
static const struct gpio_dt_spec can_stb =
	GPIO_DT_SPEC_GET(CAN_PHY_NODE, standby_gpios);
#endif

static void prepare_for_low_power(const char *mode)
{
	printk("XIAO STM32C5 low-power %s test\n", mode);
	printk("Device will run normally for %d seconds, then enter %s.\n",
	       PREPARE_SECONDS, mode);

	if (gpio_is_ready_dt(&led) && gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE) == 0) {
		for (int remaining = PREPARE_SECONDS; remaining > 0; remaining--) {
			gpio_pin_toggle_dt(&led);
			printk("Entering %s in %d second(s)\n", mode, remaining);
			k_msleep(1000);
		}

		gpio_pin_set_dt(&led, 0);
	} else {
		for (int remaining = PREPARE_SECONDS; remaining > 0; remaining--) {
			printk("Entering %s in %d second(s)\n", mode, remaining);
			k_msleep(1000);
		}
	}
}

static void clear_pending_irqs(void)
{
	LL_EXTI_ClearRisingFlag_0_31(LL_EXTI_LINE_ALL_0_31);
	LL_EXTI_ClearFallingFlag_0_31(LL_EXTI_LINE_ALL_0_31);
	LL_EXTI_ClearRisingFlag_32_63(LL_EXTI_LINE_ALL_32_63);
	LL_EXTI_ClearFallingFlag_32_63(LL_EXTI_LINE_ALL_32_63);

	for (size_t i = 0; i < ARRAY_SIZE(NVIC->ICPR); i++) {
		NVIC->ICPR[i] = UINT32_MAX;
	}

	SCB->ICSR = SCB_ICSR_PENDSTCLR_Msk | SCB_ICSR_PENDSVCLR_Msk;
}

static void release_console_and_usb_pins(void)
{
	LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_GPIOA);

	LL_GPIO_SetPinMode(GPIOA, LL_GPIO_PIN_9 | LL_GPIO_PIN_10 |
				  LL_GPIO_PIN_11 | LL_GPIO_PIN_12,
			   LL_GPIO_MODE_ANALOG);
	LL_GPIO_SetPinPull(GPIOA, LL_GPIO_PIN_9 | LL_GPIO_PIN_10 |
				  LL_GPIO_PIN_11 | LL_GPIO_PIN_12,
			   LL_GPIO_PULL_NO);
}

static void disable_console_uart(void)
{
#ifdef USART1
	NVIC_DisableIRQ(USART1_IRQn);
	NVIC_ClearPendingIRQ(USART1_IRQn);

	LL_USART_Disable(USART1);
	LL_APB2_GRP1_DisableClock(LL_APB2_GRP1_PERIPH_USART1);
	LL_APB2_GRP1_DisableClockLowPower(LL_APB2_GRP1_PERIPH_USART1);
#endif
}

static void disable_usb_peripheral(void)
{
#if IS_ENABLED(CONFIG_UDC_DRIVER) && DT_NODE_EXISTS(DT_NODELABEL(zephyr_udc0))
	const struct device *const udc = DEVICE_DT_GET(DT_NODELABEL(zephyr_udc0));

	if (device_is_ready(udc)) {
		(void)udc_disable(udc);
	}
#endif

#ifdef USB_DRD_FS_IRQn
	NVIC_DisableIRQ(USB_DRD_FS_IRQn);
	NVIC_ClearPendingIRQ(USB_DRD_FS_IRQn);
#endif

#ifdef LL_APB2_GRP1_PERIPH_USB
	LL_APB2_GRP1_DisableClock(LL_APB2_GRP1_PERIPH_USB);
	LL_APB2_GRP1_DisableClockLowPower(LL_APB2_GRP1_PERIPH_USB);
#endif
}

static void disable_debug_low_power_emulation(void)
{
#ifdef DBGMCU
	DBGMCU->CR &= ~(DBGMCU_CR_DBG_SLEEP | DBGMCU_CR_DBG_STOP |
		       DBGMCU_CR_DBG_STANDBY | DBGMCU_CR_TRACE_IOEN |
		       DBGMCU_CR_TRACE_EN);
#endif
}

static void set_gpio_output(GPIO_TypeDef *gpio, uint32_t pin, bool high)
{
	if (high) {
		LL_GPIO_SetOutputPin(gpio, pin);
	} else {
		LL_GPIO_ResetOutputPin(gpio, pin);
	}

	LL_GPIO_SetPinMode(gpio, pin, LL_GPIO_MODE_OUTPUT);
	LL_GPIO_SetPinOutputType(gpio, pin, LL_GPIO_OUTPUT_PUSHPULL);
	LL_GPIO_SetPinSpeed(gpio, pin, LL_GPIO_SPEED_FREQ_LOW);
	LL_GPIO_SetPinPull(gpio, pin, LL_GPIO_PULL_NO);
}

static void set_gpio_analog(GPIO_TypeDef *gpio, uint32_t pin)
{
	LL_GPIO_SetPinMode(gpio, pin, LL_GPIO_MODE_ANALOG);
	LL_GPIO_SetPinPull(gpio, pin, LL_GPIO_PULL_NO);
}

static void bitbang_spi_write_byte(uint8_t byte)
{
	for (int bit = 7; bit >= 0; bit--) {
		if ((byte & BIT(bit)) != 0U) {
			LL_GPIO_SetOutputPin(EXT_FLASH_IO0_PORT, EXT_FLASH_IO0_PIN);
		} else {
			LL_GPIO_ResetOutputPin(EXT_FLASH_IO0_PORT, EXT_FLASH_IO0_PIN);
		}

		k_busy_wait(1);
		LL_GPIO_SetOutputPin(EXT_FLASH_CLK_PORT, EXT_FLASH_CLK_PIN);
		k_busy_wait(1);
		LL_GPIO_ResetOutputPin(EXT_FLASH_CLK_PORT, EXT_FLASH_CLK_PIN);
	}
}

static void enter_external_flash_deep_power_down(void)
{
	LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_GPIOA);
	LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_GPIOB);

	/* PY25Q128HA DP command: CS# low, send B9h in SPI mode 0, CS# high. */
	set_gpio_output(EXT_FLASH_CS_PORT, EXT_FLASH_CS_PIN, true);
	set_gpio_output(EXT_FLASH_CLK_PORT, EXT_FLASH_CLK_PIN, false);
	set_gpio_output(EXT_FLASH_IO0_PORT, EXT_FLASH_IO0_PIN, false);
	set_gpio_output(EXT_FLASH_IO2_PORT, EXT_FLASH_IO2_PIN, true);
	set_gpio_output(EXT_FLASH_IO3_PORT, EXT_FLASH_IO3_PIN, true);
	set_gpio_analog(EXT_FLASH_IO1_PORT, EXT_FLASH_IO1_PIN);
	k_busy_wait(1);

	LL_GPIO_ResetOutputPin(EXT_FLASH_CS_PORT, EXT_FLASH_CS_PIN);
	k_busy_wait(1);
	bitbang_spi_write_byte(EXT_FLASH_CMD_DEEP_POWER_DOWN);
	k_busy_wait(1);
	LL_GPIO_SetOutputPin(EXT_FLASH_CS_PORT, EXT_FLASH_CS_PIN);
	k_busy_wait(EXT_FLASH_TDP_US);
}

static void prepare_external_flash_for_low_power(void)
{
	enter_external_flash_deep_power_down();

	/* Keep the NOR flash deselected and in deep power-down. WP#/HOLD# stay
	 * at valid CMOS levels; SCLK/IO0/IO1 go analog to minimize leakage.
	 */
	set_gpio_output(EXT_FLASH_CS_PORT, EXT_FLASH_CS_PIN, true);
	set_gpio_output(EXT_FLASH_IO2_PORT, EXT_FLASH_IO2_PIN, true);
	set_gpio_output(EXT_FLASH_IO3_PORT, EXT_FLASH_IO3_PIN, true);

	set_gpio_analog(EXT_FLASH_CLK_PORT, EXT_FLASH_CLK_PIN);
	set_gpio_analog(EXT_FLASH_IO0_PORT, EXT_FLASH_IO0_PIN);
	set_gpio_analog(EXT_FLASH_IO1_PORT, EXT_FLASH_IO1_PIN);
}

static void prepare_board_for_stop(void)
{
#if DT_NODE_HAS_PROP(CAN_PHY_NODE, standby_gpios)
	if (gpio_is_ready_dt(&can_stb)) {
		(void)gpio_pin_configure_dt(&can_stb, GPIO_OUTPUT_ACTIVE);
	}
#endif

	if (gpio_is_ready_dt(&led)) {
		(void)gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
	}

	prepare_external_flash_for_low_power();
	release_console_and_usb_pins();
	disable_console_uart();
	disable_usb_peripheral();
	disable_debug_low_power_emulation();
	clear_pending_irqs();
}

int main(void)
{
	prepare_for_low_power(LOW_POWER_STOP_NAME);

	printk("Entering %s now. Reset the board to exit this test.\n", LOW_POWER_STOP_NAME);
	k_msleep(20);

	prepare_board_for_stop();
	SysTick->CTRL &= ~SysTick_CTRL_ENABLE_Msk;
	__disable_irq();

	LL_PWR_ClearFlag_STOP();
	LL_PWR_EnableFlashLowPWRMode();
	LL_PWR_SetPowerMode(LOW_POWER_STOP_MODE);
	SCB_EnableDeepSleep();

	while (true) {
		__DSB();
		__WFI();
	}

	return 0;
}
