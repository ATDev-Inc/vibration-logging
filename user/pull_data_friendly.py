import os
import sys
import hashlib
import argparse
import getpass
import subprocess
import time
import platform
from datetime import datetime
from pathlib import Path

# Configuration
WIFI_SSID = "AT-DEV-LOGGER"
WIFI_PASS = "supersafepassword"
DEFAULT_USER = "ubuntu"
DEFAULT_PASS = "ubuntu"
DEFAULT_HOST = "10.42.0.1"

# Try to import rich for pretty output, fallback to print if not available
try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
    from rich.theme import Theme

    custom_theme = Theme({
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "highlight": "bold blue",
        "step": "bold white"
    })
    console = Console(theme=custom_theme)
    USE_RICH = True
except ImportError:
    USE_RICH = False
    class SimpleConsole:
        def print(self, msg):
            # Strip rich tags for plain print
            clean_msg = msg.replace("[info]", "").replace("[/info]", "") \
                         .replace("[warning]", "WARNING: ").replace("[/warning]", "") \
                         .replace("[error]", "ERROR: ").replace("[/error]", "") \
                         .replace("[success]", "SUCCESS: ").replace("[/success]", "") \
                         .replace("[step]", ">> ").replace("[/step]", "") \
                         .replace("[highlight]", "").replace("[/highlight]", "") \
                         .replace("[bold]", "").replace("[/bold]", "")
            print(clean_msg)
        def status(self, msg):
            self.print(msg)
            class Dummy:
                def __enter__(self): return self
                def __exit__(self, *args): pass
            return Dummy()
    console = SimpleConsole()

# Check for paramiko
try:
    import paramiko
except ImportError:
    console.print("[error]Error: 'paramiko' library is required.[/error]")
    console.print("[info]Please install it by running: pip install paramiko rich[/info]")
    sys.exit(1)

def connect_wifi_windows():
    """Windows-specific Wi-Fi connection using netsh."""
    try:
        xml_content = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{WIFI_SSID}</name>
    <SSIDConfig>
        <SSID><name>{WIFI_SSID}</name></SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{WIFI_PASS}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""
        xml_file = "wifi_profile_temp.xml"
        with open(xml_file, "w") as f:
            f.write(xml_content)
        subprocess.run(["netsh", "wlan", "add", "profile", f"filename={xml_file}"], capture_output=True, check=True)
        os.remove(xml_file)
        subprocess.run(["netsh", "wlan", "connect", f"name={WIFI_SSID}"], capture_output=True, check=True)
        return True
    except Exception:
        return False

def connect_wifi_macos():
    """macOS-specific Wi-Fi connection using networksetup."""
    try:
        res = subprocess.check_output(["networksetup", "-listallhardwareports"], text=True)
        interface = "en0"
        lines = res.splitlines()
        for i, line in enumerate(lines):
            if "Wi-Fi" in line:
                interface = lines[i+1].split(": ")[1].strip()
                break
        subprocess.run(["networksetup", "-setairportnetwork", interface, WIFI_SSID, WIFI_PASS], capture_output=True, check=True)
        return True
    except Exception:
        return False

def ensure_wifi_connected():
    """Attempts to connect to the Pi's Wi-Fi network based on the OS."""
    console.print(f"[step]Checking connection to [highlight]{WIFI_SSID}[/highlight]...[/step]")

    def can_ping_pi():
        ping_param = "-n" if platform.system() == "Windows" else "-c"
        try:
            subprocess.run(["ping", ping_param, "1", DEFAULT_HOST], capture_output=True, check=True, timeout=2)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    # Check if we can already reach the Pi
    if can_ping_pi():
        console.print("[success]Already connected to the Pi network.[/success]")
        return True

    console.print(f"[info]Attempting to auto-connect to {WIFI_SSID}...[/info]")
    system = platform.system()

    if system == "Windows":
        connect_wifi_windows()
    elif system == "Darwin": # macOS
        connect_wifi_macos()
    else:
        # Fallback for Linux (nmcli)
        try:
            subprocess.run(["nmcli", "dev", "wifi", "connect", WIFI_SSID, "password", WIFI_PASS], capture_output=True, check=True)
        except:
            pass

    # Verify connection
    console.print("[info]Verifying connection (this may take a few seconds)...[/info]")
    for i in range(3): # Try pinging 3 times over 15 seconds
        time.sleep(5)
        if can_ping_pi():
            console.print(f"[success]Successfully connected to {WIFI_SSID}.[/success]")
            return True
        console.print(f"[info]Waiting for Pi to become reachable ({i+1}/3)...[/info]")

    console.print(f"[warning]Could not verify connection to Pi. Please manually connect to Wi-Fi: {WIFI_SSID}[/warning]")
    return False

