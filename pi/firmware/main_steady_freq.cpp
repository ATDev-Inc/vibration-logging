#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <chrono>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>

#include "lsm6dsox_reg.h"

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

// Platform Delay
void platform_delay(uint32_t ms) { usleep(ms * 1000); }

void setup_vibration_logging(stmdev_ctx_t* ctx)
{
  lsm6dsox_reset_set(ctx, PROPERTY_ENABLE);
  platform_delay(50);
  lsm6dsox_block_data_update_set(ctx, PROPERTY_ENABLE);
  lsm6dsox_timestamp_set(ctx, PROPERTY_ENABLE);

  // Set to 208 Hz for testing
  lsm6dsox_xl_data_rate_set(ctx, LSM6DSOX_XL_ODR_833Hz);
  lsm6dsox_xl_full_scale_set(ctx, LSM6DSOX_16g);
  lsm6dsox_gy_data_rate_set(ctx, LSM6DSOX_GY_ODR_833Hz);
  lsm6dsox_gy_full_scale_set(ctx, LSM6DSOX_2000dps);

  lsm6dsox_fifo_xl_batch_set(ctx, LSM6DSOX_XL_BATCHED_AT_833Hz);
  lsm6dsox_fifo_gy_batch_set(ctx, LSM6DSOX_GY_BATCHED_AT_833Hz);
  lsm6dsox_fifo_timestamp_decimation_set(ctx, LSM6DSOX_DEC_1);
  lsm6dsox_fifo_mode_set(ctx, LSM6DSOX_STREAM_MODE);
}

void rotate_log(std::ofstream& outfile, std::string& ram_path)
{
  if (outfile.is_open())
  {
    outfile.close();
    // Rename current to a "ready" status for the janitor
    std::string ready_path =
        ram_path + "." + std::to_string(std::time(0)) + ".ready";
    std::rename(ram_path.c_str(), ready_path.c_str());
  }
  outfile.open(ram_path, std::ios::binary | std::ios::out);
}

void data_loop(stmdev_ctx_t* ctx, const std::string& sd_dir,
               int rotation_seconds)
{
  uint16_t num_samples = 0;
  uint8_t fifo_word[7];
  std::string ram_path = "/dev/shm/vibration_current.bin";
  std::ofstream outfile;

  mkdir(sd_dir.c_str(), 0777);
  auto next_rotation =
      std::chrono::steady_clock::now() + std::chrono::seconds(rotation_seconds);
  rotate_log(outfile, ram_path);

  std::cout << "Logging... (833Hz, 400kHz I2C)" << std::endl;

  long total_samples = 0;
  while (true)
  {
    auto now = std::chrono::steady_clock::now();
    if (now >= next_rotation)
    {
      rotate_log(outfile, ram_path);
      next_rotation = now + std::chrono::seconds(rotation_seconds);
      std::cout << "Samples in last segment: " << total_samples << std::endl;
      total_samples = 0;
    }

    lsm6dsox_fifo_data_level_get(ctx, &num_samples);
    if (num_samples > 0)
    {
      for (int i = 0; i < num_samples; i++)
      {
        if (lsm6dsox_read_reg(ctx, LSM6DSOX_FIFO_DATA_OUT_TAG, fifo_word, 7) ==
            0)
        {
          outfile.write(reinterpret_cast<char*>(fifo_word), 7);
          total_samples++;
        }
      }
    }
    else
    {
      usleep(1000);
    }
  }
}

int main(int argc, char** argv)
{
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
  data_loop(&dev_ctx, "logs", 10);  // 10s segments

  close(fd);
  return 0;
}
