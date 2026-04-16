#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/logging/log.h>
#include <nrfx_power.h>
#include <string.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

// Register log module
LOG_MODULE_REGISTER(gps_app, LOG_LEVEL_INF);

// Type definitions
#define UBYTE uint8_t
#define UWORD uint16_t
#define UDOUBLE uint32_t

// Buffer sizes
#define SENTENCE_SIZE 100
#define BUFFSIZE 800

// NMEA Commands
#define HOT_START "$PMTK101"
#define WARM_START "$PMTK102"
#define COLD_START "$PMTK103"
#define FULL_COLD_START "$PMTK104"
#define SET_PERPETUAL_STANDBY_MODE "$PMTK161"
#define SET_PERIODIC_MODE "$PMTK225"
#define SET_NORMAL_MODE "$PMTK225,0"
#define SET_PERIODIC_BACKUP_MODE "$PMTK225,1,1000,2000"
#define SET_PERIODIC_STANDBY_MODE "$PMTK225,2,1000,2000"
#define SET_PERPETUAL_BACKUP_MODE "$PMTK225,4"
#define SET_ALWAYSLOCATE_STANDBY_MODE "$PMTK225,8"
#define SET_ALWAYSLOCATE_BACKUP_MODE "$PMTK225,9"
#define SET_POS_FIX "$PMTK220"
#define SET_POS_FIX_100MS "$PMTK220,100"
#define SET_POS_FIX_200MS "$PMTK220,200"
#define SET_POS_FIX_400MS "$PMTK220,400"
#define SET_POS_FIX_800MS "$PMTK220,800"
#define SET_POS_FIX_1S "$PMTK220,1000"
#define SET_POS_FIX_2S "$PMTK220,2000"
#define SET_POS_FIX_4S "$PMTK220,4000"
#define SET_POS_FIX_8S "$PMTK220,8000"
#define SET_POS_FIX_10S "$PMTK220,10000"
#define SET_SYNC_PPS_NMEA_OFF "$PMTK255,0"
#define SET_SYNC_PPS_NMEA_ON "$PMTK255,1"
#define SET_NMEA_BAUDRATE "$PMTK251"
#define SET_NMEA_BAUDRATE_115200 "$PMTK251,115200"
#define SET_NMEA_BAUDRATE_57600 "$PMTK251,57600"
#define SET_NMEA_BAUDRATE_38400 "$PMTK251,38400"
#define SET_NMEA_BAUDRATE_19200 "$PMTK251,19200"
#define SET_NMEA_BAUDRATE_14400 "$PMTK251,14400"
#define SET_NMEA_BAUDRATE_9600 "$PMTK251,9600"
#define SET_NMEA_BAUDRATE_4800 "$PMTK251,4800"
#define SET_REDUCTION "$PMTK314,-1"
#define SET_NMEA_OUTPUT "$PMTK314,0,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0"

// Struct definitions
typedef struct
{
	double Lon;	   // GPS Longitude
	double Lat;	   // GPS Latitude
	char Lon_area; // E or W
	char Lat_area; // N or S
	UBYTE Time_H;  // Time Hour
	UBYTE Time_M;  // Time Minute
	UBYTE Time_S;  // Time Second
	UBYTE Status;  // 1: Successful positioning, 0: Positioning failed
} GNRMC;

typedef struct
{
	double Lon;
	double Lat;
} Coordinates;

// Global variables and constants
char const Temp[16] = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F'};
static const double pi = 3.14159265358979324;
static const double a = 6378245.0;
static const double ee = 0.00669342162296594323;
static const double x_pi = 3.14159265358979324 * 3000.0 / 180.0;

static char buff_t[BUFFSIZE] = {0};
static GNRMC GPS;

// UART device and buffers
static const struct device *uart_dev;
static char latest_gnrmc[SENTENCE_SIZE];
static volatile bool new_gnrmc_available = false;

