# 🚀 High-Frequency Vibration Logging System (Pi 5)

Professional-grade data acquisition system designed to capture 6-axis IMU data from an LSM6DSOX at **6.66 kHz**. Optimized for Raspberry Pi 5.

---

## 📂 Project Structure

### 🍓 Pi Code (`/pi`)
Everything that runs on the Raspberry Pi 5.
* `pi/firmware/`: Low-level C++ logging engine (SPI @ 20MHz).
* `pi/scripts/`: System management scripts (Janitor, LED blinker, EMI reduction).
* `pi/install.sh`: Automated installer for the Pi.
* `pi/vibration_logger.service`: Systemd service definition.

### 💻 User/Analysis Code (`/user`)
Everything that runs on your local computer.
* `user/pull_data_friendly.py`: **Main tool for end-users.** Auto-connects to Pi Wi-Fi and downloads logs.
* `user/analysis/`: Python utilities for data processing and statistical analysis.

---

## 💻 For End Users: Downloading Data

### 1. Requirements
* Python 3.10+ installed on your computer.
* Install requirements (one time):
  ```bash
  pip install paramiko rich
  ```

### 2. Run the Download Tool
Simply run the friendly script from the `user/` folder:
```bash
python user/pull_data_friendly.py
```
**Features:**
* **Auto-Wi-Fi:** Connects your PC to the `AT-DEV-LOGGER` network automatically.
* **Service Sync:** Stops collection during transfer and restarts it after.
* **Verification:** SHA256 verification of every file to ensure zero data loss.

---

## 🛠 For Developers: Installation on Pi

### 1. Clone (with submodules)
The firmware depends on the ST `lsm6dsox-pid` driver, included as a git submodule at `pi/firmware/drivers/lsm6dsox-pid`. Clone with submodules so the build can find it:
```bash
git clone --recurse-submodules git@github.com:ATDev-Inc/vibration-logging.git
```
If you already cloned without it:
```bash
git submodule update --init --recursive
```

### 2. Build & Install
Run the installer on the Pi:
```bash
cd pi
./install.sh
```

### 3. Analysis
```bash
# Combine logs
python3 user/analysis/read_data.py logs/

# Analyze results
uv run --with pandas --with matplotlib --with numpy user/analysis/analyze_data.py combined_imu_data.csv
```

---

## ⚙️ Hardware (Pi 5)
* **Sensor:** LSM6DSOX (6-Axis IMU) @ **6.66 kHz**.
* **Wi-Fi SSID:** `AT-DEV-LOGGER` (Password: `supersafepassword`)