def get_hash(filepath, block_size=65536):
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for block in iter(lambda: f.read(block_size), b''):
            sha256.update(block)
    return sha256.hexdigest()

def get_remote_hash(ssh, remote_path):
    stdin, stdout, stderr = ssh.exec_command(f"sha256sum {remote_path}")
    result = stdout.read().decode().split()
    return result[0] if result else None

def pull_data(host, user, remote_dir, local_dir, password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    console.print(f"[step]Connecting to Pi at [highlight]{host}[/highlight]...[/step]")
    try:
        ssh.connect(host, username=user, password=password, timeout=10)
        sftp = ssh.open_sftp()
    except Exception as e:
        console.print(f"[error]Failed to connect: {e}[/error]")
        console.print("[info]Tip: Ensure you are connected to the 'AT-DEV-LOGGER' Wi-Fi network.[/info]")
        return

    # Stop the logger service to ensure we don't transfer files while they are being written
    console.print("[info]Stopping data collection service on Pi...[/info]")
    ssh.exec_command(f"echo {password} | sudo -S systemctl stop vibration_logger.service")

    try:
        Path(local_dir).mkdir(parents=True, exist_ok=True)

        with console.status("[info]Searching for logs on Pi...[/info]"):
            command = f"ls {remote_dir}/*.bin {remote_dir}/*.ready 2>/dev/null"
            stdin, stdout, stderr = ssh.exec_command(command)
            remote_files = stdout.read().decode().splitlines()

        if not remote_files:
            console.print("[warning]No log files found on the Pi.[/warning]")
        else:
            console.print(f"[success]Found {len(remote_files)} files to download.[/success]")

            if USE_RICH:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=console
                ) as progress:
                    for remote_file in remote_files:
                        filename = os.path.basename(remote_file)
                        local_path = os.path.join(local_dir, filename)
                        remote_hash = get_remote_hash(ssh, remote_file)

                        try:
                            task_id = progress.add_task(f"Downloading {filename}", total=sftp.stat(remote_file).st_size)
                            sftp.get(remote_file, local_path, callback=lambda tr, to: progress.update(task_id, completed=tr))

                            if remote_hash == get_hash(local_path):
                                console.print(f"  [success]✓ {filename} verified.[/success]")
                                sftp.remove(remote_file)
                            else:
                                console.print(f"  [error]✗ {filename} verification FAILED![/error]")
                        except Exception as e:
                            console.print(f"  [error]Failed {filename}: {e}[/error]")
            else:
                for remote_file in remote_files:
                    filename = os.path.basename(remote_file)
                    local_path = os.path.join(local_dir, filename)
                    console.print(f"[info]Downloading {filename}...[/info]")
                    sftp.get(remote_file, local_path)
                    sftp.remove(remote_file)
                    console.print(f"[success]Downloaded {filename}[/success]")

            console.print(f"\n[success][bold]All Done![/bold][/success] Logs saved in: [highlight]{local_dir}[/highlight]")

    finally:
        # Restart the logger service regardless of success or failure
        console.print("[info]Restarting data collection service on Pi...[/info]")
        ssh.exec_command(f"echo {password} | sudo -S systemctl start vibration_logger.service")
        sftp.close()
        ssh.close()

if __name__ == "__main__":
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_local_dir = os.path.join("logs", f"download_{timestamp}")

    parser = argparse.ArgumentParser(description="Easy Vibration Log Puller")
    parser.add_argument("--local-dir", default=default_local_dir, help="Where to save logs")
    parser.add_argument("--skip-wifi", action="store_true", help="Skip Wi-Fi auto-connect")
    args = parser.parse_args()

    if not args.skip_wifi:
        ensure_wifi_connected()

    try:
        pull_data(DEFAULT_HOST, DEFAULT_USER, "/home/ubuntu/vibration-logger/pi/logs", args.local_dir, DEFAULT_PASS)
    except KeyboardInterrupt:
        console.print("\n[warning]Cancelled by user.[/warning]")
    except Exception as e:
        console.print(f"[error]An unexpected error occurred: {e}[/error]")
