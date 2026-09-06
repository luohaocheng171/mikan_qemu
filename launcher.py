#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mikan QEMU 启动器 v13.2 - 侧边栏跟随 QEMU 窗口
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
from typing import Optional, List, Dict, Tuple

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

# ============================================================
# 配置
# ============================================================
BASE_DIR = Path(__file__).parent
VMS_DIR = BASE_DIR / "vms"
SHARE_DIR = BASE_DIR / "share"
SHARE_DIR.mkdir(parents=True, exist_ok=True)

running_vms: Dict[str, QProcess] = {}

# ============================================================
# Windows API
# ============================================================
if sys.platform == "win32":
    user32 = ctypes.windll.user32


def find_gtk_window(vm_name: str, timeout: float = 15.0) -> Optional[int]:
    """查找 QEMU GTK 窗口"""
    if sys.platform != "win32":
        return None
    
    try:
        import ctypes.wintypes
        import psutil
        
        found_hwnd = None
        
        gtk_class_names = [
            "gdkWindowToplevel",
            "gtk", "Gtk", "GDK",
            "QEMU", "qemu",
        ]
        
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
    """查找 QEMU SDL 窗口"""
    if sys.platform != "win32":
        return None
    
    try:
        import ctypes.wintypes
        import psutil
        
        found_hwnd = None
        
        sdl_class_names = [
            "SDL", "SDL_app", "SDL_window",
            "sdl", "qemu", "QEMU",
        ]
        
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
    """获取窗口位置和大小"""
    if sys.platform != "win32":
        return None
    try:
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    except:
        return None


def is_window_fullscreen(hwnd: int) -> bool:
    """检查窗口是否全屏"""
    if sys.platform != "win32":
        return False
    try:
        style = user32.GetWindowLongW(hwnd, -16)
        if not (style & 0x00C00000):
            return True
        return False
    except:
        return False


def align_sidebar_to_qemu(sidebar_hwnd: int, qemu_hwnd: int, sidebar_width: int):
    """将侧边栏对齐到 QEMU 窗口左侧"""
    if sys.platform != "win32":
        return
    
    try:
        qemu_rect = get_window_rect(qemu_hwnd)
        if not qemu_rect:
            return
        
        qemu_x, qemu_y, qemu_w, qemu_h = qemu_rect
        
        # 侧边栏位置 = QEMU 窗口左侧 - 侧边栏宽度
        sidebar_x = qemu_x - sidebar_width
        sidebar_y = qemu_y
        sidebar_h = qemu_h
        
        # 确保不超出屏幕左侧
        if sidebar_x < 0:
            sidebar_x = 0
        
        user32.SetWindowPos(
            sidebar_hwnd, None,
            sidebar_x, sidebar_y,
            sidebar_width, sidebar_h,
            0x0000
        )
        
    except Exception as e:
        print(f"⚠️ 对齐失败: {e}")


def bring_window_to_top(hwnd: int):
    """将窗口置顶并激活"""
    if sys.platform != "win32":
        return
    try:
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0004 | 0x0001)
        user32.SetForegroundWindow(hwnd)
    except:
        pass


# ============================================================
# QEMU 功能检测
# ============================================================
_qemu_features_cache: Dict[str, dict] = {}

def get_qemu_features(qemu_exe: Path) -> dict:
    exe_path = str(qemu_exe)
    if exe_path in _qemu_features_cache:
        return _qemu_features_cache[exe_path]
    
    features = {
        "grab_on_click": False,
        "window_size": False,
        "audiodev": False,
        "sdl": False,
        "gtk": False,
        "qmp": False,
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
            if "window-size" in output:
                features["window_size"] = True
            if "sdl" in output:
                features["sdl"] = True
            if "gtk" in output:
                features["gtk"] = True
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
            [str(qemu_exe), "-qmp", "help"],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=5
        )
        if result.returncode == 0:
            features["qmp"] = True
    except:
        pass
    
    _qemu_features_cache[exe_path] = features
    return features


