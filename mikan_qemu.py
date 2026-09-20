#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mikan QEMU Manager v5.5 - VMware风格UI
完整功能版 + 硬件配置管理 + 网络模式 + 自定义路径 + 内存磁盘 + 硬件直通 + 多文件夹 + 搜索
"""

import os
import sys
import subprocess
import importlib
import json
import shutil
import zipfile
import tempfile
import time
import re
import socket
import shlex
import ctypes
import glob
import platform
import webbrowser
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from threading import Thread
from collections import defaultdict

# ============================================================
# 自动依赖检查和安装
# ============================================================
def check_and_install_dependencies():
    required_packages = {
        "PySide6": "PySide6",
        "psutil": "psutil",
    }
    missing_packages = []
    installed_packages = []
    print("=" * 60)
    print("🔍 检查依赖包...")
    print("=" * 60)
    for package, import_name in required_packages.items():
        try:
            importlib.import_module(import_name)
            installed_packages.append(package)
            print(f"✅ {package} 已安装")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package} 未安装")
    if missing_packages:
        print("\n" + "=" * 60)
        print(f"📦 正在安装缺失的 {len(missing_packages)} 个依赖包...")
        print("=" * 60)
        for package in missing_packages:
            print(f"⬇️ 正在安装 {package}...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", package],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                print(f"✅ {package} 安装成功")
            except subprocess.CalledProcessError as e:
                print(f"❌ {package} 安装失败: {e}")
                print(f"   请手动安装: pip install {package}")
                return False
        for package, import_name in required_packages.items():
            try:
                importlib.import_module(import_name)
                print(f"✅ {package} 验证通过")
            except ImportError:
                print(f"❌ {package} 仍然无法导入")
                return False
    print("\n" + "=" * 60)
    print("✅ 所有依赖检查通过！")
    print("=" * 60)
    return True

if not check_and_install_dependencies():
    print("\n⚠️ 依赖安装失败，请手动安装后重新运行")
    print("   pip install PySide6 psutil")
    input("\n按回车键退出...")
    sys.exit(1)

# ============================================================
# 导入依赖
# ============================================================
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
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

# ========== 配置 ==========
BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = CONFIG_DIR / "settings.json"
FOLDERS_FILE = CONFIG_DIR / "folders.json"

DEFAULT_WORKSPACE = BASE_DIR

SUBDIR_VMS = "vms"
SUBDIR_ISO = "iso"
SUBDIR_SNAPSHOTS = "snapshots"
SUBDIR_EXPORTS = "exports"
SUBDIR_SHARE = "share"
SUBDIR_HW_PROFILES = "hardware_profiles"

VMS_DIR = DEFAULT_WORKSPACE / SUBDIR_VMS
ISO_DIR = DEFAULT_WORKSPACE / SUBDIR_ISO
SNAPSHOTS_DIR = DEFAULT_WORKSPACE / SUBDIR_SNAPSHOTS
EXPORT_DIR = DEFAULT_WORKSPACE / SUBDIR_EXPORTS
SHARE_DIR = DEFAULT_WORKSPACE / SUBDIR_SHARE
HARDWARE_PROFILES_DIR = DEFAULT_WORKSPACE / SUBDIR_HW_PROFILES
CUSTOM_HARDWARE_DIR = HARDWARE_PROFILES_DIR / "custom"

FOLDERS_CONFIG = {"folders": [], "active_index": 0}


def load_folders_config():
    global FOLDERS_CONFIG
    if FOLDERS_FILE.exists():
        try:
            with open(FOLDERS_FILE, 'r', encoding='utf-8') as f:
                FOLDERS_CONFIG = json.load(f)
            if "folders" not in FOLDERS_CONFIG:
                FOLDERS_CONFIG = {"folders": [], "active_index": 0}
        except Exception as e:
            print(f"加载文件夹配置失败: {e}")
            FOLDERS_CONFIG = {"folders": [], "active_index": 0}
    if not FOLDERS_CONFIG.get("folders"):
        FOLDERS_CONFIG = {
            "folders": [{
                "name": "程序目录",
                "path": str(DEFAULT_WORKSPACE),
                "qemu_path": ""
            }],
            "active_index": 0
        }
    return FOLDERS_CONFIG


def save_folders_config():
    try:
        with open(FOLDERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(FOLDERS_CONFIG, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"保存文件夹配置失败: {e}")


def apply_active_folder():
    global VMS_DIR, ISO_DIR, SNAPSHOTS_DIR, EXPORT_DIR, SHARE_DIR
    global HARDWARE_PROFILES_DIR, CUSTOM_HARDWARE_DIR
    folders = FOLDERS_CONFIG.get("folders", [])
    idx = FOLDERS_CONFIG.get("active_index", 0)
    if not folders or idx >= len(folders):
        return
    base = Path(folders[idx].get("path", str(DEFAULT_WORKSPACE)))
    VMS_DIR = base / SUBDIR_VMS
    ISO_DIR = base / SUBDIR_ISO
    SNAPSHOTS_DIR = base / SUBDIR_SNAPSHOTS
    EXPORT_DIR = base / SUBDIR_EXPORTS
    SHARE_DIR = base / SUBDIR_SHARE
    HARDWARE_PROFILES_DIR = base / SUBDIR_HW_PROFILES
    CUSTOM_HARDWARE_DIR = HARDWARE_PROFILES_DIR / "custom"
    for d in [VMS_DIR, ISO_DIR, SNAPSHOTS_DIR, EXPORT_DIR, SHARE_DIR,
              HARDWARE_PROFILES_DIR, CUSTOM_HARDWARE_DIR]:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"创建目录失败 {d}: {e}")


def get_active_folder() -> dict:
    folders = FOLDERS_CONFIG.get("folders", [])
    idx = FOLDERS_CONFIG.get("active_index", 0)
    if folders and 0 <= idx < len(folders):
        return folders[idx]
    return {"name": "程序目录", "path": str(DEFAULT_WORKSPACE), "qemu_path": ""}


def get_active_qemu_dir() -> str:
    return get_active_folder().get("qemu_path", "")


def load_settings():
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载设置失败: {e}")
    return {}


def save_settings(settings: dict):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"保存设置失败: {e}")


load_folders_config()
load_settings()
apply_active_folder()

APP_VERSION = "5.5"
CONFIG_VERSION = "5.5"

GITHUB_URL = "https://github.com/luohaocheng171/mikan_qemu"

# ============================================================
# 硬件配置预设数据（内置）
# ============================================================
BUILTIN_HARDWARE_PROFILES = {
    "retro_2011": {
        "year": 2011, "cpu_model": "Nehalem", "cpu_flags": "+aes,+avx",
        "vga": "cirrus", "sound": "sb16", "nic": "rtl8139",
        "disk_interface": "ide", "machine": "pc", "accel": "tcg",
        "display": "gtk", "usb_controller": "piix3-usb-uhci",
        "description": "2011年复古硬件配置 (XP/98)"
    },
    "retro_2013": {
        "year": 2013, "cpu_model": "SandyBridge", "cpu_flags": "+aes,+avx,+rdrand,+f16c",
        "vga": "std", "sound": "ac97", "nic": "e1000",
        "disk_interface": "ide", "machine": "pc", "accel": "tcg",
        "display": "gtk", "usb_controller": "usb-ehci",
        "description": "2013年硬件配置 (Win7)"
    },
    "transition_2016": {
        "year": 2016, "cpu_model": "Skylake-Client",
        "cpu_flags": "+aes,+avx,+avx2,+bmi1,+bmi2,+f16c,+fma,+rdrand,+rdseed,+sha-ni,+xsave,+xsavec,+xsaves",
        "vga": "std", "sound": "ac97", "nic": "e1000",
        "disk_interface": "sata", "machine": "pc", "accel": "tcg",
        "display": "gtk", "usb_controller": "usb-ehci",
        "description": "2016年过渡配置 (Win7/8.1)"
    },
    "modern_2019": {
        "year": 2019, "cpu_model": "CascadeLake",
        "cpu_flags": "+aes,+avx,+avx2,+avx512f,+avx512bw,+avx512cd,+avx512dq,+avx512vl,+bmi1,+bmi2,+f16c,+fma,+rdrand,+rdseed,+sha-ni,+xsave,+xsavec,+xsaves",
        "vga": "virtio", "sound": "hda", "nic": "virtio",
        "disk_interface": "virtio", "machine": "q35", "accel": "hax",
        "display": "gtk", "usb_controller": "usb-ehci",
        "description": "2019年现代配置 (Win10)"
    },
    "latest_2024": {
        "year": 2024, "cpu_model": "host",
        "cpu_flags": "+aes,+avx,+avx2,+avx512f,+avx512bw,+avx512cd,+avx512dq,+avx512vl,+bmi1,+bmi2,+f16c,+fma,+rdrand,+rdseed,+sha-ni,+xsave,+xsavec,+xsaves",
        "vga": "virtio", "sound": "hda", "nic": "virtio",
        "disk_interface": "virtio", "machine": "q35", "accel": "hax",
        "display": "gtk", "usb_controller": "usb-xhci",
        "description": "2024年最新配置 (Win10/11)"
    },
    "epyc_2023": {
        "year": 2023, "cpu_model": "EPYC",
        "cpu_flags": "+aes,+avx,+avx2,+avx512f,+avx512bw,+avx512cd,+avx512dq,+avx512vl,+bmi1,+bmi2,+f16c,+fma,+rdrand,+rdseed,+sha-ni,+xsave,+xsavec,+xsaves",
        "vga": "virtio", "sound": "hda", "nic": "virtio",
        "disk_interface": "virtio", "machine": "q35", "accel": "hax",
        "display": "gtk", "usb_controller": "usb-xhci",
        "description": "AMD EPYC 服务器配置"
    },
    "minimal": {
        "year": 2020, "cpu_model": "qemu64", "cpu_flags": "",
        "vga": "none", "sound": "none", "nic": "e1000",
        "disk_interface": "ide", "machine": "pc", "accel": "tcg",
        "display": "none", "usb_controller": "none",
        "description": "最小化配置 (无图形/声音)"
    },
    "macos": {
        "year": 2020, "cpu_model": "host",
        "cpu_flags": "+aes,+avx,+avx2,+bmi1,+bmi2,+f16c,+fma,+rdrand,+rdseed,+sha-ni,+xsave,+xsavec,+xsaves",
        "vga": "vmvga", "sound": "hda", "nic": "e1000",
        "disk_interface": "sata", "machine": "q35", "accel": "hvf",
        "display": "gtk", "usb_controller": "usb-xhci",
        "description": "macOS 专用配置 (需要 HVF)"
    },
    "android": {
        "year": 2019, "cpu_model": "qemu64", "cpu_flags": "+aes,+avx,+rdrand",
        "vga": "std", "sound": "none", "nic": "e1000",
        "disk_interface": "ide", "machine": "pc", "accel": "tcg",
        "display": "gtk", "usb_controller": "usb-ehci",
        "description": "Android x86 专用配置"
    },
    "linux_server": {
        "year": 2020, "cpu_model": "host",
        "cpu_flags": "+aes,+avx,+avx2,+bmi1,+bmi2,+f16c,+fma,+rdrand,+rdseed,+sha-ni,+xsave,+xsavec,+xsaves",
        "vga": "none", "sound": "none", "nic": "virtio",
        "disk_interface": "virtio", "machine": "q35", "accel": "kvm",
        "display": "none", "usb_controller": "none",
        "description": "Linux 服务器 (无图形界面)"
    },
}


class HardwareProfileManager:
    """硬件配置文件管理器"""
    def __init__(self):
        self.profiles = {}
        self._ensure_dirs()
        self.load_all()
    
    def _ensure_dirs(self):
        HARDWARE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        CUSTOM_HARDWARE_DIR.mkdir(parents=True, exist_ok=True)
    
    def load_all(self):
        self.profiles = {}
        for name, data in BUILTIN_HARDWARE_PROFILES.items():
            self.profiles[name] = {"name": name, "is_builtin": True, **data}
        for json_file in CUSTOM_HARDWARE_DIR.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    name = data.get("name", json_file.stem)
                    if name in self.profiles and self.profiles[name].get("is_builtin", False):
                        continue
                    self.profiles[name] = {
                        "name": name, "is_builtin": False,
                        "file_path": str(json_file), **data
                    }
            except Exception as e:
                print(f"加载失败 {json_file}: {e}")
    
    def get_all_names(self) -> List[str]:
        builtin = [n for n, d in self.profiles.items() if d.get("is_builtin", False)]
        custom = [n for n, d in self.profiles.items() if not d.get("is_builtin", False)]
        builtin.sort(key=lambda n: self.profiles[n].get("year", 0))
        custom.sort(key=lambda n: self.profiles[n].get("year", 0))
        return builtin + custom
    
    def get_profile(self, name):
        return self.profiles.get(name)
    
    def is_builtin(self, name):
        profile = self.get_profile(name)
        return profile is not None and profile.get("is_builtin", False)
    
    def create_profile(self, name, data):
        if not name or name in self.profiles:
            return False
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        data["name"] = name
        file_path = CUSTOM_HARDWARE_DIR / f"{safe_name}.json"
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.profiles[name] = {"name": name, "is_builtin": False, "file_path": str(file_path), **data}
            return True
        except Exception as e:
            print(f"保存失败: {e}")
            return False
    
    def update_profile(self, name, data):
        if name not in self.profiles or self.profiles[name].get("is_builtin", False):
            return False
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        data["name"] = name
        file_path = CUSTOM_HARDWARE_DIR / f"{safe_name}.json"
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.profiles[name].update(data)
            return True
        except Exception as e:
            print(f"更新失败: {e}")
            return False
    
    def delete_profile(self, name):
        if name not in self.profiles or self.profiles[name].get("is_builtin", False):
            return False
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        file_path = CUSTOM_HARDWARE_DIR / f"{safe_name}.json"
        try:
            if file_path.exists():
                file_path.unlink()
            del self.profiles[name]
            return True
        except:
            return False
    
    def apply_to_vm(self, profile_name, vm):
        profile = self.get_profile(profile_name)
        if not profile:
            return
        field_mapping = {
            "cpu_model": "cpu_model", "cpu_flags": "cpu_flags",
            "vga": "vga", "sound": "sound", "nic": "nic_model",
            "disk_interface": "disk_interface", "machine": "machine_type",
            "accel": "accel", "display": "display",
            "usb_controller": "custom_usb_controller",
        }
        for src, dst in field_mapping.items():
            if src in profile and profile[src] is not None:
                setattr(vm, dst, profile[src])
        if profile.get("vga") == "none":
            vm.opengl = False
        if profile.get("display") == "none":
            vm.display = "none"


FORCE_CPU_MODELS = [
    "host", "qemu64", "qemu32", "core2duo", "phenom",
    "Opteron_G1", "Opteron_G2", "Opteron_G3", "Opteron_G4", "Opteron_G5",
    "EPYC", "EPYC-Rome", "EPYC-Milan", "EPYC-Genoa",
    "Skylake-Client", "Skylake-Server", "CascadeLake", "Cooperlake",
    "Icelake-Client", "Icelake-Server", "SapphireRapids", "GraniteRapids",
    "Nehalem", "Nehalem-IBRS", "Westmere", "Westmere-IBRS",
    "SandyBridge", "SandyBridge-IBRS", "Haswell", "Haswell-IBRS",
    "Haswell-noTSX", "Haswell-noTSX-IBRS", "Broadwell", "Broadwell-IBRS",
    "Broadwell-noTSX", "Broadwell-noTSX-IBRS", "Denverton", "Snowridge",
    "Penryn", "Conroe", "n270", "atom", "max",
]

class HardwareProfileEditDialog(QDialog):
    def __init__(self, parent=None, profile_name=None, manager=None):
        super().__init__(parent)
        self.manager = manager or HardwareProfileManager()
        self.profile_name = profile_name
        self.is_edit = profile_name is not None
        self.init_ui()
        if self.is_edit:
            self.setWindowTitle(f"✏️ 编辑硬件配置: {profile_name}")
            data = self.manager.get_profile(profile_name)
            if data:
                self.load_data(data)
            else:
                self.reject()
        else:
            self.setWindowTitle("📦 新建硬件配置")
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)
        tabs = QTabWidget()
        
        basic_tab = QWidget()
        basic_layout = QGridLayout(basic_tab)
        row = 0
        basic_layout.addWidget(QLabel("配置名称:"), row, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如: my_gaming_config")
        basic_layout.addWidget(self.name_edit, row, 1)
        row += 1
        basic_layout.addWidget(QLabel("年份标签:"), row, 0)
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2011, 2030)
        self.year_spin.setValue(2024)
        basic_layout.addWidget(self.year_spin, row, 1)
        row += 1
        basic_layout.addWidget(QLabel("描述:"), row, 0)
        self.desc_edit = QLineEdit()
        basic_layout.addWidget(self.desc_edit, row, 1)
        basic_layout.setRowStretch(row + 1, 1)
        tabs.addTab(basic_tab, "📋 基本信息")
        
        cpu_tab = QWidget()
        cpu_layout = QGridLayout(cpu_tab)
        row = 0
        cpu_layout.addWidget(QLabel("CPU 型号:"), row, 0)
        self.cpu_model_combo = QComboBox()
        self.cpu_model_combo.addItems(FORCE_CPU_MODELS)
        self.cpu_model_combo.setEditable(True)
        cpu_layout.addWidget(self.cpu_model_combo, row, 1)
        row += 1
        cpu_layout.addWidget(QLabel("指令集标志:"), row, 0)
        self.cpu_flags_edit = QLineEdit()
        cpu_layout.addWidget(self.cpu_flags_edit, row, 1)
        cpu_layout.setRowStretch(row + 1, 1)
        tabs.addTab(cpu_tab, "🖥️ CPU")
        
        gpu_tab = QWidget()
        gpu_layout = QGridLayout(gpu_tab)
        row = 0
        gpu_layout.addWidget(QLabel("显卡型号:"), row, 0)
        self.vga_combo = QComboBox()
        self.vga_combo.addItems(["virtio", "std", "cirrus", "vmvga", "qxl", "none", "bochs", "ramfb", "sga"])
        self.vga_combo.setEditable(True)
        gpu_layout.addWidget(self.vga_combo, row, 1)
        row += 1
        gpu_layout.addWidget(QLabel("显示后端:"), row, 0)
        self.display_combo = QComboBox()
        self.display_combo.addItems(["gtk", "sdl", "none", "curses", "spice", "egl-headless"])
        self.display_combo.setEditable(True)
        gpu_layout.addWidget(self.display_combo, row, 1)
        gpu_layout.setRowStretch(row + 1, 1)
        tabs.addTab(gpu_tab, "🖥️ 显卡/显示")
        
        audio_net_tab = QWidget()
        audio_net_layout = QGridLayout(audio_net_tab)
        row = 0
        audio_net_layout.addWidget(QLabel("声卡型号:"), row, 0)
        self.sound_combo = QComboBox()
        self.sound_combo.addItems(["hda", "ac97", "sb16", "ich9-intel-hda", "none", "cs4231a", "gus", "intel-hda", "isa", "pcspk", "pl041"])
        self.sound_combo.setEditable(True)
        audio_net_layout.addWidget(self.sound_combo, row, 1)
        row += 1
        audio_net_layout.addWidget(QLabel("网卡型号:"), row, 0)
        self.nic_combo = QComboBox()
        self.nic_combo.addItems(["virtio", "e1000", "rtl8139", "pcnet", "e1000e", "vmxnet3", "usb-net", "ne2k_pci"])
        self.nic_combo.setEditable(True)
        audio_net_layout.addWidget(self.nic_combo, row, 1)
        audio_net_layout.setRowStretch(row + 1, 1)
        tabs.addTab(audio_net_tab, "🔊 声音/网络")
        
        board_tab = QWidget()
        board_layout = QGridLayout(board_tab)
        row = 0
        board_layout.addWidget(QLabel("机器类型:"), row, 0)
        self.machine_combo = QComboBox()
        self.machine_combo.addItems(["pc", "q35", "pc-i440fx-11.1", "pc-i440fx-9.2", "pc-q35-11.1", "pc-q35-9.2", "virt", "microvm"])
        self.machine_combo.setEditable(True)
        board_layout.addWidget(self.machine_combo, row, 1)
        row += 1
        board_layout.addWidget(QLabel("磁盘接口:"), row, 0)
        self.disk_interface_combo = QComboBox()
        self.disk_interface_combo.addItems(["ide", "sata", "virtio", "scsi", "nvme", "usb", "sd", "floppy"])
        board_layout.addWidget(self.disk_interface_combo, row, 1)
        row += 1
        board_layout.addWidget(QLabel("加速模式:"), row, 0)
        self.accel_combo = QComboBox()
        self.accel_combo.addItems(["tcg", "hax", "whpx", "kvm", "hvf", "qtest", "none"])
        board_layout.addWidget(self.accel_combo, row, 1)
        row += 1
        board_layout.addWidget(QLabel("USB 控制器:"), row, 0)
        self.usb_controller_combo = QComboBox()
        self.usb_controller_combo.addItems(["none", "piix3-usb-uhci", "usb-ehci", "usb-ohci", "usb-uhci", "usb-xhci", "nec-usb-xhci"])
        board_layout.addWidget(self.usb_controller_combo, row, 1)
        board_layout.setRowStretch(row + 1, 1)
        tabs.addTab(board_tab, "🔌 主板/存储")
        
        layout.addWidget(tabs)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.save_btn = QPushButton("💾 保存")
        self.save_btn.setMinimumHeight(36)
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; border-radius: 6px;")
        self.save_btn.clicked.connect(self.save)
        btn_layout.addWidget(self.save_btn)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
        self.setMinimumSize(550, 500)
    
    def load_data(self, data):
        self.name_edit.setText(data.get("name", ""))
        self.name_edit.setReadOnly(True)
        self.year_spin.setValue(data.get("year", 2024))
        self.desc_edit.setText(data.get("description", ""))
        self.cpu_model_combo.setCurrentText(data.get("cpu_model", "host"))
        self.cpu_flags_edit.setText(data.get("cpu_flags", ""))
        self.vga_combo.setCurrentText(data.get("vga", "virtio"))
        self.display_combo.setCurrentText(data.get("display", "gtk"))
        self.sound_combo.setCurrentText(data.get("sound", "hda"))
        self.nic_combo.setCurrentText(data.get("nic", "virtio"))
        self.machine_combo.setCurrentText(data.get("machine", "q35"))
        self.disk_interface_combo.setCurrentText(data.get("disk_interface", "virtio"))
        self.accel_combo.setCurrentText(data.get("accel", "hax"))
        self.usb_controller_combo.setCurrentText(data.get("usb_controller", "usb-ehci"))
    
    def get_data(self):
        return {
            "name": self.name_edit.text().strip(),
            "year": self.year_spin.value(),
            "description": self.desc_edit.text().strip(),
            "cpu_model": self.cpu_model_combo.currentText(),
            "cpu_flags": self.cpu_flags_edit.text().strip(),
            "vga": self.vga_combo.currentText(),
            "display": self.display_combo.currentText(),
            "sound": self.sound_combo.currentText(),
            "nic": self.nic_combo.currentText(),
            "machine": self.machine_combo.currentText(),
            "disk_interface": self.disk_interface_combo.currentText(),
            "accel": self.accel_combo.currentText(),
            "usb_controller": self.usb_controller_combo.currentText(),
        }
    
    def save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入配置名称")
            return
        if not self.is_edit and self.manager.get_profile(name):
            QMessageBox.warning(self, "提示", f"配置 '{name}' 已存在")
            return
        data = self.get_data()
        if self.is_edit:
            if self.manager.update_profile(name, data):
                QMessageBox.information(self, "成功", "✅ 已更新")
                self.accept()
            else:
                QMessageBox.warning(self, "错误", "更新失败")
        else:
            if self.manager.create_profile(name, data):
                QMessageBox.information(self, "成功", "✅ 已创建")
                self.accept()
            else:
                QMessageBox.warning(self, "错误", "创建失败")


class HardwareProfileManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = HardwareProfileManager()
        self.parent_window = parent
        self.init_ui()
        self.refresh_list()
    
    def init_ui(self):
        self.setWindowTitle("🔧 硬件配置管理")
        self.setMinimumSize(750, 550)
        layout = QVBoxLayout(self)
        info_label = QLabel(
            "📌 管理完整的硬件配置预设\n"
            "• 内置配置 (2011-2024) 不可编辑/删除\n"
            "• 自定义配置保存在选中文件夹的 hardware_profiles/custom/"
        )
        info_label.setStyleSheet("color: #aaa; font-size: 12px; padding: 8px; background: #1a1a1a; border-radius: 6px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        self.list_widget = QListWidget()
        self.list_widget.setFont(QFont("Microsoft YaHei", 12))
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        layout.addWidget(self.list_widget)
        detail_group = QGroupBox("📋 详情")
        detail_layout = QGridLayout(detail_group)
        self.detail_labels = {}
        fields = [
            ("名称:", "name"), ("年份:", "year"), ("描述:", "desc"),
            ("CPU 型号:", "cpu_model"), ("指令集标志:", "cpu_flags"),
            ("显卡:", "vga"), ("显示后端:", "display"), ("声卡:", "sound"),
            ("网卡:", "nic"), ("磁盘接口:", "disk_interface"),
            ("机器类型:", "machine"), ("加速模式:", "accel"),
            ("USB 控制器:", "usb_controller"),
        ]
        row = 0
        col = 0
        for label_text, key in fields:
            detail_layout.addWidget(QLabel(label_text), row, col * 2)
            self.detail_labels[key] = QLabel("-")
            self.detail_labels[key].setWordWrap(True)
            self.detail_labels[key].setStyleSheet("color: #ddd; font-weight: bold;")
            detail_layout.addWidget(self.detail_labels[key], row, col * 2 + 1)
            col += 1
            if col >= 2:
                col = 0
                row += 1
        layout.addWidget(detail_group)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.new_btn = QPushButton("📦 新建")
        self.new_btn.clicked.connect(self.create_profile)
        btn_layout.addWidget(self.new_btn)
        self.edit_btn = QPushButton("✏️ 编辑")
        self.edit_btn.clicked.connect(self.edit_profile)
        self.edit_btn.setEnabled(False)
        btn_layout.addWidget(self.edit_btn)
        self.delete_btn = QPushButton("🗑️ 删除")
        self.delete_btn.clicked.connect(self.delete_profile)
        self.delete_btn.setEnabled(False)
        btn_layout.addWidget(self.delete_btn)
        self.apply_btn = QPushButton("✅ 应用到当前虚拟机")
        self.apply_btn.clicked.connect(self.apply_to_current_vm)
        self.apply_btn.setEnabled(False)
        self.apply_btn.setStyleSheet("background-color: #2196F3; color: white;")
        btn_layout.addWidget(self.apply_btn)
        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self.refresh_list)
        btn_layout.addWidget(self.refresh_btn)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)
    
    def refresh_list(self):
        self.list_widget.clear()
        self.manager.load_all()
        for name in self.manager.get_all_names():
            data = self.manager.get_profile(name)
            if data:
                icon = "🔒" if data.get("is_builtin", False) else "📄"
                item = QListWidgetItem(f"{icon} {name} ({data.get('year', 0)})")
                item.setData(Qt.UserRole, name)
                if data.get("is_builtin", False):
                    item.setForeground(QColor("#888888"))
                self.list_widget.addItem(item)
        self.clear_details()
        self.edit_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
    
    def clear_details(self):
        for key, label in self.detail_labels.items():
            label.setText("-")
    
    def on_selection_changed(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        name = items[0].data(Qt.UserRole)
        data = self.manager.get_profile(name)
        if not data:
            return
        field_map = {
            "name": "name", "year": "year", "desc": "description",
            "cpu_model": "cpu_model", "cpu_flags": "cpu_flags",
            "vga": "vga", "display": "display", "sound": "sound",
            "nic": "nic", "disk_interface": "disk_interface",
            "machine": "machine", "accel": "accel",
            "usb_controller": "usb_controller",
        }
        for key, label in self.detail_labels.items():
            src_key = field_map.get(key, key)
            val = data.get(src_key, "-")
            if val == "":
                val = "(空)"
            label.setText(str(val))
        is_builtin = data.get("is_builtin", False)
        self.edit_btn.setEnabled(not is_builtin)
        self.delete_btn.setEnabled(not is_builtin)
        self.apply_btn.setEnabled(True)
    
    def create_profile(self):
        dialog = HardwareProfileEditDialog(self, None, self.manager)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_list()
    
    def edit_profile(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        name = items[0].data(Qt.UserRole)
        data = self.manager.get_profile(name)
        if not data or data.get("is_builtin", False):
            QMessageBox.warning(self, "提示", "内置配置不可编辑")
            return
        dialog = HardwareProfileEditDialog(self, name, self.manager)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_list()
    
    def delete_profile(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        name = items[0].data(Qt.UserRole)
        data = self.manager.get_profile(name)
        if not data or data.get("is_builtin", False):
            QMessageBox.warning(self, "提示", "内置配置不可删除")
            return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除硬件配置 '{name}' 吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.manager.delete_profile(name):
                QMessageBox.information(self, "成功", "✅ 已删除")
                self.refresh_list()
    
    def apply_to_current_vm(self):
        main_window = self.parent_window
        while main_window and not hasattr(main_window, 'current_vm'):
            main_window = main_window.parent() if hasattr(main_window, 'parent') else None
        if not main_window or not hasattr(main_window, 'current_vm') or not main_window.current_vm:
            QMessageBox.warning(self, "提示", "请先在主界面选择一个虚拟机")
            return
        items = self.list_widget.selectedItems()
        if not items:
            return
        name = items[0].data(Qt.UserRole)
        profile = self.manager.get_profile(name)
        if not profile:
            return
        vm = main_window.current_vm
        self.manager.apply_to_vm(name, vm)
        config_file = VMS_DIR / vm.name / "config.json"
        if config_file.exists():
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(vm.to_dict(), f, indent=2, ensure_ascii=False)
        if hasattr(main_window, 'update_summary') and hasattr(main_window, 'update_config_tab'):
            main_window.update_summary(vm)
            main_window.update_config_tab(vm)
        QMessageBox.information(self, "成功", f"✅ 硬件配置 '{name}' 已应用到虚拟机 '{vm.name}'")


# ============================================================
# 网络模式常量
# ============================================================
NETWORK_MODES = {
    "user": {"name": "user", "label": "用户态网络 (默认)",
             "description": "QEMU 内置用户态网络栈，支持端口转发，无需额外配置",
             "needs_admin": False, "needs_tap": False, "supports_port_fwd": True},
    "bridge": {"name": "bridge", "label": "桥接模式",
               "description": "通过 TAP 设备和桥接接口，让虚拟机直接接入主机网络",
               "needs_admin": True, "needs_tap": True, "supports_port_fwd": False},
    "tap": {"name": "tap", "label": "TAP 直连",
            "description": "直接使用 TAP 设备连接主机网络，需要手动配置 IP",
            "needs_admin": True, "needs_tap": True, "supports_port_fwd": False},
    "socket": {"name": "socket", "label": "Socket 网络",
               "description": "多虚拟机之间通过 Socket 通信，适合集群环境",
               "needs_admin": False, "needs_tap": False, "supports_port_fwd": False},
    "vde": {"name": "vde", "label": "VDE 网络",
            "description": "虚拟分布式以太网，多虚拟机互联",
            "needs_admin": False, "needs_tap": False, "supports_port_fwd": False},
    "none": {"name": "none", "label": "无网络",
             "description": "完全禁用网络",
             "needs_admin": False, "needs_tap": False, "supports_port_fwd": False},
}


# ============================================================
# QEMU 硬件检测（缓存 + timeout 短，避免卡死）
# ============================================================
class QEMUHardwareDetector:
    _cache = {}
    _cache_time = {}
    _cache_ttl = 300

    def __init__(self, use_cache=True):
        self.qemu_versions = {}
        self.hardware_cache = {}
        folder_sig = self._get_folder_signature()
        if use_cache and folder_sig in QEMUHardwareDetector._cache:
            if time.time() - QEMUHardwareDetector._cache_time.get(folder_sig, 0) < QEMUHardwareDetector._cache_ttl:
                self.qemu_versions = dict(QEMUHardwareDetector._cache[folder_sig])
                self.detect_acceleration()
                return
        self.scan_qemu_versions()
        self.detect_acceleration()
        if use_cache:
            QEMUHardwareDetector._cache[folder_sig] = dict(self.qemu_versions)
            QEMUHardwareDetector._cache_time[folder_sig] = time.time()
    
    def _get_folder_signature(self):
        try:
            folders = FOLDERS_CONFIG.get("folders", [])
            parts = [f"{f.get('name', '')}|{f.get('path', '')}|{f.get('qemu_path', '')}" for f in folders]
            return ";;".join(parts) if parts else "default"
        except:
            return "default"
    
    def clear_cache(self):
        QEMUHardwareDetector._cache.clear()
        QEMUHardwareDetector._cache_time.clear()

    def scan_qemu_versions(self):
        scanned_dirs = set()
        for folder in FOLDERS_CONFIG.get("folders", []):
            folder_path = Path(folder.get("path", ""))
            if not folder_path.exists():
                continue
            qemu_path = folder.get("qemu_path", "")
            if qemu_path and Path(qemu_path).exists():
                qp = Path(qemu_path)
                if qp.is_file():
                    self._scan_qemu_dir(qp.parent)
                else:
                    self._scan_qemu_dir(qp)
                    try:
                        for item in qp.iterdir():
                            if item.is_dir() and item.name.lower().startswith("qemu"):
                                self._scan_qemu_dir(item)
                    except:
                        pass
            for base in [folder_path, folder_path.parent]:
                if not base.exists():
                    continue
                try:
                    for item in base.iterdir():
                        if item.is_dir() and item.name.lower().startswith("qemu"):
                            if str(item) not in scanned_dirs:
                                self._scan_qemu_dir(item)
                                scanned_dirs.add(str(item))
                except:
                    pass
        try:
            for item in BASE_DIR.iterdir():
                if item.is_dir() and item.name.startswith("qemu"):
                    if str(item) not in scanned_dirs:
                        self._scan_qemu_dir(item)
                        scanned_dirs.add(str(item))
        except:
            pass
        for cmd in ["qemu-system-x86_64", "qemu-system-x86_64.exe"]:
            try:
                result = subprocess.run(
                    ["where" if sys.platform == "win32" else "which", cmd],
                    capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=5
                )
                if result.returncode == 0:
                    path = result.stdout.strip().split('\n')[0]
                    if path and Path(path).exists():
                        p = Path(path).parent
                        if str(p) not in scanned_dirs:
                            self._scan_qemu_dir(p)
                            scanned_dirs.add(str(p))
            except:
                pass
    
    def _scan_qemu_dir(self, dir_path: Path):
        if not dir_path or not dir_path.exists():
            return
        for exe_name in ["qemu-system-x86_64.exe", "qemu-system-x86_64",
                         "qemu-system-i386.exe", "qemu-system-i386"]:
            exe = dir_path / exe_name
            if exe.exists():
                info = self.get_qemu_info(str(exe))
                if dir_path.name not in self.qemu_versions:
                    self.qemu_versions[dir_path.name] = {"path": str(exe), "info": info}
                break
    
    def get_qemu_info(self, exe_path: str) -> dict:
        info = {
            "version": "未知", "year": 2020,
            "supported_devices": [], "vga_types": [], "display_types": [],
            "machine_types": [], "cpu_models": [], "accel_types": [],
            "netdev_types": [], "audio_devices": [], "usb_devices": [],
            "pci_devices": [], "gpu_models": [], "firmware_types": [],
            "block_drivers": [], "has_mem_backing": False,
        }
        try:
            result = subprocess.run([exe_path, "--version"], capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore', timeout=5)
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0] if result.stdout else ""
                info["version"] = version_line
                year_match = re.search(r'(20[1-9][0-9])', version_line)
                if year_match:
                    info["year"] = int(year_match.group(1))
        except:
            pass
        try:
            result = subprocess.run([exe_path, "-cpu", "help"], capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore', timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid', 'x86', 'Recognized')):
                        item = line.split()[0]
                        if item and item not in info["cpu_models"]:
                            info["cpu_models"].append(item)
        except:
            pass
        try:
            result = subprocess.run([exe_path, "-device", "help"], capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore', timeout=8)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    match = re.match(r'name "([^"]+)".*bus ([^,]+).*desc "([^"]*)"', line)
                    if match:
                        name, bus, desc = match.groups()
                        info["supported_devices"].append({"name": name, "bus": bus, "desc": desc})
                        if bus == "PCI":
                            info["pci_devices"].append(name)
                        elif bus == "USB":
                            info["usb_devices"].append(name)
        except:
            pass
        try:
            result = subprocess.run([exe_path, "-vga", "help"], capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore', timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["vga_types"]:
                            info["vga_types"].append(item)
                            if item not in info["gpu_models"]:
                                info["gpu_models"].append(item)
        except:
            pass
        try:
            result = subprocess.run([exe_path, "-display", "help"], capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore', timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["display_types"]:
                            info["display_types"].append(item)
        except:
            pass
        try:
            result = subprocess.run([exe_path, "-machine", "help"], capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore', timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid', 'Machine')):
                        parts = line.split()
                        if parts:
                            machine = parts[0].replace(':', '')
                            if machine and machine not in info["machine_types"]:
                                info["machine_types"].append(machine)
        except:
            pass
        try:
            result = subprocess.run([exe_path, "-accel", "help"], capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore', timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["accel_types"]:
                            info["accel_types"].append(item)
        except:
            pass
        try:
            result = subprocess.run([exe_path, "-netdev", "help"], capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore', timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["netdev_types"]:
                            info["netdev_types"].append(item)
        except:
            pass
        try:
            result = subprocess.run([exe_path, "-audiodev", "help"], capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore', timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["audio_devices"]:
                            info["audio_devices"].append(item)
        except:
            pass
        try:
            result = subprocess.run([exe_path, "-help"], capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore', timeout=5)
            if result.returncode == 0:
                help_text = result.stdout + result.stderr
                if "-mem-path" in help_text or "memory-backend-file" in help_text:
                    info["has_mem_backing"] = True
        except:
            pass
        return info
    
    def detect_acceleration(self):
        self.available_accel = []
        self.hypervisor_info = {}
        if sys.platform == "win32":
            try:
                result = subprocess.run(["systeminfo"], capture_output=True, text=True,
                                        encoding='utf-8', errors='ignore', timeout=10)
                if "Hyper-V" in result.stdout:
                    self.hypervisor_info["hyperv"] = True
                    self.available_accel.append("whpx")
                result = subprocess.run(["sc", "query", "haxm"], capture_output=True,
                                        text=True, encoding='utf-8', errors='ignore', timeout=5)
                if "RUNNING" in result.stdout or "STOPPED" in result.stdout:
                    self.hypervisor_info["haxm"] = True
                    self.available_accel.append("hax")
            except:
                pass
        elif sys.platform == "linux":
            try:
                if Path("/dev/kvm").exists():
                    self.hypervisor_info["kvm"] = True
                    self.available_accel.append("kvm")
            except:
                pass
        elif sys.platform == "darwin":
            try:
                result = subprocess.run(["sysctl", "kern.hv_support"], capture_output=True,
                                        text=True, encoding='utf-8', errors='ignore', timeout=5)
                if "1" in result.stdout:
                    self.hypervisor_info["hvf"] = True
                    self.available_accel.append("hvf")
            except:
                pass
        if "tcg" not in self.available_accel:
            self.available_accel.insert(0, "tcg")
        self.default_accel = self.available_accel[0] if self.available_accel else "tcg"
    
    def add_custom_qemu(self, qemu_path: str) -> bool:
        if not qemu_path or not Path(qemu_path).exists():
            return False
        qemu_dir = Path(qemu_path).parent
        exe_name = Path(qemu_path).name
        if not exe_name.startswith("qemu-system-"):
            for name in ["qemu-system-x86_64.exe", "qemu-system-x86_64"]:
                exe = qemu_dir / name
                if exe.exists():
                    qemu_path = str(exe)
                    break
            else:
                return False
        version_name = f"自定义_{qemu_dir.name}"
        if version_name in self.qemu_versions:
            return True
        info = self.get_qemu_info(qemu_path)
        self.qemu_versions[version_name] = {"path": qemu_path, "info": info, "is_custom": True}
        return True

# ========== VMConfig 类 ==========
class VMConfig:
    def __init__(self, name: str = ""):
        self.name = name
        self.vm_dir = VMS_DIR / name
        self.folder_name = ""
        self.os_type = "Windows"
        self.os_version = "10"
        self.arch = "x86_64"
        self.memory = 4096
        self.cpu = 4
        self.smp_threads = 1
        self.smp_sockets = 1
        self.disk_size = 64
        self.disk_format = "qcow2"
        self.disk_interface = "sata"
        self.disk_path = ""
        self.disks: List[Dict] = []
        self.disk_id_counter = 0
        self.boot_iso = ""
        self.kernel_iso = ""
        self.driver_iso = ""
        self.created = ""
        self.cpu_model = "host"
        self.cpu_profile = ""
        self.accel = "hax"
        self.cpu_flags = ""
        self.numa_config = ""
        self.cpu_capacity = 100
        self.cpu_latency = 10
        self.cpu_quota = 0
        self.cpu_period = 100000
        self.cpu_freq = 0
        self.cpu_clock = 0
        self.vga = "virtio"
        self.display = "gtk"
        self.resolution = "1920x1080"
        self.opengl = True
        self.vnc_port = ""
        self.vnc_password = ""
        self.spice_port = ""
        self.spice_password = ""
        self.gpu_edid = ""
        self.gpu_rendernode = ""
        self.gpu_gl_version = "3.3"
        self.machine_type = "q35"
        self.acpi = True
        self.usb = True
        self.usb_tablet = True
        self.no_mouse_integration = False
        self.no_hpet = False
        self.no_hpet_adv = False
        self.no_kvm = False
        self.no_kvm_nested = False
        self.force_tcg = False
        self.bios_file = ""
        self.custom_bios = ""
        self.custom_firmware = ""
        self.custom_rtc = "utc"
        self.rtc_base = ""
        self.seed_value = ""
        self.boot_menu = False
        self.boot_once = ""
        self.sound = "hda"
        self.nic_model = "virtio"
        self.mac_address = ""
        self.network_mode = "user"
        self.bridge_interface = ""
        self.tap_interface = ""
        self.socket_path = ""
        self.vde_socket = ""
        self.network_script = ""
        self.network_down_script = ""
        self.hostfwd = ""
        self.net_subnet = ""
        self.net_dns = ""
        self.net_restrict = False
        self.boot_order = "cdrom"
        self.qemu_version = ""
        self.custom_qemu_path = ""
        self.preset = "Windows 10"
        self.extra_args = ""
        self.share_enabled = False
        self.share_dir = ""
        self.memory_backing_enabled = False
        self.memory_backing_file = ""
        self.memory_backing_size = 0
        self.mem_prealloc = False
        self.hugepages = False
        self.pci_passthrough: List[Dict] = []
        self.usb_passthrough: List[Dict] = []
        self.cache = "writeback"
        self.aio = "默认"
        self.discard = "默认"
        self.detect_zeroes = "默认"
        self.backing_file = ""
        self.snapshot_mode = False
        self.disk_readonly = False
        self.log_file = ""
        self.debug_level = "默认"
        self.qmp_socket = ""
        self.monitor_stdio = False
        self.no_reboot = False
        self.no_shutdown = False
        self.sandbox = False
        self.extra_advanced_args = ""
        self.custom_cpu_vendor = "AuthenticAMD"
        self.custom_cpu_family = "6"
        self.custom_cpu_model_id = "94"
        self.custom_cpu_stepping = "3"
        self.custom_cpu_level = "0x1"
        self.custom_cpu_xlevel = "0x80000008"
        self.custom_cpu_features = "+aes,+avx,+avx2,+bmi1,+bmi2,+f16c,+fma,+rdrand,+rdseed,+sha-ni,+xsave,+xsavec,+xsaves"
        self.custom_gpu_model = "virtio-vga-gl"
        self.custom_gpu_ram = 256
        self.custom_gpu_freq = 800
        self.custom_gpu_vgamem = 64
        self.custom_nic_model = "virtio-net-pci"
        self.custom_nic_mac = ""
        self.custom_nic_queues = 1
        self.custom_disk_cache = "writeback"
        self.custom_disk_aio = "native"
        self.custom_disk_discard = "unmap"
        self.custom_disk_detect_zeroes = "unmap"
        self.custom_disk_latency = 0
        self.custom_audio_model = "ich9-intel-hda"
        self.custom_audio_codec = "hda-duplex"
        self.custom_usb_controller = "usb-ehci"
        self.custom_usb_ports = 6
        self.custom_pci_bus = "pcie.0"
        self.custom_pci_slot = 0
        self.custom_serial = "pty"
        self.custom_parallel = "none"
        self.storage_type = "file"
        self.storage_format = "qcow2"
        self.storage_encryption = False
        self.storage_encryption_key = ""
        self.storage_compression = False
        self.storage_cluster_size = 65536
        self.security_selinux = False
        self.security_apparmor = False
        self.security_chroot = ""
        self.security_user = ""
        self.trace_events = ""
        self.log_level = 0
        self.gdb_port = 1234
        self.gdb_stop = False

    def add_disk(self, path, size_gb, format_type="qcow2", interface="sata",
                 cache="writeback", backing_file="", readonly=False, removable=False):
        self.disk_id_counter += 1
        disk = {"id": self.disk_id_counter, "path": path, "size": size_gb,
                "format": format_type, "interface": interface, "cache": cache,
                "backing_file": backing_file, "readonly": readonly, "removable": removable}
        self.disks.append(disk)
        if len(self.disks) == 1:
            self.disk_path = path
            self.disk_size = size_gb
            self.disk_format = format_type
            self.disk_interface = interface
        return disk

    def remove_disk(self, disk_id):
        self.disks = [d for d in self.disks if d["id"] != disk_id]
        if self.disks:
            first = self.disks[0]
            self.disk_path = first["path"]
            self.disk_size = first["size"]
            self.disk_format = first["format"]
            self.disk_interface = first["interface"]
        else:
            self.disk_path = ""
            self.disk_size = 0
            self.disk_format = "qcow2"
            self.disk_interface = "sata"

    def get_disk(self, disk_id):
        for d in self.disks:
            if d["id"] == disk_id:
                return d
        return None

    def to_dict(self) -> dict:
        return {
            "version": CONFIG_VERSION, "name": self.name, "folder_name": self.folder_name,
            "os_type": self.os_type, "os_version": self.os_version, "arch": self.arch,
            "memory": self.memory, "cpu": self.cpu,
            "smp_threads": self.smp_threads, "smp_sockets": self.smp_sockets,
            "disk_size": self.disk_size, "disk_format": self.disk_format,
            "disk_interface": self.disk_interface, "disk_path": self.disk_path,
            "disks": self.disks, "disk_id_counter": self.disk_id_counter,
            "boot_iso": self.boot_iso, "kernel_iso": self.kernel_iso,
            "driver_iso": self.driver_iso, "created": self.created,
            "cpu_model": self.cpu_model, "cpu_profile": self.cpu_profile,
            "accel": self.accel, "cpu_flags": self.cpu_flags,
            "numa_config": self.numa_config, "cpu_capacity": self.cpu_capacity,
            "cpu_latency": self.cpu_latency, "cpu_quota": self.cpu_quota,
            "cpu_period": self.cpu_period, "cpu_freq": self.cpu_freq,
            "cpu_clock": self.cpu_clock,
            "vga": self.vga, "display": self.display,
            "resolution": self.resolution, "opengl": self.opengl,
            "vnc_port": self.vnc_port, "vnc_password": self.vnc_password,
            "spice_port": self.spice_port, "spice_password": self.spice_password,
            "gpu_edid": self.gpu_edid, "gpu_rendernode": self.gpu_rendernode,
            "gpu_gl_version": self.gpu_gl_version,
            "machine_type": self.machine_type, "acpi": self.acpi,
            "usb": self.usb, "usb_tablet": self.usb_tablet,
            "no_mouse_integration": self.no_mouse_integration,
            "no_hpet": self.no_hpet, "no_hpet_adv": self.no_hpet_adv,
            "no_kvm": self.no_kvm, "no_kvm_nested": self.no_kvm_nested,
            "force_tcg": self.force_tcg,
            "bios_file": self.bios_file, "custom_bios": self.custom_bios,
            "custom_firmware": self.custom_firmware, "custom_rtc": self.custom_rtc,
            "rtc_base": self.rtc_base, "seed_value": self.seed_value,
            "boot_menu": self.boot_menu, "boot_once": self.boot_once,
            "sound": self.sound,
            "nic_model": self.nic_model, "mac_address": self.mac_address,
            "network_mode": self.network_mode,
            "bridge_interface": self.bridge_interface,
            "tap_interface": self.tap_interface,
            "socket_path": self.socket_path, "vde_socket": self.vde_socket,
            "network_script": self.network_script,
            "network_down_script": self.network_down_script,
            "hostfwd": self.hostfwd, "net_subnet": self.net_subnet,
            "net_dns": self.net_dns, "net_restrict": self.net_restrict,
            "boot_order": self.boot_order,
            "qemu_version": self.qemu_version, "custom_qemu_path": self.custom_qemu_path,
            "preset": self.preset, "extra_args": self.extra_args,
            "share_enabled": self.share_enabled, "share_dir": self.share_dir,
            "memory_backing_enabled": self.memory_backing_enabled,
            "memory_backing_file": self.memory_backing_file,
            "memory_backing_size": self.memory_backing_size,
            "mem_prealloc": self.mem_prealloc, "hugepages": self.hugepages,
            "pci_passthrough": self.pci_passthrough,
            "usb_passthrough": self.usb_passthrough,
            "cache": self.cache, "aio": self.aio, "discard": self.discard,
            "detect_zeroes": self.detect_zeroes, "backing_file": self.backing_file,
            "snapshot_mode": self.snapshot_mode, "disk_readonly": self.disk_readonly,
            "log_file": self.log_file, "debug_level": self.debug_level,
            "qmp_socket": self.qmp_socket, "monitor_stdio": self.monitor_stdio,
            "no_reboot": self.no_reboot, "no_shutdown": self.no_shutdown,
            "sandbox": self.sandbox, "extra_advanced_args": self.extra_advanced_args,
            "custom_cpu_vendor": self.custom_cpu_vendor,
            "custom_cpu_family": self.custom_cpu_family,
            "custom_cpu_model_id": self.custom_cpu_model_id,
            "custom_cpu_stepping": self.custom_cpu_stepping,
            "custom_cpu_level": self.custom_cpu_level,
            "custom_cpu_xlevel": self.custom_cpu_xlevel,
            "custom_cpu_features": self.custom_cpu_features,
            "custom_gpu_model": self.custom_gpu_model,
            "custom_gpu_ram": self.custom_gpu_ram,
            "custom_gpu_freq": self.custom_gpu_freq,
            "custom_gpu_vgamem": self.custom_gpu_vgamem,
            "custom_nic_model": self.custom_nic_model,
            "custom_nic_mac": self.custom_nic_mac,
            "custom_nic_queues": self.custom_nic_queues,
            "custom_disk_cache": self.custom_disk_cache,
            "custom_disk_aio": self.custom_disk_aio,
            "custom_disk_discard": self.custom_disk_discard,
            "custom_disk_detect_zeroes": self.custom_disk_detect_zeroes,
            "custom_disk_latency": self.custom_disk_latency,
            "custom_audio_model": self.custom_audio_model,
            "custom_audio_codec": self.custom_audio_codec,
            "custom_usb_controller": self.custom_usb_controller,
            "custom_usb_ports": self.custom_usb_ports,
            "custom_pci_bus": self.custom_pci_bus,
            "custom_pci_slot": self.custom_pci_slot,
            "custom_serial": self.custom_serial,
            "custom_parallel": self.custom_parallel,
            "storage_type": self.storage_type, "storage_format": self.storage_format,
            "storage_encryption": self.storage_encryption,
            "storage_encryption_key": self.storage_encryption_key,
            "storage_compression": self.storage_compression,
            "storage_cluster_size": self.storage_cluster_size,
            "security_selinux": self.security_selinux,
            "security_apparmor": self.security_apparmor,
            "security_chroot": self.security_chroot,
            "security_user": self.security_user,
            "trace_events": self.trace_events, "log_level": self.log_level,
            "gdb_port": self.gdb_port, "gdb_stop": self.gdb_stop,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'VMConfig':
        vm = cls(data.get("name", ""))
        for key, value in data.items():
            if key in ("version", "vm_dir"):
                continue
            if hasattr(vm, key):
                setattr(vm, key, value)
        return vm


# ========== 多语言支持 ==========
LANGUAGES = {
    "zh_CN": {
        "name": "简体中文",
        "app_title": "Mikan QEMU 管理器 v{}",
        "status_ready": "就绪",
        "status_refreshed": "✅ 已刷新",
        "status_created": "✅ 创建成功: {}",
        "status_updated": "✅ 配置已更新: {}",
        "status_deleted": "🗑️ 已删除: {}",
        "status_launched": "🚀 已启动: {}",
        "status_exporting": "📦 正在导出 {}...",
        "status_export_done": "✅ 导出成功 ({:.1f} MB)",
        "status_export_failed": "❌ 导出失败",
        "status_importing": "📥 正在导入...",
        "status_import_done": "✅ 导入成功: {}",
        "status_import_failed": "❌ 导入失败",
        "status_export_script": "✅ 脚本已导出",
        "status_detecting": "🔍 正在检测QEMU硬件...",
        "menu_help": "❓ 帮助",
        "menu_help_about": "📖 使用说明",
        "menu_help_github": "🌐 开源项目 (GitHub)",
        "menu_language": "🌐 语言",
        "menu_detect": "🔍 检测",
        "menu_detect_hw": "🔍 检测系统硬件",
        "menu_profile": "🧠 硬件配置",
        "menu_profile_new": "📦 新建硬件配置",
        "menu_profile_manage": "📋 管理硬件配置",
        "btn_new": "新建",
        "btn_edit": "编辑",
        "btn_delete": "删除",
        "btn_export": "导出",
        "btn_import": "导入",
        "btn_snapshot": "快照",
        "btn_disk": "磁盘",
        "btn_script": "脚本",
        "btn_launch": "启动",
        "btn_refresh": "刷新",
        "btn_create": "创建",
        "btn_save": "保存",
        "btn_cancel": "取消",
        "btn_close": "关闭",
        "btn_browse": "浏览",
        "btn_clear": "清空",
        "btn_help": "帮助",
        "btn_unlock": "解锁高级",
        "btn_unlocked": "已解锁",
        "btn_reset_adv": "恢复默认",
        "btn_browse_qemu": "📂 选择QEMU",
        "adv_title": "高级选项",
        "adv_locked": "🔒 已锁定",
        "adv_unlocked": "🔓 已解锁",
        "adv_warning": "⚠️ 高级选项修改不当可能导致虚拟机无法启动或数据损坏！",
        "adv_unlock_warning": "⚠️ 高级调试警告\n\n如需自主调试，请先备份虚拟机重要资料！\n\n出问题本作者概不负责！\n\n你确定要继续吗？",
        "adv_acknowledged": "已确认",
        "adv_reset_confirm": "将重置所有高级选项为官方推荐值，是否继续？",
        "adv_reset_done": "已重置",
        "adv_reset_ok": "所有高级选项已恢复为官方默认值",
        "tab_basic": "基本信息",
        "tab_hardware": "硬件配置",
        "tab_display": "显示/声音",
        "tab_advanced": "高级配置",
        "tab_disk_adv": "磁盘",
        "tab_network": "网络",
        "tab_cpu_adv": "CPU/内存",
        "tab_display_adv": "显示",
        "tab_debug": "调试",
        "tab_other": "其他",
        "tab_custom_hw": "自定义硬件",
        "tab_performance": "性能调优",
        "label_preset": "预设模板:",
        "label_name": "名称:",
        "label_os_type": "系统类型:",
        "label_os_version": "系统版本:",
        "label_arch": "CPU 架构:",
        "label_memory": "内存 (MB):",
        "label_cpu_cores": "CPU 核心:",
        "label_cpu_threads": "CPU 线程数:",
        "label_cpu_sockets": "CPU 插槽:",
        "label_disk_size": "磁盘大小:",
        "label_disk_format": "磁盘格式:",
        "label_disk_interface": "磁盘接口:",
        "label_cpu_model": "CPU 型号:",
        "label_cpu_profile": "硬件配置:",
        "label_accel": "加速模式:",
        "label_machine": "机器类型:",
        "label_qemu_version": "QEMU 版本:",
        "label_vga": "显卡:",
        "label_display": "显示后端:",
        "label_resolution": "分辨率:",
        "label_vnc_port": "VNC 端口:",
        "label_sound": "声卡:",
        "label_nic": "网卡:",
        "label_boot_order": "启动顺序:",
        "label_extra_args": "额外参数:",
        "label_share_dir": "共享目录:",
        "label_boot_iso": "启动镜像:",
        "label_driver_iso": "驱动镜像:",
        "label_cpu_flags": "CPU 指令集附加:",
        "label_numa": "NUMA 配置:",
        "label_hostfwd": "端口转发:",
        "label_subnet": "自定义子网:",
        "label_dns": "自定义 DNS:",
        "label_tap": "TAP 网卡名:",
        "label_mac": "MAC 地址:",
        "label_bios": "自定义 BIOS:",
        "label_vnc_password": "VNC 密码:",
        "label_spice_port": "SPICE 端口:",
        "label_spice_password": "SPICE 密码:",
        "label_log_file": "日志文件:",
        "label_debug_level": "调试级别:",
        "label_qmp_socket": "QMP Socket:",
        "label_rtc": "RTC 基准时间:",
        "label_seed": "固定随机种子:",
        "label_boot_once": "仅本次启动设备:",
        "label_extra_adv": "额外高级参数:",
        "label_cache": "磁盘缓存:",
        "label_aio": "AIO 模式:",
        "label_discard": "TRIM 支持:",
        "label_detect_zeroes": "零块检测:",
        "label_backing": "后端镜像:",
        "label_cpu_vendor": "CPU 厂商:",
        "label_cpu_family": "CPU 家族:",
        "label_cpu_model_id": "CPU 型号 ID:",
        "label_cpu_features": "CPU 特性:",
        "label_cpu_capacity": "CPU 容量 (%):",
        "label_cpu_latency": "CPU 延迟 (µs):",
        "label_gpu_model": "GPU 型号:",
        "label_gpu_ram": "GPU 内存 (MB):",
        "label_gpu_vgamem": "VGA 内存 (MB):",
        "label_nic_model": "网卡型号:",
        "label_nic_queues": "网卡队列数:",
        "label_nic_mac": "MAC 地址:",
        "label_audio_model": "音频模型:",
        "label_usb_controller": "USB 控制器:",
        "label_usb_ports": "USB 端口数:",
        "label_serial": "串口:",
        "label_memory_backing": "💾 内存磁盘 (使用本地文件作为内存)",
        "label_memory_backing_file": "内存文件路径:",
        "label_memory_backing_size": "内存文件大小 (MB):",
        "check_acpi": "启用 ACPI (电源管理)",
        "check_usb": "启用 USB",
        "check_opengl": "启用 OpenGL 加速",
        "check_share": "启用共享文件夹",
        "check_snapshot": "📸 快照模式 (-snapshot)",
        "check_readonly": "🔒 磁盘只读模式",
        "check_net_restrict": "🚫 限制网络访问",
        "check_mem_prealloc": "📌 预分配所有内存",
        "check_hugepages": "📌 使用大页内存 (Linux)",
        "check_monitor_stdio": "📟 启用 Monitor 控制台",
        "check_sandbox": "🔒 沙箱模式",
        "error": "错误",
        "warning": "提示",
        "info": "信息",
        "success": "成功",
        "confirm": "确认",
        "msg_select_vm": "请先选择一个虚拟机",
        "msg_name_empty": "请输入虚拟机名称",
        "msg_vm_exists": "虚拟机 '{}' 已存在",
        "msg_launcher_missing": "启动器不存在:\n{}\n\n请确保 launcher.py 在同一目录",
        "msg_launch_failed": "启动失败:\n{}",
        "msg_export_confirm": "将导出虚拟机 \"{}\" 到:\n{}\n\n是否继续？",
        "msg_import_confirm": "将导入虚拟机包:\n{}\n\n是否继续？",
        "msg_overwrite_confirm": "虚拟机 \"{}\" 已存在，是否覆盖？",
        "msg_qemu_img_not_found": "找不到 qemu-img",
        "msg_export_format_choose": "Yes = Windows (.bat)\nNo = Linux/Shell (.sh)",
        "msg_script_exported": "脚本已导出:\n{}",
        "msg_mikan_format": "请选择 .mikan 格式",
        "msg_history_no_entries": "没有找到 '{}' 的历史配置",
        "msg_history_restore": "将恢复配置 '{}' 的历史版本？\n\n当前配置将被覆盖。",
        "msg_history_restored": "已恢复历史配置",
        "msg_history_select": "请选择一个历史配置",
        "msg_history_restore_failed": "恢复失败",
        "custom_hw_title": "🔧 自定义硬件 - {}",
        "custom_hw_saved": "✅ 自定义硬件配置已保存",
        "history_title": "📜 历史配置 - {}",
        "history_restore_btn": "↩️ 恢复此配置",
        "history_entry": "[{}] {}",
        "custom_hw_cpu": "🖥️ CPU",
        "custom_hw_gpu": "🎮 GPU",
        "custom_hw_network": "🌐 网络",
        "custom_hw_storage": "💾 存储",
        "custom_hw_other": "🔌 其他硬件",
        "custom_hw_performance": "⚡ 性能",
        "custom_hw_security": "🔒 安全/调试",
        "msg_custom_hw": "🔧 点击「自定义硬件」按钮打开完整硬件配置面板",
        "label_gpu_edid_browse": "选择 EDID 文件",
        "label_bios_browse": "选择 BIOS 文件",
        "label_network_mode": "网络模式:",
        "label_bridge_interface": "桥接接口:",
        "label_socket_path": "Socket 路径:",
        "label_vde_socket": "VDE Socket:",
        "label_network_script": "网络启动脚本:",
        "label_network_down_script": "网络关闭脚本:",
    },
    "en_US": {
        "name": "English",
        "app_title": "Mikan QEMU Manager v{}",
        "status_ready": "Ready",
        "status_refreshed": "✅ Refreshed",
        "status_created": "✅ Created: {}",
        "status_updated": "✅ Updated: {}",
        "status_deleted": "🗑️ Deleted: {}",
        "status_launched": "🚀 Launched: {}",
        "menu_help": "❓ Help",
        "menu_help_about": "📖 User Guide",
        "menu_help_github": "🌐 GitHub Repository",
        "menu_language": "🌐 Language",
        "menu_detect": "🔍 Detect",
        "menu_detect_hw": "🔍 Detect System Hardware",
        "menu_profile": "🧠 Hardware Profiles",
        "menu_profile_new": "📦 New Hardware Profile",
        "menu_profile_manage": "📋 Manage Hardware Profiles",
        "btn_new": "New", "btn_edit": "Edit", "btn_delete": "Delete",
        "btn_export": "Export", "btn_import": "Import",
        "btn_snapshot": "Snapshot", "btn_disk": "Disk", "btn_script": "Script",
        "btn_launch": "Launch", "btn_refresh": "Refresh", "btn_create": "Create",
        "btn_save": "Save", "btn_cancel": "Cancel", "btn_close": "Close",
        "btn_browse": "Browse", "btn_clear": "Clear", "btn_help": "Help",
        "btn_unlock": "Unlock Advanced", "btn_unlocked": "Unlocked",
        "btn_reset_adv": "Reset Default", "btn_browse_qemu": "📂 Select QEMU",
        "adv_title": "Advanced Options", "adv_locked": "🔒 Locked",
        "adv_unlocked": "🔓 Unlocked",
        "adv_warning": "⚠️ Incorrect advanced settings may cause VM boot failure!",
        "adv_unlock_warning": "⚠️ Advanced Debug Warning\n\nPlease backup important VM data before proceeding!\n\nThe author is not responsible for any issues!\n\nAre you sure you want to continue?",
        "adv_acknowledged": "Acknowledged",
        "adv_reset_confirm": "Reset all advanced options to official defaults. Continue?",
        "adv_reset_done": "Reset Complete",
        "adv_reset_ok": "All advanced options have been reset to official defaults",
        "tab_basic": "Basic", "tab_hardware": "Hardware",
        "tab_display": "Display/Sound", "tab_advanced": "Advanced",
        "tab_disk_adv": "Disk", "tab_network": "Network",
        "tab_cpu_adv": "CPU/Memory", "tab_display_adv": "Display",
        "tab_debug": "Debug", "tab_other": "Other",
        "tab_custom_hw": "Custom Hardware", "tab_performance": "Performance",
        "label_preset": "Preset:", "label_name": "Name:",
        "label_os_type": "OS Type:", "label_os_version": "OS Version:",
        "label_arch": "Architecture:", "label_memory": "Memory (MB):",
        "label_cpu_cores": "CPU Cores:", "label_cpu_threads": "CPU Threads:",
        "label_cpu_sockets": "CPU Sockets:", "label_disk_size": "Disk Size:",
        "label_disk_format": "Disk Format:", "label_disk_interface": "Disk Interface:",
        "label_cpu_model": "CPU Model:", "label_cpu_profile": "Hardware Profile:",
        "label_accel": "Acceleration:", "label_machine": "Machine Type:",
        "label_qemu_version": "QEMU Version:", "label_vga": "Graphics:",
        "label_display": "Display Backend:", "label_resolution": "Resolution:",
        "label_vnc_port": "VNC Port:", "label_sound": "Sound Card:",
        "label_nic": "Network Card:", "label_boot_order": "Boot Order:",
        "label_extra_args": "Extra Args:", "label_share_dir": "Share Directory:",
        "label_boot_iso": "Boot ISO:", "label_driver_iso": "Driver ISO:",
        "label_cpu_flags": "CPU Flags:", "label_numa": "NUMA Config:",
        "label_hostfwd": "Port Forwarding:", "label_subnet": "Custom Subnet:",
        "label_dns": "Custom DNS:", "label_tap": "TAP Interface:",
        "label_mac": "MAC Address:", "label_bios": "Custom BIOS:",
        "label_vnc_password": "VNC Password:", "label_spice_port": "SPICE Port:",
        "label_spice_password": "SPICE Password:", "label_log_file": "Log File:",
        "label_debug_level": "Debug Level:", "label_qmp_socket": "QMP Socket:",
        "label_rtc": "RTC Base Time:", "label_seed": "Fixed Seed:",
        "label_boot_once": "Boot Once:", "label_extra_adv": "Extra Advanced Args:",
        "label_cache": "Disk Cache:", "label_aio": "AIO Mode:",
        "label_discard": "TRIM Support:", "label_detect_zeroes": "Zero Detection:",
        "label_backing": "Backing File:", "label_cpu_vendor": "CPU Vendor:",
        "label_cpu_family": "CPU Family:", "label_cpu_model_id": "CPU Model ID:",
        "label_cpu_features": "CPU Features:",
        "label_cpu_capacity": "CPU Capacity (%):", "label_cpu_latency": "CPU Latency (µs):",
        "label_gpu_model": "GPU Model:", "label_gpu_ram": "GPU RAM (MB):",
        "label_gpu_vgamem": "VGA Memory (MB):", "label_nic_model": "NIC Model:",
        "label_nic_queues": "NIC Queues:", "label_nic_mac": "MAC Address:",
        "label_audio_model": "Audio Model:", "label_usb_controller": "USB Controller:",
        "label_usb_ports": "USB Ports:", "label_serial": "Serial:",
        "label_memory_backing": "💾 Memory Backing File (Use disk as RAM)",
        "label_memory_backing_file": "Memory File Path:",
        "label_memory_backing_size": "Memory File Size (MB):",
        "check_acpi": "Enable ACPI", "check_usb": "Enable USB",
        "check_opengl": "Enable OpenGL Acceleration", "check_share": "Enable Shared Folder",
        "check_snapshot": "📸 Snapshot Mode (-snapshot)", "check_readonly": "🔒 Read-only Disk Mode",
        "check_net_restrict": "🚫 Restrict Network Access",
        "check_mem_prealloc": "📌 Pre-allocate all memory",
        "check_hugepages": "📌 Use Huge Pages (Linux)",
        "check_monitor_stdio": "📟 Enable Monitor Console", "check_sandbox": "🔒 Sandbox Mode",
        "error": "Error", "warning": "Warning", "info": "Info", "success": "Success", "confirm": "Confirm",
        "msg_select_vm": "Please select a VM first", "msg_name_empty": "Please enter a VM name",
        "msg_vm_exists": "VM '{}' already exists",
        "msg_launcher_missing": "Launcher not found:\n{}\n\nPlease ensure launcher.py is in the same directory",
        "msg_launch_failed": "Launch failed:\n{}",
        "msg_export_confirm": "Export VM \"{}\" to:\n{}\n\nContinue?",
        "msg_import_confirm": "Import VM package:\n{}\n\nContinue?",
        "msg_overwrite_confirm": "VM \"{}\" already exists. Overwrite?",
        "msg_qemu_img_not_found": "qemu-img not found",
        "msg_export_format_choose": "Yes = Windows (.bat)\nNo = Linux/Shell (.sh)",
        "msg_script_exported": "Script exported:\n{}",
        "msg_mikan_format": "Please select .mikan format",
        "msg_history_no_entries": "No history found for '{}'",
        "msg_history_restore": "Restore historical version of '{}'?",
        "msg_history_restored": "Historical configuration restored",
        "msg_history_select": "Please select a history entry",
        "msg_history_restore_failed": "Restore failed",
        "custom_hw_title": "🔧 Custom Hardware - {}",
        "custom_hw_saved": "✅ Custom hardware configuration saved",
        "history_title": "📜 History - {}",
        "history_restore_btn": "↩️ Restore This Config",
        "history_entry": "[{}] {}",
        "custom_hw_cpu": "🖥️ CPU", "custom_hw_gpu": "🎮 GPU",
        "custom_hw_network": "🌐 Network", "custom_hw_storage": "💾 Storage",
        "custom_hw_other": "🔌 Other Hardware", "custom_hw_performance": "⚡ Performance",
        "custom_hw_security": "🔒 Security/Debug",
        "msg_custom_hw": "🔧 Click the 'Custom Hardware' button to open the full hardware configuration panel",
        "label_gpu_edid_browse": "Select EDID File", "label_bios_browse": "Select BIOS File",
        "label_network_mode": "Network Mode:", "label_bridge_interface": "Bridge Interface:",
        "label_socket_path": "Socket Path:", "label_vde_socket": "VDE Socket:",
        "label_network_script": "Network Up Script:", "label_network_down_script": "Network Down Script:",
    }
}


class Translator:
    _instance = None
    _current_lang = "zh_CN"
    _lang_data = LANGUAGES

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def set_language(self, lang_code):
        if lang_code in self._lang_data:
            self._current_lang = lang_code
            try:
                with open(CONFIG_DIR / "lang.json", 'w', encoding='utf-8') as f:
                    json.dump({"language": lang_code}, f)
            except:
                pass
        if hasattr(self, '_main_window') and self._main_window:
            self._main_window.refresh_ui_texts()

    def set_main_window(self, window):
        self._main_window = window

    def get_language(self):
        return self._current_lang

    def tr(self, key, *args):
        text = self._lang_data.get(self._current_lang, {}).get(key, key)
        if args:
            try:
                return text.format(*args)
            except:
                return text
        return text

    def get_languages(self):
        return {code: data.get("name", code) for code, data in self._lang_data.items()}


def tr(key, *args):
    return Translator().tr(key, *args)


class SystemDetector:
    @staticmethod
    def get_system_info():
        info = {
            "操作系统": platform.system() + " " + platform.release(),
            "系统版本": platform.version(),
            "架构": platform.machine(),
            "处理器": platform.processor() or "未知",
            "主机名": socket.gethostname(),
            "Python版本": platform.python_version(),
            "CPU核心数": os.cpu_count() or "未知",
        }
        try:
            vm = psutil.virtual_memory()
            info["总内存"] = f"{vm.total / (1024**3):.1f} GB"
            info["可用内存"] = f"{vm.available / (1024**3):.1f} GB"
            info["内存使用率"] = f"{vm.percent}%"
        except:
            pass
        try:
            info["CPU使用率"] = f"{psutil.cpu_percent(interval=0.5)}%"
        except:
            pass
        try:
            disk = psutil.disk_usage(str(BASE_DIR))
            info["磁盘总量"] = f"{disk.total / (1024**3):.1f} GB"
            info["磁盘可用"] = f"{disk.free / (1024**3):.1f} GB"
        except:
            pass
        if sys.platform == "win32":
            info["系统"] = "Windows"
            try:
                result = subprocess.run(["systeminfo"], capture_output=True, text=True,
                                        encoding='utf-8', errors='ignore', timeout=10)
                info["Hyper-V"] = "✅ 已启用" if "Hyper-V" in result.stdout else "❌ 未启用"
            except:
                info["Hyper-V"] = "未知"
        elif sys.platform == "linux":
            info["系统"] = "Linux"
            info["KVM"] = "✅ 已支持" if Path("/dev/kvm").exists() else "❌ 未支持"
        elif sys.platform == "darwin":
            info["系统"] = "macOS"
        return info

    @staticmethod
    def get_qemu_supported_hardware():
        detector = QEMUHardwareDetector()
        hardware_info = {
            "QEMU版本": [], "可用加速器": [], "支持CPU型号": [],
            "支持显卡": [], "支持机器类型": [], "支持网络设备": [],
            "支持音频设备": [], "支持USB设备": [], "支持固件": [],
        }
        for ver_name, ver_info in detector.qemu_versions.items():
            info = ver_info["info"]
            hardware_info["QEMU版本"].append({
                "版本": ver_name, "路径": ver_info["path"],
                "信息": info.get("version", "未知")
            })
            for item in info.get("cpu_models", []):
                if item not in hardware_info["支持CPU型号"]:
                    hardware_info["支持CPU型号"].append(item)
            for item in info.get("vga_types", []):
                if item not in hardware_info["支持显卡"]:
                    hardware_info["支持显卡"].append(item)
            for item in info.get("machine_types", []):
                if item not in hardware_info["支持机器类型"]:
                    hardware_info["支持机器类型"].append(item)
            for item in info.get("netdev_types", []):
                if item not in hardware_info["支持网络设备"]:
                    hardware_info["支持网络设备"].append(item)
            for item in info.get("audio_devices", []):
                if item not in hardware_info["支持音频设备"]:
                    hardware_info["支持音频设备"].append(item)
            for item in info.get("usb_devices", []):
                if item not in hardware_info["支持USB设备"]:
                    hardware_info["支持USB设备"].append(item)
        return hardware_info


class ConfigHistory:
    def __init__(self):
        self.history_file = CONFIG_DIR / "history.json"
        self.history = defaultdict(list)
        self.max_entries = 20
        self.load()

    def load(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, entries in data.items():
                        self.history[key] = entries[:self.max_entries]
            except Exception as e:
                print(f"加载历史配置失败: {e}")

    def save(self):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(dict(self.history), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存历史配置失败: {e}")

    def add_entry(self, vm_name, config):
        if vm_name not in self.history:
            self.history[vm_name] = []
        entry = {"timestamp": datetime.now().isoformat(), "config": config}
        self.history[vm_name].insert(0, entry)
        self.history[vm_name] = self.history[vm_name][:self.max_entries]
        self.save()

    def get_history(self, vm_name):
        return self.history.get(vm_name, [])

    def clear_history(self, vm_name):
        if vm_name in self.history:
            del self.history[vm_name]
            self.save()

    def restore_entry(self, vm_name, index):
        history = self.get_history(vm_name)
        if 0 <= index < len(history):
            return history[index]["config"]
        return None


# ============================================================
# ⚡ 修复版 find_qemu_img()：递归扫描所有 qemu 目录
# ============================================================
def find_qemu_img():
    """查找 qemu-img（递归扫描所有 qemu 目录）"""
    candidates = []

    # 1. folders.json 里的 qemu_path 和 path
    for folder in FOLDERS_CONFIG.get("folders", []):
        qemu_dir = folder.get("qemu_path", "")
        if qemu_dir:
            qp = Path(qemu_dir)
            if qp.exists():
                if qp.is_file():
                    if qp.name in ("qemu-img.exe", "qemu-img"):
                        return qp
                    qp = qp.parent
                candidates.append(qp)
        folder_path = Path(folder.get("path", ""))
        if folder_path.exists():
            candidates.append(folder_path)
            candidates.append(folder_path.parent)

    # 2. BASE_DIR 下所有 qemu* 目录
    for pattern in ["qemu-*", "qemu*", "QEMU*"]:
        try:
            for ver_dir in BASE_DIR.glob(pattern):
                if ver_dir.is_dir():
                    candidates.append(ver_dir)
        except:
            pass

    # 3. BASE_DIR 自身
    candidates.append(BASE_DIR)

    # 4. 逐个扫描（根目录 + 递归）
    for base in candidates:
        if not base.exists() or not base.is_dir():
            continue
        for name in ["qemu-img.exe", "qemu-img"]:
            p = base / name
            if p.exists():
                return p
        try:
            for name in ["qemu-img.exe", "qemu-img"]:
                results = list(base.rglob(name))
                if results:
                    results.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    return results[0]
        except (PermissionError, OSError):
            pass

    # 5. 系统 PATH
    for cmd in ["qemu-img", "qemu-img.exe"]:
        try:
            result = subprocess.run(
                ["where" if sys.platform == "win32" else "which", cmd],
                capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=5
            )
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                if path and Path(path).exists():
                    return Path(path)
        except:
            pass

    return None

# ============================================================
# 硬件直通检测器
# ============================================================
class PassthroughDetector:
    @staticmethod
    def get_usb_devices():
        devices = []
        try:
            if sys.platform == "win32":
                try:
                    result = subprocess.run(
                        ["powershell", "-Command",
                         "Get-PnpDevice -Class USB -Status OK | Select-Object FriendlyName,InstanceId | ConvertTo-Json"],
                        capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=15
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        data = json.loads(result.stdout)
                        if isinstance(data, dict):
                            data = [data]
                        for dev in data:
                            iid = dev.get("InstanceId", "")
                            vid, pid = PassthroughDetector._extract_vid_pid(iid)
                            devices.append({
                                "name": dev.get("FriendlyName", "USB设备"),
                                "id": iid, "vendor_id": vid, "product_id": pid,
                            })
                except Exception as e:
                    print(f"USB检测失败: {e}")
            elif sys.platform == "linux":
                try:
                    result = subprocess.run(["lsusb"], capture_output=True, text=True,
                                            encoding='utf-8', errors='ignore', timeout=10)
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            m = re.search(r'ID (\w+):(\w+) (.+)', line)
                            if m:
                                vid, pid, name = m.groups()
                                devices.append({"name": name.strip(), "id": f"{vid}:{pid}",
                                                "vendor_id": vid, "product_id": pid})
                except:
                    pass
        except Exception as e:
            print(f"USB检测异常: {e}")
        return devices

    @staticmethod
    def get_pci_devices():
        devices = []
        try:
            if sys.platform == "win32":
                try:
                    result = subprocess.run(
                        ["powershell", "-Command",
                         "Get-PnpDevice -Class 'Display','Net','SCSIAdapter' -Status OK | Select-Object FriendlyName,InstanceId,Class | ConvertTo-Json"],
                        capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=15
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        data = json.loads(result.stdout)
                        if isinstance(data, dict):
                            data = [data]
                        for dev in data:
                            iid = dev.get("InstanceId", "")
                            if iid.startswith("PCI\\"):
                                devices.append({
                                    "name": dev.get("FriendlyName", "PCI设备"),
                                    "id": iid, "class": dev.get("Class", ""),
                                    "address": PassthroughDetector._extract_pci_addr(iid),
                                })
                except Exception as e:
                    print(f"PCI检测失败: {e}")
            elif sys.platform == "linux":
                try:
                    result = subprocess.run(["lspci", "-nn"], capture_output=True, text=True,
                                            encoding='utf-8', errors='ignore', timeout=10)
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            m = re.match(r'^([0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F])\s+(.+)', line.strip())
                            if m:
                                addr, name = m.groups()
                                devices.append({"name": name.strip(), "id": addr,
                                                "address": addr, "class": ""})
                except:
                    pass
        except Exception as e:
            print(f"PCI检测异常: {e}")
        return devices

    @staticmethod
    def _extract_vid_pid(iid):
        vid = pid = ""
        try:
            m1 = re.search(r'VID_([0-9A-Fa-f]{4})', iid)
            m2 = re.search(r'PID_([0-9A-Fa-f]{4})', iid)
            if m1:
                vid = f"0x{m1.group(1)}"
            if m2:
                pid = f"0x{m2.group(1)}"
        except:
            pass
        return vid, pid

    @staticmethod
    def _extract_pci_addr(iid):
        try:
            m = re.search(r'VEN_(\w+)&DEV_(\w+)', iid)
            if m:
                return f"{m.group(1)}:{m.group(2)}"
        except:
            pass
        return ""


# ============================================================
# 文件夹管理对话框
# ============================================================
class FolderEditDialog(QDialog):
    def __init__(self, parent=None, folder_data=None):
        super().__init__(parent)
        self.folder_data = folder_data or {}
        self.init_ui()
        if folder_data:
            self.load_data(folder_data)

    def init_ui(self):
        self.setWindowTitle("📁 文件夹设置")
        self.setMinimumSize(550, 280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        grid = QGridLayout()
        row = 0
        grid.addWidget(QLabel("文件夹名称:"), row, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如: 游戏虚拟机")
        grid.addWidget(self.name_edit, row, 1)
        row += 1
        grid.addWidget(QLabel("根目录:"), row, 0)
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择根目录（vms/iso/等子文件夹将自动生成）")
        path_row.addWidget(self.path_edit)
        browse_btn = QPushButton("📂 浏览")
        browse_btn.clicked.connect(self.browse_path)
        path_row.addWidget(browse_btn)
        grid.addLayout(path_row, row, 1)
        row += 1
        grid.addWidget(QLabel("QEMU 目录 (可选):"), row, 0)
        qemu_row = QHBoxLayout()
        self.qemu_edit = QLineEdit()
        self.qemu_edit.setPlaceholderText("留空自动扫描")
        qemu_row.addWidget(self.qemu_edit)
        qemu_browse = QPushButton("📂 浏览")
        qemu_browse.clicked.connect(self.browse_qemu)
        qemu_row.addWidget(qemu_browse)
        grid.addLayout(qemu_row, row, 1)
        layout.addLayout(grid)
        hint = QLabel("💡 选中根目录后，程序会在其中自动创建:\n   vms/ iso/ snapshots/ exports/ share/ hardware_profiles/")
        hint.setStyleSheet("color: #888; font-size: 11px; padding: 8px; background: #1a1a1a; border-radius: 6px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("💾 保存")
        save_btn.setStyleSheet("background-color: #4a7a4a; color: white;")
        save_btn.clicked.connect(self.save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def browse_path(self):
        p = QFileDialog.getExistingDirectory(self, "选择根目录", str(BASE_DIR))
        if p:
            self.path_edit.setText(p)
            if not self.name_edit.text():
                self.name_edit.setText(Path(p).name)

    def browse_qemu(self):
        p = QFileDialog.getExistingDirectory(self, "选择QEMU目录", str(BASE_DIR))
        if p:
            self.qemu_edit.setText(p)

    def load_data(self, data):
        self.name_edit.setText(data.get("name", ""))
        self.path_edit.setText(data.get("path", ""))
        self.qemu_edit.setText(data.get("qemu_path", ""))

    def get_data(self):
        name = self.name_edit.text().strip()
        path = self.path_edit.text().strip()
        if not name or not path:
            QMessageBox.warning(self, "提示", "请填写名称和路径")
            return None
        return {"name": name, "path": path, "qemu_path": self.qemu_edit.text().strip()}

    def save(self):
        d = self.get_data()
        if d:
            self.accept()


class FolderManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.init_ui()
        self.refresh_list()

    def init_ui(self):
        self.setWindowTitle("🗂️ 文件夹管理")
        self.setMinimumSize(700, 500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        info = QLabel(
            "🗂️ 绑定多个根文件夹\n"
            "• 每个根文件夹下自动生成 vms/iso/snapshots/exports/share/hardware_profiles\n"
            "• 可在主界面下拉栏快速切换\n"
            "• QEMU 从所有绑定文件夹扫描"
        )
        info.setStyleSheet("color: #aaa; font-size: 11px; padding: 8px; background: #1a1a1a; border-radius: 6px;")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.switch_to)
        layout.addWidget(self.list_widget, 1)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕ 添加文件夹")
        add_btn.setStyleSheet("background-color: #4a7a4a; color: white;")
        add_btn.clicked.connect(self.add_folder)
        btn_row.addWidget(add_btn)
        edit_btn = QPushButton("✏️ 编辑")
        edit_btn.clicked.connect(self.edit_folder)
        btn_row.addWidget(edit_btn)
        remove_btn = QPushButton("➖ 移除")
        remove_btn.setStyleSheet("background-color: #8a4a4a; color: white;")
        remove_btn.clicked.connect(self.remove_folder)
        btn_row.addWidget(remove_btn)
        switch_btn = QPushButton("🔄 切换到此")
        switch_btn.setStyleSheet("background-color: #4a6a8a; color: white;")
        switch_btn.clicked.connect(self.switch_to)
        btn_row.addWidget(switch_btn)
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def refresh_list(self):
        self.list_widget.clear()
        folders = FOLDERS_CONFIG.get("folders", [])
        active = FOLDERS_CONFIG.get("active_index", 0)
        for i, f in enumerate(folders):
            prefix = "✅ " if i == active else "   "
            item = QListWidgetItem(f"{prefix}📁 {f.get('name', f'文件夹{i+1}')}")
            item.setData(Qt.UserRole, i)
            tooltip = f"根目录: {f.get('path', '')}"
            if f.get('qemu_path'):
                tooltip += f"\nQEMU: {f.get('qemu_path')}"
            item.setToolTip(tooltip)
            if i == active:
                item.setForeground(QColor("#4CAF50"))
            self.list_widget.addItem(item)

    def _bg_refresh_qemu(self):
        def _bg():
            try:
                new_detector = QEMUHardwareDetector(use_cache=False)
                self.parent_window.hardware_detector = new_detector
                msg = f"✅ QEMU 已刷新: {len(new_detector.qemu_versions)} 个版本"
                QMetaObject.invokeMethod(self.parent_window, "update_status", Qt.QueuedConnection,
                                         Q_ARG(str, msg))
            except Exception as e:
                print(f"后台刷新QEMU失败: {e}")
        Thread(target=_bg, daemon=True).start()

    def add_folder(self):
        dlg = FolderEditDialog(self)
        if dlg.exec() == QDialog.Accepted:
            d = dlg.get_data()
            if d:
                FOLDERS_CONFIG["folders"].append(d)
                save_folders_config()
                self.refresh_list()
                if self.parent_window:
                    self.parent_window.load_folders_to_combo()

    def edit_folder(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        idx = items[0].data(Qt.UserRole)
        dlg = FolderEditDialog(self, FOLDERS_CONFIG["folders"][idx])
        if dlg.exec() == QDialog.Accepted:
            d = dlg.get_data()
            if d:
                FOLDERS_CONFIG["folders"][idx] = d
                save_folders_config()
                self.refresh_list()
                if self.parent_window:
                    self.parent_window.load_folders_to_combo()

    def remove_folder(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        if len(FOLDERS_CONFIG["folders"]) <= 1:
            QMessageBox.warning(self, "提示", "至少保留一个文件夹")
            return
        idx = items[0].data(Qt.UserRole)
        reply = QMessageBox.question(self, "确认", "移除此文件夹绑定？(不会删除文件)",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            del FOLDERS_CONFIG["folders"][idx]
            if FOLDERS_CONFIG["active_index"] >= len(FOLDERS_CONFIG["folders"]):
                FOLDERS_CONFIG["active_index"] = 0
            save_folders_config()
            apply_active_folder()
            self.refresh_list()
            if self.parent_window:
                self.parent_window.load_folders_to_combo()
                self.parent_window.load_vms()
                self.parent_window.refresh_vm_list()
            self._bg_refresh_qemu()

    def switch_to(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        idx = items[0].data(Qt.UserRole)
        FOLDERS_CONFIG["active_index"] = idx
        save_folders_config()
        apply_active_folder()
        self.refresh_list()
        if self.parent_window:
            self.parent_window.load_folders_to_combo()
            self.parent_window.load_vms()
            self.parent_window.refresh_vm_list()
            name = FOLDERS_CONFIG['folders'][idx].get('name', '')
            self.parent_window.status_bar.showMessage(f"✅ 已切换到: {name}  |  QEMU 扫描中...")
        self._bg_refresh_qemu()


# ============================================================
# 自定义硬件对话框
# ============================================================
class CustomHardwareDialog(QDialog):
    def __init__(self, vm, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.parent_dialog = parent
        self.init_ui()
        self.load_data()

    def init_ui(self):
        self.setWindowTitle(tr("custom_hw_title", self.vm.name))
        self.setMinimumSize(750, 650)
        self.resize(750, 650)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)
        self.tab_widget.setDocumentMode(True)

        cpu_tab = self.create_cpu_custom_tab()
        self.tab_widget.addTab(cpu_tab, tr("custom_hw_cpu"))
        gpu_tab = self.create_gpu_custom_tab()
        self.tab_widget.addTab(gpu_tab, tr("custom_hw_gpu"))
        net_tab = self.create_net_custom_tab()
        self.tab_widget.addTab(net_tab, tr("custom_hw_network"))
        storage_tab = self.create_storage_custom_tab()
        self.tab_widget.addTab(storage_tab, tr("custom_hw_storage"))
        hw_tab = self.create_hw_custom_tab()
        self.tab_widget.addTab(hw_tab, tr("custom_hw_other"))
        perf_tab = self.create_perf_custom_tab()
        self.tab_widget.addTab(perf_tab, tr("custom_hw_performance"))
        sec_tab = self.create_security_tab()
        self.tab_widget.addTab(sec_tab, tr("custom_hw_security"))

        layout.addWidget(self.tab_widget, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.save_btn = QPushButton(tr("btn_save"))
        self.save_btn.clicked.connect(self.save_and_close)
        btn_layout.addWidget(self.save_btn)
        self.cancel_btn = QPushButton(tr("btn_close"))
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def create_cpu_custom_tab(self):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setVerticalSpacing(6)
        layout.setHorizontalSpacing(8)
        row = 0
        layout.addWidget(QLabel(tr("label_cpu_vendor")), row, 0)
        self.cpu_vendor = QComboBox()
        self.cpu_vendor.addItems(["AuthenticAMD", "GenuineIntel", "QEMU", "Unknown"])
        self.cpu_vendor.setEditable(True)
        layout.addWidget(self.cpu_vendor, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_cpu_family")), row, 0)
        self.cpu_family = QLineEdit()
        layout.addWidget(self.cpu_family, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_cpu_model_id")), row, 0)
        self.cpu_model_id = QLineEdit()
        layout.addWidget(self.cpu_model_id, row, 1)
        row += 1
        layout.addWidget(QLabel("CPU 步进:"), row, 0)
        self.cpu_stepping = QLineEdit()
        layout.addWidget(self.cpu_stepping, row, 1)
        row += 1
        layout.addWidget(QLabel("CPU 级别:"), row, 0)
        self.cpu_level = QLineEdit()
        layout.addWidget(self.cpu_level, row, 1)
        row += 1
        layout.addWidget(QLabel("CPU 扩展级别:"), row, 0)
        self.cpu_xlevel = QLineEdit()
        layout.addWidget(self.cpu_xlevel, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_cpu_features")), row, 0)
        self.cpu_features = QLineEdit()
        self.cpu_features.setPlaceholderText("+aes,+avx,-hypervisor,...")
        layout.addWidget(self.cpu_features, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_cpu_capacity")), row, 0)
        self.cpu_capacity = QSpinBox()
        self.cpu_capacity.setRange(1, 200)
        self.cpu_capacity.setSuffix("%")
        layout.addWidget(self.cpu_capacity, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_cpu_latency")), row, 0)
        self.cpu_latency = QSpinBox()
        self.cpu_latency.setRange(0, 1000)
        self.cpu_latency.setSuffix(" µs")
        layout.addWidget(self.cpu_latency, row, 1)
        row += 1
        layout.addWidget(QLabel("CPU 配额:"), row, 0)
        self.cpu_quota = QSpinBox()
        self.cpu_quota.setRange(0, 200)
        self.cpu_quota.setSuffix("%")
        layout.addWidget(self.cpu_quota, row, 1)
        row += 1
        layout.addWidget(QLabel("CPU 周期:"), row, 0)
        self.cpu_period = QSpinBox()
        self.cpu_period.setRange(1000, 1000000)
        self.cpu_period.setSuffix(" µs")
        layout.addWidget(self.cpu_period, row, 1)
        layout.setRowStretch(row + 1, 1)
        return widget

    def create_gpu_custom_tab(self):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setVerticalSpacing(6)
        layout.setHorizontalSpacing(8)
        row = 0
        layout.addWidget(QLabel(tr("label_gpu_model")), row, 0)
        self.gpu_model = QComboBox()
        self.gpu_model.addItems(["virtio-vga-gl", "virtio-gpu-gl", "virtio-vga", "virtio-gpu",
                                 "vmvga", "qxl", "std", "cirrus", "bochs", "ramfb", "sga"])
        self.gpu_model.setEditable(True)
        layout.addWidget(self.gpu_model, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_gpu_ram")), row, 0)
        self.gpu_ram = QSpinBox()
        self.gpu_ram.setRange(16, 4096)
        self.gpu_ram.setSuffix(" MB")
        layout.addWidget(self.gpu_ram, row, 1)
        row += 1
        layout.addWidget(QLabel("GPU 频率:"), row, 0)
        self.gpu_freq = QSpinBox()
        self.gpu_freq.setRange(100, 3000)
        self.gpu_freq.setSuffix(" MHz")
        layout.addWidget(self.gpu_freq, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_gpu_vgamem")), row, 0)
        self.gpu_vgamem = QSpinBox()
        self.gpu_vgamem.setRange(4, 512)
        self.gpu_vgamem.setSuffix(" MB")
        layout.addWidget(self.gpu_vgamem, row, 1)
        row += 1
        layout.addWidget(QLabel("OpenGL 版本:"), row, 0)
        self.gpu_gl_version = QComboBox()
        self.gpu_gl_version.addItems(["3.3", "3.0", "2.1", "4.6", "4.5"])
        layout.addWidget(self.gpu_gl_version, row, 1)
        row += 1
        layout.addWidget(QLabel("渲染节点:"), row, 0)
        self.gpu_rendernode = QLineEdit()
        self.gpu_rendernode.setPlaceholderText("/dev/dri/renderD128")
        layout.addWidget(self.gpu_rendernode, row, 1)
        row += 1
        layout.addWidget(QLabel("EDID 文件:"), row, 0)
        edid_row = QHBoxLayout()
        self.gpu_edid = QLineEdit()
        self.gpu_edid.setPlaceholderText("edid.bin")
        edid_row.addWidget(self.gpu_edid)
        browse_btn = QPushButton(tr("btn_browse"))
        browse_btn.clicked.connect(lambda: self.browse_edid())
        edid_row.addWidget(browse_btn)
        layout.addLayout(edid_row, row, 1)
        row += 1
        self.gpu_opengl_check = QCheckBox(tr("check_opengl"))
        self.gpu_opengl_check.setChecked(True)
        layout.addWidget(self.gpu_opengl_check, row, 0, 1, 2)
        layout.setRowStretch(row + 1, 1)
        return widget

    def create_net_custom_tab(self):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setVerticalSpacing(6)
        layout.setHorizontalSpacing(8)
        row = 0
        layout.addWidget(QLabel(tr("label_nic_model")), row, 0)
        self.nic_model = QComboBox()
        self.nic_model.addItems(["virtio-net-pci", "e1000", "e1000e", "rtl8139", "pcnet", "vmxnet3", "usb-net", "ne2k_pci"])
        self.nic_model.setEditable(True)
        layout.addWidget(self.nic_model, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_nic_queues")), row, 0)
        self.nic_queues = QSpinBox()
        self.nic_queues.setRange(1, 16)
        layout.addWidget(self.nic_queues, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_nic_mac")), row, 0)
        self.nic_mac = QLineEdit()
        self.nic_mac.setPlaceholderText("52:54:00:12:34:56")
        layout.addWidget(self.nic_mac, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_hostfwd")), row, 0)
        self.hostfwd = QLineEdit()
        self.hostfwd.setPlaceholderText("tcp::2222-:22")
        layout.addWidget(self.hostfwd, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_subnet")), row, 0)
        self.net_subnet = QLineEdit()
        self.net_subnet.setPlaceholderText("192.168.1.0/24")
        layout.addWidget(self.net_subnet, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_dns")), row, 0)
        self.net_dns = QLineEdit()
        self.net_dns.setPlaceholderText("8.8.8.8")
        layout.addWidget(self.net_dns, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_tap")), row, 0)
        self.tap_interface = QLineEdit()
        self.tap_interface.setPlaceholderText("tap0")
        layout.addWidget(self.tap_interface, row, 1)
        row += 1
        self.net_restrict_check = QCheckBox(tr("check_net_restrict"))
        layout.addWidget(self.net_restrict_check, row, 0, 1, 2)
        layout.setRowStretch(row + 1, 1)
        return widget

    def create_storage_custom_tab(self):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setVerticalSpacing(6)
        layout.setHorizontalSpacing(8)
        row = 0
        layout.addWidget(QLabel("存储类型:"), row, 0)
        self.storage_type = QComboBox()
        self.storage_type.addItems(["file", "block", "iscsi", "nbd", "gluster", "rbd", "ssh"])
        layout.addWidget(self.storage_type, row, 1)
        row += 1
        layout.addWidget(QLabel("存储格式:"), row, 0)
        self.storage_format = QComboBox()
        self.storage_format.addItems(["qcow2", "raw", "vmdk", "vdi", "vhdx", "qcow", "cow", "parallels", "dmg", "bochs", "cloop", "luks", "qed", "vpc", "vvfat"])
        layout.addWidget(self.storage_format, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_cache")), row, 0)
        self.disk_cache = QComboBox()
        self.disk_cache.addItems(["writeback", "none", "writethrough", "directsync", "unsafe"])
        layout.addWidget(self.disk_cache, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_aio")), row, 0)
        self.disk_aio = QComboBox()
        self.disk_aio.addItems(["native", "threads", "io_uring"])
        layout.addWidget(self.disk_aio, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_discard")), row, 0)
        self.disk_discard = QComboBox()
        self.disk_discard.addItems(["unmap", "ignore", "none"])
        layout.addWidget(self.disk_discard, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_detect_zeroes")), row, 0)
        self.disk_detect_zeroes = QComboBox()
        self.disk_detect_zeroes.addItems(["unmap", "off", "on"])
        layout.addWidget(self.disk_detect_zeroes, row, 1)
        row += 1
        layout.addWidget(QLabel("簇大小:"), row, 0)
        self.cluster_size = QSpinBox()
        self.cluster_size.setRange(4096, 2097152)
        self.cluster_size.setSingleStep(4096)
        self.cluster_size.setSuffix(" bytes")
        layout.addWidget(self.cluster_size, row, 1)
        row += 1
        self.encryption_check = QCheckBox("🔐 加密存储")
        layout.addWidget(self.encryption_check, row, 0, 1, 2)
        row += 1
        self.compression_check = QCheckBox("📦 压缩存储")
        layout.addWidget(self.compression_check, row, 0, 1, 2)
        layout.setRowStretch(row + 1, 1)
        return widget

    def create_hw_custom_tab(self):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setVerticalSpacing(6)
        layout.setHorizontalSpacing(8)
        row = 0
        layout.addWidget(QLabel(tr("label_audio_model")), row, 0)
        self.audio_model = QComboBox()
        self.audio_model.addItems(["ich9-intel-hda", "hda", "ac97", "sb16", "es1370", "cs4231a", "gus", "pl041", "sga"])
        self.audio_model.setEditable(True)
        layout.addWidget(self.audio_model, row, 1)
        row += 1
        layout.addWidget(QLabel("音频编解码器:"), row, 0)
        self.audio_codec = QComboBox()
        self.audio_codec.addItems(["hda-duplex", "hda-output", "hda-input", "ac97", "es1370"])
        self.audio_codec.setEditable(True)
        layout.addWidget(self.audio_codec, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_usb_controller")), row, 0)
        self.usb_controller = QComboBox()
        self.usb_controller.addItems(["usb-ehci", "usb-ohci", "usb-uhci", "usb-xhci", "nec-usb-xhci"])
        layout.addWidget(self.usb_controller, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_usb_ports")), row, 0)
        self.usb_ports = QSpinBox()
        self.usb_ports.setRange(0, 32)
        layout.addWidget(self.usb_ports, row, 1)
        row += 1
        layout.addWidget(QLabel("PCI 总线:"), row, 0)
        self.pci_bus = QLineEdit()
        self.pci_bus.setPlaceholderText("pcie.0")
        layout.addWidget(self.pci_bus, row, 1)
        row += 1
        layout.addWidget(QLabel("PCI 插槽:"), row, 0)
        self.pci_slot = QSpinBox()
        self.pci_slot.setRange(0, 31)
        layout.addWidget(self.pci_slot, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_serial")), row, 0)
        self.serial = QComboBox()
        self.serial.addItems(["pty", "null", "stdio", "file", "tcp", "telnet", "none"])
        layout.addWidget(self.serial, row, 1)
        row += 1
        layout.addWidget(QLabel("并口:"), row, 0)
        self.parallel = QComboBox()
        self.parallel.addItems(["none", "pty", "file", "null"])
        layout.addWidget(self.parallel, row, 1)
        row += 1
        layout.addWidget(QLabel(tr("label_bios")), row, 0)
        bios_row = QHBoxLayout()
        self.bios = QLineEdit()
        self.bios.setPlaceholderText("bios.bin")
        bios_row.addWidget(self.bios)
        browse_btn = QPushButton(tr("btn_browse"))
        browse_btn.clicked.connect(lambda: self.browse_bios())
        bios_row.addWidget(browse_btn)
        layout.addLayout(bios_row, row, 1)
        row += 1
        layout.addWidget(QLabel("固件:"), row, 0)
        self.firmware = QLineEdit()
        self.firmware.setPlaceholderText("UEFI.fd")
        layout.addWidget(self.firmware, row, 1)
        row += 1
        layout.addWidget(QLabel("RTC 模式:"), row, 0)
        self.rtc = QComboBox()
        self.rtc.addItems(["utc", "localtime", "custom"])
        layout.addWidget(self.rtc, row, 1)
        layout.setRowStretch(row + 1, 1)
        return widget

    def create_perf_custom_tab(self):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setVerticalSpacing(6)
        layout.setHorizontalSpacing(8)
        row = 0
        layout.addWidget(QLabel("CPU 容量:"), row, 0)
        self.perf_cpu_capacity = QSlider(Qt.Horizontal)
        self.perf_cpu_capacity.setRange(1, 200)
        self.perf_cpu_capacity.setValue(100)
        layout.addWidget(self.perf_cpu_capacity, row, 1)
        self.perf_cpu_capacity_label = QLabel("100%")
        layout.addWidget(self.perf_cpu_capacity_label, row, 2)
        self.perf_cpu_capacity.valueChanged.connect(lambda v: self.perf_cpu_capacity_label.setText(f"{v}%"))
        row += 1
        layout.addWidget(QLabel("CPU 延迟:"), row, 0)
        self.perf_cpu_latency = QSlider(Qt.Horizontal)
        self.perf_cpu_latency.setRange(0, 1000)
        self.perf_cpu_latency.setValue(10)
        layout.addWidget(self.perf_cpu_latency, row, 1)
        self.perf_cpu_latency_label = QLabel("10 µs")
        layout.addWidget(self.perf_cpu_latency_label, row, 2)
        self.perf_cpu_latency.valueChanged.connect(lambda v: self.perf_cpu_latency_label.setText(f"{v} µs"))
        row += 1
        layout.addWidget(QLabel("GPU 内存:"), row, 0)
        self.perf_gpu_ram = QSlider(Qt.Horizontal)
        self.perf_gpu_ram.setRange(16, 4096)
        self.perf_gpu_ram.setValue(256)
        layout.addWidget(self.perf_gpu_ram, row, 1)
        self.perf_gpu_ram_label = QLabel("256 MB")
        layout.addWidget(self.perf_gpu_ram_label, row, 2)
        self.perf_gpu_ram.valueChanged.connect(lambda v: self.perf_gpu_ram_label.setText(f"{v} MB"))
        row += 1
        layout.addWidget(QLabel("GPU 频率:"), row, 0)
        self.perf_gpu_freq = QSlider(Qt.Horizontal)
        self.perf_gpu_freq.setRange(100, 3000)
        self.perf_gpu_freq.setValue(800)
        layout.addWidget(self.perf_gpu_freq, row, 1)
        self.perf_gpu_freq_label = QLabel("800 MHz")
        layout.addWidget(self.perf_gpu_freq_label, row, 2)
        self.perf_gpu_freq.valueChanged.connect(lambda v: self.perf_gpu_freq_label.setText(f"{v} MHz"))
        row += 1
        layout.addWidget(QLabel("磁盘缓存:"), row, 0)
        self.perf_disk_cache = QComboBox()
        self.perf_disk_cache.addItems(["writeback", "none", "writethrough", "directsync", "unsafe"])
        layout.addWidget(self.perf_disk_cache, row, 1, 1, 2)
        row += 1
        self.mem_prealloc_check = QCheckBox(tr("check_mem_prealloc"))
        layout.addWidget(self.mem_prealloc_check, row, 0, 1, 3)
        row += 1
        self.hugepages_check = QCheckBox(tr("check_hugepages"))
        layout.addWidget(self.hugepages_check, row, 0, 1, 3)
        layout.setRowStretch(row + 1, 1)
        return widget

    def create_security_tab(self):
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setVerticalSpacing(6)
        layout.setHorizontalSpacing(8)
        row = 0
        self.selinux_check = QCheckBox("🔐 SELinux")
        layout.addWidget(self.selinux_check, row, 0, 1, 2)
        row += 1
        self.apparmor_check = QCheckBox("🔐 AppArmor")
        layout.addWidget(self.apparmor_check, row, 0, 1, 2)
        row += 1
        layout.addWidget(QLabel("Chroot 路径:"), row, 0)
        self.chroot = QLineEdit()
        self.chroot.setPlaceholderText("/path/to/chroot")
        layout.addWidget(self.chroot, row, 1)
        row += 1
        layout.addWidget(QLabel("安全用户:"), row, 0)
        self.security_user = QLineEdit()
        self.security_user.setPlaceholderText("user")
        layout.addWidget(self.security_user, row, 1)
        row += 1
        self.sandbox_check = QCheckBox(tr("check_sandbox"))
        layout.addWidget(self.sandbox_check, row, 0, 1, 2)
        row += 1
        layout.addWidget(QLabel("追踪事件:"), row, 0)
        self.trace_events = QLineEdit()
        self.trace_events.setPlaceholderText("qemu_system_reset,usb_packet")
        layout.addWidget(self.trace_events, row, 1)
        row += 1
        layout.addWidget(QLabel("日志级别:"), row, 0)
        self.log_level = QSpinBox()
        self.log_level.setRange(0, 10)
        layout.addWidget(self.log_level, row, 1)
        row += 1
        layout.addWidget(QLabel("GDB 端口:"), row, 0)
        self.gdb_port = QSpinBox()
        self.gdb_port.setRange(1, 65535)
        self.gdb_port.setValue(1234)
        layout.addWidget(self.gdb_port, row, 1)
        row += 1
        self.gdb_stop_check = QCheckBox("🛑 在 GDB 连接时停止")
        layout.addWidget(self.gdb_stop_check, row, 0, 1, 2)
        layout.setRowStretch(row + 1, 1)
        return widget

    def browse_edid(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 EDID 文件", str(BASE_DIR), "EDID 文件 (*.bin);;所有文件 (*)")
        if path:
            self.gpu_edid.setText(path)

    def browse_bios(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 BIOS 文件", str(BASE_DIR), "BIOS 文件 (*.bin *.rom);;所有文件 (*)")
        if path:
            self.bios.setText(path)

    def load_data(self):
        vm = self.vm
        self.cpu_vendor.setCurrentText(vm.custom_cpu_vendor)
        self.cpu_family.setText(vm.custom_cpu_family)
        self.cpu_model_id.setText(vm.custom_cpu_model_id)
        self.cpu_stepping.setText(getattr(vm, 'custom_cpu_stepping', '3'))
        self.cpu_level.setText(getattr(vm, 'custom_cpu_level', '0x1'))
        self.cpu_xlevel.setText(getattr(vm, 'custom_cpu_xlevel', '0x80000008'))
        self.cpu_features.setText(vm.custom_cpu_features)
        self.cpu_capacity.setValue(vm.cpu_capacity)
        self.cpu_latency.setValue(vm.cpu_latency)
        self.cpu_quota.setValue(vm.cpu_quota)
        self.cpu_period.setValue(vm.cpu_period)
        self.gpu_model.setCurrentText(vm.custom_gpu_model)
        self.gpu_ram.setValue(vm.custom_gpu_ram)
        self.gpu_freq.setValue(vm.custom_gpu_freq)
        self.gpu_vgamem.setValue(vm.custom_gpu_vgamem)
        self.gpu_gl_version.setCurrentText(vm.gpu_gl_version)
        self.gpu_rendernode.setText(vm.gpu_rendernode)
        self.gpu_edid.setText(vm.gpu_edid)
        self.gpu_opengl_check.setChecked(vm.opengl)
        self.nic_model.setCurrentText(vm.custom_nic_model)
        self.nic_queues.setValue(vm.custom_nic_queues)
        self.nic_mac.setText(vm.custom_nic_mac)
        self.hostfwd.setText(vm.hostfwd)
        self.net_subnet.setText(vm.net_subnet)
        self.net_dns.setText(vm.net_dns)
        self.tap_interface.setText(vm.tap_interface)
        self.net_restrict_check.setChecked(vm.net_restrict)
        self.storage_type.setCurrentText(vm.storage_type)
        self.storage_format.setCurrentText(vm.storage_format)
        self.disk_cache.setCurrentText(vm.custom_disk_cache)
        self.disk_aio.setCurrentText(vm.custom_disk_aio)
        self.disk_discard.setCurrentText(vm.custom_disk_discard)
        self.disk_detect_zeroes.setCurrentText(vm.custom_disk_detect_zeroes)
        self.cluster_size.setValue(vm.storage_cluster_size)
        self.encryption_check.setChecked(vm.storage_encryption)
        self.compression_check.setChecked(vm.storage_compression)
        self.audio_model.setCurrentText(vm.custom_audio_model)
        self.audio_codec.setCurrentText(vm.custom_audio_codec)
        self.usb_controller.setCurrentText(vm.custom_usb_controller)
        self.usb_ports.setValue(vm.custom_usb_ports)
        self.pci_bus.setText(vm.custom_pci_bus)
        self.pci_slot.setValue(vm.custom_pci_slot)
        self.serial.setCurrentText(vm.custom_serial)
        self.parallel.setCurrentText(vm.custom_parallel)
        self.bios.setText(vm.custom_bios)
        self.firmware.setText(vm.custom_firmware)
        self.rtc.setCurrentText(vm.custom_rtc)
        self.perf_cpu_capacity.setValue(vm.cpu_capacity)
        self.perf_cpu_capacity_label.setText(f"{vm.cpu_capacity}%")
        self.perf_cpu_latency.setValue(vm.cpu_latency)
        self.perf_cpu_latency_label.setText(f"{vm.cpu_latency} µs")
        self.perf_gpu_ram.setValue(vm.custom_gpu_ram)
        self.perf_gpu_ram_label.setText(f"{vm.custom_gpu_ram} MB")
        self.perf_gpu_freq.setValue(vm.custom_gpu_freq)
        self.perf_gpu_freq_label.setText(f"{vm.custom_gpu_freq} MHz")
        self.perf_disk_cache.setCurrentText(vm.custom_disk_cache)
        self.mem_prealloc_check.setChecked(vm.mem_prealloc)
        self.hugepages_check.setChecked(vm.hugepages)
        self.selinux_check.setChecked(vm.security_selinux)
        self.apparmor_check.setChecked(vm.security_apparmor)
        self.chroot.setText(vm.security_chroot)
        self.security_user.setText(vm.security_user)
        self.sandbox_check.setChecked(vm.sandbox)
        self.trace_events.setText(vm.trace_events)
        self.log_level.setValue(vm.log_level)
        self.gdb_port.setValue(vm.gdb_port)
        self.gdb_stop_check.setChecked(vm.gdb_stop)

    def save_to_vm(self):
        vm = self.vm
        vm.custom_cpu_vendor = self.cpu_vendor.currentText()
        vm.custom_cpu_family = self.cpu_family.text().strip()
        vm.custom_cpu_model_id = self.cpu_model_id.text().strip()
        vm.custom_cpu_stepping = self.cpu_stepping.text().strip()
        vm.custom_cpu_level = self.cpu_level.text().strip()
        vm.custom_cpu_xlevel = self.cpu_xlevel.text().strip()
        vm.custom_cpu_features = self.cpu_features.text().strip()
        vm.cpu_capacity = self.cpu_capacity.value()
        vm.cpu_latency = self.cpu_latency.value()
        vm.cpu_quota = self.cpu_quota.value()
        vm.cpu_period = self.cpu_period.value()
        vm.custom_gpu_model = self.gpu_model.currentText()
        vm.custom_gpu_ram = self.gpu_ram.value()
        vm.custom_gpu_freq = self.gpu_freq.value()
        vm.custom_gpu_vgamem = self.gpu_vgamem.value()
        vm.gpu_gl_version = self.gpu_gl_version.currentText()
        vm.gpu_rendernode = self.gpu_rendernode.text().strip()
        vm.gpu_edid = self.gpu_edid.text().strip()
        vm.opengl = self.gpu_opengl_check.isChecked()
        vm.custom_nic_model = self.nic_model.currentText()
        vm.custom_nic_queues = self.nic_queues.value()
        vm.custom_nic_mac = self.nic_mac.text().strip()
        vm.hostfwd = self.hostfwd.text().strip()
        vm.net_subnet = self.net_subnet.text().strip()
        vm.net_dns = self.net_dns.text().strip()
        vm.tap_interface = self.tap_interface.text().strip()
        vm.net_restrict = self.net_restrict_check.isChecked()
        vm.storage_type = self.storage_type.currentText()
        vm.storage_format = self.storage_format.currentText()
        vm.custom_disk_cache = self.disk_cache.currentText()
        vm.custom_disk_aio = self.disk_aio.currentText()
        vm.custom_disk_discard = self.disk_discard.currentText()
        vm.custom_disk_detect_zeroes = self.disk_detect_zeroes.currentText()
        vm.storage_cluster_size = self.cluster_size.value()
        vm.storage_encryption = self.encryption_check.isChecked()
        vm.storage_compression = self.compression_check.isChecked()
        vm.custom_audio_model = self.audio_model.currentText()
        vm.custom_audio_codec = self.audio_codec.currentText()
        vm.custom_usb_controller = self.usb_controller.currentText()
        vm.custom_usb_ports = self.usb_ports.value()
        vm.custom_pci_bus = self.pci_bus.text().strip()
        vm.custom_pci_slot = self.pci_slot.value()
        vm.custom_serial = self.serial.currentText()
        vm.custom_parallel = self.parallel.currentText()
        vm.custom_bios = self.bios.text().strip()
        vm.custom_firmware = self.firmware.text().strip()
        vm.custom_rtc = self.rtc.currentText()
        vm.cpu_capacity = self.perf_cpu_capacity.value()
        vm.cpu_latency = self.perf_cpu_latency.value()
        vm.custom_gpu_ram = self.perf_gpu_ram.value()
        vm.custom_gpu_freq = self.perf_gpu_freq.value()
        vm.custom_disk_cache = self.perf_disk_cache.currentText()
        vm.mem_prealloc = self.mem_prealloc_check.isChecked()
        vm.hugepages = self.hugepages_check.isChecked()
        vm.security_selinux = self.selinux_check.isChecked()
        vm.security_apparmor = self.apparmor_check.isChecked()
        vm.security_chroot = self.chroot.text().strip()
        vm.security_user = self.security_user.text().strip()
        vm.sandbox = self.sandbox_check.isChecked()
        vm.trace_events = self.trace_events.text().strip()
        vm.log_level = self.log_level.value()
        vm.gdb_port = self.gdb_port.value()
        vm.gdb_stop = self.gdb_stop_check.isChecked()

    def save_and_close(self):
        self.save_to_vm()
        QMessageBox.information(self, "成功", tr("custom_hw_saved"))
        self.accept()


# ============================================================
# 高级选项面板
# ============================================================
class AdvancedOptionsWidget(QGroupBox):
    def __init__(self, parent=None):
        super().__init__(tr("adv_title"), parent)
        self.setChecked(False)
        self.warning_acknowledged = False
        self.parent_dialog = parent
        self._custom_hw_dialog = None
        self._vm_ref = None
        self._passthrough_dialog = None

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(4)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)
        self.status_label = QLabel(tr("adv_locked"))
        self.status_label.setStyleSheet("color: #FF8A9C; font-weight: bold; font-size: 12px;")
        top_layout.addWidget(self.status_label)
        top_layout.addStretch()
        self.unlock_btn = QPushButton(tr("btn_unlock"))
        self.unlock_btn.setStyleSheet("""
            QPushButton { background-color: #FF8A9C; color: white; font-weight: bold; padding: 4px 16px; border-radius: 12px; font-size: 12px; border: none; }
            QPushButton:hover { background-color: #FF6B7A; }
        """)
        self.unlock_btn.clicked.connect(self.unlock_advanced)
        top_layout.addWidget(self.unlock_btn)
        main_layout.addLayout(top_layout)

        warning_label = QLabel(tr("adv_warning"))
        warning_label.setStyleSheet("QLabel { background-color: #FFF3E0; color: #B85C00; padding: 3px 8px; border-radius: 10px; border: 1px solid #FFD1B3; font-size: 10px; }")
        warning_label.setWordWrap(True)
        main_layout.addWidget(warning_label)

        self.adv_tabs = QTabWidget()
        self.adv_tabs.setTabPosition(QTabWidget.North)
        self.adv_tabs.setDocumentMode(True)
        self.adv_tabs.setEnabled(False)

        tab_disk = self.create_disk_tab()
        self.adv_tabs.addTab(tab_disk, tr("tab_disk_adv"))
        tab_network = self.create_network_tab()
        self.adv_tabs.addTab(tab_network, tr("tab_network"))
        tab_cpu = self.create_cpu_tab()
        self.adv_tabs.addTab(tab_cpu, tr("tab_cpu_adv"))
        tab_display = self.create_display_adv_tab()
        self.adv_tabs.addTab(tab_display, tr("tab_display_adv"))
        tab_debug = self.create_debug_tab()
        self.adv_tabs.addTab(tab_debug, tr("tab_debug"))
        tab_other = self.create_other_tab()
        self.adv_tabs.addTab(tab_other, tr("tab_other"))
        tab_custom_hw = self.create_custom_hw_tab()
        self.adv_tabs.addTab(tab_custom_hw, tr("tab_custom_hw"))

        main_layout.addWidget(self.adv_tabs, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.reset_btn = QPushButton(tr("btn_reset_adv"))
        self.reset_btn.clicked.connect(self.reset_to_default)
        btn_row.addWidget(self.reset_btn)
        main_layout.addLayout(btn_row)

    def unlock_advanced(self):
        if self.warning_acknowledged:
            return
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(tr("warning"))
        msg_box.setText(tr("adv_unlock_warning"))
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        reply = msg_box.exec()
        if reply == QMessageBox.Yes:
            self.warning_acknowledged = True
            self.adv_tabs.setEnabled(True)
            self.status_label.setText(tr("adv_unlocked"))
            self.status_label.setStyleSheet("color: #A8E6CF; font-weight: bold; font-size: 12px;")
            self.unlock_btn.setText(tr("btn_unlocked"))
            self.unlock_btn.setStyleSheet("""
                QPushButton { background-color: #A8E6CF; color: white; font-weight: bold; padding: 4px 16px; border-radius: 12px; font-size: 12px; border: none; }
                QPushButton:hover { background-color: #8CD4B8; }
            """)
            self.unlock_btn.setEnabled(False)
            QMessageBox.information(self, tr("adv_acknowledged"), tr("adv_acknowledged"))

    def create_disk_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(4)
        grid = QGridLayout()
        grid.setVerticalSpacing(5)
        grid.setHorizontalSpacing(8)
        row = 0
        grid.addWidget(QLabel(tr("label_cache")), row, 0)
        self.cache_combo = QComboBox()
        self.cache_combo.addItems(["writeback", "none", "writethrough", "directsync", "unsafe"])
        grid.addWidget(self.cache_combo, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_aio")), row, 0)
        self.aio_combo = QComboBox()
        self.aio_combo.addItems(["默认", "native", "threads", "io_uring"])
        grid.addWidget(self.aio_combo, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_discard")), row, 0)
        self.discard_combo = QComboBox()
        self.discard_combo.addItems(["默认", "on", "off"])
        grid.addWidget(self.discard_combo, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_detect_zeroes")), row, 0)
        self.detect_zeroes_combo = QComboBox()
        self.detect_zeroes_combo.addItems(["默认", "on", "off"])
        grid.addWidget(self.detect_zeroes_combo, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_backing")), row, 0)
        backing_row = QHBoxLayout()
        self.backing_edit = QLineEdit()
        self.backing_edit.setPlaceholderText(tr("label_backing"))
        backing_row.addWidget(self.backing_edit)
        self.backing_browse_btn = QPushButton(tr("btn_browse"))
        self.backing_browse_btn.clicked.connect(lambda: self.browse_backing_file())
        backing_row.addWidget(self.backing_browse_btn)
        grid.addLayout(backing_row, row, 1)
        row += 1
        self.snapshot_check = QCheckBox(tr("check_snapshot"))
        grid.addWidget(self.snapshot_check, row, 0, 1, 2)
        row += 1
        self.disk_readonly_check = QCheckBox(tr("check_readonly"))
        grid.addWidget(self.disk_readonly_check, row, 0, 1, 2)
        layout.addLayout(grid)
        layout.addStretch()
        return widget

    def create_network_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(4)
        grid = QGridLayout()
        grid.setVerticalSpacing(5)
        grid.setHorizontalSpacing(8)
        row = 0
        grid.addWidget(QLabel(tr("label_hostfwd")), row, 0)
        self.hostfwd_edit = QLineEdit()
        self.hostfwd_edit.setPlaceholderText("例: tcp::2222-:22")
        grid.addWidget(self.hostfwd_edit, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_subnet")), row, 0)
        self.net_subnet_edit = QLineEdit()
        self.net_subnet_edit.setPlaceholderText("例: 192.168.1.0/24")
        grid.addWidget(self.net_subnet_edit, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_dns")), row, 0)
        self.net_dns_edit = QLineEdit()
        self.net_dns_edit.setPlaceholderText("例: 8.8.8.8")
        grid.addWidget(self.net_dns_edit, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_tap")), row, 0)
        self.tap_edit = QLineEdit()
        self.tap_edit.setPlaceholderText("例: tap0")
        grid.addWidget(self.tap_edit, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_mac")), row, 0)
        self.mac_edit = QLineEdit()
        self.mac_edit.setPlaceholderText("例: 52:54:00:12:34:56")
        grid.addWidget(self.mac_edit, row, 1)
        row += 1
        self.net_restrict_check = QCheckBox(tr("check_net_restrict"))
        grid.addWidget(self.net_restrict_check, row, 0, 1, 2)
        layout.addLayout(grid)
        layout.addStretch()
        return widget

    def create_cpu_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(4)
        grid = QGridLayout()
        grid.setVerticalSpacing(5)
        grid.setHorizontalSpacing(8)
        row = 0
        grid.addWidget(QLabel(tr("label_cpu_flags")), row, 0)
        self.cpu_flags_edit = QLineEdit()
        self.cpu_flags_edit.setPlaceholderText("例: +aes,+avx,-hypervisor")
        grid.addWidget(self.cpu_flags_edit, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_numa")), row, 0)
        self.numa_edit = QLineEdit()
        self.numa_edit.setPlaceholderText("例: node,cpus=0-3,mem=4096")
        grid.addWidget(self.numa_edit, row, 1)
        row += 1
        self.mem_prealloc_check = QCheckBox(tr("check_mem_prealloc"))
        grid.addWidget(self.mem_prealloc_check, row, 0, 1, 2)
        row += 1
        self.hugepages_check = QCheckBox(tr("check_hugepages"))
        grid.addWidget(self.hugepages_check, row, 0, 1, 2)
        row += 1
        self.no_hpet_adv_check = QCheckBox("⏱️ 禁用 HPET")
        grid.addWidget(self.no_hpet_adv_check, row, 0, 1, 2)
        row += 1
        self.no_kvm_nested_check = QCheckBox("🚫 禁用 KVM 嵌套虚拟化")
        grid.addWidget(self.no_kvm_nested_check, row, 0, 1, 2)
        row += 1
        self.force_tcg_check = QCheckBox("⚠️ 强制 TCG 模式")
        self.force_tcg_check.setStyleSheet("QCheckBox { color: #FF8A9C; }")
        grid.addWidget(self.force_tcg_check, row, 0, 1, 2)
        layout.addLayout(grid)
        layout.addStretch()
        return widget

    def create_display_adv_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(4)
        grid = QGridLayout()
        grid.setVerticalSpacing(5)
        grid.setHorizontalSpacing(8)
        row = 0
        self.usb_tablet_check = QCheckBox("🖱️ USB 平板模式 (绝对坐标) ✅")
        self.usb_tablet_check.setChecked(True)
        grid.addWidget(self.usb_tablet_check, row, 0, 1, 2)
        row += 1
        self.no_mouse_integration_check = QCheckBox("🚫 禁用鼠标集成")
        grid.addWidget(self.no_mouse_integration_check, row, 0, 1, 2)
        row += 1
        grid.addWidget(QLabel(tr("label_bios")), row, 0)
        bios_row = QHBoxLayout()
        self.bios_edit = QLineEdit()
        self.bios_edit.setPlaceholderText("留空使用默认 BIOS")
        bios_row.addWidget(self.bios_edit)
        self.bios_browse_btn = QPushButton(tr("btn_browse"))
        self.bios_browse_btn.clicked.connect(lambda: self.browse_bios_file())
        bios_row.addWidget(self.bios_browse_btn)
        grid.addLayout(bios_row, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_vnc_password")), row, 0)
        self.vnc_password_edit = QLineEdit()
        self.vnc_password_edit.setEchoMode(QLineEdit.Password)
        self.vnc_password_edit.setPlaceholderText("留空无密码")
        grid.addWidget(self.vnc_password_edit, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_spice_port")), row, 0)
        self.spice_port_edit = QLineEdit()
        self.spice_port_edit.setPlaceholderText("例: 5900")
        grid.addWidget(self.spice_port_edit, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_spice_password")), row, 0)
        self.spice_password_edit = QLineEdit()
        self.spice_password_edit.setEchoMode(QLineEdit.Password)
        self.spice_password_edit.setPlaceholderText("留空无密码")
        grid.addWidget(self.spice_password_edit, row, 1)
        layout.addLayout(grid)
        layout.addStretch()
        return widget

    def create_debug_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(4)
        grid = QGridLayout()
        grid.setVerticalSpacing(5)
        grid.setHorizontalSpacing(8)
        row = 0
        grid.addWidget(QLabel(tr("label_log_file")), row, 0)
        log_row = QHBoxLayout()
        self.log_edit = QLineEdit()
        self.log_edit.setPlaceholderText("留空不输出日志")
        log_row.addWidget(self.log_edit)
        self.log_browse_btn = QPushButton(tr("btn_browse"))
        self.log_browse_btn.clicked.connect(lambda: self.browse_log_file())
        log_row.addWidget(self.log_browse_btn)
        grid.addLayout(log_row, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_debug_level")), row, 0)
        self.debug_combo = QComboBox()
        self.debug_combo.addItems(["默认", "cpu", "exec", "int", "mmu", "pci", "qmp", "all"])
        grid.addWidget(self.debug_combo, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_qmp_socket")), row, 0)
        self.qmp_edit = QLineEdit()
        self.qmp_edit.setPlaceholderText("例: /tmp/qmp.sock")
        grid.addWidget(self.qmp_edit, row, 1)
        row += 1
        self.monitor_stdio_check = QCheckBox(tr("check_monitor_stdio"))
        grid.addWidget(self.monitor_stdio_check, row, 0, 1, 2)
        row += 1
        self.no_reboot_check = QCheckBox("🚫 崩溃后不重启")
        grid.addWidget(self.no_reboot_check, row, 0, 1, 2)
        row += 1
        self.no_shutdown_check = QCheckBox("🚫 不关机")
        grid.addWidget(self.no_shutdown_check, row, 0, 1, 2)
        row += 1
        self.sandbox_check = QCheckBox(tr("check_sandbox"))
        grid.addWidget(self.sandbox_check, row, 0, 1, 2)
        layout.addLayout(grid)
        layout.addStretch()
        return widget

    def create_other_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(4)
        grid = QGridLayout()
        grid.setVerticalSpacing(5)
        grid.setHorizontalSpacing(8)
        row = 0
        grid.addWidget(QLabel(tr("label_rtc")), row, 0)
        self.rtc_edit = QLineEdit()
        self.rtc_edit.setPlaceholderText("例: 2020-01-01T00:00:00")
        grid.addWidget(self.rtc_edit, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_seed")), row, 0)
        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText("例: 0xdeadbeef")
        grid.addWidget(self.seed_edit, row, 1)
        row += 1
        grid.addWidget(QLabel(tr("label_boot_once")), row, 0)
        self.boot_once_edit = QLineEdit()
        self.boot_once_edit.setPlaceholderText("例: cdrom")
        grid.addWidget(self.boot_once_edit, row, 1)
        row += 1
        self.boot_menu_check = QCheckBox("📋 显示启动菜单")
        grid.addWidget(self.boot_menu_check, row, 0, 1, 2)
        row += 1
        grid.addWidget(QLabel(tr("label_extra_adv")), row, 0)
        self.extra_adv_edit = QTextEdit()
        self.extra_adv_edit.setPlaceholderText("每行一个 QEMU 参数")
        self.extra_adv_edit.setMaximumHeight(60)
        grid.addWidget(self.extra_adv_edit, row, 1)
        layout.addLayout(grid)
        layout.addStretch()
        return widget

    def create_custom_hw_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(4)
        info_label = QLabel(tr("msg_custom_hw"))
        info_label.setStyleSheet("color: #888; font-size: 11px; padding: 8px; background: #FFF3E0; border-radius: 10px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        self.custom_hw_btn = QPushButton("🔧 " + tr("tab_custom_hw"))
        self.custom_hw_btn.setMinimumHeight(40)
        self.custom_hw_btn.setStyleSheet("""
            QPushButton { background-color: #D4A5FF; color: white; font-weight: bold; border-radius: 8px; border: none; font-size: 13px; }
            QPushButton:hover { background-color: #C48AF0; }
        """)
        self.custom_hw_btn.clicked.connect(self.open_custom_hw)
        layout.addWidget(self.custom_hw_btn)
        layout.addStretch()
        return widget

    def open_custom_hw(self):
        if self._custom_hw_dialog:
            self._custom_hw_dialog.raise_()
            self._custom_hw_dialog.activateWindow()
            return
        vm = self._vm_ref
        if not vm:
            parent = self.parent_dialog
            if hasattr(parent, 'vm'):
                vm = parent.vm
            elif hasattr(parent, 'existing_vm'):
                vm = parent.existing_vm
        if vm:
            self._custom_hw_dialog = CustomHardwareDialog(vm, self)
            self._custom_hw_dialog.finished.connect(self._custom_hw_closed)
            self._custom_hw_dialog.show()

    def _custom_hw_closed(self):
        self._custom_hw_dialog = None

    def set_vm_ref(self, vm):
        self._vm_ref = vm

    def browse_log_file(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("label_log_file"), str(BASE_DIR), "日志文件 (*.log);;所有文件 (*)")
        if path:
            self.log_edit.setText(path)

    def browse_bios_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("label_bios_browse"), str(BASE_DIR), "BIOS 文件 (*.bin *.rom);;所有文件 (*)")
        if path:
            self.bios_edit.setText(path)

    def browse_backing_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("label_backing"), str(VMS_DIR), "磁盘镜像 (*.qcow2 *.img *.raw *.vmdk);;所有文件 (*)")
        if path:
            self.backing_edit.setText(path)

    def reset_to_default(self):
        reply = QMessageBox.question(self, tr("confirm"), tr("adv_reset_confirm"), QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.cache_combo.setCurrentText("writeback")
        self.aio_combo.setCurrentText("默认")
        self.discard_combo.setCurrentText("默认")
        self.detect_zeroes_combo.setCurrentText("默认")
        self.backing_edit.setText("")
        self.snapshot_check.setChecked(False)
        self.disk_readonly_check.setChecked(False)
        self.hostfwd_edit.setText("")
        self.net_subnet_edit.setText("")
        self.net_dns_edit.setText("")
        self.tap_edit.setText("")
        self.mac_edit.setText("")
        self.net_restrict_check.setChecked(False)
        self.cpu_flags_edit.setText("")
        self.numa_edit.setText("")
        self.mem_prealloc_check.setChecked(False)
        self.hugepages_check.setChecked(False)
        self.no_hpet_adv_check.setChecked(False)
        self.no_kvm_nested_check.setChecked(False)
        self.force_tcg_check.setChecked(False)
        self.usb_tablet_check.setChecked(True)
        self.bios_edit.setText("")
        self.vnc_password_edit.setText("")
        self.spice_port_edit.setText("")
        self.spice_password_edit.setText("")
        self.no_mouse_integration_check.setChecked(False)
        self.log_edit.setText("")
        self.debug_combo.setCurrentText("默认")
        self.qmp_edit.setText("")
        self.monitor_stdio_check.setChecked(False)
        self.no_reboot_check.setChecked(False)
        self.no_shutdown_check.setChecked(False)
        self.sandbox_check.setChecked(False)
        self.rtc_edit.setText("")
        self.seed_edit.setText("")
        self.boot_once_edit.setText("")
        self.boot_menu_check.setChecked(False)
        self.extra_adv_edit.setText("")
        QMessageBox.information(self, tr("adv_reset_done"), tr("adv_reset_ok"))

    def get_config(self) -> dict:
        return {
            "cache": self.cache_combo.currentText(),
            "aio": self.aio_combo.currentText(),
            "discard": self.discard_combo.currentText(),
            "detect_zeroes": self.detect_zeroes_combo.currentText(),
            "backing_file": self.backing_edit.text().strip(),
            "snapshot_mode": self.snapshot_check.isChecked(),
            "disk_readonly": self.disk_readonly_check.isChecked(),
            "hostfwd": self.hostfwd_edit.text().strip(),
            "net_subnet": self.net_subnet_edit.text().strip(),
            "net_dns": self.net_dns_edit.text().strip(),
            "net_restrict": self.net_restrict_check.isChecked(),
            "tap_interface": self.tap_edit.text().strip(),
            "mac_address": self.mac_edit.text().strip(),
            "cpu_flags": self.cpu_flags_edit.text().strip(),
            "numa_config": self.numa_edit.text().strip(),
            "mem_prealloc": self.mem_prealloc_check.isChecked(),
            "hugepages": self.hugepages_check.isChecked(),
            "no_hpet_adv": self.no_hpet_adv_check.isChecked(),
            "no_kvm_nested": self.no_kvm_nested_check.isChecked(),
            "force_tcg": self.force_tcg_check.isChecked(),
            "usb_tablet": self.usb_tablet_check.isChecked(),
            "bios_file": self.bios_edit.text().strip(),
            "vnc_password": self.vnc_password_edit.text().strip(),
            "spice_port": self.spice_port_edit.text().strip(),
            "spice_password": self.spice_password_edit.text().strip(),
            "no_mouse_integration": self.no_mouse_integration_check.isChecked(),
            "log_file": self.log_edit.text().strip(),
            "debug_level": self.debug_combo.currentText(),
            "qmp_socket": self.qmp_edit.text().strip(),
            "monitor_stdio": self.monitor_stdio_check.isChecked(),
            "no_reboot": self.no_reboot_check.isChecked(),
            "no_shutdown": self.no_shutdown_check.isChecked(),
            "sandbox": self.sandbox_check.isChecked(),
            "rtc_base": self.rtc_edit.text().strip(),
            "seed_value": self.seed_edit.text().strip(),
            "boot_menu": self.boot_menu_check.isChecked(),
            "boot_once": self.boot_once_edit.text().strip(),
            "extra_advanced_args": self.extra_adv_edit.toPlainText().strip(),
        }

    def set_config(self, config: dict):
        if not config:
            return
        try:
            self.cache_combo.setCurrentText(config.get("cache", "writeback"))
            self.aio_combo.setCurrentText(config.get("aio", "默认"))
            self.discard_combo.setCurrentText(config.get("discard", "默认"))
            self.detect_zeroes_combo.setCurrentText(config.get("detect_zeroes", "默认"))
            self.backing_edit.setText(config.get("backing_file", ""))
            self.snapshot_check.setChecked(config.get("snapshot_mode", False))
            self.disk_readonly_check.setChecked(config.get("disk_readonly", False))
            self.hostfwd_edit.setText(config.get("hostfwd", ""))
            self.net_subnet_edit.setText(config.get("net_subnet", ""))
            self.net_dns_edit.setText(config.get("net_dns", ""))
            self.net_restrict_check.setChecked(config.get("net_restrict", False))
            self.tap_edit.setText(config.get("tap_interface", ""))
            self.mac_edit.setText(config.get("mac_address", ""))
            self.cpu_flags_edit.setText(config.get("cpu_flags", ""))
            self.numa_edit.setText(config.get("numa_config", ""))
            self.mem_prealloc_check.setChecked(config.get("mem_prealloc", False))
            self.hugepages_check.setChecked(config.get("hugepages", False))
            self.no_hpet_adv_check.setChecked(config.get("no_hpet_adv", False))
            self.no_kvm_nested_check.setChecked(config.get("no_kvm_nested", False))
            self.force_tcg_check.setChecked(config.get("force_tcg", False))
            self.usb_tablet_check.setChecked(config.get("usb_tablet", True))
            self.bios_edit.setText(config.get("bios_file", ""))
            self.vnc_password_edit.setText(config.get("vnc_password", ""))
            self.spice_port_edit.setText(config.get("spice_port", ""))
            self.spice_password_edit.setText(config.get("spice_password", ""))
            self.no_mouse_integration_check.setChecked(config.get("no_mouse_integration", False))
            self.log_edit.setText(config.get("log_file", ""))
            self.debug_combo.setCurrentText(config.get("debug_level", "默认"))
            self.qmp_edit.setText(config.get("qmp_socket", ""))
            self.monitor_stdio_check.setChecked(config.get("monitor_stdio", False))
            self.no_reboot_check.setChecked(config.get("no_reboot", False))
            self.no_shutdown_check.setChecked(config.get("no_shutdown", False))
            self.sandbox_check.setChecked(config.get("sandbox", False))
            self.rtc_edit.setText(config.get("rtc_base", ""))
            self.seed_edit.setText(config.get("seed_value", ""))
            self.boot_menu_check.setChecked(config.get("boot_menu", False))
            self.boot_once_edit.setText(config.get("boot_once", ""))
            self.extra_adv_edit.setText(config.get("extra_advanced_args", ""))
        except Exception as e:
            print(f"⚠️ 加载高级配置时出错: {e}")

# ============================================================
# 声卡参数生成
# ============================================================
def get_sound_params(year, config_sound, os_type, arch, features):
    if config_sound == "none" or os_type == "Android" or arch not in ["x86", "x86_64"]:
        return []
    supports_audiodev = features.get("audiodev", False)
    if supports_audiodev:
        if sys.platform == "win32":
            audio_backend = "dsound"
        elif sys.platform == "darwin":
            audio_backend = "coreaudio"
        else:
            audio_backend = "pa"
        if config_sound == "ac97":
            return ["-audiodev", f"{audio_backend},id=audio0", "-device", "AC97,audiodev=audio0"]
        elif config_sound == "sb16":
            return ["-audiodev", f"{audio_backend},id=audio0", "-device", "sb16,audiodev=audio0"]
        else:
            return ["-audiodev", f"{audio_backend},id=audio0", "-device", "intel-hda", "-device", "hda-duplex,audiodev=audio0"]
    if year <= 2013:
        return ["-soundhw", "sb16"]
    elif year <= 2019:
        return ["-soundhw", "ac97"]
    else:
        return ["-soundhw", "ac97"] if config_sound == "ac97" else ["-soundhw", "hda"]


# ========== 常量 ==========
DISK_INTERFACES = ["ide", "sata", "virtio", "scsi", "nvme", "usb", "sd", "floppy"]
DISK_FORMATS = ["qcow2", "raw", "vmdk", "vdi", "vhdx", "qcow", "cow", "parallels", "dmg", "bochs", "cloop", "luks", "qed", "vpc", "vvfat"]
MACHINE_TYPES = ["pc", "q35", "pc-i440fx-11.1", "pc-i440fx-9.2", "pc-q35-11.1", "pc-q35-9.2", "virt", "microvm"]
ACCEL_MODES = ["tcg", "hax", "whpx", "kvm", "hvf", "qtest", "none"]
VGA_TYPES = ["virtio", "std", "cirrus", "vmvga", "qxl", "none", "bochs", "ramfb", "sga"]
DISPLAY_TYPES = ["gtk", "sdl", "none", "curses", "spice", "egl-headless"]
SOUND_TYPES = ["hda", "ac97", "sb16", "ich9-intel-hda", "none", "cs4231a", "gus", "intel-hda", "isa", "pcspk", "pl041"]
NIC_TYPES = ["virtio", "e1000", "rtl8139", "pcnet", "e1000e", "vmxnet3", "usb-net", "ne2k_pci"]
BOOT_TYPES = ["cdrom", "disk", "floppy", "network", "memtest"]
RESOLUTIONS = ["自定义", "640x480", "800x600", "1024x768", "1280x720", "1366x768", "1600x900", "1920x1080", "2560x1440", "3840x2160"]


SYSTEM_PRESETS = {
    "Windows XP": {
        "os_type": "Windows", "os_version": "XP", "arch": "x86",
        "memory": 512, "cpu": 1, "disk_size": 16, "disk_format": "qcow2",
        "disk_interface": "ide", "cpu_model": "qemu32",
        "accel": "tcg", "vga": "cirrus", "display": "gtk",
        "resolution": "1024x768", "machine_type": "pc",
        "acpi": False, "usb": True, "sound": "sb16",
        "boot_order": "cdrom", "opengl": False, "nic_model": "rtl8139",
        "qemu_version": "qemu-w64-setup-2016",
        "description": "Windows XP 经典版，推荐 QEMU 2015-2016"
    },
    "Windows 7": {
        "os_type": "Windows", "os_version": "7", "arch": "x86_64",
        "memory": 2048, "cpu": 2, "disk_size": 32, "disk_format": "qcow2",
        "disk_interface": "sata", "cpu_model": "core2duo",
        "accel": "tcg", "vga": "std", "display": "gtk",
        "resolution": "1280x720", "machine_type": "pc",
        "acpi": True, "usb": True, "sound": "ac97",
        "boot_order": "cdrom", "opengl": False, "nic_model": "e1000",
        "qemu_version": "qemu-w64-setup-2019",
        "description": "Windows 7 推荐配置，推荐 QEMU 2017-2019"
    },
    "Windows 8.1": {
        "os_type": "Windows", "os_version": "8.1", "arch": "x86_64",
        "memory": 2048, "cpu": 2, "disk_size": 32, "disk_format": "qcow2",
        "disk_interface": "sata", "cpu_model": "host",
        "accel": "hax", "vga": "std", "display": "gtk",
        "resolution": "1280x720", "machine_type": "q35",
        "acpi": True, "usb": True, "sound": "ac97",
        "boot_order": "cdrom", "opengl": False, "nic_model": "e1000",
        "qemu_version": "qemu-w64-setup-20190815",
        "description": "Windows 8.1 推荐配置，推荐 QEMU 2019"
    },
    "Windows 10": {
        "os_type": "Windows", "os_version": "10", "arch": "x86_64",
        "memory": 4096, "cpu": 4, "disk_size": 64, "disk_format": "qcow2",
        "disk_interface": "virtio", "cpu_model": "host",
        "accel": "hax", "vga": "virtio", "display": "gtk",
        "resolution": "1920x1080", "machine_type": "q35",
        "acpi": True, "usb": True, "sound": "hda",
        "boot_order": "cdrom", "opengl": True, "nic_model": "virtio",
        "qemu_version": "qemu-w64-setup-20251224",
        "description": "Windows 10 推荐配置，推荐 QEMU 2020+"
    },
    "Windows 11": {
        "os_type": "Windows", "os_version": "11", "arch": "x86_64",
        "memory": 8192, "cpu": 4, "disk_size": 80, "disk_format": "qcow2",
        "disk_interface": "virtio", "cpu_model": "host",
        "accel": "hax", "vga": "virtio", "display": "gtk",
        "resolution": "1920x1080", "machine_type": "q35",
        "acpi": True, "usb": True, "sound": "hda",
        "boot_order": "cdrom", "opengl": True, "nic_model": "virtio",
        "qemu_version": "qemu-w64-setup-20251224",
        "description": "Windows 11 推荐配置，推荐 QEMU 2021+"
    },
    "Ubuntu 22.04": {
        "os_type": "Linux", "os_version": "Ubuntu", "arch": "x86_64",
        "memory": 4096, "cpu": 4, "disk_size": 40, "disk_format": "qcow2",
        "disk_interface": "virtio", "cpu_model": "host",
        "accel": "hax", "vga": "virtio", "display": "gtk",
        "resolution": "1920x1080", "machine_type": "q35",
        "acpi": True, "usb": True, "sound": "hda",
        "boot_order": "cdrom", "opengl": True, "nic_model": "virtio",
        "qemu_version": "qemu-w64-setup-20251224",
        "description": "Ubuntu 22.04 推荐配置"
    },
    "Debian 12": {
        "os_type": "Linux", "os_version": "Debian", "arch": "x86_64",
        "memory": 2048, "cpu": 2, "disk_size": 32, "disk_format": "qcow2",
        "disk_interface": "sata", "cpu_model": "host",
        "accel": "hax", "vga": "std", "display": "gtk",
        "resolution": "1280x720", "machine_type": "q35",
        "acpi": True, "usb": True, "sound": "hda",
        "boot_order": "cdrom", "opengl": False, "nic_model": "e1000",
        "qemu_version": "qemu-w64-setup-20251224",
        "description": "Debian 12 推荐配置"
    },
    "Android x86 9.0": {
        "os_type": "Android", "os_version": "Android", "arch": "x86_64",
        "memory": 2048, "cpu": 2, "disk_size": 16, "disk_format": "qcow2",
        "disk_interface": "ide", "cpu_model": "qemu64",
        "accel": "tcg", "vga": "std", "display": "gtk",
        "resolution": "自定义", "machine_type": "pc",
        "acpi": False, "usb": True, "sound": "none",
        "boot_order": "cdrom", "opengl": False, "nic_model": "e1000",
        "qemu_version": "qemu-w64-setup-20190815",
        "description": "Android x86 9.0，推荐 QEMU 2019 + IDE 硬盘"
    },
    "macOS Catalina": {
        "os_type": "macOS", "os_version": "Catalina", "arch": "x86_64",
        "memory": 4096, "cpu": 4, "disk_size": 64, "disk_format": "qcow2",
        "disk_interface": "sata", "cpu_model": "host",
        "accel": "hvf", "vga": "vmvga", "display": "gtk",
        "resolution": "1920x1080", "machine_type": "q35",
        "acpi": True, "usb": True, "sound": "hda",
        "boot_order": "cdrom", "opengl": True, "nic_model": "e1000",
        "qemu_version": "qemu-w64-setup-20251224",
        "description": "macOS Catalina，推荐 QEMU 2020+"
    },
    "FreeBSD 13": {
        "os_type": "其他", "os_version": "FreeBSD", "arch": "x86_64",
        "memory": 1024, "cpu": 2, "disk_size": 16, "disk_format": "qcow2",
        "disk_interface": "virtio", "cpu_model": "host",
        "accel": "tcg", "vga": "std", "display": "gtk",
        "resolution": "1024x768", "machine_type": "q35",
        "acpi": True, "usb": True, "sound": "none",
        "boot_order": "cdrom", "opengl": False, "nic_model": "virtio",
        "qemu_version": "qemu-w64-setup-20251224",
        "description": "FreeBSD 13 推荐配置"
    },
    "最小化 Linux": {
        "os_type": "Linux", "os_version": "其他", "arch": "x86_64",
        "memory": 512, "cpu": 1, "disk_size": 8, "disk_format": "qcow2",
        "disk_interface": "ide", "cpu_model": "qemu64",
        "accel": "tcg", "vga": "none", "display": "none",
        "resolution": "自定义", "machine_type": "pc",
        "acpi": True, "usb": False, "sound": "none",
        "boot_order": "cdrom", "opengl": False, "nic_model": "e1000",
        "qemu_version": "qemu-w64-setup-20251224",
        "description": "最小化 Linux，资源占用极少"
    }
}

QEMU_VERSIONS_INFO = {
    "qemu-w64-setup-2016": {"year": 2016, "arch": "x86_64", "desc": "XP/7 专用"},
    "qemu-w64-setup-20190815": {"year": 2019, "arch": "x86_64", "desc": "过渡版，Android/8.1"},
    "qemu-w64-setup-20251224": {"year": 2025, "arch": "x86_64", "desc": "最新版，Win10/11"},
}

def get_qemu_version_info(version):
    for key, info in QEMU_VERSIONS_INFO.items():
        if key in version or version in key:
            return info
    return {"year": 2020, "arch": "x86_64", "desc": "未知版本"}

def get_qemu_year(qemu_version):
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


# ============================================================
# 创建/编辑虚拟机对话框
# ============================================================
class CreateVMDialog(QDialog):
    def __init__(self, parent=None, existing_vm=None):
        super().__init__(parent)
        self.parent = parent
        self.existing_vm = existing_vm
        self.vm = existing_vm if existing_vm else VMConfig()
        self.history = ConfigHistory()
        self._temp_iso_path = ""
        self._temp_driver_path = ""
        self._temp_share_dir = ""
        self._pending_usb_devices = []
        self._pending_pci_devices = []
        self.hardware_detector = parent.hardware_detector if parent else QEMUHardwareDetector()
        self.init_ui()
        if existing_vm:
            self.setWindowTitle(f"✏️ 编辑 - {existing_vm.name}")
            self.create_btn.setText("💾 保存")
            self.name_edit.setReadOnly(True)
            self.name_edit.setStyleSheet("color: #888;")
            self.load_vm_data(existing_vm)
        else:
            self.setWindowTitle("📦 新建虚拟机")
            self.create_btn.setText("✅ 创建")
        self.on_qemu_version_changed()
        self.load_hardware_profiles()

    def init_ui(self):
        font = QFont("Microsoft YaHei", 12)
        self.setFont(font)
        self.setMinimumSize(1100, 850)
        self.resize(1100, 850)
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)
        self.tab_widget = QTabWidget()
        self.tab_widget.setFont(font)

        self.tab_widget.addTab(self.create_basic_tab(), "📋 基本信息")
        self.tab_widget.addTab(self.create_hardware_tab(), "🔧 硬件配置")
        self.tab_widget.addTab(self.create_display_tab(), "🖥️ 显示/声音")
        self.tab_widget.addTab(self.create_network_tab(), "🌐 网络")
        self.tab_widget.addTab(self.create_passthrough_tab(), "🔌 硬件直通")

        self.advanced_widget = AdvancedOptionsWidget(self)
        self.advanced_widget.set_vm_ref(self.vm)
        adv_tab = QWidget()
        adv_layout = QVBoxLayout(adv_tab)
        adv_layout.addWidget(self.advanced_widget)
        self.tab_widget.addTab(adv_tab, "⚙️ 高级配置")

        main_layout.addWidget(self.tab_widget, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        history_btn = QPushButton("📜 历史配置")
        history_btn.setMinimumHeight(34)
        history_btn.clicked.connect(self.show_history)
        btn_layout.addWidget(history_btn)
        self.create_btn = QPushButton("✅ 创建")
        self.create_btn.setMinimumHeight(40)
        self.create_btn.setMinimumWidth(120)
        self.create_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; border-radius: 8px; font-size: 14px; padding: 8px 20px;")
        self.create_btn.clicked.connect(self.save)
        btn_layout.addWidget(self.create_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.setStyleSheet("background-color: #666; color: white; border-radius: 8px; font-size: 14px; padding: 8px 20px;")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)

    def create_basic_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        preset_group = QGroupBox("🏷️ 预设模板")
        preset_group.setFont(QFont("Microsoft YaHei", 12))
        preset_layout = QVBoxLayout(preset_group)
        row = QHBoxLayout()
        row.addWidget(QLabel("预设:"))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumHeight(32)
        for name in SYSTEM_PRESETS.keys():
            self.preset_combo.addItem(name)
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        row.addWidget(self.preset_combo, 1)
        preset_help = QPushButton("帮助")
        preset_help.setFixedSize(64, 32)
        preset_help.clicked.connect(self.show_preset_help)
        row.addWidget(preset_help)
        preset_layout.addLayout(row)
        self.preset_desc = QLabel("")
        self.preset_desc.setStyleSheet("color: #aaa; font-size: 11px; padding: 4px 8px; background: #3a3a3a; border-radius: 6px;")
        self.preset_desc.setWordWrap(True)
        preset_layout.addWidget(self.preset_desc)
        layout.addWidget(preset_group)

        basic_group = QGroupBox("📋 基本信息")
        basic_group.setFont(QFont("Microsoft YaHei", 12))
        grid = QGridLayout(basic_group)
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(12)
        row = 0
        grid.addWidget(QLabel("名称:"), row, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setMinimumHeight(32)
        self.name_edit.setPlaceholderText("输入名称（英文或数字）")
        grid.addWidget(self.name_edit, row, 1)
        row += 1
        grid.addWidget(QLabel("系统类型:"), row, 0)
        self.os_combo = QComboBox()
        self.os_combo.setMinimumHeight(32)
        self.os_combo.addItems(["Windows", "Linux", "Android", "macOS", "其他"])
        grid.addWidget(self.os_combo, row, 1)
        row += 1
        grid.addWidget(QLabel("系统版本:"), row, 0)
        self.version_combo = QComboBox()
        self.version_combo.setMinimumHeight(32)
        self.version_combo.addItems(["XP", "7", "8.1", "10", "11", "Server", "Ubuntu", "Debian", "Fedora", "Android", "Catalina", "FreeBSD", "其他"])
        grid.addWidget(self.version_combo, row, 1)
        row += 1
        grid.addWidget(QLabel("架构:"), row, 0)
        self.arch_combo = QComboBox()
        self.arch_combo.setMinimumHeight(32)
        self.arch_combo.addItems(["x86", "x86_64", "ARM64"])
        grid.addWidget(self.arch_combo, row, 1)
        row += 1

        grid.addWidget(QLabel("QEMU 版本:"), row, 0)
        qemu_layout = QHBoxLayout()
        self.qemu_version_combo = QComboBox()
        self.qemu_version_combo.setMinimumHeight(32)
        versions = list(self.hardware_detector.qemu_versions.keys())
        if versions:
            self.qemu_version_combo.addItems(versions)
        else:
            self.qemu_version_combo.addItem("未检测到 QEMU")
        self.qemu_version_combo.currentTextChanged.connect(self.on_qemu_version_changed)
        qemu_layout.addWidget(self.qemu_version_combo, 1)
        self.qemu_browse_btn = QPushButton("📂 选择")
        self.qemu_browse_btn.setMinimumHeight(32)
        self.qemu_browse_btn.setToolTip("选择自定义 QEMU 可执行文件")
        self.qemu_browse_btn.clicked.connect(self.browse_custom_qemu)
        qemu_layout.addWidget(self.qemu_browse_btn)
        grid.addLayout(qemu_layout, row, 1)
        row += 1

        self.hw_info_label = QLabel("🔍 点击刷新检测硬件")
        self.hw_info_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        grid.addWidget(self.hw_info_label, row, 0, 1, 2)
        layout.addWidget(basic_group)
        layout.addStretch()
        return widget

    def create_hardware_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        cpu_group = QGroupBox("💻 CPU/内存")
        cpu_group.setFont(QFont("Microsoft YaHei", 12))
        grid = QGridLayout(cpu_group)
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(12)
        row = 0
        grid.addWidget(QLabel("内存 (MB):"), row, 0)
        self.memory_spin = QSpinBox()
        self.memory_spin.setMinimumHeight(32)
        self.memory_spin.setRange(128, 65536)
        self.memory_spin.setSingleStep(512)
        grid.addWidget(self.memory_spin, row, 1)
        row += 1
        grid.addWidget(QLabel("CPU 核心:"), row, 0)
        self.cpu_spin = QSpinBox()
        self.cpu_spin.setMinimumHeight(32)
        self.cpu_spin.setRange(1, 32)
        grid.addWidget(self.cpu_spin, row, 1)
        row += 1
        grid.addWidget(QLabel("CPU 线程数:"), row, 0)
        self.smp_threads_spin = QSpinBox()
        self.smp_threads_spin.setMinimumHeight(32)
        self.smp_threads_spin.setRange(1, 8)
        grid.addWidget(self.smp_threads_spin, row, 1)
        row += 1
        grid.addWidget(QLabel("CPU 插槽:"), row, 0)
        self.smp_sockets_spin = QSpinBox()
        self.smp_sockets_spin.setMinimumHeight(32)
        self.smp_sockets_spin.setRange(1, 4)
        grid.addWidget(self.smp_sockets_spin, row, 1)
        row += 1
        grid.addWidget(QLabel("CPU 型号:"), row, 0)
        self.cpu_model_combo = QComboBox()
        self.cpu_model_combo.setMinimumHeight(32)
        self.cpu_model_combo.addItems(FORCE_CPU_MODELS)
        self.cpu_model_combo.setEditable(True)
        grid.addWidget(self.cpu_model_combo, row, 1)
        row += 1
        grid.addWidget(QLabel("硬件配置:"), row, 0)
        profile_layout = QHBoxLayout()
        self.cpu_profile_combo = QComboBox()
        self.cpu_profile_combo.setMinimumHeight(32)
        profile_layout.addWidget(self.cpu_profile_combo, 1)
        profile_mgr_btn = QPushButton("⚙️")
        profile_mgr_btn.setFixedSize(32, 32)
        profile_mgr_btn.setToolTip("管理硬件配置")
        profile_mgr_btn.clicked.connect(self.open_hardware_profile_manager)
        profile_layout.addWidget(profile_mgr_btn)
        grid.addLayout(profile_layout, row, 1)
        layout.addWidget(cpu_group)

        disk_group = QGroupBox("💾 磁盘")
        disk_group.setFont(QFont("Microsoft YaHei", 12))
        disk_layout = QGridLayout(disk_group)
        disk_layout.setVerticalSpacing(8)
        disk_layout.setHorizontalSpacing(12)
        row = 0
        disk_layout.addWidget(QLabel("磁盘大小 (GB):"), row, 0)
        self.disk_spin = QSpinBox()
        self.disk_spin.setMinimumHeight(32)
        self.disk_spin.setRange(1, 1024)
        disk_layout.addWidget(self.disk_spin, row, 1)
        disk_layout.addWidget(QLabel(" GB"), row, 2)
        row += 1
        disk_layout.addWidget(QLabel("磁盘格式:"), row, 0)
        self.disk_format_combo = QComboBox()
        self.disk_format_combo.setMinimumHeight(32)
        self.disk_format_combo.addItems(DISK_FORMATS)
        self.disk_format_combo.setCurrentText("qcow2")
        disk_layout.addWidget(self.disk_format_combo, row, 1, 1, 2)
        row += 1
        disk_layout.addWidget(QLabel("磁盘接口:"), row, 0)
        self.disk_interface_combo = QComboBox()
        self.disk_interface_combo.setMinimumHeight(32)
        self.disk_interface_combo.addItems(DISK_INTERFACES)
        self.disk_interface_combo.setCurrentText("sata")
        disk_layout.addWidget(self.disk_interface_combo, row, 1, 1, 2)
        layout.addWidget(disk_group)

        hw_group = QGroupBox("⚙️ 系统")
        hw_group.setFont(QFont("Microsoft YaHei", 12))
        grid2 = QGridLayout(hw_group)
        grid2.setVerticalSpacing(8)
        grid2.setHorizontalSpacing(12)
        row = 0
        grid2.addWidget(QLabel("加速模式:"), row, 0)
        self.accel_combo = QComboBox()
        self.accel_combo.setMinimumHeight(32)
        all_accel = ["tcg", "hax", "whpx", "kvm", "hvf"]
        self.accel_combo.addItems(all_accel)
        if hasattr(self.parent, 'hardware_detector'):
            default = self.parent.hardware_detector.default_accel
            idx = self.accel_combo.findText(default)
            if idx >= 0:
                self.accel_combo.setCurrentIndex(idx)
        grid2.addWidget(self.accel_combo, row, 1)
        self.accel_status_label = QLabel("")
        self.accel_status_label.setStyleSheet("color: #6a9a6a; font-size: 11px;")
        grid2.addWidget(self.accel_status_label, row + 1, 0, 1, 2)
        row += 1
        grid2.addWidget(QLabel("机器类型:"), row, 0)
        self.machine_combo = QComboBox()
        self.machine_combo.setMinimumHeight(32)
        self.machine_combo.addItems(MACHINE_TYPES)
        grid2.addWidget(self.machine_combo, row, 1)
        row += 1
        self.acpi_check = QCheckBox("启用 ACPI (电源管理)")
        self.acpi_check.setChecked(True)
        grid2.addWidget(self.acpi_check, row, 0, 1, 2)
        row += 1
        self.mem_backing_check = QCheckBox("💾 内存磁盘 (使用本地文件作为内存)")
        self.mem_backing_check.toggled.connect(self.on_mem_backing_toggle)
        grid2.addWidget(self.mem_backing_check, row, 0, 1, 2)
        row += 1
        grid2.addWidget(QLabel("内存文件:"), row, 0)
        mem_row = QHBoxLayout()
        self.mem_backing_file_edit = QLineEdit()
        self.mem_backing_file_edit.setEnabled(False)
        mem_row.addWidget(self.mem_backing_file_edit)
        self.mem_backing_browse_btn = QPushButton("浏览")
        self.mem_backing_browse_btn.setEnabled(False)
        self.mem_backing_browse_btn.clicked.connect(self.browse_mem_backing_file)
        mem_row.addWidget(self.mem_backing_browse_btn)
        grid2.addLayout(mem_row, row, 1)
        row += 1
        grid2.addWidget(QLabel("大小 (MB):"), row, 0)
        self.mem_backing_size_spin = QSpinBox()
        self.mem_backing_size_spin.setRange(128, 65536)
        self.mem_backing_size_spin.setSingleStep(512)
        self.mem_backing_size_spin.setEnabled(False)
        grid2.addWidget(self.mem_backing_size_spin, row, 1)
        row += 1
        self.mem_backing_support_label = QLabel("")
        self.mem_backing_support_label.setStyleSheet("color: #888; font-size: 11px;")
        grid2.addWidget(self.mem_backing_support_label, row, 0, 1, 2)
        layout.addWidget(hw_group)
        layout.addStretch()
        return widget

    def on_mem_backing_toggle(self, checked):
        self.mem_backing_file_edit.setEnabled(checked)
        self.mem_backing_size_spin.setEnabled(checked)
        self.mem_backing_browse_btn.setEnabled(checked)
        if checked:
            vm_name = self.name_edit.text().strip() or "vm"
            default_path = str(VMS_DIR / vm_name / f"{vm_name}.mem")
            if not self.mem_backing_file_edit.text():
                self.mem_backing_file_edit.setText(default_path)
            self.check_qemu_mem_backing_support()
        else:
            self.mem_backing_support_label.setText("")

    def check_qemu_mem_backing_support(self):
        qemu_ver = self.qemu_version_combo.currentText()
        if qemu_ver in self.hardware_detector.qemu_versions:
            info = self.hardware_detector.qemu_versions[qemu_ver]["info"]
            if info.get("has_mem_backing", False):
                self.mem_backing_support_label.setText("✅ QEMU 支持内存后备文件")
                self.mem_backing_support_label.setStyleSheet("color: #6a9a6a; font-size: 11px;")
            else:
                self.mem_backing_support_label.setText("⚠️ 当前 QEMU 可能不支持内存后备")
                self.mem_backing_support_label.setStyleSheet("color: #FF8A9C; font-size: 11px;")

    def browse_mem_backing_file(self):
        vm_name = self.name_edit.text().strip() or "vm"
        default_path = str(VMS_DIR / vm_name / f"{vm_name}.mem")
        file_path, _ = QFileDialog.getSaveFileName(self, "选择内存文件", default_path,
                                                    "内存文件 (*.mem *.img);;所有文件 (*)")
        if file_path:
            self.mem_backing_file_edit.setText(file_path)

    def create_display_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        display_group = QGroupBox("🖥️ 显示")
        display_group.setFont(QFont("Microsoft YaHei", 12))
        grid = QGridLayout(display_group)
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(12)
        row = 0
        grid.addWidget(QLabel("显卡:"), row, 0)
        self.vga_combo = QComboBox()
        self.vga_combo.setMinimumHeight(32)
        self.vga_combo.addItems(VGA_TYPES)
        grid.addWidget(self.vga_combo, row, 1)
        row += 1
        grid.addWidget(QLabel("显示后端:"), row, 0)
        self.display_combo = QComboBox()
        self.display_combo.setMinimumHeight(32)
        self.display_combo.addItems(DISPLAY_TYPES)
        grid.addWidget(self.display_combo, row, 1)
        row += 1
        grid.addWidget(QLabel("分辨率:"), row, 0)
        self.resolution_combo = QComboBox()
        self.resolution_combo.setMinimumHeight(32)
        self.resolution_combo.addItems(RESOLUTIONS)
        grid.addWidget(self.resolution_combo, row, 1)
        row += 1
        grid.addWidget(QLabel("VNC 端口:"), row, 0)
        self.vnc_edit = QLineEdit()
        self.vnc_edit.setMinimumHeight(32)
        self.vnc_edit.setPlaceholderText("留空使用 GTK，输入 :0 使用 VNC")
        grid.addWidget(self.vnc_edit, row, 1)
        row += 1
        self.opengl_check = QCheckBox("启用 OpenGL 加速")
        grid.addWidget(self.opengl_check, row, 0, 1, 2)
        layout.addWidget(display_group)

        sound_group = QGroupBox("🔊 声音/其他")
        sound_group.setFont(QFont("Microsoft YaHei", 12))
        grid2 = QGridLayout(sound_group)
        grid2.setVerticalSpacing(8)
        grid2.setHorizontalSpacing(12)
        row = 0
        grid2.addWidget(QLabel("声卡:"), row, 0)
        self.sound_combo = QComboBox()
        self.sound_combo.setMinimumHeight(32)
        self.sound_combo.addItems(SOUND_TYPES)
        grid2.addWidget(self.sound_combo, row, 1)
        row += 1
        grid2.addWidget(QLabel("网卡:"), row, 0)
        self.nic_combo = QComboBox()
        self.nic_combo.setMinimumHeight(32)
        self.nic_combo.addItems(NIC_TYPES)
        grid2.addWidget(self.nic_combo, row, 1)
        row += 1
        grid2.addWidget(QLabel("启动顺序:"), row, 0)
        self.boot_combo = QComboBox()
        self.boot_combo.setMinimumHeight(32)
        self.boot_combo.addItems(BOOT_TYPES)
        grid2.addWidget(self.boot_combo, row, 1)
        row += 1
        self.usb_check = QCheckBox("启用 USB")
        self.usb_check.setChecked(True)
        grid2.addWidget(self.usb_check, row, 0, 1, 2)
        layout.addWidget(sound_group)

        share_group = QGroupBox("📁 共享文件夹")
        share_layout = QGridLayout(share_group)
        share_layout.setVerticalSpacing(8)
        share_layout.setHorizontalSpacing(12)
        row = 0
        self.share_enable_check = QCheckBox("启用共享文件夹")
        self.share_enable_check.toggled.connect(self.on_share_toggle)
        share_layout.addWidget(self.share_enable_check, row, 0, 1, 2)
        row += 1
        share_layout.addWidget(QLabel("共享目录:"), row, 0)
        self.share_dir_label = QLabel("未选择")
        self.share_dir_label.setStyleSheet("border: 2px solid #555; padding: 4px; border-radius: 6px; color: #aaa;")
        self.share_dir_label.mousePressEvent = self.browse_share_dir_click
        share_layout.addWidget(self.share_dir_label, row, 1)
        self.share_dir_btn = QPushButton("浏览")
        self.share_dir_btn.clicked.connect(self.browse_share_dir)
        share_layout.addWidget(self.share_dir_btn, row, 2)
        info_label = QLabel("💡 虚拟机内访问: \\\\10.0.2.4\\qemu")
        info_label.setStyleSheet("color: #888; font-size: 10px;")
        share_layout.addWidget(info_label, row + 1, 0, 1, 3)
        layout.addWidget(share_group)

        iso_group = QGroupBox("💿 镜像文件")
        iso_group.setFont(QFont("Microsoft YaHei", 12))
        iso_layout = QGridLayout(iso_group)
        iso_layout.setVerticalSpacing(8)
        iso_layout.setHorizontalSpacing(12)
        row = 0
        iso_layout.addWidget(QLabel("启动镜像:"), row, 0)
        self.boot_iso_label = QLabel("未选择")
        self.boot_iso_label.setStyleSheet("border: 2px solid #555; padding: 4px; border-radius: 6px; color: #aaa;")
        iso_layout.addWidget(self.boot_iso_label, row, 1)
        self.boot_iso_btn = QPushButton("浏览")
        self.boot_iso_btn.clicked.connect(lambda: self.browse_iso("boot"))
        iso_layout.addWidget(self.boot_iso_btn, row, 2)
        self.boot_clear_btn = QPushButton("清空")
        self.boot_clear_btn.clicked.connect(lambda: self.clear_iso("boot"))
        iso_layout.addWidget(self.boot_clear_btn, row, 3)
        row += 1
        iso_layout.addWidget(QLabel("驱动镜像:"), row, 0)
        self.driver_iso_label = QLabel("未选择")
        self.driver_iso_label.setStyleSheet("border: 2px solid #555; padding: 4px; border-radius: 6px; color: #aaa;")
        iso_layout.addWidget(self.driver_iso_label, row, 1)
        self.driver_iso_btn = QPushButton("浏览")
        self.driver_iso_btn.clicked.connect(lambda: self.browse_iso("driver"))
        iso_layout.addWidget(self.driver_iso_btn, row, 2)
        self.driver_clear_btn = QPushButton("清空")
        self.driver_clear_btn.clicked.connect(lambda: self.clear_iso("driver"))
        iso_layout.addWidget(self.driver_clear_btn, row, 3)
        row += 1
        iso_layout.addWidget(QLabel("额外参数:"), row, 0)
        self.extra_edit = QLineEdit()
        self.extra_edit.setMinimumHeight(32)
        self.extra_edit.setPlaceholderText("额外的 QEMU 参数")
        iso_layout.addWidget(self.extra_edit, row, 1, 1, 3)
        layout.addWidget(iso_group)
        layout.addStretch()
        return widget

    def create_network_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        mode_group = QGroupBox("🌐 网络模式")
        mode_group.setFont(QFont("Microsoft YaHei", 12))
        mode_layout = QGridLayout(mode_group)
        mode_layout.setVerticalSpacing(8)
        mode_layout.setHorizontalSpacing(12)
        row = 0
        mode_layout.addWidget(QLabel("网络模式:"), row, 0)
        self.network_mode_combo = QComboBox()
        self.network_mode_combo.setMinimumHeight(32)
        for mode_key in ["user", "bridge", "tap", "socket", "vde", "none"]:
            mode_info = NETWORK_MODES.get(mode_key, {})
            self.network_mode_combo.addItem(mode_info.get("label", mode_key), mode_key)
        self.network_mode_combo.currentIndexChanged.connect(self.on_network_mode_changed)
        mode_layout.addWidget(self.network_mode_combo, row, 1, 1, 2)
        row += 1
        self.network_mode_desc = QLabel("")
        self.network_mode_desc.setStyleSheet("color: #888; font-size: 11px; padding: 4px 8px; background: #1a1a1a; border-radius: 6px;")
        self.network_mode_desc.setWordWrap(True)
        mode_layout.addWidget(self.network_mode_desc, row, 0, 1, 3)
        row += 1
        self.network_mode_warning = QLabel("")
        self.network_mode_warning.setStyleSheet("color: #FF8A9C; font-size: 11px; padding: 4px 8px; background: #2a1a1a; border-radius: 6px;")
        self.network_mode_warning.setWordWrap(True)
        self.network_mode_warning.setVisible(False)
        mode_layout.addWidget(self.network_mode_warning, row, 0, 1, 3)
        layout.addWidget(mode_group)

        param_group = QGroupBox("⚙️ 网络参数")
        param_group.setFont(QFont("Microsoft YaHei", 12))
        param_layout = QGridLayout(param_group)
        param_layout.setVerticalSpacing(8)
        param_layout.setHorizontalSpacing(12)
        row = 0
        param_layout.addWidget(QLabel("网卡型号:"), row, 0)
        self.net_nic_combo = QComboBox()
        self.net_nic_combo.setMinimumHeight(32)
        self.net_nic_combo.addItems(["virtio", "e1000", "rtl8139", "pcnet", "e1000e", "vmxnet3", "usb-net", "ne2k_pci"])
        self.net_nic_combo.setEditable(True)
        param_layout.addWidget(self.net_nic_combo, row, 1, 1, 3)
        row += 1
        param_layout.addWidget(QLabel("MAC 地址:"), row, 0)
        self.net_mac_edit = QLineEdit()
        self.net_mac_edit.setMinimumHeight(32)
        self.net_mac_edit.setPlaceholderText("自动生成，或输入 52:54:00:xx:xx:xx")
        param_layout.addWidget(self.net_mac_edit, row, 1, 1, 3)
        row += 1
        self.hostfwd_label = QLabel("端口转发:")
        param_layout.addWidget(self.hostfwd_label, row, 0)
        self.net_hostfwd_edit = QLineEdit()
        self.net_hostfwd_edit.setMinimumHeight(32)
        self.net_hostfwd_edit.setPlaceholderText("tcp::2222-:22, tcp::3389-:3389")
        param_layout.addWidget(self.net_hostfwd_edit, row, 1, 1, 3)
        row += 1
        self.bridge_label = QLabel("桥接接口:")
        self.bridge_label.setVisible(False)
        param_layout.addWidget(self.bridge_label, row, 0)
        self.bridge_edit = QLineEdit()
        self.bridge_edit.setMinimumHeight(32)
        self.bridge_edit.setPlaceholderText("br0 (Linux) 或 以太网适配器名 (Windows)")
        self.bridge_edit.setVisible(False)
        param_layout.addWidget(self.bridge_edit, row, 1, 1, 3)
        row += 1
        self.tap_label = QLabel("TAP 接口:")
        self.tap_label.setVisible(False)
        param_layout.addWidget(self.tap_label, row, 0)
        self.tap_edit = QLineEdit()
        self.tap_edit.setMinimumHeight(32)
        self.tap_edit.setPlaceholderText("tap0 (Linux) 或 网卡名 (Windows)")
        self.tap_edit.setVisible(False)
        param_layout.addWidget(self.tap_edit, row, 1, 1, 3)
        row += 1
        self.socket_label = QLabel("Socket 路径:")
        self.socket_label.setVisible(False)
        param_layout.addWidget(self.socket_label, row, 0)
        self.socket_edit = QLineEdit()
        self.socket_edit.setMinimumHeight(32)
        self.socket_edit.setPlaceholderText("/tmp/qemu-socket")
        self.socket_edit.setVisible(False)
        param_layout.addWidget(self.socket_edit, row, 1, 1, 3)
        row += 1
        self.vde_label = QLabel("VDE Socket:")
        self.vde_label.setVisible(False)
        param_layout.addWidget(self.vde_label, row, 0)
        self.vde_edit = QLineEdit()
        self.vde_edit.setMinimumHeight(32)
        self.vde_edit.setPlaceholderText("/tmp/vde.ctl")
        self.vde_edit.setVisible(False)
        param_layout.addWidget(self.vde_edit, row, 1, 1, 3)
        layout.addWidget(param_group)

        extra_group = QGroupBox("🔒 额外网络选项")
        extra_group.setFont(QFont("Microsoft YaHei", 12))
        extra_layout = QGridLayout(extra_group)
        extra_layout.setVerticalSpacing(8)
        extra_layout.setHorizontalSpacing(12)
        row = 0
        extra_layout.addWidget(QLabel("自定义子网:"), row, 0)
        self.net_subnet_edit = QLineEdit()
        self.net_subnet_edit.setMinimumHeight(32)
        self.net_subnet_edit.setPlaceholderText("192.168.1.0/24")
        extra_layout.addWidget(self.net_subnet_edit, row, 1, 1, 2)
        row += 1
        extra_layout.addWidget(QLabel("自定义 DNS:"), row, 0)
        self.net_dns_edit = QLineEdit()
        self.net_dns_edit.setMinimumHeight(32)
        self.net_dns_edit.setPlaceholderText("8.8.8.8")
        extra_layout.addWidget(self.net_dns_edit, row, 1, 1, 2)
        row += 1
        self.net_restrict_check = QCheckBox("限制网络访问")
        extra_layout.addWidget(self.net_restrict_check, row, 0, 1, 3)
        layout.addWidget(extra_group)
        layout.addStretch()
        return widget

    def on_network_mode_changed(self, index):
        mode_key = self.network_mode_combo.currentData()
        mode_info = NETWORK_MODES.get(mode_key, {})
        self.network_mode_desc.setText(mode_info.get("description", ""))
        warnings = []
        if mode_info.get("needs_admin", False):
            warnings.append("⚠️ 此模式需要管理员/root权限")
        if mode_info.get("needs_tap", False):
            warnings.append("⚠️ 此模式需要创建 TAP 设备")
        if warnings:
            self.network_mode_warning.setText("\n".join(warnings))
            self.network_mode_warning.setVisible(True)
        else:
            self.network_mode_warning.setVisible(False)
        is_bridge = mode_key == "bridge"
        is_tap = mode_key == "tap"
        is_socket = mode_key == "socket"
        is_vde = mode_key == "vde"
        is_user = mode_key == "user"
        self.hostfwd_label.setVisible(is_user)
        self.net_hostfwd_edit.setVisible(is_user)
        self.bridge_label.setVisible(is_bridge)
        self.bridge_edit.setVisible(is_bridge)
        show_tap = is_bridge or is_tap
        self.tap_label.setVisible(show_tap)
        self.tap_edit.setVisible(show_tap)
        self.socket_label.setVisible(is_socket)
        self.socket_edit.setVisible(is_socket)
        self.vde_label.setVisible(is_vde)
        self.vde_edit.setVisible(is_vde)

    def create_passthrough_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)
        info = QLabel(
            "💡 硬件直通让虚拟机直接访问物理设备\n"
            "• USB 直通：让虚拟机使用 U 盘、USB 网卡、USB 声卡等\n"
            "• PCI 直通：让虚拟机使用物理显卡、网卡（需要 IOMMU/VT-d）\n"
            "• 直通的设备主机将无法使用"
        )
        info.setStyleSheet("color: #FFB74D; font-size: 11px; padding: 10px; background: #2a1a00; border-radius: 6px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        usb_group = QGroupBox("🔌 USB 直通")
        usb_layout = QVBoxLayout(usb_group)
        usb_row1 = QHBoxLayout()
        usb_row1.addWidget(QLabel("主机 USB 设备:"))
        usb_row1.addStretch()
        refresh_usb_btn = QPushButton("🔄 刷新")
        refresh_usb_btn.clicked.connect(self._refresh_usb_list)
        usb_row1.addWidget(refresh_usb_btn)
        add_usb_btn = QPushButton("➕ 添加")
        add_usb_btn.setStyleSheet("background-color: #4a7a4a; color: white;")
        add_usb_btn.clicked.connect(self._add_usb_passthrough)
        usb_row1.addWidget(add_usb_btn)
        usb_layout.addLayout(usb_row1)
        self._usb_host_list = QListWidget()
        self._usb_host_list.setMaximumHeight(120)
        usb_layout.addWidget(self._usb_host_list)
        usb_row2 = QHBoxLayout()
        usb_row2.addWidget(QLabel("已直通的 USB 设备:"))
        usb_row2.addStretch()
        remove_usb_btn = QPushButton("➖ 移除选中")
        remove_usb_btn.setStyleSheet("background-color: #8a4a4a; color: white;")
        remove_usb_btn.clicked.connect(self._remove_usb_passthrough)
        usb_row2.addWidget(remove_usb_btn)
        usb_layout.addLayout(usb_row2)
        self._usb_vm_list = QListWidget()
        self._usb_vm_list.setMaximumHeight(120)
        usb_layout.addWidget(self._usb_vm_list)
        layout.addWidget(usb_group)

        pci_group = QGroupBox("🖥️ PCI 直通")
        pci_layout = QVBoxLayout(pci_group)
        pci_row1 = QHBoxLayout()
        pci_row1.addWidget(QLabel("主机 PCI 设备:"))
        pci_row1.addStretch()
        refresh_pci_btn = QPushButton("🔄 刷新")
        refresh_pci_btn.clicked.connect(self._refresh_pci_list)
        pci_row1.addWidget(refresh_pci_btn)
        add_pci_btn = QPushButton("➕ 添加")
        add_pci_btn.setStyleSheet("background-color: #4a7a4a; color: white;")
        add_pci_btn.clicked.connect(self._add_pci_passthrough)
        pci_row1.addWidget(add_pci_btn)
        pci_layout.addLayout(pci_row1)
        self._pci_host_list = QListWidget()
        self._pci_host_list.setMaximumHeight(120)
        pci_layout.addWidget(self._pci_host_list)
        pci_row2 = QHBoxLayout()
        pci_row2.addWidget(QLabel("已直通的 PCI 设备:"))
        pci_row2.addStretch()
        remove_pci_btn = QPushButton("➖ 移除选中")
        remove_pci_btn.setStyleSheet("background-color: #8a4a4a; color: white;")
        remove_pci_btn.clicked.connect(self._remove_pci_passthrough)
        pci_row2.addWidget(remove_pci_btn)
        pci_layout.addLayout(pci_row2)
        self._pci_vm_list = QListWidget()
        self._pci_vm_list.setMaximumHeight(120)
        pci_layout.addWidget(self._pci_vm_list)
        layout.addWidget(pci_group)
        layout.addStretch()
        QTimer.singleShot(500, self._refresh_usb_list)
        QTimer.singleShot(600, self._refresh_pci_list)
        return widget

    def _refresh_usb_list(self):
        def _bg():
            devices = PassthroughDetector.get_usb_devices()
            self._pending_usb_devices = devices
            QMetaObject.invokeMethod(self, "_apply_usb_list", Qt.QueuedConnection)
        Thread(target=_bg, daemon=True).start()

    @Slot()
    def _apply_usb_list(self):
        self._usb_host_list.clear()
        for dev in getattr(self, '_pending_usb_devices', []):
            text = f"🔌 {dev['name']}"
            if dev.get('vendor_id'):
                text += f"  [{dev['vendor_id']}:{dev.get('product_id', '')}]"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, dev)
            self._usb_host_list.addItem(item)
        if self._usb_host_list.count() == 0:
            self._usb_host_list.addItem("(未检测到USB设备)")

    def _refresh_pci_list(self):
        def _bg():
            devices = PassthroughDetector.get_pci_devices()
            self._pending_pci_devices = devices
            QMetaObject.invokeMethod(self, "_apply_pci_list", Qt.QueuedConnection)
        Thread(target=_bg, daemon=True).start()

    @Slot()
    def _apply_pci_list(self):
        self._pci_host_list.clear()
        for dev in getattr(self, '_pending_pci_devices', []):
            text = f"🖥️ {dev['name']}"
            if dev.get('address'):
                text = f"[{dev['address']}] " + text
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, dev)
            self._pci_host_list.addItem(item)
        if self._pci_host_list.count() == 0:
            self._pci_host_list.addItem("(未检测到PCI设备)")

    def _add_usb_passthrough(self):
        items = self._usb_host_list.selectedItems()
        if not items:
            return
        dev = items[0].data(Qt.UserRole)
        if not dev:
            return
        if not hasattr(self.vm, 'usb_passthrough'):
            self.vm.usb_passthrough = []
        if any(d.get('id') == dev.get('id') for d in self.vm.usb_passthrough):
            QMessageBox.information(self, "提示", "该设备已添加")
            return
        self.vm.usb_passthrough.append(dev)
        self._refresh_vm_usb_list()

    def _remove_usb_passthrough(self):
        items = self._usb_vm_list.selectedItems()
        if not items:
            return
        dev = items[0].data(Qt.UserRole)
        self.vm.usb_passthrough = [d for d in self.vm.usb_passthrough if d.get('id') != dev.get('id')]
        self._refresh_vm_usb_list()

    def _refresh_vm_usb_list(self):
        self._usb_vm_list.clear()
        for dev in getattr(self.vm, 'usb_passthrough', []):
            text = f"🔌 {dev.get('name', '未知')}"
            if dev.get('vendor_id'):
                text += f"  [{dev['vendor_id']}:{dev.get('product_id', '')}]"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, dev)
            self._usb_vm_list.addItem(item)

    def _add_pci_passthrough(self):
        items = self._pci_host_list.selectedItems()
        if not items:
            return
        dev = items[0].data(Qt.UserRole)
        if not dev:
            return
        if not hasattr(self.vm, 'pci_passthrough'):
            self.vm.pci_passthrough = []
        if any(d.get('id') == dev.get('id') for d in self.vm.pci_passthrough):
            QMessageBox.information(self, "提示", "该设备已添加")
            return
        self.vm.pci_passthrough.append(dev)
        self._refresh_vm_pci_list()

    def _remove_pci_passthrough(self):
        items = self._pci_vm_list.selectedItems()
        if not items:
            return
        dev = items[0].data(Qt.UserRole)
        self.vm.pci_passthrough = [d for d in self.vm.pci_passthrough if d.get('id') != dev.get('id')]
        self._refresh_vm_pci_list()

    def _refresh_vm_pci_list(self):
        self._pci_vm_list.clear()
        for dev in getattr(self.vm, 'pci_passthrough', []):
            text = f"🖥️ {dev.get('name', '未知')}"
            if dev.get('address'):
                text = f"[{dev['address']}] " + text
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, dev)
            self._pci_vm_list.addItem(item)

    def browse_custom_qemu(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 QEMU 可执行文件", str(BASE_DIR),
            "QEMU 可执行文件 (qemu-system-*);;所有文件 (*)"
        )
        if not file_path:
            return
        exe_name = Path(file_path).name
        if not exe_name.startswith("qemu-system-"):
            reply = QMessageBox.question(
                self, "确认",
                f"选择的文件 '{exe_name}' 可能不是 QEMU 可执行文件。\n\n是否继续添加？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        if self.hardware_detector.add_custom_qemu(file_path):
            self.qemu_version_combo.clear()
            versions = list(self.hardware_detector.qemu_versions.keys())
            if versions:
                self.qemu_version_combo.addItems(versions)
            custom_name = f"自定义_{Path(file_path).parent.name}"
            idx = self.qemu_version_combo.findText(custom_name)
            if idx >= 0:
                self.qemu_version_combo.setCurrentIndex(idx)
            self.vm.custom_qemu_path = file_path
            QMessageBox.information(self, "成功", f"✅ 已添加自定义 QEMU:\n{file_path}")
        else:
            QMessageBox.warning(self, "错误", "无法添加此 QEMU，请确保文件存在且可执行")

    def on_qemu_version_changed(self):
        qemu_ver = self.qemu_version_combo.currentText()
        if qemu_ver and qemu_ver in self.hardware_detector.qemu_versions:
            info = self.hardware_detector.qemu_versions[qemu_ver]["info"]
            hw_text = f"📦 {info.get('version', '未知')} | "
            hw_text += f"🏷️ {info.get('year', 2020)}年 | "
            hw_text += f"💻 CPU: {len(info.get('cpu_models', []))}种 | "
            hw_text += f"🖥️ VGA: {len(info.get('vga_types', []))}种 | "
            hw_text += f"⚡ 加速: {len(info.get('accel_types', []))}种"
            self.hw_info_label.setText(hw_text)
            self.hw_info_label.setStyleSheet("color: #6a9a6a; font-size: 11px; padding: 4px;")
            self.update_hardware_lists(info)
            if self.mem_backing_check.isChecked():
                self.check_qemu_mem_backing_support()

    def update_hardware_lists(self, info):
        if info.get('cpu_models'):
            current = self.cpu_model_combo.currentText()
            for model in info['cpu_models']:
                if self.cpu_model_combo.findText(model) == -1:
                    self.cpu_model_combo.addItem(model)
            if current and self.cpu_model_combo.findText(current) != -1:
                self.cpu_model_combo.setCurrentText(current)
        if info.get('vga_types'):
            current = self.vga_combo.currentText()
            for item in info['vga_types']:
                if self.vga_combo.findText(item) == -1:
                    self.vga_combo.addItem(item)
            if current and self.vga_combo.findText(current) != -1:
                self.vga_combo.setCurrentText(current)
        if info.get('display_types'):
            current = self.display_combo.currentText()
            for item in info['display_types']:
                if self.display_combo.findText(item) == -1:
                    self.display_combo.addItem(item)
            if current and self.display_combo.findText(current) != -1:
                self.display_combo.setCurrentText(current)
        if info.get('machine_types'):
            current = self.machine_combo.currentText()
            for item in info['machine_types']:
                if self.machine_combo.findText(item) == -1:
                    self.machine_combo.addItem(item)
            if current and self.machine_combo.findText(current) != -1:
                self.machine_combo.setCurrentText(current)
        if info.get('accel_types'):
            current = self.accel_combo.currentText()
            for item in info['accel_types']:
                if self.accel_combo.findText(item) == -1:
                    self.accel_combo.addItem(item)
            if current and self.accel_combo.findText(current) != -1:
                self.accel_combo.setCurrentText(current)
            else:
                if hasattr(self.parent, 'hardware_detector'):
                    default = self.parent.hardware_detector.default_accel
                    if default and self.accel_combo.findText(default) != -1:
                        self.accel_combo.setCurrentText(default)
                        self.accel_status_label.setText(f"✅ 系统支持: {default}")
                        self.accel_status_label.setStyleSheet("color: #6a9a6a; font-size: 11px;")
                    else:
                        self.accel_status_label.setText("⚠️ 当前加速器可能不受系统支持")
                        self.accel_status_label.setStyleSheet("color: #FF8A9C; font-size: 11px;")
        if info.get('netdev_types'):
            current = self.nic_combo.currentText()
            for item in info['netdev_types']:
                if self.nic_combo.findText(item) == -1:
                    self.nic_combo.addItem(item)
            if current and self.nic_combo.findText(current) != -1:
                self.nic_combo.setCurrentText(current)
        if info.get('audio_devices'):
            current = self.sound_combo.currentText()
            for item in info['audio_devices']:
                if self.sound_combo.findText(item) == -1:
                    self.sound_combo.addItem(item)
            if current and self.sound_combo.findText(current) != -1:
                self.sound_combo.setCurrentText(current)

    def load_hardware_profiles(self):
        manager = HardwareProfileManager()
        self.cpu_profile_combo.clear()
        for name in manager.get_all_names():
            self.cpu_profile_combo.addItem(name)
        if hasattr(self.vm, 'cpu_profile') and self.vm.cpu_profile:
            idx = self.cpu_profile_combo.findText(self.vm.cpu_profile)
            if idx >= 0:
                self.cpu_profile_combo.setCurrentIndex(idx)

    def open_hardware_profile_manager(self):
        dialog = HardwareProfileManagerDialog(self)
        dialog.exec()
        self.load_hardware_profiles()

    def on_preset_changed(self, preset_name):
        preset = SYSTEM_PRESETS.get(preset_name)
        if not preset:
            return
        if not self.existing_vm:
            self.name_edit.setText("")
        self.os_combo.setCurrentText(preset["os_type"])
        self.version_combo.setCurrentText(preset["os_version"])
        self.arch_combo.setCurrentText(preset["arch"])
        self.memory_spin.setValue(preset["memory"])
        self.cpu_spin.setValue(preset["cpu"])
        self.disk_spin.setValue(preset["disk_size"])
        self.disk_format_combo.setCurrentText(preset["disk_format"])
        self.disk_interface_combo.setCurrentText(preset.get("disk_interface", "sata"))
        self.cpu_model_combo.setCurrentText(preset.get("cpu_model", "host"))
        self.accel_combo.setCurrentText(preset.get("accel", "tcg"))
        self.vga_combo.setCurrentText(preset.get("vga", "std"))
        self.display_combo.setCurrentText(preset.get("display", "gtk"))
        self.resolution_combo.setCurrentText(preset.get("resolution", "自定义"))
        self.machine_combo.setCurrentText(preset.get("machine_type", "pc"))
        self.acpi_check.setChecked(preset.get("acpi", True))
        self.usb_check.setChecked(preset.get("usb", True))
        self.sound_combo.setCurrentText(preset.get("sound", "none"))
        self.boot_combo.setCurrentText(preset.get("boot_order", "cdrom"))
        self.opengl_check.setChecked(preset.get("opengl", False))
        self.nic_combo.setCurrentText(preset.get("nic_model", "e1000"))
        self.smp_threads_spin.setValue(1)
        self.smp_sockets_spin.setValue(1)
        self.vnc_edit.setText("")
        qemu_ver = preset.get("qemu_version", "")
        if qemu_ver:
            idx = self.qemu_version_combo.findText(qemu_ver)
            if idx >= 0:
                self.qemu_version_combo.setCurrentIndex(idx)
        self.preset_desc.setText(f"💡 {preset.get('description', '')}")

    def show_preset_help(self):
        QMessageBox.information(self, "预设说明",
            "📋 系统预设 = 一键配置最佳参数\n\n"
            "• Windows XP → QEMU 2016 + IDE + SB16\n"
            "• Windows 7 → QEMU 2019 + SATA + AC97\n"
            "• Windows 10/11 → QEMU 2025 + VirtIO + HDA\n"
            "• Android → QEMU 2019 + IDE + 关闭声卡\n\n"
            "选好预设后可以手动微调每个参数！")

    def on_share_toggle(self, checked):
        self.share_dir_label.setEnabled(checked)
        self.share_dir_btn.setEnabled(checked)

    def browse_share_dir_click(self, event):
        if self.share_enable_check.isChecked():
            self.browse_share_dir()

    def browse_share_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择共享目录", str(BASE_DIR))
        if folder:
            self.share_dir_label.setText(folder)
            self._temp_share_dir = folder

    def browse_iso(self, iso_type):
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"选择{iso_type}镜像", str(ISO_DIR),
            "镜像文件 (*.iso *.img);;所有文件 (*)"
        )
        if file_path:
            if iso_type == "boot":
                self.boot_iso_label.setText(Path(file_path).name)
                self.boot_iso_label.setStyleSheet("border: 2px solid #4CAF50; padding: 4px; border-radius: 6px; background: #e8f5e9;")
                self._temp_iso_path = file_path
            elif iso_type == "driver":
                self.driver_iso_label.setText(Path(file_path).name)
                self.driver_iso_label.setStyleSheet("border: 2px solid #4CAF50; padding: 4px; border-radius: 6px; background: #e8f5e9;")
                self._temp_driver_path = file_path

    def clear_iso(self, iso_type):
        if iso_type == "boot":
            self.boot_iso_label.setText("未选择")
            self.boot_iso_label.setStyleSheet("border: 2px solid #555; padding: 4px; border-radius: 6px; color: #aaa;")
            self._temp_iso_path = ""
        elif iso_type == "driver":
            self.driver_iso_label.setText("未选择")
            self.driver_iso_label.setStyleSheet("border: 2px solid #555; padding: 4px; border-radius: 6px; color: #aaa;")
            self._temp_driver_path = ""

    def show_history(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入虚拟机名称")
            return
        history = self.history.get_history(name)
        if not history:
            QMessageBox.information(self, "信息", f"没有找到 '{name}' 的历史配置")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"📜 历史配置 - {name}")
        dialog.setMinimumSize(600, 400)
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        for i, entry in enumerate(history):
            timestamp = entry.get("timestamp", "未知时间")
            list_widget.addItem(f"[{i+1}] {timestamp}")
        layout.addWidget(list_widget)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        restore_btn = QPushButton("↩️ 恢复此配置")
        restore_btn.clicked.connect(lambda: self.restore_history(dialog, list_widget.currentRow(), name))
        btn_layout.addWidget(restore_btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        dialog.exec()

    def restore_history(self, dialog, index, name):
        if index < 0:
            QMessageBox.warning(dialog, "提示", "请选择一个历史配置")
            return
        config = self.history.restore_entry(name, index)
        if not config:
            QMessageBox.warning(dialog, "错误", "恢复失败")
            return
        reply = QMessageBox.question(dialog, "确认",
            f"恢复配置 '{name}' 的历史版本？\n\n当前配置将被覆盖。",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        vm = VMConfig.from_dict(config)
        self.vm = vm
        self.advanced_widget.set_vm_ref(vm)
        self.load_vm_data(vm)
        dialog.accept()
        QMessageBox.information(self, "成功", "已恢复历史配置")

    def load_vm_data(self, vm):
        self.name_edit.setText(vm.name)
        self.os_combo.setCurrentText(vm.os_type)
        self.version_combo.setCurrentText(vm.os_version)
        self.arch_combo.setCurrentText(vm.arch)
        self.memory_spin.setValue(vm.memory)
        self.cpu_spin.setValue(vm.cpu)
        self.smp_threads_spin.setValue(getattr(vm, 'smp_threads', 1))
        self.smp_sockets_spin.setValue(getattr(vm, 'smp_sockets', 1))
        self.disk_spin.setValue(vm.disk_size)
        self.disk_format_combo.setCurrentText(vm.disk_format)
        self.disk_interface_combo.setCurrentText(vm.disk_interface)
        self.cpu_model_combo.setCurrentText(vm.cpu_model)
        self.accel_combo.setCurrentText(vm.accel)
        self.vga_combo.setCurrentText(vm.vga)
        self.display_combo.setCurrentText(vm.display)
        self.resolution_combo.setCurrentText(vm.resolution)
        self.machine_combo.setCurrentText(vm.machine_type)
        self.acpi_check.setChecked(vm.acpi)
        self.usb_check.setChecked(vm.usb)
        self.sound_combo.setCurrentText(vm.sound)
        self.boot_combo.setCurrentText(vm.boot_order)
        self.opengl_check.setChecked(vm.opengl)
        self.nic_combo.setCurrentText(vm.nic_model)
        self.vnc_edit.setText(vm.vnc_port)
        self.share_enable_check.setChecked(vm.share_enabled)
        if vm.share_dir:
            self.share_dir_label.setText(vm.share_dir)
            self._temp_share_dir = vm.share_dir
        self.on_share_toggle(vm.share_enabled)
        if vm.qemu_version:
            idx = self.qemu_version_combo.findText(vm.qemu_version)
            if idx >= 0:
                self.qemu_version_combo.setCurrentIndex(idx)
        if vm.custom_qemu_path:
            self.hardware_detector.add_custom_qemu(vm.custom_qemu_path)
            self.qemu_version_combo.clear()
            versions = list(self.hardware_detector.qemu_versions.keys())
            if versions:
                self.qemu_version_combo.addItems(versions)
        if vm.boot_iso:
            self.boot_iso_label.setText(Path(vm.boot_iso).name)
            self.boot_iso_label.setStyleSheet("border: 2px solid #4CAF50; padding: 4px; border-radius: 6px; background: #e8f5e9;")
            self._temp_iso_path = vm.boot_iso
        if vm.driver_iso:
            self.driver_iso_label.setText(Path(vm.driver_iso).name)
            self.driver_iso_label.setStyleSheet("border: 2px solid #4CAF50; padding: 4px; border-radius: 6px; background: #e8f5e9;")
            self._temp_driver_path = vm.driver_iso
        self.extra_edit.setText(vm.extra_args)
        self.mem_backing_check.setChecked(vm.memory_backing_enabled)
        self.mem_backing_file_edit.setText(vm.memory_backing_file)
        self.mem_backing_size_spin.setValue(vm.memory_backing_size or vm.memory)
        self.on_mem_backing_toggle(vm.memory_backing_enabled)
        if vm.memory_backing_enabled:
            self.check_qemu_mem_backing_support()
        idx = self.network_mode_combo.findData(vm.network_mode)
        if idx >= 0:
            self.network_mode_combo.setCurrentIndex(idx)
        self.bridge_edit.setText(vm.bridge_interface)
        self.tap_edit.setText(vm.tap_interface)
        self.socket_edit.setText(getattr(vm, 'socket_path', ''))
        self.vde_edit.setText(getattr(vm, 'vde_socket', ''))
        self.net_nic_combo.setCurrentText(vm.nic_model)
        self.net_mac_edit.setText(vm.mac_address)
        self.net_hostfwd_edit.setText(vm.hostfwd)
        self.net_subnet_edit.setText(vm.net_subnet)
        self.net_dns_edit.setText(vm.net_dns)
        self.net_restrict_check.setChecked(vm.net_restrict)
        self.on_network_mode_changed(self.network_mode_combo.currentIndex())
        self.advanced_widget.set_config({
            "cache": vm.cache, "aio": vm.aio,
            "discard": vm.discard, "detect_zeroes": vm.detect_zeroes,
            "backing_file": vm.backing_file,
            "snapshot_mode": vm.snapshot_mode, "disk_readonly": vm.disk_readonly,
            "hostfwd": vm.hostfwd, "net_subnet": vm.net_subnet,
            "net_dns": vm.net_dns, "net_restrict": vm.net_restrict,
            "tap_interface": vm.tap_interface, "mac_address": vm.mac_address,
            "cpu_flags": vm.cpu_flags, "numa_config": vm.numa_config,
            "mem_prealloc": vm.mem_prealloc, "hugepages": vm.hugepages,
            "no_hpet_adv": vm.no_hpet_adv, "no_kvm_nested": vm.no_kvm_nested,
            "force_tcg": vm.force_tcg, "usb_tablet": vm.usb_tablet,
            "bios_file": vm.bios_file, "vnc_password": vm.vnc_password,
            "spice_port": vm.spice_port, "spice_password": vm.spice_password,
            "no_mouse_integration": vm.no_mouse_integration,
            "log_file": vm.log_file, "debug_level": vm.debug_level,
            "qmp_socket": vm.qmp_socket, "monitor_stdio": vm.monitor_stdio,
            "no_reboot": vm.no_reboot, "no_shutdown": vm.no_shutdown,
            "sandbox": vm.sandbox, "rtc_base": vm.rtc_base,
            "seed_value": vm.seed_value, "boot_menu": vm.boot_menu,
            "boot_once": vm.boot_once, "extra_advanced_args": vm.extra_advanced_args,
        })
        self.load_hardware_profiles()
        if vm.cpu_profile:
            idx = self.cpu_profile_combo.findText(vm.cpu_profile)
            if idx >= 0:
                self.cpu_profile_combo.setCurrentIndex(idx)
        self._refresh_vm_usb_list()
        self._refresh_vm_pci_list()

    def save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入虚拟机名称")
            return
        if not self.existing_vm and (VMS_DIR / name).exists():
            QMessageBox.warning(self, "提示", f"虚拟机 '{name}' 已存在")
            return
        vm = self.vm if self.existing_vm else VMConfig()
        vm.name = name
        vm.folder_name = get_active_folder().get("name", "")
        vm.os_type = self.os_combo.currentText()
        vm.os_version = self.version_combo.currentText()
        vm.arch = self.arch_combo.currentText()
        vm.memory = self.memory_spin.value()
        vm.cpu = self.cpu_spin.value()
        vm.smp_threads = self.smp_threads_spin.value()
        vm.smp_sockets = self.smp_sockets_spin.value()
        vm.disk_size = self.disk_spin.value()
        vm.disk_format = self.disk_format_combo.currentText()
        vm.disk_interface = self.disk_interface_combo.currentText()
        vm.cpu_model = self.cpu_model_combo.currentText()
        vm.cpu_profile = self.cpu_profile_combo.currentText()
        vm.accel = self.accel_combo.currentText()
        vm.vga = self.vga_combo.currentText()
        vm.display = self.display_combo.currentText()
        vm.resolution = self.resolution_combo.currentText()
        vm.machine_type = self.machine_combo.currentText()
        vm.acpi = self.acpi_check.isChecked()
        vm.usb = self.usb_check.isChecked()
        vm.sound = self.sound_combo.currentText()
        vm.boot_order = self.boot_combo.currentText()
        vm.opengl = self.opengl_check.isChecked()
        vm.nic_model = self.nic_combo.currentText()
        vm.qemu_version = self.qemu_version_combo.currentText()
        vm.preset = self.preset_combo.currentText()
        vm.vnc_port = self.vnc_edit.text().strip()
        vm.share_enabled = self.share_enable_check.isChecked()
        vm.share_dir = self._temp_share_dir if self._temp_share_dir else ""
        vm.boot_iso = self._temp_iso_path
        vm.driver_iso = self._temp_driver_path
        vm.extra_args = self.extra_edit.text().strip()
        vm.memory_backing_enabled = self.mem_backing_check.isChecked()
        vm.memory_backing_file = self.mem_backing_file_edit.text().strip()
        vm.memory_backing_size = self.mem_backing_size_spin.value()
        vm.network_mode = self.network_mode_combo.currentData()
        vm.bridge_interface = self.bridge_edit.text().strip()
        vm.tap_interface = self.tap_edit.text().strip()
        vm.socket_path = self.socket_edit.text().strip()
        vm.vde_socket = self.vde_edit.text().strip()
        vm.nic_model = self.net_nic_combo.currentText()
        vm.mac_address = self.net_mac_edit.text().strip()
        vm.hostfwd = self.net_hostfwd_edit.text().strip()
        vm.net_subnet = self.net_subnet_edit.text().strip()
        vm.net_dns = self.net_dns_edit.text().strip()
        vm.net_restrict = self.net_restrict_check.isChecked()
        adv = self.advanced_widget.get_config()
        for key, val in adv.items():
            if hasattr(vm, key):
                setattr(vm, key, val)
        if not self.existing_vm:
            vm.created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            vm_dir = VMS_DIR / name
            vm_dir.mkdir(parents=True, exist_ok=True)
            disk_path = vm_dir / f"disk.{vm.disk_format}"
            qemu_img = find_qemu_img()
            if qemu_img:
                try:
                    subprocess.run([str(qemu_img), "create", "-f", vm.disk_format,
                                    str(disk_path), f"{vm.disk_size}G"],
                                   capture_output=True, text=True, encoding='utf-8',
                                   errors='ignore', check=True)
                    vm.disk_path = str(disk_path)
                    vm.add_disk(str(disk_path), vm.disk_size, vm.disk_format, vm.disk_interface)
                except Exception as e:
                    print(f"创建磁盘失败: {e}")
        vm_dir = VMS_DIR / vm.name
        config_file = vm_dir / "config.json"
        config_data = vm.to_dict()
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        self.history.add_entry(vm.name, config_data)
        self.vm = vm
        self.accept()

    def get_vm(self):
        return self.vm


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.vm_list = []
        self.current_vm = None
        self.translator = Translator()
        self.translator.set_main_window(self)
        self.history = ConfigHistory()
        self.hardware_detector = QEMUHardwareDetector()
        self.init_ui()
        self.load_vms()
        self.refresh_vm_list()
        self.load_language_setting()
        self.status_bar.showMessage(f"就绪 | 当前工作区: {get_active_folder().get('name', '默认')}")

    def init_ui(self):
        font = QFont("Microsoft YaHei", 11)
        self.setFont(font)
        self.setWindowTitle(f"Mikan QEMU Manager v{APP_VERSION}")
        self.setMinimumSize(1100, 700)
        self.resize(1300, 800)
        self.setStyleSheet("""
            QMainWindow { background-color: #000000; color: #ffffff; }
            QMenuBar { background-color: #000000; color: #ffffff; border-bottom: 1px solid #333333; font-size: 12px; font-family: "Microsoft YaHei"; }
            QMenuBar::item:selected { background-color: #333333; }
            QMenu { background-color: #000000; color: #ffffff; border: 1px solid #333333; font-size: 12px; font-family: "Microsoft YaHei"; }
            QMenu::item:selected { background-color: #333333; }
            QToolBar { background-color: #000000; border: none; spacing: 4px; padding: 4px 8px; }
            QToolButton { background-color: transparent; color: #ffffff; border: none; padding: 6px 14px; border-radius: 4px; font-size: 13px; font-family: "Microsoft YaHei"; }
            QToolButton:hover { background-color: #333333; }
            QToolButton:disabled { color: #666666; }
            QListWidget { background-color: #000000; color: #ffffff; border: none; outline: none; font-size: 13px; font-family: "Microsoft YaHei"; }
            QListWidget::item { padding: 10px 14px; border-radius: 4px; }
            QListWidget::item:selected { background-color: #333333; }
            QListWidget::item:hover { background-color: #1a1a1a; }
            QTabWidget::pane { background-color: #000000; border: 1px solid #333333; border-radius: 4px; }
            QTabBar::tab { background-color: #000000; color: #aaaaaa; padding: 10px 20px; border: 1px solid #333333; border-bottom: none; margin-right: 2px; font-size: 13px; font-family: "Microsoft YaHei"; }
            QTabBar::tab:selected { color: #ffffff; }
            QGroupBox { color: #ffffff; border: 1px solid #333333; border-radius: 4px; margin-top: 12px; padding-top: 10px; font-size: 13px; font-family: "Microsoft YaHei"; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 8px; color: #aaaaaa; }
            QLabel { color: #ffffff; font-size: 12px; font-family: "Microsoft YaHei"; }
            QLineEdit, QSpinBox, QComboBox, QTextEdit { background-color: #000000; color: #ffffff; border: 1px solid #333333; border-radius: 4px; padding: 6px 10px; font-size: 12px; font-family: "Microsoft YaHei"; }
            QComboBox QAbstractItemView { background-color: #000000; color: #ffffff; selection-background-color: #333333; border: 1px solid #333333; }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #555555; }
            QPushButton { background-color: #333333; color: #ffffff; border: none; border-radius: 4px; padding: 8px 18px; font-weight: bold; font-size: 13px; font-family: "Microsoft YaHei"; }
            QPushButton:hover { background-color: #444444; }
            QPushButton:disabled { background-color: #1a1a1a; color: #666666; }
            QCheckBox { color: #ffffff; font-size: 12px; font-family: "Microsoft YaHei"; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #333333; background-color: #000000; }
            QCheckBox::indicator:checked { background-color: #4a7a4a; border-color: #4a7a4a; }
            QScrollBar:vertical { background-color: #000000; width: 14px; border-radius: 6px; }
            QScrollBar::handle:vertical { background-color: #333333; border-radius: 6px; min-height: 20px; }
            QStatusBar { background-color: #000000; color: #888888; border-top: 1px solid #333333; font-size: 12px; font-family: "Microsoft YaHei"; }
        """)
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件(&F)")
        new_action = QAction("📦 新建虚拟机", self)
        new_action.triggered.connect(self.create_vm)
        new_action.setShortcut("Ctrl+N")
        file_menu.addAction(new_action)
        file_menu.addSeparator()
        import_action = QAction("📥 导入", self)
        import_action.triggered.connect(self.import_vm)
        file_menu.addAction(import_action)
        export_action = QAction("📤 导出", self)
        export_action.triggered.connect(self.export_vm)
        file_menu.addAction(export_action)
        export_as_menu = QMenu("📤 导出为", self)
        for fmt, desc in [("mikan", "Mikan (.mikan)"), ("vmdk", "VMDK"), ("vdi", "VDI"), ("vhdx", "VHDX"), ("raw", "RAW")]:
            action = QAction(desc, self)
            action.triggered.connect(lambda checked, f=fmt: self.export_vm_as(f))
            export_as_menu.addAction(action)
        file_menu.addMenu(export_as_menu)
        file_menu.addSeparator()
        folder_action = QAction("🗂️ 文件夹管理", self)
        folder_action.triggered.connect(self.open_folder_manager)
        folder_action.setShortcut("Ctrl+Shift+F")
        file_menu.addAction(folder_action)
        file_menu.addSeparator()
        exit_action = QAction("退出(&X)", self)
        exit_action.triggered.connect(self.close)
        exit_action.setShortcut("Ctrl+Q")
        file_menu.addAction(exit_action)

        vm_menu = menubar.addMenu("虚拟机(&V)")
        edit_action = QAction("✏️ 编辑", self)
        edit_action.triggered.connect(self.edit_vm)
        edit_action.setShortcut("Ctrl+S")
        vm_menu.addAction(edit_action)
        launch_action = QAction("🚀 启动", self)
        launch_action.triggered.connect(self.launch_vm)
        launch_action.setShortcut("Ctrl+P")
        vm_menu.addAction(launch_action)
        vm_menu.addSeparator()
        snapshot_action = QAction("📸 快照", self)
        snapshot_action.triggered.connect(self.manage_snapshots)
        vm_menu.addAction(snapshot_action)
        script_action = QAction("📄 导出启动脚本", self)
        script_action.triggered.connect(self.export_script)
        vm_menu.addAction(script_action)
        disk_action = QAction("💾 磁盘管理", self)
        disk_action.triggered.connect(self.show_disk_manager)
        vm_menu.addAction(disk_action)
        vm_menu.addSeparator()
        delete_action = QAction("🗑️ 删除", self)
        delete_action.triggered.connect(self.delete_vm)
        delete_action.setShortcut("Delete")
        vm_menu.addAction(delete_action)

        hw_menu = menubar.addMenu("🔧 硬件配置")
        new_hw_action = QAction("📦 新建硬件配置", self)
        new_hw_action.triggered.connect(self.open_new_hw_profile_dialog)
        hw_menu.addAction(new_hw_action)
        manage_hw_action = QAction("📋 管理硬件配置", self)
        manage_hw_action.triggered.connect(self.open_hw_profile_manager)
        hw_menu.addAction(manage_hw_action)

        detect_menu = menubar.addMenu("🔍 检测")
        detect_hw_action = QAction("🔍 检测系统硬件", self)
        detect_hw_action.triggered.connect(self.detect_system_hardware)
        detect_menu.addAction(detect_hw_action)
        detect_qemu_action = QAction("🔍 检测 QEMU 硬件", self)
        detect_qemu_action.triggered.connect(self.detect_qemu_hardware)
        detect_menu.addAction(detect_qemu_action)
        detect_menu.addSeparator()
        refresh_qemu_action = QAction("🔄 重新扫描 QEMU", self)
        refresh_qemu_action.triggered.connect(self.refresh_qemu)
        detect_menu.addAction(refresh_qemu_action)

        view_menu = menubar.addMenu("查看(&V)")
        lang_menu = view_menu.addMenu("🌐 语言")
        for code, name in self.translator.get_languages().items():
            action = QAction(name, self)
            action.triggered.connect(lambda checked, c=code: self.change_language(c))
            lang_menu.addAction(action)

        help_menu = menubar.addMenu("❓ 帮助")
        about_action = QAction("📖 使用说明", self)
        about_action.triggered.connect(self.show_help)
        help_menu.addAction(about_action)
        github_action = QAction("🌐 开源项目 (GitHub)", self)
        github_action.triggered.connect(lambda: webbrowser.open(GITHUB_URL))
        help_menu.addAction(github_action)

        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.btn_new = QToolButton()
        self.btn_new.setText("📦 新建")
        self.btn_new.clicked.connect(self.create_vm)
        toolbar.addWidget(self.btn_new)
        toolbar.addSeparator()
        self.btn_edit = QToolButton()
        self.btn_edit.setText("✏️ 编辑")
        self.btn_edit.clicked.connect(self.edit_vm)
        self.btn_edit.setEnabled(False)
        toolbar.addWidget(self.btn_edit)
        toolbar.addSeparator()
        self.btn_launch = QToolButton()
        self.btn_launch.setText("🚀 启动")
        self.btn_launch.clicked.connect(self.launch_vm)
        self.btn_launch.setEnabled(False)
        self.btn_launch.setStyleSheet("QToolButton { color: #6a9a6a; font-weight: bold; }")
        toolbar.addWidget(self.btn_launch)
        toolbar.addSeparator()
        self.btn_export = QToolButton()
        self.btn_export.setText("📤 导出")
        self.btn_export.clicked.connect(self.export_vm)
        self.btn_export.setEnabled(False)
        toolbar.addWidget(self.btn_export)
        self.btn_import = QToolButton()
        self.btn_import.setText("📥 导入")
        self.btn_import.clicked.connect(self.import_vm)
        toolbar.addWidget(self.btn_import)
        toolbar.addSeparator()
        self.btn_folders = QToolButton()
        self.btn_folders.setText("🗂️ 文件夹")
        self.btn_folders.clicked.connect(self.open_folder_manager)
        toolbar.addWidget(self.btn_folders)
        toolbar.addSeparator()
        self.btn_refresh = QToolButton()
        self.btn_refresh.setText("🔄 刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(self.btn_refresh)

        splitter = QSplitter(Qt.Horizontal)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        title_widget = QWidget()
        title_widget.setStyleSheet("background-color: #000000; padding: 6px 10px;")
        title_layout = QVBoxLayout(title_widget)
        title_layout.setContentsMargins(4, 4, 4, 4)
        title_layout.setSpacing(6)
        row1 = QHBoxLayout()
        title_label = QLabel("📂 虚拟机")
        title_label.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 14px;")
        row1.addWidget(title_label)
        row1.addStretch()
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet("color: #888888; font-size: 12px;")
        row1.addWidget(self.count_label)
        title_layout.addLayout(row1)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(4)
        folder_icon = QLabel("🗂️")
        folder_row.addWidget(folder_icon)
        self.folder_combo = QComboBox()
        self.folder_combo.setStyleSheet("""
            QComboBox { background-color: #1a1a1a; color: #ffffff; border: 1px solid #4a6a8a; border-radius: 4px; padding: 5px 8px; font-size: 12px; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView { background-color: #1a1a1a; color: #ffffff; selection-background-color: #333333; border: 1px solid #4a6a8a; }
        """)
        self.folder_combo.setToolTip("切换虚拟机文件夹")
        self.folder_combo.currentIndexChanged.connect(self.on_folder_changed)
        folder_row.addWidget(self.folder_combo, 1)
        folder_manage_btn = QPushButton("⚙️")
        folder_manage_btn.setFixedSize(26, 26)
        folder_manage_btn.setToolTip("管理文件夹")
        folder_manage_btn.clicked.connect(self.open_folder_manager)
        folder_row.addWidget(folder_manage_btn)
        title_layout.addLayout(folder_row)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜索虚拟机...")
        self.search_edit.setStyleSheet("""
            QLineEdit { background-color: #1a1a1a; color: #ffffff; border: 1px solid #333333; border-radius: 4px; padding: 5px 10px; font-size: 12px; }
            QLineEdit:focus { border-color: #555555; }
        """)
        self.search_edit.textChanged.connect(self.on_search_changed)
        title_layout.addWidget(self.search_edit)
        left_layout.addWidget(title_widget)

        self.vm_list_widget = QListWidget()
        self.vm_list_widget.setFont(QFont("Microsoft YaHei", 12))
        self.vm_list_widget.itemSelectionChanged.connect(self.on_vm_selected)
        self.vm_list_widget.itemDoubleClicked.connect(self.launch_vm)
        left_layout.addWidget(self.vm_list_widget)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        info_widget = QWidget()
        info_widget.setStyleSheet("background-color: #000000; border-radius: 4px;")
        info_layout = QHBoxLayout(info_widget)
        info_layout.setContentsMargins(12, 8, 12, 8)
        self.vm_name_label = QLabel("选择虚拟机")
        self.vm_name_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        info_layout.addWidget(self.vm_name_label)
        info_layout.addStretch()
        self.vm_status_label = QLabel("● 未运行")
        self.vm_status_label.setStyleSheet("color: #666666; font-size: 13px;")
        info_layout.addWidget(self.vm_status_label)
        right_layout.addWidget(info_widget)
        self.tab_widget = QTabWidget()
        self.summary_tab = self.create_summary_tab()
        self.tab_widget.addTab(self.summary_tab, "📋 摘要")
        self.config_tab = self.create_config_tab()
        self.tab_widget.addTab(self.config_tab, "⚙️ 配置")
        right_layout.addWidget(self.tab_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([300, 1000])

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(splitter)
        self.setCentralWidget(central)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def create_summary_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)
        info_group = QGroupBox("基本信息")
        info_group.setFont(QFont("Microsoft YaHei", 12))
        info_layout = QGridLayout(info_group)
        info_layout.setVerticalSpacing(8)
        info_layout.setHorizontalSpacing(16)
        self.summary_labels = {}
        fields = [("系统类型:", "os_type"), ("系统版本:", "os_version"), ("架构:", "arch"),
                  ("内存:", "memory"), ("CPU核心:", "cpu"), ("磁盘大小:", "disk_size"),
                  ("QEMU版本:", "qemu_version"), ("创建时间:", "created")]
        for row, (label, key) in enumerate(fields):
            info_layout.addWidget(QLabel(label), row, 0)
            self.summary_labels[key] = QLabel("-")
            self.summary_labels[key].setStyleSheet("color: #ffffff; font-weight: bold;")
            info_layout.addWidget(self.summary_labels[key], row, 1)
        layout.addWidget(info_group)
        status_group = QGroupBox("运行状态")
        status_group.setFont(QFont("Microsoft YaHei", 12))
        status_layout = QVBoxLayout(status_group)
        self.summary_status_label = QLabel("● 未运行")
        self.summary_status_label.setStyleSheet("color: #666666; font-size: 16px; padding: 6px;")
        status_layout.addWidget(self.summary_status_label)
        layout.addWidget(status_group)
        layout.addStretch()
        return widget

    def create_config_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        self.config_info_label = QLabel("请选择一个虚拟机来查看配置")
        self.config_info_label.setStyleSheet("color: #888888; font-size: 14px; padding: 20px;")
        self.config_info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.config_info_label)
        layout.addStretch()
        return widget

    def refresh_ui_texts(self):
        self.setWindowTitle(f"Mikan QEMU Manager v{APP_VERSION}")
        self.btn_new.setText("📦 新建")
        self.btn_edit.setText("✏️ 编辑")
        self.btn_launch.setText("🚀 启动")
        self.btn_export.setText("📤 导出")
        self.btn_import.setText("📥 导入")
        self.btn_refresh.setText("🔄 刷新")

    def load_folders_to_combo(self):
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()
        folders = FOLDERS_CONFIG.get("folders", [])
        active_idx = FOLDERS_CONFIG.get("active_index", 0)
        for i, folder in enumerate(folders):
            display = folder.get("name", f"文件夹{i+1}")
            path = folder.get("path", "")
            if path:
                display += f"  [{Path(path).name}]"
            self.folder_combo.addItem(display, i)
        if 0 <= active_idx < self.folder_combo.count():
            self.folder_combo.setCurrentIndex(active_idx)
        self.folder_combo.blockSignals(False)

    def on_folder_changed(self, index):
        if index < 0:
            return
        idx = self.folder_combo.itemData(index)
        if idx is None:
            return
        if idx == FOLDERS_CONFIG.get("active_index", 0):
            return
        FOLDERS_CONFIG["active_index"] = idx
        save_folders_config()
        apply_active_folder()
        self.load_vms()
        self.refresh_vm_list()
        folder_name = FOLDERS_CONFIG["folders"][idx].get("name", "未命名")
        self.status_bar.showMessage(f"✅ 已切换到: {folder_name}  |  QEMU 扫描中...")
        def _bg():
            try:
                new_detector = QEMUHardwareDetector(use_cache=False)
                self.hardware_detector = new_detector
                msg = f"✅ 已切换到: {folder_name}  |  QEMU: {len(new_detector.qemu_versions)}个"
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection, Q_ARG(str, msg))
            except Exception as e:
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection, Q_ARG(str, f"⚠️ QEMU 扫描失败: {e}"))

    def on_folder_changed(self, index):
        if index < 0:
            return
        idx = self.folder_combo.itemData(index)
        if idx is None:
            return
        if idx == FOLDERS_CONFIG.get("active_index", 0):
            return
        FOLDERS_CONFIG["active_index"] = idx
        save_folders_config()
        apply_active_folder()
        self.load_vms()
        self.refresh_vm_list()
        folder_name = FOLDERS_CONFIG["folders"][idx].get("name", "未命名")
        self.status_bar.showMessage(f"✅ 已切换到: {folder_name}  |  QEMU 扫描中...")
        def _bg():
            try:
                new_detector = QEMUHardwareDetector(use_cache=False)
                self.hardware_detector = new_detector
                msg = f"✅ 已切换到: {folder_name}  |  QEMU: {len(new_detector.qemu_versions)}个"
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection,
                                         Q_ARG(str, msg))
            except Exception as e:
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection,
                                         Q_ARG(str, f"⚠️ QEMU 扫描失败: {e}"))
        Thread(target=_bg, daemon=True).start()

    def on_search_changed(self, text):
        keyword = text.strip().lower()
        self.vm_list_widget.clear()
        icons = {"Windows": "🪟", "Linux": "🐧", "Android": "📱", "macOS": "🍎"}
        filtered = 0
        for vm in self.vm_list:
            if keyword:
                searchable = f"{vm.name} {vm.os_type} {vm.os_version} {vm.cpu_model} {vm.preset}".lower()
                if keyword not in searchable:
                    continue
            icon = icons.get(vm.os_type, "💻")
            item = QListWidgetItem(f"{icon} {vm.name}")
            item.setData(Qt.UserRole, vm)
            self.vm_list_widget.addItem(item)
            filtered += 1
        if keyword:
            self.count_label.setText(f"{filtered}/{len(self.vm_list)}")
        else:
            self.count_label.setText(str(len(self.vm_list)))

    def load_vms(self):
        self.vm_list = []
        if not VMS_DIR.exists():
            return
        for vm_dir in VMS_DIR.iterdir():
            if not vm_dir.is_dir():
                continue
            config_file = vm_dir / "config.json"
            if config_file.exists():
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        vm = VMConfig.from_dict(data)
                        self.vm_list.append(vm)
                except Exception as e:
                    print(f"加载失败 {vm_dir.name}: {e}")

    def refresh_vm_list(self):
        self.load_folders_to_combo()
        if hasattr(self, 'search_edit'):
            self.on_search_changed(self.search_edit.text())
        else:
            self.vm_list_widget.clear()
            for vm in self.vm_list:
                item = QListWidgetItem(f"💻 {vm.name}")
                item.setData(Qt.UserRole, vm)
                self.vm_list_widget.addItem(item)
            self.count_label.setText(str(len(self.vm_list)))

    def on_vm_selected(self):
        items = self.vm_list_widget.selectedItems()
        if not items:
            self.current_vm = None
            self.btn_edit.setEnabled(False)
            self.btn_launch.setEnabled(False)
            self.btn_export.setEnabled(False)
            self.vm_name_label.setText("选择虚拟机")
            return
        vm = items[0].data(Qt.UserRole)
        self.current_vm = vm
        self.btn_edit.setEnabled(True)
        self.btn_launch.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.vm_name_label.setText(vm.name)
        self.update_summary(vm)
        self.update_config_tab(vm)

    def update_summary(self, vm):
        self.summary_labels["os_type"].setText(vm.os_type)
        self.summary_labels["os_version"].setText(vm.os_version)
        self.summary_labels["arch"].setText(vm.arch)
        self.summary_labels["memory"].setText(f"{vm.memory} MB")
        self.summary_labels["cpu"].setText(f"{vm.cpu} 核心")
        self.summary_labels["disk_size"].setText(f"{vm.disk_size} GB")
        self.summary_labels["qemu_version"].setText(vm.qemu_version)
        self.summary_labels["created"].setText(vm.created or "-")

    def update_config_tab(self, vm):
        for child in self.tab_widget.widget(1).findChildren(QWidget):
            if child != self.tab_widget.widget(1):
                child.deleteLater()
        layout = QVBoxLayout(self.tab_widget.widget(1))
        layout.setContentsMargins(12, 12, 12, 12)
        mem_backing_info = ""
        if vm.memory_backing_enabled:
            mem_backing_info = f"<br><b>内存磁盘:</b> ✅ 已启用 ({vm.memory_backing_size or vm.memory} MB)<br>"
            mem_backing_info += f"<b>内存文件:</b> {vm.memory_backing_file or '默认'}<br>"
        custom_qemu_info = ""
        if vm.custom_qemu_path:
            custom_qemu_info = f"<br><b>自定义QEMU:</b> {vm.custom_qemu_path}<br>"
        pt_info = ""
        if getattr(vm, 'usb_passthrough', None) or getattr(vm, 'pci_passthrough', None):
            pt_info = f"<br><b>硬件直通:</b> USB {len(vm.usb_passthrough)}个 | PCI {len(vm.pci_passthrough)}个<br>"
        text = f"""
        <b>名称:</b> {vm.name}<br>
        <b>归属文件夹:</b> {vm.folder_name or "-"}<br>
        <b>系统:</b> {vm.os_type} {vm.os_version}<br>
        <b>架构:</b> {vm.arch}<br>
        <b>内存:</b> {vm.memory} MB<br>
        <b>CPU:</b> {vm.cpu} 核心<br>
        <b>磁盘:</b> {vm.disk_size} GB ({vm.disk_format})<br>
        <b>接口:</b> {vm.disk_interface}<br>
        <b>CPU模型:</b> {vm.cpu_model}<br>
        <b>硬件配置:</b> {vm.cpu_profile or "默认"}<br>
        <b>加速:</b> {vm.accel}<br>
        <b>显卡:</b> {vm.vga}<br>
        <b>机器:</b> {vm.machine_type}<br>
        <b>声卡:</b> {vm.sound}<br>
        <b>网卡:</b> {vm.nic_model}<br>
        <b>网络模式:</b> {vm.network_mode}<br>
        <b>QEMU:</b> {vm.qemu_version}{custom_qemu_info}
        {pt_info}
        {mem_backing_info}
        """
        if vm.boot_iso:
            text += f"<b>启动ISO:</b> {Path(vm.boot_iso).name}<br>"
        if vm.share_dir:
            text += f"<b>共享目录:</b> {vm.share_dir}<br>"
        if vm.hostfwd:
            text += f"<b>端口转发:</b> {vm.hostfwd}<br>"
        if vm.bridge_interface:
            text += f"<b>桥接接口:</b> {vm.bridge_interface}<br>"
        if vm.tap_interface:
            text += f"<b>TAP设备:</b> {vm.tap_interface}<br>"
        label = QLabel(text)
        label.setStyleSheet("color: #d0d0d0; font-size: 13px; padding: 8px;")
        label.setWordWrap(True)
        layout.addWidget(label)
        edit_btn = QPushButton("✏️ 编辑配置")
        edit_btn.setMinimumHeight(36)
        edit_btn.clicked.connect(self.edit_vm)
        layout.addWidget(edit_btn)
        layout.addStretch()

    def open_folder_manager(self):
        dialog = FolderManagerDialog(self)
        dialog.exec()

    def open_new_hw_profile_dialog(self):
        dialog = HardwareProfileEditDialog(self, None, HardwareProfileManager())
        if dialog.exec() == QDialog.Accepted:
            QMessageBox.information(self, "成功", "✅ 硬件配置已保存")

    def open_hw_profile_manager(self):
        dialog = HardwareProfileManagerDialog(self)
        dialog.exec()

    def refresh_qemu(self):
        self.status_bar.showMessage("🔄 正在重新扫描 QEMU...")
        def _bg():
            try:
                new_detector = QEMUHardwareDetector(use_cache=False)
                self.hardware_detector = new_detector
                msg = f"✅ 已重新扫描 QEMU: 找到 {len(new_detector.qemu_versions)} 个版本"
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection, Q_ARG(str, msg))
            except Exception as e:
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection, Q_ARG(str, f"❌ 扫描失败: {e}"))
        Thread(target=_bg, daemon=True).start()

    def create_vm(self):
        dialog = CreateVMDialog(self)
        if dialog.exec() == QDialog.Accepted:
            vm = dialog.get_vm()
            if vm:
                self.vm_list.append(vm)
                self.refresh_vm_list()
                self.status_bar.showMessage(f"✅ 创建成功: {vm.name}")

    def edit_vm(self):
        if not self.current_vm:
            QMessageBox.warning(self, "提示", "请先选择一个虚拟机")
            return
        dialog = CreateVMDialog(self, self.current_vm)
        if dialog.exec() == QDialog.Accepted:
            vm = dialog.get_vm()
            if vm:
                self.load_vms()
                self.refresh_vm_list()
                self.status_bar.showMessage(f"✅ 配置已更新: {vm.name}")

    def launch_vm(self):
        if not self.current_vm:
            QMessageBox.warning(self, "提示", "请先选择一个虚拟机")
            return
        launcher = BASE_DIR / "launcher.py"
        if not launcher.exists():
            QMessageBox.warning(self, "错误", f"启动器不存在:\n{launcher}\n\n请确保 launcher.py 在同一目录")
            return
        try:
            subprocess.Popen(
                ["python", str(launcher), self.current_vm.name],
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )
            self.status_bar.showMessage(f"🚀 已启动: {self.current_vm.name}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"启动失败:\n{e}")

    def delete_vm(self):
        if not self.current_vm:
            return
        reply = QMessageBox.question(self, "确认",
            f"确定要删除虚拟机 '{self.current_vm.name}' 吗？\n\n⚠️ 此操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        vm_dir = VMS_DIR / self.current_vm.name
        if vm_dir.exists():
            shutil.rmtree(vm_dir)
        snap_dir = SNAPSHOTS_DIR / self.current_vm.name
        if snap_dir.exists():
            shutil.rmtree(snap_dir)
        self.vm_list.remove(self.current_vm)
        self.current_vm = None
        self.refresh_vm_list()
        self.vm_name_label.setText("选择虚拟机")
        self.status_bar.showMessage("🗑️ 已删除")

    def export_vm(self):
        if not self.current_vm:
            QMessageBox.warning(self, "提示", "请先选择一个虚拟机")
            return
        default_name = f"{self.current_vm.name}.mikan"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出", str(EXPORT_DIR / default_name),
            "Mikan 虚拟机包 (*.mikan)")
        if not file_path:
            return
        if not file_path.endswith('.mikan'):
            file_path += '.mikan'
        reply = QMessageBox.question(self, "确认",
            f"将导出虚拟机 \"{self.current_vm.name}\" 到:\n{file_path}\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.status_bar.showMessage(f"📦 正在导出 {self.current_vm.name}...")
        def do_export():
            try:
                vm_dir = VMS_DIR / self.current_vm.name
                if not vm_dir.exists():
                    return
                temp_dir = Path(tempfile.mkdtemp())
                shutil.copytree(vm_dir, temp_dir / self.current_vm.name)
                snap_dir = SNAPSHOTS_DIR / self.current_vm.name
                if snap_dir.exists():
                    shutil.copytree(snap_dir, temp_dir / "snapshots" / self.current_vm.name)
                info = {"name": self.current_vm.name, "exported": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                with open(temp_dir / "vm_info.json", 'w', encoding='utf-8') as f:
                    json.dump(info, f, indent=2, ensure_ascii=False)
                with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file in temp_dir.rglob('*'):
                        if file.is_file():
                            zipf.write(file, file.relative_to(temp_dir))
                shutil.rmtree(temp_dir)
                size_mb = Path(file_path).stat().st_size / 1024 / 1024
                self.status_bar.showMessage(f"✅ 导出成功 ({size_mb:.1f} MB)")
                QMessageBox.information(self, "成功", f"✅ 导出成功 ({size_mb:.1f} MB)\n{file_path}")
            except Exception as e:
                self.status_bar.showMessage("❌ 导出失败")
                QMessageBox.warning(self, "错误", f"导出失败:\n{e}")
        Thread(target=do_export).start()

    def export_vm_as(self, format_type: str):
        if not self.current_vm:
            QMessageBox.warning(self, "提示", "请先选择一个虚拟机")
            return
        if format_type == "mikan":
            self.export_vm()
            return
        if self.current_vm.disks:
            disk_path = Path(self.current_vm.disks[0]["path"])
            disk_format = self.current_vm.disks[0]["format"]
        elif self.current_vm.disk_path:
            disk_path = Path(self.current_vm.disk_path)
            disk_format = self.current_vm.disk_format
        else:
            QMessageBox.warning(self, "错误", "虚拟机没有磁盘")
            return
        if not disk_path.exists():
            QMessageBox.warning(self, "错误", "磁盘文件不存在")
            return
        format_map = {"vmdk": ("vmdk", "VMDK"), "vdi": ("vdi", "VDI"), "vhdx": ("vhdx", "VHDX"), "raw": ("img", "RAW")}
        ext, desc = format_map.get(format_type, (format_type, format_type.upper()))
        qemu_img = find_qemu_img()
        if not qemu_img:
            QMessageBox.warning(self, "错误", "找不到 qemu-img")
            return
        zip_path, _ = QFileDialog.getSaveFileName(
            self, f"导出为 {desc}", str(EXPORT_DIR / f"{self.current_vm.name}_{format_type}.zip"),
            "ZIP 压缩包 (*.zip)")
        if not zip_path:
            return
        self.status_bar.showMessage(f"⏳ 正在导出 {desc}...")
        def do_export():
            try:
                temp_disk = EXPORT_DIR / f"temp_{self.current_vm.name}.{ext}"
                subprocess.run([str(qemu_img), "convert", "-f", disk_format, "-O", format_type,
                              str(disk_path), str(temp_disk)], check=True, capture_output=True,
                              encoding='utf-8', errors='ignore')
                temp_dir = EXPORT_DIR / f"temp_export_{int(time.time())}"
                temp_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(temp_disk, temp_dir / f"{self.current_vm.name}.{ext}")
                config_file = VMS_DIR / self.current_vm.name / "config.json"
                if config_file.exists():
                    shutil.copy2(config_file, temp_dir / "config.json")
                with open(temp_dir / "README.txt", 'w', encoding='utf-8') as f:
                    f.write(f"{desc} 磁盘\n虚拟机: {self.current_vm.name}\n导出: {datetime.now()}\n格式: {ext}")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file in temp_dir.rglob('*'):
                        if file.is_file():
                            zipf.write(file, file.relative_to(temp_dir))
                shutil.rmtree(temp_dir)
                if temp_disk.exists():
                    temp_disk.unlink()
                size_mb = Path(zip_path).stat().st_size / 1024 / 1024
                self.status_bar.showMessage(f"✅ 导出成功 ({size_mb:.1f} MB)")
                QMessageBox.information(self, "成功", f"✅ 导出成功 ({size_mb:.1f} MB)\n{zip_path}")
            except Exception as e:
                self.status_bar.showMessage("❌ 导出失败")
                QMessageBox.warning(self, "错误", f"导出失败:\n{e}")
        Thread(target=do_export).start()

    def import_vm(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入", str(EXPORT_DIR),
            "Mikan 虚拟机包 (*.mikan)")
        if not file_path:
            return
        if not file_path.endswith('.mikan'):
            QMessageBox.warning(self, "错误", "请选择 .mikan 格式")
            return
        reply = QMessageBox.question(self, "确认",
            f"将导入虚拟机包:\n{Path(file_path).name}\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.status_bar.showMessage("📥 正在导入...")
        def do_import():
            try:
                temp_dir = Path(tempfile.mkdtemp())
                with zipfile.ZipFile(file_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                info_file = temp_dir / "vm_info.json"
                if info_file.exists():
                    with open(info_file, 'r', encoding='utf-8') as f:
                        info = json.load(f)
                    vm_name = info.get("name", Path(file_path).stem)
                else:
                    vm_name = Path(file_path).stem
                vm_source = temp_dir / vm_name
                if not vm_source.exists():
                    dirs = [d for d in temp_dir.iterdir() if d.is_dir() and d.name != "snapshots"]
                    if dirs:
                        vm_source = dirs[0]
                        vm_name = vm_source.name
                    else:
                        raise Exception("找不到虚拟机文件")
                target_dir = VMS_DIR / vm_name
                if target_dir.exists():
                    reply = QMessageBox.question(self, "确认",
                        f"虚拟机 \"{vm_name}\" 已存在，是否覆盖？",
                        QMessageBox.Yes | QMessageBox.No)
                    if reply != QMessageBox.Yes:
                        shutil.rmtree(temp_dir)
                        return
                    shutil.rmtree(target_dir)
                shutil.copytree(vm_source, target_dir)
                snap_source = temp_dir / "snapshots" / vm_name
                if snap_source.exists():
                    snap_target = SNAPSHOTS_DIR / vm_name
                    if snap_target.exists():
                        shutil.rmtree(snap_target)
                    shutil.copytree(snap_source, snap_target)
                shutil.rmtree(temp_dir)
                self.load_vms()
                self.refresh_vm_list()
                self.status_bar.showMessage(f"✅ 导入成功: {vm_name}")
                QMessageBox.information(self, "成功", f"✅ 导入成功: {vm_name}")
            except Exception as e:
                self.status_bar.showMessage("❌ 导入失败")
                QMessageBox.warning(self, "错误", f"导入失败:\n{e}")
        Thread(target=do_import).start()

    def manage_snapshots(self):
        if not self.current_vm:
            QMessageBox.warning(self, "提示", "请先选择一个虚拟机")
            return
        QMessageBox.information(self, "📸 快照管理",
            "快照功能已在启动器中完整实现\n\n"
            "三种快照方案:\n"
            "❄️ 冷快照 - 关机后复制磁盘文件\n"
            "🔥 内部快照 - 运行时 savevm (需要QMP)\n"
            "🔥 外部快照 - 运行时 blockdev-snapshot-sync\n\n"
            "请通过启动器窗口操作快照")

    def export_script(self):
        if not self.current_vm:
            QMessageBox.warning(self, "提示", "请先选择一个虚拟机")
            return
        reply = QMessageBox.question(self, "确认",
            "Yes = Windows (.bat)\nNo = Linux/Shell (.sh)",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if reply == QMessageBox.Cancel:
            return
        is_windows = (reply == QMessageBox.Yes)
        ext = ".bat" if is_windows else ".sh"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出启动脚本", str(BASE_DIR / f"{self.current_vm.name}_launch{ext}"),
            f"脚本文件 (*{ext})")
        if not file_path:
            return
        try:
            from launcher import build_command
            cmd, error = build_command(self.current_vm.to_dict())
            if error:
                QMessageBox.warning(self, "错误", f"构建命令失败:\n{error}")
                return
            if is_windows:
                content = f"@echo off\nchcp 65001 >nul\necho 🚀 启动: {self.current_vm.name}\necho.\n{' '.join(cmd)}\npause\n"
            else:
                content = f"#!/bin/bash\necho \"🚀 启动: {self.current_vm.name}\"\necho\n{' '.join(cmd)}\nread -p \"按 Enter 退出...\"\n"
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            if not is_windows:
                os.chmod(file_path, 0o755)
            self.status_bar.showMessage("✅ 脚本已导出")
            QMessageBox.information(self, "成功", f"脚本已导出:\n{file_path}")
        except ImportError:
            QMessageBox.warning(self, "错误", "找不到 launcher.py")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"导出失败:\n{e}")

    def show_disk_manager(self):
        if not self.current_vm:
            QMessageBox.warning(self, "提示", "请先选择一个虚拟机")
            return
        QMessageBox.information(self, "💾 磁盘管理",
            "💾 磁盘管理功能已在虚拟机配置中集成\n\n"
            "请在「编辑」→ 硬件配置中调整磁盘设置\n"
            "包括: 磁盘大小、格式、接口等")

    def refresh(self):
        self.load_vms()
        self.refresh_vm_list()
        self.status_bar.showMessage("✅ 已刷新")

    def change_language(self, lang_code: str):
        self.translator.set_language(lang_code)
        self.refresh_ui_texts()
        self.status_bar.showMessage("🌐 语言已切换")

    def load_language_setting(self):
        lang_file = CONFIG_DIR / "lang.json"
        if lang_file.exists():
            try:
                with open(lang_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    lang = data.get("language", "zh_CN")
                    self.translator.set_language(lang)
            except:
                pass

    def show_help(self):
        QMessageBox.information(self, "使用说明",
            f"📖 Mikan QEMU Manager v{APP_VERSION}\n\n"
            "📦 新建 - 创建虚拟机\n"
            "✏️ 编辑 - 修改配置\n"
            "📤 导出 - 导出 .mikan 包\n"
            "📤 导出为 - 导出为 VMDK/VDI/VHDX/RAW\n"
            "📥 导入 - 导入 .mikan 包\n"
            "📸 快照 - 管理快照\n"
            "📄 脚本 - 导出启动脚本\n"
            "🚀 启动 - 启动虚拟机\n\n"
            "🔍 自动检测当前目录下所有QEMU版本\n"
            "⚡ 自动检测系统支持的硬件加速\n"
            "🧠 内置2011-2026年硬件配置，支持用户自定义\n"
            "🌐 支持多语言: 简体中文 / English\n"
            "🌐 支持网络模式: user/bridge/tap/socket/vde/none\n"
            "💾 支持内存磁盘模式 (使用本地文件作为内存)\n"
            "🗂️ 支持多文件夹管理\n"
            "🔍 支持虚拟机搜索\n"
            "🔌 支持硬件直通 (USB/PCI)\n"
            f"🔗 开源项目: {GITHUB_URL}")

    def detect_system_hardware(self):
        self.status_bar.showMessage("🔍 正在检测系统硬件...")
        def worker():
            try:
                info = SystemDetector.get_system_info()
                text = "🖥️ 系统信息\n" + "=" * 40 + "\n"
                for key, value in info.items():
                    text += f"{key}: {value}\n"
                text += "\n\n🔍 QEMU 支持硬件\n" + "=" * 40 + "\n"
                qemu_info = SystemDetector.get_qemu_supported_hardware()
                for category, items in qemu_info.items():
                    if items:
                        text += f"\n📌 {category}:\n"
                        for item in items:
                            if isinstance(item, dict):
                                text += f"  • {item.get('版本', '')} - {item.get('信息', '')}\n"
                            else:
                                text += f"  • {item}\n"
                QMetaObject.invokeMethod(self, "show_detection_result", Qt.QueuedConnection,
                                         Q_ARG(str, "🔍 系统检测结果"), Q_ARG(str, text))
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection,
                                         Q_ARG(str, "✅ 系统检测完成"))
            except Exception as e:
                QMetaObject.invokeMethod(self, "show_error", Qt.QueuedConnection,
                                         Q_ARG(str, f"检测失败:\n{e}"))
        Thread(target=worker).start()

    def detect_qemu_hardware(self):
        self.status_bar.showMessage("🔍 正在检测 QEMU 硬件支持...")
        def worker():
            try:
                qemu_info = SystemDetector.get_qemu_supported_hardware()
                text = "🔍 QEMU 硬件支持详情\n" + "=" * 40 + "\n"
                qemu_versions = qemu_info.get("QEMU版本", [])
                if qemu_versions:
                    text += f"\n📦 检测到 {len(qemu_versions)} 个 QEMU 版本:\n"
                    for ver in qemu_versions:
                        text += f"  • {ver.get('版本', '')} ({ver.get('信息', '')})\n"
                else:
                    text += "\n⚠️ 未检测到 QEMU 版本\n"
                accels = qemu_info.get("可用加速器", [])
                if accels:
                    text += f"\n⚡ 支持的加速器:\n"
                    for accel in accels:
                        text += f"  • {accel}\n"
                cpus = qemu_info.get("支持CPU型号", [])
                if cpus:
                    text += f"\n💻 支持的 CPU 型号 ({len(cpus)}种):\n"
                    for cpu in cpus[:15]:
                        text += f"  • {cpu}\n"
                    if len(cpus) > 15:
                        text += f"  ... 还有 {len(cpus)-15} 种\n"
                vgas = qemu_info.get("支持显卡", [])
                if vgas:
                    text += f"\n🖥️ 支持的显卡 ({len(vgas)}种):\n"
                    for vga in vgas[:10]:
                        text += f"  • {vga}\n"
                machines = qemu_info.get("支持机器类型", [])
                if machines:
                    text += f"\n🏷️ 支持的机器类型 ({len(machines)}种):\n"
                    for machine in machines[:10]:
                        text += f"  • {machine}\n"
                QMetaObject.invokeMethod(self, "show_detection_result", Qt.QueuedConnection,
                                         Q_ARG(str, "🔍 QEMU 硬件支持"), Q_ARG(str, text))
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection,
                                         Q_ARG(str, "✅ QEMU 硬件检测完成"))
            except Exception as e:
                QMetaObject.invokeMethod(self, "show_error", Qt.QueuedConnection,
                                         Q_ARG(str, f"检测失败:\n{e}"))
        Thread(target=worker).start()

    @Slot(str, str)
    def show_detection_result(self, title: str, text: str):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(520, 400)
        dialog.setStyleSheet("""
            QDialog { background-color: #000000; color: #ffffff; }
            QLabel { color: #ffffff; font-size: 12px; font-family: "Microsoft YaHei"; }
            QScrollArea { background-color: #000000; border: 1px solid #333333; border-radius: 4px; }
            QPushButton { background-color: #333333; color: #ffffff; border: none; border-radius: 4px; padding: 8px 20px; font-weight: bold; font-size: 13px; font-family: "Microsoft YaHei"; }
            QPushButton:hover { background-color: #444444; }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        content_layout.addWidget(label)
        content_layout.addStretch()
        scroll.setWidget(content_widget)
        layout.addWidget(scroll, 1)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        dialog.exec()

    @Slot(str)
    def update_status(self, message: str):
        self.status_bar.showMessage(message)

    @Slot(str)
    def show_error(self, message: str):
        QMessageBox.warning(self, "错误", message)


# ============================================================
# main()
# ============================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("Mikan QEMU Manager")
    app.setApplicationVersion(APP_VERSION)
    font = QFont("Microsoft YaHei", 11)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()