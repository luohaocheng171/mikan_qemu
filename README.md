# Mikan QEMU 工具箱

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)](https://www.qt.io/qt-for-python)

> QEMU 虚拟机全功能管理套件 — 图形化硬件配置管理 + 智能窗口追踪启动器

本仓库包含两个紧密协作的 QEMU 管理工具：

| 工具 | 版本 | 说明 |
|------|------|------|
| Mikan QEMU Manager | v5.5 | VMware 风格 UI 的完整 QEMU 虚拟机管理器，支持硬件配置预设、多文件夹管理、自定义路径、内存磁盘调优、硬件直通等 |
| Mikan QEMU Launcher | v14.2 | 侧边栏跟随 QEMU 窗口的智能启动器，支持多文件夹绑定、自定义 QEMU 路径、非阻塞功能检测、全异步命令构建 |

---

## 项目介绍

### Mikan QEMU Manager v5.5

Mikan QEMU Manager 是一款基于 Python 和 PySide6 开发的 QEMU 虚拟机管理器桌面应用程序，采用 VMware 风格图形界面。提供完整的硬件配置预设系统（内置 2011-2024 年各时代硬件配置 + 自定义配置），支持 CPU 型号/指令集、显卡/显示后端、声卡/网卡、磁盘接口、机器类型、加速模式、USB 控制器等全维度硬件参数调优。内置多文件夹管理（config/folders.json），可切换不同 QEMU 安装目录和虚拟机工作区，支持自定义 QEMU 路径、内存盘回退、硬件直通等高级功能。

### Mikan QEMU Launcher v14.2

Mikan QEMU Launcher 是一款智能 QEMU 启动器，核心能力是自动追踪 QEMU 窗口（GTK/SDL）并实现侧边栏跟随。支持多文件夹绑定（从 config/folders.json 读取）、自定义 QEMU 路径、build_command 覆盖主编辑器 v5.5 所有字段。v14.2 版本引入非阻塞 QEMU features 检测 + 文件缓存 + build_command 全异步（UI 不卡），支持多架构（x86_64/x86/ARM64/ARM/RISC-V）自动识别与可执行文件查找。

---

## 功能特性

### Mikan QEMU Manager v5.5

#### 硬件配置管理

- **内置硬件预设**：10 套内置配置覆盖 2011-2024 年各时代硬件（retro_2011、retro_2013、transition_2016、modern_2019、latest_2024、epyc_2023、minimal、macos、android、linux_server）
- **自定义配置**：创建/编辑/删除自定义硬件配置文件（JSON 持久化）
- **CPU 配置**：支持 40+ CPU 型号（host、qemu64、Opteron系列、EPYC系列、Skylake系列、SandyBridge系列、Haswell系列、Broadwell系列等），自定义指令集标志
- **显卡配置**：virtio/std/cirrus/vmvga/qxl/bochs/ramfb/sga/none，显示后端 gtk/sdl/none/curses/spice/egl-headless
- **声卡配置**：hda/ac97/sb16/ich9-intel-hda/ich9-hda/cs4231a/gus/intel-hda/isa/pcspk/pl041/none
- **网卡配置**：virtio/e1000/rtl8139/pcnet/e1000e/vmxnet3/usb-net/ne2k_pci
- **磁盘接口**：ide/sata/virtio/scsi/nvme/usb/sd/floppy
- **机器类型**：pc/q35/virt/microvm 及各版本兼容型号
- **加速模式**：tcg/hax/whpx/kvm/hvf/qtest/none
- **USB 控制器**：none/piix3-usb-uhci/usb-ehci/usb-ohci/usb-uhci/usb-xhci/nec-usb-xhci

#### 多文件夹管理

- 支持多个工作文件夹绑定（config/folders.json）
- 每个文件夹独立配置 QEMU 路径
- 活动文件夹切换，自动重建目录结构（vms/iso/snapshots/exports/share/hardware_profiles）
- 配置文件随文件夹切换自动加载

#### 设置与配置

- JSON 持久化配置（settings.json）
- 自定义 QEMU 可执行文件路径
- 各虚拟机独立配置（config.json）
- 硬件配置文件导入导出

#### UI 特性

- VMware 风格扁平化 UI
- 硬件配置管理对话框（多 Tab 页：基本信息/CPU/显卡显示/声音网络/主板存储）
- 硬件配置列表（内置/自定义分组显示）
- 实时详情面板展示选中配置的完整参数

#### 其他特性

- 自动依赖检查与安装（PySide6、psutil）
- 管理员权限检测
- UTF-8 编码自动适配（Windows）
- 异步 Worker 线程（不阻塞 UI）

---

### Mikan QEMU Launcher v14.2

#### 窗口追踪与跟随

- **GTK 窗口追踪**：自动枚举 Windows 窗口，通过类名（gdkWindowToplevel/gtk/GDK）和标题关键词（QEMU/qemu）匹配，支持 psutil 进程名验证
- **SDL 窗口追踪**：类似机制追踪 SDL 后端窗口（SDL/SDL_app/SDL_window 类名）
- **窗口矩形获取**：获取窗口位置、大小（GetWindowRect）
- **全屏检测**：通过窗口样式位判断是否全屏
- **置顶控制**：SetWindowPos + SetForegroundWindow 将窗口置顶

#### 多文件夹与路径管理

- 从 config/folders.json 读取所有绑定文件夹
- 自动扫描所有绑定文件夹的 vms 目录
- 自定义 QEMU 路径优先级最高（config.json 的 custom_qemu_path）
- 支持文件夹级 qemu_path 配置

#### QEMU 智能检测

- **版本识别**：从版本字符串中提取年份（2011-2026），支持日期格式（YYYYMMDD）
- **架构适配**：x86_64/x86/ARM64/ARM/RISC-V 自动选择对应可执行文件名
- **可执行文件查找**：多级优先级搜索（custom_qemu_path > folders.json qemu_path > 绑定文件夹扫描 > BASE_DIR > PATH）
- **功能检测（v14.2 增强）**：
  - 非阻塞执行（subprocess + timeout 强制 kill）
  - 内存缓存（_qemu_features_cache）
  - 文件缓存（qemu_features_cache.json，按 mtime 失效）
  - 检测项目：grab_on_click、window_size、audiodev、sdl、gtk、qmp、mem_path、memory_backend_file、vfio_pci、usb_host、whpx、hax、kvm、hvf、accel_option

#### 命令构建引擎（build_command）

- **内存配置**：基础内存、内存后备（memory-backend-file / mem-path）
- **CPU/SMP 配置**：sockets/cores/threads 多维配置、maxcpus 计算、CPU 型号年份自适应、自定义指令集标志
- **磁盘配置**：qcow2/raw/img/vmdk 格式自动检测、多种接口（virtio/sata/nvme/scsi/ide）、缓存模式、AIO 模式、discard/unmap、快照模式
- **启动配置**：磁盘启动/网络启动/光盘启动、启动顺序、一次性启动设备
- **显示配置**：VGA 型号年份自适应、GTK/SDL 后端自动切换、分辨率设置、grab-on-click、OpenGL 加速
- **声卡配置**：audiodev 模式（dsound/coreaudio/pa）+ 传统 soundhw 回退
- **USB 配置**：USB 控制器开关、USB 鼠标、USB 设备直通（vendor_id/product_id）
- **网络配置**：user/bridge 模式、SMB 共享、端口转发、子网/DNS 限制、TAP 桥接
- **机器类型**：年份自适应（q35/pc）、ACPI 开关、HPET 开关
- **ISO 挂载**：启动 ISO + 驱动 ISO 双光盘支持

#### UI 特性

- 侧边栏跟随 QEMU 窗口位置
- 非阻塞架构（UI 不卡）
- 异步命令构建

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.8+ |
| GUI 框架 | PySide6 (Qt for Python) |
| 系统交互 | subprocess、ctypes（Windows API）、socket |
| 配置存储 | JSON 文件（settings.json / folders.json / config.json） |
| 进程管理 | QProcess（Launcher）、subprocess（Manager） |
| 路径管理 | pathlib |
| 并发模型 | threading.Thread + QThread |
| 窗口追踪 | ctypes.windll.user32（EnumWindows/GetWindowText/GetWindowRect 等） |
| 进程检测 | psutil |
| UI 样式 | 自定义 QSS 主题 |

---

## 安装与运行

### 环境要求

- Windows 10/11（推荐）/ Linux / macOS
- Python 3.8 或更高版本
- QEMU 已安装（Manager 和 Launcher 均依赖外部 QEMU）

### 安装依赖

```
pip install PySide6 psutil
```

### 运行程序

**Mikan QEMU Manager v5.5：**

```
python mikan_qemu.py
```

首次运行自动检测并安装缺失依赖（PySide6、psutil）。

**Mikan QEMU Launcher v14.2：**

```
python launcher.py
```

Launcher 会自动读取 Manager 的 config/folders.json 配置文件，无需额外配置。

### 配置文件说明

| 文件 | 说明 |
|------|------|
| config/folders.json | 多文件夹绑定配置（两个工具共用） |
| config/settings.json | Manager 用户设置 |
| config/qemu_features_cache.json | Launcher QEMU 功能检测缓存（v14.2 新增） |
| vms/<vm_name>/config.json | 各虚拟机独立配置 |

---

## 项目结构

```
mikan_qemu.py              # Mikan QEMU Manager v5.5 主程序（单文件应用）
launcher.py                # Mikan QEMU Launcher v14.2 主程序（单文件应用）
├── config/                # 配置目录（两个工具共用）
│   ├── folders.json       # 多文件夹绑定配置
│   ├── settings.json      # Manager 设置
│   └── qemu_features_cache.json  # Launcher 功能检测缓存
├── vms/                   # 虚拟机目录（按虚拟机名称分文件夹）
│   └── <vm_name>/
│       ├── config.json    # 虚拟机配置
│       ├── disk.qcow2     # 磁盘文件
│       └── ...
├── iso/                   # ISO 镜像目录
├── snapshots/             # 快照目录
├── exports/               # 导出目录
├── share/                 # 共享目录
└── hardware_profiles/     # 硬件配置文件目录
    └── custom/            # 自定义硬件配置（JSON）
```

> 注：两个项目均采用单文件架构，所有模块、类、对话框和工具函数均集成在各自的主文件中，便于分发和部署。Manager 负责图形化配置管理，Launcher 负责智能启动与窗口追踪，二者通过共用 config/folders.json 实现数据共享。

---

## 模块说明

### Mikan QEMU Manager v5.5

| 模块 | 说明 |
|------|------|
| `check_and_install_dependencies` | 自动依赖检查与安装（PySide6、psutil） |
| `HardwareProfileManager` | 硬件配置文件管理器（加载内置/自定义配置、创建/更新/删除） |
| `HardwareProfileEditDialog` | 硬件配置编辑对话框（多 Tab 页：基本信息/CPU/显卡显示/声音网络/主板存储） |
| `HardwareProfileManagerDialog` | 硬件配置管理对话框（列表展示、详情面板、新建/编辑/删除/应用到当前VM） |
| `load_folders_config` / `save_folders_config` | 多文件夹配置读写 |
| `apply_active_folder` | 切换活动文件夹并重建目录结构 |
| `load_settings` / `save_settings` | 用户设置 JSON 持久化 |
| `BUILTIN_HARDWARE_PROFILES` | 内置硬件预设数据（10 套配置） |
| `FORCE_CPU_MODELS` | 支持的 CPU 型号列表（40+ 型号） |
| `is_admin` | Windows 管理员权限检测 |

### Mikan QEMU Launcher v14.2

| 模块 | 说明 |
|------|------|
| `find_gtk_window` | GTK 窗口查找（枚举窗口 + 类名/标题匹配 + psutil 验证） |
| `find_sdl_window` | SDL 窗口查找（类似机制） |
| `get_window_rect` | 获取窗口位置/大小 |
| `is_window_fullscreen` | 全屏检测 |
| `bring_window_to_top` | 窗口置顶 |
| `load_folders_config` | 读取多文件夹配置 |
| `get_all_vms_dirs` | 获取所有绑定文件夹的 VMS 目录 |
| `find_vm_dir` | 按名称查找虚拟机目录 |
| `get_active_folder` | 获取活动文件夹 |
| `get_qemu_features` | QEMU 功能检测（v14.2：非阻塞 + 内存缓存 + 文件缓存） |
| `get_qemu_year` | 从版本字符串识别年份 |
| `arch_to_exe_names` | 架构到可执行文件名映射 |
| `find_qemu_exe` | QEMU 可执行文件多级查找 |
| `get_arch_defaults` | 架构默认配置 |
| `get_host_ip` | 主机 IP 检测 |
| `detect_removable_drives` | 可移动磁盘检测 |
| `build_command` | 完整 QEMU 命令构建引擎（覆盖 v5.5 所有字段） |

---

## 注意事项

1. **管理员权限**：部分 QEMU 功能（硬件直通、KVM 加速等）可能需要管理员权限。
2. **杀毒软件**：程序涉及进程创建、窗口枚举和系统底层操作，可能被杀毒软件误报，请将程序加入白名单。
3. **QEMU 安装**：本工具集不捆绑 QEMU，需用户自行安装 QEMU 并通过配置文件指定路径。
4. **首次运行**：首次运行会自动检测并安装 Python 依赖包（PySide6、psutil），请确保网络畅通。
5. **配置文件**：两个工具共用 config/folders.json，确保路径配置一致。
6. **Windows 编码**：程序已内置 UTF-8 编码适配，如遇到乱码请检查系统区域设置。
7. **性能调优**：建议在 config.json 中根据实际硬件选择合适的加速模式（KVM > HAXM > TCG）。
8. **硬件直通**：USB 直通和 VFIO 需要系统级权限配置，请查阅 QEMU 文档。

---

## 开发指南

### 代码风格

- 遵循 PEP 8 编码规范
- 使用类型注解（typing）
- 异步操作通过 QThread / threading.Thread 实现
- UI 样式统一使用 QSS 管理

### Manager 扩展指引

1. 在 `HardwareProfileManager` 中添加新的内置硬件预设
2. 在 `FORCE_CPU_MODELS` 中添加新的 CPU 型号
3. 在 `HardwareProfileEditDialog.init_ui()` 中扩展新的配置 Tab 页
4. 通过 `apply_active_folder()` 支持新的目录结构

### Launcher 扩展指引

1. 在 `arch_to_exe_names()` 中添加新的架构支持
2. 在 `find_qemu_exe()` 中扩展可执行文件查找逻辑
3. 在 `get_qemu_features()` 中添加新的功能检测项
4. 在 `build_command()` 中扩展新的命令行参数
5. 窗口追踪逻辑可根据目标窗口类名/标题关键词灵活调整

---

## 许可证

本项目采用 **GNU General Public License v3.0** 许可。你可以自由地复制、修改和再分发本软件，但必须保留版权声明和许可声明。衍生作品也必须以相同的许可证开源。

详见 [LICENSE](LICENSE) 文件。

---

## 致谢

- [PySide6](https://www.qt.io/qt-for-python) - Qt for Python 绑定
- [QEMU](https://www.qemu.org/) - 开源虚拟机模拟器
- [psutil](https://github.com/giampaolo/psutil) - 跨平台进程和系统监控
- [DeepSeek](https://www.deepseek.com/) - AI 辅助开发

---

## 联系方式

如有问题或建议，欢迎提交 Issue 或 Pull Request。

---

*Made with care by Mikan Team · AI assisted by DeepSeek*
