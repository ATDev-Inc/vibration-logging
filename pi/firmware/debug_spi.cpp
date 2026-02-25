#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <iostream>
#include <iomanip>
#include <cstring>
#include <cstdint>

int main() {
    // Open SPI device
    int fd = open("/dev/spidev0.0", O_RDWR);
    if (fd < 0) {
        std::cerr << "Error: Could not open /dev/spidev0.0. Is SPI enabled in raspi-config?" << std::endl;
        return 1;
    }

    // Set SPI Mode 3
    uint8_t mode = 3;
    if (ioctl(fd, SPI_IOC_WR_MODE, &mode) < 0) {
        perror("Set Mode");
        return 1;
    }

    // Set slow speed for debugging
    uint32_t speed = 1000000; // 1MHz
    if (ioctl(fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed) < 0) {
        perror("Set Speed");
        return 1;
    }

    // Attempt to read WHO_AM_I (Register 0x0F)
    uint8_t tx[2] = { 0x8F, 0x00 };
    uint8_t rx[2] = { 0x00, 0x00 };

    struct spi_ioc_transfer tr = {0};
    tr.tx_buf = (unsigned long)tx;
    tr.rx_buf = (unsigned long)rx;
    tr.len = 2;
    tr.speed_hz = speed;
    tr.bits_per_word = 8;

    std::cout << "--- SPI Debug Diagnostic ---" << std::endl;
    if (ioctl(fd, SPI_IOC_MESSAGE(1), &tr) < 1) {
        perror("SPI Transfer");
    } else {
        std::cout << "Sent:     0x" << std::hex << (int)tx[0] << " 0x" << (int)tx[1] << std::endl;
        std::cout << "Received: 0x" << std::hex << (int)rx[0] << " 0x" << (int)rx[1] << std::endl;
        
        if (rx[1] == 0x6C) {
            std::cout << "\nRESULT: SUCCESS! LSM6DSOX found (0x6C)." << std::endl;
        } else if (rx[1] == 0x00 || rx[1] == 0xFF) {
            std::cout << "\nRESULT: BUS SILENT (0x00/0xFF). Check wiring (especially MISO/SDO)." << std::endl;
        } else {
            std::cout << "\nRESULT: WRONG ID (Expected 0x6C). Check SPI Mode or Power." << std::endl;
        }
    }

    close(fd);
    return 0;
}
