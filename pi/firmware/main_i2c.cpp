#include <fcntl.h>
#include <gpiod.h>
#include <linux/i2c-dev.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>

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

// Note: On Pi 5, the 40-pin header is usually /dev/gpiochip4
#define GPIO_CHIP_PATH "/dev/gpiochip0"
#define INT1_GPIO_OFFSET 17

std::atomic<bool> keep_running(true);

void signal_handler(int signum)
{
  const char msg[] = "\n[Signal] Shutting down cleanly...\n";
  (void)write(STDOUT_FILENO, msg, sizeof(msg) - 1);
  keep_running = false;
}

// I2C Platform Write
int32_t platform_write(void* handle, uint8_t reg, const uint8_t* bufp,
                       uint16_t len)
{
  int fd = *(int*)handle;
  uint8_t tx_buf[len + 1];
  tx_buf[0] = reg;
  memcpy(&tx_buf[1], bufp, len);

  if (write(fd, tx_buf, len + 1) != (len + 1)) return -1;
  return 0;
}

// I2C Platform Read
int32_t platform_read(void* handle, uint8_t reg, uint8_t* bufp, uint16_t len)
{
  int fd = *(int*)handle;
  if (write(fd, &reg, 1) != 1) return -1;
  if (read(fd, bufp, len) != len) return -1;
  return 0;
}

void platform_delay(uint32_t ms) { usleep(ms * 1000); }

void setup_vibration_logging(stmdev_ctx_t* ctx)
{
  lsm6dsox_reset_set(ctx, PROPERTY_ENABLE);
  platform_delay(50);
  lsm6dsox_block_data_update_set(ctx, PROPERTY_ENABLE);
  lsm6dsox_timestamp_set(ctx, PROPERTY_ENABLE);

  // Set to 833 Hz
  lsm6dsox_xl_data_rate_set(ctx, LSM6DSOX_XL_ODR_833Hz);
  lsm6dsox_xl_full_scale_set(ctx, LSM6DSOX_16g);
  lsm6dsox_gy_data_rate_set(ctx, LSM6DSOX_GY_ODR_833Hz);
  lsm6dsox_gy_full_scale_set(ctx, LSM6DSOX_2000dps);

  lsm6dsox_fifo_xl_batch_set(ctx, LSM6DSOX_XL_BATCHED_AT_833Hz);
  lsm6dsox_fifo_gy_batch_set(ctx, LSM6DSOX_GY_BATCHED_AT_833Hz);
  lsm6dsox_fifo_timestamp_decimation_set(ctx, LSM6DSOX_DEC_1);

  lsm6dsox_fifo_watermark_set(ctx, 128);

  lsm6dsox_pin_int1_route_t int1_route;
  memset(&int1_route, 0, sizeof(int1_route));
  int1_route.fifo_th = PROPERTY_ENABLE;
  lsm6dsox_pin_int1_route_set(ctx, int1_route);

  lsm6dsox_fifo_mode_set(ctx, LSM6DSOX_STREAM_MODE);
}

void rotate_log(std::ofstream& outfile, std::string& ram_path)
{
  if (outfile.is_open())
  {
    outfile.flush();
    outfile.close();
    std::string ready_path =
        ram_path + "." + std::to_string(std::time(0)) + ".ready";
    std::rename(ram_path.c_str(), ready_path.c_str());
  }
}

