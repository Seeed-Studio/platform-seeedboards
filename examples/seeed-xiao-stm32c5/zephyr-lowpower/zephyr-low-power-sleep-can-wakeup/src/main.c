/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * XIAO STM32C5 CAN wake from Sleep sample.
 */

#include <stdbool.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/can.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/usb/udc.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/sys_io.h>

#include <cmsis_core.h>
#include <stm32_ll_bus.h>
#include <stm32_ll_gpio.h>
#include <stm32_ll_rcc.h>
#include <stm32_ll_usart.h>

#define CANBUS_NODE DT_CHOSEN(zephyr_canbus)
#define CAN_PHY_NODE DT_NODELABEL(can_phy0)
#define CAN_RX_GPIO_NODE DT_NODELABEL(gpiob)
#define LED0_NODE DT_ALIAS(led0)

#define CAN_BITRATE 500000U
#define RX_QUEUE_DEPTH 8
#define PREPARE_SECONDS 5
#define SLEEP_UART_BAUDRATE 115200U
#define SLEEP_SYSCLK_HZ 48000000U
#define CAN_RX_WAKE_PIN 5U

#define FDCAN2_BASE_ADDR 0x4000a800UL
#define FDCAN_IR_OFFSET 0x050UL
#define FDCAN_IE_OFFSET 0x054UL
#define FDCAN_ILS_OFFSET 0x058UL
#define FDCAN_ILE_OFFSET 0x05cUL
#define FDCAN_RXF0S_OFFSET 0x0a4UL
#define FDCAN_RXF1S_OFFSET 0x0b8UL

static const struct device *const can_dev = DEVICE_DT_GET(CANBUS_NODE);
static const struct device *const can_rx_gpio = DEVICE_DT_GET(CAN_RX_GPIO_NODE);
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static struct gpio_callback can_rx_wake_cb;
static volatile bool can_rx_wake_seen;

#if DT_NODE_HAS_PROP(CAN_PHY_NODE, standby_gpios)
static const struct gpio_dt_spec can_stb = GPIO_DT_SPEC_GET(CAN_PHY_NODE, standby_gpios);
#endif

CAN_MSGQ_DEFINE(rx_msgq, RX_QUEUE_DEPTH);

static void print_frame(const struct can_frame *frame)
{
	uint8_t len = can_dlc_to_bytes(frame->dlc);

	printk("CAN wake frame: id=%s 0x%0*x dlc=%u len=%u data=",
	       (frame->flags & CAN_FRAME_IDE) != 0U ? "ext" : "std",
	       (frame->flags & CAN_FRAME_IDE) != 0U ? 8 : 3,
	       frame->id, frame->dlc, len);

	for (uint8_t i = 0; i < len; i++) {
		printk("%02x%s", frame->data[i], i + 1U == len ? "" : " ");
	}

	printk("\n");
}

static void prepare_countdown(void)
{
	printk("XIAO STM32C5 CAN wake from Sleep sample\n");
	printk("Listening on %s at %u bps. Send any Classic CAN frame to wake.\n",
	       can_dev->name, CAN_BITRATE);
	printk("Entering Sleep in %d seconds.\n", PREPARE_SECONDS);

	if (gpio_is_ready_dt(&led) &&
	    gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE) == 0) {
		for (int remaining = PREPARE_SECONDS; remaining > 0; remaining--) {
			gpio_pin_toggle_dt(&led);
			printk("%d...\n", remaining);
			k_sleep(K_SECONDS(1));
		}

		gpio_pin_set_dt(&led, 0);
	} else {
		for (int remaining = PREPARE_SECONDS; remaining > 0; remaining--) {
			printk("%d...\n", remaining);
			k_sleep(K_SECONDS(1));
		}
	}
}

