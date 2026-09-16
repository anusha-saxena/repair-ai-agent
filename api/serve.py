"""Initialize container egress restrictions before accepting any requests."""
import os
import subprocess


def main():
    """Keep the server non-root and fail closed if the firewall cannot be installed."""
    port = os.getenv("PORT", "8000")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("PORT must be a number between 1 and 65535")
    subprocess.run(["sudo", "-n", "/usr/local/bin/flake-sandbox", "--init-network"],
                   check=True, timeout=15)
    os.execvp("uvicorn", ["uvicorn", "api.main:app", "--host", "0.0.0.0",
                         "--port", port, "--workers", "1", "--no-proxy-headers"])


if __name__ == "__main__":
    main()