// Function prototypes
void DEV_Uart_SendByte(char data);
void DEV_Uart_SendString(char *data);
void L76X_Send_Command(char *data);
GNRMC L76X_Gat_GNRMC(void);
Coordinates L76X_Baidu_Coordinates(void);
Coordinates L76X_Google_Coordinates(void);
static double transformLat(double x, double y);
static double transformLon(double x, double y);
static Coordinates bd_encrypt(Coordinates gg);
static Coordinates transform(Coordinates gps);

// UART interrupt callback
static void uart_callback(const struct device *dev, void *user_data)
{
	ARG_UNUSED(user_data);
	static char temp_buffer[SENTENCE_SIZE];
	static int temp_index = 0;

	while (uart_irq_update(dev) && uart_irq_is_pending(dev))
	{
		if (uart_irq_rx_ready(dev))
		{
			uint8_t byte;
			if (uart_fifo_read(dev, &byte, 1) == 1)
			{
				if (byte == '\n')
				{
					temp_buffer[temp_index] = '\0';
					if (strncmp(temp_buffer, "$GNRMC", 6) == 0 || strncmp(temp_buffer, "$PNRMC", 6) == 0)
					{
						strncpy(latest_gnrmc, temp_buffer, SENTENCE_SIZE);
						new_gnrmc_available = true;
					}
					temp_index = 0;
				}
				else
				{
					if (temp_index < SENTENCE_SIZE - 1)
					{
						temp_buffer[temp_index++] = byte;
					}
					else
					{
						temp_index = 0; // Reset on overflow
					}
				}
			}
		}
	}
}

// Main function
int main(void)
{
	// Request constant latency mode when NRFX power driver is available.
#if defined(CONFIG_NRFX_POWER) && (CONFIG_NRFX_POWER == 1)
	nrfx_power_constlat_mode_request();
#endif
	LOG_INF("Starting L76X GPS Module Example");

	// Initialize UART device
	uart_dev = DEVICE_DT_GET(DT_NODELABEL(xiao_serial));
	if (!device_is_ready(uart_dev))
	{
		LOG_ERR("UART device not ready!");
		return -1;
	}
	LOG_INF("UART device initialized.");

	// Configure UART interrupt
	if (uart_irq_callback_user_data_set(uart_dev, uart_callback, NULL) != 0)
	{
		LOG_ERR("Failed to set UART callback!");
		return -1;
	}
	uart_irq_rx_enable(uart_dev);
	LOG_INF("UART interrupt enabled.");

	// Initialize GPS module
	L76X_Send_Command(SET_NMEA_OUTPUT);
	k_msleep(100);
	L76X_Send_Command(SET_POS_FIX_1S);
	k_msleep(100);

	LOG_INF("GPS module initialized. Waiting for data...");

	while (true)
	{
		// Check for new GNRMC sentence
		if (new_gnrmc_available)
		{
			strncpy(buff_t, latest_gnrmc, BUFFSIZE);
			new_gnrmc_available = false;

			// Log raw GNRMC sentence for debugging
			LOG_INF("Raw GNRMC: %s", buff_t);

			// Parse GNRMC data
			GPS = L76X_Gat_GNRMC();

			// Output GPS data
			LOG_INF("\n--- GPS Data ---");
			LOG_INF("Time (GMT+8): %02d:%02d:%02d", GPS.Time_H, GPS.Time_M, GPS.Time_S);
			if (GPS.Status == 1)
			{
				LOG_INF("Latitude (WGS-84): %.6f %c", GPS.Lat, GPS.Lat_area);
				LOG_INF("Longitude (WGS-84): %.6f %c", GPS.Lon, GPS.Lon_area);

				// Coordinate conversion
				Coordinates baidu_coords = L76X_Baidu_Coordinates();
				LOG_INF("Baidu Latitude: %.6f", baidu_coords.Lat);
				LOG_INF("Baidu Longitude: %.6f", baidu_coords.Lon);

				Coordinates google_coords = L76X_Google_Coordinates();
				LOG_INF("Google Latitude: %.6f", google_coords.Lat);
				LOG_INF("Google Longitude: %.6f", google_coords.Lon);
				LOG_INF("GPS positioning successful.");
			}
			else
			{
				LOG_INF("GPS positioning failed or no valid data.");
			}
		}
		else
		{
			LOG_INF("No new GNRMC data available.");
		}

		k_msleep(2000); // Wait 2 seconds before next reading
	}

	return 0;
}

