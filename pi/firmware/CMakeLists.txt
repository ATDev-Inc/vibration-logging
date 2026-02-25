cmake_minimum_required(VERSION 3.10)
project(VibrationLogger)

set(CMAKE_CXX_STANDARD 17)

# 1. Define paths for the ST Driver
set(ST_DRIVER_DIR ${CMAKE_CURRENT_SOURCE_DIR}/drivers/lsm6dsox-pid)

# 2. Find system dependencies for Pi 5
find_package(PkgConfig REQUIRED)
pkg_check_modules(GPIOD REQUIRED libgpiod)

# 3. Include directories (Your app + the ST driver)
include_directories(
    .
    ${ST_DRIVER_DIR}
    ${GPIOD_INCLUDE_DIRS}
)

# 4. Create the executable
add_executable(vibration_logger
    main.cpp
    ${ST_DRIVER_DIR}/lsm6dsox_reg.c
)

# 5. Link libraries
target_link_libraries(vibration_logger ${GPIOD_LIBRARIES})