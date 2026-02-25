import struct
import sys
import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.fft import fft, fftfreq
from scipy.signal import find_peaks
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

console = Console()

# LSM6DSOX Constants from read_data.py
LSM6DSOX_GYRO_NC_TAG = 1
LSM6DSOX_XL_NC_TAG = 2
LSM6DSOX_TIMESTAMP_TAG = 4
ACCEL_FS_16G_SENSITIVITY = 0.488  # mg/LSB
GYRO_FS_2000DPS_SENSITIVITY = 70.0  # mdps/LSB
TIMESTAMP_RES_US = 25.0  # 25us per LSB

def parse_binary_logs(bin_files):
    """Robustly parses binary log files into a DataFrame."""
    data_store = {}
    last_ts = 0
    rows = []

    if not bin_files:
        return pd.DataFrame()

    console.print(f"[info]Parsing {len(bin_files)} binary files...[/info]")

    with Progress() as progress:
        task = progress.add_task("[cyan]Processing Binary...", total=len(bin_files))
        for bin_filename in sorted(bin_files):
            with open(bin_filename, "rb") as f_bin:
                while True:
                    record = f_bin.read(7)
                    if len(record) < 7: break

                    tag = (record[0] >> 3) & 0x1F
                    payload = record[1:]

                    if tag == LSM6DSOX_TIMESTAMP_TAG:
                        last_ts = struct.unpack("<I", payload[:4])[0]
                    elif tag == LSM6DSOX_XL_NC_TAG:
                        if last_ts not in data_store:
                            data_store[last_ts] = {'ax': None, 'ay': None, 'az': None, 'gx': None, 'gy': None, 'gz': None}
                        x, y, z = struct.unpack("<hhh", payload)
                        data_store[last_ts]['ax'] = (x * ACCEL_FS_16G_SENSITIVITY) / 1000.0
                        data_store[last_ts]['ay'] = (y * ACCEL_FS_16G_SENSITIVITY) / 1000.0
                        data_store[last_ts]['az'] = (z * ACCEL_FS_16G_SENSITIVITY) / 1000.0
                    elif tag == LSM6DSOX_GYRO_NC_TAG:
                        if last_ts not in data_store:
                            data_store[last_ts] = {'ax': None, 'ay': None, 'az': None, 'gx': None, 'gy': None, 'gz': None}
                        x, y, z = struct.unpack("<hhh", payload)
                        data_store[last_ts]['gx'] = (x * GYRO_FS_2000DPS_SENSITIVITY) / 1000.0
                        data_store[last_ts]['gy'] = (y * GYRO_FS_2000DPS_SENSITIVITY) / 1000.0
                        data_store[last_ts]['gz'] = (z * GYRO_FS_2000DPS_SENSITIVITY) / 1000.0

                    if len(data_store) > 500:
                        completed_ts = []
                        # We use a threshold to ensure we don't drop samples that are still being aligned
                        for ts in sorted(data_store.keys()):
                            entry = data_store[ts]
                            if entry['ax'] is not None and entry['gx'] is not None:
                                ts_s = (ts * TIMESTAMP_RES_US / 1_000_000.0)
                                rows.append([ts_s, entry['ax'], entry['ay'], entry['az'], entry['gx'], entry['gy'], entry['gz']])
                                completed_ts.append(ts)
                            elif ts < last_ts - 1000: # Stale data cleanup
                                completed_ts.append(ts)
                        for ts in completed_ts: del data_store[ts]
            progress.update(task, advance=1)

    # Final flush
    for ts in sorted(data_store.keys()):
        entry = data_store[ts]
        if entry['ax'] is not None and entry['gx'] is not None:
            ts_s = (ts * TIMESTAMP_RES_US / 1_000_000.0)
            rows.append([ts_s, entry['ax'], entry['ay'], entry['az'], entry['gx'], entry['gy'], entry['gz']])

    df = pd.DataFrame(rows, columns=['time_s', 'accel_x_g', 'accel_y_g', 'accel_z_g', 'gyro_x_dps', 'gyro_y_dps', 'gyro_z_dps'])
    return df