static void clear_pending_irqs(void)
{
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

static void restore_console_pins(void)
{
	LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_GPIOA);

	LL_GPIO_SetPinMode(GPIOA, LL_GPIO_PIN_9 | LL_GPIO_PIN_10,
			   LL_GPIO_MODE_ALTERNATE);
	LL_GPIO_SetAFPin_8_15(GPIOA, LL_GPIO_PIN_9 | LL_GPIO_PIN_10,
			      LL_GPIO_AF_7);
	LL_GPIO_SetPinPull(GPIOA, LL_GPIO_PIN_9 | LL_GPIO_PIN_10,
			   LL_GPIO_PULL_UP);
	LL_GPIO_SetPinSpeed(GPIOA, LL_GPIO_PIN_9 | LL_GPIO_PIN_10,
			    LL_GPIO_SPEED_FREQ_HIGH);
	LL_GPIO_SetPinOutputType(GPIOA, LL_GPIO_PIN_9 | LL_GPIO_PIN_10,
				 LL_GPIO_OUTPUT_PUSHPULL);
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

static void restore_console_uart(void)
{
#ifdef USART1
	restore_console_pins();

	LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_USART1);
	LL_USART_Disable(USART1);
	LL_USART_SetBaudRate(USART1, SLEEP_SYSCLK_HZ, LL_USART_PRESCALER_DIV1,
			      LL_USART_OVERSAMPLING_16, SLEEP_UART_BAUDRATE);
	LL_USART_EnableDirectionTx(USART1);
	LL_USART_EnableDirectionRx(USART1);
	LL_USART_Enable(USART1);

	for (uint32_t timeout = 100000U;
	     timeout > 0U &&
	     (LL_USART_IsActiveFlag_TEACK(USART1) == 0U ||
	      LL_USART_IsActiveFlag_REACK(USART1) == 0U);
	     timeout--) {
	}
#endif
}

static void restore_usb_pins(void)
{
	LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_GPIOA);

	LL_GPIO_SetPinMode(GPIOA, LL_GPIO_PIN_11 | LL_GPIO_PIN_12,
			   LL_GPIO_MODE_ALTERNATE);
	LL_GPIO_SetAFPin_8_15(GPIOA, LL_GPIO_PIN_11 | LL_GPIO_PIN_12,
			      LL_GPIO_AF_10);
	LL_GPIO_SetPinPull(GPIOA, LL_GPIO_PIN_11 | LL_GPIO_PIN_12,
			   LL_GPIO_PULL_NO);
	LL_GPIO_SetPinSpeed(GPIOA, LL_GPIO_PIN_11 | LL_GPIO_PIN_12,
			    LL_GPIO_SPEED_FREQ_HIGH);
	LL_GPIO_SetPinOutputType(GPIOA, LL_GPIO_PIN_11 | LL_GPIO_PIN_12,
				 LL_GPIO_OUTPUT_PUSHPULL);
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

static void restore_usb_peripheral(void)
{
#ifdef LL_APB2_GRP1_PERIPH_USB
	LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_USB);
	LL_APB2_GRP1_EnableClockLowPower(LL_APB2_GRP1_PERIPH_USB);
#endif

	restore_usb_pins();

#ifdef USB_DRD_FS_IRQn
	NVIC_ClearPendingIRQ(USB_DRD_FS_IRQn);
	NVIC_EnableIRQ(USB_DRD_FS_IRQn);
#endif

#if IS_ENABLED(CONFIG_UDC_DRIVER) && DT_NODE_EXISTS(DT_NODELABEL(zephyr_udc0))
	const struct device *const udc = DEVICE_DT_GET(DT_NODELABEL(zephyr_udc0));

	if (device_is_ready(udc)) {
		(void)udc_enable(udc);
	}
#endif
}

static void switch_system_clock_to_hsidiv3_keep_fdcan_clock(void)
{
	LL_RCC_HSIDIV3_Enable();
	for (uint32_t timeout = 100000U;
	     timeout > 0U && LL_RCC_HSIDIV3_IsReady() == 0U; timeout--) {
	}

	if (LL_RCC_HSIDIV3_IsReady() == 0U) {
		return;
	}

	LL_RCC_SetAHBPrescaler(LL_RCC_HCLK_PRESCALER_1);
	LL_RCC_SetAPB1Prescaler(LL_RCC_APB1_PRESCALER_1);
	LL_RCC_SetAPB2Prescaler(LL_RCC_APB2_PRESCALER_1);
	LL_RCC_SetAPB3Prescaler(LL_RCC_APB3_PRESCALER_1);
	LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_HSIDIV3);

	for (uint32_t timeout = 100000U;
	     timeout > 0U &&
	     LL_RCC_GetSysClkSource() != LL_RCC_SYS_CLKSOURCE_STATUS_HSIDIV3;
	     timeout--) {
	}

	if (LL_RCC_GetSysClkSource() != LL_RCC_SYS_CLKSOURCE_STATUS_HSIDIV3) {
		return;
	}

	LL_RCC_HSIK_Disable();
	LL_RCC_HSIS_Disable();

#if defined(RCC_CR1_PSIKON)
	LL_RCC_PSIK_Disable();
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

