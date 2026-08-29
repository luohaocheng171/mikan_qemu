#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mikan QEMU Manager v5.0 - VMware风格UI
完整功能版 - 保留全部功能，只改UI布局
"""

import os
import sys
import subprocess
import importlib  # 修复：提前导入 importlib
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
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from threading import Thread
from collections import defaultdict

# ============================================================
# 自动依赖检查和安装
# ============================================================
def check_and_install_dependencies():
    """检查并自动安装所有依赖"""
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
        
        # 验证安装
        print("\n" + "=" * 60)
        print("🔍 验证依赖安装...")
        print("=" * 60)
        
        for package, import_name in required_packages.items():
            try:
                importlib.import_module(import_name)
                print(f"✅ {package} 验证通过")
            except ImportError:
                print(f"❌ {package} 仍然无法导入")
                print(f"   请手动安装: pip install {package}")
                return False
    
    print("\n" + "=" * 60)
    print("✅ 所有依赖检查通过！")
    print("=" * 60)
    return True

# 运行依赖检查
if not check_and_install_dependencies():
    print("\n⚠️ 依赖安装失败，请手动安装后重新运行")
    print("   pip install PySide6 psutil")
    input("\n按回车键退出...")
    sys.exit(1)

# ============================================================
# 导入依赖（在检查之后）
# ============================================================
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

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

# ========== 配置 ==========
BASE_DIR = Path(__file__).parent
VMS_DIR = BASE_DIR / "vms"
ISO_DIR = BASE_DIR / "iso"
SNAPSHOTS_DIR = BASE_DIR / "snapshots"
EXPORT_DIR = BASE_DIR / "exports"
CONFIG_DIR = BASE_DIR / "config"
SHARE_DIR = BASE_DIR / "share"

for d in [VMS_DIR, ISO_DIR, SNAPSHOTS_DIR, EXPORT_DIR, CONFIG_DIR, SHARE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

APP_VERSION = "5.0"
CONFIG_VERSION = "5.0"

# ============================================================
# QEMU 硬件检测（修复版 - 独立try-except + 20秒超时）
# ============================================================
class QEMUHardwareDetector:
    """检测QEMU支持的硬件"""
    
    def __init__(self):
        self.qemu_versions = {}
        self.hardware_cache = {}
        self.scan_qemu_versions()
        self.detect_acceleration()
    
    def scan_qemu_versions(self):
        """扫描所有QEMU版本"""
        for item in BASE_DIR.iterdir():
            if item.is_dir() and item.name.startswith("qemu"):
                exe_path = None
                for exe_name in ["qemu-system-x86_64.exe", "qemu-system-x86_64", 
                                 "qemu-system-i386.exe", "qemu-system-i386"]:
                    exe = item / exe_name
                    if exe.exists():
                        exe_path = str(exe)
                        break
                if exe_path:
                    info = self.get_qemu_info(exe_path)
                    self.qemu_versions[item.name] = {
                        "path": exe_path,
                        "info": info
                    }
    
    def get_qemu_info(self, exe_path: str) -> dict:
        """获取QEMU版本信息 - 完整版（独立try-except + 20秒超时）"""
        info = {
            "version": "未知",
            "year": 2020,
            "supported_devices": [],
            "vga_types": [],
            "display_types": [],
            "machine_types": [],
            "cpu_models": [],
            "accel_types": [],
            "netdev_types": [],
            "audio_devices": [],
            "usb_devices": [],
            "pci_devices": [],
            "gpu_models": [],
            "firmware_types": [],
            "block_drivers": []
        }
        
        exe_name = Path(exe_path).name if Path(exe_path).name else "QEMU"
        
        # 版本信息 - 单独 try-except
        try:
            result = subprocess.run(
                [exe_path, "--version"],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=20
            )
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0] if result.stdout else ""
                info["version"] = version_line
                year_match = re.search(r'(20[1-9][0-9])', version_line)
                if year_match:
                    info["year"] = int(year_match.group(1))
        except subprocess.TimeoutExpired:
            print(f"⚠️ {exe_name} --version 超时（20秒），跳过版本检测")
        except Exception as e:
            print(f"⚠️ {exe_name} --version 出错: {e}")
        
        # 检测设备 - 单独 try-except
        try:
            result = subprocess.run(
                [exe_path, "-device", "help"],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=20
            )
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
        except subprocess.TimeoutExpired:
            print(f"⚠️ {exe_name} -device help 超时（20秒），跳过设备检测")
        except Exception as e:
            print(f"⚠️ {exe_name} -device help 出错: {e}")
        
        # 检测显卡 - 单独 try-except
        try:
            result = subprocess.run(
                [exe_path, "-vga", "help"],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=20
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["vga_types"]:
                            info["vga_types"].append(item)
                            # GPU 型号（用于 GPU 下拉框）
                            if item not in info["gpu_models"]:
                                info["gpu_models"].append(item)
        except subprocess.TimeoutExpired:
            print(f"⚠️ {exe_name} -vga help 超时（20秒），跳过显卡检测")
        except Exception as e:
            print(f"⚠️ {exe_name} -vga help 出错: {e}")
        
        # 检测显示后端 - 单独 try-except
        try:
            result = subprocess.run(
                [exe_path, "-display", "help"],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=20
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["display_types"]:
                            info["display_types"].append(item)
        except subprocess.TimeoutExpired:
            print(f"⚠️ {exe_name} -display help 超时（20秒），跳过显示后端检测")
        except Exception as e:
            print(f"⚠️ {exe_name} -display help 出错: {e}")
        
        # 检测机器类型 - 单独 try-except
        try:
            result = subprocess.run(
                [exe_path, "-machine", "help"],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=20
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid', 'Machine')):
                        parts = line.split()
                        if parts:
                            machine = parts[0].replace(':', '')
                            if machine and machine not in info["machine_types"]:
                                info["machine_types"].append(machine)
        except subprocess.TimeoutExpired:
            print(f"⚠️ {exe_name} -machine help 超时（20秒），跳过机器类型检测")
        except Exception as e:
            print(f"⚠️ {exe_name} -machine help 出错: {e}")
        
        # 检测CPU模型 - 单独 try-except（完整版）
        try:
            result = subprocess.run(
                [exe_path, "-cpu", "help"],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=20
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid', 'x86', 'Recognized')):
                        item = line.split()[0]
                        if item and item not in info["cpu_models"]:
                            info["cpu_models"].append(item)
        except subprocess.TimeoutExpired:
            print(f"⚠️ {exe_name} -cpu help 超时（20秒），跳过CPU模型检测")
        except Exception as e:
            print(f"⚠️ {exe_name} -cpu help 出错: {e}")
        
        # 检测加速器 - 单独 try-except
        try:
            result = subprocess.run(
                [exe_path, "-accel", "help"],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=20
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["accel_types"]:
                            info["accel_types"].append(item)
        except subprocess.TimeoutExpired:
            print(f"⚠️ {exe_name} -accel help 超时（20秒），跳过加速器检测")
        except Exception as e:
            print(f"⚠️ {exe_name} -accel help 出错: {e}")
        
        # 检测网络后端 - 单独 try-except
        try:
            result = subprocess.run(
                [exe_path, "-netdev", "help"],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=20
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["netdev_types"]:
                            info["netdev_types"].append(item)
        except subprocess.TimeoutExpired:
            print(f"⚠️ {exe_name} -netdev help 超时（20秒），跳过网络后端检测")
        except Exception as e:
            print(f"⚠️ {exe_name} -netdev help 出错: {e}")
        
        # 检测音频设备 - 单独 try-except
        try:
            result = subprocess.run(
                [exe_path, "-audiodev", "help"],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=20
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["audio_devices"]:
                            info["audio_devices"].append(item)
        except subprocess.TimeoutExpired:
            print(f"⚠️ {exe_name} -audiodev help 超时（20秒），跳过音频设备检测")
        except Exception as e:
            print(f"⚠️ {exe_name} -audiodev help 出错: {e}")
        
        # 检测固件（-fw_cfg 或 -bios 相关）
        try:
            result = subprocess.run(
                [exe_path, "-fw_cfg", "help"],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=20
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["firmware_types"]:
                            info["firmware_types"].append(item)
        except subprocess.TimeoutExpired:
            print(f"⚠️ {exe_name} -fw_cfg help 超时（20秒），跳过固件检测")
        except Exception as e:
            print(f"⚠️ {exe_name} -fw_cfg help 出错: {e}")
        
        # 检测块设备驱动（-drive 相关）
        try:
            result = subprocess.run(
                [exe_path, "-drive", "help"],
                capture_output=True, text=True, encoding='utf-8', errors='ignore',
                timeout=20
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line and not line.startswith(('-', 'Available', 'Valid')):
                        item = line.split()[0]
                        if item and item not in info["block_drivers"]:
                            info["block_drivers"].append(item)
        except subprocess.TimeoutExpired:
            print(f"⚠️ {exe_name} -drive help 超时（20秒），跳过块设备驱动检测")
        except Exception as e:
            print(f"⚠️ {exe_name} -drive help 出错: {e}")
                            
        return info
    
    def detect_acceleration(self):
        """检测当前系统支持的硬件加速"""
        self.available_accel = []
        self.hypervisor_info = {}
        
        if sys.platform == "win32":
            try:
                result = subprocess.run(
                    ["systeminfo"], capture_output=True, text=True, encoding='utf-8', errors='ignore',
                    timeout=15
                )
                if "Hyper-V" in result.stdout:
                    self.hypervisor_info["hyperv"] = True
                    self.available_accel.append("whpx")
                
                result = subprocess.run(
                    ["sc", "query", "haxm"], capture_output=True, text=True, encoding='utf-8', errors='ignore',
                    timeout=5
                )
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
                result = subprocess.run(
                    ["sysctl", "kern.hv_support"],
                    capture_output=True, text=True, encoding='utf-8', errors='ignore',
                    timeout=5
                )
                if "1" in result.stdout:
                    self.hypervisor_info["hvf"] = True
                    self.available_accel.append("hvf")
            except:
                pass
        
        if "tcg" not in self.available_accel:
            self.available_accel.insert(0, "tcg")
        
        self.default_accel = self.available_accel[0] if self.available_accel else "tcg"

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
        "status_converting": "🔄 正在转换...",
        "status_convert_done": "✅ 转换完成",
        "status_convert_failed": "❌ 转换失败",
        "status_resizing": "📏 正在调整...",
        "status_resize_done": "✅ 已调整为 {} GB",
        "status_resize_failed": "❌ 调整失败",
        "status_detecting": "🔍 正在检测QEMU硬件...",
        "menu_help": "❓ 帮助",
        "menu_help_about": "📖 使用说明",
        "menu_view": "👁️ 视图",
        "menu_view_toolbar": "显示工具栏",
        "menu_language": "🌐 语言",
        "menu_detect": "🔍 检测",
        "menu_detect_hw": "🔍 检测系统硬件",
        "btn_new": "新建",
        "btn_edit": "编辑",
        "btn_delete": "删除",
        "btn_export": "导出",
        "btn_export_as": "导出为",
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
        "label_preset_desc": "💡 {}",
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
        "label_kernel_iso": "引导镜像:",
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
        "label_cpu_stepping": "CPU 步进:",
        "label_cpu_level": "CPU 级别:",
        "label_cpu_xlevel": "CPU 扩展级别:",
        "label_cpu_features": "CPU 特性:",
        "label_cpu_capacity": "CPU 容量 (%):",
        "label_cpu_latency": "CPU 延迟 (µs):",
        "label_cpu_quota": "CPU 配额 (%):",
        "label_cpu_period": "CPU 周期 (µs):",
        "label_gpu_model": "GPU 型号:",
        "label_gpu_ram": "GPU 内存 (MB):",
        "label_gpu_freq": "GPU 频率 (MHz):",
        "label_gpu_vgamem": "VGA 内存 (MB):",
        "label_gpu_gl_version": "OpenGL 版本:",
        "label_gpu_rendernode": "渲染节点:",
        "label_gpu_edid": "EDID 文件:",
        "label_nic_model": "网卡型号:",
        "label_nic_queues": "网卡队列数:",
        "label_nic_mac": "MAC 地址:",
        "label_storage_type": "存储类型:",
        "label_storage_format": "存储格式:",
        "label_cluster_size": "簇大小:",
        "label_audio_model": "音频模型:",
        "label_audio_codec": "音频编解码器:",
        "label_usb_controller": "USB 控制器:",
        "label_usb_ports": "USB 端口数:",
        "label_pci_bus": "PCI 总线:",
        "label_pci_slot": "PCI 插槽:",
        "label_serial": "串口:",
        "label_parallel": "并口:",
        "label_firmware": "固件:",
        "label_rtc_mode": "RTC 模式:",
        "label_trace_events": "追踪事件:",
        "label_log_level": "日志级别:",
        "label_gdb_port": "GDB 端口:",
        "label_chroot": "Chroot 路径:",
        "label_security_user": "安全用户:",
        "label_cpu_freq": "CPU 频率 (MHz):",
        "label_cpu_clock": "CPU 时钟 (MHz):",
        "check_acpi": "启用 ACPI (电源管理)",
        "check_usb": "启用 USB",
        "check_opengl": "启用 OpenGL 加速",
        "check_share": "启用共享文件夹",
        "check_snapshot": "📸 快照模式 (-snapshot)",
        "check_readonly": "🔒 磁盘只读模式",
        "check_net_restrict": "🚫 限制网络访问",
        "check_mem_prealloc": "📌 预分配所有内存",
        "check_hugepages": "📌 使用大页内存 (Linux)",
        "check_no_hpet": "⏱️ 禁用 HPET",
        "check_no_kvm_nested": "🚫 禁用 KVM 嵌套虚拟化",
        "check_force_tcg": "⚠️ 强制 TCG 模式",
        "check_usb_tablet": "🖱️ USB 平板模式 (绝对坐标) ✅",
        "check_no_mouse": "🚫 禁用鼠标集成",
        "check_monitor_stdio": "📟 启用 Monitor 控制台",
        "check_no_reboot": "🚫 崩溃后不重启",
        "check_no_shutdown": "🚫 不关机",
        "check_sandbox": "🔒 沙箱模式",
        "check_boot_menu": "📋 显示启动菜单",
        "check_encryption": "🔐 加密存储",
        "check_compression": "📦 压缩存储",
        "check_selinux": "🔐 SELinux",
        "check_apparmor": "🔐 AppArmor",
        "check_gdb_stop": "🛑 在 GDB 连接时停止",
        "disk_mgr_title": "💾 虚拟磁盘管理器（高级） - {}",
        "disk_mgr_new": "📦 新建",
        "disk_mgr_attach": "🔗 选择已有",
        "disk_mgr_detach": "⛓️卸载",
        "disk_mgr_properties": "📊 属性",
        "disk_mgr_convert": "🔄 转换",
        "disk_mgr_resize": "📏 调整",
        "disk_mgr_no_disk": "无磁盘",
        "disk_mgr_count": "共 {} 块磁盘",
        "disk_mgr_created": "✅ 已创建: {}",
        "disk_mgr_attached": "✅ 已挂载: {}",
        "disk_mgr_detached": "⛓️已卸载: {}",
        "snapshot_title": "📸 快照管理 - {}",
        "snapshot_info": "📌 快照备份整个虚拟机文件夹（磁盘+配置）",
        "snapshot_create": "📸 创建",
        "snapshot_restore": "↩️ 恢复",
        "snapshot_delete": "🗑️ 删除",
        "snapshot_no_snapshots": "(暂无快照)",
        "snapshot_create_title": "创建快照",
        "snapshot_create_prompt": "请输入快照名称:",
        "snapshot_restore_confirm": "确定要恢复快照 '{}' 吗？\n\n⚠️ 当前虚拟机的所有数据将被覆盖！\n快照大小: {}\n此操作不可撤销！",
        "snapshot_delete_confirm": "确定要删除快照 '{}' 吗？\n\n快照大小: {}",
        "snapshot_created": "快照 '{}' 创建成功！\n\n共备份 {} 个文件",
        "snapshot_restored": "快照 '{}' 恢复成功！",
        "snapshot_deleted": "快照 '{}' 已删除",
        "error": "错误",
        "warning": "提示",
        "info": "信息",
        "success": "成功",
        "confirm": "确认",
        "msg_select_vm": "请先选择一个虚拟机",
        "msg_name_empty": "请输入虚拟机名称",
        "msg_vm_exists": "虚拟机 '{}' 已存在",
        "msg_vm_not_found": "虚拟机不存在",
        "msg_config_missing": "配置文件不存在",
        "msg_launcher_missing": "启动器不存在:\n{}\n\n请确保 launcher.py 在同一目录",
        "msg_launch_failed": "启动失败:\n{}",
        "msg_export_confirm": "将导出虚拟机 \"{}\" 到:\n{}\n\n是否继续？",
        "msg_import_confirm": "将导入虚拟机包:\n{}\n\n是否继续？",
        "msg_overwrite_confirm": "虚拟机 \"{}\" 已存在，是否覆盖？",
        "msg_convert_confirm": "当前格式: {}\n选择目标格式:",
        "msg_resize_confirm": "当前大小: {} GB\n请输入新大小 (GB):",
        "msg_create_disk_failed": "创建失败:\n{}",
        "msg_attach_disk_failed": "挂载失败:\n{}",
        "msg_detach_confirm": "确定要卸载磁盘 {} 吗？",
        "msg_detach_system_confirm": "这是系统盘 (第一块磁盘)，卸载后虚拟机可能无法启动。\n\n确定要卸载吗？",
        "msg_qemu_img_not_found": "找不到 qemu-img",
        "msg_export_format_choose": "Yes = Windows (.bat)\nNo = Linux/Shell (.sh)",
        "msg_script_exported": "脚本已导出:\n{}",
        "msg_mikan_format": "请选择 .mikan 格式",
        "msg_history_no_entries": "没有找到 '{}' 的历史配置",
        "msg_history_restore": "将恢复配置 '{}' 的历史版本？\n\n当前配置将被覆盖。",
        "msg_history_restored": "已恢复历史配置",
        "msg_history_select": "请选择一个历史配置",
        "msg_history_restore_failed": "恢复失败",
        "msg_disk_manager_disabled": "磁盘管理器功能已集成到高级选项和自定义硬件中",
        "msg_snapshot_disabled": "快照功能已集成到高级选项中",
        "custom_hw_title": "🔧 自定义硬件 - {}",
        "custom_hw_saved": "✅ 自定义硬件配置已保存",
        "footer": "v{} | {}",
        "history_title": "📜 历史配置 - {}",
        "history_restore_btn": "↩️ 恢复此配置",
        "history_entry": "[{}] {}",
        "perf_cpu_capacity": "CPU 容量",
        "perf_cpu_latency": "CPU 延迟",
        "perf_gpu_ram": "GPU 内存",
        "perf_gpu_freq": "GPU 频率",
        "perf_disk_cache": "磁盘缓存",
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
        "status_exporting": "📦 Exporting {}...",
        "status_export_done": "✅ Export successful ({:.1f} MB)",
        "status_export_failed": "❌ Export failed",
        "status_importing": "📥 Importing...",
        "status_import_done": "✅ Import successful: {}",
        "status_import_failed": "❌ Import failed",
        "status_export_script": "✅ Script exported",
        "status_converting": "🔄 Converting...",
        "status_convert_done": "✅ Conversion complete",
        "status_convert_failed": "❌ Conversion failed",
        "status_resizing": "📏 Resizing...",
        "status_resize_done": "✅ Resized to {} GB",
        "status_resize_failed": "❌ Resize failed",
        "status_detecting": "🔍 Detecting QEMU hardware...",
        "menu_help": "❓ Help",
        "menu_help_about": "📖 User Guide",
        "menu_view": "👁️ View",
        "menu_view_toolbar": "Show Toolbar",
        "menu_language": "🌐 Language",
        "menu_detect": "🔍 Detect",
        "menu_detect_hw": "🔍 Detect System Hardware",
        "btn_new": "New",
        "btn_edit": "Edit",
        "btn_delete": "Delete",
        "btn_export": "Export",
        "btn_export_as": "Export As",
        "btn_import": "Import",
        "btn_snapshot": "Snapshot",
        "btn_disk": "Disk",
        "btn_script": "Script",
        "btn_launch": "Launch",
        "btn_refresh": "Refresh",
        "btn_create": "Create",
        "btn_save": "Save",
        "btn_cancel": "Cancel",
        "btn_close": "Close",
        "btn_browse": "Browse",
        "btn_clear": "Clear",
        "btn_help": "Help",
        "btn_unlock": "Unlock Advanced",
        "btn_unlocked": "Unlocked",
        "btn_reset_adv": "Reset Default",
        "adv_title": "Advanced Options",
        "adv_locked": "🔒 Locked",
        "adv_unlocked": "🔓 Unlocked",
        "adv_warning": "⚠️ Incorrect advanced settings may cause VM boot failure!",
        "adv_unlock_warning": "⚠️ Advanced Debug Warning\n\nPlease backup important VM data before proceeding!\n\nThe author is not responsible for any issues!\n\nAre you sure you want to continue?",
        "adv_acknowledged": "Acknowledged",
        "adv_reset_confirm": "Reset all advanced options to official defaults. Continue?",
        "adv_reset_done": "Reset Complete",
        "adv_reset_ok": "All advanced options have been reset to official defaults",
        "tab_basic": "Basic",
        "tab_hardware": "Hardware",
        "tab_display": "Display/Sound",
        "tab_advanced": "Advanced",
        "tab_disk_adv": "Disk",
        "tab_network": "Network",
        "tab_cpu_adv": "CPU/Memory",
        "tab_display_adv": "Display",
        "tab_debug": "Debug",
        "tab_other": "Other",
        "tab_custom_hw": "Custom Hardware",
        "tab_performance": "Performance",
        "label_preset": "Preset:",
        "label_preset_desc": "💡 {}",
        "label_name": "Name:",
        "label_os_type": "OS Type:",
        "label_os_version": "OS Version:",
        "label_arch": "Architecture:",
        "label_memory": "Memory (MB):",
        "label_cpu_cores": "CPU Cores:",
        "label_cpu_threads": "CPU Threads:",
        "label_cpu_sockets": "CPU Sockets:",
        "label_disk_size": "Disk Size:",
        "label_disk_format": "Disk Format:",
        "label_disk_interface": "Disk Interface:",
        "label_cpu_model": "CPU Model:",
        "label_accel": "Acceleration:",
        "label_machine": "Machine Type:",
        "label_qemu_version": "QEMU Version:",
        "label_vga": "Graphics:",
        "label_display": "Display Backend:",
        "label_resolution": "Resolution:",
        "label_vnc_port": "VNC Port:",
        "label_sound": "Sound Card:",
        "label_nic": "Network Card:",
        "label_boot_order": "Boot Order:",
        "label_extra_args": "Extra Args:",
        "label_share_dir": "Share Directory:",
        "label_boot_iso": "Boot ISO:",
        "label_kernel_iso": "Kernel ISO:",
        "label_driver_iso": "Driver ISO:",
        "label_cpu_flags": "CPU Flags:",
        "label_numa": "NUMA Config:",
        "label_hostfwd": "Port Forwarding:",
        "label_subnet": "Custom Subnet:",
        "label_dns": "Custom DNS:",
        "label_tap": "TAP Interface:",
        "label_mac": "MAC Address:",
        "label_bios": "Custom BIOS:",
        "label_vnc_password": "VNC Password:",
        "label_spice_port": "SPICE Port:",
        "label_spice_password": "SPICE Password:",
        "label_log_file": "Log File:",
        "label_debug_level": "Debug Level:",
        "label_qmp_socket": "QMP Socket:",
        "label_rtc": "RTC Base Time:",
        "label_seed": "Fixed Seed:",
        "label_boot_once": "Boot Once:",
        "label_extra_adv": "Extra Advanced Args:",
        "label_cache": "Disk Cache:",
        "label_aio": "AIO Mode:",
        "label_discard": "TRIM Support:",
        "label_detect_zeroes": "Zero Detection:",
        "label_backing": "Backing File:",
        "label_cpu_vendor": "CPU Vendor:",
        "label_cpu_family": "CPU Family:",
        "label_cpu_model_id": "CPU Model ID:",
        "label_cpu_stepping": "CPU Stepping:",
        "label_cpu_level": "CPU Level:",
        "label_cpu_xlevel": "CPU XLevel:",
        "label_cpu_features": "CPU Features:",
        "label_cpu_capacity": "CPU Capacity (%):",
        "label_cpu_latency": "CPU Latency (µs):",
        "label_cpu_quota": "CPU Quota (%):",
        "label_cpu_period": "CPU Period (µs):",
        "label_gpu_model": "GPU Model:",
        "label_gpu_ram": "GPU RAM (MB):",
        "label_gpu_freq": "GPU Frequency (MHz):",
        "label_gpu_vgamem": "VGA Memory (MB):",
        "label_gpu_gl_version": "OpenGL Version:",
        "label_gpu_rendernode": "Render Node:",
        "label_gpu_edid": "EDID File:",
        "label_nic_model": "NIC Model:",
        "label_nic_queues": "NIC Queues:",
        "label_nic_mac": "MAC Address:",
        "label_storage_type": "Storage Type:",
        "label_storage_format": "Storage Format:",
        "label_cluster_size": "Cluster Size:",
        "label_audio_model": "Audio Model:",
        "label_audio_codec": "Audio Codec:",
        "label_usb_controller": "USB Controller:",
        "label_usb_ports": "USB Ports:",
        "label_pci_bus": "PCI Bus:",
        "label_pci_slot": "PCI Slot:",
        "label_serial": "Serial:",
        "label_parallel": "Parallel:",
        "label_firmware": "Firmware:",
        "label_rtc_mode": "RTC Mode:",
        "label_trace_events": "Trace Events:",
        "label_log_level": "Log Level:",
        "label_gdb_port": "GDB Port:",
        "label_chroot": "Chroot Path:",
        "label_security_user": "Security User:",
        "label_cpu_freq": "CPU Frequency (MHz):",
        "label_cpu_clock": "CPU Clock (MHz):",
        "check_acpi": "Enable ACPI",
        "check_usb": "Enable USB",
        "check_opengl": "Enable OpenGL Acceleration",
        "check_share": "Enable Shared Folder",
        "check_snapshot": "📸 Snapshot Mode (-snapshot)",
        "check_readonly": "🔒 Read-only Disk Mode",
        "check_net_restrict": "🚫 Restrict Network Access",
        "check_mem_prealloc": "📌 Pre-allocate all memory",
        "check_hugepages": "📌 Use Huge Pages (Linux)",
        "check_no_hpet": "⏱️ Disable HPET",
        "check_no_kvm_nested": "🚫 Disable KVM Nested",
        "check_force_tcg": "⚠️ Force TCG Mode",
        "check_usb_tablet": "🖱️ USB Tablet Mode (Absolute) ✅",
        "check_no_mouse": "🚫 Disable Mouse Integration",
        "check_monitor_stdio": "📟 Enable Monitor Console",
        "check_no_reboot": "🚫 No Reboot on Crash",
        "check_no_shutdown": "🚫 No Shutdown",
        "check_sandbox": "🔒 Sandbox Mode",
        "check_boot_menu": "📋 Show Boot Menu",
        "check_encryption": "🔐 Encrypted Storage",
        "check_compression": "📦 Compressed Storage",
        "check_selinux": "🔐 SELinux",
        "check_apparmor": "🔐 AppArmor",
        "check_gdb_stop": "🛑 Stop on GDB Connection",
        "disk_mgr_title": "💾 Virtual Disk Manager (Advanced) - {}",
        "disk_mgr_new": "📦 New",
        "disk_mgr_attach": "🔗 Attach Existing",
        "disk_mgr_detach": "⛓️Detach",
        "disk_mgr_properties": "📊 Properties",
        "disk_mgr_convert": "🔄 Convert",
        "disk_mgr_resize": "📏 Resize",
        "disk_mgr_no_disk": "No disks",
        "disk_mgr_count": "Total {} disks",
        "disk_mgr_created": "✅ Created: {}",
        "disk_mgr_attached": "✅ Attached: {}",
        "disk_mgr_detached": "⛓️Detached: {}",
        "snapshot_title": "📸 Snapshot Manager - {}",
        "snapshot_info": "📌 Snapshots backup the entire VM folder (disks + config)",
        "snapshot_create": "📸 Create",
        "snapshot_restore": "↩️ Restore",
        "snapshot_delete": "🗑️ Delete",
        "snapshot_no_snapshots": "(No snapshots)",
        "snapshot_create_title": "Create Snapshot",
        "snapshot_create_prompt": "Enter snapshot name:",
        "snapshot_restore_confirm": "Restore snapshot '{}'?\n\n⚠️ All current VM data will be overwritten!\nSnapshot size: {}\nThis action is irreversible!",
        "snapshot_delete_confirm": "Delete snapshot '{}'?\n\nSnapshot size: {}",
        "snapshot_created": "Snapshot '{}' created successfully!\n\nBacked up {} files",
        "snapshot_restored": "Snapshot '{}' restored successfully!",
        "snapshot_deleted": "Snapshot '{}' deleted",
        "error": "Error",
        "warning": "Warning",
        "info": "Info",
        "success": "Success",
        "confirm": "Confirm",
        "msg_select_vm": "Please select a VM first",
        "msg_name_empty": "Please enter a VM name",
        "msg_vm_exists": "VM '{}' already exists",
        "msg_vm_not_found": "VM not found",
        "msg_config_missing": "Config file not found",
        "msg_launcher_missing": "Launcher not found:\n{}\n\nPlease ensure launcher.py is in the same directory",
        "msg_launch_failed": "Launch failed:\n{}",
        "msg_export_confirm": "Export VM \"{}\" to:\n{}\n\nContinue?",
        "msg_import_confirm": "Import VM package:\n{}\n\nContinue?",
        "msg_overwrite_confirm": "VM \"{}\" already exists. Overwrite?",
        "msg_convert_confirm": "Current format: {}\nSelect target format:",
        "msg_resize_confirm": "Current size: {} GB\nEnter new size (GB):",
        "msg_create_disk_failed": "Create failed:\n{}",
        "msg_attach_disk_failed": "Attach failed:\n{}",
        "msg_detach_confirm": "Detach disk {}?",
        "msg_detach_system_confirm": "This is the system disk (first disk). Detaching may make VM unbootable.\n\nContinue?",
        "msg_qemu_img_not_found": "qemu-img not found",
        "msg_export_format_choose": "Yes = Windows (.bat)\nNo = Linux/Shell (.sh)",
        "msg_script_exported": "Script exported:\n{}",
        "msg_mikan_format": "Please select .mikan format",
        "msg_history_no_entries": "No history found for '{}'",
        "msg_history_restore": "Restore historical version of '{}'?\n\nCurrent configuration will be overwritten.",
        "msg_history_restored": "Historical configuration restored",
        "msg_history_select": "Please select a history entry",
        "msg_history_restore_failed": "Restore failed",
        "msg_disk_manager_disabled": "Disk Manager is integrated into Advanced Options and Custom Hardware",
        "msg_snapshot_disabled": "Snapshot feature is integrated into Advanced Options",
        "custom_hw_title": "🔧 Custom Hardware - {}",
        "custom_hw_saved": "✅ Custom hardware configuration saved",
        "footer": "v{} | {}",
        "history_title": "📜 History - {}",
        "history_restore_btn": "↩️ Restore This Config",
        "history_entry": "[{}] {}",
        "perf_cpu_capacity": "CPU Capacity",
        "perf_cpu_latency": "CPU Latency",
        "perf_gpu_ram": "GPU RAM",
        "perf_gpu_freq": "GPU Frequency",
        "perf_disk_cache": "Disk Cache",
        "custom_hw_cpu": "🖥️ CPU",
        "custom_hw_gpu": "🎮 GPU",
        "custom_hw_network": "🌐 Network",
        "custom_hw_storage": "💾 Storage",
        "custom_hw_other": "🔌 Other Hardware",
        "custom_hw_performance": "⚡ Performance",
        "custom_hw_security": "🔒 Security/Debug",
        "msg_custom_hw": "🔧 Click the 'Custom Hardware' button to open the full hardware configuration panel",
        "label_gpu_edid_browse": "Select EDID File",
        "label_bios_browse": "Select BIOS File",
    }
}

# ========== 翻译器 ==========
class Translator:
    _instance = None
    _current_lang = "zh_CN"
    _lang_data = LANGUAGES
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def set_language(self, lang_code: str):
        if lang_code in self._lang_data:
            self._current_lang = lang_code
            try:
                with open(CONFIG_DIR / "lang.json", 'w', encoding='utf-8') as f:
                    json.dump({"language": lang_code}, f)
            except:
                pass
        self.update_ui()
    
    def update_ui(self):
        if hasattr(self, '_main_window') and self._main_window:
            self._main_window.refresh_ui_texts()
    
    def set_main_window(self, window):
        self._main_window = window
    
    def get_language(self) -> str:
        return self._current_lang
    
    def tr(self, key: str, *args) -> str:
        text = self._lang_data.get(self._current_lang, {}).get(key, key)
        if args:
            try:
                return text.format(*args)
            except:
                return text
        return text
    
    def get_languages(self) -> Dict[str, str]:
        return {code: data.get("name", code) for code, data in self._lang_data.items()}

def tr(key: str, *args) -> str:
    return Translator().tr(key, *args)

# ========== 系统检测（新增） ==========
class SystemDetector:
    """检测系统硬件信息"""
    
    @staticmethod
    def get_system_info() -> dict:
        """获取完整系统信息"""
        info = {
            "操作系统": platform.system() + " " + platform.release(),
            "系统版本": platform.version(),
            "架构": platform.machine(),
            "处理器": platform.processor() or "未知",
            "主机名": socket.gethostname(),
            "Python版本": platform.python_version(),
            "CPU核心数": os.cpu_count() or "未知",
        }
        
        # 内存信息
        try:
            vm = psutil.virtual_memory()
            info["总内存"] = f"{vm.total / (1024**3):.1f} GB"
            info["可用内存"] = f"{vm.available / (1024**3):.1f} GB"
            info["内存使用率"] = f"{vm.percent}%"
        except:
            pass
        
        # CPU信息
        try:
            cpu_percent = psutil.cpu_percent(interval=0.5)
            info["CPU使用率"] = f"{cpu_percent}%"
        except:
            pass
        
        # 磁盘信息
        try:
            disk = psutil.disk_usage(str(BASE_DIR))
            info["磁盘总量"] = f"{disk.total / (1024**3):.1f} GB"
            info["磁盘可用"] = f"{disk.free / (1024**3):.1f} GB"
        except:
            pass
        
        # 操作系统详细信息
        if sys.platform == "win32":
            info["系统"] = "Windows"
            # Hyper-V检测
            try:
                result = subprocess.run(
                    ["systeminfo"], capture_output=True, text=True, encoding='utf-8', errors='ignore',
                    timeout=15
                )
                if "Hyper-V" in result.stdout:
                    info["Hyper-V"] = "✅ 已启用"
                else:
                    info["Hyper-V"] = "❌ 未启用"
            except:
                info["Hyper-V"] = "未知"
            
            # WHPX检测
            try:
                result = subprocess.run(
                    ["reg", "query", "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Virtualization"],
                    capture_output=True, text=True, encoding='utf-8', errors='ignore',
                    timeout=5
                )
                if result.returncode == 0:
                    info["WHPX"] = "✅ 已支持"
                else:
                    info["WHPX"] = "❌ 未支持"
            except:
                info["WHPX"] = "未知"
            
            # HAXM检测
            try:
                result = subprocess.run(
                    ["sc", "query", "haxm"], capture_output=True, text=True, encoding='utf-8', errors='ignore',
                    timeout=5
                )
                if "RUNNING" in result.stdout:
                    info["HAXM"] = "✅ 已启用"
                elif "STOPPED" in result.stdout:
                    info["HAXM"] = "⚠️ 已停止"
                else:
                    info["HAXM"] = "❌ 未安装"
            except:
                info["HAXM"] = "未知"
        
        elif sys.platform == "linux":
            info["系统"] = "Linux"
            try:
                if Path("/dev/kvm").exists():
                    info["KVM"] = "✅ 已支持"
                else:
                    info["KVM"] = "❌ 未支持"
            except:
                info["KVM"] = "未知"
        
        elif sys.platform == "darwin":
            info["系统"] = "macOS"
            try:
                result = subprocess.run(
                    ["sysctl", "kern.hv_support"],
                    capture_output=True, text=True, encoding='utf-8', errors='ignore',
                    timeout=5
                )
                if "1" in result.stdout:
                    info["Hypervisor.framework"] = "✅ 已支持"
                else:
                    info["Hypervisor.framework"] = "❌ 未支持"
            except:
                info["Hypervisor.framework"] = "未知"
        
        return info
    
    @staticmethod
    def get_qemu_supported_hardware() -> dict:
        """获取QEMU支持的硬件信息"""
        detector = QEMUHardwareDetector()
        hardware_info = {
            "QEMU版本": [],
            "可用加速器": [],
            "支持CPU型号": [],
            "支持显卡": [],
            "支持机器类型": [],
            "支持网络设备": [],
            "支持音频设备": [],
            "支持USB设备": [],
            "支持固件": [],
        }
        
        for ver_name, ver_info in detector.qemu_versions.items():
            info = ver_info["info"]
            hardware_info["QEMU版本"].append({
                "版本": ver_name,
                "路径": ver_info["path"],
                "信息": info.get("version", "未知")
            })
            
            # 合并所有硬件支持
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
            
            for item in info.get("firmware_types", []):
                if item not in hardware_info["支持固件"]:
                    hardware_info["支持固件"].append(item)
        
        return hardware_info

# ========== 配置选项数据 ==========
DISK_INTERFACES = ["ide", "sata", "virtio", "scsi", "nvme", "usb", "sd", "floppy"]
DISK_FORMATS = ["qcow2", "raw", "vmdk", "vdi", "vhdx", "qcow", "cow", "parallels", "dmg", "bochs", "cloop", "luks", "qed", "vpc", "vvfat"]
MACHINE_TYPES = ["pc", "q35", "pc-i440fx-11.1", "pc-i440fx-9.2", "pc-q35-11.1", "pc-q35-9.2", "virt", "microvm"]
CPU_MODELS = ["host", "qemu64", "qemu32", "core2duo", "Nehalem", "Westmere", "SandyBridge", "Haswell", "Broadwell", "Skylake-Client", "EPYC"]
ACCEL_MODES = ["tcg", "hax", "whpx", "kvm", "hvf", "qtest", "none"]
VGA_TYPES = ["virtio", "std", "cirrus", "vmvga", "qxl", "none", "bochs", "ramfb", "sga"]
DISPLAY_TYPES = ["gtk", "sdl", "none", "curses", "spice", "egl-headless"]
SOUND_TYPES = ["hda", "ac97", "sb16", "ich9-intel-hda", "none", "cs4231a", "gus", "intel-hda", "isa", "pcspk", "pl041"]
NIC_TYPES = ["virtio", "e1000", "rtl8139", "pcnet", "e1000e", "vmxnet3", "usb-net", "ne2k_pci"]
BOOT_TYPES = ["cdrom", "disk", "floppy", "network", "memtest"]
RESOLUTIONS = ["自定义", "640x480", "800x600", "1024x768", "1280x720", "1366x768", "1600x900", "1920x1080", "2560x1440", "3840x2160"]

# ========== 系统预设 ==========
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

# ========== QEMU 版本信息 ==========
QEMU_VERSIONS_INFO = {
    "qemu-w64-setup-2016": {"year": 2016, "arch": "x86_64", "desc": "XP/7 专用"},
    "qemu-w64-setup-20190815": {"year": 2019, "arch": "x86_64", "desc": "过渡版，Android/8.1"},
    "qemu-w64-setup-20251224": {"year": 2025, "arch": "x86_64", "desc": "最新版，Win10/11"},
}

def get_qemu_version_info(version: str) -> dict:
    for key, info in QEMU_VERSIONS_INFO.items():
        if key in version or version in key:
            return info
    return {"year": 2020, "arch": "x86_64", "desc": "未知版本"}

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

def find_qemu_img() -> Optional[Path]:
    for ver_dir in BASE_DIR.glob("qemu-*"):
        for name in ["qemu-img.exe", "qemu-img"]:
            qemu_img = ver_dir / name
            if qemu_img.exists():
                return qemu_img
    for cmd in ["qemu-img", "qemu-img.exe"]:
        result = subprocess.run(["where" if sys.platform == "win32" else "which", cmd], 
                               capture_output=True, text=True, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            path = result.stdout.strip().split('\n')[0]
            if path and Path(path).exists():
                return Path(path)
    return None

# ========== 历史配置保存 ==========
class ConfigHistory:
    def __init__(self):
        self.history_file = CONFIG_DIR / "history.json"
        self.history: Dict[str, List[Dict]] = defaultdict(list)
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
    
    def add_entry(self, vm_name: str, config: Dict):
        if vm_name not in self.history:
            self.history[vm_name] = []
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "config": config
        }
        self.history[vm_name].insert(0, entry)
        self.history[vm_name] = self.history[vm_name][:self.max_entries]
        self.save()
    
    def get_history(self, vm_name: str) -> List[Dict]:
        return self.history.get(vm_name, [])
    
    def clear_history(self, vm_name: str):
        if vm_name in self.history:
            del self.history[vm_name]
            self.save()
    
    def restore_entry(self, vm_name: str, index: int) -> Optional[Dict]:
        history = self.get_history(vm_name)
        if 0 <= index < len(history):
            return history[index]["config"]
        return None

# ========== 虚拟机配置类 ==========
class VMConfig:
    def __init__(self, name: str = ""):
        self.name = name
        self.vm_dir = VMS_DIR / name
        self.os_type = "Windows"
        self.os_version = "10"
        self.arch = "x86_64"
        self.memory = 4096
        self.cpu = 4
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
        self.accel = "hax"
        self.vga = "virtio"
        self.display = "gtk"
        self.resolution = "1920x1080"
        self.machine_type = "q35"
        self.acpi = True
        self.usb = True
        self.sound = "hda"
        self.boot_order = "cdrom"
        self.opengl = True
        self.nic_model = "virtio"
        self.qemu_version = "qemu-w64-setup-20251224"
        self.preset = "Windows 10"
        self.extra_args = ""
        self.no_hpet = False
        self.no_kvm = False
        self.vnc_port = ""
        self.smp_threads = 1
        self.smp_sockets = 1
        self.share_enabled = False
        self.share_dir = ""
        
        # 高级选项
        self.cache = "writeback"
        self.aio = "默认"
        self.discard = "默认"
        self.detect_zeroes = "默认"
        self.backing_file = ""
        self.snapshot_mode = False
        self.disk_readonly = False
        self.hostfwd = ""
        self.net_subnet = ""
        self.net_dns = ""
        self.net_restrict = False
        self.tap_interface = ""
        self.mac_address = ""
        self.cpu_flags = ""
        self.numa_config = ""
        self.mem_prealloc = False
        self.hugepages = False
        self.no_hpet_adv = False
        self.no_kvm_nested = False
        self.force_tcg = False
        self.usb_tablet = True
        self.bios_file = ""
        self.vnc_password = ""
        self.spice_port = ""
        self.spice_password = ""
        self.no_mouse_integration = False
        self.log_file = ""
        self.debug_level = "默认"
        self.qmp_socket = ""
        self.monitor_stdio = False
        self.no_reboot = False
        self.no_shutdown = False
        self.sandbox = False
        self.rtc_base = ""
        self.seed_value = ""
        self.boot_menu = False
        self.boot_once = ""
        self.extra_advanced_args = ""
        
        # 自定义硬件
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
        self.custom_bios = ""
        self.custom_firmware = ""
        self.custom_rtc = "utc"
        
        # 性能
        self.cpu_capacity = 100
        self.cpu_latency = 10
        self.cpu_quota = 0
        self.cpu_period = 100000
        self.gpu_edid = ""
        self.gpu_rendernode = ""
        self.gpu_gl_version = "3.3"
        self.cpu_freq = 0
        self.cpu_clock = 0
        
        # 存储
        self.storage_type = "file"
        self.storage_format = "qcow2"
        self.storage_encryption = False
        self.storage_encryption_key = ""
        self.storage_compression = False
        self.storage_cluster_size = 65536
        
        # 安全
        self.security_selinux = False
        self.security_apparmor = False
        self.security_chroot = ""
        self.security_user = ""
        
        # 调试
        self.trace_events = ""
        self.log_level = 0
        self.gdb_port = 1234
        self.gdb_stop = False
    
    def add_disk(self, path: str, size_gb: int, format_type: str = "qcow2", 
                 interface: str = "sata", cache: str = "writeback", 
                 backing_file: str = "", readonly: bool = False, 
                 removable: bool = False) -> Dict:
        self.disk_id_counter += 1
        disk = {
            "id": self.disk_id_counter,
            "path": path,
            "size": size_gb,
            "format": format_type,
            "interface": interface,
            "cache": cache,
            "backing_file": backing_file,
            "readonly": readonly,
            "removable": removable
        }
        self.disks.append(disk)
        if len(self.disks) == 1:
            self.disk_path = path
            self.disk_size = size_gb
            self.disk_format = format_type
            self.disk_interface = interface
        return disk
    
    def remove_disk(self, disk_id: int):
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
    
    def get_disk(self, disk_id: int) -> Optional[Dict]:
        for d in self.disks:
            if d["id"] == disk_id:
                return d
        return None
    
    def to_dict(self) -> dict:
        return {
            "version": CONFIG_VERSION,
            "name": self.name,
            "os_type": self.os_type,
            "os_version": self.os_version,
            "arch": self.arch,
            "memory": self.memory,
            "cpu": self.cpu,
            "smp_threads": self.smp_threads,
            "smp_sockets": self.smp_sockets,
            "disk_size": self.disk_size,
            "disk_format": self.disk_format,
            "disk_interface": self.disk_interface,
            "disk_path": self.disk_path,
            "disks": self.disks,
            "disk_id_counter": self.disk_id_counter,
            "boot_iso": self.boot_iso,
            "kernel_iso": self.kernel_iso,
            "driver_iso": self.driver_iso,
            "created": self.created,
            "cpu_model": self.cpu_model,
            "accel": self.accel,
            "vga": self.vga,
            "display": self.display,
            "resolution": self.resolution,
            "machine_type": self.machine_type,
            "acpi": self.acpi,
            "usb": self.usb,
            "sound": self.sound,
            "boot_order": self.boot_order,
            "opengl": self.opengl,
            "nic_model": self.nic_model,
            "qemu_version": self.qemu_version,
            "preset": self.preset,
            "extra_args": self.extra_args,
            "no_hpet": self.no_hpet,
            "no_kvm": self.no_kvm,
            "vnc_port": self.vnc_port,
            "share_enabled": self.share_enabled,
            "share_dir": self.share_dir,
            "cache": self.cache,
            "aio": self.aio,
            "discard": self.discard,
            "detect_zeroes": self.detect_zeroes,
            "backing_file": self.backing_file,
            "snapshot_mode": self.snapshot_mode,
            "disk_readonly": self.disk_readonly,
            "hostfwd": self.hostfwd,
            "net_subnet": self.net_subnet,
            "net_dns": self.net_dns,
            "net_restrict": self.net_restrict,
            "tap_interface": self.tap_interface,
            "mac_address": self.mac_address,
            "cpu_flags": self.cpu_flags,
            "numa_config": self.numa_config,
            "mem_prealloc": self.mem_prealloc,
            "hugepages": self.hugepages,
            "no_hpet_adv": self.no_hpet_adv,
            "no_kvm_nested": self.no_kvm_nested,
            "force_tcg": self.force_tcg,
            "usb_tablet": self.usb_tablet,
            "bios_file": self.bios_file,
            "vnc_password": self.vnc_password,
            "spice_port": self.spice_port,
            "spice_password": self.spice_password,
            "no_mouse_integration": self.no_mouse_integration,
            "log_file": self.log_file,
            "debug_level": self.debug_level,
            "qmp_socket": self.qmp_socket,
            "monitor_stdio": self.monitor_stdio,
            "no_reboot": self.no_reboot,
            "no_shutdown": self.no_shutdown,
            "sandbox": self.sandbox,
            "rtc_base": self.rtc_base,
            "seed_value": self.seed_value,
            "boot_menu": self.boot_menu,
            "boot_once": self.boot_once,
            "extra_advanced_args": self.extra_advanced_args,
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
            "custom_bios": self.custom_bios,
            "custom_firmware": self.custom_firmware,
            "custom_rtc": self.custom_rtc,
            "cpu_capacity": self.cpu_capacity,
            "cpu_latency": self.cpu_latency,
            "cpu_quota": self.cpu_quota,
            "cpu_period": self.cpu_period,
            "gpu_edid": self.gpu_edid,
            "gpu_rendernode": self.gpu_rendernode,
            "gpu_gl_version": self.gpu_gl_version,
            "cpu_freq": self.cpu_freq,
            "cpu_clock": self.cpu_clock,
            "storage_type": self.storage_type,
            "storage_format": self.storage_format,
            "storage_encryption": self.storage_encryption,
            "storage_encryption_key": self.storage_encryption_key,
            "storage_compression": self.storage_compression,
            "storage_cluster_size": self.storage_cluster_size,
            "security_selinux": self.security_selinux,
            "security_apparmor": self.security_apparmor,
            "security_chroot": self.security_chroot,
            "security_user": self.security_user,
            "trace_events": self.trace_events,
            "log_level": self.log_level,
            "gdb_port": self.gdb_port,
            "gdb_stop": self.gdb_stop,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'VMConfig':
        vm = cls(data.get("name", ""))
        vm.os_type = data.get("os_type", "Windows")
        vm.os_version = data.get("os_version", "10")
        vm.arch = data.get("arch", "x86_64")
        vm.memory = data.get("memory", 4096)
        vm.cpu = data.get("cpu", 4)
        vm.smp_threads = data.get("smp_threads", 1)
        vm.smp_sockets = data.get("smp_sockets", 1)
        vm.disk_size = data.get("disk_size", 64)
        vm.disk_format = data.get("disk_format", "qcow2")
        vm.disk_interface = data.get("disk_interface", "sata")
        vm.disk_path = data.get("disk_path", "")
        vm.disks = data.get("disks", [])
        vm.disk_id_counter = data.get("disk_id_counter", 0)
        vm.boot_iso = data.get("boot_iso", "")
        vm.kernel_iso = data.get("kernel_iso", "")
        vm.driver_iso = data.get("driver_iso", "")
        vm.created = data.get("created", "")
        vm.cpu_model = data.get("cpu_model", "host")
        vm.accel = data.get("accel", "hax")
        vm.vga = data.get("vga", "virtio")
        vm.display = data.get("display", "gtk")
        vm.resolution = data.get("resolution", "1920x1080")
        vm.machine_type = data.get("machine_type", "q35")
        vm.acpi = data.get("acpi", True)
        vm.usb = data.get("usb", True)
        vm.sound = data.get("sound", "hda")
        vm.boot_order = data.get("boot_order", "cdrom")
        vm.opengl = data.get("opengl", True)
        vm.nic_model = data.get("nic_model", "virtio")
        vm.qemu_version = data.get("qemu_version", "qemu-w64-setup-20251224")
        vm.preset = data.get("preset", "Windows 10")
        vm.extra_args = data.get("extra_args", "")
        vm.no_hpet = data.get("no_hpet", False)
        vm.no_kvm = data.get("no_kvm", False)
        vm.vnc_port = data.get("vnc_port", "")
        vm.share_enabled = data.get("share_enabled", False)
        vm.share_dir = data.get("share_dir", "")
        vm.cache = data.get("cache", "writeback")
        vm.aio = data.get("aio", "默认")
        vm.discard = data.get("discard", "默认")
        vm.detect_zeroes = data.get("detect_zeroes", "默认")
        vm.backing_file = data.get("backing_file", "")
        vm.snapshot_mode = data.get("snapshot_mode", False)
        vm.disk_readonly = data.get("disk_readonly", False)
        vm.hostfwd = data.get("hostfwd", "")
        vm.net_subnet = data.get("net_subnet", "")
        vm.net_dns = data.get("net_dns", "")
        vm.net_restrict = data.get("net_restrict", False)
        vm.tap_interface = data.get("tap_interface", "")
        vm.mac_address = data.get("mac_address", "")
        vm.cpu_flags = data.get("cpu_flags", "")
        vm.numa_config = data.get("numa_config", "")
        vm.mem_prealloc = data.get("mem_prealloc", False)
        vm.hugepages = data.get("hugepages", False)
        vm.no_hpet_adv = data.get("no_hpet_adv", False)
        vm.no_kvm_nested = data.get("no_kvm_nested", False)
        vm.force_tcg = data.get("force_tcg", False)
        vm.usb_tablet = data.get("usb_tablet", True)
        vm.bios_file = data.get("bios_file", "")
        vm.vnc_password = data.get("vnc_password", "")
        vm.spice_port = data.get("spice_port", "")
        vm.spice_password = data.get("spice_password", "")
        vm.no_mouse_integration = data.get("no_mouse_integration", False)
        vm.log_file = data.get("log_file", "")
        vm.debug_level = data.get("debug_level", "默认")
        vm.qmp_socket = data.get("qmp_socket", "")
        vm.monitor_stdio = data.get("monitor_stdio", False)
        vm.no_reboot = data.get("no_reboot", False)
        vm.no_shutdown = data.get("no_shutdown", False)
        vm.sandbox = data.get("sandbox", False)
        vm.rtc_base = data.get("rtc_base", "")
        vm.seed_value = data.get("seed_value", "")
        vm.boot_menu = data.get("boot_menu", False)
        vm.boot_once = data.get("boot_once", "")
        vm.extra_advanced_args = data.get("extra_advanced_args", "")
        vm.custom_cpu_vendor = data.get("custom_cpu_vendor", "AuthenticAMD")
        vm.custom_cpu_family = data.get("custom_cpu_family", "6")
        vm.custom_cpu_model_id = data.get("custom_cpu_model_id", "94")
        vm.custom_cpu_stepping = data.get("custom_cpu_stepping", "3")
        vm.custom_cpu_level = data.get("custom_cpu_level", "0x1")
        vm.custom_cpu_xlevel = data.get("custom_cpu_xlevel", "0x80000008")
        vm.custom_cpu_features = data.get("custom_cpu_features", "+aes,+avx,+avx2,+bmi1,+bmi2,+f16c,+fma,+rdrand,+rdseed,+sha-ni,+xsave,+xsavec,+xsaves")
        vm.custom_gpu_model = data.get("custom_gpu_model", "virtio-vga-gl")
        vm.custom_gpu_ram = data.get("custom_gpu_ram", 256)
        vm.custom_gpu_freq = data.get("custom_gpu_freq", 800)
        vm.custom_gpu_vgamem = data.get("custom_gpu_vgamem", 64)
        vm.custom_nic_model = data.get("custom_nic_model", "virtio-net-pci")
        vm.custom_nic_mac = data.get("custom_nic_mac", "")
        vm.custom_nic_queues = data.get("custom_nic_queues", 1)
        vm.custom_disk_cache = data.get("custom_disk_cache", "writeback")
        vm.custom_disk_aio = data.get("custom_disk_aio", "native")
        vm.custom_disk_discard = data.get("custom_disk_discard", "unmap")
        vm.custom_disk_detect_zeroes = data.get("custom_disk_detect_zeroes", "unmap")
        vm.custom_disk_latency = data.get("custom_disk_latency", 0)
        vm.custom_audio_model = data.get("custom_audio_model", "ich9-intel-hda")
        vm.custom_audio_codec = data.get("custom_audio_codec", "hda-duplex")
        vm.custom_usb_controller = data.get("custom_usb_controller", "usb-ehci")
        vm.custom_usb_ports = data.get("custom_usb_ports", 6)
        vm.custom_pci_bus = data.get("custom_pci_bus", "pcie.0")
        vm.custom_pci_slot = data.get("custom_pci_slot", 0)
        vm.custom_serial = data.get("custom_serial", "pty")
        vm.custom_parallel = data.get("custom_parallel", "none")
        vm.custom_bios = data.get("custom_bios", "")
        vm.custom_firmware = data.get("custom_firmware", "")
        vm.custom_rtc = data.get("custom_rtc", "utc")
        vm.cpu_capacity = data.get("cpu_capacity", 100)
        vm.cpu_latency = data.get("cpu_latency", 10)
        vm.cpu_quota = data.get("cpu_quota", 0)
        vm.cpu_period = data.get("cpu_period", 100000)
        vm.gpu_edid = data.get("gpu_edid", "")
        vm.gpu_rendernode = data.get("gpu_rendernode", "")
        vm.gpu_gl_version = data.get("gpu_gl_version", "3.3")
        vm.cpu_freq = data.get("cpu_freq", 0)
        vm.cpu_clock = data.get("cpu_clock", 0)
        vm.storage_type = data.get("storage_type", "file")
        vm.storage_format = data.get("storage_format", "qcow2")
        vm.storage_encryption = data.get("storage_encryption", False)
        vm.storage_encryption_key = data.get("storage_encryption_key", "")
        vm.storage_compression = data.get("storage_compression", False)
        vm.storage_cluster_size = data.get("storage_cluster_size", 65536)
        vm.security_selinux = data.get("security_selinux", False)
        vm.security_apparmor = data.get("security_apparmor", False)
        vm.security_chroot = data.get("security_chroot", "")
        vm.security_user = data.get("security_user", "")
        vm.trace_events = data.get("trace_events", "")
        vm.log_level = data.get("log_level", 0)
        vm.gdb_port = data.get("gdb_port", 1234)
        vm.gdb_stop = data.get("gdb_stop", False)
        return vm

# ========== 自定义硬件对话框 ==========
class CustomHardwareDialog(QDialog):
    def __init__(self, vm: VMConfig, parent=None):
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
        
        # CPU
        cpu_tab = self.create_cpu_custom_tab()
        self.tab_widget.addTab(cpu_tab, tr("custom_hw_cpu"))
        
        # GPU
        gpu_tab = self.create_gpu_custom_tab()
        self.tab_widget.addTab(gpu_tab, tr("custom_hw_gpu"))
        
        # 网络
        net_tab = self.create_net_custom_tab()
        self.tab_widget.addTab(net_tab, tr("custom_hw_network"))
        
        # 存储
        storage_tab = self.create_storage_custom_tab()
        self.tab_widget.addTab(storage_tab, tr("custom_hw_storage"))
        
        # 其他硬件
        hw_tab = self.create_hw_custom_tab()
        self.tab_widget.addTab(hw_tab, tr("custom_hw_other"))
        
        # 性能
        perf_tab = self.create_perf_custom_tab()
        self.tab_widget.addTab(perf_tab, tr("custom_hw_performance"))
        
        # 安全
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
        layout.addWidget(QLabel(tr("label_cpu_stepping")), row, 0)
        self.cpu_stepping = QLineEdit()
        layout.addWidget(self.cpu_stepping, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_cpu_level")), row, 0)
        self.cpu_level = QLineEdit()
        layout.addWidget(self.cpu_level, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_cpu_xlevel")), row, 0)
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
        layout.addWidget(QLabel(tr("label_cpu_quota")), row, 0)
        self.cpu_quota = QSpinBox()
        self.cpu_quota.setRange(0, 200)
        self.cpu_quota.setSuffix("%")
        layout.addWidget(self.cpu_quota, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_cpu_period")), row, 0)
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
        layout.addWidget(QLabel(tr("label_gpu_freq")), row, 0)
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
        layout.addWidget(QLabel(tr("label_gpu_gl_version")), row, 0)
        self.gpu_gl_version = QComboBox()
        self.gpu_gl_version.addItems(["3.3", "3.0", "2.1", "4.6", "4.5"])
        layout.addWidget(self.gpu_gl_version, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_gpu_rendernode")), row, 0)
        self.gpu_rendernode = QLineEdit()
        self.gpu_rendernode.setPlaceholderText("/dev/dri/renderD128")
        layout.addWidget(self.gpu_rendernode, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_gpu_edid")), row, 0)
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
        layout.addWidget(QLabel(tr("label_storage_type")), row, 0)
        self.storage_type = QComboBox()
        self.storage_type.addItems(["file", "block", "iscsi", "nbd", "gluster", "rbd", "ssh"])
        layout.addWidget(self.storage_type, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_storage_format")), row, 0)
        self.storage_format = QComboBox()
        self.storage_format.addItems(DISK_FORMATS)
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
        layout.addWidget(QLabel(tr("label_cluster_size")), row, 0)
        self.cluster_size = QSpinBox()
        self.cluster_size.setRange(4096, 2097152)
        self.cluster_size.setSingleStep(4096)
        self.cluster_size.setSuffix(" bytes")
        layout.addWidget(self.cluster_size, row, 1)
        
        row += 1
        self.encryption_check = QCheckBox(tr("check_encryption"))
        layout.addWidget(self.encryption_check, row, 0, 1, 2)
        
        row += 1
        self.compression_check = QCheckBox(tr("check_compression"))
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
        layout.addWidget(QLabel(tr("label_audio_codec")), row, 0)
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
        layout.addWidget(QLabel(tr("label_pci_bus")), row, 0)
        self.pci_bus = QLineEdit()
        self.pci_bus.setPlaceholderText("pcie.0")
        layout.addWidget(self.pci_bus, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_pci_slot")), row, 0)
        self.pci_slot = QSpinBox()
        self.pci_slot.setRange(0, 31)
        layout.addWidget(self.pci_slot, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_serial")), row, 0)
        self.serial = QComboBox()
        self.serial.addItems(["pty", "null", "stdio", "file", "tcp", "telnet", "none"])
        layout.addWidget(self.serial, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_parallel")), row, 0)
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
        layout.addWidget(QLabel(tr("label_firmware")), row, 0)
        self.firmware = QLineEdit()
        self.firmware.setPlaceholderText("UEFI.fd")
        layout.addWidget(self.firmware, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_rtc_mode")), row, 0)
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
        layout.addWidget(QLabel(tr("perf_cpu_capacity") + ":"), row, 0)
        self.perf_cpu_capacity = QSlider(Qt.Horizontal)
        self.perf_cpu_capacity.setRange(1, 200)
        self.perf_cpu_capacity.setValue(100)
        self.perf_cpu_capacity.setTickPosition(QSlider.TicksBelow)
        self.perf_cpu_capacity.setTickInterval(10)
        layout.addWidget(self.perf_cpu_capacity, row, 1)
        self.perf_cpu_capacity_label = QLabel("100%")
        layout.addWidget(self.perf_cpu_capacity_label, row, 2)
        self.perf_cpu_capacity.valueChanged.connect(lambda v: self.perf_cpu_capacity_label.setText(f"{v}%"))
        
        row += 1
        layout.addWidget(QLabel(tr("perf_cpu_latency") + ":"), row, 0)
        self.perf_cpu_latency = QSlider(Qt.Horizontal)
        self.perf_cpu_latency.setRange(0, 1000)
        self.perf_cpu_latency.setValue(10)
        self.perf_cpu_latency.setTickPosition(QSlider.TicksBelow)
        self.perf_cpu_latency.setTickInterval(50)
        layout.addWidget(self.perf_cpu_latency, row, 1)
        self.perf_cpu_latency_label = QLabel("10 µs")
        layout.addWidget(self.perf_cpu_latency_label, row, 2)
        self.perf_cpu_latency.valueChanged.connect(lambda v: self.perf_cpu_latency_label.setText(f"{v} µs"))
        
        row += 1
        layout.addWidget(QLabel(tr("perf_gpu_ram") + ":"), row, 0)
        self.perf_gpu_ram = QSlider(Qt.Horizontal)
        self.perf_gpu_ram.setRange(16, 4096)
        self.perf_gpu_ram.setValue(256)
        self.perf_gpu_ram.setTickPosition(QSlider.TicksBelow)
        self.perf_gpu_ram.setTickInterval(128)
        layout.addWidget(self.perf_gpu_ram, row, 1)
        self.perf_gpu_ram_label = QLabel("256 MB")
        layout.addWidget(self.perf_gpu_ram_label, row, 2)
        self.perf_gpu_ram.valueChanged.connect(lambda v: self.perf_gpu_ram_label.setText(f"{v} MB"))
        
        row += 1
        layout.addWidget(QLabel(tr("perf_gpu_freq") + ":"), row, 0)
        self.perf_gpu_freq = QSlider(Qt.Horizontal)
        self.perf_gpu_freq.setRange(100, 3000)
        self.perf_gpu_freq.setValue(800)
        self.perf_gpu_freq.setTickPosition(QSlider.TicksBelow)
        self.perf_gpu_freq.setTickInterval(100)
        layout.addWidget(self.perf_gpu_freq, row, 1)
        self.perf_gpu_freq_label = QLabel("800 MHz")
        layout.addWidget(self.perf_gpu_freq_label, row, 2)
        self.perf_gpu_freq.valueChanged.connect(lambda v: self.perf_gpu_freq_label.setText(f"{v} MHz"))
        
        row += 1
        layout.addWidget(QLabel(tr("perf_disk_cache") + ":"), row, 0)
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
        self.selinux_check = QCheckBox(tr("check_selinux"))
        layout.addWidget(self.selinux_check, row, 0, 1, 2)
        
        row += 1
        self.apparmor_check = QCheckBox(tr("check_apparmor"))
        layout.addWidget(self.apparmor_check, row, 0, 1, 2)
        
        row += 1
        layout.addWidget(QLabel(tr("label_chroot")), row, 0)
        self.chroot = QLineEdit()
        self.chroot.setPlaceholderText("/path/to/chroot")
        layout.addWidget(self.chroot, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_security_user")), row, 0)
        self.security_user = QLineEdit()
        self.security_user.setPlaceholderText("user")
        layout.addWidget(self.security_user, row, 1)
        
        row += 1
        self.sandbox_check = QCheckBox(tr("check_sandbox"))
        layout.addWidget(self.sandbox_check, row, 0, 1, 2)
        
        row += 1
        layout.addWidget(QLabel(tr("label_trace_events")), row, 0)
        self.trace_events = QLineEdit()
        self.trace_events.setPlaceholderText("qemu_system_reset,usb_packet")
        layout.addWidget(self.trace_events, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_log_level")), row, 0)
        self.log_level = QSpinBox()
        self.log_level.setRange(0, 10)
        layout.addWidget(self.log_level, row, 1)
        
        row += 1
        layout.addWidget(QLabel(tr("label_gdb_port")), row, 0)
        self.gdb_port = QSpinBox()
        self.gdb_port.setRange(1, 65535)
        self.gdb_port.setValue(1234)
        layout.addWidget(self.gdb_port, row, 1)
        
        row += 1
        self.gdb_stop_check = QCheckBox(tr("check_gdb_stop"))
        layout.addWidget(self.gdb_stop_check, row, 0, 1, 2)
        
        layout.setRowStretch(row + 1, 1)
        return widget
    
    def browse_edid(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("label_gpu_edid_browse"), str(BASE_DIR), "EDID 文件 (*.bin);;所有文件 (*)")
        if path:
            self.gpu_edid.setText(path)
    
    def browse_bios(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("label_bios_browse"), str(BASE_DIR), "BIOS 文件 (*.bin *.rom);;所有文件 (*)")
        if path:
            self.bios.setText(path)
    
    def load_data(self):
        vm = self.vm
        # CPU
        self.cpu_vendor.setCurrentText(vm.custom_cpu_vendor)
        self.cpu_family.setText(vm.custom_cpu_family)
        self.cpu_model_id.setText(vm.custom_cpu_model_id)
        self.cpu_stepping.setText(vm.custom_cpu_stepping)
        self.cpu_level.setText(vm.custom_cpu_level)
        self.cpu_xlevel.setText(vm.custom_cpu_xlevel)
        self.cpu_features.setText(vm.custom_cpu_features)
        self.cpu_capacity.setValue(vm.cpu_capacity)
        self.cpu_latency.setValue(vm.cpu_latency)
        self.cpu_quota.setValue(vm.cpu_quota)
        self.cpu_period.setValue(vm.cpu_period)
        # GPU
        self.gpu_model.setCurrentText(vm.custom_gpu_model)
        self.gpu_ram.setValue(vm.custom_gpu_ram)
        self.gpu_freq.setValue(vm.custom_gpu_freq)
        self.gpu_vgamem.setValue(vm.custom_gpu_vgamem)
        self.gpu_gl_version.setCurrentText(vm.gpu_gl_version)
        self.gpu_rendernode.setText(vm.gpu_rendernode)
        self.gpu_edid.setText(vm.gpu_edid)
        self.gpu_opengl_check.setChecked(vm.opengl)
        # 网络
        self.nic_model.setCurrentText(vm.custom_nic_model)
        self.nic_queues.setValue(vm.custom_nic_queues)
        self.nic_mac.setText(vm.custom_nic_mac)
        self.hostfwd.setText(vm.hostfwd)
        self.net_subnet.setText(vm.net_subnet)
        self.net_dns.setText(vm.net_dns)
        self.tap_interface.setText(vm.tap_interface)
        self.net_restrict_check.setChecked(vm.net_restrict)
        # 存储
        self.storage_type.setCurrentText(vm.storage_type)
        self.storage_format.setCurrentText(vm.storage_format)
        self.disk_cache.setCurrentText(vm.custom_disk_cache)
        self.disk_aio.setCurrentText(vm.custom_disk_aio)
        self.disk_discard.setCurrentText(vm.custom_disk_discard)
        self.disk_detect_zeroes.setCurrentText(vm.custom_disk_detect_zeroes)
        self.cluster_size.setValue(vm.storage_cluster_size)
        self.encryption_check.setChecked(vm.storage_encryption)
        self.compression_check.setChecked(vm.storage_compression)
        # 其他硬件
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
        # 性能
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
        # 安全
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
        # CPU
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
        # GPU
        vm.custom_gpu_model = self.gpu_model.currentText()
        vm.custom_gpu_ram = self.gpu_ram.value()
        vm.custom_gpu_freq = self.gpu_freq.value()
        vm.custom_gpu_vgamem = self.gpu_vgamem.value()
        vm.gpu_gl_version = self.gpu_gl_version.currentText()
        vm.gpu_rendernode = self.gpu_rendernode.text().strip()
        vm.gpu_edid = self.gpu_edid.text().strip()
        vm.opengl = self.gpu_opengl_check.isChecked()
        # 网络
        vm.custom_nic_model = self.nic_model.currentText()
        vm.custom_nic_queues = self.nic_queues.value()
        vm.custom_nic_mac = self.nic_mac.text().strip()
        vm.hostfwd = self.hostfwd.text().strip()
        vm.net_subnet = self.net_subnet.text().strip()
        vm.net_dns = self.net_dns.text().strip()
        vm.tap_interface = self.tap_interface.text().strip()
        vm.net_restrict = self.net_restrict_check.isChecked()
        # 存储
        vm.storage_type = self.storage_type.currentText()
        vm.storage_format = self.storage_format.currentText()
        vm.custom_disk_cache = self.disk_cache.currentText()
        vm.custom_disk_aio = self.disk_aio.currentText()
        vm.custom_disk_discard = self.disk_discard.currentText()
        vm.custom_disk_detect_zeroes = self.disk_detect_zeroes.currentText()
        vm.storage_cluster_size = self.cluster_size.value()
        vm.storage_encryption = self.encryption_check.isChecked()
        vm.storage_compression = self.compression_check.isChecked()
        # 其他硬件
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
        # 性能
        vm.cpu_capacity = self.perf_cpu_capacity.value()
        vm.cpu_latency = self.perf_cpu_latency.value()
        vm.custom_gpu_ram = self.perf_gpu_ram.value()
        vm.custom_gpu_freq = self.perf_gpu_freq.value()
        vm.custom_disk_cache = self.perf_disk_cache.currentText()
        vm.mem_prealloc = self.mem_prealloc_check.isChecked()
        vm.hugepages = self.hugepages_check.isChecked()
        # 安全
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
        QMessageBox.information(self, tr("success"), tr("custom_hw_saved"))
        self.accept()

# ========== 高级选项面板 ==========
class AdvancedOptionsWidget(QGroupBox):
    def __init__(self, parent=None):
        super().__init__(tr("adv_title"), parent)
        self.setChecked(False)
        self.warning_acknowledged = False
        self.parent_dialog = parent
        self._custom_hw_dialog = None
        self._vm_ref = None
        
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
            QPushButton {
                background-color: #FF8A9C;
                color: white;
                font-weight: bold;
                padding: 4px 16px;
                border-radius: 12px;
                font-size: 12px;
                border: none;
            }
            QPushButton:hover { background-color: #FF6B7A; }
        """)
        self.unlock_btn.clicked.connect(self.unlock_advanced)
        top_layout.addWidget(self.unlock_btn)
        main_layout.addLayout(top_layout)
        
        warning_label = QLabel(tr("adv_warning"))
        warning_label.setStyleSheet("""
            QLabel {
                background-color: #FFF3E0;
                color: #B85C00;
                padding: 3px 8px;
                border-radius: 10px;
                border: 1px solid #FFD1B3;
                font-size: 10px;
            }
        """)
        warning_label.setWordWrap(True)
        main_layout.addWidget(warning_label)
        
        self.adv_tabs = QTabWidget()
        self.adv_tabs.setTabPosition(QTabWidget.North)
        self.adv_tabs.setDocumentMode(True)
        self.adv_tabs.setEnabled(False)
        
        # 磁盘
        tab_disk = self.create_disk_tab()
        self.adv_tabs.addTab(tab_disk, tr("tab_disk_adv"))
        
        # 网络
        tab_network = self.create_network_tab()
        self.adv_tabs.addTab(tab_network, tr("tab_network"))
        
        # CPU
        tab_cpu = self.create_cpu_tab()
        self.adv_tabs.addTab(tab_cpu, tr("tab_cpu_adv"))
        
        # 显示
        tab_display = self.create_display_adv_tab()
        self.adv_tabs.addTab(tab_display, tr("tab_display_adv"))
        
        # 调试
        tab_debug = self.create_debug_tab()
        self.adv_tabs.addTab(tab_debug, tr("tab_debug"))
        
        # 其他
        tab_other = self.create_other_tab()
        self.adv_tabs.addTab(tab_other, tr("tab_other"))
        
        # 自定义硬件
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
                QPushButton {
                    background-color: #A8E6CF;
                    color: white;
                    font-weight: bold;
                    padding: 4px 16px;
                    border-radius: 12px;
                    font-size: 12px;
                    border: none;
                }
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
        self.no_hpet_adv_check = QCheckBox(tr("check_no_hpet"))
        grid.addWidget(self.no_hpet_adv_check, row, 0, 1, 2)
        
        row += 1
        self.no_kvm_nested_check = QCheckBox(tr("check_no_kvm_nested"))
        grid.addWidget(self.no_kvm_nested_check, row, 0, 1, 2)
        
        row += 1
        self.force_tcg_check = QCheckBox(tr("check_force_tcg"))
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
        self.usb_tablet_check = QCheckBox(tr("check_usb_tablet"))
        self.usb_tablet_check.setChecked(True)
        grid.addWidget(self.usb_tablet_check, row, 0, 1, 2)
        
        row += 1
        self.no_mouse_integration_check = QCheckBox(tr("check_no_mouse"))
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
        self.no_reboot_check = QCheckBox(tr("check_no_reboot"))
        grid.addWidget(self.no_reboot_check, row, 0, 1, 2)
        
        row += 1
        self.no_shutdown_check = QCheckBox(tr("check_no_shutdown"))
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
        self.boot_menu_check = QCheckBox(tr("check_boot_menu"))
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
        
        self.custom_hw_btn = QPushButton(tr("tab_custom_hw"))
        self.custom_hw_btn.setMinimumHeight(32)
        self.custom_hw_btn.setStyleSheet("""
            QPushButton {
                background-color: #D4A5FF;
                color: white;
                font-weight: bold;
                border-radius: 12px;
                border: none;
                font-size: 13px;
            }
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
    
    def set_vm_ref(self, vm: VMConfig):
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

# ========== 创建/编辑虚拟机对话框 ==========
class CreateVMDialog(QDialog):
    def __init__(self, parent=None, existing_vm: VMConfig = None):
        super().__init__(parent)
        self.parent = parent
        self.existing_vm = existing_vm
        self.vm = existing_vm if existing_vm else VMConfig()
        self.history = ConfigHistory()
        self._temp_iso_path = ""
        self._temp_driver_path = ""
        self._temp_share_dir = ""
        self.hardware_detector = parent.hardware_detector if parent else QEMUHardwareDetector()
        self.init_ui()
        if existing_vm:
            self.setWindowTitle(tr("btn_edit") + f" - {existing_vm.name}")
            self.create_btn.setText(tr("btn_save"))
            self.name_edit.setReadOnly(True)
            self.name_edit.setStyleSheet("color: #888;")
            self.load_vm_data(existing_vm)
        else:
            self.setWindowTitle(tr("btn_new"))
            self.create_btn.setText(tr("btn_create"))
        self.on_qemu_version_changed()
    
    def init_ui(self):
        # 大字体微软雅黑
        font = QFont("Microsoft YaHei", 12)
        self.setFont(font)
        
        self.setMinimumSize(950, 800)
        self.resize(950, 800)
        
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.setFont(font)
        
        # 基本
        tab_basic = self.create_basic_tab()
        self.tab_widget.addTab(tab_basic, tr("tab_basic"))
        
        # 硬件
        tab_hardware = self.create_hardware_tab()
        self.tab_widget.addTab(tab_hardware, tr("tab_hardware"))
        
        # 显示
        tab_display = self.create_display_tab()
        self.tab_widget.addTab(tab_display, tr("tab_display"))
        
        # 高级
        self.advanced_widget = AdvancedOptionsWidget(self)
        self.advanced_widget.set_vm_ref(self.vm)
        tab_advanced = QWidget()
        adv_layout = QVBoxLayout(tab_advanced)
        adv_layout.addWidget(self.advanced_widget)
        self.tab_widget.addTab(tab_advanced, tr("tab_advanced"))
        
        main_layout.addWidget(self.tab_widget, 1)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.history_btn = QPushButton("📜 " + tr("history_title", ""))
        self.history_btn.setMinimumHeight(34)
        self.history_btn.clicked.connect(self.show_history)
        btn_layout.addWidget(self.history_btn)
        
        self.create_btn = QPushButton(tr("btn_create"))
        self.create_btn.setMinimumHeight(40)
        self.create_btn.setMinimumWidth(120)
        self.create_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
                border: none;
                padding: 8px 20px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        self.create_btn.clicked.connect(self.save)
        btn_layout.addWidget(self.create_btn)
        
        self.cancel_btn = QPushButton(tr("btn_cancel"))
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                font-size: 14px;
                border-radius: 8px;
                border: none;
                padding: 8px 20px;
            }
            QPushButton:hover { background-color: #555; }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(btn_layout)
    
    def create_basic_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # 预设
        preset_group = QGroupBox("🏷️ " + tr("label_preset"))
        preset_group.setFont(QFont("Microsoft YaHei", 12))
        preset_layout = QVBoxLayout(preset_group)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("label_preset")))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumHeight(32)
        self.preset_combo.setFont(QFont("Microsoft YaHei", 12))
        for name in SYSTEM_PRESETS.keys():
            self.preset_combo.addItem(name)
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        row.addWidget(self.preset_combo, 1)
        preset_help = QPushButton(tr("btn_help"))
        preset_help.setFixedSize(32, 32)
        preset_help.clicked.connect(self.show_preset_help)
        row.addWidget(preset_help)
        preset_layout.addLayout(row)
        self.preset_desc = QLabel("")
        self.preset_desc.setStyleSheet("color: #aaa; font-size: 11px; padding: 4px 8px; background: #3a3a3a; border-radius: 6px;")
        self.preset_desc.setWordWrap(True)
        preset_layout.addWidget(self.preset_desc)
        layout.addWidget(preset_group)
        
        # 基本信息
        basic_group = QGroupBox(tr("tab_basic"))
        basic_group.setFont(QFont("Microsoft YaHei", 12))
        grid = QGridLayout(basic_group)
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(12)
        
        row = 0
        grid.addWidget(QLabel(tr("label_name")), row, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setMinimumHeight(32)
        self.name_edit.setFont(QFont("Microsoft YaHei", 12))
        self.name_edit.setPlaceholderText("输入名称（英文或数字）")
        grid.addWidget(self.name_edit, row, 1)
        
        row += 1
        grid.addWidget(QLabel(tr("label_os_type")), row, 0)
        self.os_combo = QComboBox()
        self.os_combo.setMinimumHeight(32)
        self.os_combo.setFont(QFont("Microsoft YaHei", 12))
        self.os_combo.addItems(["Windows", "Linux", "Android", "macOS", "其他"])
        grid.addWidget(self.os_combo, row, 1)
        
        row += 1
        grid.addWidget(QLabel(tr("label_os_version")), row, 0)
        self.version_combo = QComboBox()
        self.version_combo.setMinimumHeight(32)
        self.version_combo.setFont(QFont("Microsoft YaHei", 12))
        self.version_combo.addItems(["XP", "7", "8.1", "10", "11", "Server", "Ubuntu", "Debian", "Fedora", "Android", "Catalina", "FreeBSD", "其他"])
        grid.addWidget(self.version_combo, row, 1)
        
        row += 1
        grid.addWidget(QLabel(tr("label_arch")), row, 0)
        self.arch_combo = QComboBox()
        self.arch_combo.setMinimumHeight(32)
        self.arch_combo.setFont(QFont("Microsoft YaHei", 12))
        self.arch_combo.addItems(["x86", "x86_64", "ARM64"])
        grid.addWidget(self.arch_combo, row, 1)
        
        row += 1
        grid.addWidget(QLabel(tr("label_qemu_version")), row, 0)
        self.qemu_version_combo = QComboBox()
        self.qemu_version_combo.setMinimumHeight(32)
        self.qemu_version_combo.setFont(QFont("Microsoft YaHei", 12))
        versions = list(self.hardware_detector.qemu_versions.keys())
        if versions:
            self.qemu_version_combo.addItems(versions)
        else:
            self.qemu_version_combo.addItem("未检测到 QEMU")
        self.qemu_version_combo.currentTextChanged.connect(self.on_qemu_version_changed)
        grid.addWidget(self.qemu_version_combo, row, 1)
        
        # QEMU硬件信息
        self.hw_info_label = QLabel("🔍 点击刷新检测硬件")
        self.hw_info_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        grid.addWidget(self.hw_info_label, row + 1, 0, 1, 2)
        
        layout.addWidget(basic_group)
        layout.addStretch()
        return widget
    
    def create_hardware_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # CPU/内存
        cpu_group = QGroupBox(tr("tab_cpu_adv"))
        cpu_group.setFont(QFont("Microsoft YaHei", 12))
        grid = QGridLayout(cpu_group)
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(12)
        
        row = 0
        grid.addWidget(QLabel(tr("label_memory")), row, 0)
        self.memory_spin = QSpinBox()
        self.memory_spin.setMinimumHeight(32)
        self.memory_spin.setFont(QFont("Microsoft YaHei", 12))
        self.memory_spin.setRange(128, 65536)
        self.memory_spin.setSingleStep(512)
        grid.addWidget(self.memory_spin, row, 1)
        
        row += 1
        grid.addWidget(QLabel(tr("label_cpu_cores")), row, 0)
        self.cpu_spin = QSpinBox()
        self.cpu_spin.setMinimumHeight(32)
        self.cpu_spin.setFont(QFont("Microsoft YaHei", 12))
        self.cpu_spin.setRange(1, 32)
        grid.addWidget(self.cpu_spin, row, 1)
        
        row += 1
        grid.addWidget(QLabel(tr("label_cpu_threads")), row, 0)
        self.smp_threads_spin = QSpinBox()
        self.smp_threads_spin.setMinimumHeight(32)
        self.smp_threads_spin.setFont(QFont("Microsoft YaHei", 12))
        self.smp_threads_spin.setRange(1, 8)
        grid.addWidget(self.smp_threads_spin, row, 1)
        
        row += 1
        grid.addWidget(QLabel(tr("label_cpu_sockets")), row, 0)
        self.smp_sockets_spin = QSpinBox()
        self.smp_sockets_spin.setMinimumHeight(32)
        self.smp_sockets_spin.setFont(QFont("Microsoft YaHei", 12))
        self.smp_sockets_spin.setRange(1, 4)
        grid.addWidget(self.smp_sockets_spin, row, 1)
        
        layout.addWidget(cpu_group)
        
        # 磁盘
        disk_group = QGroupBox(tr("tab_disk_adv"))
        disk_group.setFont(QFont("Microsoft YaHei", 12))
        disk_layout = QGridLayout(disk_group)
        disk_layout.setVerticalSpacing(8)
        disk_layout.setHorizontalSpacing(12)
        
        row = 0
        disk_layout.addWidget(QLabel(tr("label_disk_size")), row, 0)
        self.disk_spin = QSpinBox()
        self.disk_spin.setMinimumHeight(32)
        self.disk_spin.setFont(QFont("Microsoft YaHei", 12))
        self.disk_spin.setRange(1, 1024)
        disk_layout.addWidget(self.disk_spin, row, 1)
        disk_layout.addWidget(QLabel(" GB"), row, 2)
        
        row += 1
        disk_layout.addWidget(QLabel(tr("label_disk_format")), row, 0)
        self.disk_format_combo = QComboBox()
        self.disk_format_combo.setMinimumHeight(32)
        self.disk_format_combo.setFont(QFont("Microsoft YaHei", 12))
        self.disk_format_combo.addItems(DISK_FORMATS)
        self.disk_format_combo.setCurrentText("qcow2")
        disk_layout.addWidget(self.disk_format_combo, row, 1, 1, 2)
        
        row += 1
        disk_layout.addWidget(QLabel(tr("label_disk_interface")), row, 0)
        self.disk_interface_combo = QComboBox()
        self.disk_interface_combo.setMinimumHeight(32)
        self.disk_interface_combo.setFont(QFont("Microsoft YaHei", 12))
        self.disk_interface_combo.addItems(DISK_INTERFACES)
        self.disk_interface_combo.setCurrentText("sata")
        disk_layout.addWidget(self.disk_interface_combo, row, 1, 1, 2)
        
        layout.addWidget(disk_group)
        
        # 硬件
        hw_group = QGroupBox(tr("tab_hardware"))
        hw_group.setFont(QFont("Microsoft YaHei", 12))
        grid2 = QGridLayout(hw_group)
        grid2.setVerticalSpacing(8)
        grid2.setHorizontalSpacing(12)
        
        row = 0
        grid2.addWidget(QLabel(tr("label_cpu_model")), row, 0)
        self.cpu_model_combo = QComboBox()
        self.cpu_model_combo.setMinimumHeight(32)
        self.cpu_model_combo.setFont(QFont("Microsoft YaHei", 12))
        self.cpu_model_combo.addItems(CPU_MODELS)
        grid2.addWidget(self.cpu_model_combo, row, 1)
        
        row += 1
        grid2.addWidget(QLabel(tr("label_accel")), row, 0)
        self.accel_combo = QComboBox()
        self.accel_combo.setMinimumHeight(32)
        self.accel_combo.setFont(QFont("Microsoft YaHei", 12))
        all_accel = ["tcg", "hax", "whpx", "kvm", "hvf"]
        self.accel_combo.addItems(all_accel)
        if hasattr(self.parent, 'hardware_detector'):
            default = self.parent.hardware_detector.default_accel
            idx = self.accel_combo.findText(default)
            if idx >= 0:
                self.accel_combo.setCurrentIndex(idx)
        grid2.addWidget(self.accel_combo, row, 1)
        
        # 加速状态显示
        self.accel_status_label = QLabel("")
        self.accel_status_label.setStyleSheet("color: #6a9a6a; font-size: 11px;")
        grid2.addWidget(self.accel_status_label, row + 1, 0, 1, 2)
        
        row += 1
        grid2.addWidget(QLabel(tr("label_machine")), row, 0)
        self.machine_combo = QComboBox()
        self.machine_combo.setMinimumHeight(32)
        self.machine_combo.setFont(QFont("Microsoft YaHei", 12))
        self.machine_combo.addItems(MACHINE_TYPES)
        grid2.addWidget(self.machine_combo, row, 1)
        
        row += 1
        self.acpi_check = QCheckBox(tr("check_acpi"))
        self.acpi_check.setFont(QFont("Microsoft YaHei", 12))
        self.acpi_check.setChecked(True)
        grid2.addWidget(self.acpi_check, row, 0, 1, 2)
        
        layout.addWidget(hw_group)
        layout.addStretch()
        return widget
    
    def create_display_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # 显示
        display_group = QGroupBox(tr("tab_display_adv"))
        display_group.setFont(QFont("Microsoft YaHei", 12))
        grid = QGridLayout(display_group)
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(12)
        
        row = 0
        grid.addWidget(QLabel(tr("label_vga")), row, 0)
        self.vga_combo = QComboBox()
        self.vga_combo.setMinimumHeight(32)
        self.vga_combo.setFont(QFont("Microsoft YaHei", 12))
        self.vga_combo.addItems(VGA_TYPES)
        grid.addWidget(self.vga_combo, row, 1)
        
        row += 1
        grid.addWidget(QLabel(tr("label_display")), row, 0)
        self.display_combo = QComboBox()
        self.display_combo.setMinimumHeight(32)
        self.display_combo.setFont(QFont("Microsoft YaHei", 12))
        self.display_combo.addItems(DISPLAY_TYPES)
        grid.addWidget(self.display_combo, row, 1)
        
        row += 1
        grid.addWidget(QLabel(tr("label_resolution")), row, 0)
        self.resolution_combo = QComboBox()
        self.resolution_combo.setMinimumHeight(32)
        self.resolution_combo.setFont(QFont("Microsoft YaHei", 12))
        self.resolution_combo.addItems(RESOLUTIONS)
        grid.addWidget(self.resolution_combo, row, 1)
        
        row += 1
        grid.addWidget(QLabel(tr("label_vnc_port")), row, 0)
        self.vnc_edit = QLineEdit()
        self.vnc_edit.setMinimumHeight(32)
        self.vnc_edit.setFont(QFont("Microsoft YaHei", 12))
        self.vnc_edit.setPlaceholderText("留空使用 GTK，输入 :0 使用 VNC")
        grid.addWidget(self.vnc_edit, row, 1)
        
        row += 1
        self.opengl_check = QCheckBox(tr("check_opengl"))
        self.opengl_check.setFont(QFont("Microsoft YaHei", 12))
        grid.addWidget(self.opengl_check, row, 0, 1, 2)
        
        layout.addWidget(display_group)
        
        # 声音/网络
        sound_group = QGroupBox(tr("tab_display"))
        sound_group.setFont(QFont("Microsoft YaHei", 12))
        grid2 = QGridLayout(sound_group)
        grid2.setVerticalSpacing(8)
        grid2.setHorizontalSpacing(12)
        
        row = 0
        grid2.addWidget(QLabel(tr("label_sound")), row, 0)
        self.sound_combo = QComboBox()
        self.sound_combo.setMinimumHeight(32)
        self.sound_combo.setFont(QFont("Microsoft YaHei", 12))
        self.sound_combo.addItems(SOUND_TYPES)
        grid2.addWidget(self.sound_combo, row, 1)
        
        row += 1
        grid2.addWidget(QLabel(tr("label_nic")), row, 0)
        self.nic_combo = QComboBox()
        self.nic_combo.setMinimumHeight(32)
        self.nic_combo.setFont(QFont("Microsoft YaHei", 12))
        self.nic_combo.addItems(NIC_TYPES)
        grid2.addWidget(self.nic_combo, row, 1)
        
        row += 1
        grid2.addWidget(QLabel(tr("label_boot_order")), row, 0)
        self.boot_combo = QComboBox()
        self.boot_combo.setMinimumHeight(32)
        self.boot_combo.setFont(QFont("Microsoft YaHei", 12))
        self.boot_combo.addItems(BOOT_TYPES)
        grid2.addWidget(self.boot_combo, row, 1)
        
        row += 1
        self.usb_check = QCheckBox(tr("check_usb"))
        self.usb_check.setFont(QFont("Microsoft YaHei", 12))
        self.usb_check.setChecked(True)
        grid2.addWidget(self.usb_check, row, 0, 1, 2)
        
        layout.addWidget(sound_group)
        
        # 共享文件夹
        share_group = QGroupBox("📁 " + tr("check_share"))
        share_group.setFont(QFont("Microsoft YaHei", 12))
        share_layout = QGridLayout(share_group)
        share_layout.setVerticalSpacing(8)
        share_layout.setHorizontalSpacing(12)
        
        row = 0
        self.share_enable_check = QCheckBox(tr("check_share"))
        self.share_enable_check.setFont(QFont("Microsoft YaHei", 12))
        self.share_enable_check.toggled.connect(self.on_share_toggle)
        share_layout.addWidget(self.share_enable_check, row, 0, 1, 2)
        
        row += 1
        share_layout.addWidget(QLabel(tr("label_share_dir")), row, 0)
        self.share_dir_label = QLabel("未选择")
        self.share_dir_label.setStyleSheet("border: 2px solid #555; padding: 4px; border-radius: 6px; color: #aaa;")
        self.share_dir_label.mousePressEvent = self.browse_share_dir_click
        share_layout.addWidget(self.share_dir_label, row, 1)
        self.share_dir_btn = QPushButton(tr("btn_browse"))
        self.share_dir_btn.setMinimumHeight(32)
        self.share_dir_btn.clicked.connect(self.browse_share_dir)
        share_layout.addWidget(self.share_dir_btn, row, 2)
        
        info_label = QLabel("💡 虚拟机内访问: \\\\10.0.2.4\\qemu")
        info_label.setStyleSheet("color: #888; font-size: 10px;")
        share_layout.addWidget(info_label, row+1, 0, 1, 3)
        
        layout.addWidget(share_group)
        
        # ISO
        iso_group = QGroupBox("💿 " + tr("tab_basic"))
        iso_group.setFont(QFont("Microsoft YaHei", 12))
        iso_layout = QGridLayout(iso_group)
        iso_layout.setVerticalSpacing(8)
        iso_layout.setHorizontalSpacing(12)
        
        row = 0
        iso_layout.addWidget(QLabel(tr("label_boot_iso")), row, 0)
        self.boot_iso_label = QLabel("未选择")
        self.boot_iso_label.setStyleSheet("border: 2px solid #555; padding: 4px; border-radius: 6px; color: #aaa;")
        iso_layout.addWidget(self.boot_iso_label, row, 1)
        self.boot_iso_btn = QPushButton(tr("btn_browse"))
        self.boot_iso_btn.setMinimumHeight(32)
        self.boot_iso_btn.clicked.connect(lambda: self.browse_iso("boot"))
        iso_layout.addWidget(self.boot_iso_btn, row, 2)
        self.boot_clear_btn = QPushButton(tr("btn_clear"))
        self.boot_clear_btn.setMinimumHeight(32)
        self.boot_clear_btn.clicked.connect(lambda: self.clear_iso("boot"))
        iso_layout.addWidget(self.boot_clear_btn, row, 3)
        
        row += 1
        iso_layout.addWidget(QLabel(tr("label_driver_iso")), row, 0)
        self.driver_iso_label = QLabel("未选择")
        self.driver_iso_label.setStyleSheet("border: 2px solid #555; padding: 4px; border-radius: 6px; color: #aaa;")
        iso_layout.addWidget(self.driver_iso_label, row, 1)
        self.driver_iso_btn = QPushButton(tr("btn_browse"))
        self.driver_iso_btn.setMinimumHeight(32)
        self.driver_iso_btn.clicked.connect(lambda: self.browse_iso("driver"))
        iso_layout.addWidget(self.driver_iso_btn, row, 2)
        self.driver_clear_btn = QPushButton(tr("btn_clear"))
        self.driver_clear_btn.setMinimumHeight(32)
        self.driver_clear_btn.clicked.connect(lambda: self.clear_iso("driver"))
        iso_layout.addWidget(self.driver_clear_btn, row, 3)
        
        row += 1
        iso_layout.addWidget(QLabel(tr("label_extra_args")), row, 0)
        self.extra_edit = QLineEdit()
        self.extra_edit.setMinimumHeight(32)
        self.extra_edit.setFont(QFont("Microsoft YaHei", 12))
        self.extra_edit.setPlaceholderText("额外的 QEMU 参数")
        iso_layout.addWidget(self.extra_edit, row, 1, 1, 3)
        
        layout.addWidget(iso_group)
        layout.addStretch()
        return widget
    
    def on_qemu_version_changed(self):
        """QEMU版本切换时更新硬件信息"""
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
    
    def update_hardware_lists(self, info: dict):
        """更新硬件下拉列表（动态从QEMU检测结果填充）"""
        # CPU型号
        if info.get('cpu_models'):
            current = self.cpu_model_combo.currentText()
            self.cpu_model_combo.clear()
            self.cpu_model_combo.addItems(info['cpu_models'])
            if current in info['cpu_models']:
                self.cpu_model_combo.setCurrentText(current)
            else:
                self.cpu_model_combo.setCurrentIndex(0)
        
        # 显卡
        if info.get('vga_types'):
            current = self.vga_combo.currentText()
            self.vga_combo.clear()
            self.vga_combo.addItems(info['vga_types'])
            if current in info['vga_types']:
                self.vga_combo.setCurrentText(current)
        
        # 显示后端
        if info.get('display_types'):
            current = self.display_combo.currentText()
            self.display_combo.clear()
            self.display_combo.addItems(info['display_types'])
            if current in info['display_types']:
                self.display_combo.setCurrentText(current)
        
        # 机器类型
        if info.get('machine_types'):
            current = self.machine_combo.currentText()
            self.machine_combo.clear()
            self.machine_combo.addItems(info['machine_types'])
            if current in info['machine_types']:
                self.machine_combo.setCurrentText(current)
        
        # 加速器
        if info.get('accel_types'):
            current = self.accel_combo.currentText()
            self.accel_combo.clear()
            self.accel_combo.addItems(info['accel_types'])
            if hasattr(self.parent, 'hardware_detector'):
                default = self.parent.hardware_detector.default_accel
                if default in info['accel_types']:
                    self.accel_combo.setCurrentText(default)
                    self.accel_status_label.setText(f"✅ 系统支持: {default}")
                    self.accel_status_label.setStyleSheet("color: #6a9a6a; font-size: 11px;")
                else:
                    self.accel_status_label.setText("⚠️ 当前加速器可能不受系统支持")
                    self.accel_status_label.setStyleSheet("color: #FF8A9C; font-size: 11px;")
        
        # 网络设备
        if info.get('netdev_types'):
            current = self.nic_combo.currentText()
            self.nic_combo.clear()
            self.nic_combo.addItems(info['netdev_types'])
            if current in info['netdev_types']:
                self.nic_combo.setCurrentText(current)
        
        # 音频设备
        if info.get('audio_devices'):
            current = self.sound_combo.currentText()
            self.sound_combo.clear()
            self.sound_combo.addItems(info['audio_devices'])
            if current in info['audio_devices']:
                self.sound_combo.setCurrentText(current)
    
    def on_preset_changed(self, preset_name: str):
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
        
        self.preset_desc.setText(tr("label_preset_desc", preset.get('description', '')))
    
    def on_share_toggle(self, checked):
        self.share_dir_label.setEnabled(checked)
        self.share_dir_btn.setEnabled(checked)
    
    def browse_share_dir_click(self, event):
        if self.share_enable_check.isChecked():
            self.browse_share_dir()
    
    def browse_share_dir(self):
        folder = QFileDialog.getExistingDirectory(self, tr("label_share_dir"), str(BASE_DIR))
        if folder:
            self.share_dir_label.setText(folder)
            self._temp_share_dir = folder
    
    def browse_iso(self, iso_type: str):
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
    
    def clear_iso(self, iso_type: str):
        if iso_type == "boot":
            self.boot_iso_label.setText("未选择")
            self.boot_iso_label.setStyleSheet("border: 2px solid #555; padding: 4px; border-radius: 6px; color: #aaa;")
            self._temp_iso_path = ""
        elif iso_type == "driver":
            self.driver_iso_label.setText("未选择")
            self.driver_iso_label.setStyleSheet("border: 2px solid #555; padding: 4px; border-radius: 6px; color: #aaa;")
            self._temp_driver_path = ""
    
    def show_preset_help(self):
        QMessageBox.information(self, tr("info"),
            "📋 系统预设 = 一键配置最佳参数\n\n"
            "每个预设都针对特定系统优化：\n"
            "• Windows XP → QEMU 2016 + IDE + SB16\n"
            "• Windows 7 → QEMU 2019 + SATA + AC97\n"
            "• Windows 8.1 → QEMU 2019 + SATA + AC97\n"
            "• Windows 10/11 → QEMU 2025 + VirtIO + HDA\n"
            "• Android → QEMU 2019 + IDE + 关闭声卡\n\n"
            "选好预设后可以手动微调每个参数！"
        )
    
    def show_history(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, tr("warning"), tr("msg_name_empty"))
            return
        
        history = self.history.get_history(name)
        if not history:
            QMessageBox.information(self, tr("info"), tr("msg_history_no_entries", name))
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("history_title", name))
        dialog.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        list_widget = QListWidget()
        for i, entry in enumerate(history):
            timestamp = entry.get("timestamp", "未知时间")
            list_widget.addItem(tr("history_entry", i+1, timestamp))
        layout.addWidget(list_widget)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        restore_btn = QPushButton(tr("history_restore_btn"))
        restore_btn.clicked.connect(lambda: self.restore_history(dialog, list_widget.currentRow(), name))
        btn_layout.addWidget(restore_btn)
        
        close_btn = QPushButton(tr("btn_close"))
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec()
    
    def restore_history(self, dialog, index, name):
        if index < 0:
            QMessageBox.warning(dialog, tr("warning"), tr("msg_history_select"))
            return
        
        config = self.history.restore_entry(name, index)
        if not config:
            QMessageBox.warning(dialog, tr("error"), tr("msg_history_restore_failed"))
            return
        
        reply = QMessageBox.question(dialog, tr("confirm"), 
            tr("msg_history_restore", name),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        
        vm = VMConfig.from_dict(config)
        self.vm = vm
        self.advanced_widget.set_vm_ref(vm)
        self.load_vm_data(vm)
        dialog.accept()
        QMessageBox.information(self, tr("success"), tr("msg_history_restored"))
    
    def load_vm_data(self, vm: VMConfig):
        self.name_edit.setText(vm.name)
        self.os_combo.setCurrentText(vm.os_type)
        self.version_combo.setCurrentText(vm.os_version)
        self.arch_combo.setCurrentText(vm.arch)
        self.memory_spin.setValue(vm.memory)
        self.cpu_spin.setValue(vm.cpu)
        self.smp_threads_spin.setValue(vm.smp_threads)
        self.smp_sockets_spin.setValue(vm.smp_sockets)
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
        if vm.boot_iso:
            self.boot_iso_label.setText(Path(vm.boot_iso).name)
            self.boot_iso_label.setStyleSheet("border: 2px solid #4CAF50; padding: 4px; border-radius: 6px; background: #e8f5e9;")
            self._temp_iso_path = vm.boot_iso
        if vm.driver_iso:
            self.driver_iso_label.setText(Path(vm.driver_iso).name)
            self.driver_iso_label.setStyleSheet("border: 2px solid #4CAF50; padding: 4px; border-radius: 6px; background: #e8f5e9;")
            self._temp_driver_path = vm.driver_iso
        self.extra_edit.setText(vm.extra_args)
        self.advanced_widget.set_config({
            "cache": vm.cache,
            "aio": vm.aio,
            "discard": vm.discard,
            "detect_zeroes": vm.detect_zeroes,
            "backing_file": vm.backing_file,
            "snapshot_mode": vm.snapshot_mode,
            "disk_readonly": vm.disk_readonly,
            "hostfwd": vm.hostfwd,
            "net_subnet": vm.net_subnet,
            "net_dns": vm.net_dns,
            "net_restrict": vm.net_restrict,
            "tap_interface": vm.tap_interface,
            "mac_address": vm.mac_address,
            "cpu_flags": vm.cpu_flags,
            "numa_config": vm.numa_config,
            "mem_prealloc": vm.mem_prealloc,
            "hugepages": vm.hugepages,
            "no_hpet_adv": vm.no_hpet_adv,
            "no_kvm_nested": vm.no_kvm_nested,
            "force_tcg": vm.force_tcg,
            "usb_tablet": vm.usb_tablet,
            "bios_file": vm.bios_file,
            "vnc_password": vm.vnc_password,
            "spice_port": vm.spice_port,
            "spice_password": vm.spice_password,
            "no_mouse_integration": vm.no_mouse_integration,
            "log_file": vm.log_file,
            "debug_level": vm.debug_level,
            "qmp_socket": vm.qmp_socket,
            "monitor_stdio": vm.monitor_stdio,
            "no_reboot": vm.no_reboot,
            "no_shutdown": vm.no_shutdown,
            "sandbox": vm.sandbox,
            "rtc_base": vm.rtc_base,
            "seed_value": vm.seed_value,
            "boot_menu": vm.boot_menu,
            "boot_once": vm.boot_once,
            "extra_advanced_args": vm.extra_advanced_args,
        })
    
    def save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, tr("warning"), tr("msg_name_empty"))
            return
        
        if not self.existing_vm and (VMS_DIR / name).exists():
            QMessageBox.warning(self, tr("warning"), tr("msg_vm_exists", name))
            return
        
        vm = self.vm if self.existing_vm else VMConfig()
        vm.name = name
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
        vm.no_hpet = False
        vm.no_kvm = False
        
        # 性能参数（从高级选项获取）
        # CPU频率和时钟在性能调优选项卡中
        
        adv = self.advanced_widget.get_config()
        for key, val in adv.items():
            setattr(vm, key, val)
        
        if not self.existing_vm:
            vm.created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            vm_dir = VMS_DIR / name
            vm_dir.mkdir(parents=True, exist_ok=True)
            
            disk_path = vm_dir / f"disk.{vm.disk_format}"
            qemu_img = find_qemu_img()
            if qemu_img:
                try:
                    subprocess.run(
                        [str(qemu_img), "create", "-f", vm.disk_format, str(disk_path), f"{vm.disk_size}G"],
                        capture_output=True, text=True, encoding='utf-8', errors='ignore', check=True
                    )
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
    
    def get_vm(self) -> Optional[VMConfig]:
        return self.vm

# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.vm_list: List[VMConfig] = []
        self.current_vm: Optional[VMConfig] = None
        self.translator = Translator()
        self.translator.set_main_window(self)
        self.history = ConfigHistory()
        self.hardware_detector = QEMUHardwareDetector()
        self.init_ui()
        self.load_vms()
        self.refresh_vm_list()
        self.load_language_setting()
        self.status_bar.showMessage(tr("status_detecting") + " " + tr("status_ready"))
    
    def init_ui(self):
        # 大字体微软雅黑
        font = QFont("Microsoft YaHei", 11)
        self.setFont(font)
        
        self.setWindowTitle(tr("app_title", APP_VERSION))
        self.setMinimumSize(1100, 700)
        self.resize(1200, 750)
        
        # 全局黑色背景 + 白色文字
        self.setStyleSheet("""
            QMainWindow {
                background-color: #000000;
                color: #ffffff;
            }
            QMenuBar {
                background-color: #000000;
                color: #ffffff;
                border-bottom: 1px solid #333333;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QMenuBar::item:selected {
                background-color: #333333;
            }
            QMenu {
                background-color: #000000;
                color: #ffffff;
                border: 1px solid #333333;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QMenu::item:selected {
                background-color: #333333;
            }
            QToolBar {
                background-color: #000000;
                border: none;
                spacing: 4px;
                padding: 4px 8px;
            }
            QToolButton {
                background-color: transparent;
                color: #ffffff;
                border: none;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }
            QToolButton:hover {
                background-color: #333333;
            }
            QToolButton:pressed {
                background-color: #444444;
            }
            QToolButton:disabled {
                color: #666666;
            }
            QSplitter::handle {
                background-color: #333333;
            }
            QListWidget {
                background-color: #000000;
                color: #ffffff;
                border: none;
                outline: none;
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }
            QListWidget::item {
                padding: 10px 14px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #333333;
            }
            QListWidget::item:hover {
                background-color: #1a1a1a;
            }
            QTabWidget::pane {
                background-color: #000000;
                border: 1px solid #333333;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #000000;
                color: #aaaaaa;
                padding: 10px 20px;
                border: 1px solid #333333;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }
            QTabBar::tab:selected {
                background-color: #000000;
                color: #ffffff;
            }
            QTabBar::tab:hover {
                background-color: #1a1a1a;
            }
            QGroupBox {
                color: #ffffff;
                border: 1px solid #333333;
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
                color: #aaaaaa;
            }
            QLabel {
                color: #ffffff;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #000000;
                color: #ffffff;
                border: 1px solid #333333;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QComboBox QAbstractItemView {
                background-color: #000000;
                color: #ffffff;
                selection-background-color: #333333;
                selection-color: #ffffff;
                border: 1px solid #333333;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border-color: #555555;
            }
            QLineEdit:disabled {
                color: #888888;
            }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 18px;
                font-weight: bold;
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }
            QPushButton:hover {
                background-color: #444444;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
            }
            QCheckBox {
                color: #ffffff;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 1px solid #333333;
                background-color: #000000;
            }
            QCheckBox::indicator:checked {
                background-color: #4a7a4a;
                border-color: #4a7a4a;
            }
            QScrollBar:vertical {
                background-color: #000000;
                width: 14px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #333333;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #444444;
            }
            QScrollBar:horizontal {
                background-color: #000000;
                height: 14px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background-color: #333333;
                border-radius: 6px;
                min-width: 20px;
            }
            QStatusBar {
                background-color: #000000;
                color: #888888;
                border-top: 1px solid #333333;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QMessageBox {
                background-color: #000000;
                color: #ffffff;
            }
            QMessageBox QPushButton {
                min-width: 80px;
                padding: 8px 20px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #333333;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #555555;
                width: 18px;
                height: 18px;
                border-radius: 9px;
                margin: -6px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #666666;
            }
        """)
        
        # ===== 菜单栏 =====
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        new_action = QAction(tr("btn_new"), self)
        new_action.triggered.connect(self.create_vm)
        new_action.setShortcut("Ctrl+N")
        file_menu.addAction(new_action)
        
        file_menu.addSeparator()
        
        import_action = QAction(tr("btn_import"), self)
        import_action.triggered.connect(self.import_vm)
        file_menu.addAction(import_action)
        
        export_action = QAction(tr("btn_export"), self)
        export_action.triggered.connect(self.export_vm)
        file_menu.addAction(export_action)
        
        export_as_menu = QMenu(tr("btn_export_as"), self)
        for fmt, desc in [("mikan", "Mikan (.mikan)"), ("vmdk", "VMDK"), ("vdi", "VDI"), ("vhdx", "VHDX"), ("raw", "RAW")]:
            action = QAction(desc, self)
            action.triggered.connect(lambda checked, f=fmt: self.export_vm_as(f))
            export_as_menu.addAction(action)
        file_menu.addMenu(export_as_menu)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出(&X)", self)
        exit_action.triggered.connect(self.close)
        exit_action.setShortcut("Ctrl+Q")
        file_menu.addAction(exit_action)
        
        # 虚拟机菜单
        vm_menu = menubar.addMenu("虚拟机(&V)")
        settings_action = QAction(tr("btn_edit"), self)
        settings_action.triggered.connect(self.edit_vm)
        settings_action.setShortcut("Ctrl+S")
        vm_menu.addAction(settings_action)
        
        vm_menu.addSeparator()
        
        launch_action = QAction(tr("btn_launch"), self)
        launch_action.triggered.connect(self.launch_vm)
        launch_action.setShortcut("Ctrl+P")
        vm_menu.addAction(launch_action)
        
        vm_menu.addSeparator()
        
        snapshot_action = QAction(tr("btn_snapshot"), self)
        snapshot_action.triggered.connect(self.manage_snapshots)
        vm_menu.addAction(snapshot_action)
        
        script_action = QAction(tr("btn_script"), self)
        script_action.triggered.connect(self.export_script)
        vm_menu.addAction(script_action)
        
        disk_action = QAction(tr("btn_disk"), self)
        disk_action.triggered.connect(self.show_disk_manager)
        vm_menu.addAction(disk_action)
        
        vm_menu.addSeparator()
        
        delete_action = QAction(tr("btn_delete"), self)
        delete_action.triggered.connect(self.delete_vm)
        delete_action.setShortcut("Delete")
        vm_menu.addAction(delete_action)
        
        # 检测菜单（新增）
        detect_menu = menubar.addMenu(tr("menu_detect"))
        detect_hw_action = QAction(tr("menu_detect_hw"), self)
        detect_hw_action.triggered.connect(self.detect_system_hardware)
        detect_menu.addAction(detect_hw_action)
        
        detect_qemu_action = QAction("🔍 检测 QEMU 硬件", self)
        detect_qemu_action.triggered.connect(self.detect_qemu_hardware)
        detect_menu.addAction(detect_qemu_action)
        
        # 查看菜单
        view_menu = menubar.addMenu("查看(&V)")
        lang_menu = view_menu.addMenu(tr("menu_language"))
        for code, name in self.translator.get_languages().items():
            action = QAction(name, self)
            action.triggered.connect(lambda checked, c=code: self.change_language(c))
            lang_menu.addAction(action)
        
        # 帮助菜单
        help_menu = menubar.addMenu(tr("menu_help"))
        about_action = QAction(tr("menu_help_about"), self)
        about_action.triggered.connect(self.show_help)
        help_menu.addAction(about_action)
        
        # ===== 工具栏 - 只保留核心按钮 =====
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        self.btn_new = QToolButton()
        self.btn_new.setText("📦 " + tr("btn_new"))
        self.btn_new.clicked.connect(self.create_vm)
        toolbar.addWidget(self.btn_new)
        
        toolbar.addSeparator()
        
        self.btn_edit = QToolButton()
        self.btn_edit.setText("✏️ " + tr("btn_edit"))
        self.btn_edit.clicked.connect(self.edit_vm)
        self.btn_edit.setEnabled(False)
        toolbar.addWidget(self.btn_edit)
        
        toolbar.addSeparator()
        
        self.btn_launch = QToolButton()
        self.btn_launch.setText("🚀 " + tr("btn_launch"))
        self.btn_launch.clicked.connect(self.launch_vm)
        self.btn_launch.setEnabled(False)
        self.btn_launch.setStyleSheet("QToolButton { color: #6a9a6a; font-weight: bold; }")
        toolbar.addWidget(self.btn_launch)
        
        toolbar.addSeparator()
        
        self.btn_export = QToolButton()
        self.btn_export.setText("📦 " + tr("btn_export"))
        self.btn_export.clicked.connect(self.export_vm)
        self.btn_export.setEnabled(False)
        toolbar.addWidget(self.btn_export)
        
        self.btn_import = QToolButton()
        self.btn_import.setText("📥 " + tr("btn_import"))
        self.btn_import.clicked.connect(self.import_vm)
        toolbar.addWidget(self.btn_import)
        
        toolbar.addSeparator()
        
        self.btn_refresh = QToolButton()
        self.btn_refresh.setText("🔄 " + tr("btn_refresh"))
        self.btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(self.btn_refresh)
        
        # ===== 主布局 =====
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧 - 虚拟机列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        
        title_widget = QWidget()
        title_widget.setStyleSheet("background-color: #000000; padding: 6px 12px;")
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(8, 4, 8, 4)
        title_label = QLabel("📂 虚拟机")
        title_label.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet("color: #888888; font-size: 12px;")
        title_layout.addWidget(self.count_label)
        left_layout.addWidget(title_widget)
        
        self.vm_list_widget = QListWidget()
        self.vm_list_widget.setFont(QFont("Microsoft YaHei", 12))
        self.vm_list_widget.itemSelectionChanged.connect(self.on_vm_selected)
        self.vm_list_widget.itemDoubleClicked.connect(self.launch_vm)
        left_layout.addWidget(self.vm_list_widget)
        
        splitter.addWidget(left_widget)
        
        # 右侧 - 详细信息面板
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        
        # 顶部信息栏
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
        
        # 选项卡
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("QTabWidget::pane { background-color: #000000; border: none; }")
        
        # 摘要
        self.summary_tab = self.create_summary_tab()
        self.tab_widget.addTab(self.summary_tab, "📋 摘要")
        
        # 配置
        self.config_tab = self.create_config_tab()
        self.tab_widget.addTab(self.config_tab, "⚙️ 配置")
        
        right_layout.addWidget(self.tab_widget)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([280, 920])
        
        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(splitter)
        self.setCentralWidget(central)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(tr("status_ready"))
    
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
        fields = [
            ("系统类型:", "os_type"),
            ("系统版本:", "os_version"),
            ("架构:", "arch"),
            ("内存:", "memory"),
            ("CPU核心:", "cpu"),
            ("磁盘大小:", "disk_size"),
            ("QEMU版本:", "qemu_version"),
            ("创建时间:", "created"),
        ]
        
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
        """刷新UI文字（语言切换时调用）"""
        self.setWindowTitle(tr("app_title", APP_VERSION))
        self.btn_new.setText("📦 " + tr("btn_new"))
        self.btn_edit.setText("✏️ " + tr("btn_edit"))
        self.btn_launch.setText("🚀 " + tr("btn_launch"))
        self.btn_export.setText("📦 " + tr("btn_export"))
        self.btn_import.setText("📥 " + tr("btn_import"))
        self.btn_refresh.setText("🔄 " + tr("btn_refresh"))
        self.status_bar.showMessage(tr("status_refreshed"))
    
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
        self.vm_list_widget.clear()
        icons = {"Windows": "🪟", "Linux": "🐧", "Android": "📱", "macOS": "🍎"}
        for vm in self.vm_list:
            icon = icons.get(vm.os_type, "💻")
            item = QListWidgetItem(f"{icon} {vm.name}")
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
    
    def update_summary(self, vm: VMConfig):
        self.summary_labels["os_type"].setText(vm.os_type)
        self.summary_labels["os_version"].setText(vm.os_version)
        self.summary_labels["arch"].setText(vm.arch)
        self.summary_labels["memory"].setText(f"{vm.memory} MB")
        self.summary_labels["cpu"].setText(f"{vm.cpu} 核心")
        self.summary_labels["disk_size"].setText(f"{vm.disk_size} GB")
        self.summary_labels["qemu_version"].setText(vm.qemu_version)
        self.summary_labels["created"].setText(vm.created or "-")
    
    def update_config_tab(self, vm: VMConfig):
        # 清除旧的配置显示
        for child in self.tab_widget.widget(1).findChildren(QWidget):
            if child != self.tab_widget.widget(1):
                child.deleteLater()
        
        layout = QVBoxLayout(self.tab_widget.widget(1))
        layout.setContentsMargins(12, 12, 12, 12)
        
        text = f"""
        <b>名称:</b> {vm.name}<br>
        <b>系统:</b> {vm.os_type} {vm.os_version}<br>
        <b>架构:</b> {vm.arch}<br>
        <b>内存:</b> {vm.memory} MB<br>
        <b>CPU:</b> {vm.cpu} 核心<br>
        <b>磁盘:</b> {vm.disk_size} GB ({vm.disk_format})<br>
        <b>接口:</b> {vm.disk_interface}<br>
        <b>CPU模型:</b> {vm.cpu_model}<br>
        <b>加速:</b> {vm.accel}<br>
        <b>显卡:</b> {vm.vga}<br>
        <b>机器:</b> {vm.machine_type}<br>
        <b>声卡:</b> {vm.sound}<br>
        <b>网卡:</b> {vm.nic_model}<br>
        <b>QEMU:</b> {vm.qemu_version}<br>
        """
        if vm.boot_iso:
            text += f"<b>启动ISO:</b> {Path(vm.boot_iso).name}<br>"
        if vm.share_dir:
            text += f"<b>共享目录:</b> {vm.share_dir}<br>"
        if vm.hostfwd:
            text += f"<b>端口转发:</b> {vm.hostfwd}<br>"
        if vm.cpu_freq > 0:
            text += f"<b>CPU频率:</b> {vm.cpu_freq} MHz<br>"
        if vm.cpu_clock > 0:
            text += f"<b>CPU时钟:</b> {vm.cpu_clock} MHz<br>"
        
        label = QLabel(text)
        label.setStyleSheet("color: #d0d0d0; font-size: 13px; padding: 8px;")
        label.setWordWrap(True)
        layout.addWidget(label)
        
        edit_btn = QPushButton("✏️ " + tr("btn_edit"))
        edit_btn.setMinimumHeight(36)
        edit_btn.clicked.connect(self.edit_vm)
        layout.addWidget(edit_btn)
        
        layout.addStretch()
    
    def create_vm(self):
        dialog = CreateVMDialog(self)
        if dialog.exec() == QDialog.Accepted:
            vm = dialog.get_vm()
            if vm:
                self.vm_list.append(vm)
                self.refresh_vm_list()
                self.status_bar.showMessage(tr("status_created", vm.name))
    
    def edit_vm(self):
        if not self.current_vm:
            QMessageBox.warning(self, tr("warning"), tr("msg_select_vm"))
            return
        
        dialog = CreateVMDialog(self, self.current_vm)
        if dialog.exec() == QDialog.Accepted:
            vm = dialog.get_vm()
            if vm:
                self.load_vms()
                self.refresh_vm_list()
                self.status_bar.showMessage(tr("status_updated", vm.name))
    
    def launch_vm(self):
        if not self.current_vm:
            QMessageBox.warning(self, tr("warning"), tr("msg_select_vm"))
            return
        
        launcher = BASE_DIR / "launcher.py"
        if not launcher.exists():
            QMessageBox.warning(self, tr("error"), tr("msg_launcher_missing", launcher))
            return
        
        try:
            subprocess.Popen(
                ["python", str(launcher), self.current_vm.name],
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )
            self.status_bar.showMessage(tr("status_launched", self.current_vm.name))
        except Exception as e:
            QMessageBox.warning(self, tr("error"), tr("msg_launch_failed", e))
    
    def delete_vm(self):
        if not self.current_vm:
            return
        
        reply = QMessageBox.question(
            self, tr("confirm"),
            f"确定要删除虚拟机 '{self.current_vm.name}' 吗？\n\n⚠️ 此操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No
        )
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
        self.status_bar.showMessage(tr("status_deleted"))
    
    def export_vm(self):
        if not self.current_vm:
            QMessageBox.warning(self, tr("warning"), tr("msg_select_vm"))
            return
        
        default_name = f"{self.current_vm.name}.mikan"
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("btn_export"), str(EXPORT_DIR / default_name),
            "Mikan 虚拟机包 (*.mikan)"
        )
        if not file_path:
            return
        
        if not file_path.endswith('.mikan'):
            file_path += '.mikan'
        
        reply = QMessageBox.question(self, tr("confirm"), 
            tr("msg_export_confirm", self.current_vm.name, file_path),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        
        self.status_bar.showMessage(tr("status_exporting", self.current_vm.name))
        
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
                self.status_bar.showMessage(tr("status_export_done", size_mb))
                QMessageBox.information(self, tr("success"), f"{tr('status_export_done', size_mb)}\n{file_path}")
            except Exception as e:
                self.status_bar.showMessage(tr("status_export_failed"))
                QMessageBox.warning(self, tr("error"), f"{tr('status_export_failed')}:\n{e}")
        
        Thread(target=do_export).start()
    
    def export_vm_as(self, format_type: str):
        """导出为指定格式"""
        if not self.current_vm:
            QMessageBox.warning(self, tr("warning"), tr("msg_select_vm"))
            return
        
        if format_type == "mikan":
            self.export_vm()
            return
        
        # 查找磁盘文件
        if self.current_vm.disks:
            disk_path = Path(self.current_vm.disks[0]["path"])
            disk_format = self.current_vm.disks[0]["format"]
        elif self.current_vm.disk_path:
            disk_path = Path(self.current_vm.disk_path)
            disk_format = self.current_vm.disk_format
        else:
            QMessageBox.warning(self, tr("error"), "虚拟机没有磁盘")
            return
        
        if not disk_path.exists():
            QMessageBox.warning(self, tr("error"), "磁盘文件不存在")
            return
        
        format_map = {"vmdk": ("vmdk", "VMDK"), "vdi": ("vdi", "VDI"), "vhdx": ("vhdx", "VHDX"), "raw": ("img", "RAW")}
        ext, desc = format_map.get(format_type, (format_type, format_type.upper()))
        
        qemu_img = find_qemu_img()
        if not qemu_img:
            QMessageBox.warning(self, tr("error"), tr("msg_qemu_img_not_found"))
            return
        
        zip_path, _ = QFileDialog.getSaveFileName(
            self, f"导出为 {desc}", str(EXPORT_DIR / f"{self.current_vm.name}_{format_type}.zip"),
            "ZIP 压缩包 (*.zip)"
        )
        if not zip_path:
            return
        
        self.status_bar.showMessage(f"⏳ 正在导出 {desc}...")
        
        def do_export():
            try:
                temp_disk = EXPORT_DIR / f"temp_{self.current_vm.name}.{ext}"
                subprocess.run([str(qemu_img), "convert", "-f", disk_format, "-O", format_type, 
                              str(disk_path), str(temp_disk)], check=True, capture_output=True, encoding='utf-8', errors='ignore')
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
                self.status_bar.showMessage(tr("status_export_done", size_mb))
                QMessageBox.information(self, tr("success"), f"{tr('status_export_done', size_mb)}\n{zip_path}")
            except Exception as e:
                self.status_bar.showMessage(tr("status_export_failed"))
                QMessageBox.warning(self, tr("error"), f"{tr('status_export_failed')}:\n{e}")
        
        Thread(target=do_export).start()
    
    def import_vm(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("btn_import"), str(EXPORT_DIR),
            "Mikan 虚拟机包 (*.mikan)"
        )
        if not file_path:
            return
        
        if not file_path.endswith('.mikan'):
            QMessageBox.warning(self, tr("error"), tr("msg_mikan_format"))
            return
        
        reply = QMessageBox.question(self, tr("confirm"), 
            tr("msg_import_confirm", Path(file_path).name),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        
        self.status_bar.showMessage(tr("status_importing"))
        
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
                    reply = QMessageBox.question(self, tr("confirm"), 
                        tr("msg_overwrite_confirm", vm_name),
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
                self.status_bar.showMessage(tr("status_import_done", vm_name))
                QMessageBox.information(self, tr("success"), tr("status_import_done", vm_name))
            except Exception as e:
                self.status_bar.showMessage(tr("status_import_failed"))
                QMessageBox.warning(self, tr("error"), f"{tr('status_import_failed')}:\n{e}")
        
        Thread(target=do_import).start()
    
    def manage_snapshots(self):
        if not self.current_vm:
            QMessageBox.warning(self, tr("warning"), tr("msg_select_vm"))
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
            QMessageBox.warning(self, tr("warning"), tr("msg_select_vm"))
            return
        
        reply = QMessageBox.question(self, tr("confirm"), 
            tr("msg_export_format_choose"),
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if reply == QMessageBox.Cancel:
            return
        
        is_windows = (reply == QMessageBox.Yes)
        ext = ".bat" if is_windows else ".sh"
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("btn_script"), str(BASE_DIR / f"{self.current_vm.name}_launch{ext}"),
            f"脚本文件 (*{ext})"
        )
        if not file_path:
            return
        
        try:
            from launcher import build_command
            cmd, error = build_command(self.current_vm.to_dict())
            if error:
                QMessageBox.warning(self, tr("error"), f"构建命令失败:\n{error}")
                return
            if is_windows:
                content = f"@echo off\nchcp 65001 >nul\necho 🚀 启动: {self.current_vm.name}\necho.\n{' '.join(cmd)}\npause\n"
            else:
                content = f"#!/bin/bash\necho \"🚀 启动: {self.current_vm.name}\"\necho\n{' '.join(cmd)}\nread -p \"按 Enter 退出...\"\n"
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            if not is_windows:
                os.chmod(file_path, 0o755)
            self.status_bar.showMessage(tr("status_export_script"))
            QMessageBox.information(self, tr("success"), tr("msg_script_exported", file_path))
        except ImportError:
            QMessageBox.warning(self, tr("error"), "找不到 launcher.py")
        except Exception as e:
            QMessageBox.warning(self, tr("error"), f"导出失败:\n{e}")
    
    def show_disk_manager(self):
        if not self.current_vm:
            QMessageBox.warning(self, tr("warning"), tr("msg_select_vm"))
            return
        
        QMessageBox.information(self, tr("btn_disk"), 
            "💾 磁盘管理功能已在虚拟机配置中集成\n\n"
            "请在「编辑」→ 硬件配置中调整磁盘设置\n"
            "包括: 磁盘大小、格式、接口等")
    
    def refresh(self):
        self.load_vms()
        self.refresh_vm_list()
        self.status_bar.showMessage(tr("status_refreshed"))
    
    def change_language(self, lang_code: str):
        self.translator.set_language(lang_code)
        self.refresh_ui_texts()
        self.status_bar.showMessage(f"🌐 语言已切换")
    
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
        QMessageBox.information(self, tr("menu_help_about"),
            f"📖 Mikan QEMU Manager v{APP_VERSION}\n\n"
            f"📦 {tr('btn_new')} - 创建虚拟机\n"
            f"✏️ {tr('btn_edit')} - 修改配置\n"
            f"📦 {tr('btn_export')} - 导出 .mikan 包\n"
            f"📤 {tr('btn_export_as')} - 导出为 VMDK/VDI/VHDX/RAW\n"
            f"📥 {tr('btn_import')} - 导入 .mikan 包\n"
            f"📸 {tr('btn_snapshot')} - 管理快照\n"
            f"📄 {tr('btn_script')} - 导出启动脚本\n"
            f"🚀 {tr('btn_launch')} - 启动虚拟机\n\n"
            "快捷键: F5刷新 | Delete删除 | Enter启动\n\n"
            "🔍 自动检测当前目录下所有QEMU版本\n"
            "⚡ 自动检测系统支持的硬件加速\n"
            "💻 根据选择的QEMU版本动态更新硬件列表\n"
            "🌐 支持多语言: 简体中文 / English"
        )
    
    def detect_system_hardware(self):
        """检测系统硬件信息 - 使用紧凑对话框"""
        self.status_bar.showMessage("🔍 正在检测系统硬件...")
        
        def worker():
            try:
                info = SystemDetector.get_system_info()
                
                # 构建文本
                text = "🖥️ 系统信息\n"
                text += "=" * 40 + "\n"
                for key, value in info.items():
                    text += f"{key}: {value}\n"
                
                # QEMU 硬件信息
                text += "\n\n🔍 QEMU 支持硬件\n"
                text += "=" * 40 + "\n"
                qemu_info = SystemDetector.get_qemu_supported_hardware()
                
                for category, items in qemu_info.items():
                    if items:
                        text += f"\n📌 {category}:\n"
                        for item in items:
                            if isinstance(item, dict):
                                text += f"  • {item.get('版本', '')} - {item.get('信息', '')}\n"
                            else:
                                text += f"  • {item}\n"
                
                # 通过信号回到主线程显示
                QMetaObject.invokeMethod(self, "show_detection_result", Qt.QueuedConnection, 
                                         Q_ARG(str, "🔍 系统检测结果"), Q_ARG(str, text))
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection, 
                                         Q_ARG(str, "✅ 系统检测完成"))
            except Exception as e:
                QMetaObject.invokeMethod(self, "show_error", Qt.QueuedConnection, 
                                         Q_ARG(str, f"检测失败:\n{e}"))
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection, 
                                         Q_ARG(str, f"❌ 检测失败: {e}"))
        
        Thread(target=worker).start()
    
    def detect_qemu_hardware(self):
        """检测 QEMU 硬件支持 - 使用紧凑对话框"""
        self.status_bar.showMessage("🔍 正在检测 QEMU 硬件支持...")
        
        def worker():
            try:
                qemu_info = SystemDetector.get_qemu_supported_hardware()
                
                text = "🔍 QEMU 硬件支持详情\n"
                text += "=" * 40 + "\n"
                
                # 检测到多少个 QEMU 版本
                qemu_versions = qemu_info.get("QEMU版本", [])
                if qemu_versions:
                    text += f"\n📦 检测到 {len(qemu_versions)} 个 QEMU 版本:\n"
                    for ver in qemu_versions:
                        text += f"  • {ver.get('版本', '')} ({ver.get('信息', '')})\n"
                else:
                    text += "\n⚠️ 未检测到 QEMU 版本\n"
                
                # 支持的加速器
                accels = qemu_info.get("可用加速器", [])
                if accels:
                    text += f"\n⚡ 支持的加速器:\n"
                    for accel in accels:
                        text += f"  • {accel}\n"
                
                # CPU型号（只显示前15个）
                cpus = qemu_info.get("支持CPU型号", [])
                if cpus:
                    text += f"\n💻 支持的 CPU 型号 ({len(cpus)}种):\n"
                    for cpu in cpus[:15]:
                        text += f"  • {cpu}\n"
                    if len(cpus) > 15:
                        text += f"  ... 还有 {len(cpus)-15} 种\n"
                
                # 显卡（只显示前10个）
                vgas = qemu_info.get("支持显卡", [])
                if vgas:
                    text += f"\n🖥️ 支持的显卡 ({len(vgas)}种):\n"
                    for vga in vgas[:10]:
                        text += f"  • {vga}\n"
                    if len(vgas) > 10:
                        text += f"  ... 还有 {len(vgas)-10} 种\n"
                
                # 机器类型（只显示前10个）
                machines = qemu_info.get("支持机器类型", [])
                if machines:
                    text += f"\n🏷️ 支持的机器类型 ({len(machines)}种):\n"
                    for machine in machines[:10]:
                        text += f"  • {machine}\n"
                    if len(machines) > 10:
                        text += f"  ... 还有 {len(machines)-10} 种\n"
                
                # 网络设备（只显示前10个）
                nets = qemu_info.get("支持网络设备", [])
                if nets:
                    text += f"\n🌐 支持的网络设备 ({len(nets)}种):\n"
                    for net in nets[:10]:
                        text += f"  • {net}\n"
                    if len(nets) > 10:
                        text += f"  ... 还有 {len(nets)-10} 种\n"
                
                # 音频设备（只显示前10个）
                audios = qemu_info.get("支持音频设备", [])
                if audios:
                    text += f"\n🔊 支持的音频设备 ({len(audios)}种):\n"
                    for audio in audios[:10]:
                        text += f"  • {audio}\n"
                    if len(audios) > 10:
                        text += f"  ... 还有 {len(audios)-10} 种\n"
                
                # USB设备（只显示前10个）
                usbs = qemu_info.get("支持USB设备", [])
                if usbs:
                    text += f"\n🔌 支持的 USB 设备 ({len(usbs)}种):\n"
                    for usb in usbs[:10]:
                        text += f"  • {usb}\n"
                    if len(usbs) > 10:
                        text += f"  ... 还有 {len(usbs)-10} 种\n"
                
                # 通过信号回到主线程显示
                QMetaObject.invokeMethod(self, "show_detection_result", Qt.QueuedConnection, 
                                         Q_ARG(str, "🔍 QEMU 硬件支持"), Q_ARG(str, text))
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection, 
                                         Q_ARG(str, "✅ QEMU 硬件检测完成"))
            except Exception as e:
                QMetaObject.invokeMethod(self, "show_error", Qt.QueuedConnection, 
                                         Q_ARG(str, f"检测失败:\n{e}"))
                QMetaObject.invokeMethod(self, "update_status", Qt.QueuedConnection, 
                                         Q_ARG(str, f"❌ 检测失败: {e}"))
        
        Thread(target=worker).start()
    
    @Slot(str, str)
    def show_detection_result(self, title: str, text: str):
        """显示检测结果 - 使用紧凑的自定义对话框（深色主题 + 滚动条）"""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(520, 400)  # 固定大小，紧凑
        
        # 深色主题
        dialog.setStyleSheet("""
            QDialog {
                background-color: #000000;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
                font-size: 12px;
                font-family: "Microsoft YaHei";
            }
            QScrollArea {
                background-color: #000000;
                border: 1px solid #333333;
                border-radius: 4px;
            }
            QScrollBar:vertical {
                background-color: #000000;
                width: 14px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #333333;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #444444;
            }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 13px;
                font-family: "Microsoft YaHei";
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # 内容滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)
        
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)  # 允许复制
        content_layout.addWidget(label)
        content_layout.addStretch()
        
        scroll.setWidget(content_widget)
        layout.addWidget(scroll, 1)
        
        # 关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton(tr("btn_close"))
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    @Slot(str)
    def update_status(self, message: str):
        """更新状态栏"""
        self.status_bar.showMessage(message)
    
    @Slot(str)
    def show_error(self, message: str):
        """显示错误"""
        QMessageBox.warning(self, tr("error"), message)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("Mikan QEMU Manager")
    app.setApplicationVersion(APP_VERSION)
    
    # 设置默认字体
    font = QFont("Microsoft YaHei", 11)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
