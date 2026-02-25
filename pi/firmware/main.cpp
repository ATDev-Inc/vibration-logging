#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <unistd.h>
#include <gpiod.h>

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>

#include "lsm6dsox_reg.h"

// Hardware Configuration for Pi 5
#define GPIO_CHIP_PATH "/dev/gpiochip0"
#define INT1_GPIO_OFFSET 24
#define SPI_DEVICE "/dev/spidev0.0"
#define SPI_SPEED_HZ 20000000 // Increased to 20MHz

std::atomic<bool> keep_running(true);

// Cleanup callback for SIGINT (Ctrl+C) and SIGTERM (Shutdown)
void signal_handler(int signum)
{
  const char msg[] = "\n[Signal] Shutdown event detected. Finalizing logs...\n";
  (void)write(STDOUT_FILENO, msg, sizeof(msg) - 1);
  keep_running = false;
}

// SPI Platform Write: MSB of address is 0
int32_t platform_write(void* handle, uint8_t reg, const uint8_t* bufp,
                       uint16_t len)
{
  int fd = *(int*)handle;
  uint8_t tx_buf[len + 1];
  tx_buf[0] = reg & 0x7F; 
  memcpy(&tx_buf[1], bufp, len);

  struct spi_ioc_transfer tr = {0};
  tr.tx_buf = (unsigned long)tx_buf;
  tr.len = (uint32_t)(len + 1);
  tr.speed_hz = SPI_SPEED_HZ;
  tr.bits_per_word = 8;

  if (ioctl(fd, SPI_IOC_MESSAGE(1), &tr) < 1) return -1;
  return 0;
}

// SPI Platform Read: MSB of address is 1
int32_t platform_read(void* handle, uint8_t reg, uint8_t* bufp, uint16_t len)
{
  int fd = *(int*)handle;
  uint8_t tx_buf[len + 1] = {0};
  uint8_t rx_buf[len + 1] = {0};
  tx_buf[0] = reg | 0x80;

  struct spi_ioc_transfer tr = {0};
  tr.tx_buf = (unsigned long)tx_buf;
  tr.rx_buf = (unsigned long)rx_buf;
  tr.len = (uint32_t)(len + 1);
  tr.speed_hz = SPI_SPEED_HZ;
  tr.bits_per_word = 8;

  if (ioctl(fd, SPI_IOC_MESSAGE(1), &tr) < 1) return -1;
  memcpy(bufp, &rx_buf[1], len);
  return 0;
}

void platform_delay(uint32_t ms) { usleep(ms * 1000); }

void setup_vibration_logging(stmdev_ctx_t* ctx)
{
  lsm6dsox_reset_set(ctx, PROPERTY_ENABLE);
  platform_delay(50);
  lsm6dsox_block_data_update_set(ctx, PROPERTY_ENABLE);
  lsm6dsox_timestamp_set(ctx, PROPERTY_ENABLE);

  // Set to 6.66 kHz (Maximum ODR)
  lsm6dsox_xl_data_rate_set(ctx, LSM6DSOX_XL_ODR_6667Hz);
  lsm6dsox_xl_full_scale_set(ctx, LSM6DSOX_16g);
  lsm6dsox_gy_data_rate_set(ctx, LSM6DSOX_GY_ODR_6667Hz);
  lsm6dsox_gy_full_scale_set(ctx, LSM6DSOX_2000dps);

  lsm6dsox_fifo_xl_batch_set(ctx, LSM6DSOX_XL_BATCHED_AT_6667Hz);
  lsm6dsox_fifo_gy_batch_set(ctx, LSM6DSOX_GY_BATCHED_AT_6667Hz);
  lsm6dsox_fifo_timestamp_decimation_set(ctx, LSM6DSOX_DEC_1);

  // Increased Watermark to 256 words to provide ~19ms of rotation headroom
  lsm6dsox_fifo_watermark_set(ctx, 256);

  // Enable hardware Low-Pass Filters to stabilize the 6.66kHz signal
  lsm6dsox_gy_lp1_bandwidth_set(ctx, LSM6DSOX_ULTRA_LIGHT);
  lsm6dsox_xl_hp_path_on_out_set(ctx, LSM6DSOX_LP_ODR_DIV_10);
  lsm6dsox_xl_filter_lp2_set(ctx, PROPERTY_ENABLE);

  lsm6dsox_pin_int1_route_t int1_route;
  memset(&int1_route, 0, sizeof(int1_route));
  int1_route.fifo_th = PROPERTY_ENABLE;
  lsm6dsox_pin_int1_route_set(ctx, int1_route);

  lsm6dsox_fifo_mode_set(ctx, LSM6DSOX_STREAM_MODE);

  // Warmup Period
  platform_delay(100);
  uint16_t num_samples = 0;
  uint8_t dummy[7];
  lsm6dsox_fifo_data_level_get(ctx, &num_samples);
  for (int i = 0; i < num_samples; i++) {
    lsm6dsox_read_reg(ctx, LSM6DSOX_FIFO_DATA_OUT_TAG, dummy, 7);
  }
}

void rotate_log(std::ofstream& outfile, std::string& ram_path)
{
  if (outfile.is_open())
  {
    outfile.flush();
    outfile.close();
    std::string ready_path = ram_path + "." + std::to_string(std::time(0)) + ".ready";
    std::rename(ram_path.c_str(), ready_path.c_str());
  }
}

