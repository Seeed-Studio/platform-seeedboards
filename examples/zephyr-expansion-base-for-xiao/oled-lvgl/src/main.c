#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <lvgl.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/drivers/display.h>
#include <zephyr/drivers/rtc.h>

#define LOG_LEVEL CONFIG_LOG_DEFAULT_LEVEL
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(main_app, LOG_LEVEL);


static void set_compile_time(const struct device *rtc_dev)
{
    struct rtc_time tm;
    char month_str[4];
    int month, day, year;
    sscanf(__DATE__, "%s %d %d", month_str, &day, &year);

    if (strcmp(month_str, "Jan") == 0) month = 1;
    else if (strcmp(month_str, "Feb") == 0) month = 2;
    else if (strcmp(month_str, "Mar") == 0) month = 3;
    else if (strcmp(month_str, "Apr") == 0) month = 4;
    else if (strcmp(month_str, "May") == 0) month = 5;
    else if (strcmp(month_str, "Jun") == 0) month = 6;
    else if (strcmp(month_str, "Jul") == 0) month = 7;
    else if (strcmp(month_str, "Aug") == 0) month = 8;
    else if (strcmp(month_str, "Sep") == 0) month = 9;
    else if (strcmp(month_str, "Oct") == 0) month = 10;
    else if (strcmp(month_str, "Nov") == 0) month = 11;
    else if (strcmp(month_str, "Dec") == 0) month = 12;

    tm.tm_year = year - 1900;
    tm.tm_mon = month - 1;
    tm.tm_mday = day;

    sscanf(__TIME__, "%d:%d:%d", &tm.tm_hour, &tm.tm_min, &tm.tm_sec);

    // tm_wday is not set, but it's not critical for this application
    tm.tm_wday = 0; 

    rtc_set_time(rtc_dev, &tm);
}


int main(void)
{
	const struct device *display_dev;
	const struct device *rtc_dev;

	display_dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_display));
	if (!device_is_ready(display_dev)) {
		LOG_ERR("Device not ready, aborting test");
		return -1;
	}

	rtc_dev = DEVICE_DT_GET(DT_ALIAS(rtc));
    if (!device_is_ready(rtc_dev)) {
        LOG_ERR("RTC device not ready");
        return -1;
    }

	set_compile_time(rtc_dev);

	lv_obj_t *date_label;
	lv_obj_t *time_label;

	date_label = lv_label_create(lv_scr_act());
	lv_obj_align(date_label, LV_ALIGN_TOP_MID, 0, 8);

	time_label = lv_label_create(lv_scr_act());
	lv_obj_align(time_label, LV_ALIGN_CENTER, 0, 0);
	lv_obj_set_style_text_font(time_label, &lv_font_montserrat_24, 0);


	lv_task_handler();
	display_blanking_off(display_dev);

	struct rtc_time tm;
    char date_str[36];
    char time_str[11];

	while (1) {
		rtc_get_time(rtc_dev, &tm);
        snprintf(date_str, sizeof(date_str), "%04d-%02d-%02d", tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday);
        snprintf(time_str, sizeof(time_str), "%02d:%02d:%02d", tm.tm_hour, tm.tm_min, tm.tm_sec);

        lv_label_set_text(date_label, date_str);
        lv_label_set_text(time_label, time_str);

		lv_task_handler();
		k_sleep(K_MSEC(1000));
	}
	return 0;
}