// Send a single byte
void DEV_Uart_SendByte(char data)
{
	uart_poll_out(uart_dev, data);
}

// Send a string
void DEV_Uart_SendString(char *data)
{
	while (*data)
	{
		DEV_Uart_SendByte(*data++);
	}
}

// Send L76X command with checksum
void L76X_Send_Command(char *data)
{
	char Check = data[1], Check_char[3] = {0};
	UBYTE i = 0;
	DEV_Uart_SendByte('\r');
	DEV_Uart_SendByte('\n');

	for (i = 2; data[i] != '\0'; i++)
	{
		Check ^= data[i]; // Calculate checksum
	}
	Check_char[0] = Temp[Check / 16 % 16];
	Check_char[1] = Temp[Check % 16];
	Check_char[2] = '\0';

	DEV_Uart_SendString(data);
	DEV_Uart_SendByte('*');
	DEV_Uart_SendString(Check_char);
	DEV_Uart_SendByte('\r');
	DEV_Uart_SendByte('\n');
}

// Parse GNRMC data
GNRMC L76X_Gat_GNRMC(void)
{
	GNRMC gps = {0}; // Initialize with zeros
	UWORD add = 0, x = 0, z = 0, i = 0;
	UDOUBLE Time = 0;

	add = 0;
	while (add < BUFFSIZE)
	{
		// Look for GNRMC or PNRMC sentence
		if (buff_t[add] == '$' && buff_t[add + 1] == 'G' && (buff_t[add + 2] == 'N' || buff_t[add + 2] == 'P') &&
			buff_t[add + 3] == 'R' && buff_t[add + 4] == 'M' && buff_t[add + 5] == 'C')
		{
			x = 0;
			for (z = 0; x < 12; z++)
			{
				if (buff_t[add + z] == '\0')
				{
					break;
				}
				if (buff_t[add + z] == ',')
				{
					x++;
					if (x == 1)
					{ // Time field
						if (buff_t[add + z + 1] != ',')
						{ // Check if time field is not empty
							Time = 0;
							for (i = 0; buff_t[add + z + i + 1] != '.'; i++)
							{
								if (buff_t[add + z + i + 1] == '\0' || buff_t[add + z + i + 1] == ',')
								{
									break;
								}
								Time = (buff_t[add + z + i + 1] - '0') + Time * 10;
							}
							gps.Time_H = Time / 10000 + 8; // Adjust for GMT+8
							gps.Time_M = (Time / 100) % 100;
							gps.Time_S = Time % 100;
							if (gps.Time_H >= 24)
							{
								gps.Time_H = gps.Time_H - 24;
							}
						}
					}
					else if (x == 2)
					{ // Status field
						if (buff_t[add + z + 1] == 'A')
						{
							gps.Status = 1; // Position successful
						}
						else
						{
							gps.Status = 0; // Positioning failed
							break;			// Exit early if invalid
						}
					}
					else if (x == 3)
					{ // Latitude field
						if (buff_t[add + z + 1] != ',')
						{ // Check if latitude field is not empty
							double latitude_val = 0;
							UBYTE decimal_found = 0;
							double decimal_multiplier = 0.1;

							int k = 1;
							while (buff_t[add + z + k] != ',' && buff_t[add + z + k] != '\0')
							{
								if (buff_t[add + z + k] == '.')
								{
									decimal_found = 1;
									k++;
									continue;
								}
								if (!decimal_found)
								{
									latitude_val = latitude_val * 10 + (buff_t[add + z + k] - '0');
								}
								else
								{
									latitude_val = latitude_val + (buff_t[add + z + k] - '0') * decimal_multiplier;
									decimal_multiplier *= 0.1;
								}
								k++;
							}
							gps.Lat = latitude_val;
							gps.Lat_area = buff_t[add + z + k + 1]; // N or S
							z += k + 1;
						}
						else
						{
							gps.Status = 0; // Invalid data
							break;
						}
					}
					else if (x == 5)
					{ // Longitude field
						if (buff_t[add + z + 1] != ',')
						{ // Check if longitude field is not empty
							double longitude_val = 0;
							UBYTE decimal_found = 0;
							double decimal_multiplier = 0.1;

							int k = 1;
							while (buff_t[add + z + k] != ',' && buff_t[add + z + k] != '\0')
							{
								if (buff_t[add + z + k] == '.')
								{
									decimal_found = 1;
									k++;
									continue;
								}
								if (!decimal_found)
								{
									longitude_val = longitude_val * 10 + (buff_t[add + z + k] - '0');
								}
								else
								{
									longitude_val = longitude_val + (buff_t[add + z + k] - '0') * decimal_multiplier;
									decimal_multiplier *= 0.1;
								}
								k++;
							}
							gps.Lon = longitude_val;
							gps.Lon_area = buff_t[add + z + k + 1]; // E or W
							z += k + 1;
							break;
						}
						else
						{
							gps.Status = 0; // Invalid data
							break;
						}
					}
				}
			}
			break;
		}
		add++;
	}
	return gps;
}