void data_loop(stmdev_ctx_t* ctx, int rotation_seconds)
{
  uint16_t num_samples = 0;
  uint8_t fifo_word[7];
  std::string ram_path = "/dev/shm/vibration_current.bin";
  std::ofstream outfile;

  struct gpiod_chip* chip = gpiod_chip_open(GPIO_CHIP_PATH);
  if (!chip) { std::cerr << "Failed to open GPIO chip." << std::endl; return; }

  struct gpiod_line_settings* settings = gpiod_line_settings_new();
  gpiod_line_settings_set_direction(settings, GPIOD_LINE_DIRECTION_INPUT);
  gpiod_line_settings_set_edge_detection(settings, GPIOD_LINE_EDGE_RISING);

  struct gpiod_line_config* line_cfg = gpiod_line_config_new();
  unsigned int offset = INT1_GPIO_OFFSET;
  gpiod_line_config_add_line_settings(line_cfg, &offset, 1, settings);

  struct gpiod_line_request* request = gpiod_chip_request_lines(chip, NULL, line_cfg);
  gpiod_line_settings_free(settings);
  gpiod_line_config_free(line_cfg);

  if (!request) { std::cerr << "Failed to request GPIO line." << std::endl; gpiod_chip_close(chip); return; }
  struct gpiod_edge_event_buffer* event_buffer = gpiod_edge_event_buffer_new(16);

    auto next_rotation = std::chrono::steady_clock::now() + std::chrono::seconds(rotation_seconds);
    outfile.open(ram_path, std::ios::binary | std::ios::out);
  
    // Final flush to ensure INT1 starts LOW and we catch the very first edge
    lsm6dsox_fifo_data_level_get(ctx, &num_samples);
    while (num_samples > 0) {
        for (int i = 0; i < num_samples; i++) {
            lsm6dsox_read_reg(ctx, LSM6DSOX_FIFO_DATA_OUT_TAG, fifo_word, 7);
        }
        lsm6dsox_fifo_data_level_get(ctx, &num_samples);
    }
  
    std::cout << "Production Logger Active (6.66kHz SPI @ 20MHz)." << std::endl;
  
    struct timespec timeout = { 0, 100000000 }; // 100ms timeout
  
    while (keep_running)
    {
      int wait_ret = gpiod_line_request_wait_edge_events(request, 100000000);
      if (wait_ret > 0) {
          gpiod_line_request_read_edge_events(request, event_buffer, 16);
      }
  
      auto now = std::chrono::steady_clock::now();
      if (now >= next_rotation) {
          rotate_log(outfile, ram_path);
          outfile.open(ram_path, std::ios::binary | std::ios::out);
          next_rotation = now + std::chrono::seconds(rotation_seconds);
      }
  
      lsm6dsox_fifo_data_level_get(ctx, &num_samples);
      while (num_samples > 0) {
          for (int i = 0; i < num_samples; i++) {
              if (lsm6dsox_read_reg(ctx, LSM6DSOX_FIFO_DATA_OUT_TAG, fifo_word, 7) == 0) {
                  outfile.write(reinterpret_cast<char*>(fifo_word), 7);
              }
          }
          lsm6dsox_fifo_data_level_get(ctx, &num_samples);
      }
    }
  
    rotate_log(outfile, ram_path);
    lsm6dsox_fifo_mode_set(ctx, LSM6DSOX_BYPASS_MODE);
  lsm6dsox_xl_data_rate_set(ctx, LSM6DSOX_XL_ODR_OFF);
  lsm6dsox_gy_data_rate_set(ctx, LSM6DSOX_GY_ODR_OFF);

  gpiod_edge_event_buffer_free(event_buffer);
  gpiod_line_request_release(request);
  gpiod_chip_close(chip);
}

int main(int argc, char** argv)
{
  // Lock memory to prevent latency spikes from page faults
  if (mlockall(MCL_CURRENT | MCL_FUTURE) == -1) {
      perror("mlockall");
  }

  signal(SIGINT, signal_handler);
  signal(SIGTERM, signal_handler);

  int fd = open(SPI_DEVICE, O_RDWR);
  if (fd < 0) {
      std::cerr << "Failed to open SPI device" << std::endl;
      return 1;
  }

  uint8_t mode = SPI_MODE_3, bits = 8;
  uint32_t speed = SPI_SPEED_HZ;
  ioctl(fd, SPI_IOC_WR_MODE, &mode);
  ioctl(fd, SPI_IOC_WR_BITS_PER_WORD, &bits);
  ioctl(fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed);

  stmdev_ctx_t dev_ctx;
  dev_ctx.write_reg = platform_write;
  dev_ctx.read_reg = platform_read;
  dev_ctx.mdelay = platform_delay;
  dev_ctx.handle = &fd;
  dev_ctx.priv_data = NULL;

  uint8_t whoamI;
  lsm6dsox_device_id_get(&dev_ctx, &whoamI);
  if (whoamI != LSM6DSOX_ID) {
    std::cerr << "Device ID mismatch (SPI): " << (int)whoamI << std::endl;
  }

  setup_vibration_logging(&dev_ctx);
  data_loop(&dev_ctx, 60);

  close(fd);
  return 0;
}
