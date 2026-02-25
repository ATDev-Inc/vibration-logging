import os
import sys
import hashlib
import argparse
import getpass
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from rich.theme import Theme

# Custom theme for consistent styling
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "highlight": "bold blue",
    "step": "bold white"
})

console = Console(theme=custom_theme)

try:
    import paramiko
except ImportError:
    console.print("[error]Error: paramiko is required.[/error]")
    console.print("Install dependencies using: [bold]pip install .[/bold] or [bold]uv sync[/bold]")
    sys.exit(1)

def get_hash(filepath, block_size=65536):
    """Calculates SHA256 hash of a local file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for block in iter(lambda: f.read(block_size), b''):
            sha256.update(block)
    return sha256.hexdigest()

def get_remote_hash(ssh, remote_path):
    """Calculates SHA256 hash of a remote file using sha256sum."""
    stdin, stdout, stderr = ssh.exec_command(f"sha256sum {remote_path}")
    result = stdout.read().decode().split()
    if not result:
        return None
    return result[0]

def pull_data(host, user, remote_dir, local_dir, password=None, key_file=None):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    console.print(f"[step]Connecting to [highlight]{user}@{host}[/highlight]...[/step]")
    try:
        ssh.connect(host, username=user, password=password, key_filename=key_file)
        sftp = ssh.open_sftp()
    except paramiko.AuthenticationException:
        raise
    except Exception as e:
        console.print(f"[error]Failed to connect: {e}[/error]")
        return

    # Ensure local directory exists
    Path(local_dir).mkdir(parents=True, exist_ok=True)

    # Find log files on remote
    with console.status("[info]Searching for logs on Pi...[/info]"):
        command = f"ls {remote_dir}/*.bin {remote_dir}/*.ready 2>/dev/null"
        stdin, stdout, stderr = ssh.exec_command(command)
        remote_files = stdout.read().decode().splitlines()

    if not remote_files:
        console.print("[warning]No log files found on the Pi.[/warning]")
        sftp.close()
        ssh.close()
        return

    console.print(f"[success]Found {len(remote_files)} files to download.[/success]")

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

            # 1. Get remote hash
            remote_hash = get_remote_hash(ssh, remote_file)
            if not remote_hash:
                console.print(f"[warning]  Warning: Could not get hash for {filename}. Skipping.[/warning]")
                continue

            # 2. Download with progress
            task_id = progress.add_task(f"Downloading {filename}", total=sftp.stat(remote_file).st_size)
            
            def sftp_callback(transferred, total):
                progress.update(task_id, completed=transferred)

            sftp.get(remote_file, local_path, callback=sftp_callback)

            # 3. Verify
            local_hash = get_hash(local_path)
            if remote_hash == local_hash:
                console.print(f"  [success]✓ {filename} verified.[/success]")
                # 4. Cleanup
                sftp.remove(remote_file)
            else:
                console.print(f"  [error]✗ {filename} verification FAILED![/error]")

    console.print(f"\n[success][bold]Sync Complete![/bold][/success] Data stored in [highlight]{local_dir}[/highlight]")
    sftp.close()
    ssh.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull vibration logs from Raspberry Pi.")
    parser.add_argument("--host", default="10.42.0.1", help="Pi hostname or IP")
    parser.add_argument("--user", default="ubuntu", help="SSH username")
    parser.add_argument("--remote-dir", default="/home/ubuntu/vibration-logger/logs", help="Remote logs directory")
    parser.add_argument("--local-dir", default="./pulled_logs", help="Local directory to store logs")
    parser.add_argument("--key", help="Path to SSH private key file")
    parser.add_argument("--password", action="store_true", help="Prompt for password")

    args = parser.parse_args()

    password = None
    if args.password:
        password = getpass.getpass(f"Password for {args.user}@{args.host}: ")

    try:
        pull_data(args.host, args.user, args.remote_dir, args.local_dir, password=password, key_file=args.key)
    except paramiko.AuthenticationException:
        if not password:
            console.print("[warning]Authentication failed. Please enter password.[/warning]")
            password = getpass.getpass(f"Password for {args.user}@{args.host}: ")
            pull_data(args.host, args.user, args.remote_dir, args.local_dir, password=password, key_file=args.key)
        else:
            console.print("[error]Authentication failed even with password.[/error]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[error]An error occurred: {e}[/error]")
        sys.exit(1)