void data_loop(stmdev_ctx_t* ctx, int rotation_seconds)
{
  uint16_t num_samples = 0;
  uint8_t fifo_word[7];
  std::string ram_path = "/dev/shm/vibration_current.bin";
  std::ofstream outfile;

  // --- Libgpiod v2.x Setup ---
  struct gpiod_chip* chip = gpiod_chip_open(GPIO_CHIP_PATH);
  if (!chip)
  {
    std::cerr << "Failed to open " << GPIO_CHIP_PATH << std::endl;
    return;
  }

  struct gpiod_line_settings* settings = gpiod_line_settings_new();
  gpiod_line_settings_set_direction(settings, GPIOD_LINE_DIRECTION_INPUT);
  gpiod_line_settings_set_edge_detection(settings, GPIOD_LINE_EDGE_RISING);

  struct gpiod_line_config* line_cfg = gpiod_line_config_new();
  unsigned int offset = INT1_GPIO_OFFSET;
  gpiod_line_config_add_line_settings(line_cfg, &offset, 1, settings);

  struct gpiod_line_request* request =
      gpiod_chip_request_lines(chip, NULL, line_cfg);

  gpiod_line_settings_free(settings);
  gpiod_line_config_free(line_cfg);

  if (!request)
  {
    std::cerr << "Failed to request GPIO line" << std::endl;
    gpiod_chip_close(chip);
    return;
  }

  struct gpiod_edge_event_buffer* event_buffer =
      gpiod_edge_event_buffer_new(16);
  if (!event_buffer)
  {
    std::cerr << "Failed to allocate event buffer" << std::endl;
    gpiod_line_request_release(request);
    gpiod_chip_close(chip);
    return;
  }

  auto next_rotation =
      std::chrono::steady_clock::now() + std::chrono::seconds(rotation_seconds);
  outfile.open(ram_path, std::ios::binary | std::ios::out);

  std::cout << "Logging with libgpiod v2.x (Chip " << GPIO_CHIP_PATH
            << ", Line " << INT1_GPIO_OFFSET << ")..." << std::endl;

  while (keep_running)
  {
    // Wait for edge events (500ms timeout)
    int wait_ret = gpiod_line_request_wait_edge_events(request, 500000000);

    if (wait_ret > 0)
    {
      // Read events from the request into the buffer
      gpiod_line_request_read_edge_events(request, event_buffer, 16);
    }

    auto now = std::chrono::steady_clock::now();
    if (now >= next_rotation)
    {
      rotate_log(outfile, ram_path);
      outfile.open(ram_path, std::ios::binary | std::ios::out);
      next_rotation = now + std::chrono::seconds(rotation_seconds);
    }

    // Drain FIFO
    lsm6dsox_fifo_data_level_get(ctx, &num_samples);
    while (num_samples > 0)
    {
      for (int i = 0; i < num_samples; i++)
      {
        if (lsm6dsox_read_reg(ctx, LSM6DSOX_FIFO_DATA_OUT_TAG, fifo_word, 7) ==
            0)
        {
          outfile.write(reinterpret_cast<char*>(fifo_word), 7);
        }
      }
      lsm6dsox_fifo_data_level_get(ctx, &num_samples);
    }
  }

  // Cleanup
  rotate_log(outfile, ram_path);
  lsm6dsox_fifo_mode_set(ctx, LSM6DSOX_BYPASS_MODE);
  lsm6dsox_xl_data_rate_set(ctx, LSM6DSOX_XL_ODR_OFF);
  lsm6dsox_gy_data_rate_set(ctx, LSM6DSOX_GY_ODR_OFF);

  gpiod_edge_event_buffer_free(event_buffer);
  gpiod_line_request_release(request);
  gpiod_chip_close(chip);
  std::cout << "Cleanup finished." << std::endl;
}

int main(int argc, char** argv)
{
  signal(SIGINT, signal_handler);

  const char* i2c_device = "/dev/i2c-1";
  int fd = open(i2c_device, O_RDWR);
  if (fd < 0) return 1;

  if (ioctl(fd, I2C_SLAVE, LSM6DSOX_I2C_ADD_L >> 1) < 0)
  {
    close(fd);
    return 1;
  }

  stmdev_ctx_t dev_ctx;
  dev_ctx.write_reg = platform_write;
  dev_ctx.read_reg = platform_read;
  dev_ctx.handle = &fd;

  uint8_t whoamI;
  lsm6dsox_device_id_get(&dev_ctx, &whoamI);
  if (whoamI != LSM6DSOX_ID)
  {
    std::cerr << "Device ID mismatch: " << (int)whoamI << std::endl;
    close(fd);
    return 1;
  }

  setup_vibration_logging(&dev_ctx);
  data_loop(&dev_ctx, 5);

  close(fd);
  return 0;
}