# ============================================================
# QEMU 版本识别
# ============================================================
def get_qemu_year(qemu_version: str) -> int:
    match = re.search(r'(20[1-9][0-9])', qemu_version)
    if match:
        year = int(match.group(1))
        if 2011 <= year <= 2026:
            return year
    return 2020


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
        "x86": ["qemu-system-i386.exe", "qemu-system-i386"],
        "ARM64": ["qemu-system-aarch64.exe", "qemu-system-aarch64"],
        "ARM": ["qemu-system-arm.exe", "qemu-system-arm"],
        "RISC-V": ["qemu-system-riscv64.exe", "qemu-system-riscv64"],
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
# 构建命令
# ============================================================
def build_command(config: dict, display_type: str = "gtk") -> Tuple[Optional[List[str]], Optional[str]]:
    vm_name = config.get('name', 'vm')
    arch = config.get('arch', 'x86_64')
    qemu_ver = config.get('qemu_version', '')
    year = get_qemu_year(qemu_ver)

    qemu_exe = get_qemu_exe(qemu_ver, arch)
    if not qemu_exe:
        return None, f"找不到 QEMU: {qemu_ver}"

    qemu_features = get_qemu_features(qemu_exe)
    arch_defaults = get_arch_defaults(arch)
    
    if display_type == "sdl" and not qemu_features.get("sdl", False):
        display_type = "gtk"
    elif display_type == "gtk" and not qemu_features.get("gtk", False):
        display_type = "sdl"
    
    cmd = [str(qemu_exe)]

    memory = config.get('memory', 1024)
    cmd.extend(["-m", str(memory)])

    cpu = config.get('cpu', 2)
    threads = config.get('smp_threads', 1)
    sockets = config.get('smp_sockets', 1)
    cmd.extend(["-smp", f"cores={cpu},threads={threads},sockets={sockets}"])

    cpu_model = config.get('cpu_model', 'host')
    if year <= 2013:
        cpu_model = "qemu32" if arch in ["x86", "x86_64"] else arch_defaults.get("cpu", "host")
    elif year <= 2016:
        cpu_model = "qemu64" if arch in ["x86", "x86_64"] else arch_defaults.get("cpu", "host")
    else:
        cpu_model = arch_defaults.get("cpu", "host")
    cmd.extend(["-cpu", cpu_model])

    disk_path = VMS_DIR / vm_name / f"disk.{config.get('disk_format', 'qcow2')}"
    if disk_path.exists():
        interface = config.get('disk_interface', 'sata')
        cmd.extend(["-drive", f"file={disk_path},format={config.get('disk_format', 'qcow2')},if={interface}"])

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

    machine = config.get('machine_type', 'auto')
    if machine == "auto":
        machine = arch_defaults.get("machine", "q35") if year >= 2020 else arch_defaults.get("machine", "pc")
    cmd.extend(["-machine", machine])

    vga = config.get('vga', 'auto')
    if vga == "auto":
        if year <= 2013:
            vga = "cirrus" if arch in ["x86", "x86_64"] else arch_defaults.get("vga", "std")
        elif year <= 2016:
            vga = "std" if arch in ["x86", "x86_64"] else arch_defaults.get("vga", "std")
        else:
            vga = arch_defaults.get("vga", "virtio")
    if vga != "none":
        cmd.extend(["-vga", vga])

    resolution = config.get('resolution', '')
    display_params = ["-display", display_type]
    if resolution and resolution != "自定义" and qemu_features.get("window_size", False):
        display_params[1] += f",window-size={resolution}"
    if qemu_features.get("grab_on_click", False):
        display_params[1] += ",grab-on-click=on"
    cmd.extend(display_params)

    sound = config.get('sound', 'hda')
    if sound != "none":
        if qemu_features.get("audiodev", False):
            cmd.extend(["-audiodev", "wav,id=audio0"])
            cmd.extend(["-device", "intel-hda,audiodev=audio0"])
        else:
            cmd.extend(["-soundhw", "hda"])

    if config.get('usb', True):
        cmd.extend(["-usb", "-device", "usb-tablet"])

    nic_model = config.get('nic_model', 'e1000')
    netdev = "user,id=net0"
    if share_dir and Path(share_dir).exists():
        netdev += f",smb={share_dir}"
    cmd.extend(["-netdev", netdev])
    if nic_model == "virtio":
        cmd.extend(["-device", "virtio-net-pci,netdev=net0"])
    else:
        cmd.extend(["-device", f"{nic_model},netdev=net0"])

    accel = config.get('accel', 'tcg')
    if accel != "tcg":
        if year <= 2016:
            cmd.extend(["-enable-kvm"])
        else:
            cmd.extend(["-accel", accel])

    qmp_socket = config.get('qmp_socket', '')
    if qmp_socket and qemu_features.get("qmp", False):
        cmd.extend(["-qmp", f"unix:{qmp_socket},server,nowait"])

    return cmd, None


