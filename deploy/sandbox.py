#!/usr/local/bin/python -I
"""Root-owned, fixed-command launcher; never accepts paths or executable code."""
import json
from contextlib import suppress
import logging
import os
from pathlib import Path
import pwd
import re
import resource
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlparse


def restrict_network(uid):
    """Allow this OS user to reach only the fixed HTTPS proxy, including IPv6 denial."""
    proxy = urlparse(os.environ["HTTPS_PROXY"])
    if proxy.scheme != "http" or proxy.hostname != "proxy" or proxy.port != 3128:
        raise ValueError("The sandbox requires the configured internal proxy")
    address = socket.gethostbyname("proxy")
    for tool in ("/usr/sbin/iptables", "/usr/sbin/ip6tables"):
        def run(*args, check=True):
            return subprocess.run([tool, "-w", *args], check=check,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run("-N", "FLAKE_SANDBOX", check=False)
        run("-F", "FLAKE_SANDBOX")
        if tool.endswith("/iptables"):
            run("-A", "FLAKE_SANDBOX", "-p", "tcp", "-d", address,
                "--dport", "3128", "-j", "ACCEPT")
        run("-A", "FLAKE_SANDBOX", "-j", "DROP")
        rule = ("OUTPUT", "-m", "owner", "--uid-owner", str(uid), "-j", "FLAKE_SANDBOX")
        if run("-C", *rule, check=False).returncode:
            run("-A", *rule)
    return f"http://{address}:3128"


def positive_setting(name, default):
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError("Resource settings must be positive")
    return value


def initialize_network():
    """Allow inbound response traffic and proxy connections; deny other container egress."""
    proxy_url = restrict_network(pwd.getpwnam("sandboxuser").pw_uid)
    address = urlparse(proxy_url).hostname
    for tool in ("/usr/sbin/iptables", "/usr/sbin/ip6tables"):
        def run(*args, check=True):
            return subprocess.run([tool, "-w", *args], check=check,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run("-N", "FLAKE_EGRESS", check=False)
        run("-F", "FLAKE_EGRESS")
        run("-A", "FLAKE_EGRESS", "-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "ACCEPT")
        if tool.endswith("/iptables"):
            # Only the privileged launcher resolves the fixed internal proxy hostname.
            run("-A", "FLAKE_EGRESS", "-d", "127.0.0.11", "-m", "owner", "--uid-owner", "0", "-j", "ACCEPT")
            run("-A", "FLAKE_EGRESS", "-d", address, "-p", "tcp", "--dport", "3128", "-j", "ACCEPT")
        run("-A", "FLAKE_EGRESS", "-j", "DROP")
        if run("-C", "OUTPUT", "-j", "FLAKE_EGRESS", check=False).returncode:
            run("-A", "OUTPUT", "-j", "FLAKE_EGRESS")


def main():
    if os.geteuid() == 0 and sys.argv[1:] == ["--init-network"]:
        initialize_network()
        return 0
    cleanup = len(sys.argv) == 3 and sys.argv[1] == "--clean"
    job_id = sys.argv[2] if cleanup else (sys.argv[1] if len(sys.argv) == 2 else "")
    if os.geteuid() != 0 or not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise ValueError("Invalid sandbox invocation")
    directory = Path("/work/jobs") / job_id
    if cleanup:
        if directory.is_symlink():
            directory.unlink()
        elif directory.exists():
            shutil.rmtree(directory)
        return 0
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Invalid job directory")
    metadata_path = directory / "job.json"
    if metadata_path.is_symlink():
        raise ValueError("Invalid job metadata")
    target = json.loads(metadata_path.read_text())["target"]
    if not re.fullmatch(r"test_[a-zA-Z0-9_]+\.py::test_[a-zA-Z0-9_]+", target):
        raise ValueError("Invalid target")
    source = directory / target.split("::")[0]
    if source.is_symlink() or not source.is_file():
        raise ValueError("Invalid target source")
    credentials = json.loads(sys.stdin.readline(16384))
    user = pwd.getpwnam("sandboxuser")
    proxy_url = restrict_network(user.pw_uid)
    os.chown(directory, user.pw_uid, user.pw_gid)
    os.chmod(directory, 0o2770)
    os.chown(source, user.pw_uid, user.pw_gid)
    os.chmod(source, 0o660)
    wall = positive_setting("SANDBOX_WALL_SECONDS", 90)
    cpu = positive_setting("SANDBOX_CPU_SECONDS", 60)
    memory = positive_setting("SANDBOX_MEMORY_MB", 512) * 1024 * 1024
    processes = positive_setting("SANDBOX_PROCESSES", 32)

    def limits():
        # This helper is single threaded; preexec_fn is safe here.
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_NPROC, (processes, processes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o007)
        os.setsid()

    command = ["/usr/bin/bwrap", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
               "--new-session", "--die-with-parent", "--cap-drop", "ALL",
               "--uid", str(user.pw_uid), "--gid", str(user.pw_gid),
               "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
               "--ro-bind", "/app", "/app", "--ro-bind", "/etc/ssl", "/etc/ssl",
               "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
               "--ro-bind", "/etc/hosts", "/etc/hosts",
               "--ro-bind", "/etc/nsswitch.conf", "/etc/nsswitch.conf",
               "--proc", "/proc", "--dev", "/dev", "--bind", str(directory), "/job",
               "--symlink", "/job", "/tmp", "--chdir", "/job"]
    if Path("/lib64").exists():
        command.extend(["--ro-bind", "/lib64", "/lib64"])
    command.extend(["--remount-ro", "/", "--disable-userns"])
    command.extend(["/usr/local/bin/python", "/app/main.py", target, "--runs", "5",
                    "--max-retries", "3", "--json-report", "/job/result.json"])
    environment = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/job", "TMPDIR": "/job",
                   "PYTHONDONTWRITEBYTECODE": "1", "ANTHROPIC_API_KEY": credentials["api_key"],
                   "HTTPS_PROXY": proxy_url, "PYTHONUNBUFFERED": "1"}
    # A private pipe keeps the process-group ID out of the sandbox's writable files.
    pid_read, pid_write = os.pipe()
    def prepare():
        limits()
        os.write(pid_write, str(os.getpid()).encode())
        os.close(pid_write)
        os.setgroups([])
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    try:
        with tempfile.TemporaryFile() as diagnostic:
            result = subprocess.run(command, env=environment, preexec_fn=prepare,
                                    pass_fds=(pid_write,), timeout=wall,
                                    stdout=diagnostic, stderr=diagnostic, check=False)
            if result.returncode:
                diagnostic.seek(0)
                details = diagnostic.read(65536).decode("utf-8", errors="replace")
                key = credentials.get("api_key", "")
                if key:
                    details = details.replace(key, "[redacted]")
                logging.error("Worker diagnostics: %s", details)
        return result.returncode
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(int(os.read(pid_read, 32)), signal.SIGKILL)
        raise RuntimeError("Sandbox wall-clock limit exceeded")
    finally:
        os.close(pid_read)
        os.close(pid_write)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logging.exception("Sandbox launcher failed")
        sys.exit(2)