static void disable_unused_sleep_clocks_keep_gpio_wake(void)
{
	LL_AHB1_GRP1_DisableClockLowPower(LL_AHB1_GRP1_PERIPH_ALL);
	LL_AHB2_GRP1_DisableClockLowPower(LL_AHB2_GRP1_PERIPH_ALL);
#ifdef LL_AHB4_GRP1_PERIPH_ALL
	LL_AHB4_GRP1_DisableClockLowPower(LL_AHB4_GRP1_PERIPH_ALL);
#endif

	LL_APB1_GRP1_DisableClockLowPower(LL_APB1_GRP1_PERIPH_ALL);
	LL_APB1_GRP2_DisableClockLowPower(LL_APB1_GRP2_PERIPH_ALL);
	LL_APB2_GRP1_DisableClockLowPower(LL_APB2_GRP1_PERIPH_ALL);
	LL_APB3_GRP1_DisableClockLowPower(LL_APB3_GRP1_PERIPH_ALL);

#ifdef LL_AHB2_GRP1_PERIPH_GPIOB
	LL_AHB2_GRP1_EnableClockLowPower(LL_AHB2_GRP1_PERIPH_GPIOB);
#endif

#ifdef LL_AHB4_GRP1_PERIPH_ALL
	LL_AHB4_DisableBusClock();
#endif
	LL_APB2_DisableBusClock();
	LL_APB3_DisableBusClock();
}

static void disable_fdcan_clock(void)
{
#ifdef LL_APB1_GRP2_PERIPH_FDCAN
	LL_APB1_GRP2_DisableClock(LL_APB1_GRP2_PERIPH_FDCAN);
	LL_APB1_GRP2_DisableClockLowPower(LL_APB1_GRP2_PERIPH_FDCAN);
#endif
}

static void enable_fdcan_clock(void)
{
#ifdef LL_APB1_GRP2_PERIPH_FDCAN
	LL_APB1_GRP2_EnableClock(LL_APB1_GRP2_PERIPH_FDCAN);
	LL_APB1_GRP2_EnableClockLowPower(LL_APB1_GRP2_PERIPH_FDCAN);
#endif
}

static void restore_active_bus_clocks(void)
{
	LL_AHB1_EnableBusClock();
	LL_AHB2_EnableBusClock();
#ifdef LL_AHB4_GRP1_PERIPH_ALL
	LL_AHB4_EnableBusClock();
#endif
	LL_APB1_EnableBusClock();
	LL_APB2_EnableBusClock();
	LL_APB3_EnableBusClock();
}

static void restore_active_sleep_clocks(void)
{
	LL_AHB1_GRP1_EnableClockLowPower(LL_AHB1_GRP1_PERIPH_ALL);
	LL_AHB2_GRP1_EnableClockLowPower(LL_AHB2_GRP1_PERIPH_ALL);
#ifdef LL_AHB4_GRP1_PERIPH_ALL
	LL_AHB4_GRP1_EnableClockLowPower(LL_AHB4_GRP1_PERIPH_ALL);
#endif

	LL_APB1_GRP1_EnableClockLowPower(LL_APB1_GRP1_PERIPH_ALL);
	LL_APB1_GRP2_EnableClockLowPower(LL_APB1_GRP2_PERIPH_ALL);
	LL_APB2_GRP1_EnableClockLowPower(LL_APB2_GRP1_PERIPH_ALL);
	LL_APB3_GRP1_EnableClockLowPower(LL_APB3_GRP1_PERIPH_ALL);
}

static void restore_debug_low_power_emulation(void)
{
#ifdef DBGMCU
	DBGMCU->CR |= DBGMCU_CR_DBG_SLEEP;
#endif
}

static void set_can_transceiver_normal(void)
{
#if DT_NODE_HAS_PROP(CAN_PHY_NODE, standby_gpios)
	if (gpio_is_ready_dt(&can_stb)) {
		(void)gpio_pin_configure_dt(&can_stb, GPIO_OUTPUT_INACTIVE);
	}
#endif
}

static void set_can_transceiver_standby(void)
{
#if DT_NODE_HAS_PROP(CAN_PHY_NODE, standby_gpios)
	if (gpio_is_ready_dt(&can_stb)) {
		(void)gpio_pin_configure_dt(&can_stb, GPIO_OUTPUT_ACTIVE);
	}
#endif
}

static void can_rx_wake_callback(const struct device *dev,
				 struct gpio_callback *cb,
				 uint32_t pins)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(cb);

	if ((pins & BIT(CAN_RX_WAKE_PIN)) != 0U) {
		can_rx_wake_seen = true;
	}
}

