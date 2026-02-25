#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Configuration
BUILD_DIR="build"
EXECUTABLE_NAME="vibration_logger"

echo "--- Starting Build Process for $EXECUTABLE_NAME ---"

# 1. Check for required dependencies (libgpiod and cmake)
if ! pkg-config --exists libgpiod; then
    echo "Error: libgpiod-dev is not installed."
    echo "Please run: sudo apt-get install libgpiod-dev cmake"
    exit 1
fi

# 2. Handle the Build Directory
if [ -d "$BUILD_DIR" ]; then
    echo "Cleaning existing build directory..."
    rm -rf "$BUILD_DIR"
fi
mkdir "$BUILD_DIR"
cd "$BUILD_DIR"

# 3. Run CMake
echo "Running CMake..."
# We use -DCMAKE_EXPORT_COMPILE_COMMANDS=ON to help IDEs like VS Code with IntelliSense
cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON ..

# 4. Compile the project
# Using -j$(nproc) tells the Pi 5 to use all its CPU cores for a faster build
echo "Compiling with $(nproc) cores..."
make -j$(nproc)

echo "--- Build Successful! ---"
echo "You can now run the logger using: ./$BUILD_DIR/$EXECUTABLE_NAME"