// Convert to Baidu coordinates (BD-09)
Coordinates L76X_Baidu_Coordinates(void)
{
	Coordinates wgs84_coords;
	wgs84_coords.Lat = GPS.Lat;
	wgs84_coords.Lon = GPS.Lon;

	Coordinates gcj02_coords = transform(wgs84_coords);
	Coordinates bd09_coords = bd_encrypt(gcj02_coords);
	return bd09_coords;
}

// Convert to Google coordinates (GCJ-02)
Coordinates L76X_Google_Coordinates(void)
{
	Coordinates wgs84_coords;
	wgs84_coords.Lat = GPS.Lat;
	wgs84_coords.Lon = GPS.Lon;

	Coordinates gcj02_coords = transform(wgs84_coords);
	return gcj02_coords;
}

// Coordinate transformation helper functions
static double transformLat(double x, double y)
{
	double ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * sqrt(fabs(x));
	ret += (20.0 * sin(6.0 * x * pi) + 20.0 * sin(2.0 * x * pi)) * 2.0 / 3.0;
	ret += (20.0 * sin(y * pi) + 40.0 * sin(y / 3.0 * pi)) * 2.0 / 3.0;
	ret += (160.0 * sin(y / 12.0 * pi) + 320 * sin(y * pi / 30.0)) * 2.0 / 3.0;
	return ret;
}

static double transformLon(double x, double y)
{
	double ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * sqrt(fabs(x));
	ret += (20.0 * sin(6.0 * x * pi) + 20.0 * sin(2.0 * x * pi)) * 2.0 / 3.0;
	ret += (20.0 * sin(x * pi) + 40.0 * sin(x / 3.0 * pi)) * 2.0 / 3.0;
	ret += (150.0 * sin(x / 12.0 * pi) + 300.0 * sin(x / 30.0 * pi)) * 2.0 / 3.0;
	return ret;
}

static Coordinates bd_encrypt(Coordinates gg)
{
	Coordinates bd;
	double x = gg.Lon, y = gg.Lat;
	double z = sqrt(x * x + y * y) + 0.00002 * sin(y * x_pi);
	double theta = atan2(y, x) + 0.000003 * cos(x * x_pi);
	bd.Lon = z * cos(theta) + 0.0065;
	bd.Lat = z * sin(theta) + 0.006;
	return bd;
}

static Coordinates transform(Coordinates gps)
{
	Coordinates gg;
	double dLat = transformLat(gps.Lon - 105.0, gps.Lat - 35.0);
	double dLon = transformLon(gps.Lon - 105.0, gps.Lat - 35.0);
	double radLat = gps.Lat / 180.0 * pi;
	double magic = sin(radLat);
	magic = 1 - ee * magic * magic;
	double sqrtMagic = sqrt(magic);
	dLat = (dLat * 180.0) / ((a * (1 - ee)) / (magic * sqrtMagic) * pi);
	dLon = (dLon * 180.0) / (a / sqrtMagic * cos(radLat) * pi);
	gg.Lat = gps.Lat + dLat;
	gg.Lon = gps.Lon + dLon;
	return gg;
}