static void configure_can_rxd_as_wake_gpio(void)
{
	if (!device_is_ready(can_rx_gpio)) {
		return;
	}

	can_rx_wake_seen = false;
	(void)gpio_pin_interrupt_configure(can_rx_gpio, CAN_RX_WAKE_PIN,
					   GPIO_INT_DISABLE);
	(void)gpio_pin_configure(can_rx_gpio, CAN_RX_WAKE_PIN,
				 GPIO_INPUT | GPIO_PULL_UP);
	gpio_init_callback(&can_rx_wake_cb, can_rx_wake_callback,
			   BIT(CAN_RX_WAKE_PIN));
	(void)gpio_add_callback(can_rx_gpio, &can_rx_wake_cb);
	(void)gpio_pin_interrupt_configure(can_rx_gpio, CAN_RX_WAKE_PIN,
					   GPIO_INT_EDGE_FALLING);

	if (gpio_pin_get(can_rx_gpio, CAN_RX_WAKE_PIN) == 0) {
		can_rx_wake_seen = true;
	}
}

static void disable_can_rxd_wake_gpio(void)
{
	if (!device_is_ready(can_rx_gpio)) {
		return;
	}

	(void)gpio_pin_interrupt_configure(can_rx_gpio, CAN_RX_WAKE_PIN,
					   GPIO_INT_DISABLE);
	(void)gpio_remove_callback(can_rx_gpio, &can_rx_wake_cb);
}

static void restore_fdcan2_pins(void)
{
	LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_GPIOB);

	LL_GPIO_SetPinMode(GPIOB, LL_GPIO_PIN_5 | LL_GPIO_PIN_13,
			   LL_GPIO_MODE_ALTERNATE);
	LL_GPIO_SetAFPin_0_7(GPIOB, LL_GPIO_PIN_5, LL_GPIO_AF_9);
	LL_GPIO_SetAFPin_8_15(GPIOB, LL_GPIO_PIN_13, LL_GPIO_AF_9);
	LL_GPIO_SetPinPull(GPIOB, LL_GPIO_PIN_5 | LL_GPIO_PIN_13,
			   LL_GPIO_PULL_NO);
	LL_GPIO_SetPinSpeed(GPIOB, LL_GPIO_PIN_5 | LL_GPIO_PIN_13,
			    LL_GPIO_SPEED_FREQ_HIGH);
	LL_GPIO_SetPinOutputType(GPIOB, LL_GPIO_PIN_5 | LL_GPIO_PIN_13,
				 LL_GPIO_OUTPUT_PUSHPULL);
}

static uint32_t suspend_systick(void)
{
	uint32_t saved_ctrl = SysTick->CTRL;

	SysTick->CTRL = saved_ctrl & ~(SysTick_CTRL_ENABLE_Msk | SysTick_CTRL_TICKINT_Msk);
	SCB->ICSR = SCB_ICSR_PENDSTCLR_Msk | SCB_ICSR_PENDSVCLR_Msk;

	return saved_ctrl;
}

static void restore_systick(uint32_t saved_ctrl)
{
	SCB->ICSR = SCB_ICSR_PENDSTCLR_Msk | SCB_ICSR_PENDSVCLR_Msk;
	SysTick->CTRL = saved_ctrl;
}

static void prepare_board_for_can_sleep(void)
{
	if (gpio_is_ready_dt(&led)) {
		(void)gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
	}

	release_console_and_usb_pins();
	disable_console_uart();
	disable_usb_peripheral();
	disable_debug_low_power_emulation();
	switch_system_clock_to_hsidiv3_keep_fdcan_clock();
	disable_unused_sleep_clocks_keep_gpio_wake();
	clear_pending_irqs();
}

static void sleep_until_can_or_irq(void)
{
	uint32_t saved_systick_ctrl;
	int ret;

	ret = can_stop(can_dev);
	if (ret != 0 && ret != -EALREADY) {
		printk("Failed to stop CAN before Sleep: %d\n", ret);
		return;
	}

	set_can_transceiver_standby();
	k_busy_wait(200);
	configure_can_rxd_as_wake_gpio();
	disable_fdcan_clock();

	saved_systick_ctrl = suspend_systick();
	prepare_board_for_can_sleep();
	SCB->SCR &= ~SCB_SCR_SLEEPDEEP_Msk;

	if (!can_rx_wake_seen) {
		__DSB();
		__WFI();
		__ISB();
	}

	restore_active_bus_clocks();
	restore_active_sleep_clocks();
	restore_systick(saved_systick_ctrl);
	disable_can_rxd_wake_gpio();
	enable_fdcan_clock();
	restore_fdcan2_pins();
	set_can_transceiver_normal();
	k_busy_wait(200);
	restore_console_uart();
	restore_usb_peripheral();
	restore_debug_low_power_emulation();

	ret = can_start(can_dev);
	if (ret != 0 && ret != -EALREADY) {
		printk("Failed to restart CAN after wake: %d\n", ret);
	}
}

