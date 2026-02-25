import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sys

def analyze_imu_integrity(csv_file):
    print(f"--- Analyzing {csv_file} ---")
    try:
        df = pd.read_csv(csv_file)
    except FileNotFoundError:
        print(f"Error: {csv_file} not found.")
        return

    if df.empty:
        print("Error: CSV is empty.")
        return

    # 1. Time Step Integrity
    df['dt'] = df['time_s'].diff()
    mean_dt = df['dt'].mean()
    std_dt = df['dt'].std()
    
    print("\n[Time Step Integrity]")
    print(f"Total Samples:    {len(df)}")
    if not np.isnan(mean_dt):
        print(f"Mean Sample Rate: {1/mean_dt:.2f} Hz ({mean_dt*1000:.3f} ms)")
        print(f"Jitter (Std Dev): {std_dt*1000:.6f} ms")
        
        # Precise Tick Gap Detection
        if 'raw_ts_ticks' in df.columns:
            df['ts_diff'] = df['raw_ts_ticks'].diff()
            # LSM6DSOX timestamp is 25us per tick. 
            # 104Hz -> ~9.6ms -> ~384 ticks
            # 417Hz -> ~2.4ms -> ~96 ticks
            median_tick_diff = df['ts_diff'].median()
            tick_gaps = df[df['ts_diff'] > median_tick_diff * 1.5]
            print(f"Median Tick Diff: {median_tick_diff} ({median_tick_diff*25/1000:.3f} ms)")
            print(f"Tick gaps detected: {len(tick_gaps)}")
            if len(tick_gaps) > 0:
                print(tick_gaps[['time_s', 'ts_diff']].head(5))
        
        # Identify gaps (e.g., > 2x the mean dt)
        gaps = df[df['dt'] > mean_dt * 2.0]
        if not gaps.empty:
            print(f"Found {len(gaps)} potential gaps/dropped samples (>2x mean dt):")
            print(gaps[['time_s', 'dt']].head(10))
        else:
            print("No significant time gaps detected.")
    else:
        print("Insufficient data for time step analysis.")

    # 2. IMU Data Jumps (Deltas)
    sensor_cols = ['accel_x_g', 'accel_y_g', 'accel_z_g', 'gyro_x_dps', 'gyro_y_dps', 'gyro_z_dps']
    
    print("\n[Sensor Data Integrity - Max Jumps per Sample]")
    for col in sensor_cols:
        if col not in df.columns: continue
        diff = df[col].diff().abs()
        max_jump = diff.max()
        # Threshold: 6 sigma jump is very aggressive
        threshold = diff.mean() + 6 * diff.std()
        jumps = df[diff > threshold]
        
        print(f"{col:15}: Max Δ = {max_jump:8.4f} | Threshold (6σ) = {threshold:8.4f} | Outliers: {len(jumps)}")

    # 3. Visualization
    try:
        fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
        
        # Plot Accel
        axes[0].plot(df['time_s'], df[['accel_x_g', 'accel_y_g', 'accel_z_g']])
        axes[0].set_ylabel('Accel (g)')
        axes[0].set_title('Accelerometer Data')
        axes[0].legend(['X', 'Y', 'Z'], loc='upper right')
        axes[0].grid(True, alpha=0.3)
        
        # Plot Gyro
        axes[1].plot(df['time_s'], df[['gyro_x_dps', 'gyro_y_dps', 'gyro_z_dps']])
        axes[1].set_ylabel('Gyro (dps)')
        axes[1].set_title('Gyroscope Data')
        axes[1].legend(['X', 'Y', 'Z'], loc='upper right')
        axes[1].grid(True, alpha=0.3)
        
        # Plot DT Jitter
        if not np.isnan(mean_dt):
            axes[2].plot(df['time_s'], df['dt'] * 1000)
            axes[2].axhline(y=mean_dt*1000, color='r', linestyle='--', label='Mean DT')
            axes[2].set_ylabel('Delta T (ms)')
            axes[2].set_title('Sample-to-Sample Time Delta')
            axes[2].set_xlabel('Time (s)')
            axes[2].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plot_name = "data_integrity_report.png"
        plt.savefig(plot_name)
        print(f"\nAnalysis plot saved to {plot_name}")
    except Exception as e:
        print(f"\nSkipping plot generation: {e}")

if __name__ == "__main__":
    target = "imu_data.csv"
    if len(sys.argv) > 1:
        target = sys.argv[1]
    analyze_imu_integrity(target)
