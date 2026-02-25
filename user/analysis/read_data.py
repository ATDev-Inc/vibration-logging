import struct
import sys
import csv
import math
import os
import glob

# Constants from lsm6dsox_reg.h
LSM6DSOX_GYRO_NC_TAG = 1
LSM6DSOX_XL_NC_TAG = 2
LSM6DSOX_TIMESTAMP_TAG = 4

# Conversion factors
ACCEL_FS_16G_SENSITIVITY = 0.488  # mg/LSB
GYRO_FS_2000DPS_SENSITIVITY = 70.0  # mdps/LSB
TIMESTAMP_RES_US = 25.0  # 25us per LSB

def write_row(writer, ts, entry):
    ts_s = (ts * TIMESTAMP_RES_US / 1_000_000.0)
    total_g = math.sqrt(entry['ax']**2 + entry['ay']**2 + entry['az']**2)
    writer.writerow([
        f"{ts_s:.6f}",
        f"{entry['ax']:.4f}", f"{entry['ay']:.4f}", f"{entry['az']:.4f}",
        f"{total_g:.4f}",
        f"{entry['gx']:.3f}", f"{entry['gy']:.3f}", f"{entry['gz']:.3f}",
        ts
    ])

def process_files(bin_files, output_csv):
    print(f"Combining {len(bin_files)} files into {output_csv}...")
    
    # Persistent store to catch alignment across file boundaries
    data_store = {}
    last_ts = 0
    rows_written = 0

    try:
        with open(output_csv, "w", newline='') as f_csv:
            writer = csv.writer(f_csv)
            writer.writerow(["time_s", "accel_x_g", "accel_y_g", "accel_z_g", "total_g", "gyro_x_dps", "gyro_y_dps", "gyro_z_dps", "raw_ts_ticks"])
            
            # Sort files chronologically
            for bin_filename in sorted(bin_files):
                print(f"  Reading {os.path.basename(bin_filename)}...")
                with open(bin_filename, "rb") as f_bin:
                    while True:
                        record = f_bin.read(7)
                        if len(record) < 7: break
                        
                        tag = (record[0] >> 3) & 0x1F
                        payload = record[1:]
                        
                        if tag == LSM6DSOX_TIMESTAMP_TAG:
                            last_ts = struct.unpack("<I", payload[:4])[0]
                            if last_ts not in data_store:
                                data_store[last_ts] = {'ax': None, 'ay': None, 'az': None, 'gx': None, 'gy': None, 'gz': None}

                        elif tag == LSM6DSOX_XL_NC_TAG:
                            if last_ts not in data_store:
                                data_store[last_ts] = {'ax': None, 'ay': None, 'az': None, 'gx': None, 'gy': None, 'gz': None}
                            x, y, z = struct.unpack("<hhh", payload)
                            data_store[last_ts]['ax'] = (x * ACCEL_FS_2G_SENSITIVITY) / 1000.0
                            data_store[last_ts]['ay'] = (y * ACCEL_FS_2G_SENSITIVITY) / 1000.0
                            data_store[last_ts]['az'] = (z * ACCEL_FS_2G_SENSITIVITY) / 1000.0

                        elif tag == LSM6DSOX_GYRO_NC_TAG:
                            if last_ts not in data_store:
                                data_store[last_ts] = {'ax': None, 'ay': None, 'az': None, 'gx': None, 'gy': None, 'gz': None}
                            x, y, z = struct.unpack("<hhh", payload)
                            data_store[last_ts]['gx'] = (x * GYRO_FS_2000DPS_SENSITIVITY) / 1000.0
                            data_store[last_ts]['gy'] = (y * GYRO_FS_2000DPS_SENSITIVITY) / 1000.0
                            data_store[last_ts]['gz'] = (z * GYRO_FS_2000DPS_SENSITIVITY) / 1000.0

                        # Flush completed rows
                        completed_ts = []
                        # We use a sorted list of keys to find aligned samples
                        ts_keys = sorted(data_store.keys())
                        for ts in ts_keys:
                            entry = data_store[ts]
                            if entry['ax'] is not None and entry['gx'] is not None:
                                write_row(writer, ts, entry)
                                rows_written += 1
                                completed_ts.append(ts)
                            elif ts < last_ts - 500: # Cleanup stale/incomplete entries
                                completed_ts.append(ts)
                        
                        for ts in completed_ts:
                            del data_store[ts]
            
            # Final flush of anything left
            for ts in sorted(data_store.keys()):
                entry = data_store[ts]
                if entry['ax'] is not None and entry['gx'] is not None:
                    write_row(writer, ts, entry)
                    rows_written += 1

        print(f"Finished. Total samples written: {rows_written}")

    except Exception as e:
        print(f"Error during processing: {e}")

if __name__ == "__main__":
    path = "logs"
    if len(sys.argv) > 1:
        path = sys.argv[1]
    
    if os.path.isdir(path):
        files = glob.glob(os.path.join(path, "*.ready"))
        if not files:
            files = glob.glob(os.path.join(path, "*.bin"))
    else:
        files = [path]

    if not files:
        print(f"No log files found in {path}")
    else:
        process_files(files, "combined_imu_data.csv")
