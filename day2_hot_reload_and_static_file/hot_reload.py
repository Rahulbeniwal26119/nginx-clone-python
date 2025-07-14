# Adding support for hot reloading the server when files change
import signal
import subprocess
import sys
import time
from pathlib import Path

# Planning
# We will store the last modified times of files we care about in a dict
# When we detect a change, we will restart the server

EXTS = {".py", ".json", ".html"}


def scan_files(root="."):
    mtimes = {}
    for path in Path(root).rglob("*"):
        if path.suffix in EXTS and path.is_file():
            mtimes[path] = path.stat().st_mtime
    return mtimes


def reload_require(prev_mtimes):
    current_mtimes = scan_files()
    for path, mtime in current_mtimes.items():
        if path in prev_mtimes and prev_mtimes[path] != mtime:
            return True, current_mtimes

    # Handle for delete files too
    for path in prev_mtimes:
        if path not in current_mtimes:
            return True, current_mtimes

    return False, prev_mtimes


# Great we are almost done, now let's logic for this scripts to start a child process


def run_child(cmd):
    try:
        proc = subprocess.Popen(
            [
                sys.executable,  # Python executable in current env
                *cmd,
            ],
            stdin=subprocess.PIPE,  # Allow sending input to child process
        )
        print(f"Child process running on {proc.pid}")
        return proc
    except Exception as e:
        print(f"failed to start child process: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 hot_reload.py <script.py>")
        return

    child = None
    while True:
        command = " ".join(sys.argv[1:])
        print(f"🦄 Starting {command}")
        child = run_child(sys.argv[1:])
        if not child:
            print(f"Failed to start {command}")
            sys.exit(1)

        mtimes = scan_files()

        try:
            while True:
                time.sleep(0.5)  # Buffer for half second
                # Check if child process has existed
                if child.poll():
                    print(
                        f"Child process with pid {child.pid} existed with errorcode {child.returncode}"
                    )
                    sys.exit(child.returncode)

                # check if restart needed
                restart, mtimes = reload_require(mtimes)

                if restart:
                    print(f"🦄 Restart: {command}")

                    # Kill the existing process
                    child.send_signal(signal.SIGTERM)
                    # wait for 2 second
                    try:
                        child.wait(2)
                    except subprocess.TimeoutExpired:
                        child.kill()
                    break
        except KeyboardInterrupt:
            print("🦄 Termiating the hot reload script")
            # kill the child process too
            if child:
                child.kill()
                child.wait()
            sys.exit(0)  # Success


if __name__ == "__main__":
    main()