# ============================================================
# 创建托盘图标
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


# ============================================================
# 系统托盘图标
# ============================================================
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
        
        # 定时检查 QEMU 全屏状态
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
# 侧边栏窗口 - 跟随 QEMU
# ============================================================
class SidebarWindow(QWidget):
    def __init__(self, vm_name: str = None):
        super().__init__()
        self.vm_name = vm_name
        self.config = None
        self.cmd = None
        self.process: Optional[QProcess] = None
        self.http_process = None
        
        # 吸附相关
        self.display_hwnd = None
        self.find_timer = None
        self.find_attempts = 0
        self.sidebar_width = 280
        self.min_width = 180
        self.max_width = 500
        
        self.display_type = "gtk"
        self.display_mode = "attach"
        
        # 系统托盘
        self.tray = TrayIcon(self)
        self.tray.show()
        
        self.init_ui()
        
        if vm_name:
            self.load_config(vm_name)
            self.update_display()
        
        self.refresh_vm_list()
        
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.closeEvent = self.hide_event
        
        # 定时器：持续跟随 QEMU 窗口
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
            QWidget {
                background-color: #1a1a1a;
                color: #f0f0f0;
            }
            QLabel {
                color: #ddd;
                font-family: "Microsoft YaHei";
                font-size: 12px;
            }
            QComboBox {
                background-color: #2b2b2b;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: "Microsoft YaHei";
                min-height: 26px;
            }
            QPushButton {
                font-family: "Microsoft YaHei";
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666;
            }
            QGroupBox {
                color: #ddd;
                border: 1px solid #333;
                border-radius: 4px;
                margin-top: 6px;
                padding-top: 6px;
                font-family: "Microsoft YaHei";
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #aaa;
                font-size: 11px;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #2b2b2b;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #5a5a5a;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #6a6a6a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
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
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #2a2a2a; color: #666; }
        """)
        self.launch_btn.clicked.connect(self.launch)
        btn_layout.addWidget(self.launch_btn)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setMinimumHeight(38)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 14px;
            }
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

        layout.addStretch()

        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        # 右侧调整大小手柄
        self.resize_handle = QFrame(self)
        self.resize_handle.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
            QFrame:hover {
                background-color: #3a6a8a;
            }
        """)
        self.resize_handle.setCursor(Qt.SplitHCursor)
        self.resize_handle.setFixedWidth(4)
        self.resize_handle.raise_()
        
        self.mousePressEvent = self.on_sidebar_click
        
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.on_resize_finished)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_handle.setGeometry(self.width() - 4, 0, 4, self.height())
        self.sidebar_width = self.width()

    def on_resize_finished(self):
        pass  # 不再需要

    def on_sidebar_click(self, event):
        if self.display_hwnd and self.display_mode == "attach":
            bring_window_to_top(self.display_hwnd)
        event.accept()

    # ============================================================
    # 跟随 QEMU 窗口 - 核心逻辑
    # ============================================================
    def follow_qemu(self):
        """持续跟随 QEMU 窗口位置"""
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
            
            # 计算侧边栏应该的位置
            target_x = qemu_x - self.sidebar_width
            target_y = qemu_y
            target_h = qemu_h
            
            # 不超出屏幕左侧
            if target_x < 0:
                target_x = 0
            
            # 获取当前侧边栏位置
            current_rect = get_window_rect(int(self.winId()))
            if not current_rect:
                return
            
            current_x, current_y, current_w, current_h = current_rect
            
            # 如果位置或大小变化超过阈值，才移动
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
        if name:
            self.vm_name = name
            self.setWindowTitle(f"🧲 Mikan QEMU - {name}")
            self.load_config(name)
            self.update_display()

    def load_config(self, vm_name: str):
        config_file = VMS_DIR / vm_name / "config.json"
        if not config_file.exists():
            return
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.cmd, error = build_command(self.config, display_type=self.display_type)
        if error:
            print(f"❌ {error}")

    def update_display(self):
        if not self.config or not self.cmd:
            return
        
        arch = self.config.get('arch', 'x86_64')
        memory = self.config.get('memory', 1024)
        cpu = self.config.get('cpu', 2)
        
        info_text = f"{arch} | {memory}MB | {cpu}核 | {self.display_type.upper()}"
        self.info_label.setText(info_text)
        
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
        if self.config:
            self.cmd, error = build_command(self.config, display_type=self.display_type)
            if error:
                print(f"❌ {error}")
            else:
                self.update_display()

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

    # ============================================================
    # 查找 QEMU 窗口
    # ============================================================
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
        
        # 立即执行一次跟随，让侧边栏对齐到 QEMU
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
    # 启动/停止
    # ============================================================
    def launch(self):
        global running_vms
        vm_name = self.vm_combo.currentText()
        if not vm_name:
            QMessageBox.warning(self, "提示", "请选择虚拟机")
            return
        
        self.load_config(vm_name)
        if not self.cmd:
            QMessageBox.warning(self, "错误", "无法构建命令")
            return
        
        if vm_name in running_vms:
            QMessageBox.warning(self, "提示", f"虚拟机 {vm_name} 已在运行中")
            return

        self.launch_btn.setEnabled(False)
        self.status_label.setText("● 启动中...")
        self.status_label.setStyleSheet("color: #FFA500; font-size: 12px; padding: 4px 0;")

        try:
            qemu_exe = Path(self.cmd[0])
            qemu_dir = qemu_exe.parent
            args = self.cmd[1:]

            self.process = QProcess()
            self.process.setProgram(str(qemu_exe))
            self.process.setArguments(args)
            self.process.setWorkingDirectory(str(qemu_dir))

            self.process.finished.connect(self.on_process_finished)
            self.process.errorOccurred.connect(self.on_process_error)

            self.process.start()
            if self.process.waitForStarted(3000):
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

    def on_process_error(self, error):
        self.launch_btn.setEnabled(True)
        QMessageBox.warning(self, "错误", f"进程错误: {error}")

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
        if self.cmd:
            QApplication.clipboard().setText(" ".join(self.cmd))
            QMessageBox.information(self, "成功", "命令已复制到剪贴板")

    # ============================================================
    # 快照
    # ============================================================
    def create_snapshot(self):
        if not self.vm_name:
            QMessageBox.warning(self, "提示", "请先选择虚拟机")
            return
        
        name = self.snap_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入快照名称")
            return
        
        if self.vm_name in running_vms:
            reply = QMessageBox.question(self, "提示", 
                "创建快照需要关闭虚拟机。\n是否关闭虚拟机并创建快照？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            self.stop_vm()
            time.sleep(2)
        
        try:
            vm_dir = VMS_DIR / self.vm_name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            disk_path = vm_dir / f"disk.{self.config.get('disk_format', 'qcow2')}"
            if not disk_path.exists():
                QMessageBox.warning(self, "错误", f"找不到磁盘文件")
                return
            
            backup_name = f"disk_{name}_{timestamp}.qcow2"
            backup_path = vm_dir / backup_name
            
            shutil.copy2(disk_path, backup_path)
            
            self.snap_name_edit.clear()
            self.refresh_snapshot_list()
            
            QMessageBox.information(self, "✅ 快照创建成功", 
                f"快照名称: {name}\n📄 文件: {backup_name}")
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"快照创建失败: {e}")

    def restore_snapshot(self):
        if not self.vm_name:
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
                "恢复快照需要关闭虚拟机。\n是否关闭虚拟机并恢复？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            self.stop_vm()
            time.sleep(2)
        
        vm_dir = VMS_DIR / self.vm_name
        disk_path = vm_dir / f"disk.{self.config.get('disk_format', 'qcow2')}"
        
        snapshot_files = []
        for f in vm_dir.glob(f"disk_{name}_*.qcow2"):
            if f.name != "disk.qcow2" and not f.name.startswith("disk_before_restore_"):
                snapshot_files.append(f)
        
        if not snapshot_files:
            QMessageBox.warning(self, "错误", f"找不到快照 '{name}'")
            return
        
        selected_path = snapshot_files[0]
        if len(snapshot_files) > 1:
            items = [f.name for f in snapshot_files]
            selected, ok = QInputDialog.getItem(
                self, "选择快照文件", 
                "找到多个快照文件，请选择：", 
                items, 0, False
            )
            if not ok or not selected:
                return
            selected_path = vm_dir / selected
        
        reply = QMessageBox.question(self, "确认恢复", 
            f"确定要从快照恢复吗？\n\n"
            f"📁 快照文件: {selected_path.name}\n"
            f"⚠️ 当前磁盘将被覆盖！",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        
        try:
            backup = vm_dir / f"disk_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.qcow2"
            shutil.copy2(disk_path, backup)
            shutil.copy2(selected_path, disk_path)
            
            self.refresh_snapshot_list()
            QMessageBox.information(self, "✅ 恢复成功", 
                f"恢复前磁盘已备份到:\n{backup.name}")
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"恢复失败: {e}")

    def delete_snapshot(self):
        if not self.vm_name:
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
        
        vm_dir = VMS_DIR / self.vm_name
        files_to_delete = []
        for f in vm_dir.glob(f"disk_{name}_*.qcow2"):
            if f.name != "disk.qcow2" and not f.name.startswith("disk_before_restore_"):
                files_to_delete.append(f)
        
        if not files_to_delete:
            QMessageBox.warning(self, "错误", f"找不到快照 '{name}'")
            return
        
        file_list = "\n".join(f"  - {f.name}" for f in files_to_delete)
        reply = QMessageBox.question(self, "确认删除", 
            f"确定要删除快照 '{name}' 吗？\n\n"
            f"将删除以下文件：\n{file_list}\n"
            f"⚠️ 此操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        
        try:
            for f in files_to_delete:
                f.unlink()
            self.refresh_snapshot_list()
            QMessageBox.information(self, "成功", f"快照 '{name}' 已删除")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"删除失败: {e}")

    def refresh_snapshot_list(self):
        self.snap_list_combo.clear()
        if not self.vm_name:
            return
        
        vm_dir = VMS_DIR / self.vm_name
        snapshots = []
        
        for f in vm_dir.glob("disk_*.qcow2"):
            if f.name == "disk.qcow2":
                continue
            if f.name.startswith("disk_before_restore_"):
                continue
            name = f.stem.replace("disk_", "")
            name = re.sub(r'_\d{8}_\d{6}$', '', name)
            size_mb = f.stat().st_size / 1024 / 1024
            snapshots.append((f.stat().st_mtime, f"{name} ({size_mb:.1f} MB)"))
        
        snapshots.sort(key=lambda x: x[0], reverse=True)
        for _, display in snapshots:
            self.snap_list_combo.addItem(display)

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
                f"虚拟机正在运行，挂载需要重启虚拟机。\n是否继续？", 
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        config_file = VMS_DIR / self.vm_name / "config.json"
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
        if not self.vm_name:
            return
        config_file = VMS_DIR / self.vm_name / "config.json"
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
            if not self.vm_name:
                QMessageBox.warning(self, "提示", "请先选择虚拟机")
                return
            config_file = VMS_DIR / self.vm_name / "config.json"
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

    # ============================================================
    # 关闭
    # ============================================================
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