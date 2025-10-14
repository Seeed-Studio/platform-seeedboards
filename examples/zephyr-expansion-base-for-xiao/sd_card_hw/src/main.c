/*
 * Copyright (c) 2019 Tavish Naruka <tavishnaruka@gmail.com>
 * Copyright (c) 2023 Nordic Semiconductor ASA
 * Copyright (c) 2023 Antmicro <www.antmicro.com>
 * Copyright (c) 2025 Seeed Technology Co.,Ltd
 *
 * SPDX-License-Identifier: Apache-2.0
 */

/** @file
 * @brief SD Card and ZMS Storage Sample for XIAO nRF54L15
 * 
 * This sample demonstrates:
 * - Using the filesystem API with SDHC driver for SD card access
 * - Using ZMS (Zephyr Memory Storage) for persistent settings on nRF54L15
 * - Reading/writing files on SD card
 * - Storing configuration data in ZMS
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/logging/log.h>
#include <zephyr/fs/fs.h>
#include <zephyr/fs/zms.h>
#include <zephyr/settings/settings.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/storage/flash_map.h>

#ifdef CONFIG_NRFX_POWER
#include <nrfx_power.h>
#endif

#if defined(CONFIG_FAT_FILESYSTEM_ELM)

#include <ff.h>

/*
 *  Note the fatfs library is able to mount only strings inside _VOLUME_STRS
 *  in ffconf.h
 */
#if defined(CONFIG_DISK_DRIVER_MMC)
#define DISK_DRIVE_NAME "SD2"
#else
#define DISK_DRIVE_NAME "SD"
#endif

#define DISK_MOUNT_PT "/"DISK_DRIVE_NAME":"

static FATFS fat_fs;
/* mounting info */
static struct fs_mount_t mp = {
	.type = FS_FATFS,
	.fs_data = &fat_fs,
};

#elif defined(CONFIG_FILE_SYSTEM_EXT2)

#include <zephyr/fs/ext2.h>

#define DISK_DRIVE_NAME "SD"
#define DISK_MOUNT_PT "/ext"

static struct fs_mount_t mp = {
	.type = FS_EXT2,
	.flags = FS_MOUNT_FLAG_NO_FORMAT,
	.storage_dev = (void *)DISK_DRIVE_NAME,
	.mnt_point = "/ext",
};

#endif

#if defined(CONFIG_FAT_FILESYSTEM_ELM)
#define FS_RET_OK FR_OK
#else
#define FS_RET_OK 0
#endif

LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

#define MAX_PATH 128
#define SOME_FILE_NAME "some.dat"
#define SOME_DIR_NAME "some"
#define SOME_REQUIRED_LEN MAX(sizeof(SOME_FILE_NAME), sizeof(SOME_DIR_NAME))

/* ZMS Configuration */
#ifdef CONFIG_ZMS
#define ZMS_PARTITION_ID FIXED_PARTITION_ID(storage_partition)
/* Storage partition is 8KB (0x2000 bytes) at 0x15c000 */
/* Use 2 sectors of 4KB = 8KB */
#define ZMS_SECTOR_SIZE 4096
#define ZMS_SECTOR_COUNT 2

static struct zms_fs zms = {
	.sector_size = ZMS_SECTOR_SIZE,
	.sector_count = ZMS_SECTOR_COUNT,
};

/* ZMS Data IDs */
#define ZMS_ID_BOOT_COUNT 1
#define ZMS_ID_SD_ACCESS_COUNT 2
#define ZMS_ID_CONFIG_VERSION 3

static int zms_init(void)
{
	int rc;
	struct flash_pages_info info;
	
	zms.flash_device = DEVICE_DT_GET(DT_CHOSEN(zephyr_flash_controller));
	if (!device_is_ready(zms.flash_device)) {
		LOG_ERR("Flash device not ready");
		return -ENODEV;
	}

	zms.offset = FIXED_PARTITION_OFFSET(storage_partition);
	rc = flash_get_page_info_by_offs(zms.flash_device, zms.offset, &info);
	if (rc) {
		LOG_ERR("Unable to get page info (err %d)", rc);
		return rc;
	}

	/* Verify our configured sector size fits in the partition */
	uint32_t partition_size = FIXED_PARTITION_SIZE(storage_partition);
	uint32_t required_size = zms.sector_size * zms.sector_count;
	
	if (required_size > partition_size) {
		LOG_ERR("ZMS config too large: %u bytes required, %u available", 
			required_size, partition_size);
		return -EINVAL;
	}
	
	LOG_INF("ZMS using %u sectors of %u bytes = %u bytes total (partition: %u bytes)",
		zms.sector_count, zms.sector_size, required_size, partition_size);

	rc = zms_mount(&zms);
	if (rc) {
		LOG_ERR("ZMS mount failed (err %d)", rc);
		return rc;
	}

	LOG_INF("ZMS mounted successfully at offset 0x%lx", (unsigned long)zms.offset);
	return 0;
}

