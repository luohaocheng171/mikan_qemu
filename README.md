[README.md](https://github.com/user-attachments/files/31579664/README.md)
# mikan_qemu
一个简单用python写的qemu管理器
# 🍊 Mikan QEMU：跨平台虚拟机管理利器

**Mikan QEMU** 是一款轻量级、开箱即用的 QEMU 虚拟机管理工具。项目由两个核心 Python 文件构成，旨在提供类似 VMware 的直观图形界面体验，同时具备强大的底层参数生成与多架构兼容能力。无论是进行跨平台开发、系统测试还是架构研究，Mikan QEMU 都能为你提供流畅的虚拟化体验。

---

## ✨ 核心功能特性

### 🚀 智能启动器 (`launcher.py` v9.0)

- **QEMU 功能自动检测**：智能识别 `grab_on_click`、`gl_on`、`window_size`、`audiodev`、`sandbox`、`no_shutdown`、`no_reboot`、`qmp`、`virtio_gpu` 等高级特性支持情况，根据 QEMU 版本动态启用功能。
- **28 种架构全覆盖**：支持 x86_64、x86、ARM64、ARM、RISC-V、RISC-V32、LoongArch、MIPS、MIPS64、PPC、PPC64、SPARC、SPARC64、Alpha、HPPA、SH4、XTENSA、M68K、MICROBLAZE、NIOS2、OR1K、UNICORE32 等主流及小众架构，并为每种架构提供默认的 machine、cpu、vga 及 display 配置。
- **智能参数生成**：根据 QEMU 版本年份（0.15 - 11.0）自动匹配 CPU 模型（qemu32/qemu64/host）、VGA 显卡（cirrus/std/virtio）及声卡（sb16/ac97/hda）参数，确保最佳兼容性。
- **路径自动修复**：自动处理 VM 配置中的路径问题，包括 Administrator 用户名替换、相对路径重新定位，以及自动重建磁盘列表，告别繁琐的手动配置。

### 🖥️ 图形化管理器 (`mikan_qemu.py` v5.0)

- **VMware 风格 GUI**：基于 PySide6 构建的现代化图形界面，支持多语言（内置简体中文），操作直观流畅。
- **一键环境部署**：首次启动自动检测并安装 `PySide6` 和 `psutil` 依赖，无需手动配置 Python 环境。
- **硬件加速感知**：自动扫描并适配 WHPX (Hyper-V)、HAXM、KVM、HVF 及 TCG 软件模拟，智能选择最优加速方案。
- **全生命周期管理**：提供虚拟机的创建、启动、停止、删除及 ZIP 格式导出功能，管理便捷。
- **快照与 ISO 管理**：支持快照的创建、加载与删除；提供便捷的 ISO 镜像挂载/卸载功能。
- **实时性能监控**：基于 `psutil` 实时展示 CPU、内存、网络及磁盘 I/O 状态，掌握虚拟机运行状况。
- **QEMU 硬件深度探测**：自动检测设备列表、VGA 类型、显示后端、机器类型、CPU 模型、加速器、网络后端、音频设备、固件类型及块设备驱动。

---

## 🏗️ 架构与工作流程

Mikan QEMU 采用前后端分离的设计思想，`launcher.py` 作为底层引擎负责复杂的参数计算与硬件探测，`mikan_qemu.py` 作为前端界面负责用户交互与任务调度。

```
[用户操作] --> [mikan_qemu.py (GUI / 生命周期管理)]
                        |
                        v
              [launcher.py (参数生成 / 架构适配)]
                        |
                        v
              [QEMU 进程 (虚拟化执行)]
```

---

## 📦 安装与运行

### 环境要求

| 项目 | 要求 |
|:---|:---|
| Python | 3.8+ |
| 操作系统 | Windows / Linux / macOS |
| QEMU | 需本地安装 QEMU 可执行文件（放置于 `qemu*` 目录） |

### 快速启动

```bash
# 克隆项目
git clone <repository-url>
cd Mikan-QEMU

# 运行主程序（首次运行将自动安装 PySide6 和 psutil 依赖）
python mikan_qemu.py
```

> **提示**：程序启动时会自动检查 `PySide6` 和 `psutil`，若缺失将通过 `pip` 自动安装，无需手动配置环境。如遇网络问题导致自动安装失败，可手动执行 `pip install PySide6 psutil`。

### 手动安装依赖

```bash
pip install PySide6 psutil
python mikan_qemu.py
```

---

## 📂 项目目录结构

```
Mikan-QEMU/
├── launcher.py              # 启动器核心（参数生成、架构配置）
├── mikan_qemu.py            # 主程序（GUI 管理器）
├── vms/                     # 虚拟机配置文件目录
│   └── <vm_name>/
│       ├── config.json      # 虚拟机配置 (JSON)
│       └── disk.qcow2       # 磁盘镜像文件
├── iso/                     # ISO 镜像存放目录
├── snapshots/               # 虚拟机快照目录
├── exports/                 # 虚拟机导出 (ZIP) 目录
├── config/                  # 全局应用配置
├── share/                   # 共享资源目录
└── qemu*/                   # QEMU 可执行文件目录（需用户自行放置）
```

---

## ⚙️ 配置说明

虚拟机配置采用 JSON 格式存储于 `vms/<vm_name>/config.json`，支持以下高级配置项：

| 配置项 | 说明 |
|:---|:---|
| `disk_path` / `disks` | 磁盘路径与多磁盘配置（支持 qcow2 格式、缓存策略、接口类型） |
| `boot_iso` / `kernel_iso` | 启动 ISO 镜像路径 |
| `driver_iso` | 驱动 ISO 路径（用于安装 VirtIO 驱动等） |
| `bios_file` | BIOS/UEFI 固件文件路径 |
| `share_dir` | 共享目录路径 |
| `log_file` | 日志文件路径 |
| `memory` | 内存大小（MB） |
| `vcpus` | CPU 核心数 |
| `network` | 网络配置（后端类型、MAC 地址） |
| `usb` | USB 设备直通配置 |
| `display` | 显示后端与分辨率设置 |

> **提示**：首次创建虚拟机时，可通过 GUI 界面填写配置项；高级用户也可直接编辑 `config.json` 文件进行精细调整。

---

## 🌐 支持的 QEMU 架构

| 架构系列 | 支持的架构 |
|:---|:---|
| **x86 系列** | x86_64、x86 |
| **ARM 系列** | ARM64、ARM |
| **RISC-V** | RISC-V、RISC-V32 |
| **MIPS 系列** | MIPS、MIPS64 |
| **PowerPC** | PPC、PPC64 |
| **SPARC** | SPARC、SPARC64 |
| **其他架构** | LoongArch、Alpha、HPPA、SH4、XTENSA、M68K、MICROBLAZE、NIOS2、OR1K、UNICORE32 |

> 共支持 **28 种** CPU 架构，覆盖从嵌入式到服务器级的广泛场景。

---

## ⚡ 硬件加速支持

| 操作系统 | 支持的加速器 | 说明 |
|:---|:---|:---|
| **Windows** | WHPX (Hyper-V)、HAXM | 自动检测 Hyper-V 和 HAXM 状态 |
| **Linux** | KVM | 需确保 `/dev/kvm` 存在且有读写权限 |
| **macOS** | HVF | Apple 原生虚拟化框架 |
| **全平台** | TCG | 软件模拟回退方案（性能较低） |

> 程序启动时会自动检测当前系统可用的硬件加速方案，并优先使用性能最优的加速器。若未检测到任何硬件加速，将自动降级为 TCG 软件模拟。

---

## 🛠️ 技术栈

| 组件 | 技术选型 |
|:---|:---|
| **GUI 框架** | PySide6 (Qt6) |
| **虚拟化后端** | QEMU |
| **系统监控** | psutil |
| **配置格式** | JSON |
| **打包格式** | ZIP |
| **进程管理** | QProcess (Qt) |
| **多线程** | QThread / threading |

---

## 📸 界面预览

> Mikan QEMU 提供 VMware 风格的图形界面，包含虚拟机列表、控制台窗口、性能监控面板及配置管理面板。

| 功能模块 | 说明 |
|:---|:---|
| **虚拟机列表** | 左侧面板展示所有已创建的虚拟机，支持搜索和排序 |
| **控制台窗口** | 实时显示 QEMU 进程的 stdout/stderr 输出 |
| **性能监控** | 实时展示 CPU 使用率、内存占用、网络流量、磁盘 I/O |
| **配置面板** | 图形化配置 CPU、内存、磁盘、网络、USB、显示等参数 |
| **快照管理** | 创建、加载、删除虚拟机快照 |

---

## 🐛 常见问题

### 1. 首次运行提示依赖安装失败

确保网络连接正常，程序会自动通过 `pip` 安装 `PySide6` 和 `psutil`。如仍失败，请手动执行：

```bash
pip install PySide6 psutil
```

### 2. 无法检测到 QEMU

请将 QEMU 可执行文件（如 `qemu-system-x86_64.exe`）放置在项目根目录下的 `qemu` 或 `qemu-xxx` 文件夹中，程序会自动扫描。

### 3. 性能较差

检查是否成功启用了硬件加速（KVM / WHPX / HVF）。可在性能监控面板中查看当前使用的加速器类型。若使用 TCG 模拟，性能会显著下降。

### 4. 虚拟机无法启动

- 检查 `vms/<vm_name>/config.json` 中的磁盘路径是否正确
- 查看控制台窗口的错误输出
- 确认 QEMU 版本与配置参数兼容

### 5. 中文乱码（Windows）

程序已内置 Windows 编码修复逻辑。如仍有乱码，请确保终端支持 UTF-8：

```bash
# 在 PowerShell 中运行
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

---

## 🤝 贡献指南

欢迎提交 Issue 或 Pull Request 来改进 Mikan QEMU！

1. **Fork** 本仓库
2. 创建特性分支：`git checkout -b feature/AmazingFeature`
3. 提交更改：`git commit -m 'Add some AmazingFeature'`
4. 推送分支：`git push origin feature/AmazingFeature`
5. 开启 **Pull Request**

---

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源，详情请参阅 LICENSE 文件。

---

## 🙏 致谢

- [QEMU](https://www.qemu.org/) — 强大的开源机器模拟与虚拟化技术
- [PySide6](https://www.qt.io/qt-for-python) — Qt6 的 Python 绑定
- [psutil](https://github.com/giampaolo/psutil) — 跨平台进程和系统监控工具
