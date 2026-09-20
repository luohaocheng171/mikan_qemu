#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mikan QEMU 启动器 v14.2 - 侧边栏跟随 QEMU 窗口
- 支持多文件夹绑定（从 config/folders.json 读取）
- 支持自定义 QEMU 路径（config.json 的 custom_qemu_path）
- build_command 覆盖主编辑器 v5.5 所有字段
- v14.1: 修复 soundhw / smp maxcpus / whpx 回退 / gl=on 冲突 / stderr 捕获
- v14.2: 非阻塞 QEMU features 检测 + 文件缓存 + build_command 全异步（UI 不卡）
"""

import os
import sys
import json
import subprocess
import time
import re
import shutil
import ctypes
import socket
import shlex
import glob
from pathlib import Path
from datetime import datetime
from threading import Thread
from typing import Optional, List, Dict, Tuple

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

# ============================================================
# 配置
# ============================================================
BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
FOLDERS_FILE = CONFIG_DIR / "folders.json"
FEATURES_CACHE_FILE = CONFIG_DIR / "qemu_features_cache.json"

FALLBACK_VMS_DIR = BASE_DIR / "vms"
FALLBACK_SHARE_DIR = BASE_DIR / "share"
FALLBACK_SHARE_DIR.mkdir(parents=True, exist_ok=True)

running_vms: Dict[str, QProcess] = {}

# ============================================================
# Windows API
# ============================================================
if sys.platform == "win32":
    user32 = ctypes.windll.user32


def find_gtk_window(vm_name: str, timeout: float = 15.0) -> Optional[int]:
    if sys.platform != "win32":
        return None
    try:
        import ctypes.wintypes
        import psutil
        found_hwnd = None
        gtk_class_names = ["gdkWindowToplevel", "gtk", "Gtk", "GDK", "QEMU", "qemu"]
        title_keywords = ["QEMU", "qemu", vm_name if vm_name else ""]
        title_keywords = [k for k in title_keywords if k]

        def enum_callback(hwnd, lparam):
            nonlocal found_hwnd
            if found_hwnd:
                return False
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_buf, 256)
            class_name = class_buf.value
            is_gtk = False
            for cls in gtk_class_names:
                if cls.lower() in class_name.lower():
                    is_gtk = True
                    break
            if not is_gtk and title:
                for kw in title_keywords:
                    if kw and kw.lower() in title.lower():
                        is_gtk = True
                        break
            if not is_gtk:
                return True
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                try:
                    proc = psutil.Process(pid.value)
                    if "qemu" in proc.name().lower():
                        found_hwnd = hwnd
                        print(f"✅ 找到 GTK 窗口: '{title}' | 类: '{class_name}'")
                        return False
                except:
                    pass
                if "gtk" in class_name.lower() or "gdk" in class_name.lower():
                    found_hwnd = hwnd
                    print(f"✅ 找到 GTK 窗口: '{title}' | 类: '{class_name}'")
                    return False
            return True

        enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(enum_callback)
        print("🔍 查找 GTK 窗口...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            user32.EnumWindows(enum_proc, 0)
            if found_hwnd:
                return found_hwnd
            time.sleep(0.5)
        print("⚠️ 未找到 GTK 窗口")
        return None
    except Exception as e:
        print(f"⚠️ 查找失败: {e}")
        return None


def find_sdl_window(vm_name: str, timeout: float = 15.0) -> Optional[int]:
    if sys.platform != "win32":
        return None
    try:
        import ctypes.wintypes
        import psutil
        found_hwnd = None
        sdl_class_names = ["SDL", "SDL_app", "SDL_window", "sdl", "qemu", "QEMU"]
        title_keywords = ["QEMU", "qemu", vm_name if vm_name else ""]
        title_keywords = [k for k in title_keywords if k]

        def enum_callback(hwnd, lparam):
            nonlocal found_hwnd
            if found_hwnd:
                return False
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_buf, 256)
            class_name = class_buf.value
            is_sdl = False
            for cls in sdl_class_names:
                if cls.lower() in class_name.lower():
                    is_sdl = True
                    break
            if not is_sdl and title:
                for kw in title_keywords:
                    if kw and kw.lower() in title.lower():
                        is_sdl = True
                        break
            if not is_sdl:
                return True
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                try:
                    proc = psutil.Process(pid.value)
                    if "qemu" in proc.name().lower():
                        found_hwnd = hwnd
                        print(f"✅ 找到 SDL 窗口: '{title}' | 类: '{class_name}'")
                        return False
                except:
                    pass
            return True

        enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(enum_callback)
        print("🔍 查找 SDL 窗口...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            user32.EnumWindows(enum_proc, 0)
            if found_hwnd:
                return found_hwnd
            time.sleep(0.5)
        print("⚠️ 未找到 SDL 窗口")
        return None
    except Exception as e:
        print(f"⚠️ 查找SDL窗口失败: {e}")
        return None


def get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    if sys.platform != "win32":
        return None
    try:
        import ctypes.wintypes
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    except:
        return None


def is_window_fullscreen(hwnd: int) -> bool:
    if sys.platform != "win32":
        return False
    try:
        style = user32.GetWindowLongW(hwnd, -16)
        if not (style & 0x00C00000):
            return True
        return False
    except:
        return False


def bring_window_to_top(hwnd: int):
    if sys.platform != "win32":
        return
    try:
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0004 | 0x0001)
        user32.SetForegroundWindow(hwnd)
    except:
        pass


# ============================================================
# 多文件夹配置读取
# ============================================================
def load_folders_config() -> Optional[dict]:
    if not FOLDERS_FILE.exists():
        return None
    try:
        with open(FOLDERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ 读取 folders.json 失败: {e}")
        return None


def get_all_vms_dirs() -> List[Path]:
    result = []
    folders_config = load_folders_config()
    if folders_config:
        for folder in folders_config.get("folders", []):
            base = Path(folder.get("path", ""))
            if not base.exists():
                continue
            result.append(base / "vms")
    if FALLBACK_VMS_DIR.exists():
        result.append(FALLBACK_VMS_DIR)
    return result


def find_vm_dir(vm_name: str) -> Optional[Path]:
    for vms_dir in get_all_vms_dirs():
        vm_dir = vms_dir / vm_name
        if (vm_dir / "config.json").exists():
            return vm_dir
    return None


def get_active_folder() -> Optional[dict]:
    folders_config = load_folders_config()
    if not folders_config:
        return None
    folders = folders_config.get("folders", [])
    idx = folders_config.get("active_index", 0)
    if folders and 0 <= idx < len(folders):
        return folders[idx]
    return folders[0] if folders else None


# ============================================================
# QEMU 功能检测（v14.2: 非阻塞 + 文件缓存）
# ============================================================
_qemu_features_cache: Dict[str, dict] = {}


def _default_features() -> dict:
    return {
        "grab_on_click": False,
        "window_size": False,
        "audiodev": False,
        "sdl": False,
        "gtk": False,
        "qmp": False,
        "mem_path": False,
        "memory_backend_file": False,
        "vfio_pci": False,
        "usb_host": False,
        "whpx": False,
        "hax": False,
        "kvm": False,
        "hvf": False,
        "accel_option": False,
    }


def _load_features_cache() -> dict:
    if FEATURES_CACHE_FILE.exists():
        try:
            with open(FEATURES_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def _save_features_cache(cache: dict):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(FEATURES_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except:
        pass


def _run_qemu_help(qemu_exe: Path, args: List[str], timeout: float = 1.5) -> Optional[str]:
    """非阻塞跑 QEMU help 命令，超时强制 kill。返回 stdout+stderr 合并字符串"""
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        p = subprocess.Popen(
            [str(qemu_exe)] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creationflags
        )
        try:
            out, _ = p.communicate(timeout=timeout)
            return out.decode('utf-8', errors='ignore') if out else ""
        except subprocess.TimeoutExpired:
            try:
                p.kill()
                p.communicate(timeout=1)
            except:
                pass
            print(f"⚠️ QEMU 命令超时({timeout}s): {' '.join(args)}")
            return None
    except Exception as e:
        print(f"⚠️ QEMU 命令异常: {e}")
        return None


def get_qemu_features(qemu_exe: Path) -> dict:
    """检测 QEMU 功能，带内存+文件缓存"""
    if not qemu_exe.exists():
        return _default_features()

    exe_key = str(qemu_exe)
    try:
        mtime = qemu_exe.stat().st_mtime
    except:
        mtime = 0

    if exe_key in _qemu_features_cache:
        return _qemu_features_cache[exe_key]

    disk_cache = _load_features_cache()
    cached = disk_cache.get(exe_key)
    if cached and cached.get("_mtime") == mtime:
        feats = cached.get("features", {})
        base = _default_features()
        base.update(feats)
        _qemu_features_cache[exe_key] = base
        print(f"✅ 从缓存读取 QEMU features")
        return base

    features = _default_features()
    print(f"🔍 检测 QEMU features: {qemu_exe.name}")

    out = _run_qemu_help(qemu_exe, ["-help"], timeout=1.5)
    if out is not None:
        if "-audiodev" in out:
            features["audiodev"] = True
        if "-mem-path" in out:
            features["mem_path"] = True
        if "memory-backend-file" in out:
            features["memory_backend_file"] = True
        if "-accel" in out:
            features["accel_option"] = True
        if "-qmp" in out:
            features["qmp"] = True

    out = _run_qemu_help(qemu_exe, ["-display", "help"], timeout=1.5)
    if out is not None:
        if "grab-on-click" in out:
            features["grab_on_click"] = True
        if "window-size" in out:
            features["window_size"] = True
        if "sdl" in out:
            features["sdl"] = True
        if "gtk" in out:
            features["gtk"] = True

    out = _run_qemu_help(qemu_exe, ["-accel", "help"], timeout=1.5)
    if out is not None:
        low = out.lower()
        if "whpx" in low:
            features["whpx"] = True
        if "hax" in low:
            features["hax"] = True
        if "kvm" in low:
            features["kvm"] = True
        if "hvf" in low:
            features["hvf"] = True

    out = _run_qemu_help(qemu_exe, ["-device", "help"], timeout=2.0)
    if out is not None:
        if "vfio-pci" in out:
            features["vfio_pci"] = True
        if "usb-host" in out:
            features["usb_host"] = True

    _qemu_features_cache[exe_key] = features
    disk_cache[exe_key] = {"_mtime": mtime, "features": features}
    _save_features_cache(disk_cache)
    print(f"✅ QEMU features 检测完成并缓存")

    return features


# ============================================================
# QEMU 版本识别 + 可执行文件查找
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
    return 2020


def arch_to_exe_names(arch: str) -> List[str]:
    arch_map = {
        "x86_64": ["qemu-system-x86_64.exe", "qemu-system-x86_64", "qemu-system-x86_64w.exe"],
        "x86": ["qemu-system-i386.exe", "qemu-system-i386"],
        "ARM64": ["qemu-system-aarch64.exe", "qemu-system-aarch64"],
        "ARM": ["qemu-system-arm.exe", "qemu-system-arm"],
        "RISC-V": ["qemu-system-riscv64.exe", "qemu-system-riscv64"],
    }
    return arch_map.get(arch, ["qemu-system-x86_64.exe", "qemu-system-x86_64"])


def find_qemu_exe(config: dict) -> Optional[Path]:
    """优先级：custom_qemu_path > folders.json 的 qemu_path > 绑定文件夹扫描 > BASE_DIR > PATH"""
    custom = config.get("custom_qemu_path", "")
    if custom:
        cp = Path(custom)
        if cp.exists():
            if cp.is_file():
                return cp
            for name in arch_to_exe_names(config.get("arch", "x86_64")):
                exe = cp / name
                if exe.exists():
                    return exe

    qemu_version = config.get("qemu_version", "")
    arch = config.get("arch", "x86_64")
    exe_names = arch_to_exe_names(arch)

    folders_config = load_folders_config()
    if folders_config:
        for folder in folders_config.get("folders", []):
            qemu_path = folder.get("qemu_path", "")
            if not qemu_path:
                continue
            qp = Path(qemu_path)
            if not qp.exists():
                continue
            if qp.is_file():
                return qp
            for name in exe_names:
                exe = qp / name
                if exe.exists():
                    return exe
            try:
                for sub in qp.iterdir():
                    if sub.is_dir() and sub.name.lower().startswith("qemu"):
                        for name in exe_names:
                            exe = sub / name
                            if exe.exists():
                                return exe
            except:
                pass

    if folders_config:
        for folder in folders_config.get("folders", []):
            base = Path(folder.get("path", ""))
            if not base.exists():
                continue
            for name in exe_names:
                exe = base / name
                if exe.exists():
                    return exe
            candidates = []
            try:
                for sub in base.iterdir():
                    if sub.is_dir() and sub.name.lower().startswith("qemu"):
                        candidates.append(sub)
            except:
                pass
            for sub in candidates:
                if qemu_version and qemu_version.lower() in sub.name.lower():
                    for name in exe_names:
                        exe = sub / name
                        if exe.exists():
                            return exe
            for sub in candidates:
                for name in exe_names:
                    exe = sub / name
                    if exe.exists():
                        return exe

    if qemu_version:
        qemu_dir = BASE_DIR / qemu_version
        if qemu_dir.exists():
            for name in exe_names:
                exe = qemu_dir / name
                if exe.exists():
                    return exe
    for sub in BASE_DIR.iterdir():
        if sub.is_dir() and sub.name.startswith("qemu"):
            for name in exe_names:
                exe = sub / name
                if exe.exists():
                    return exe

    for cmd in exe_names:
        try:
            where_cmd = "where" if sys.platform == "win32" else "which"
            result = subprocess.run([where_cmd, cmd], capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore', timeout=5)
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                if path and Path(path).exists():
                    return Path(path)
        except:
            pass

    return None


def get_arch_defaults(arch: str) -> dict:
    defaults = {
        "x86_64": {"machine": "q35", "cpu": "host", "vga": "virtio"},
        "x86": {"machine": "pc", "cpu": "qemu64", "vga": "std"},
        "ARM64": {"machine": "virt", "cpu": "cortex-a72", "vga": "virtio"},
        "ARM": {"machine": "virt", "cpu": "cortex-a15", "vga": "virtio"},
        "RISC-V": {"machine": "virt", "cpu": "rv64", "vga": "virtio"},
    }
    return defaults.get(arch, defaults["x86_64"])


# ============================================================
# 工具函数
# ============================================================
def get_host_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        pass
    return "10.0.2.2"


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
    except Exception as e:
        print(f"⚠️ 扫描可移动磁盘失败: {e}")
    return drives


# ============================================================
# 构建命令 v14.2
# ============================================================
def build_command(config: dict, display_type: str = "gtk") -> Tuple[Optional[List[str]], Optional[str]]:
    vm_name = config.get('name', 'vm')
    arch = config.get('arch', 'x86_64')
    year = get_qemu_year(config.get('qemu_version', ''))
    arch_defaults = get_arch_defaults(arch)

    qemu_exe = find_qemu_exe(config)
    if not qemu_exe:
        return None, f"找不到 QEMU 可执行文件\n\nqemu_version: {config.get('qemu_version', '')}\ncustom_qemu_path: {config.get('custom_qemu_path', '')}"

    features = get_qemu_features(qemu_exe)
    cmd = [str(qemu_exe)]

    cmd.extend(["-name", vm_name])

    memory = config.get('memory', 1024)

    memory_backing_enabled = config.get('memory_backing_enabled', False)
    mem_backend_added = False
    if memory_backing_enabled:
        mem_file = config.get('memory_backing_file', '')
        mem_size_mb = config.get('memory_backing_size', 0) or memory
        if mem_file and features.get("memory_backend_file", False):
            cmd.extend([
                "-object", f"memory-backend-file,id=mem0,size={mem_size_mb}M,mem-path={mem_file},share=on",
            ])
            mem_backend_added = True
        elif mem_file and features.get("mem_path", False):
            cmd.extend(["-mem-path", mem_file])

    cmd.extend(["-m", str(memory)])

    cpu = config.get('cpu', 2)
    threads = config.get('smp_threads', 1)
    sockets = config.get('smp_sockets', 1)
    maxcpus = cpu * threads * sockets
    cmd.extend(["-smp", f"{maxcpus},sockets={sockets},cores={cpu},threads={threads}"])

    cpu_model = config.get('cpu_model', '')
    if not cpu_model:
        if year <= 2013:
            cpu_model = "qemu32" if arch in ["x86", "x86_64"] else arch_defaults.get("cpu", "host")
        elif year <= 2016:
            cpu_model = "qemu64" if arch in ["x86", "x86_64"] else arch_defaults.get("cpu", "host")
        else:
            cpu_model = arch_defaults.get("cpu", "host")

    cpu_flags = config.get('cpu_flags', '').strip()
    if cpu_flags:
        flags = cpu_flags.lstrip(',').lstrip('+')
        cpu_arg = f"{cpu_model},+{flags}" if flags else cpu_model
    else:
        cpu_arg = cpu_model
    cmd.extend(["-cpu", cpu_arg])

    vm_dir = find_vm_dir(vm_name)
    disk_format = config.get('disk_format', 'qcow2')
    disk_interface = config.get('disk_interface', 'sata')
    disk_readonly = config.get('disk_readonly', False)
    snapshot_mode = config.get('snapshot_mode', False)

    disk_path = None
    if vm_dir:
        possible = vm_dir / f"disk.{disk_format}"
        if possible.exists():
            disk_path = possible
    if not disk_path and vm_dir:
        for ext in ["qcow2", "raw", "img", "vmdk"]:
            p = vm_dir / f"disk.{ext}"
            if p.exists():
                disk_path = p
                disk_format = ext
                break

    if disk_path and disk_path.exists():
        drive_opts = f"file={disk_path},format={disk_format},if=none,id=disk0"
        if disk_readonly:
            drive_opts += ",readonly=on"
        cache = config.get('cache', 'writeback')
        if cache and cache != "默认":
            drive_opts += f",cache={cache}"
        aio = config.get('aio', '默认')
        if aio and aio != "默认":
            drive_opts += f",aio={aio}"
        discard = config.get('discard', '默认')
        if discard and discard != "默认" and discard == "on":
            drive_opts += ",discard=unmap"
        cmd.extend(["-drive", drive_opts])

        if disk_interface == "virtio":
            cmd.extend(["-device", "virtio-blk-pci,drive=disk0"])
        elif disk_interface == "nvme":
            cmd.extend(["-device", "nvme,drive=disk0,serial=deadbeef"])
        elif disk_interface == "scsi":
            cmd.extend(["-device", "scsi-hd,drive=disk0"])
        elif disk_interface == "ide":
            cmd.extend(["-device", "ide-hd,drive=disk0,bus=ide.0"])
        elif disk_interface == "sata":
            cmd.extend(["-device", "ide-hd,drive=disk0,bus=ide.0"])
        else:
            cmd.extend(["-device", f"ide-hd,drive=disk0"])

    if snapshot_mode:
        cmd.extend(["-snapshot"])

    boot_order = config.get('boot_order', 'cdrom')
    boot_iso = config.get('boot_iso', '')
    driver_iso = config.get('driver_iso', '')

    if driver_iso and Path(driver_iso).exists():
        cmd.extend(["-drive", f"file={driver_iso},format=raw,if=ide,media=cdrom,index=1"])

    if boot_order == "disk":
        cmd.extend(["-boot", "c"])
    elif boot_order == "network":
        cmd.extend(["-boot", "n"])
    else:
        cmd.extend(["-boot", "d"])
        if boot_iso and Path(boot_iso).exists():
            cmd.extend(["-drive", f"file={boot_iso},format=raw,if=ide,media=cdrom,index=2"])

    boot_once = config.get('boot_once', '')
    if boot_once:
        cmd.extend(["-boot", f"once={boot_once}"])

    machine = config.get('machine_type', '')
    if not machine:
        machine = arch_defaults.get("machine", "q35") if year >= 2020 else arch_defaults.get("machine", "pc")

    if mem_backend_added:
        cmd.extend(["-machine", f"{machine},memory-backend=mem0"])
    else:
        cmd.extend(["-machine", machine])

    if not config.get('acpi', True):
        cmd.extend(["-no-acpi"])

    if config.get('no_hpet', False) or config.get('no_hpet_adv', False):
        cmd.extend(["-no-hpet"])

    vga = config.get('vga', '')
    if not vga:
        if year <= 2013:
            vga = "cirrus" if arch in ["x86", "x86_64"] else arch_defaults.get("vga", "std")
        elif year <= 2016:
            vga = "std" if arch in ["x86", "x86_64"] else arch_defaults.get("vga", "std")
        else:
            vga = arch_defaults.get("vga", "virtio")
    if vga and vga != "none":
        cmd.extend(["-vga", vga])

    if display_type == "sdl" and not features.get("sdl", False):
        display_type = "gtk"
    elif display_type == "gtk" and not features.get("gtk", False):
        display_type = "sdl"

    vnc_port = config.get('vnc_port', '')
    if vnc_port:
        cmd.extend(["-vnc", vnc_port])
    else:
        display_params = ["-display", display_type]
        resolution = config.get('resolution', '')
        if resolution and resolution != "自定义" and features.get("window_size", False):
            display_params[1] += f",window-size={resolution}"
        if features.get("grab_on_click", False):
            display_params[1] += ",grab-on-click=on"
        opengl_capable_vga = ["virtio", "virtio-vga", "virtio-gpu", "virtio-vga-gl",
                              "virtio-gpu-gl", "vmvga", "qxl"]
        if config.get('opengl', False) and vga in opengl_capable_vga:
            display_params[1] += ",gl=on"
        cmd.extend(display_params)

    sound = config.get('sound', 'hda')
    if sound and sound != "none":
        if features.get("audiodev", False):
            if sys.platform == "win32":
                audio_backend = config.get('audio_backend', 'dsound')
                if audio_backend not in ("dsound", "wav", "none"):
                    audio_backend = "dsound"
            elif sys.platform == "darwin":
                audio_backend = "coreaudio"
            else:
                audio_backend = "pa"

            if audio_backend != "none":
                if sound == "ac97":
                    cmd.extend(["-audiodev", f"{audio_backend},id=audio0",
                                "-device", "AC97,audiodev=audio0"])
                elif sound == "sb16":
                    cmd.extend(["-audiodev", f"{audio_backend},id=audio0",
                                "-device", "sb16,audiodev=audio0"])
                else:
                    cmd.extend(["-audiodev", f"{audio_backend},id=audio0",
                                "-device", "intel-hda",
                                "-device", "hda-duplex,audiodev=audio0"])
        else:
            cmd.extend(["-soundhw", sound if sound else "hda"])

    if config.get('usb', True):
        cmd.extend(["-usb"])
        if config.get('usb_tablet', True):
            cmd.extend(["-device", "usb-tablet"])
        for dev in config.get('usb_passthrough', []):
            vid = dev.get('vendor_id', '')
            pid = dev.get('product_id', '')
            if vid and pid:
                vid_clean = vid.replace('0x', '').replace('0X', '')
                pid_clean = pid.replace('0x', '').replace('0X', '')
                cmd.extend(["-device", f"usb-host,vendorid=0x{vid_clean},productid=0x{pid_clean}"])

    network_mode = config.get('network_mode', 'user')
    nic_model = config.get('nic_model', 'e1000')
    mac = config.get('mac_address', '')
    hostfwd = config.get('hostfwd', '')
    net_subnet = config.get('net_subnet', '')
    net_dns = config.get('net_dns', '')
    net_restrict = config.get('net_restrict', False)
    share_dir = config.get('share_dir', '')

    netdev_opts = None
    netdev_id = "net0"

    if network_mode == "none":
        pass
    elif network_mode == "user":
        netdev_opts = f"user,id={netdev_id}"
        if share_dir and Path(share_dir).exists():
            netdev_opts += f",smb={share_dir}"
        if hostfwd:
            for line in hostfwd.split(','):
                line = line.strip()
                if line:
                    netdev_opts += f",hostfwd={line}"
        if net_subnet:
            netdev_opts += f",net={net_subnet}"
        if net_dns:
            netdev_opts += f",dns={net_dns}"
        if net_restrict:
            netdev_opts += ",restrict=on"
        cmd.extend(["-netdev", netdev_opts])
    elif network_mode == "bridge":
        bridge = config.get('bridge_interface', '')
        tap = config.get('tap_interface', '')
        if tap:
            netdev_opts = f"tap,id={netdev_id},ifname={tap}"
            if bridge:
                netdev_opts += f",br={bridge}"
            script = config.get('network_script', '')
            if script:
                netdev_opts += f",script={script}"
            downscript = config.get('network_down_script', '')
            if downscript:
                netdev_opts += f",downscript={downscript}"
            cmd.extend(["-netdev", netdev_opts])
    elif network_mode == "tap":
        tap = config.get('tap_interface', '')
        if tap:
            netdev_opts = f"tap,id={netdev_id},ifname={tap}"
            script = config.get('network_script', '')
            if script:
                netdev_opts += f",script={script}"
            cmd.extend(["-netdev", netdev_opts])
    elif network_mode == "socket":
        sock = config.get('socket_path', '')
        if sock:
            netdev_opts = f"socket,id={netdev_id},listen=:{sock}"
            cmd.extend(["-netdev", netdev_opts])
    elif network_mode == "vde":
        vde = config.get('vde_socket', '')
        if vde:
            netdev_opts = f"vde,id={netdev_id},sock={vde}"
            cmd.extend(["-netdev", netdev_opts])

    if netdev_opts is not None:
        if nic_model == "virtio":
            dev_opts = f"virtio-net-pci,netdev={netdev_id}"
        else:
            dev_opts = f"{nic_model},netdev={netdev_id}"
        if mac:
            dev_opts += f",mac={mac}"
        cmd.extend(["-device", dev_opts])

    for dev in config.get('pci_passthrough', []):
        addr = dev.get('address', '')
        if addr and features.get("vfio_pci", False):
            if re.match(r'^[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]$', addr):
                cmd.extend(["-device", f"vfio-pci,host={addr}"])

    accel = config.get('accel', 'tcg')
    if config.get('force_tcg', False):
        accel = "tcg"

    if accel == "whpx" and not features.get("whpx", False):
        print(f"⚠️ QEMU 不支持 whpx，回退 tcg")
        accel = "tcg"
    elif accel == "hax" and not features.get("hax", False):
        print(f"⚠️ QEMU 不支持 hax，回退 tcg")
        accel = "tcg"
    elif accel == "kvm" and not features.get("kvm", False):
        print(f"⚠️ QEMU 不支持 kvm，回退 tcg")
        accel = "tcg"
    elif accel == "hvf" and not features.get("hvf", False):
        print(f"⚠️ QEMU 不支持 hvf，回退 tcg")
        accel = "tcg"

    if accel != "tcg":
        if year <= 2016 and accel == "kvm":
            cmd.extend(["-enable-kvm"])
        elif features.get("accel_option", False):
            cmd.extend(["-accel", accel])
        elif accel == "kvm":
            cmd.extend(["-enable-kvm"])
        else:
            print(f"⚠️ QEMU 版本太老（{year}），不支持 -accel {accel}，回退 tcg")
            accel = "tcg"

    if config.get('mem_prealloc', False):
        cmd.extend(["-mem-prealloc"])
    if config.get('hugepages', False) and sys.platform == "linux":
        cmd.extend(["-mem-path", "/dev/hugepages"])

    qmp_socket = config.get('qmp_socket', '')
    if qmp_socket and features.get("qmp", False):
        cmd.extend(["-qmp", f"unix:{qmp_socket},server,nowait"])

    log_file = config.get('log_file', '')
    if log_file:
        cmd.extend(["-D", log_file])
    debug_level = config.get('debug_level', '')
    if debug_level and debug_level != "默认" and log_file:
        cmd.extend(["-d", debug_level])

    if config.get('no_reboot', False):
        cmd.extend(["-no-reboot"])
    if config.get('no_shutdown', False):
        cmd.extend(["-no-shutdown"])
    if config.get('sandbox', False):
        cmd.extend(["-sandbox", "on"])

    rtc_base = config.get('rtc_base', '')
    if rtc_base:
        cmd.extend(["-rtc", f"base={rtc_base}"])
    elif config.get('custom_rtc') and config.get('custom_rtc') != "utc":
        cmd.extend(["-rtc", f"base={config.get('custom_rtc')}"])

    seed_value = config.get('seed_value', '')
    if seed_value:
        cmd.extend(["-seed", seed_value])

    bios_file = config.get('bios_file', '') or config.get('custom_bios', '')
    if bios_file and Path(bios_file).exists():
        cmd.extend(["-bios", bios_file])

    extra_args = config.get('extra_args', '')
    if extra_args:
        try:
            cmd.extend(shlex.split(extra_args))
        except:
            cmd.extend(extra_args.split())

    extra_adv = config.get('extra_advanced_args', '')
    if extra_adv:
        for line in extra_adv.split('\n'):
            line = line.strip()
            if line:
                try:
                    cmd.extend(shlex.split(line))
                except:
                    cmd.extend(line.split())

    return cmd, None


# ============================================================
# 托盘图标
# ============================================================
def create_tray_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(42, 130, 218))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(4, 4, 56, 56)
    painter.setPen(QColor(255, 255, 255))
    painter.setFont(QFont("Segoe UI Emoji", 32))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "🧲")
    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setIcon(create_tray_icon())
        self.setToolTip("🧲 Mikan QEMU")

        self.menu = QMenu()
        self.show_action = QAction("📂 显示控制面板", self)
        self.show_action.triggered.connect(self.show_window)
        self.menu.addAction(self.show_action)
        self.menu.addSeparator()
        self.launch_action = QAction("▶ 启动虚拟机", self)
        self.launch_action.triggered.connect(self.launch_vm)
        self.menu.addAction(self.launch_action)
        self.stop_action = QAction("⏹ 停止虚拟机", self)
        self.stop_action.triggered.connect(self.stop_vm)
        self.stop_action.setEnabled(False)
        self.menu.addAction(self.stop_action)
        self.menu.addSeparator()
        self.http_action = QAction("📡 启动 HTTP", self)
        self.http_action.triggered.connect(self.toggle_http)
        self.menu.addAction(self.http_action)
        self.menu.addSeparator()
        self.quit_action = QAction("🚪 退出", self)
        self.quit_action.triggered.connect(self.quit_app)
        self.menu.addAction(self.quit_action)
        self.setContextMenu(self.menu)
        self.activated.connect(self.on_activated)

        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_fullscreen)
        self.check_timer.start(500)
        self.is_fullscreen = False

    def show_window(self):
        if self.parent:
            self.parent.show()
            self.parent.raise_()
            self.parent.activateWindow()

    def launch_vm(self):
        if self.parent:
            self.parent.launch()

    def stop_vm(self):
        if self.parent:
            self.parent.stop_vm()

    def toggle_http(self):
        if self.parent:
            self.parent.toggle_http()

    def quit_app(self):
        if self.parent:
            self.parent.close()
        QApplication.quit()

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()

    def check_fullscreen(self):
        if not self.parent or not self.parent.display_hwnd:
            return
        try:
            fullscreen = is_window_fullscreen(self.parent.display_hwnd)
            if fullscreen and not self.is_fullscreen:
                self.is_fullscreen = True
                self.parent.hide()
                self.showMessage("🧲 Mikan QEMU", "虚拟机已全屏\n控制面板已隐藏到托盘", QSystemTrayIcon.Information, 2000)
            elif not fullscreen and self.is_fullscreen:
                self.is_fullscreen = False
                self.parent.show()
                self.showMessage("🧲 Mikan QEMU", "虚拟机退出全屏\n控制面板已恢复", QSystemTrayIcon.Information, 2000)
        except:
            pass

    def update_menu(self, is_running: bool, is_http: bool):
        self.launch_action.setEnabled(not is_running)
        self.stop_action.setEnabled(is_running)
        if is_http:
            self.http_action.setText("⏹ 停止 HTTP")
        else:
            self.http_action.setText("📡 启动 HTTP")


# ============================================================
# 侧边栏
# ============================================================
class SidebarWindow(QWidget):
    def __init__(self, vm_name: str = None):
        super().__init__()
        self.vm_name = vm_name
        self.vm_dir = None
        self.config = None
        self.cmd = None
        self.process: Optional[QProcess] = None
        self.http_process = None

        self.display_hwnd = None
        self.find_timer = None
        self.find_attempts = 0
        self.sidebar_width = 280
        self.min_width = 180
        self.max_width = 500

        self.display_type = "gtk"
        self.display_mode = "attach"
        self._error_shown = False

        self.tray = TrayIcon(self)
        self.tray.show()

        self.init_ui()

        if vm_name:
            self.load_config(vm_name)
            self.update_display()

        self.refresh_vm_list()

        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.closeEvent = self.hide_event

        self.follow_timer = QTimer()
        self.follow_timer.timeout.connect(self.follow_qemu)
        self.follow_timer.start(100)

    def init_ui(self):
        font = QFont("Microsoft YaHei", 10)
        self.setFont(font)
        self.setWindowTitle(f"🧲 Mikan QEMU - {self.vm_name if self.vm_name else '选择虚拟机'}")
        self.setMinimumWidth(self.min_width)
        self.setMaximumWidth(self.max_width)
        self.setMinimumHeight(300)
        self.resize(self.sidebar_width, 600)

        self.setStyleSheet("""
            QWidget { background-color: #1a1a1a; color: #f0f0f0; }
            QLabel { color: #ddd; font-family: "Microsoft YaHei"; font-size: 12px; }
            QComboBox { background-color: #2b2b2b; color: #ddd; border: 1px solid #444; border-radius: 4px; padding: 4px 8px; font-family: "Microsoft YaHei"; min-height: 26px; }
            QLineEdit { background-color: #2b2b2b; color: #ddd; border: 1px solid #444; border-radius: 4px; padding: 4px 8px; font-family: "Microsoft YaHei"; min-height: 22px; }
            QPushButton { font-family: "Microsoft YaHei"; font-weight: bold; border: none; border-radius: 4px; padding: 6px 14px; font-size: 12px; }
            QPushButton:disabled { background-color: #2a2a2a; color: #666; }
            QGroupBox { color: #ddd; border: 1px solid #333; border-radius: 4px; margin-top: 6px; padding-top: 6px; font-family: "Microsoft YaHei"; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; color: #aaa; font-size: 11px; }
            QScrollArea { border: none; background-color: transparent; }
            QScrollBar:vertical { background-color: #2b2b2b; width: 10px; border-radius: 5px; }
            QScrollBar::handle:vertical { background-color: #5a5a5a; border-radius: 5px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background-color: #6a6a6a; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #1a1a1a;")
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        title = QLabel("🧲 Mikan QEMU")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff; padding: 4px 0 8px 0;")
        layout.addWidget(title)

        layout.addWidget(QLabel("虚拟机"))
        self.vm_combo = QComboBox()
        self.vm_combo.setMinimumHeight(30)
        self.vm_combo.currentTextChanged.connect(self.on_vm_selected)
        layout.addWidget(self.vm_combo)

        refresh_btn = QPushButton("🔄 刷新列表")
        refresh_btn.setStyleSheet("background-color: #3a3a3a; color: #ddd; font-weight: normal;")
        refresh_btn.clicked.connect(self.refresh_vm_list)
        layout.addWidget(refresh_btn)

        layout.addSpacing(6)

        display_group = QGroupBox("🖥️ 显示")
        display_layout = QVBoxLayout(display_group)
        display_layout.setSpacing(4)
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("类型:"))
        self.display_type_combo = QComboBox()
        self.display_type_combo.addItems(["GTK", "SDL"])
        self.display_type_combo.setMinimumHeight(26)
        self.display_type_combo.currentTextChanged.connect(self.on_display_type_changed)
        type_layout.addWidget(self.display_type_combo)
        display_layout.addLayout(type_layout)
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("模式:"))
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItems(["磁铁吸附", "窗口模式"])
        self.display_mode_combo.setMinimumHeight(26)
        self.display_mode_combo.currentTextChanged.connect(self.on_display_mode_changed)
        mode_layout.addWidget(self.display_mode_combo)
        display_layout.addLayout(mode_layout)
        self.attach_status = QLabel("🔗 等待启动...")
        self.attach_status.setStyleSheet("color: #888; font-size: 11px; padding: 4px 6px; background: #2a2a2a; border-radius: 4px;")
        display_layout.addWidget(self.attach_status)
        layout.addWidget(display_group)

        snap_group = QGroupBox("📸 快照")
        snap_layout = QVBoxLayout(snap_group)
        snap_layout.setSpacing(4)
        snap_name_layout = QHBoxLayout()
        self.snap_name_edit = QLineEdit()
        self.snap_name_edit.setPlaceholderText("快照名称")
        snap_name_layout.addWidget(self.snap_name_edit, 1)
        self.create_snap_btn = QPushButton("创建")
        self.create_snap_btn.setStyleSheet("background-color: #4a7a4a; color: white; font-weight: normal;")
        self.create_snap_btn.clicked.connect(self.create_snapshot)
        snap_name_layout.addWidget(self.create_snap_btn)
        snap_layout.addLayout(snap_name_layout)
        snap_list_layout = QHBoxLayout()
        self.snap_list_combo = QComboBox()
        self.snap_list_combo.setMinimumHeight(26)
        snap_list_layout.addWidget(self.snap_list_combo, 1)
        self.restore_snap_btn = QPushButton("恢复")
        self.restore_snap_btn.setStyleSheet("background-color: #5a5a5a; color: white; font-weight: normal;")
        self.restore_snap_btn.clicked.connect(self.restore_snapshot)
        snap_list_layout.addWidget(self.restore_snap_btn)
        self.delete_snap_btn = QPushButton("删除")
        self.delete_snap_btn.setStyleSheet("background-color: #8a4a4a; color: white; font-weight: normal;")
        self.delete_snap_btn.clicked.connect(self.delete_snapshot)
        snap_list_layout.addWidget(self.delete_snap_btn)
        snap_layout.addLayout(snap_list_layout)
        layout.addWidget(snap_group)

        usb_group = QGroupBox("💾 U盘 + HTTP")
        usb_layout = QHBoxLayout(usb_group)
        usb_layout.setSpacing(4)
        self.usb_btn = QPushButton("挂载")
        self.usb_btn.setStyleSheet("background-color: #2a6a8a; color: white; font-weight: normal;")
        self.usb_btn.clicked.connect(self.show_usb_dialog)
        usb_layout.addWidget(self.usb_btn)
        self.usb_remove_btn = QPushButton("移除")
        self.usb_remove_btn.setStyleSheet("background-color: #8a6a2a; color: white; font-weight: normal;")
        self.usb_remove_btn.clicked.connect(self.remove_usb)
        usb_layout.addWidget(self.usb_remove_btn)
        self.http_btn = QPushButton("HTTP")
        self.http_btn.setStyleSheet("background-color: #3a6a3a; color: white; font-weight: normal;")
        self.http_btn.clicked.connect(self.toggle_http)
        usb_layout.addWidget(self.http_btn)
        layout.addWidget(usb_group)

        layout.addSpacing(4)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        self.launch_btn = QPushButton("▶ 启动")
        self.launch_btn.setMinimumHeight(38)
        self.launch_btn.setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: white; font-size: 14px; }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #2a2a2a; color: #666; }
        """)
        self.launch_btn.clicked.connect(self.launch)
        btn_layout.addWidget(self.launch_btn)
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setMinimumHeight(38)
        self.stop_btn.setStyleSheet("""
            QPushButton { background-color: #f44336; color: white; font-size: 14px; }
            QPushButton:hover { background-color: #d32f2f; }
            QPushButton:disabled { background-color: #2a2a2a; color: #666; }
        """)
        self.stop_btn.clicked.connect(self.stop_vm)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

        self.copy_btn = QPushButton("📋 复制命令")
        self.copy_btn.setStyleSheet("background-color: #3a3a3a; color: #ddd; font-weight: normal;")
        self.copy_btn.clicked.connect(self.copy_command)
        layout.addWidget(self.copy_btn)

        layout.addSpacing(4)

        self.status_label = QLabel("● 未运行")
        self.status_label.setStyleSheet("color: #666; font-size: 12px; padding: 4px 0;")
        layout.addWidget(self.status_label)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #888; font-size: 10px; padding: 2px 0;")
        layout.addWidget(self.info_label)

        self.folder_label = QLabel("")
        self.folder_label.setStyleSheet("color: #666; font-size: 10px; padding: 2px 0;")
        layout.addWidget(self.folder_label)

        layout.addStretch()
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        self.resize_handle = QFrame(self)
        self.resize_handle.setStyleSheet("""
            QFrame { background-color: transparent; border: none; }
            QFrame:hover { background-color: #3a6a8a; }
        """)
        self.resize_handle.setCursor(Qt.SplitHCursor)
        self.resize_handle.setFixedWidth(4)
        self.resize_handle.raise_()
        self.mousePressEvent = self.on_sidebar_click

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_handle.setGeometry(self.width() - 4, 0, 4, self.height())
        self.sidebar_width = self.width()

    def on_sidebar_click(self, event):
        if self.display_hwnd and self.display_mode == "attach":
            bring_window_to_top(self.display_hwnd)
        event.accept()

    def follow_qemu(self):
        if not self.display_hwnd or self.display_mode != "attach":
            return
        if not self.isVisible():
            return
        if sys.platform != "win32":
            return
        try:
            qemu_rect = get_window_rect(self.display_hwnd)
            if not qemu_rect:
                return
            qemu_x, qemu_y, qemu_w, qemu_h = qemu_rect
            target_x = qemu_x - self.sidebar_width
            target_y = qemu_y
            target_h = qemu_h
            if target_x < 0:
                target_x = 0
            current_rect = get_window_rect(int(self.winId()))
            if not current_rect:
                return
            current_x, current_y, current_w, current_h = current_rect
            if (abs(current_x - target_x) > 5 or
                abs(current_y - target_y) > 5 or
                abs(current_h - target_h) > 5):
                user32.SetWindowPos(
                    int(self.winId()), None,
                    target_x, target_y,
                    self.sidebar_width, target_h,
                    0x0000
                )
        except Exception as e:
            print(f"⚠️ 跟随失败: {e}")

    def refresh_vm_list(self):
        self.vm_combo.blockSignals(True)
        self.vm_combo.clear()
        seen = set()
        for vms_dir in get_all_vms_dirs():
            if not vms_dir.exists():
                continue
            for vm_dir in vms_dir.iterdir():
                if vm_dir.is_dir() and (vm_dir / "config.json").exists():
                    if vm_dir.name not in seen:
                        self.vm_combo.addItem(vm_dir.name)
                        seen.add(vm_dir.name)
        self.vm_combo.blockSignals(False)
        if self.vm_combo.count() > 0:
            if self.vm_name and self.vm_combo.findText(self.vm_name) >= 0:
                self.vm_combo.setCurrentText(self.vm_name)
            else:
                self.vm_combo.setCurrentIndex(0)
                self.vm_name = self.vm_combo.currentText()

    def on_vm_selected(self, name: str):
        if name:
            self.vm_name = name
            self.setWindowTitle(f"🧲 Mikan QEMU - {name}")
            self.load_config(name)
            self.update_display()

    def load_config(self, vm_name: str):
        vm_dir = find_vm_dir(vm_name)
        if not vm_dir:
            print(f"⚠️ 找不到虚拟机: {vm_name}")
            self.config = None
            self.cmd = None
            self.vm_dir = None
            return
        self.vm_dir = vm_dir
        config_file = vm_dir / "config.json"
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"⚠️ 读取配置失败: {e}")
            self.config = None
            self.cmd = None
            return
        # v14.2: 不在这里构建命令
        self.cmd = None

    def update_display(self):
        if not self.config:
            self.info_label.setText("")
            self.folder_label.setText("")
            return
        arch = self.config.get('arch', 'x86_64')
        memory = self.config.get('memory', 1024)
        cpu = self.config.get('cpu', 2)
        info_text = f"{arch} | {memory}MB | {cpu}核 | {self.display_type.upper()}"
        self.info_label.setText(info_text)
        if self.vm_dir:
            try:
                self.folder_label.setText(f"📁 {self.vm_dir.parent.parent.name}")
            except:
                self.folder_label.setText("")
        usb_disk = self.config.get('usb_disk_mounted', '')
        if usb_disk:
            self.usb_btn.setText(f"💾 {Path(usb_disk).name[:6]}")
            self.usb_btn.setStyleSheet("background-color: #4a8a4a; color: white; font-weight: normal;")
        else:
            self.usb_btn.setText("挂载")
            self.usb_btn.setStyleSheet("background-color: #2a6a8a; color: white; font-weight: normal;")
        self.refresh_snapshot_list()

    def on_display_type_changed(self, text: str):
        self.display_type = "sdl" if text.lower() == "sdl" else "gtk"
        self.cmd = None

    def on_display_mode_changed(self, text: str):
        if "吸附" in text:
            self.display_mode = "attach"
            self.attach_status.setText("🔗 等待吸附...")
            self.attach_status.setStyleSheet("color: #FFA500; font-size: 11px; padding: 4px 6px; background: #2a2a2a; border-radius: 4px;")
            if self.vm_name and self.vm_name in running_vms and self.process:
                self.start_pinning()
        else:
            self.display_mode = "window"
            self.attach_status.setText("🪟 窗口模式")
            self.attach_status.setStyleSheet("color: #888; font-size: 11px; padding: 4px 6px; background: #2a2a2a; border-radius: 4px;")
            self.stop_pinning()

    def start_pinning(self):
        if sys.platform != "win32":
            return
        if not self.process or self.process.state() != QProcess.Running:
            return
        self.stop_pinning()
        self.find_timer = QTimer()
        self.find_timer.timeout.connect(self.try_find_window)
        self.find_timer.start(500)
        self.find_attempts = 0
        self.attach_status.setText("🔍 查找窗口...")
        self.attach_status.setStyleSheet("color: #FFA500; font-size: 11px; padding: 4px 6px; background: #2a2a2a; border-radius: 4px;")

    def try_find_window(self):
        self.find_attempts += 1
        if not self.process or self.process.state() != QProcess.Running:
            self.find_timer.stop()
            self.attach_status.setText("❌ 进程已退出")
            self.attach_status.setStyleSheet("color: #FF6B6B; font-size: 11px; padding: 4px 6px; background: #2a2a2a; border-radius: 4px;")
            return
        if self.find_attempts > 30:
            self.find_timer.stop()
            self.attach_status.setText("⚠️ 窗口查找超时")
            self.attach_status.setStyleSheet("color: #FF6B6B; font-size: 11px; padding: 4px 6px; background: #2a2a2a; border-radius: 4px;")
            return
        hwnd = None
        if self.display_type == "gtk":
            hwnd = find_gtk_window(self.vm_name, timeout=0.3)
        else:
            hwnd = find_sdl_window(self.vm_name, timeout=0.3)
        if hwnd:
            self.find_timer.stop()
            self.display_hwnd = hwnd
            self.attach_window(hwnd)

    def attach_window(self, hwnd: int):
        if sys.platform != "win32":
            return
        self.attach_status.setText("✅ 已吸附")
        self.attach_status.setStyleSheet("color: #6a9a6a; font-size: 11px; padding: 4px 6px; background: #2a3a2a; border-radius: 4px;")
        QTimer.singleShot(100, self.follow_qemu)

    def stop_pinning(self):
        if self.find_timer:
            self.find_timer.stop()
            self.find_timer = None
        self.display_hwnd = None

    def hide_event(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage("🧲 Mikan QEMU", "程序已最小化到系统托盘", QSystemTrayIcon.Information, 2000)

    # ============================================================
    # 启动（v14.2: 后台构建命令）
    # ============================================================
    def launch(self):
        global running_vms
        vm_name = self.vm_combo.currentText()
        if not vm_name:
            QMessageBox.warning(self, "提示", "请选择虚拟机")
            return
        if vm_name in running_vms:
            QMessageBox.warning(self, "提示", f"虚拟机 {vm_name} 已在运行中")
            return

        self.launch_btn.setEnabled(False)
        self.status_label.setText("● 构建命令中...")
        self.status_label.setStyleSheet("color: #FFA500; font-size: 12px; padding: 4px 0;")

        def _build_bg():
            try:
                vm_dir = find_vm_dir(vm_name)
                if not vm_dir:
                    QMetaObject.invokeMethod(self, "_launch_error",
                                             Qt.QueuedConnection,
                                             Q_ARG(str, f"找不到虚拟机: {vm_name}"))
                    return
                with open(vm_dir / "config.json", 'r', encoding='utf-8') as f:
                    config = json.load(f)
                cmd, error = build_command(config, display_type=self.display_type)
                payload = json.dumps({
                    "cmd": cmd, "error": error,
                    "config": config, "vm_dir": str(vm_dir)
                }, ensure_ascii=False)
                QMetaObject.invokeMethod(self, "_launch_ready",
                                         Qt.QueuedConnection,
                                         Q_ARG(str, vm_name),
                                         Q_ARG(str, payload))
            except Exception as e:
                QMetaObject.invokeMethod(self, "_launch_error",
                                         Qt.QueuedConnection,
                                         Q_ARG(str, str(e)))

        Thread(target=_build_bg, daemon=True).start()

    @Slot(str, str)
    def _launch_ready(self, vm_name, data_json):
        try:
            data = json.loads(data_json)
        except:
            self._launch_error("数据解析失败")
            return
        cmd = data.get("cmd")
        error = data.get("error")
        config = data.get("config")
        vm_dir_str = data.get("vm_dir")

        if error or not cmd:
            self._launch_error(f"无法构建命令:\n\n{error}")
            return

        self.vm_dir = Path(vm_dir_str) if vm_dir_str else None
        self.config = config
        self.cmd = cmd

        print("\n" + "=" * 60)
        print(f"🚀 启动 {vm_name}")
        print("=" * 60)
        print(" ".join(cmd))
        print("=" * 60 + "\n")

        try:
            qemu_exe = Path(cmd[0])
            qemu_dir = qemu_exe.parent
            args = cmd[1:]
            self.process = QProcess()
            self.process.setProgram(str(qemu_exe))
            self.process.setArguments(args)
            self.process.setWorkingDirectory(str(qemu_dir))
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            self.process.readyReadStandardOutput.connect(self.on_qemu_output)
            self.process.finished.connect(self.on_process_finished)
            self.process.errorOccurred.connect(self.on_process_error)
            self.process.start()
            if self.process.waitForStarted(5000):
                running_vms[vm_name] = self.process
                self.vm_name = vm_name
                self.stop_btn.setEnabled(True)
                self.status_label.setText("● 运行中")
                self.status_label.setStyleSheet("color: #6a9a6a; font-size: 12px; padding: 4px 0;")
                self.tray.update_menu(True, self.http_process is not None)
                if self.display_mode == "attach":
                    QTimer.singleShot(1500, self.start_pinning)
            else:
                self.launch_btn.setEnabled(True)
                self.status_label.setText("● 启动超时")
                self.status_label.setStyleSheet("color: #FF6B6B; font-size: 12px; padding: 4px 0;")
        except Exception as e:
            self.launch_btn.setEnabled(True)
            self.status_label.setText("● 启动失败")
            self.status_label.setStyleSheet("color: #FF6B6B; font-size: 12px; padding: 4px 0;")
            QMessageBox.warning(self, "错误", f"启动失败: {e}")

    @Slot(str)
    def _launch_error(self, msg):
        self.launch_btn.setEnabled(True)
        self.status_label.setText("● 构建失败")
        self.status_label.setStyleSheet("color: #FF6B6B; font-size: 12px; padding: 4px 0;")
        QMessageBox.warning(self, "错误", msg)

    def on_qemu_output(self):
        try:
            output = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='ignore')
            if output:
                print(f"[QEMU] {output}", end='', flush=True)
                lower = output.lower()
                if ("error" in lower or "invalid" in lower or "failed" in lower) and not self._error_shown:
                    self._error_shown = True
                    QTimer.singleShot(100, lambda: QMessageBox.warning(
                        self, "QEMU 错误",
                        f"QEMU 报告错误:\n\n{output[:800]}\n\n完整信息请看运行 launcher 的终端窗口。"
                    ))
        except:
            pass

    def on_process_finished(self):
        global running_vms
        if self.vm_name in running_vms:
            del running_vms[self.vm_name]
        self.launch_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("● 已停止")
        self.status_label.setStyleSheet("color: #666; font-size: 12px; padding: 4px 0;")
        self.process = None
        self.stop_pinning()
        self.display_hwnd = None
        self.attach_status.setText("🔗 等待启动...")
        self.attach_status.setStyleSheet("color: #888; font-size: 11px; padding: 4px 6px; background: #2a2a2a; border-radius: 4px;")
        self.tray.update_menu(False, self.http_process is not None)
        self._error_shown = False

    def on_process_error(self, error):
        self.launch_btn.setEnabled(True)
        error_map = {
            QProcess.FailedToStart: "无法启动进程（QEMU 可执行文件可能不存在）",
            QProcess.Crashed: "进程崩溃",
            QProcess.Timedout: "启动超时",
            QProcess.WriteError: "写入错误",
            QProcess.ReadError: "读取错误",
            QProcess.UnknownError: "未知错误",
        }
        msg = error_map.get(error, f"错误码: {error}")
        QMessageBox.warning(self, "错误", f"进程错误: {msg}")

    def stop_vm(self):
        global running_vms
        if not self.vm_name or self.vm_name not in running_vms:
            QMessageBox.warning(self, "提示", "虚拟机未运行")
            return
        reply = QMessageBox.question(self, "确认停止", f"确定要停止 {self.vm_name} 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            proc = running_vms[self.vm_name]
            proc.terminate()
            proc.waitForFinished(5000)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"停止失败: {e}")

    def copy_command(self):
        if not self.vm_name:
            QMessageBox.warning(self, "提示", "请先选择虚拟机")
            return
        self.copy_btn.setEnabled(False)
        self.copy_btn.setText("📋 构建中...")
        vm_name = self.vm_name

        def _bg():
            try:
                vm_dir = find_vm_dir(vm_name)
                if not vm_dir:
                    QMetaObject.invokeMethod(self, "_copy_done",
                                             Qt.QueuedConnection,
                                             Q_ARG(str, ""))
                    return
                with open(vm_dir / "config.json", 'r', encoding='utf-8') as f:
                    config = json.load(f)
                cmd, error = build_command(config, display_type=self.display_type)
                cmd_str = " ".join(cmd) if cmd else ""
                QMetaObject.invokeMethod(self, "_copy_done",
                                         Qt.QueuedConnection,
                                         Q_ARG(str, cmd_str))
            except:
                QMetaObject.invokeMethod(self, "_copy_done",
                                         Qt.QueuedConnection,
                                         Q_ARG(str, ""))

        Thread(target=_bg, daemon=True).start()

    @Slot(str)
    def _copy_done(self, cmd_str):
        self.copy_btn.setEnabled(True)
        self.copy_btn.setText("📋 复制命令")
        if cmd_str:
            QApplication.clipboard().setText(cmd_str)
            QMessageBox.information(self, "成功", "命令已复制到剪贴板\n\n粘贴到 CMD 可手动调试")
        else:
            QMessageBox.warning(self, "错误", "构建命令失败")

    # ============================================================
    # 快照
    # ============================================================
    def _get_qemu_img(self):
        if not self.config:
            return None
        qemu_exe = find_qemu_exe(self.config)
        if not qemu_exe:
            return None
        for name in ["qemu-img.exe", "qemu-img"]:
            p = qemu_exe.parent / name
            if p.exists():
                return p
        return None

    def _get_disk_path(self):
        if not self.vm_dir:
            return None
        for ext in ["qcow2", "raw", "img", "vmdk"]:
            p = self.vm_dir / f"disk.{ext}"
            if p.exists():
                return p
        return None

    def create_snapshot(self):
        if not self.vm_name or not self.vm_dir:
            QMessageBox.warning(self, "提示", "请先选择虚拟机")
            return
        name = self.snap_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入快照名称")
            return
        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "提示",
                "创建快照前建议关闭虚拟机。\n是否关闭虚拟机并继续？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            self.stop_vm()
            time.sleep(2)
        disk_path = self._get_disk_path()
        if not disk_path:
            QMessageBox.warning(self, "错误", "找不到磁盘文件")
            return
        if disk_path.suffix.lower() != ".qcow2":
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup = disk_path.parent / f"disk_{name}_{timestamp}{disk_path.suffix}"
                shutil.copy2(disk_path, backup)
                self.snap_name_edit.clear()
                self.refresh_snapshot_list()
                QMessageBox.information(self, "✅ 快照创建成功", f"快照: {name}\n文件: {backup.name}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"快照失败: {e}")
            return
        qemu_img = self._get_qemu_img()
        if not qemu_img:
            QMessageBox.warning(self, "错误", "找不到 qemu-img")
            return
        try:
            result = subprocess.run(
                [str(qemu_img), "snapshot", "-c", name, str(disk_path)],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=30
            )
            if result.returncode == 0:
                self.snap_name_edit.clear()
                self.refresh_snapshot_list()
                QMessageBox.information(self, "✅ 快照创建成功", f"快照: {name}")
            else:
                err = result.stderr or result.stdout
                QMessageBox.warning(self, "错误", f"快照创建失败:\n{err}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"快照失败: {e}")

    def restore_snapshot(self):
        if not self.vm_name or not self.vm_dir:
            QMessageBox.warning(self, "提示", "请先选择虚拟机")
            return
        item_text = self.snap_list_combo.currentText()
        if not item_text:
            QMessageBox.warning(self, "提示", "请选择快照")
            return
        name = item_text.split("(")[0].strip() if "(" in item_text else item_text.strip()
        if not name:
            QMessageBox.warning(self, "提示", "无法解析快照名称")
            return
        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "提示",
                "恢复快照前需要关闭虚拟机。\n是否关闭虚拟机并恢复？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            self.stop_vm()
            time.sleep(2)
        disk_path = self._get_disk_path()
        if not disk_path:
            QMessageBox.warning(self, "错误", "找不到磁盘文件")
            return
        if name.startswith("📄 "):
            file_name = name[2:].strip()
            snap_file = self.vm_dir / file_name
            if not snap_file.exists():
                QMessageBox.warning(self, "错误", f"找不到文件: {file_name}")
                return
            reply = QMessageBox.question(self, "确认恢复",
                f"确定要从快照恢复吗？\n\n📁 {file_name}\n⚠️ 当前磁盘将被覆盖！",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            try:
                backup = self.vm_dir / f"disk_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}{disk_path.suffix}"
                shutil.copy2(disk_path, backup)
                shutil.copy2(snap_file, disk_path)
                self.refresh_snapshot_list()
                QMessageBox.information(self, "✅ 恢复成功", f"恢复前磁盘已备份到:\n{backup.name}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"恢复失败: {e}")
        else:
            qemu_img = self._get_qemu_img()
            if not qemu_img:
                QMessageBox.warning(self, "错误", "找不到 qemu-img")
                return
            reply = QMessageBox.question(self, "确认恢复",
                f"确定要恢复到快照 '{name}' 吗？\n\n⚠️ 当前状态将被覆盖！",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            try:
                result = subprocess.run(
                    [str(qemu_img), "snapshot", "-a", name, str(disk_path)],
                    capture_output=True, text=True, encoding='utf-8', errors='ignore',
                    timeout=30
                )
                if result.returncode == 0:
                    QMessageBox.information(self, "✅ 恢复成功", f"已恢复到快照: {name}")
                else:
                    err = result.stderr or result.stdout
                    QMessageBox.warning(self, "错误", f"恢复失败:\n{err}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"恢复失败: {e}")

    def delete_snapshot(self):
        if not self.vm_name or not self.vm_dir:
            QMessageBox.warning(self, "提示", "请先选择虚拟机")
            return
        item_text = self.snap_list_combo.currentText()
        if not item_text:
            QMessageBox.warning(self, "提示", "请选择快照")
            return
        name = item_text.split("(")[0].strip() if "(" in item_text else item_text.strip()
        if not name:
            QMessageBox.warning(self, "提示", "无法解析快照名称")
            return
        disk_path = self._get_disk_path()
        if not disk_path:
            QMessageBox.warning(self, "错误", "找不到磁盘文件")
            return
        if name.startswith("📄 "):
            file_name = name[2:].strip()
            snap_file = self.vm_dir / file_name
            if not snap_file.exists():
                QMessageBox.warning(self, "错误", f"找不到: {file_name}")
                return
            reply = QMessageBox.question(self, "确认删除",
                f"确定要删除快照文件吗？\n\n📁 {file_name}\n⚠️ 不可恢复！",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            try:
                snap_file.unlink()
                self.refresh_snapshot_list()
                QMessageBox.information(self, "成功", "快照已删除")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除失败: {e}")
        else:
            qemu_img = self._get_qemu_img()
            if not qemu_img:
                QMessageBox.warning(self, "错误", "找不到 qemu-img")
                return
            reply = QMessageBox.question(self, "确认删除",
                f"确定要删除快照 '{name}' 吗？\n\n⚠️ 不可恢复！",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            try:
                result = subprocess.run(
                    [str(qemu_img), "snapshot", "-d", name, str(disk_path)],
                    capture_output=True, text=True, encoding='utf-8', errors='ignore',
                    timeout=30
                )
                if result.returncode == 0:
                    self.refresh_snapshot_list()
                    QMessageBox.information(self, "成功", f"快照 '{name}' 已删除")
                else:
                    err = result.stderr or result.stdout
                    QMessageBox.warning(self, "错误", f"删除失败:\n{err}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除失败: {e}")

    def refresh_snapshot_list(self):
        self.snap_list_combo.clear()
        if not self.vm_name or not self.vm_dir:
            return
        disk_path = self._get_disk_path()
        if disk_path and disk_path.suffix.lower() == ".qcow2":
            qemu_img = self._get_qemu_img()
            if qemu_img:
                try:
                    result = subprocess.run(
                        [str(qemu_img), "snapshot", "-l", str(disk_path)],
                        capture_output=True, text=True, encoding='utf-8', errors='ignore',
                        timeout=15
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            line = line.strip()
                            if line and not line.startswith("Snapshot list") and not line.startswith("ID") and not line.startswith("---"):
                                parts = line.split()
                                if len(parts) >= 2:
                                    snap_name = parts[1]
                                    size = parts[3] if len(parts) > 3 else ""
                                    tag = parts[4] if len(parts) > 4 else ""
                                    display = f"{snap_name} ({size})"
                                    if tag == "VM":
                                        display += " [RAM]"
                                    self.snap_list_combo.addItem(display)
                except:
                    pass
        for f in self.vm_dir.glob("disk_*.qcow2"):
            if f.name == "disk.qcow2":
                continue
            if f.name.startswith("disk_before_restore_"):
                continue
            size_mb = f.stat().st_size / 1024 / 1024
            self.snap_list_combo.addItem(f"📄 {f.name} ({size_mb:.1f} MB)")

    # ============================================================
    # U盘 + HTTP
    # ============================================================
    def show_usb_dialog(self):
        drives = detect_removable_drives()
        if not drives:
            QMessageBox.information(self, "提示", "未检测到可移动磁盘")
            return
        if not self.vm_name:
            QMessageBox.warning(self, "提示", "请先选择虚拟机")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("💾 选择 U 盘")
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(200)
        dialog.setStyleSheet("background-color: #2b2b2b; color: #f0f0f0;")
        layout = QVBoxLayout(dialog)
        label = QLabel("选择要挂载的 U 盘：")
        layout.addWidget(label)
        list_widget = QListWidget()
        list_widget.setStyleSheet("background-color: #3c3c3c; color: #f0f0f0; border: 1px solid #555;")
        for d in drives:
            item = QListWidgetItem(f"{d['device']}  {d['name']}  ({d['size']})")
            item.setData(Qt.UserRole, d)
            list_widget.addItem(item)
        layout.addWidget(list_widget)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("✅ 挂载")
        ok_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        ok_btn.clicked.connect(lambda: self._mount_usb(list_widget, dialog))
        btn_layout.addWidget(ok_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("background-color: #666; color: white;")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        dialog.exec()

    def _mount_usb(self, list_widget, dialog):
        item = list_widget.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请选择一个磁盘")
            return
        drive_data = item.data(Qt.UserRole)
        device = drive_data['device']
        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "提示",
                "虚拟机正在运行，挂载需要重启虚拟机。\n是否继续？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        if not self.vm_dir:
            QMessageBox.warning(self, "错误", "找不到虚拟机目录")
            return
        config_file = self.vm_dir / "config.json"
        if not config_file.exists():
            return
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        disk_path = f"\\\\.\\{device}" if sys.platform == "win32" else device
        config['usb_disk_mounted'] = disk_path
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
        QMessageBox.information(self, "✅ U盘已挂载 + HTTP 服务已启动",
            f"U 盘 {device} 已挂载\n\n"
            f"📡 HTTP 服务地址:\n"
            f"  http://{host_ip}:8080\n"
            f"  http://10.0.2.2:8080")
        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "重启虚拟机",
                "是否立即重启虚拟机使 U 盘生效？",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.stop_vm()
                time.sleep(1)
                QTimer.singleShot(1000, self.launch)

    def remove_usb(self):
        if not self.vm_name or not self.vm_dir:
            return
        config_file = self.vm_dir / "config.json"
        if not config_file.exists():
            return
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if 'usb_disk_mounted' not in config:
            QMessageBox.information(self, "提示", "当前没有挂载 U 盘")
            return
        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "提示",
                "虚拟机正在运行，移除 U 盘需要重启虚拟机。\n是否继续？",
                QMessageBox.Yes | QMessageBox.No)
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
            reply = QMessageBox.question(self, "重启虚拟机",
                "是否立即重启虚拟机？",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.stop_vm()
                time.sleep(1)
                QTimer.singleShot(1000, self.launch)

    def toggle_http(self):
        if self.http_process and self.http_process.poll() is None:
            self.stop_http_server()
        else:
            if not self.vm_name or not self.vm_dir:
                QMessageBox.warning(self, "提示", "请先选择虚拟机")
                return
            config_file = self.vm_dir / "config.json"
            if not config_file.exists():
                return
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            share_dir = config.get('share_dir', '')
            if not share_dir or not Path(share_dir).exists():
                QMessageBox.warning(self, "提示", "没有可用的共享目录，请先挂载 U 盘")
                return
            self.start_http_server(f"{share_dir}\\")

    def start_http_server(self, path: str):
        if self.http_process and self.http_process.poll() is None:
            return
        try:
            self.http_process = subprocess.Popen(
                [sys.executable, "-m", "http.server", "8080", "-d", path],
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.http_btn.setText("⏹ HTTP")
            self.http_btn.setStyleSheet("background-color: #8a4a4a; color: white; font-weight: normal;")
            self.tray.update_menu(self.vm_name in running_vms, True)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"HTTP 启动失败: {e}")

    def stop_http_server(self):
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
        self.http_btn.setText("HTTP")
        self.http_btn.setStyleSheet("background-color: #3a6a3a; color: white; font-weight: normal;")
        self.tray.update_menu(self.vm_name in running_vms, False)

    def closeEvent(self, event):
        self.stop_pinning()
        self.stop_http_server()
        self.follow_timer.stop()
        self.tray.hide()
        for name, proc in list(running_vms.items()):
            try:
                proc.terminate()
                proc.waitForFinished(3000)
            except:
                pass
        running_vms.clear()
        event.accept()


# ============================================================
# 入口
# ============================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "错误", "系统托盘不可用")
        return
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    vm_name = sys.argv[1] if len(sys.argv) > 1 else None
    window = SidebarWindow(vm_name)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()