import fcntl
import re
import socket
import struct
import subprocess
import sys
from pathlib import Path


def get_mac_address_old() -> str:
    # deprecated because it is not bound to the interface
    from uuid import getnode as get_mac

    mac = get_mac()
    return ":".join(f"{mac:012x}"[i : i + 2] for i in range(0, 12, 2))


def get_mac_address(ifname: str = "eth0") -> str | None:
    # this replaces shell-command:
    # ip link show eth0 | grep link/ether | cut -d ' ' --fields=6
    if sys.platform != "linux":
        return None
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        info = fcntl.ioctl(sock.fileno(), 0x8927, struct.pack("256s", bytes(ifname, "utf-8")[:15]))
        return ":".join(f"{b:02x}" for b in info[18:24])
    except OSError:
        return None


def mac_2_hostname(mac: str) -> str | None:
    from shepherd_core.testbed_client import tb_client

    mac = mac.lower()
    for obs_name in tb_client.list_resource_names("Observer"):
        obs_data = tb_client.get_resource_item("Observer", name=obs_name)
        if "mac" in obs_data and mac == obs_data["mac"].lower():
            return obs_name
    return None


def get_hostname() -> str:
    import socket

    return socket.gethostname()


def set_hostname(hostname: str) -> bool:
    """First step in changing the hostname

    Debian has two ways to do it on the shell:
        sudo hostnamectl set-hostname newname
        sudo hostname -b newname
    """
    return (
        subprocess.run(  # noqa: S603
            # requires appropriate permissions, e.g., sudo
            ["/usr/bin/hostnamectl", "set-hostname", str(hostname)],
            timeout=3,
            check=False,
            shell=False,
            capture_output=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def adjust_hosts_domain_name(hostname: str, path_file: Path = Path("/etc/hosts")) -> bool:
    r"""
    ansible.builtin.lineinfile:
        dest: /etc/hosts
        regexp: '^127\.0\.1\.1\s+.+\.localdomain\s+.+'
        line: '127.0.1.1  {{ inventory_hostname }}.localdomain  {{ inventory_hostname }}'
        state: present
    """
    desired_line = f"127.0.1.1  {hostname}.localdomain  {hostname}\n"
    pattern = r"^127\.0\.1\.1\s+.+\.localdomain\s+.+"

    with path_file.open() as f:
        lines = f.readlines()

    new_lines = []
    replaced = False

    for line in lines:
        if re.match(pattern, line):
            # Replace matching line
            new_lines.append(desired_line)
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        # Append if no matching line was found
        if lines and not lines[-1].endswith("\n"):
            # ensure newline before appending
            new_lines.append("\n")
        new_lines.append(desired_line)

    # Write back requires appropriate file permissions, e.g., sudo
    with path_file.open("w") as f:
        f.writelines(new_lines)

    return replaced
