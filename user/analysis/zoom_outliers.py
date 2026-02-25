import pandas as pd
import sys
import numpy as np

def zoom_outliers(csv_file):
    print(f"--- Zooming Outliers in {csv_file} ---")
    try:
        df = pd.read_csv(csv_file)
    except Exception as e:
        print(f"Error: {e}")
        return

    # 1. Look for Sensor Outliers
    sensor_cols = ['accel_x_g', 'accel_y_g', 'accel_z_g', 'gyro_x_dps', 'gyro_y_dps', 'gyro_z_dps']
    for col in sensor_cols:
        if col not in df.columns: continue
        
        diff = df[col].diff().abs()
        max_idx = diff.idxmax()
        
        if pd.isna(max_idx) or max_idx == 0: continue
        
        # Determine Threshold (6 sigma)
        threshold = diff.mean() + 6 * diff.std()
        
        if diff.iloc[max_idx] > threshold:
            print(f"\n[Outlier in {col}] Max Δ = {diff.iloc[max_idx]:.4f} (Threshold: {threshold:.4f})")
            start = max(0, max_idx - 3)
            end = min(len(df), max_idx + 4)
            print(df.iloc[start:end][['time_s', col, 'total_g']])

    # 2. Look for Gravity Anomalies (Stationary should be 1.0G)
    if 'total_g' in df.columns:
        diff_g = (df['total_g'] - 1.0).abs()
        max_g_idx = diff_g.idxmax()
        
        print(f"\n[Gravity Anomaly] Max Deviation from 1G: {diff_g.iloc[max_g_idx]:.4f}")
        start = max(0, max_g_idx - 3)
        end = min(len(df), max_g_idx + 4)
        print(df.iloc[start:end][['time_s', 'accel_x_g', 'accel_y_g', 'accel_z_g', 'total_g']])

if __name__ == "__main__":
    target = "combined_imu_data.csv"
    if len(sys.argv) > 1:
        target = sys.argv[1]
    zoom_outliers(target)