static void zms_demo(void)
{
	int rc;
	uint32_t boot_count = 0;
	uint32_t sd_access_count = 0;
	uint16_t config_version = 100;

	/* Read boot count */
	rc = zms_read(&zms, ZMS_ID_BOOT_COUNT, &boot_count, sizeof(boot_count));
	if (rc > 0) {
		LOG_INF("Boot count: %u", boot_count);
		boot_count++;
	} else {
		LOG_INF("Boot count not found, initializing to 1");
		boot_count = 1;
	}

	/* Write updated boot count */
	rc = zms_write(&zms, ZMS_ID_BOOT_COUNT, &boot_count, sizeof(boot_count));
	if (rc < 0) {
		LOG_ERR("Failed to write boot count (err %d)", rc);
	} else {
		LOG_INF("Updated boot count to: %u", boot_count);
	}

	/* Read SD access count */
	rc = zms_read(&zms, ZMS_ID_SD_ACCESS_COUNT, &sd_access_count, sizeof(sd_access_count));
	if (rc > 0) {
		LOG_INF("SD access count: %u", sd_access_count);
	}

	/* Write config version */
	rc = zms_write(&zms, ZMS_ID_CONFIG_VERSION, &config_version, sizeof(config_version));
	if (rc < 0) {
		LOG_ERR("Failed to write config version (err %d)", rc);
	} else {
		LOG_INF("Stored config version: %u", config_version);
	}
}

static void zms_update_sd_count(void)
{
	int rc;
	uint32_t sd_access_count = 0;

	rc = zms_read(&zms, ZMS_ID_SD_ACCESS_COUNT, &sd_access_count, sizeof(sd_access_count));
	if (rc > 0) {
		sd_access_count++;
	} else {
		sd_access_count = 1;
	}

	rc = zms_write(&zms, ZMS_ID_SD_ACCESS_COUNT, &sd_access_count, sizeof(sd_access_count));
	if (rc >= 0) {
		LOG_INF("SD card accessed %u times", sd_access_count);
	}
}
#endif /* CONFIG_ZMS */

static int lsdir(const char *path);

static bool create_some_entries(const char *base_path)
{
	char path[MAX_PATH];
	struct fs_file_t file;
	int base = strlen(base_path);

	fs_file_t_init(&file);

	if (base >= (sizeof(path) - SOME_REQUIRED_LEN)) {
		LOG_ERR("Not enough concatenation buffer to create file paths");
		return false;
	}

	LOG_INF("Creating some dir entries in %s", base_path);
	strncpy(path, base_path, sizeof(path));

	path[base++] = '/';
	path[base] = 0;
	strcat(&path[base], SOME_FILE_NAME);

	if (fs_open(&file, path, FS_O_CREATE) != 0) {
		LOG_ERR("Failed to create file %s", path);
		return false;
	}
	fs_close(&file);

	path[base] = 0;
	strcat(&path[base], SOME_DIR_NAME);

	if (fs_mkdir(path) != 0) {
		LOG_ERR("Failed to create dir %s", path);
		/* If code gets here, it has at least successes to create the
		 * file so allow function to return true.
		 */
	}
	return true;
}

static const char *disk_mount_pt = DISK_MOUNT_PT;

