#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mikan QEMU 启动器 v9.0 - VMware风格UI
完整功能保留：快照、U盘挂载、鼠标切换、性能监控
"""

import os
import sys
import json
import subprocess
import time
import re
import shutil
import threading
import ctypes
import socket
import shlex
import glob
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

# ============================================================
# 修复 Windows 编码问题
# ============================================================
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
        sys.stderr.reconfigure(encoding='utf-8', errors='ignore')
    except:
        pass
    os.environ['PYTHONIOENCODING'] = 'utf-8'

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

# ============================================================
# 配置
# ============================================================
BASE_DIR = Path(__file__).parent
VMS_DIR = BASE_DIR / "vms"
SHARE_DIR = BASE_DIR / "share"
SHARE_DIR.mkdir(parents=True, exist_ok=True)

running_vms: Dict[str, QProcess] = {}

# ============================================================
# QEMU 功能自动检测（带缓存）
# ============================================================
_qemu_features_cache: Dict[str, dict] = {}

def get_qemu_features(qemu_exe: Path) -> dict:
    exe_path = str(qemu_exe)
    if exe_path in _qemu_features_cache:
        return _qemu_features_cache[exe_path]
    
    features = {
        "grab_on_click": False,
        "gl_on": False,
        "window_size": False,
        "audiodev": False,
        "sandbox": False,
        "no_shutdown": False,
        "no_reboot": False,
        "qmp": False,
        "virtio_gpu": False,
    }
    
    if not qemu_exe.exists():
        _qemu_features_cache[exe_path] = features
        return features
    
    try:
        result = subprocess.run(
            [str(qemu_exe), "-display", "help"],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=5
        )
        if result.returncode == 0:
            output = result.stdout + result.stderr
            if "grab-on-click" in output:
                features["grab_on_click"] = True
            if "gl=" in output:
                features["gl_on"] = True
            if "window-size" in output:
                features["window_size"] = True
    except:
        pass
    
    try:
        result = subprocess.run(
            [str(qemu_exe), "-audiodev", "help"],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=5
        )
        if result.returncode == 0:
            features["audiodev"] = True
    except:
        pass
    
    try:
        result = subprocess.run(
            [str(qemu_exe), "-sandbox", "help"],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=5
        )
        if result.returncode == 0:
            features["sandbox"] = True
    except:
        pass
    
    try:
        result = subprocess.run(
            [str(qemu_exe), "-no-shutdown", "-nographic", "-version"],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=5
        )
        if "unrecognized" not in (result.stderr + result.stdout).lower():
            features["no_shutdown"] = True
    except:
        pass
    
    try:
        result = subprocess.run(
            [str(qemu_exe), "-no-reboot", "-nographic", "-version"],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=5
        )
        if "unrecognized" not in (result.stderr + result.stdout).lower():
            features["no_reboot"] = True
    except:
        pass
    
    try:
        result = subprocess.run(
            [str(qemu_exe), "-qmp", "help"],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=5
        )
        if result.returncode == 0:
            features["qmp"] = True
    except:
        pass
    
    try:
        result = subprocess.run(
            [str(qemu_exe), "-device", "virtio-gpu-pci,help"],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=5
        )
        if result.returncode == 0 or "vgamem" in (result.stderr + result.stdout):
            features["virtio_gpu"] = True
    except:
        pass
    
    _qemu_features_cache[exe_path] = features
    return features

# ============================================================
# 自动路径修复
# ============================================================
def fix_vm_config_paths(config: dict, vm_name: str) -> tuple:
    fixes = []
    vm_dir = VMS_DIR / vm_name
    current_user = os.getlogin().lower() if os.name == 'nt' else os.getenv('USER', '')
    
    path_fields = ['disk_path', 'boot_iso', 'kernel_iso', 'driver_iso', 
                   'backing_file', 'bios_file', 'share_dir', 'log_file']
    
    for field in path_fields:
        if field not in config or not config[field]:
            continue
        path_str = config[field]
        if not path_str or not isinstance(path_str, str):
            continue
        if 'Administrator' in path_str and current_user:
            new_path = path_str.replace('Administrator', current_user)
            new_path = new_path.replace('administrator', current_user)
            new_path = new_path.replace('ADMINISTRATOR', current_user)
            if new_path != path_str:
                config[field] = new_path
                fixes.append(f"🔧 修复 {field}: 用户 Administrator → {current_user}")
        
        if field in ['disk_path', 'backing_file']:
            path_obj = Path(path_str)
            if not path_obj.exists():
                filename = path_obj.name
                if filename:
                    candidate = vm_dir / filename
                    if candidate.exists():
                        config[field] = str(candidate)
                        fixes.append(f"🔧 修复 {field}: 重新定位到 {candidate}")
    
    disks = config.get('disks', [])
    if disks:
        fixed_disks = []
        for disk in disks:
            if 'path' in disk:
                path_str = disk['path']
                if 'Administrator' in path_str and current_user:
                    new_path = path_str.replace('Administrator', current_user)
                    new_path = new_path.replace('administrator', current_user)
                    new_path = new_path.replace('ADMINISTRATOR', current_user)
                    if new_path != path_str:
                        disk['path'] = new_path
                        fixes.append(f"🔧 修复 磁盘路径: 用户 Administrator → {current_user}")
                path_obj = Path(disk['path'])
                if not path_obj.exists():
                    filename = path_obj.name
                    if filename:
                        candidate = vm_dir / filename
                        if candidate.exists():
                            disk['path'] = str(candidate)
                            fixes.append(f"🔧 修复 磁盘: 重新定位到 {candidate}")
            fixed_disks.append(disk)
        config['disks'] = fixed_disks
    
    if not config.get('disks') and config.get('disk_path'):
        disk_path = Path(config['disk_path'])
        if disk_path.exists():
            config['disks'] = [{
                "id": 1,
                "path": str(disk_path),
                "size": config.get('disk_size', 32),
                "format": config.get('disk_format', 'qcow2'),
                "interface": config.get('disk_interface', 'sata'),
                "cache": config.get('cache', 'writeback'),
                "backing_file": "",
                "readonly": False,
                "removable": False
            }]
            config['disk_id_counter'] = 1
            fixes.append("🔧 自动重建 disks 列表")
    
    return config, fixes

def auto_fix_all_vms():
    all_fixes = {}
    if not VMS_DIR.exists():
        return all_fixes
    
    for vm_dir in VMS_DIR.iterdir():
        if not vm_dir.is_dir():
            continue
        config_file = vm_dir / "config.json"
        if not config_file.exists():
            continue
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            fixed_config, fixes = fix_vm_config_paths(config, vm_dir.name)
            
            if fixes:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(fixed_config, f, indent=2, ensure_ascii=False)
                all_fixes[vm_dir.name] = fixes
        except Exception as e:
            print(f"⚠️ 修复 {vm_dir.name} 时出错: {e}")
    
    return all_fixes

# ============================================================
# QEMU 版本识别
# ============================================================
def get_qemu_year(qemu_version: str) -> int:
    match = re.search(r'(20[1-9][0-9])', qemu_version)
    if match:
        year = int(match.group(1))
        if 2011 <= year <= 2026:
            return year
    match = re.search(r'(\d{8})', qemu_version)
    if match:
        date_str = match.group(1)
        if date_str.startswith(('201', '202')):
            year = int(date_str[:4])
            if 2011 <= year <= 2026:
                return year
    version_map = {
        '0.15': 2011, '0.16': 2012,
        '1.0': 2012, '1.1': 2012, '1.2': 2013, '1.3': 2013,
        '1.4': 2013, '1.5': 2013, '1.6': 2013, '1.7': 2014,
        '2.0': 2014, '2.1': 2014, '2.2': 2015, '2.3': 2015,
        '2.4': 2015, '2.5': 2015, '2.6': 2016, '2.7': 2016,
        '2.8': 2016, '2.9': 2017, '2.10': 2017, '2.11': 2017,
        '2.12': 2018, '3.0': 2018, '3.1': 2019, '4.0': 2019,
        '4.1': 2020, '4.2': 2020, '5.0': 2020, '5.1': 2020,
        '5.2': 2020, '6.0': 2021, '6.1': 2021, '6.2': 2022,
        '7.0': 2022, '7.1': 2022, '7.2': 2022, '8.0': 2023,
        '8.1': 2023, '8.2': 2023, '9.0': 2024, '9.1': 2024,
        '9.2': 2024, '10.0': 2025, '10.1': 2025, '10.2': 2025,
        '11.0': 2026,
    }
    for ver_str, ver_year in version_map.items():
        if ver_str in qemu_version:
            return ver_year
    return 2020

# ============================================================
# QEMU 可执行文件检测
# ============================================================
def get_qemu_exe(qemu_version: str, arch: str) -> Optional[Path]:
    qemu_dir = BASE_DIR / qemu_version
    if not qemu_dir.exists():
        for d in BASE_DIR.iterdir():
            if d.is_dir() and d.name.startswith("qemu"):
                if qemu_version.lower() in d.name.lower() or d.name.lower() in qemu_version.lower():
                    qemu_dir = d
                    break
        if not qemu_dir.exists():
            return None
    
    arch_map = {
        "x86_64": ["qemu-system-x86_64.exe", "qemu-system-x86_64", "qemu-system-x86_64w.exe"],
        "x86": ["qemu-system-i386.exe", "qemu-system-i386", "qemu-system-x86_64.exe", "qemu-system-x86_64"],
        "ARM64": ["qemu-system-aarch64.exe", "qemu-system-aarch64"],
        "ARM": ["qemu-system-arm.exe", "qemu-system-arm"],
        "RISC-V": ["qemu-system-riscv64.exe", "qemu-system-riscv64"],
        "RISC-V32": ["qemu-system-riscv32.exe", "qemu-system-riscv32"],
        "LoongArch": ["qemu-system-loongarch64.exe", "qemu-system-loongarch64"],
        "MIPS": ["qemu-system-mips.exe", "qemu-system-mips"],
        "MIPS64": ["qemu-system-mips64.exe", "qemu-system-mips64"],
        "PPC": ["qemu-system-ppc.exe", "qemu-system-ppc"],
        "PPC64": ["qemu-system-ppc64.exe", "qemu-system-ppc64"],
        "SPARC": ["qemu-system-sparc.exe", "qemu-system-sparc"],
        "SPARC64": ["qemu-system-sparc64.exe", "qemu-system-sparc64"],
        "S390X": ["qemu-system-s390x.exe", "qemu-system-s390x"],
        "Alpha": ["qemu-system-alpha.exe", "qemu-system-alpha"],
        "HPPA": ["qemu-system-hppa.exe", "qemu-system-hppa"],
        "SH4": ["qemu-system-sh4.exe", "qemu-system-sh4"],
        "XTENSA": ["qemu-system-xtensa.exe", "qemu-system-xtensa"],
        "M68K": ["qemu-system-m68k.exe", "qemu-system-m68k"],
        "MICROBLAZE": ["qemu-system-microblaze.exe", "qemu-system-microblaze"],
        "NIOS2": ["qemu-system-nios2.exe", "qemu-system-nios2"],
        "OR1K": ["qemu-system-or1k.exe", "qemu-system-or1k"],
        "CRIS": ["qemu-system-cris.exe", "qemu-system-cris"],
        "HEXAGON": ["qemu-system-hexagon.exe", "qemu-system-hexagon"],
        "AVR": ["qemu-system-avr.exe", "qemu-system-avr"],
        "RX": ["qemu-system-rx.exe", "qemu-system-rx"],
        "TRICORE": ["qemu-system-tricore.exe", "qemu-system-tricore"],
        "UNICORE32": ["qemu-system-unicore32.exe", "qemu-system-unicore32"],
    }
    
    exe_names = arch_map.get(arch, ["qemu-system-x86_64.exe", "qemu-system-x86_64"])
    
    for name in exe_names:
        exe = qemu_dir / name
        if exe.exists():
            return exe
    
    for exe in qemu_dir.glob("qemu-system-*"):
        if exe.is_file():
            return exe
    
    return None

# ============================================================
# 架构默认配置
# ============================================================
def get_arch_defaults(arch: str) -> dict:
    defaults = {
        "x86_64": {"machine": "q35", "cpu": "host", "vga": "virtio", "display": "gtk"},
        "x86": {"machine": "pc", "cpu": "qemu64", "vga": "std", "display": "gtk"},
        "ARM64": {"machine": "virt", "cpu": "cortex-a72", "vga": "virtio", "display": "gtk"},
        "ARM": {"machine": "virt", "cpu": "cortex-a15", "vga": "virtio", "display": "gtk"},
        "RISC-V": {"machine": "virt", "cpu": "rv64", "vga": "virtio", "display": "gtk"},
        "RISC-V32": {"machine": "virt", "cpu": "rv32", "vga": "virtio", "display": "gtk"},
        "LoongArch": {"machine": "virt", "cpu": "la64", "vga": "virtio", "display": "gtk"},
        "MIPS": {"machine": "malta", "cpu": "mips32r5", "vga": "std", "display": "gtk"},
        "MIPS64": {"machine": "malta", "cpu": "mips64r5", "vga": "std", "display": "gtk"},
        "PPC": {"machine": "mac99", "cpu": "G4", "vga": "std", "display": "gtk"},
        "PPC64": {"machine": "pseries", "cpu": "POWER9", "vga": "virtio", "display": "gtk"},
        "SPARC": {"machine": "SS-5", "cpu": "Fujitsu-MB86904", "vga": "cg3", "display": "gtk"},
        "SPARC64": {"machine": "sun4u", "cpu": "UltraSPARC-IIi", "vga": "cg3", "display": "gtk"},
        "Alpha": {"machine": "clipper", "cpu": "ev67", "vga": "none", "display": "gtk"},
        "HPPA": {"machine": "hppa", "cpu": "PA-7100", "vga": "none", "display": "gtk"},
        "S390X": {"machine": "s390-ccw-virtio", "cpu": "host", "vga": "none", "display": "none"},
        "SH4": {"machine": "r2d", "cpu": "sh4", "vga": "none", "display": "gtk"},
        "XTENSA": {"machine": "sim", "cpu": "dc232b", "vga": "none", "display": "gtk"},
        "TRICORE": {"machine": "tricore", "cpu": "tc27x", "vga": "none", "display": "none"},
        "AVR": {"machine": "arduino-uno", "cpu": "avr6", "vga": "none", "display": "none"},
        "RX": {"machine": "rx", "cpu": "rx600", "vga": "none", "display": "none"},
        "HEXAGON": {"machine": "sim", "cpu": "v67", "vga": "none", "display": "none"},
        "CRIS": {"machine": "axis-dev88", "cpu": "crisv32", "vga": "none", "display": "none"},
        "M68K": {"machine": "q800", "cpu": "68040", "vga": "none", "display": "gtk"},
        "MICROBLAZE": {"machine": "petalogix-s3adsp1800", "cpu": "microblaze", "vga": "none", "display": "gtk"},
        "NIOS2": {"machine": "10m50-ghrd", "cpu": "nios2", "vga": "none", "display": "none"},
        "OR1K": {"machine": "or1k-sim", "cpu": "or1k", "vga": "none", "display": "none"},
        "UNICORE32": {"machine": "pkuni", "cpu": "UniCore-II", "vga": "none", "display": "none"},
    }
    return defaults.get(arch, defaults["x86_64"])

# ============================================================
# 各参数生成函数（完整保留）
# ============================================================
def get_cpu_model(year: int, arch: str, config_cpu: str) -> str:
    arch_defaults = get_arch_defaults(arch)
    if year <= 2013:
        return "qemu32" if arch in ["x86", "x86_64"] else arch_defaults.get("cpu", "host")
    elif year <= 2016:
        return "qemu64" if arch in ["x86", "x86_64"] else arch_defaults.get("cpu", "host")
    else:
        return "host" if config_cpu == "host" else config_cpu

def get_machine_type(year: int, arch: str, config_machine: str) -> str:
    arch_defaults = get_arch_defaults(arch)
    if config_machine and config_machine != "auto":
        return config_machine
    return arch_defaults.get("machine", "q35") if year >= 2020 else arch_defaults.get("machine", "pc")

def get_vga_model(year: int, arch: str, config_vga: str) -> str:
    arch_defaults = get_arch_defaults(arch)
    if config_vga and config_vga != "auto":
        return config_vga
    if year <= 2013:
        return "cirrus" if arch in ["x86", "x86_64"] else arch_defaults.get("vga", "std")
    elif year <= 2016:
        return "std" if arch in ["x86", "x86_64"] else arch_defaults.get("vga", "std")
    else:
        return arch_defaults.get("vga", "virtio")

def get_sound_params(year: int, config_sound: str, os_type: str, arch: str, 
                     features: dict) -> List[str]:
    if config_sound == "none" or os_type == "Android" or arch not in ["x86", "x86_64"]:
        return []
    if year <= 2013:
        return ["-soundhw", "sb16"]
    elif year <= 2019:
        return ["-soundhw", "ac97"]
    else:
        if not features.get("audiodev", False):
            if config_sound == "ac97":
                return ["-soundhw", "ac97"]
            else:
                return ["-soundhw", "hda"]
        
        if config_sound == "ac97":
            return ["-audiodev", "wav,id=audio0", "-device", "AC97,audiodev=audio0"]
        elif config_sound == "sb16":
            return ["-audiodev", "wav,id=audio0", "-device", "sb16,audiodev=audio0"]
        else:
            return ["-audiodev", "wav,id=audio0", "-device", "intel-hda,audiodev=audio0"]

def get_disk_params(year: int, disk_path: Path, disk_format: str, interface: str, 
                    cache: str = "writeback", aio: str = "默认", 
                    discard: str = "默认", detect_zeroes: str = "默认",
                    readonly: bool = False) -> List[str]:
    drive_opts = f"file={disk_path},format={disk_format}"
    
    if interface == "ide":
        drive_opts += ",if=ide,index=0"
    elif interface == "sata":
        drive_opts += ",if=ide,index=0"
    elif interface == "virtio":
        drive_opts += ",if=virtio"
    elif interface == "scsi":
        drive_opts += ",if=scsi"
    elif interface == "nvme":
        drive_opts += ",if=nvme"
    else:
        drive_opts += f",if={interface}"
    
    if cache and cache != "默认":
        drive_opts += f",cache={cache}"
    if aio and aio != "默认":
        drive_opts += f",aio={aio}"
    if discard and discard != "默认":
        drive_opts += f",discard={discard}"
    if detect_zeroes and detect_zeroes != "默认":
        drive_opts += f",detect-zeroes={detect_zeroes}"
    if readonly:
        drive_opts += ",readonly=on"
    
    return ["-drive", drive_opts]

def get_network_params(year: int, nic_model: str, share_dir: str = "",
                       hostfwd: str = "", net_subnet: str = "",
                       net_dns: str = "", net_restrict: bool = False,
                       tap_interface: str = "", mac_address: str = "") -> List[str]:
    if tap_interface:
        netdev = f"tap,id=net0,ifname={tap_interface}"
        cmd = ["-netdev", netdev]
        if nic_model == "virtio":
            cmd.extend(["-device", "virtio-net-pci,netdev=net0"])
        else:
            cmd.extend(["-device", f"{nic_model},netdev=net0"])
        return cmd
    
    netdev = "user,id=net0"
    if share_dir and Path(share_dir).exists():
        netdev += f",smb={share_dir}"
    if hostfwd:
        for fwd in hostfwd.split(','):
            fwd = fwd.strip()
            if fwd:
                netdev += f",hostfwd={fwd}"
    if net_subnet:
        netdev += f",net={net_subnet}"
    if net_dns:
        netdev += f",dns={net_dns}"
    if net_restrict:
        netdev += ",restrict=on"
    
    cmd = ["-netdev", netdev]
    device = "virtio-net-pci" if nic_model == "virtio" else nic_model
    if mac_address:
        cmd.extend(["-device", f"{device},netdev=net0,mac={mac_address}"])
    else:
        cmd.extend(["-device", f"{device},netdev=net0"])
    return cmd

def get_accel_params(year: int, accel: str, force_tcg: bool = False) -> List[str]:
    if force_tcg:
        return ["-accel", "tcg"]
    if accel == "tcg":
        return []
    if year <= 2016:
        return ["-enable-kvm"]
    else:
        return ["-accel", accel]

def get_mouse_params(year: int, arch: str, enable_usb: bool, 
                     usb_tablet: bool = True, 
                     no_mouse_integration: bool = False) -> List[str]:
    if not enable_usb and usb_tablet:
        enable_usb = True
    
    if not enable_usb:
        return []
    
    if no_mouse_integration:
        return ["-usb", "-device", "usb-tablet", "-device", "usb-mouse"]
    
    if usb_tablet:
        if year <= 2016 and arch in ["x86", "x86_64"]:
            return ["-device", "piix3-usb-uhci", "-device", "usb-tablet"]
        return ["-usb", "-device", "usb-tablet"]
    
    if arch not in ["x86", "x86_64"]:
        return ["-usb", "-device", "usb-mouse"]
    if year <= 2013:
        return ["-device", "isa-mouse"]
    return ["-usb", "-device", "usb-mouse"]

def get_display_params(year: int, arch: str, display: str, vnc_port: str, 
                       resolution: str, vnc_password: str = "",
                       spice_port: str = "", spice_password: str = "",
                       features: dict = None) -> List[str]:
    if features is None:
        features = {}
    
    arch_defaults = get_arch_defaults(arch)
    
    if display == "none" or arch_defaults.get("display") == "none":
        return ["-nographic"]
    
    if spice_port:
        spice_opts = f"port={spice_port},disable-ticketing=on"
        if spice_password:
            spice_opts = f"port={spice_port},password={spice_password}"
        return ["-spice", spice_opts, "-vga", "qxl"]
    
    if vnc_port:
        if vnc_password:
            return ["-vnc", f"{vnc_port},password={vnc_password}"]
        return ["-vnc", vnc_port]
    
    if year <= 2013:
        return ["-vnc", ":0"]
    
    if year <= 2019:
        if resolution and resolution != "自定义" and features.get("window_size", False):
            return ["-display", f"gtk,window-size={resolution}"]
        return ["-display", "gtk"]
    
    gtk_params = ["-display", "gtk"]
    
    if resolution and resolution != "自定义" and features.get("window_size", False):
        gtk_params[1] += f",window-size={resolution}"
    
    if features.get("grab_on_click", False):
        gtk_params[1] += ",grab-on-click=on"
    
    return gtk_params

def get_host_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        pass
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            return ip
    except:
        pass
    return "10.0.2.2"

def get_usb_passthrough_params(devices: List[str]) -> List[str]:
    if not devices:
        return []
    params = []
    for device in devices:
        if device.strip():
            params.extend(["-device", f"usb-host,{device}"])
    if params:
        params.insert(0, "-usb")
    return params

def detect_removable_drives() -> List[dict]:
    drives = []
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ['wmic', 'logicaldisk', 'where', 'DriveType=2', 'get', 'DeviceID,Size,VolumeName'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return drives

            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line or 'DeviceID' in line:
                    continue
                parts = line.split()
                if not parts:
                    continue
                drive = parts[0].strip()
                if drive and ':' in drive:
                    size = parts[1].strip() if len(parts) > 1 else "未知"
                    name = ' '.join(parts[2:]) if len(parts) > 2 else "可移动磁盘"
                    drives.append({
                        "device": drive,
                        "size": size,
                        "name": name or f"可移动磁盘 ({drive})"
                    })
        else:
            for dev in glob.glob('/dev/sd*'):
                if dev.endswith(('1', '2', '3', '4', '5', '6', '7', '8')):
                    continue
                try:
                    result = subprocess.run(['lsblk', '-o', 'NAME,RM,MOUNTPOINT', dev], 
                                           capture_output=True, text=True)
                    if '1' in result.stdout:
                        drives.append({
                            "device": dev,
                            "size": "未知",
                            "name": f"可移动磁盘 ({dev})"
                        })
                except:
                    pass
    except Exception as e:
        print(f"⚠️ 扫描可移动磁盘失败: {e}")
    return drives

# ============================================================
# 构建命令
# ============================================================
def build_command(config: dict, override_usb_tablet: Optional[bool] = None) -> Tuple[Optional[List[str]], Optional[str]]:
    vm_name = config.get('name', 'vm')
    arch = config.get('arch', 'x86_64')
    qemu_ver = config.get('qemu_version', '')
    year = get_qemu_year(qemu_ver)
    os_type = config.get('os_type', '')
    os_version = config.get('os_version', '')

    qemu_exe = get_qemu_exe(qemu_ver, arch)
    if not qemu_exe:
        return None, f"当前 QEMU 版本不支持架构: {arch}"

    qemu_features = get_qemu_features(qemu_exe)
    arch_defaults = get_arch_defaults(arch)
    
    cmd = [str(qemu_exe)]

    # ===== 内存 =====
    memory = config.get('memory', 1024)
    cmd.extend(["-m", str(memory)])

    # ===== CPU =====
    cpu = config.get('cpu', 2)
    threads = config.get('smp_threads', 1)
    sockets = config.get('smp_sockets', 1)
    cmd.extend(["-smp", f"cores={cpu},threads={threads},sockets={sockets}"])

    # ===== CPU 型号 =====
    cpu_model = get_cpu_model(year, arch, config.get('cpu_model', 'host'))
    cpu_flags = config.get('cpu_flags', '')
    if cpu_flags:
        cmd.extend(["-cpu", f"{cpu_model},{cpu_flags}"])
    else:
        cmd.extend(["-cpu", cpu_model])

    # ===== 内存高级 =====
    if config.get('mem_prealloc', False):
        cmd.append("-mem-prealloc")
    if config.get('hugepages', False):
        if sys.platform == "win32":
            print("⚠️ Windows 不支持大页内存，忽略 -mem-path")
        else:
            cmd.extend(["-mem-path", "/dev/hugepages"])

    # ===== NUMA =====
    numa_config = config.get('numa_config', '')
    if numa_config:
        cmd.extend(["-numa", numa_config])

    # ===== 磁盘 =====
    disks = config.get('disks', [])
    if disks:
        for disk in disks:
            disk_path = Path(disk['path'])
            if not disk_path.exists():
                print(f"⚠️ 磁盘文件不存在: {disk_path}")
                continue
            disk_params = get_disk_params(
                year, disk_path, disk.get('format', 'qcow2'),
                disk.get('interface', 'sata'),
                cache=disk.get('cache', config.get('cache', 'writeback')),
                aio=config.get('aio', '默认'),
                discard=config.get('discard', '默认'),
                detect_zeroes=config.get('detect_zeroes', '默认'),
                readonly=disk.get('readonly', config.get('disk_readonly', False))
            )
            cmd.extend(disk_params)
    else:
        disk_path = VMS_DIR / vm_name / f"disk.{config.get('disk_format', 'qcow2')}"
        disk_interface = config.get('disk_interface', 'sata')
        disk_format = config.get('disk_format', 'qcow2')
        if disk_path.exists():
            disk_params = get_disk_params(
                year, disk_path, disk_format, disk_interface,
                cache=config.get('cache', 'writeback'),
                aio=config.get('aio', '默认'),
                discard=config.get('discard', '默认'),
                detect_zeroes=config.get('detect_zeroes', '默认'),
                readonly=config.get('disk_readonly', False)
            )
            cmd.extend(disk_params)

    # ===== 快照模式 =====
    if config.get('snapshot_mode', False):
        cmd.append("-snapshot")

    # ===== 启动顺序 + ISO/U盘 =====
    boot_order = config.get('boot_order', 'cdrom')
    boot_iso = config.get('boot_iso', '')
    usb_disk_mounted = config.get('usb_disk_mounted', '')
    driver_iso = config.get('driver_iso', '')
    share_dir = config.get('share_dir', '') if config.get('share_enabled', False) else ''

    if driver_iso and Path(driver_iso).exists():
        cmd.extend(["-drive", f"file={driver_iso},format=raw,if=ide,media=cdrom,index=1"])

    if boot_order == "disk":
        cmd.extend(["-boot", "c"])
        if usb_disk_mounted and Path(usb_disk_mounted).exists():
            cmd.extend(["-drive", f"file={usb_disk_mounted},format=raw,if=ide,index=3"])
    else:
        cmd.extend(["-boot", "d"])
        if boot_iso and Path(boot_iso).exists():
            cmd.extend(["-drive", f"file={boot_iso},format=raw,if=ide,media=cdrom,index=2"])

    # ===== 启动菜单 =====
    if config.get('boot_menu', False):
        cmd.extend(["-boot", "menu=on"])

    # ===== 启动一次 =====
    boot_once = config.get('boot_once', '')
    if boot_once:
        cmd.extend(["-boot", f"once={boot_once}"])

    # ===== 机器类型 + ACPI =====
    machine = get_machine_type(year, arch, config.get('machine_type', 'auto'))
    acpi = config.get('acpi', True)
    if acpi:
        cmd.extend(["-machine", machine])
    else:
        if year >= 2017:
            cmd.extend(["-machine", f"{machine},acpi=off"])
        else:
            cmd.extend(["-machine", machine])
            cmd.extend(["-no-acpi"])

    # ===== HPET =====
    if config.get('no_hpet_adv', False) and year >= 2017:
        cmd.extend(["-no-hpet"])
    elif config.get('no_hpet', False) and year >= 2017:
        cmd.extend(["-no-hpet"])

    # ===== 显卡 =====
    vga = get_vga_model(year, arch, config.get('vga', 'auto'))
    if vga != "none":
        cmd.extend(["-vga", vga])

    # ===== 显示 =====
    display = config.get('display', 'gtk')
    vnc_port = config.get('vnc_port', '')
    resolution = config.get('resolution', '')
    vnc_password = config.get('vnc_password', '')
    spice_port = config.get('spice_port', '')
    spice_password = config.get('spice_password', '')
    cmd.extend(get_display_params(year, arch, display, vnc_port, resolution, 
                                   vnc_password, spice_port, spice_password,
                                   qemu_features))

    # ===== OpenGL 加速 =====
    opengl = config.get('opengl', False)
    if opengl and year >= 2020 and display != "none" and not vnc_port and not spice_port:
        if qemu_features.get("gl_on", False):
            for i, arg in enumerate(cmd):
                if arg == "-display" and i + 1 < len(cmd) and cmd[i + 1].startswith("gtk"):
                    if "gl" not in cmd[i + 1]:
                        cmd[i + 1] += ",gl=on"
                    break

    # ===== 声卡 =====
    sound = config.get('sound', 'hda')
    cmd.extend(get_sound_params(year, sound, os_type, arch, qemu_features))

    # ===== 鼠标 =====
    usb_enabled = config.get('usb', True)
    if override_usb_tablet is not None:
        usb_tablet = override_usb_tablet
    else:
        usb_tablet = config.get('usb_tablet', True)
    no_mouse_integration = config.get('no_mouse_integration', False)
    cmd.extend(get_mouse_params(year, arch, usb_enabled, usb_tablet, no_mouse_integration))

    # ===== 网络 =====
    nic_model = config.get('nic_model', 'e1000')
    hostfwd = config.get('hostfwd', '')
    net_subnet = config.get('net_subnet', '')
    net_dns = config.get('net_dns', '')
    net_restrict = config.get('net_restrict', False)
    tap_interface = config.get('tap_interface', '')
    mac_address = config.get('mac_address', '')
    cmd.extend(get_network_params(year, nic_model, share_dir, hostfwd, 
                                   net_subnet, net_dns, net_restrict,
                                   tap_interface, mac_address))

    # ===== 加速 =====
    accel = config.get('accel', 'tcg')
    force_tcg = config.get('force_tcg', False)
    cmd.extend(get_accel_params(year, accel, force_tcg))

    # ===== USB 直通 =====
    usb_passthrough = config.get('usb_passthrough', [])
    cmd.extend(get_usb_passthrough_params(usb_passthrough))

    # ===== 内核镜像 =====
    kernel_iso = config.get('kernel_iso', '')
    if kernel_iso and Path(kernel_iso).exists():
        cmd.extend(["-kernel", kernel_iso])
        if arch in ["ARM64", "ARM"]:
            cmd.extend(["-append", "console=ttyAMA0 root=/dev/vda"])
        elif arch in ["RISC-V", "RISC-V32"]:
            cmd.extend(["-append", "console=ttyS0 root=/dev/vda"])
        elif arch == "LoongArch":
            cmd.extend(["-append", "console=ttyS0 root=/dev/vda"])
        else:
            cmd.extend(["-append", "root=/dev/sda"])

    # ===== BIOS =====
    bios_file = config.get('bios_file', '')
    if bios_file and Path(bios_file).exists():
        cmd.extend(["-bios", bios_file])

    # ===== 日志 =====
    log_file = config.get('log_file', '')
    if log_file:
        cmd.extend(["-D", log_file])

    # ===== 调试 =====
    debug_level = config.get('debug_level', '默认')
    if debug_level and debug_level != "默认":
        cmd.extend(["-d", debug_level])

    # ===== QMP =====
    qmp_socket = config.get('qmp_socket', '')
    if qmp_socket and qemu_features.get("qmp", False):
        cmd.extend(["-qmp", f"unix:{qmp_socket},server,nowait"])

    # ===== Monitor =====
    if config.get('monitor_stdio', False):
        cmd.extend(["-monitor", "stdio"])

    # ===== 不重启 / 不关机 =====
    if config.get('no_reboot', False) and qemu_features.get("no_reboot", False):
        cmd.append("-no-reboot")
    elif config.get('no_reboot', False):
        print("⚠️ 当前 QEMU 不支持 -no-reboot，忽略")

    if config.get('no_shutdown', False) and qemu_features.get("no_shutdown", False):
        cmd.append("-no-shutdown")
    elif config.get('no_shutdown', False):
        print("⚠️ 当前 QEMU 不支持 -no-shutdown，忽略")

    # ===== 沙箱 =====
    if config.get('sandbox', False) and qemu_features.get("sandbox", False):
        cmd.extend(["-sandbox", "on"])
    elif config.get('sandbox', False):
        print("⚠️ 当前 QEMU 不支持 -sandbox，忽略")

    # ===== RTC =====
    rtc_base = config.get('rtc_base', '')
    if rtc_base:
        cmd.extend(["-rtc", f"base={rtc_base}"])

    # ===== 随机种子 =====
    seed_value = config.get('seed_value', '')
    if seed_value:
        cmd.extend(["-seed", seed_value])

    # ===== 额外参数 =====
    extra_args = config.get('extra_args', '')
    if extra_args.strip():
        try:
            cmd.extend(shlex.split(extra_args))
        except ValueError as e:
            print(f"⚠️ 解析 extra_args 失败: {e}，使用 split() fallback")
            cmd.extend(extra_args.split())

    extra_advanced = config.get('extra_advanced_args', '')
    if extra_advanced.strip():
        for line in extra_advanced.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    cmd.extend(shlex.split(line))
                except ValueError as e:
                    print(f"⚠️ 解析 extra_advanced_args 失败: {e}，跳过: {line}")

    return cmd, None

# ============================================================
# VMware风格主窗口
# ============================================================
class LauncherWindow(QMainWindow):
    def __init__(self, vm_name: str = None):
        super().__init__()
        self.vm_name = vm_name
        self.config = None
        self.cmd = None
        self.process: Optional[QProcess] = None
        self.log_buffer = []
        self.is_admin = is_admin()
        self.http_process = None
        self.override_usb_tablet = None

        self.init_ui()
        
        fixes = auto_fix_all_vms()
        if fixes:
            msg = "🔧 以下虚拟机配置已自动修复：\n\n"
            for vm_name, fix_list in fixes.items():
                msg += f"📁 {vm_name}:\n"
                for fix in fix_list:
                    msg += f"  {fix}\n"
                msg += "\n"
            msg += "✅ 所有修复已自动完成"
            QMessageBox.information(self, "配置修复", msg)
        
        if vm_name:
            self.load_config(vm_name)
            self.update_display()

        self.refresh_running_list()

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_running_list)
        self.refresh_timer.start(2000)

        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.update_performance)
        self.monitor_timer.start(1000)

        self.log_flush_timer = QTimer()
        self.log_flush_timer.timeout.connect(self.flush_log)
        self.log_flush_timer.start(30000)

    def init_ui(self):
        # 大字体微软雅黑
        font = QFont("Microsoft YaHei", 11)
        self.setFont(font)
        
        self.setWindowTitle(f"🚀 Mikan QEMU 启动器 - {self.vm_name if self.vm_name else '选择虚拟机'}")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 750)

        # VMware风格深色主题
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: #f0f0f0;
            }
            QMenuBar {
                background-color: #3c3c3c;
                color: #f0f0f0;
                border-bottom: 1px solid #555;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QMenuBar::item:selected {
                background-color: #5a5a5a;
            }
            QMenu {
                background-color: #3c3c3c;
                color: #f0f0f0;
                border: 1px solid #555;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QMenu::item:selected {
                background-color: #5a5a5a;
            }
            QToolBar {
                background-color: #3c3c3c;
                border: none;
                spacing: 4px;
                padding: 4px 8px;
            }
            QToolButton {
                background-color: transparent;
                color: #f0f0f0;
                border: none;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }
            QToolButton:hover {
                background-color: #5a5a5a;
            }
            QToolButton:pressed {
                background-color: #4a4a4a;
            }
            QToolButton:disabled {
                color: #666;
            }
            QSplitter::handle {
                background-color: #555;
            }
            QListWidget {
                background-color: #2b2b2b;
                color: #f0f0f0;
                border: none;
                outline: none;
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #5a5a5a;
            }
            QListWidget::item:hover {
                background-color: #3c3c3c;
            }
            QTabWidget::pane {
                background-color: #2b2b2b;
                border: 1px solid #555;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #aaa;
                padding: 10px 20px;
                border: 1px solid #555;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }
            QTabBar::tab:selected {
                background-color: #2b2b2b;
                color: #f0f0f0;
            }
            QTabBar::tab:hover {
                background-color: #4a4a4a;
            }
            QGroupBox {
                color: #f0f0f0;
                border: 1px solid #555;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 10px;
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px;
                color: #aaa;
            }
            QLabel {
                color: #f0f0f0;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #3c3c3c;
                color: #f0f0f0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border-color: #7a7a7a;
            }
            QLineEdit:disabled {
                color: #888;
            }
            QPushButton {
                background-color: #5a5a5a;
                color: #f0f0f0;
                border: none;
                border-radius: 4px;
                padding: 8px 18px;
                font-weight: bold;
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }
            QPushButton:hover {
                background-color: #6a6a6a;
            }
            QPushButton:pressed {
                background-color: #4a4a4a;
            }
            QPushButton:disabled {
                background-color: #3a3a3a;
                color: #666;
            }
            QCheckBox {
                color: #f0f0f0;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 1px solid #555;
                background-color: #3c3c3c;
            }
            QCheckBox::indicator:checked {
                background-color: #5a7a5a;
                border-color: #5a7a5a;
            }
            QScrollBar:vertical {
                background-color: #2b2b2b;
                width: 14px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #5a5a5a;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #6a6a6a;
            }
            QScrollBar:horizontal {
                background-color: #2b2b2b;
                height: 14px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background-color: #5a5a5a;
                border-radius: 6px;
                min-width: 20px;
            }
            QStatusBar {
                background-color: #2b2b2b;
                color: #888;
                border-top: 1px solid #555;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QMessageBox {
                background-color: #2b2b2b;
                color: #f0f0f0;
            }
            QMessageBox QPushButton {
                min-width: 80px;
                padding: 8px 20px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #555;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #7a7a7a;
                width: 18px;
                height: 18px;
                border-radius: 9px;
                margin: -6px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #9a9a9a;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 8, 12, 12)

        # ===== 顶部：虚拟机选择 + 状态 =====
        top_widget = QWidget()
        top_widget.setStyleSheet("background-color: #3c3c3c; border-radius: 6px;")
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(12, 8, 12, 8)

        top_layout.addWidget(QLabel("虚拟机:"))

        self.vm_combo = QComboBox()
        self.vm_combo.setMinimumHeight(32)
        self.vm_combo.setMinimumWidth(200)
        self.vm_combo.currentTextChanged.connect(self.on_vm_selected)
        top_layout.addWidget(self.vm_combo, 1)

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedWidth(40)
        self.refresh_btn.clicked.connect(self.refresh_vm_list)
        top_layout.addWidget(self.refresh_btn)

        top_layout.addStretch()

        self.vm_status_label = QLabel("● 未运行")
        self.vm_status_label.setStyleSheet("color: #666; font-size: 13px;")
        top_layout.addWidget(self.vm_status_label)

        admin_status = QLabel("✅ 管理员" if self.is_admin else "⚠️ 普通")
        admin_status.setStyleSheet("color: #2e7d32; font-size: 11px; padding: 2px 10px; background: #e8f5e9; border-radius: 10px;" if self.is_admin else "color: #888; font-size: 11px; padding: 2px 10px; background: #3a3a3a; border-radius: 10px;")
        top_layout.addWidget(admin_status)

        layout.addWidget(top_widget)

        # ===== 主分割 =====
        splitter = QSplitter(Qt.Horizontal)

        # -------- 左侧面板 --------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(6)

        # 配置信息
        self.config_group = QGroupBox("📋 配置信息")
        self.config_layout = QVBoxLayout(self.config_group)
        left_layout.addWidget(self.config_group)

        # 架构信息
        self.arch_info_label = QLabel("🏷️ 架构: x86_64")
        self.arch_info_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px 8px; background: #3a3a3a; border-radius: 6px;")
        left_layout.addWidget(self.arch_info_label)

        # 鼠标模式
        mouse_layout = QHBoxLayout()
        self.mouse_mode_check = QCheckBox("🖱️ 绝对坐标 (USB Tablet)")
        self.mouse_mode_check.setChecked(True)
        self.mouse_mode_check.setToolTip("勾选 = 绝对坐标（不飘）\n取消 = 相对坐标（PS/2 鼠标）")
        self.mouse_mode_check.stateChanged.connect(self.on_mouse_mode_changed)
        self.mouse_mode_check.setStyleSheet("""
            QCheckBox {
                padding: 4px 8px;
                background: #3a3a3a;
                border-radius: 6px;
            }
            QCheckBox:hover { background: #4a4a4a; }
        """)
        mouse_layout.addWidget(self.mouse_mode_check)

        self.mouse_status_label = QLabel("")
        self.mouse_status_label.setStyleSheet("color: #888; font-size: 10px;")
        mouse_layout.addWidget(self.mouse_status_label)
        mouse_layout.addStretch()
        left_layout.addLayout(mouse_layout)

        # U盘状态
        self.usb_status_label = QLabel("💾 U盘: 未挂载")
        self.usb_status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px 8px; background: #3a3a3a; border-radius: 6px;")
        left_layout.addWidget(self.usb_status_label)

        # QEMU命令
        self.cmd_group = QGroupBox("📖 QEMU 命令")
        cmd_layout = QVBoxLayout(self.cmd_group)
        self.cmd_text = QTextEdit()
        self.cmd_text.setFont(QFont("Consolas", 10))
        self.cmd_text.setReadOnly(True)
        self.cmd_text.setMaximumHeight(100)
        self.cmd_text.setStyleSheet("background-color: #1e1e1e; color: #00ff00; border: 1px solid #555;")
        cmd_layout.addWidget(self.cmd_text)
        left_layout.addWidget(self.cmd_group)

        # 快照
        snap_group = QGroupBox("📸 快照")
        snap_layout = QVBoxLayout(snap_group)

        snap_mode_layout = QHBoxLayout()
        snap_mode_layout.addWidget(QLabel("方案:"))
        self.snapshot_mode_combo = QComboBox()
        self.snapshot_mode_combo.setMinimumHeight(28)
        self.snapshot_mode_combo.addItems([
            "❄️ 冷快照 (复制文件)",
            "🔥 内部快照 (savevm)",
            "🔥 外部快照 (blockdev)"
        ])
        snap_mode_layout.addWidget(self.snapshot_mode_combo, 1)
        snap_layout.addLayout(snap_mode_layout)

        snap_row1 = QHBoxLayout()
        snap_row1.addWidget(QLabel("快照名:"))
        self.snap_name_edit = QLineEdit()
        self.snap_name_edit.setPlaceholderText("输入快照名称")
        snap_row1.addWidget(self.snap_name_edit, 1)
        self.create_snap_btn = QPushButton("📸 创建")
        self.create_snap_btn.clicked.connect(self.create_snapshot)
        snap_row1.addWidget(self.create_snap_btn)
        snap_layout.addLayout(snap_row1)

        snap_row2 = QHBoxLayout()
        self.snap_list_combo = QComboBox()
        self.snap_list_combo.setMinimumHeight(28)
        snap_row2.addWidget(self.snap_list_combo, 1)
        self.restore_snap_btn = QPushButton("↩️ 恢复")
        self.restore_snap_btn.clicked.connect(self.restore_snapshot)
        snap_row2.addWidget(self.restore_snap_btn)
        self.delete_snap_btn = QPushButton("🗑️ 删除")
        self.delete_snap_btn.clicked.connect(self.delete_snapshot)
        snap_row2.addWidget(self.delete_snap_btn)
        snap_layout.addLayout(snap_row2)

        left_layout.addWidget(snap_group)

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.launch_btn = QPushButton("▶️ 启动")
        self.launch_btn.setMinimumHeight(40)
        self.launch_btn.setMinimumWidth(90)
        self.launch_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #3a3a3a; color: #666; }
        """)
        self.launch_btn.clicked.connect(self.launch)
        btn_layout.addWidget(self.launch_btn)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setMinimumWidth(90)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover { background-color: #d32f2f; }
            QPushButton:disabled { background-color: #3a3a3a; color: #666; }
        """)
        self.stop_btn.clicked.connect(self.stop_vm)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        self.kill_btn = QPushButton("💀 强制终止")
        self.kill_btn.setMinimumHeight(40)
        self.kill_btn.setMinimumWidth(90)
        self.kill_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff5722;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover { background-color: #e64a19; }
            QPushButton:disabled { background-color: #3a3a3a; color: #666; }
        """)
        self.kill_btn.clicked.connect(self.kill_vm)
        self.kill_btn.setEnabled(False)
        btn_layout.addWidget(self.kill_btn)

        btn_layout.addStretch()

        self.copy_cmd_btn = QPushButton("📋 复制命令")
        self.copy_cmd_btn.setMinimumHeight(40)
        self.copy_cmd_btn.clicked.connect(self.copy_command)
        btn_layout.addWidget(self.copy_cmd_btn)

        left_layout.addLayout(btn_layout)

        # U盘操作
        usb_layout = QHBoxLayout()
        self.usb_btn = QPushButton("💾 挂载 U盘 + HTTP")
        self.usb_btn.setMinimumHeight(32)
        self.usb_btn.setStyleSheet("background-color: #2196F3; color: white;")
        self.usb_btn.clicked.connect(self.show_usb_dialog)
        usb_layout.addWidget(self.usb_btn)

        self.usb_remove_btn = QPushButton("🗑️ 移除 U盘")
        self.usb_remove_btn.setMinimumHeight(32)
        self.usb_remove_btn.setStyleSheet("background-color: #ff9800; color: white;")
        self.usb_remove_btn.clicked.connect(self.remove_usb)
        usb_layout.addWidget(self.usb_remove_btn)

        self.stop_http_btn = QPushButton("⏹ 停止 HTTP")
        self.stop_http_btn.setMinimumHeight(32)
        self.stop_http_btn.setStyleSheet("background-color: #9e9e9e; color: white;")
        self.stop_http_btn.clicked.connect(self.stop_http_server)
        usb_layout.addWidget(self.stop_http_btn)

        usb_layout.addStretch()
        left_layout.addLayout(usb_layout)

        left_layout.addStretch()

        # -------- 右侧面板 --------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(6)

        # 运行中的虚拟机
        running_group = QGroupBox("▶️ 运行中的虚拟机")
        running_layout = QVBoxLayout(running_group)
        self.running_list = QListWidget()
        self.running_list.setMaximumHeight(120)
        self.running_list.itemDoubleClicked.connect(self.switch_to_vm)
        running_layout.addWidget(self.running_list)
        right_layout.addWidget(running_group)

        # 日志
        log_group = QGroupBox("📝 QEMU 日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #555;")
        log_layout.addWidget(self.log_text)
        right_layout.addWidget(log_group, 1)

        # 性能监控
        perf_group = QGroupBox("📊 性能监控")
        perf_layout = QVBoxLayout(perf_group)
        self.perf_text = QLabel("等待启动...")
        self.perf_text.setStyleSheet("font-family: Consolas; font-size: 12px; color: #aaa; padding: 4px;")
        perf_layout.addWidget(self.perf_text)
        right_layout.addWidget(perf_group)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([500, 600])

        layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        self.refresh_vm_list()

    def refresh_vm_list(self):
        """刷新虚拟机列表"""
        self.vm_combo.clear()
        if VMS_DIR.exists():
            for vm_dir in VMS_DIR.iterdir():
                if vm_dir.is_dir() and (vm_dir / "config.json").exists():
                    self.vm_combo.addItem(vm_dir.name)
        if self.vm_combo.count() > 0:
            if self.vm_name and self.vm_combo.findText(self.vm_name) >= 0:
                self.vm_combo.setCurrentText(self.vm_name)
            else:
                self.vm_combo.setCurrentIndex(0)

    def on_vm_selected(self, name: str):
        """虚拟机选择"""
        if name:
            self.vm_name = name
            self.setWindowTitle(f"🚀 Mikan QEMU 启动器 - {name}")
            self.load_config(name)
            self.update_display()

    def load_config(self, vm_name: str):
        """加载配置"""
        config_file = VMS_DIR / vm_name / "config.json"
        if not config_file.exists():
            self.status_bar.showMessage(f"❌ 配置文件不存在: {config_file}")
            return
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        if self.override_usb_tablet is not None:
            self.cmd, error = build_command(self.config, override_usb_tablet=self.override_usb_tablet)
        else:
            self.cmd, error = build_command(self.config)
        if error:
            self.status_bar.showMessage(f"❌ {error}")
        
        if self.config:
            config_tablet = self.config.get('usb_tablet', True)
            if self.override_usb_tablet is None:
                self.mouse_mode_check.setChecked(config_tablet)
                if config_tablet:
                    self.mouse_status_label.setText("✅ 绝对坐标")
                    self.mouse_status_label.setStyleSheet("color: #6a9a6a; font-size: 10px;")
                else:
                    self.mouse_status_label.setText("🔄 相对坐标")
                    self.mouse_status_label.setStyleSheet("color: #ff6b6b; font-size: 10px;")

    def update_display(self):
        """更新显示"""
        if not self.config or not self.cmd:
            return
        year = get_qemu_year(self.config.get('qemu_version', ''))
        arch = self.config.get('arch', 'x86_64')
        os_type = self.config.get('os_type', '')
        os_version = self.config.get('os_version', '')
        boot_order = self.config.get('boot_order', 'cdrom')
        
        arch_names = {
            "x86_64": "x86_64", "x86": "x86",
            "ARM64": "ARM64", "ARM": "ARM",
            "RISC-V": "RISC-V", "RISC-V32": "RISC-V32",
            "LoongArch": "LoongArch",
        }
        arch_display = arch_names.get(arch, arch)
        self.arch_info_label.setText(f"🏷️ 架构: {arch_display}")

        config_text = ""
        config_text += f"系统: {os_type} {os_version}\n"
        config_text += f"架构: {arch_display}\n"
        config_text += f"内存: {self.config.get('memory', 1024)} MB\n"
        config_text += f"CPU: {self.config.get('cpu', 2)} 核\n"
        config_text += f"磁盘: {self.config.get('disk_size', 16)} GB\n"
        config_text += f"启动顺序: {boot_order}\n"
        config_text += f"QEMU: {self.config.get('qemu_version', '未知')} ({year}年)"

        usb_disk = self.config.get('usb_disk_mounted', '')
        boot_iso = self.config.get('boot_iso', '')
        driver_iso = self.config.get('driver_iso', '')

        if usb_disk:
            self.usb_status_label.setText(f"💾 U盘已挂载 (IDE3): {Path(usb_disk).name}")
            self.usb_status_label.setStyleSheet("color: #6a9a6a; font-size: 11px; padding: 4px 8px; background: #2a3a2a; border-radius: 6px;")
            config_text += f"\n💾 U盘已挂载 (IDE3): {usb_disk}"
        else:
            self.usb_status_label.setText("💾 U盘: 未挂载")
            self.usb_status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px 8px; background: #3a3a3a; border-radius: 6px;")

        if boot_iso and Path(boot_iso).exists():
            config_text += f"\n💿 主ISO (IDE2): {Path(boot_iso).name}"
        if driver_iso and Path(driver_iso).exists():
            config_text += f"\n💿 驱动ISO (IDE1): {Path(driver_iso).name}"

        # 更新配置显示
        for child in self.config_group.findChildren(QWidget):
            child.deleteLater()
        new_config_layout = QVBoxLayout(self.config_group)
        for line in config_text.split('\n'):
            lbl = QLabel(line)
            lbl.setStyleSheet("font-size: 11px; color: #ccc;")
            new_config_layout.addWidget(lbl)

        self.cmd_text.setPlainText(" ".join(self.cmd))
        self.cmd_text.moveCursor(QTextCursor.Start)

        self.refresh_snapshot_list()

    def on_mouse_mode_changed(self, state):
        """鼠标模式切换"""
        if not self.config:
            return
        if state == Qt.Checked:
            self.override_usb_tablet = True
            self.mouse_status_label.setText("✅ 绝对坐标")
            self.mouse_status_label.setStyleSheet("color: #6a9a6a; font-size: 10px;")
        else:
            self.override_usb_tablet = False
            self.mouse_status_label.setText("🔄 相对坐标")
            self.mouse_status_label.setStyleSheet("color: #ff6b6b; font-size: 10px;")
        
        self.cmd, error = build_command(self.config, override_usb_tablet=self.override_usb_tablet)
        if error:
            self.status_bar.showMessage(f"❌ {error}")
        else:
            self.update_display()
            self.status_bar.showMessage(f"🖱️ 鼠标模式: {'绝对坐标' if state == Qt.Checked else '相对坐标'}")

    # ============================================================
    # 以下所有功能方法完整保留（与原来完全相同）
    # ============================================================
    
    def refresh_running_list(self):
        """刷新运行列表"""
        global running_vms
        self.running_list.clear()
        running_vms_cleaned = {}
        for name, proc in running_vms.items():
            if proc.state() == QProcess.Running:
                running_vms_cleaned[name] = proc
                self.running_list.addItem(f"▶ {name} (PID: {proc.processId()})")
            else:
                proc.waitForFinished(100)
        running_vms = running_vms_cleaned
        if len(running_vms) == 0:
            self.running_list.addItem("(无运行中的虚拟机)")

        if self.vm_name and self.vm_name in running_vms:
            self.stop_btn.setEnabled(True)
            self.kill_btn.setEnabled(True)
            self.launch_btn.setEnabled(False)
            self.vm_status_label.setText("● 运行中")
            self.vm_status_label.setStyleSheet("color: #6a9a6a; font-size: 13px;")
            self.status_bar.showMessage(f"▶ {self.vm_name} 正在运行")
        else:
            self.stop_btn.setEnabled(False)
            self.kill_btn.setEnabled(False)
            self.launch_btn.setEnabled(True)
            self.vm_status_label.setText("● 未运行")
            self.vm_status_label.setStyleSheet("color: #666; font-size: 13px;")

    def switch_to_vm(self, item):
        """切换到虚拟机"""
        text = item.text()
        if "(" in text and ")" in text:
            name = text.split("▶")[1].split("(")[0].strip()
            if name in running_vms:
                self.vm_combo.setCurrentText(name)

    def launch(self):
        """启动虚拟机"""
        global running_vms
        vm_name = self.vm_combo.currentText()
        if not vm_name:
            QMessageBox.warning(self, "提示", "请选择虚拟机")
            return
        self.load_config(vm_name)
        if not self.cmd:
            return
        if vm_name in running_vms:
            QMessageBox.warning(self, "提示", f"虚拟机 {vm_name} 已在运行中")
            return

        self.launch_btn.setEnabled(False)
        self.status_bar.showMessage("🚀 正在启动...")

        try:
            qemu_exe = Path(self.cmd[0])
            qemu_dir = qemu_exe.parent
            args = self.cmd[1:]

            self.process = QProcess()
            self.process.setProgram(str(qemu_exe))
            self.process.setArguments(args)
            self.process.setWorkingDirectory(str(qemu_dir))

            self.process.readyReadStandardOutput.connect(self.on_stdout)
            self.process.readyReadStandardError.connect(self.on_stderr)
            self.process.finished.connect(self.on_process_finished)
            self.process.errorOccurred.connect(self.on_process_error)

            self.process.start()
            if self.process.waitForStarted(3000):
                running_vms[vm_name] = self.process
                self.vm_name = vm_name
                self.stop_btn.setEnabled(True)
                self.kill_btn.setEnabled(True)
                self.vm_status_label.setText("● 运行中")
                self.vm_status_label.setStyleSheet("color: #6a9a6a; font-size: 13px;")
                self.status_bar.showMessage(f"✅ {vm_name} 已启动")
                self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 虚拟机已启动")
                self.flush_log()
            else:
                self.status_bar.showMessage("❌ 启动超时")
                self.launch_btn.setEnabled(True)
        except Exception as e:
            self.status_bar.showMessage(f"❌ 启动失败: {e}")
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 启动失败: {e}")
            self.flush_log()
            self.launch_btn.setEnabled(True)

    def on_stdout(self):
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        if data:
            self.append_log(data.strip())

    def on_stderr(self):
        data = self.process.readAllStandardError().data().decode('utf-8', errors='ignore')
        if data:
            self.append_log(data.strip())

    def on_process_finished(self, exit_code, exit_status):
        global running_vms
        if self.vm_name in running_vms:
            del running_vms[self.vm_name]
        self.launch_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.kill_btn.setEnabled(False)
        self.vm_status_label.setText("● 未运行")
        self.vm_status_label.setStyleSheet("color: #666; font-size: 13px;")
        self.status_bar.showMessage(f"⏹ {self.vm_name} 已退出")
        self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] ⏹ 虚拟机已退出")
        self.flush_log()
        self.process = None

    def on_process_error(self, error):
        self.append_log(f"❌ QProcess 错误: {error}")
        self.flush_log()
        self.launch_btn.setEnabled(True)

    def stop_vm(self):
        """停止虚拟机"""
        global running_vms
        if not self.vm_name or self.vm_name not in running_vms:
            QMessageBox.warning(self, "提示", "虚拟机未运行")
            return
        reply = QMessageBox.question(self, "确认停止", f"确定要停止 {self.vm_name} 吗？", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            proc = running_vms[self.vm_name]
            proc.terminate()
            proc.waitForFinished(5000)
            self.status_bar.showMessage(f"⏹ 已停止 {self.vm_name}")
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] ⏹ 已停止")
            self.flush_log()
        except Exception as e:
            self.status_bar.showMessage(f"❌ 停止失败: {e}")

    def kill_vm(self):
        """强制终止"""
        global running_vms
        if not self.vm_name or self.vm_name not in running_vms:
            QMessageBox.warning(self, "提示", "虚拟机未运行")
            return
        reply = QMessageBox.question(self, "确认强制终止", f"⚠️ 确定要强制终止 {self.vm_name} 吗？", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            proc = running_vms[self.vm_name]
            proc.kill()
            proc.waitForFinished(1000)
            self.status_bar.showMessage(f"💀 已强制终止 {self.vm_name}")
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 💀 已强制终止")
            self.flush_log()
        except Exception as e:
            self.status_bar.showMessage(f"❌ 强制终止失败: {e}")

    def copy_command(self):
        """复制命令"""
        if self.cmd:
            QApplication.clipboard().setText(" ".join(self.cmd))
            self.status_bar.showMessage("✅ 命令已复制到剪贴板")

    def append_log(self, text: str):
        self.log_buffer.append(text)
        if len(self.log_buffer) > 100:
            self.log_buffer = self.log_buffer[-50:]

    def flush_log(self):
        if self.log_buffer:
            current = self.log_text.toPlainText()
            new_lines = "\n".join(self.log_buffer)
            if len(current) > 10000:
                current = current[-5000:]
            self.log_text.setPlainText(current + "\n" + new_lines)
            self.log_buffer.clear()
            self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def show_usb_dialog(self):
        """显示U盘挂载对话框"""
        drives = detect_removable_drives()
        if not drives:
            QMessageBox.information(self, "提示", "未检测到可移动磁盘\n请插入 U 盘或移动硬盘后重试")
            return

        if not self.vm_name:
            QMessageBox.warning(self, "提示", "请先选择虚拟机")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("💾 选择 U 盘")
        dialog.setMinimumWidth(550)
        dialog.setMinimumHeight(250)
        dialog.setStyleSheet("background-color: #2b2b2b; color: #f0f0f0;")
        layout = QVBoxLayout(dialog)

        label = QLabel("选择要挂载的 U 盘：")
        label.setWordWrap(True)
        layout.addWidget(label)

        list_widget = QListWidget()
        list_widget.setStyleSheet("background-color: #3c3c3c; color: #f0f0f0; border: 1px solid #555;")
        for d in drives:
            item = QListWidgetItem(f"{d['device']}  {d['name']}  ({d['size']})")
            item.setData(Qt.UserRole, d)
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        info_label = QLabel("💡 挂载后自动启动 HTTP 文件服务，XP 里用 IE 访问下载")
        info_label.setStyleSheet("color: #888; font-size: 10px; padding: 4px;")
        layout.addWidget(info_label)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("✅ 挂载并开启 HTTP 共享")
        ok_btn.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 6px; border: none; padding: 8px 20px;")
        ok_btn.clicked.connect(lambda: self._mount_usb(list_widget, dialog))
        btn_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("background-color: #666; color: white; border-radius: 6px; border: none; padding: 8px 20px;")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        dialog.exec()

    def _mount_usb(self, list_widget, dialog):
        """挂载U盘"""
        item = list_widget.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请选择一个磁盘")
            return
        drive_data = item.data(Qt.UserRole)
        device = drive_data['device']

        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "提示", f"虚拟机正在运行，挂载需要重启虚拟机。\n是否继续？", QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        if not self.vm_name:
            return
        config_file = VMS_DIR / self.vm_name / "config.json"
        if not config_file.exists():
            return

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        disk_path = f"\\\\.\\{device}" if sys.platform == "win32" else device

        config['usb_disk_mounted'] = disk_path
        config['boot_iso'] = ""
        config['boot_order'] = "disk"
        config['share_enabled'] = True
        config['share_dir'] = device

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        dialog.accept()
        self.load_config(self.vm_name)
        self.update_display()

        self.start_http_server(f"{device}\\")
        
        host_ip = get_host_ip()
        qemu_gateway = "10.0.2.2"
        
        QMessageBox.information(self, "✅ U 盘已挂载 (IDE3) + HTTP 服务已启动", 
            f"U 盘 {device} 已挂载 (IDE 通道 3)\n\n"
            f"📡 HTTP 服务已启动\n"
            f"📍 宿主机 IP: {host_ip}\n"
            f"🔗 访问地址: http://{host_ip}:8080\n"
            f"🔄 备用地址: http://{qemu_gateway}:8080\n\n"
            f"💡 在虚拟机浏览器中打开以上地址\n"
            f"   即可浏览并下载 U 盘里的所有文件\n\n"
            f"⚙️ IDE分配: 0=硬盘 | 1=驱动ISO | 2=ISO | 3=U盘")

        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "重启虚拟机", "是否立即重启虚拟机使 U 盘生效？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.stop_vm()
                time.sleep(1)
                QTimer.singleShot(1000, self.launch)

    def remove_usb(self):
        """移除U盘"""
        if not self.vm_name:
            return
        config_file = VMS_DIR / self.vm_name / "config.json"
        if not config_file.exists():
            return
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        has_usb = 'usb_disk_mounted' in config

        if not has_usb:
            QMessageBox.information(self, "提示", "当前没有挂载 U 盘")
            return

        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "提示", "虚拟机正在运行，移除 U 盘需要重启虚拟机。\n是否继续？", QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        config.pop('usb_disk_mounted', None)
        config['share_enabled'] = False
        config['share_dir'] = ""

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        self.load_config(self.vm_name)
        self.update_display()
        QMessageBox.information(self, "成功", "U 盘已移除\n重启虚拟机后生效")

        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "重启虚拟机", "是否立即重启虚拟机？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.stop_vm()
                time.sleep(1)
                QTimer.singleShot(1000, self.launch)

    def start_http_server(self, path: str):
        """启动HTTP服务"""
        if self.http_process and self.http_process.poll() is None:
            QMessageBox.information(self, "提示", "HTTP 服务已在运行中")
            return
        try:
            self.http_process = subprocess.Popen(
                [sys.executable, "-m", "http.server", "8080", "-d", path],
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception as e:
            self.append_log(f"❌ HTTP 服务启动失败: {e}")
            self.flush_log()
            return False

    def stop_http_server(self):
        """停止HTTP服务"""
        if self.http_process:
            try:
                self.http_process.terminate()
                self.http_process.wait(timeout=3)
            except:
                try:
                    self.http_process.kill()
                except:
                    pass
            self.http_process = None
            self.append_log("⏹ HTTP 服务已停止")
            self.flush_log()
            QMessageBox.information(self, "提示", "HTTP 服务已停止")
        else:
            QMessageBox.information(self, "提示", "HTTP 服务未运行")

    def create_snapshot(self):
        """创建快照"""
        if not self.vm_name:
            QMessageBox.warning(self, "提示", "请先选择虚拟机")
            return
        
        name = self.snap_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入快照名称")
            return
        
        mode = self.snapshot_mode_combo.currentText()
        
        if "冷快照" in mode:
            self.create_cold_snapshot(name)
        elif "内部快照" in mode:
            self.create_internal_snapshot(name)
        elif "外部快照" in mode:
            self.create_external_snapshot(name)

    def create_cold_snapshot(self, name: str):
        """创建冷快照"""
        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "提示", 
                "冷快照需要关闭虚拟机。\n是否关闭虚拟机并创建冷快照？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            self.stop_vm()
            time.sleep(2)
        
        try:
            vm_dir = VMS_DIR / self.vm_name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_files = []
            
            disks = self.config.get('disks', [])
            
            if disks:
                for disk in disks:
                    disk_path = Path(disk['path'])
                    if not disk_path.exists():
                        self.append_log(f"⚠️ 磁盘文件不存在，跳过: {disk_path}")
                        continue
                    backup_name = f"disk_{name}_{timestamp}{disk_path.suffix}"
                    backup_path = vm_dir / backup_name
                    self.append_log(f"📦 正在复制: {disk_path.name} → {backup_name}")
                    shutil.copy2(disk_path, backup_path)
                    backup_files.append(backup_path.name)
            else:
                disk_path = vm_dir / f"disk.{self.config.get('disk_format', 'qcow2')}"
                if disk_path.exists():
                    backup_name = f"disk_{name}_{timestamp}.qcow2"
                    backup_path = vm_dir / backup_name
                    self.append_log(f"📦 正在复制: disk.qcow2 → {backup_name}")
                    shutil.copy2(disk_path, backup_path)
                    backup_files.append(backup_path.name)
                else:
                    QMessageBox.warning(self, "错误", f"找不到磁盘文件:\n{disk_path}")
                    return
            
            if not backup_files:
                QMessageBox.warning(self, "错误", "没有找到可备份的磁盘文件")
                return
            
            self.status_bar.showMessage(f"✅ 冷快照 '{name}' 创建成功")
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] ❄️ 冷快照 '{name}' 已保存")
            self.flush_log()
            self.snap_name_edit.clear()
            self.refresh_snapshot_list()
            
            size_mb = sum(Path(vm_dir / f).stat().st_size for f in backup_files) / 1024 / 1024
            QMessageBox.information(self, "✅ 冷快照创建成功", 
                f"快照名称: {name}\n"
                f"📁 位置: {vm_dir}\n"
                f"📄 备份文件: {len(backup_files)} 个\n"
                f"📏 总大小: {size_mb:.1f} MB\n\n"
                f"💡 这是独立文件，可直接复制到其他位置备份")
            
        except Exception as e:
            self.status_bar.showMessage(f"❌ 冷快照创建失败: {e}")
            self.append_log(f"❌ 冷快照创建失败: {e}")
            self.flush_log()
            QMessageBox.warning(self, "错误", f"冷快照创建失败:\n{e}")

    def create_internal_snapshot(self, name: str):
        """创建内部快照"""
        if self.vm_name not in running_vms:
            QMessageBox.warning(self, "提示", "内部快照需要虚拟机正在运行")
            return
        
        qmp_socket = self.config.get('qmp_socket', '')
        if not qmp_socket:
            QMessageBox.warning(self, "提示", 
                "内部快照需要 QMP Socket\n"
                "请在高级选项中启用 QMP Socket 并重启虚拟机")
            return
        
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(qmp_socket)
            
            sock.send(json.dumps({"execute": "qmp_capabilities"}).encode())
            sock.recv(1024)
            
            cmd = {
                "execute": "savevm",
                "arguments": {"name": name}
            }
            sock.send(json.dumps(cmd).encode())
            result = json.loads(sock.recv(1024).decode())
            sock.close()
            
            if "error" in result:
                raise Exception(result["error"]["desc"])
            
            self.status_bar.showMessage(f"✅ 内部快照 '{name}' 创建成功")
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🔥 内部快照 '{name}' 创建成功")
            self.flush_log()
            self.snap_name_edit.clear()
            self.refresh_snapshot_list()
            QMessageBox.information(self, "成功", f"内部快照 '{name}' 创建成功！")
            
        except Exception as e:
            self.status_bar.showMessage(f"❌ 内部快照失败: {e}")
            QMessageBox.warning(self, "错误", f"内部快照失败:\n{e}")

    def create_external_snapshot(self, name: str):
        """创建外部快照"""
        if self.vm_name not in running_vms:
            QMessageBox.warning(self, "提示", "外部快照需要虚拟机正在运行")
            return
        
        qmp_socket = self.config.get('qmp_socket', '')
        if not qmp_socket:
            QMessageBox.warning(self, "提示", 
                "外部快照需要 QMP Socket\n"
                "请在高级选项中启用 QMP Socket 并重启虚拟机")
            return
        
        try:
            vm_dir = VMS_DIR / self.vm_name
            disk_path = vm_dir / f"disk.{self.config.get('disk_format', 'qcow2')}"
            overlay_path = vm_dir / f"disk_{name}_external.qcow2"
            
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(qmp_socket)
            
            sock.send(json.dumps({"execute": "qmp_capabilities"}).encode())
            sock.recv(1024)
            
            cmd = {
                "execute": "blockdev-snapshot-sync",
                "arguments": {
                    "device": "ide0-hd0",
                    "snapshot-file": str(overlay_path),
                    "format": "qcow2",
                    "mode": "absolute-paths"
                }
            }
            sock.send(json.dumps(cmd).encode())
            result = json.loads(sock.recv(1024).decode())
            sock.close()
            
            if "error" in result:
                raise Exception(result["error"]["desc"])
            
            self.status_bar.showMessage(f"✅ 外部快照 '{name}' 创建成功")
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🔥 外部快照 '{name}' 创建成功")
            self.flush_log()
            self.snap_name_edit.clear()
            self.refresh_snapshot_list()
            QMessageBox.information(self, "成功", 
                f"外部快照 '{name}' 创建成功！\n\n"
                f"📁 新镜像: {overlay_path.name}\n"
                f"💡 虚拟机仍在运行，未中断")
            
        except Exception as e:
            self.status_bar.showMessage(f"❌ 外部快照失败: {e}")
            QMessageBox.warning(self, "错误", f"外部快照失败:\n{e}")

    def restore_snapshot(self):
        """恢复快照"""
        if not self.vm_name:
            QMessageBox.warning(self, "提示", "请先选择虚拟机")
            return
        
        item_text = self.snap_list_combo.currentText()
        if not item_text:
            QMessageBox.warning(self, "提示", "请选择快照")
            return
        
        is_cold = "❄️" in item_text
        is_internal = "📦" in item_text
        
        if "(" in item_text:
            name = item_text.split("(")[0].strip()
            name = re.sub(r'^[❄️📦]\s*', '', name).strip()
        else:
            name = item_text.strip()
        
        if not name:
            QMessageBox.warning(self, "提示", "无法解析快照名称")
            return
        
        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "提示", 
                "恢复快照需要关闭虚拟机。\n是否关闭虚拟机并恢复快照？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            self.stop_vm()
            time.sleep(2)
        
        vm_dir = VMS_DIR / self.vm_name
        disk_path = vm_dir / f"disk.{self.config.get('disk_format', 'qcow2')}"
        
        if is_cold:
            snapshot_files = []
            for f in vm_dir.glob(f"disk_{name}_*.qcow2"):
                if f.name != "disk.qcow2":
                    snapshot_files.append(f)
            old_format = vm_dir / f"disk_{name}.qcow2"
            if old_format.exists() and old_format not in snapshot_files:
                snapshot_files.append(old_format)
            external = vm_dir / f"disk_{name}_external.qcow2"
            if external.exists() and external not in snapshot_files:
                snapshot_files.append(external)
            
            if not snapshot_files:
                QMessageBox.warning(self, "错误", f"找不到冷快照 '{name}'")
                return
            
            if len(snapshot_files) > 1:
                items = [f.name for f in snapshot_files]
                selected, ok = QInputDialog.getItem(
                    self, "选择快照文件", 
                    "找到多个匹配的快照文件，请选择：", 
                    items, 0, False
                )
                if not ok or not selected:
                    return
                selected_path = vm_dir / selected
            else:
                selected_path = snapshot_files[0]
            
            reply = QMessageBox.question(self, "确认恢复", 
                f"确定要从冷快照恢复吗？\n\n"
                f"📁 快照文件: {selected_path.name}\n"
                f"💾 目标磁盘: {disk_path.name}\n\n"
                f"⚠️ 当前磁盘将被覆盖！",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            
            try:
                current_backup = vm_dir / f"disk_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.qcow2"
                shutil.copy2(disk_path, current_backup)
                shutil.copy2(selected_path, disk_path)
                
                self.status_bar.showMessage(f"✅ 冷快照恢复成功")
                self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] ↩️ 冷快照恢复成功")
                self.flush_log()
                
                QMessageBox.information(self, "✅ 恢复成功", 
                    f"冷快照恢复成功！\n\n"
                    f"📁 恢复前磁盘已备份到:\n{current_backup.name}\n\n"
                    f"💡 如果确认无误，可手动删除备份文件")
                
            except Exception as e:
                self.status_bar.showMessage(f"❌ 恢复失败: {e}")
                QMessageBox.warning(self, "错误", f"恢复失败:\n{e}")
            
            return
        
        if is_internal:
            reply = QMessageBox.question(self, "确认恢复", 
                f"确定要恢复内置快照 '{name}' 吗？\n当前磁盘状态将被覆盖！",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            
            try:
                qemu_ver = self.config.get('qemu_version', '')
                qemu_img = BASE_DIR / qemu_ver / "qemu-img.exe"
                if not qemu_img.exists():
                    qemu_img = BASE_DIR / qemu_ver / "qemu-img"
                if not qemu_img.exists():
                    QMessageBox.warning(self, "错误", "找不到 qemu-img")
                    return
                
                result = subprocess.run(
                    [str(qemu_img), "snapshot", "-a", name, str(disk_path)],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    self.status_bar.showMessage(f"✅ 内置快照 '{name}' 恢复成功")
                    self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] ↩️ 内置快照 '{name}' 恢复成功")
                    self.flush_log()
                    QMessageBox.information(self, "成功", f"内置快照 '{name}' 恢复成功！")
                else:
                    error_msg = result.stderr if result.stderr else "未知错误"
                    self.status_bar.showMessage(f"❌ 恢复失败: {error_msg[:100]}")
                    QMessageBox.warning(self, "错误", f"恢复失败:\n{error_msg}")
            except Exception as e:
                self.status_bar.showMessage(f"❌ 恢复快照失败: {e}")
                QMessageBox.warning(self, "错误", f"恢复快照失败:\n{e}")
            
            return
        
        QMessageBox.warning(self, "提示", "无法识别快照类型，请确认快照格式")

    def delete_snapshot(self):
        """删除快照"""
        if not self.vm_name:
            QMessageBox.warning(self, "提示", "请先选择虚拟机")
            return
        
        item_text = self.snap_list_combo.currentText()
        if not item_text:
            QMessageBox.warning(self, "提示", "请选择快照")
            return
        
        is_cold = "❄️" in item_text
        is_internal = "📦" in item_text
        
        if "(" in item_text:
            name = item_text.split("(")[0].strip()
            name = re.sub(r'^[❄️📦]\s*', '', name).strip()
        else:
            name = item_text.strip()
        
        if not name:
            QMessageBox.warning(self, "提示", "无法解析快照名称")
            return
        
        if is_cold:
            vm_dir = VMS_DIR / self.vm_name
            
            files_to_delete = []
            for f in vm_dir.glob(f"disk_{name}*.qcow2"):
                if f.name != "disk.qcow2" and not f.name.startswith("disk_before_restore_"):
                    files_to_delete.append(f)
            
            if not files_to_delete:
                QMessageBox.warning(self, "错误", f"找不到冷快照 '{name}'")
                return
            
            file_list = "\n".join(f"  - {f.name}" for f in files_to_delete)
            reply = QMessageBox.question(self, "确认删除", 
                f"确定要删除冷快照 '{name}' 吗？\n\n"
                f"将删除以下文件：\n{file_list}\n\n"
                f"⚠️ 此操作不可恢复！",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            
            try:
                for f in files_to_delete:
                    f.unlink()
                    self.append_log(f"🗑️ 已删除: {f.name}")
                
                self.status_bar.showMessage(f"✅ 冷快照 '{name}' 已删除")
                self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🗑️ 冷快照 '{name}' 已删除")
                self.flush_log()
                self.refresh_snapshot_list()
                QMessageBox.information(self, "成功", f"冷快照 '{name}' 已删除")
                
            except Exception as e:
                self.status_bar.showMessage(f"❌ 删除失败: {e}")
                QMessageBox.warning(self, "错误", f"删除失败:\n{e}")
            
            return
        
        if is_internal:
            if self.vm_name in running_vms:
                reply = QMessageBox.question(self, "提示", 
                    "删除内置快照需要关闭虚拟机。\n是否关闭虚拟机？",
                    QMessageBox.Yes | QMessageBox.No)
                if reply != QMessageBox.Yes:
                    return
                self.stop_vm()
                time.sleep(2)
            
            reply = QMessageBox.question(self, "确认删除", 
                f"确定要删除内置快照 '{name}' 吗？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            
            try:
                vm_dir = VMS_DIR / self.vm_name
                disk_path = vm_dir / f"disk.{self.config.get('disk_format', 'qcow2')}"
                qemu_ver = self.config.get('qemu_version', '')
                qemu_img = BASE_DIR / qemu_ver / "qemu-img.exe"
                if not qemu_img.exists():
                    qemu_img = BASE_DIR / qemu_ver / "qemu-img"
                if not qemu_img.exists():
                    QMessageBox.warning(self, "错误", "找不到 qemu-img")
                    return
                
                result = subprocess.run(
                    [str(qemu_img), "snapshot", "-d", name, str(disk_path)],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    self.status_bar.showMessage(f"✅ 内置快照 '{name}' 已删除")
                    self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🗑️ 内置快照 '{name}' 已删除")
                    self.flush_log()
                    self.refresh_snapshot_list()
                    QMessageBox.information(self, "成功", f"内置快照 '{name}' 已删除")
                else:
                    error_msg = result.stderr if result.stderr else "未知错误"
                    self.status_bar.showMessage(f"❌ 删除失败: {error_msg[:100]}")
                    QMessageBox.warning(self, "错误", f"删除失败:\n{error_msg}")
            except Exception as e:
                self.status_bar.showMessage(f"❌ 删除快照失败: {e}")
                QMessageBox.warning(self, "错误", f"删除快照失败:\n{e}")
            
            return
        
        QMessageBox.warning(self, "提示", "无法识别快照类型")

    def refresh_snapshot_list(self):
        """刷新快照列表"""
        self.snap_list_combo.clear()
        if not self.vm_name:
            return
        
        vm_dir = VMS_DIR / self.vm_name
        
        cold_snapshots = []
        for f in vm_dir.glob("disk_*.qcow2"):
            if f.name == "disk.qcow2":
                continue
            if f.name.startswith("disk_before_restore_"):
                continue
            if "_external" in f.name:
                continue
            name = f.stem.replace("disk_", "")
            name = re.sub(r'_\d{8}_\d{6}$', '', name)
            size_mb = f.stat().st_size / 1024 / 1024
            cold_snapshots.append((f.stat().st_mtime, f"❄️ {name} (冷备份)  {size_mb:.1f} MB"))
        
        cold_snapshots.sort(key=lambda x: x[0], reverse=True)
        for _, display in cold_snapshots:
            self.snap_list_combo.addItem(display)
        
        external_snapshots = []
        for f in vm_dir.glob("disk_*_external.qcow2"):
            name = f.stem.replace("disk_", "").replace("_external", "")
            size_mb = f.stat().st_size / 1024 / 1024
            external_snapshots.append((f.stat().st_mtime, f"🔥 {name} (外部快照)  {size_mb:.1f} MB"))
        
        external_snapshots.sort(key=lambda x: x[0], reverse=True)
        for _, display in external_snapshots:
            self.snap_list_combo.addItem(display)
        
        disk_path = vm_dir / f"disk.{self.config.get('disk_format', 'qcow2')}"
        if disk_path.exists():
            qemu_ver = self.config.get('qemu_version', '')
            qemu_img = BASE_DIR / qemu_ver / "qemu-img.exe"
            if not qemu_img.exists():
                qemu_img = BASE_DIR / qemu_ver / "qemu-img"
            if qemu_img.exists():
                try:
                    result = subprocess.run(
                        [str(qemu_img), "snapshot", "-l", str(disk_path)],
                        capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            match = re.search(r'\d+\s+(.+?)\s+\d{4}-\d{2}-\d{2}', line)
                            if match:
                                name = match.group(1).strip()
                                self.snap_list_combo.addItem(f"📦 {name} (内置)")
                except Exception as e:
                    print(f"刷新内置快照列表失败: {e}")

    def update_performance(self):
        """更新性能监控"""
        try:
            import psutil
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            vm_pid = None
            if self.vm_name and self.vm_name in running_vms:
                try:
                    vm_pid = running_vms[self.vm_name].processId()
                except:
                    pass
            vm_cpu = 0
            vm_mem = 0
            if vm_pid:
                try:
                    proc = psutil.Process(vm_pid)
                    vm_cpu = proc.cpu_percent()
                    vm_mem = proc.memory_info().rss / 1024 / 1024
                except:
                    pass
            self.perf_text.setText(
                f"💻 系统 CPU: {cpu:.1f}%  |  内存: {mem.percent:.1f}%  |  磁盘: {disk.percent:.1f}%\n"
                f"🐧 VM CPU: {vm_cpu:.1f}%  |  VM 内存: {vm_mem:.1f} MB"
            )
        except ImportError:
            self.perf_text.setText("💡 安装 psutil 获得性能监控: pip install psutil")
        except:
            pass


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # 设置默认字体
    font = QFont("Microsoft YaHei", 11)
    app.setFont(font)
    
    vm_name = sys.argv[1] if len(sys.argv) > 1 else None
    window = LauncherWindow(vm_name)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()