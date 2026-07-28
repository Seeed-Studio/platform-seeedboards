/*
 * Copyright (c) 2026 Seeed Technology Co., Ltd.
 * SPDX-License-Identifier: Apache-2.0
 */

#include <string.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/kernel.h>

#define EXT_FLASH_NODE DT_NODELABEL(ext_flash)

#if !DT_NODE_EXISTS(EXT_FLASH_NODE)
#error "External flash node ext_flash is not defined"
#endif

#define TEST_OFFSET 0x00100000
#define TEST_LEN 256

static uint8_t write_buf[TEST_LEN];
static uint8_t read_buf[TEST_LEN];

int main(void)
{
	const struct device *flash = DEVICE_DT_GET(EXT_FLASH_NODE);
	struct flash_pages_info page;
	uint8_t jedec_id[3];
	int ret;

	printk("XIAO STM32C5 external flash sample\n");

	if (!device_is_ready(flash)) {
		printk("External flash device is not ready: %s\n", flash->name);
		return 0;
	}

	printk("Device: %s\n", flash->name);

	ret = flash_read_jedec_id(flash, jedec_id);
	if (ret == 0) {
		printk("JEDEC ID: %02x %02x %02x\n", jedec_id[0], jedec_id[1], jedec_id[2]);
	} else {
		printk("JEDEC ID read failed: %d\n", ret);
	}

	ret = flash_get_page_info_by_offs(flash, TEST_OFFSET, &page);
	if (ret != 0) {
		printk("flash_get_page_info_by_offs(0x%x) failed: %d\n", TEST_OFFSET, ret);
		return 0;
	}

	printk("Test offset: 0x%x, erase page size: %zu\n", TEST_OFFSET, page.size);

	for (size_t i = 0; i < sizeof(write_buf); i++) {
		write_buf[i] = (uint8_t)(0xa5 ^ i);
		read_buf[i] = 0;
	}

	ret = flash_erase(flash, page.start_offset, page.size);
	if (ret != 0) {
		printk("flash_erase(0x%lx, %zu) failed: %d\n",
		       (unsigned long)page.start_offset, page.size, ret);
		return 0;
	}

	ret = flash_write(flash, TEST_OFFSET, write_buf, sizeof(write_buf));
	if (ret != 0) {
		printk("flash_write(0x%x, %zu) failed: %d\n", TEST_OFFSET, sizeof(write_buf), ret);
		return 0;
	}

	ret = flash_read(flash, TEST_OFFSET, read_buf, sizeof(read_buf));
	if (ret != 0) {
		printk("flash_read(0x%x, %zu) failed: %d\n", TEST_OFFSET, sizeof(read_buf), ret);
		return 0;
	}

	ret = memcmp(write_buf, read_buf, sizeof(write_buf));
	if (ret == 0) {
		printk("External flash write/read verify passed.\n");
	} else {
		for (size_t i = 0; i < sizeof(write_buf); i++) {
			if (write_buf[i] != read_buf[i]) {
				printk("Verify failed at +0x%zx: wrote 0x%02x read 0x%02x\n",
				       i, write_buf[i], read_buf[i]);
				break;
			}
		}
	}

	return 0;
}
