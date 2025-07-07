import psutil
import subprocess
import time
import csv
import os

# Adjust command as needed
'''
command = [
    "python3", "../src/main.py",
    "--file_path", "../downloads/",
    "--port_num", "8080",
    "--torrent_file", "../torrents/linuxmint-21.2-mate-64bit.iso.torrent",
    "--compact"
]
'''
command = [
    "transmission-cli",
    "-w", "../downloads/",
    "../torrents/linuxmint-21.2-mate-64bit.iso.torrent"
]

# Start the client process with access to stdin
proc = subprocess.Popen(command, stdin=subprocess.PIPE)
ps_proc = psutil.Process(proc.pid)

# Wait briefly and send 'n\n' to stdin
time.sleep(0.1)  # Adjust delay as needed based on how long until input is expected
proc.stdin.write(b"n\n")
proc.stdin.flush()

# Set up logging
csv_file = "./transmission_stats.csv"
with open(csv_file, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Time (s)", "Memory_MB", "User_CPU_s", "System_CPU_s", "Bytes_Received_MB", "Bytes_Sent_MB"])

    print("Monitoring BitTorrent client...\n")
    start = time.time()

    try:
        while proc.poll() is None:  # while client is still running
            elapsed = time.time() - start
            mem = ps_proc.memory_info().rss / (1024 * 1024)
            cpu = ps_proc.cpu_times()
            net = ps_proc.io_counters() if hasattr(ps_proc, 'io_counters') else None

            # Network I/O (if available)
            bytes_recv = net.read_bytes / (1024 * 1024) if net else 0
            bytes_sent = net.write_bytes / (1024 * 1024) if net else 0

            print(f"Time: {elapsed:.1f}s | Mem: {mem:.2f} MB | User CPU: {cpu.user:.2f}s | "
                  f"System CPU: {cpu.system:.2f}s | RX: {bytes_recv:.2f} MB | TX: {bytes_sent:.2f} MB")

            writer.writerow([f"{elapsed:.1f}", f"{mem:.2f}", f"{cpu.user:.2f}", f"{cpu.system:.2f}",
                             f"{bytes_recv:.2f}", f"{bytes_sent:.2f}"])
            time.sleep(2)

    except KeyboardInterrupt:
        print("\nMonitoring interrupted by user.")
    finally:
        if proc.poll() is None:
            proc.terminate()

        print(f"Time: {elapsed:.1f}s | Mem: {mem:.2f} MB | User CPU: {cpu.user:.2f}s | "
                  f"System CPU: {cpu.system:.2f}s | RX: {bytes_recv:.2f} MB | TX: {bytes_sent:.2f} MB")

        writer.writerow([f"{elapsed:.1f}", f"{mem:.2f}", f"{cpu.user:.2f}", f"{cpu.system:.2f}",
                             f"{bytes_recv:.2f}", f"{bytes_sent:.2f}"])
        print(f"\nStats saved to {os.path.abspath(csv_file)}")