from scipy.signal import find_peaks, spectrogram
...
def analyze_dataframe(df, output_prefix, output_dir="."):
    """Performs FFT, Statistical, Bode, and Time-Frequency analysis."""
    if df.empty:
        console.print("[bold red]No valid IMU samples found.[/bold red]")
        return

    # 0. Pre-processing: Calculate Total-g (Vector Sum)
    console.print("[info]Calculating Vector Sum (Total-g)...[/info]")
    df['total_g'] = np.sqrt(df['accel_x_g']**2 + df['accel_y_g']**2 + df['accel_z_g']**2)
    df['total_g_detrended'] = df['total_g'] - df['total_g'].mean()

    # Calculate Sampling Frequency
    dt = df['time_s'].diff().median()
    if dt == 0 or np.isnan(dt):
        console.print("[bold red]Invalid time data.[/bold red]")
        return
    fs = 1.0 / dt
    console.print(f"Detected Sampling Frequency: [green]{fs:.2f} Hz[/green]")

    accel_axes = ['accel_x_g', 'accel_y_g', 'accel_z_g', 'total_g']

    console.print("[info]Initializing plots...[/info]")
    # --- 1. Standard Analysis Plot ---
    fig, axes_plt = plt.subplots(4, 2, figsize=(15, 14), sharex='col')
    fig.suptitle(f'Vibration Analysis: {output_prefix}', fontsize=16)

    # --- 2. Bode Plot ---
    fig_bode, axes_bode = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    fig_bode.suptitle(f'Bode Plot: {output_prefix}', fontsize=16)

    # --- 3. Spectrogram Plot (Time-Frequency) ---
    fig_spec, axes_spec = plt.subplots(4, 1, figsize=(12, 16), sharex=True)
    fig_spec.suptitle(f'Time-Frequency Analysis (Spectrogram): {output_prefix}', fontsize=16)

    stats_table = Table(title=f"Statistics: {output_prefix}")
    stats_table.add_column("Axis", style="cyan")
    stats_table.add_column("RMS (g)", justify="right")
    stats_table.add_column("Peak-to-Peak (g)", justify="right")
    stats_table.add_column("Primary Freq", justify="right")

    for i, axis in enumerate(accel_axes):
        console.print(f"Analyzing [cyan]{axis}[/cyan]...")
        # Data preparation
        data = df[axis] - df[axis].mean()
        n = len(data)

        # --- A. FFT & Stats ---
        yf = fft(data.values)
        xf = fftfreq(n, 1/fs)[:n//2]
        mag = 2.0/n * np.abs(yf[0:n//2])

        peaks, _ = find_peaks(mag, height=mag.max()*0.2)
        primary_freq = "N/A"
        if len(peaks) > 0:
            top_peak = peaks[np.argmax(mag[peaks])]
            primary_freq = f"{xf[top_peak]:.1f} Hz"

        rms = np.sqrt(np.mean(data**2))
        p2p = data.max() - data.min()
        stats_table.add_row(axis, f"{rms:.4f}", f"{p2p:.4f}", primary_freq)

        # Plot Standard
        axes_plt[i, 0].plot(df['time_s'], data, linewidth=0.5)
        axes_plt[i, 0].set_ylabel(f'{axis} (g)')
        axes_plt[i, 0].grid(True, alpha=0.3)
        if i == 0: axes_plt[i, 0].set_title('Time Domain (Detrended)')

        axes_plt[i, 1].plot(xf, mag, linewidth=0.7, color='tab:orange')
        axes_plt[i, 1].set_ylabel('Mag (g)')
        axes_plt[i, 1].grid(True, alpha=0.3)
        axes_plt[i, 1].set_xlim(0, fs/2)
        if i == 0: axes_plt[i, 1].set_title('FFT (Power Spectrum)')

        # --- B. Bode Analysis (Windowed) ---
        window = np.hanning(n)
        yf_w = fft(data.values * window)
        mag_w = 2.0/n * np.abs(yf_w[0:n//2])
        phase_w = np.angle(yf_w[0:n//2], deg=True)
        mag_db = 20 * np.log10(mag_w + 1e-9)

        axes_bode[0].semilogx(xf, mag_db, label=axis, alpha=0.8)
        axes_bode[1].semilogx(xf, phase_w, label=axis, alpha=0.6)

        # --- C. Spectrogram ---
        f_s, t_s, Sxx = spectrogram(data.values, fs, nperseg=min(n, 1024))

        im = axes_spec[i].pcolormesh(t_s, f_s, 10 * np.log10(Sxx + 1e-12), shading='gouraud', cmap='viridis')
        axes_spec[i].set_ylabel(f'{axis}\nFreq (Hz)')
        fig_spec.colorbar(im, ax=axes_spec[i], label='dB')

        # Label top 3 salient frequencies on the spectrogram
        peaks_all, _ = find_peaks(mag, height=mag.max()*0.02, distance=max(1, int(fs/50)))
        if len(peaks_all) > 0:
            # Sort by magnitude and take top 3
            sorted_peak_indices = np.argsort(mag[peaks_all])[::-1][:10]
            top_3_freqs = xf[peaks_all[sorted_peak_indices]]

            for freq in top_3_freqs:
                # Draw horizontal line and text label
                axes_spec[i].axhline(y=freq, color='white', linestyle='--', alpha=0.4, linewidth=1.0)
                axes_spec[i].text(t_s[0], freq, f" {freq:.1f}Hz", color='white',
                                  verticalalignment='bottom', fontsize=8, fontweight='bold',
                                  bbox=dict(facecolor='black', alpha=0.4, edgecolor='none', pad=1))

    # Finalize Plots
    console.print("[info]Finalizing and saving plots...[/info]")
    axes_plt[-1, 0].set_xlabel('Time (s)')
    axes_plt[-1, 1].set_xlabel('Frequency (Hz)')
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    analysis_path = os.path.join(output_dir, f"{output_prefix}_analysis.png")
    fig.savefig(analysis_path)

    axes_bode[0].set_ylabel('Magnitude (dBg)')
    axes_bode[0].grid(True, which="both", ls="-", alpha=0.3)
    axes_bode[0].legend()
    axes_bode[1].set_ylabel('Phase (deg)')
    axes_bode[1].set_xlabel('Frequency (Hz)')
    axes_bode[1].grid(True, which="both", ls="-", alpha=0.3)
    axes_bode[1].set_ylim(-180, 180)
    fig_bode.tight_layout(rect=[0, 0.03, 1, 0.95])
    bode_path = os.path.join(output_dir, f"{output_prefix}_bode.png")
    fig_bode.savefig(bode_path)

    axes_spec[-1].set_xlabel('Time (s)')
    fig_spec.tight_layout(rect=[0, 0.03, 1, 0.95])
    spec_path = os.path.join(output_dir, f"{output_prefix}_spectrogram.png")

    # Show only up to 50 hz
    for ax in axes_spec:
        ax.set_ylim(0, 50)

    fig_spec.savefig(spec_path)

    plt.close('all') # Free memory

    console.print(stats_table)
    console.print(f"\n[bold green]Reports generated in {output_dir}:[/bold green]")
    console.print(f"  - Standard:    {os.path.basename(analysis_path)}")
    console.print(f"  - Bode Plot:   {os.path.basename(bode_path)}")
    console.print(f"  - Spectrogram: {os.path.basename(spec_path)}")

def main():
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python vibration_analysis.py <dir_or_file>[/yellow]")
        return

    path = sys.argv[1]
    df = None
    output_dir = "."
    prefix = "analysis"

    if os.path.isdir(path):
        output_dir = path
        files = glob.glob(os.path.join(path, "*.ready")) + glob.glob(os.path.join(path, "*.bin"))
        df = parse_binary_logs(files)
        prefix = os.path.basename(path.rstrip('/'))
    else:
        output_dir = os.path.dirname(path) or "."
        if path.endswith('.csv'):
            console.print(f"[info]Reading CSV: {path}[/info]")
            df = pd.read_csv(path)
        else:
            df = parse_binary_logs([path])
        prefix = os.path.basename(path).split('.')[0]

    if df is not None and not df.empty:
        analyze_dataframe(df, prefix, output_dir)
    else:
        console.print("[bold red]No data found to analyze.[/bold red]")

if __name__ == "__main__":
    main()
