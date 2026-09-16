"""Initialize container egress restrictions before accepting any requests."""
import os
import subprocess


def main():
    """Keep the server non-root and fail closed if the firewall cannot be installed."""
    subprocess.run(["sudo", "-n", "/usr/local/bin/flake-sandbox", "--init-network"],
                   check=True, timeout=15)
    os.execvp("uvicorn", ["uvicorn", "api.main:app", "--host", "0.0.0.0",
                         "--port", "8000", "--workers", "1", "--no-proxy-headers"])


if __name__ == "__main__":
    main()