int main(void)
{
	LOG_INF("========================================");
	LOG_INF("XIAO nRF54L15 SD Card + ZMS Sample");
	LOG_INF("========================================");

#ifdef CONFIG_NRFX_POWER
	/* Enable constant-latency mode for stable high-speed SPI operation */
	nrfx_power_constlat_mode_request();
	LOG_INF("Constant-latency mode enabled for stable SPI operation");
#endif

#ifdef CONFIG_ZMS
	/* Initialize ZMS for persistent storage */
	LOG_INF("Initializing ZMS...");
	int zms_rc = zms_init();
	if (zms_rc == 0) {
		zms_demo();
	} else {
		LOG_ERR("ZMS initialization failed, continuing without persistent storage");
	}
#endif

	/* raw disk i/o */
	LOG_INF("Initializing SD card...");
	do {
		static const char *disk_pdrv = DISK_DRIVE_NAME;
		uint64_t memory_size_mb;
		uint32_t block_count;
		uint32_t block_size;

		if (disk_access_ioctl(disk_pdrv,
				DISK_IOCTL_CTRL_INIT, NULL) != 0) {
			LOG_ERR("SD card init ERROR! Please check:");
			LOG_ERR("  - SD card is inserted");
			LOG_ERR("  - SD card is formatted (FAT32/exFAT)");
			LOG_ERR("  - Connections are correct");
			break;
		}

		if (disk_access_ioctl(disk_pdrv,
				DISK_IOCTL_GET_SECTOR_COUNT, &block_count)) {
			LOG_ERR("Unable to get sector count");
			break;
		}
		LOG_INF("SD Card - Block count: %u", block_count);

		if (disk_access_ioctl(disk_pdrv,
				DISK_IOCTL_GET_SECTOR_SIZE, &block_size)) {
			LOG_ERR("Unable to get sector size");
			break;
		}
		LOG_INF("SD Card - Sector size: %u bytes", block_size);

		memory_size_mb = (uint64_t)block_count * block_size;
		LOG_INF("SD Card - Total size: %u MB", (uint32_t)(memory_size_mb >> 20));

#ifdef CONFIG_ZMS
		/* Update SD card access counter in ZMS */
		zms_update_sd_count();
#endif

		if (disk_access_ioctl(disk_pdrv,
				DISK_IOCTL_CTRL_DEINIT, NULL) != 0) {
			LOG_ERR("Storage deinit ERROR!");
			break;
		}
	} while (0);

	mp.mnt_point = disk_mount_pt;

	LOG_INF("Mounting SD card filesystem...");
	int res = fs_mount(&mp);

	if (res == FS_RET_OK) {
		LOG_INF("SD card mounted at %s", disk_mount_pt);
		
		/* Test unmount and remount */
		LOG_INF("Testing unmount/remount...");
		res = fs_unmount(&mp);
		if (res != FS_RET_OK) {
			LOG_ERR("Error unmounting disk");
			return res;
		}
		
		res = fs_mount(&mp);
		if (res != FS_RET_OK) {
			LOG_ERR("Error remounting disk");
			return res;
		}
		LOG_INF("Unmount/remount test successful");

		/* List directory contents */
		if (lsdir(disk_mount_pt) >= 0) {
			LOG_INF("Creating sample files and directories...");
			if (create_some_entries(disk_mount_pt)) {
				LOG_INF("Sample entries created, listing again:");
				lsdir(disk_mount_pt);
			}
		}
		
		/* Write a test file with timestamp */
		char test_file_path[64];
		snprintf(test_file_path, sizeof(test_file_path), "%s/test.txt", disk_mount_pt);
		struct fs_file_t test_file;
		fs_file_t_init(&test_file);
		
		res = fs_open(&test_file, test_file_path, FS_O_CREATE | FS_O_WRITE);
		if (res == 0) {
			const char *test_data = "XIAO nRF54L15 SD Card Test\n";
			fs_write(&test_file, test_data, strlen(test_data));
			fs_close(&test_file);
			LOG_INF("Created test file: %s", test_file_path);
		} else {
			LOG_WRN("Could not create test file (err %d)", res);
		}
		
		/* Unmount before exiting */
		fs_unmount(&mp);
		LOG_INF("SD card unmounted");
	} else {
		LOG_ERR("Failed to mount SD card (err %d)", res);
		LOG_ERR("Common issues:");
		LOG_ERR("  - SD card not formatted (use FAT32)");
		LOG_ERR("  - SD card not inserted properly");
		LOG_ERR("  - Incompatible SD card");
	}

	LOG_INF("========================================");
	LOG_INF("Sample completed. System will idle.");
	LOG_INF("========================================");

	while (1) {
		k_sleep(K_SECONDS(1));
	}
	return 0;
}

/* List dir entry by path
 *
 * @param path Absolute path to list
 *
 * @return Negative errno code on error, number of listed entries on
 *         success.
 */
static int lsdir(const char *path)
{
	int res;
	struct fs_dir_t dirp;
	static struct fs_dirent entry;
	int count = 0;

	fs_dir_t_init(&dirp);

	/* Verify fs_opendir() */
	res = fs_opendir(&dirp, path);
	if (res) {
		printk("Error opening dir %s [%d]\n", path, res);
		return res;
	}

	printk("\nListing dir %s ...\n", path);
	for (;;) {
		/* Verify fs_readdir() */
		res = fs_readdir(&dirp, &entry);

		/* entry.name[0] == 0 means end-of-dir */
		if (res || entry.name[0] == 0) {
			break;
		}

		if (entry.type == FS_DIR_ENTRY_DIR) {
			printk("[DIR ] %s\n", entry.name);
		} else {
			printk("[FILE] %s (size = %zu)\n",
				entry.name, entry.size);
		}
		count++;
	}

	/* Verify fs_closedir() */
	fs_closedir(&dirp);
	if (res == 0) {
		res = count;
	}

	return res;
}