static int drain_rx_queue(void)
{
	struct can_frame frame;
	int count = 0;

	while (k_msgq_get(&rx_msgq, &frame, K_NO_WAIT) == 0) {
		print_frame(&frame);
		count++;
	}

	return count;
}

static void print_fdcan_rx_diag(void)
{
	printk("FDCAN diag: IR=%08x IE=%08x ILS=%08x ILE=%08x RXF0S=%08x RXF1S=%08x\n",
	       sys_read32(FDCAN2_BASE_ADDR + FDCAN_IR_OFFSET),
	       sys_read32(FDCAN2_BASE_ADDR + FDCAN_IE_OFFSET),
	       sys_read32(FDCAN2_BASE_ADDR + FDCAN_ILS_OFFSET),
	       sys_read32(FDCAN2_BASE_ADDR + FDCAN_ILE_OFFSET),
	       sys_read32(FDCAN2_BASE_ADDR + FDCAN_RXF0S_OFFSET),
	       sys_read32(FDCAN2_BASE_ADDR + FDCAN_RXF1S_OFFSET));
}

static int setup_can(void)
{
	const struct can_filter std_filter = {
		.flags = 0,
		.id = 0,
		.mask = 0,
	};
	const struct can_filter ext_filter = {
		.flags = CAN_FILTER_IDE,
		.id = 0,
		.mask = 0,
	};
	int ret;

	if (!device_is_ready(can_dev)) {
		printk("CAN device %s is not ready\n", can_dev->name);
		return -ENODEV;
	}

	ret = can_set_mode(can_dev, 0);
	if (ret != 0) {
		printk("Failed to set CAN mode: %d\n", ret);
		return ret;
	}

	ret = can_set_bitrate(can_dev, CAN_BITRATE);
	if (ret != 0) {
		printk("Failed to set CAN bitrate %u: %d\n", CAN_BITRATE, ret);
		return ret;
	}

	ret = can_add_rx_filter_msgq(can_dev, &rx_msgq, &std_filter);
	if (ret < 0) {
		printk("Failed to add standard RX filter: %d\n", ret);
		return ret;
	}

	ret = can_add_rx_filter_msgq(can_dev, &rx_msgq, &ext_filter);
	if (ret < 0) {
		printk("Failed to add extended RX filter: %d\n", ret);
		return ret;
	}

	ret = can_start(can_dev);
	if (ret != 0) {
		printk("Failed to start CAN controller: %d\n", ret);
		return ret;
	}

	return 0;
}

int main(void)
{
	int rx_count;

	if (setup_can() != 0) {
		return 0;
	}

	set_can_transceiver_normal();
	printk("CAN starts in normal mode. Sleep will place TCAN3403 in standby.\n");
	prepare_countdown();
	printk("Entering Sleep now. Send CAN bus traffic/WUP to pull RXD low and wake.\n");
	k_msleep(20);

	sleep_until_can_or_irq();

	if (gpio_is_ready_dt(&led)) {
		gpio_pin_set_dt(&led, 1);
	}

	printk("Wake event observed. Low-power changes restored; staying active.\n");
	printk("PB5/RXD wake flag: %s\n", can_rx_wake_seen ? "set" : "not set");
	print_fdcan_rx_diag();
	rx_count = drain_rx_queue();
	if (rx_count == 0) {
		printk("No CAN frame was queued. This is expected for transceiver standby wake.\n");
	} else {
		printk("CAN frame(s) queued after wake: %d\n", rx_count);
	}

	while (true) {
		rx_count = drain_rx_queue();
		if (rx_count > 0) {
			printk("Additional CAN frame(s): %d\n", rx_count);
		}

		if (gpio_is_ready_dt(&led)) {
			gpio_pin_toggle_dt(&led);
		}

		printk("Active after wake; not entering Sleep again.\n");
		k_sleep(K_SECONDS(2));
	}
}
