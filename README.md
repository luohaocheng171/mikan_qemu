[README (2).md](https://github.com/user-attachments/files/31589334/README.2.md)
# Mikan QEMU Manager & Launcher

> **AI 辅助生成项目** — 核心脚本由 **DeepSeek（深度求索）AI** 辅助生成，经人工审核与调整。
> **开源协议** — 本项目严格遵循 **GNU General Public License v3.0 (GPL-3.0)**。

---

## 目录

1. [项目简介](#-项目简介)
2. [核心特性](#-核心特性)
3. [组件说明](#-组件说明)
4. [支持的 CPU 架构](#-支持的-cpu-架构)
5. [CPU 指令集管理](#-cpu-指令集管理)
6. [环境要求](#-环境要求)
7. [快速开始](#-快速开始)
8. [目录结构](#-目录结构)
9. [配置说明](#-配置说明)
10. [开发指南](#-开发指南)
11. [常见问题 (FAQ)](#-常见问题-faq)
12. [贡献代码](#-贡献代码)
13. [许可证](#-许可证)
14. [免责声明](#-免责声明)

---

## 项目简介

本项目是一套基于 **QEMU** 的虚拟机管理工具集，提供 VMware 风格的图形化界面，支持 **27 种 CPU 架构** 的虚拟机创建、启动、快照管理、U 盘挂载、鼠标切换和性能监控等功能。

项目由两个核心脚本组成：

- **launcher.py**（v9.0）— QEMU 虚拟机启动器，负责虚拟机的完整生命周期管理，包括配置解析、QEMU 参数构建、进程控制、快照操作、QMP 监控等。
- **mikan_qemu.py**（v5.1）— 虚拟机管理器，提供完整的 VMware 风格 UI，内置 **CPU 指令集管理菜单**（覆盖 2011-2026 年共 16 个年份的 x86/x86_64 指令集配置文件），支持自定义指令集的创建、编辑和删除。

适用于：

- 🖥️ **多架构虚拟化**：在 x86_64 主机上运行 ARM、RISC-V、MIPS、PPC、SPARC 等异构架构的虚拟机。
- 🧪 **操作系统开发**：快速启动不同架构和指令集版本的测试环境。
- 🔄 **兼容性测试**：通过切换 CPU 指令集模拟不同年代硬件。
- 📦 **嵌入式开发**：支持 LoongArch、RISC-V、MIPS 等嵌入式架构的交叉编译与调试。

---

## 核心特性

### 通用特性

- **VMware 风格 UI** — 基于 PySide6 (Qt6) 构建的现代化图形界面，操作直观。
- **多架构支持** — 内置 27 种 CPU 架构的默认配置（机器类型、CPU 模型、VGA、显示后端）。
- **QEMU 版本自动检测** — 自动扫描项目目录下的 QEMU 可执行文件，根据架构匹配正确的二进制。
- **QEMU 功能自动探测** — 启动时自动检测 QEMU 支持的显示后端特性（grab-on-click、gl、window-size、audiodev、sandbox、qmp 等）。
- **自动路径修复** — 智能修复虚拟机配置中的路径问题（如用户名变更、路径迁移）。
- **快照管理** — 创建、列出、恢复、删除虚拟机快照。
- **U 盘挂载** — 支持可移动存储设备的挂载与弹射。
- **鼠标切换** — 支持鼠标捕获/释放切换，兼容多种输入模式。
- **性能监控** — 实时监控虚拟机的 CPU、内存、磁盘 I/O 和网络 I/O。
- **QMP 监控** — 通过 QEMU Monitor Protocol 进行高级管理和调试。

### mikan_qemu.py 特有功能

- **CPU 指令集管理** — 独立的指令集管理菜单，支持创建、编辑、删除自定义 CPU 配置文件。
- **内置 16 个年份指令集** — 从 2011 年 Nehalem 到 2026 年最新指令集，覆盖 Intel/AMD 主要微架构。
- **自动依赖安装** — 启动时自动检测并安装缺失的 Python 依赖包（PySide6、psutil）。
- **配置文件管理** — 每个虚拟机拥有独立的 config.json 配置文件，支持磁盘、ISO、BIOS 等完整配置。

---

## 组件说明

### launcher.py — QEMU 虚拟机启动器 (v9.0)

负责虚拟机的完整生命周期管理：

| 功能模块 | 说明 |
| :--- | :--- |
| `get_qemu_features()` | 自动探测 QEMU 二进制支持的功能特性（显示、音频、沙箱、QMP 等） |
| `fix_vm_config_paths()` | 自动修复虚拟机配置文件中的路径问题（用户名替换、相对路径定位） |
| `auto_fix_all_vms()` | 批量修复所有虚拟机的配置路径 |
| `get_qemu_year()` | 从 QEMU 版本号字符串中提取年份，支持多种版本号格式 |
| `get_qemu_exe()` | 根据架构和版本自动定位 QEMU 可执行文件 |
| `get_arch_defaults()` | 为 27 种 CPU 架构提供默认机器类型、CPU 模型、VGA 和显示后端配置 |

### mikan_qemu.py — 虚拟机管理器 (v5.1)

提供完整的图形化管理界面：

| 功能模块 | 说明 |
| :--- | :--- |
| `check_and_install_dependencies()` | 启动时自动检查并安装 PySide6、psutil 依赖 |
| `CPUProfileManager` | 指令集管理器，加载内置 + 自定义 CPU 配置文件 |
| `CPUProfileEditDialog` | 创建/编辑指令集的对话框界面 |
| `BUILTIN_CPU_PROFILES` | 内置 16 个年份的 x86/x86_64 指令集定义（2011-2026） |

---

## 支持的 CPU 架构

launcher.py 内置支持以下 **27 种 CPU 架构** 的默认配置：

| 架构 | 机器类型 | 默认 CPU 模型 |
| :--- | :--- | :--- |
| x86_64 | q35 | host |
| x86 | pc | qemu64 |
| ARM64 | virt | cortex-a72 |
| ARM | virt | cortex-a15 |
| RISC-V | virt | rv64 |
| RISC-V32 | virt | rv32 |
| LoongArch | virt | la64 |
| MIPS | malta | mips32r5 |
| MIPS64 | malta | mips64r5 |
| PPC | mac99 | G4 |
| PPC64 | pseries | POWER9 |
| SPARC | SS-5 | Fujitsu-MB86904 |
| SPARC64 | sun4u | UltraSPARC-IIi |
| Alpha | clipper | ev67 |
| HPPA | hppa | PA-7100 |
| S390X | s390-ccw-virtio | host |
| SH4 | r2d | sh4 |
| XTENSA | (自定义) | (自定义) |
| M68K | (自定义) | (自定义) |
| MICROBLAZE | (自定义) | (自定义) |
| NIOS2 | (自定义) | (自定义) |
| OR1K | (自定义) | (自定义) |
| CRIS | (自定义) | (自定义) |
| HEXAGON | (自定义) | (自定义) |
| AVR | (自定义) | (自定义) |
| RX | (自定义) | (自定义) |
| TRICORE | (自定义) | (自定义) |
| UNICORE32 | (自定义) | (自定义) |

---

## CPU 指令集管理

mikan_qemu.py 内置了从 2011 年到 2026 年的 **16 个 x86/x86_64 CPU 指令集配置文件**，覆盖 Intel 和 AMD 的主要微架构：

| 年份 | CPU 模型 | 关键指令集 |
| :--- | :--- | :--- |
| 2011 | Nehalem | +aes, +avx |
| 2012 | Westmere | +aes, +avx, +rdrand |
| 2013 | SandyBridge | +aes, +avx, +rdrand, +f16c |
| 2014 | Haswell | +aes, +avx, +avx2, +bmi1, +bmi2, +f16c, +fma, +rdrand |
| 2015 | Broadwell | +aes, +avx, +avx2, +bmi1, +bmi2, +f16c, +fma, +rdrand, +rdseed |
| 2016 | Skylake-Client | +aes, +avx, +avx2, +bmi1, +bmi2, +f16c, +fma, +rdrand, +rdseed, +sha-ni, +xsave |
| 2017 | Skylake-Client | 同 2016（Skylake 架构 2017 更新） |
| 2018 | CascadeLake | 同 2016 + AVX-512 系列指令集 |
| 2019 | CascadeLake | 同 2018 |
| 2020 | Cooperlake | 同 2018（Cooper Lake 架构） |
| 2021 | EPYC | +aes, +avx, +avx2, +bmi1, +bmi2, +f16c, +fma, +rdrand, +rdseed, +sha-ni, +xsave |
| 2022 | EPYC | 同 2021 + AVX-512 系列指令集 |
| 2023 | EPYC | 同 2022 |
| 2024 | host | 同 2022（最新指令集） |
| 2025 | host | 同 2022（最新指令集） |
| 2026 | host | 同 2022（最新指令集） |

### 自定义指令集

用户可以在 `cpu_profiles/custom/` 目录下放置 JSON 格式的自定义指令集配置文件，格式如下：

```json
{
    "name": "my_custom_cpu",
    "year": 2026,
    "cpu_model": "host",
    "flags": "+aes,+avx,+avx2,+avx512f",
    "description": "My custom CPU profile"
}
```

自定义指令集会自动被 `CPUProfileManager` 扫描加载，与内置指令集共存（名称冲突时以内置为准）。

---

## 环境要求

| 依赖项 | 最低版本 | 说明 |
| :--- | :--- | :--- |
| **Python** | `3.9+` | 推荐使用 `3.11` 以获得最佳性能 |
| **QEMU** | `4.0+` | 需下载对应架构的 QEMU 二进制，放入项目目录 |
| **PySide6** | `6.0+` | Qt6 Python 绑定（mikan_qemu.py 自动安装） |
| **psutil** | `5.0+` | 系统性能监控（mikan_qemu.py 自动安装） |
| **OS** | Linux / macOS / Windows (WSL2) | Windows 原生支持有限，推荐 WSL2 |

### QEMU 二进制放置

将 QEMU 压缩包解压到项目根目录，按版本命名文件夹，例如：

```
qemu-w64-setup-20190815/
qemu-w64-setup-20251224/
```

脚本会自动扫描这些目录并匹配正确的 QEMU 二进制文件。

---

## 快速开始

### 1. 克隆/下载项目

```bash
git clone https://github.com/your-username/mikan-qemu.git
cd mikan-qemu
```

### 2. 安装依赖

mikan_qemu.py 会在首次启动时自动检测并安装缺失的依赖包。如需手动安装：

```bash
pip install PySide6 psutil
```

### 3. 放置 QEMU 二进制

下载 QEMU Windows 静态构建版，解压到项目根目录：

```
mikan-qemu/
├── launcher.py
├── mikan_qemu.py
├── qemu-w64-setup-20251224/
│   ├── qemu-system-x86_64.exe
│   ├── qemu-system-aarch64.exe
│   └── ...
└── vms/
```

### 4. 运行

```bash
# 启动虚拟机启动器
python launcher.py

# 启动完整管理器（含指令集管理菜单）
python mikan_qemu.py
```

### 5. 创建虚拟机

1. 在 UI 中点击"新建虚拟机"
2. 选择架构（如 x86_64、ARM64、RISC-V 等）
3. 配置磁盘、ISO 镜像、内存、CPU 核心数
4. 选择 CPU 指令集年份（mikan_qemu.py）
5. 点击"启动"

---

## 目录结构

```
mikan-qemu/
├── launcher.py                  # QEMU 虚拟机启动器 (v9.0)
├── mikan_qemu.py                # 虚拟机管理器 (v5.1)
├── README.md                    # 项目说明文档
├── LICENSE                      # GPL-3.0 许可证全文
├── vms/                         # 虚拟机配置文件目录
│   ├── <vm_name>/
│   │   ├── config.json          # 虚拟机配置
│   │   ├── disk.qcow2           # 磁盘镜像
│   │   └── ...
├── iso/                         # ISO 镜像存放目录
├── snapshots/                   # 快照存储目录
├── exports/                     # 导出目录
├── config/                      # 全局配置目录
├── share/                       # 共享目录
├── cpu_profiles/                # CPU 指令集配置文件目录
│   ├── profiles.json            # 指令集索引
│   └── custom/                  # 自定义指令集 JSON 文件
└── <qemu_version>/              # QEMU 二进制目录（按版本命名）
    ├── qemu-system-x86_64.exe
    ├── qemu-system-aarch64.exe
    └── ...
```

---

## 配置说明

### 虚拟机配置文件 (config.json)

每个虚拟机在 `vms/<vm_name>/config.json` 中保存完整配置，主要字段包括：

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `name` | string | 虚拟机名称 |
| `arch` | string | CPU 架构（如 x86_64、ARM64） |
| `disk_path` | string | 主磁盘镜像路径 |
| `disks` | array | 多磁盘配置列表 |
| `boot_iso` | string | 启动 ISO 镜像路径 |
| `kernel_iso` | string | 内核 ISO 路径 |
| `driver_iso` | string | 驱动 ISO 路径 |
| `backing_file` | string | 磁盘后备文件（增量快照） |
| `bios_file` | string | BIOS 文件路径 |
| `share_dir` | string | 共享目录路径 |
| `log_file` | string | 日志文件路径 |
| `memory` | int | 内存大小（MB） |
| `cpus` | int | CPU 核心数 |
| `cpu_model` | string | CPU 模型 |
| `cpu_flags` | string | CPU 指令集标志 |
| `display` | string | 显示后端 |
| `vga` | string | VGA 类型 |

### 自动路径修复

launcher.py 内置智能路径修复机制：

- **用户名替换**：自动将配置中的 `Administrator` 替换为当前登录用户。
- **相对路径定位**：当磁盘/后备文件路径不存在时，自动在虚拟机目录 `vms/<vm_name>/` 下查找同名文件。
- **disks 列表重建**：当配置中缺少 `disks` 数组但有 `disk_path` 时，自动重建标准磁盘列表。

---

## 开发指南

### 项目结构说明

- **launcher.py** — 启动器核心，负责 QEMU 进程管理、配置解析、快照操作。建议在此基础上扩展新的虚拟机管理功能。
- **mikan_qemu.py** — 管理器 UI，包含完整的图形界面和指令集管理。适合需要完整管理功能的场景。

### 代码规范

- 遵循 PEP 8 编码规范
- 使用类型提示（type hints）
- 关键函数包含 docstring
- 中文注释使用 UTF-8 编码

### 添加新架构支持

在 `launcher.py` 的 `get_arch_defaults()` 函数中添加新架构的默认配置：

```python
"NEW_ARCH": {"machine": "default_machine", "cpu": "default_cpu", "vga": "virtio", "display": "gtk"},
```

同时在 `get_qemu_exe()` 的 `arch_map` 中添加对应的 QEMU 二进制文件名。

### 添加新指令集

在 `mikan_qemu.py` 的 `BUILTIN_CPU_PROFILES` 字典中添加新年份的指令集定义，或在 `cpu_profiles/custom/` 目录下放置 JSON 文件。

---

## 常见问题 (FAQ)

**Q: 启动虚拟机时提示 QEMU 二进制未找到？**

A: 请确保已将 QEMU 静态构建版解压到项目根目录，文件夹名包含版本号（如 `qemu-w64-setup-20251224`），脚本会自动扫描匹配。

**Q: 鼠标无法捕获/释放？**

A: 确保 QEMU 版本支持 `grab-on-click` 功能。可在 UI 中查看 QEMU 功能检测结果。

**Q: 如何切换 CPU 指令集？**

A: 在 mikan_qemu.py 的虚拟机配置界面中，选择"CPU 指令集"选项，从下拉列表中选择目标年份对应的指令集配置。

**Q: 自定义指令集不生效？**

A: 检查 `cpu_profiles/custom/` 目录下的 JSON 文件格式是否正确，确保包含 `name`、`year`、`cpu_model`、`flags` 字段。自定义指令集名称不能与内置指令集冲突。

**Q: 可以在商业项目中使用吗？**

A: **可以**，但必须遵守 **GPL-3.0** 协议。如果你的项目分发了本项目的修改版或链接了本项目的代码，你的整个项目也必须以 GPL-3.0 开源。

**Q: API Key 泄露了怎么办？**

A: 本项目不涉及 API Key。如有配置文件中的敏感信息，请立即从 Git 历史中清除（使用 `git filter-repo`）。

---

## 贡献代码

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'feat: Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

> **注意**：所有贡献者需在 PR 描述中确认：*"我确认本次提交不包含未授权的闭源代码，且同意以 GPL-3.0 协议发布。"*

---

## 许可证

本项目基于 **GNU General Public License v3.0** 开源。

```
Copyright (C) 2024 [Your Name/Organization]

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```

👉 [查看完整 LICENSE 文件](./LICENSE)

---

## 免责声明

1. **AI 生成内容**：本项目脚本由 DeepSeek AI 生成，尽管经过人工审核，但**不保证 100% 无误**。
2. **生产环境**：请在**测试环境**充分验证后再用于生产环境。作者不对因使用本脚本导致的任何数据丢失、服务中断或经济损失负责。
3. **合规责任**：用户需自行确保 AI 生成内容符合当地法律法规及公司合规要求。
4. **QEMU 依赖**：本项目依赖 QEMU 虚拟机模拟器，请确保从官方渠道下载 QEMU 二进制文件，并遵守 QEMU 的开源许可证。

---

<div align="center">

**Made with ❤️ & 🤖 by DeepSeek Community**

[⬆ 返回顶部](#-mikan-qemu-manager--launcher)

</div>
