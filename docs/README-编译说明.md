# Redmi Note 9 Pro (gauguin) — KernelSU-Next / SukiSU + SUSFS 内核编译记录

- 目标设备：Redmi Note 9 Pro（gauguin / gauguinpro / gauguininpro，SM7125 / sm6150 平台）
- ROM：LineageOS 23.2（Android 15，2026-09-30 官方构建）
- 内核版本：Linux 4.19.325（非 GKI，arm64）
- 编译日期：2026-10-02
- 编译环境：Ubuntu 24.04.5 LTS，20 核 CPU / 62GB 内存 / 374GB 可用磁盘
- 工具链：clang 18.1.3 + lld 18 + GNU aarch64 binutils（均来自 Ubuntu 软件源）

---

## 0. 目录结构（所有产物存放位置）

根目录：`/media/yao/9141bf1b-7a0b-5243-a9e0-7e7c9f4db2ec/note9pro LOS23.2`

```
00-original/                  # 未经修改的原始物料
├── boot-original.img         # 原版 LOS boot.img（SHA256 已与官方校验一致）
├── android_kernel_xiaomi_gauguin/   # 未修改的官方内核源码（lineage-23.2 分支）
└── android_device_xiaomi_gauguin/   # 设备树（仅作参考，查编译参数用）
01-tools/                     # 工具与上游仓库
├── llvm18/bin/               # clang/lld/llvm 符号链接
├── bootimg_tool.py           # 自写 boot.img v2 解包/打包工具
├── KernelSU-Next/ (main/dev/legacy 各分支，用于考古)
├── SukiSU-Ultra-builtin/     # SukiSU builtin 驱动（v4.2.0 时代）
├── ShirkNeko-KSU-susfs-dev/  # SukiSU v1.5.6 扁平驱动（最终采用）
├── ShirkNeko-susfs4ksu-4.19/ # SukiSU 用的内核侧 SUSFS v1.5.9 补丁
├── susfs4ksu-4.19/           # 原版 simonpunk SUSFS v1.5.5 内核侧补丁（KSU-Next 用）
├── susfs4ksu-master/、susfs-shiba/  # 参考（susfs 2.x，未采用）
├── SukiSU_patch/             # SukiSU 官方 4.19 hooks 补丁库
├── xiaomi10-kernelsu-susfs-kernel-build/  # 已验证配方参考（clcwpwqi 项目）
├── AnyKernel3/               # osm0sis AnyKernel3 模板
├── KernelSU_Next_v3.4.0_33294-release.apk   # KSU-Next 管理器
├── SukiSU_v2.1_12572-release.apk            # SukiSU 管理器（与 v1.5.6 驱动同代）
├── SukiSU_v4.2.0_40900-release.apk          # SukiSU 最新管理器（备用）
└── ksu_module_susfs_1.5.2+.zip              # SUSFS 用户态工具/模块
02-sukisu-susfs/              # SukiSU + SUSFS 构建树（修改后的源码 + 产物）
03-ksunext-susfs/             # KSU-Next + SUSFS 构建树（修改后的源码 + 产物）
04-docs/                      # 本文档 + 完整构建日志
```

---

## 1. 下载原始物料（未修改备份）

```bash
# 原版 boot.img（mirrorbits 会 302 到 USTC 镜像并需要 JS 验证，直接带 cookie 走 USTC）
curl -fL --retry 3 -b "addr=<你的IP>" -A "Mozilla/5.0" \
  -o boot-original.img \
  "https://mirrors.ustc.edu.cn/lineageos/full/gauguin/20260930/boot.img"

# 官方 SHA256（mirrorbits ?sha256 接口）
curl -fsSL "https://mirrorbits.lineageos.org/full/gauguin/20260930/boot.img?sha256"
# 67ab48323e0438e3f317777370394a8f31622c983dff0b2aafa6d21f5a702237  ← 与本机 sha256sum 一致

# 内核源码（保持未修改，作为备份）
git clone --depth 1 --branch lineage-23.2 --single-branch \
  https://github.com/LineageOS/android_kernel_xiaomi_gauguin.git

# 设备树（查编译参数用）
git clone --depth 1 --branch lineage-23.2 --single-branch \
  https://github.com/LineageOS/android_device_xiaomi_gauguin.git
```

关键编译参数（来自设备树 BoardConfig.mk）：
- `TARGET_KERNEL_CONFIG := vendor/lito-perf_defconfig vendor/xiaomi/gauguin.config`
- `TARGET_KERNEL_NO_GCC := true`（clang 编译）
- `BOARD_KERNEL_IMAGE_NAME := Image`（未压缩 arm64 Image）
- `BOARD_BOOTIMG_HEADER_VERSION := 2`，`BOARD_RAMDISK_USE_LZ4 := true`
- boot 分区大小 128MB（镜像尾部有 0 填充）

## 2. 工具链安装

```bash
sudo apt-get install -y git curl lz4 zip unzip flex bison bc libssl-dev \
  build-essential libncurses-dev ccache clang-18 lld-18 llvm-18 \
  binutils-aarch64-linux-gnu mkbootimg
# 注意：Ubuntu 的 mkbootimg 包缺 gki 模块是坏的；本工程改用自写 bootimg_tool.py

mkdir -p llvm18/bin && cd llvm18/bin
for t in clang ld.lld llvm-ar llvm-nm llvm-objcopy llvm-objdump llvm-strip llvm-readelf llvm-as llvm-size; do
  ln -sf /usr/bin/$t-18 $t
done
```

## 3. 构建方法（两条流水线通用骨架）

> 重要：内核源码路径不能含空格（kbuild 限制），把工作目录 bind mount 到无空格路径：
> `sudo mount --bind "/media/yao/.../note9pro LOS23.2" /mnt/note9pro-build`

```bash
cd <构建树>/android_kernel_xiaomi_gauguin
export MAKEFLAGS="ARCH=arm64 CC=clang CLANG_TRIPLE=aarch64-linux-gnu- CROSS_COMPILE=aarch64-linux-gnu-"
export PATH="/mnt/note9pro-build/01-tools/llvm18/bin:$PATH"

# 1) 生成基础 defconfig
make O=out vendor/lito-perf_defconfig

# 2) 合并设备配置片段（第一个参数是 BASE，后面的才被合并进去！）
./scripts/kconfig/merge_config.sh -O out -m \
  arch/arm64/configs/vendor/lito-perf_defconfig \
  arch/arm64/configs/vendor/xiaomi/gauguin.config

# 3) 归一化配置
make O=out olddefconfig

# 4) 编译
make O=out -j10
# 产物：out/arch/arm64/boot/Image
```

### 3.1 KSU-Next + SUSFS 集成步骤（03-ksunext-susfs）

1. 驱动：KernelSU-Next **v1.1.1 tag**（扁平目录结构）+ cherry-pick rifsxd 官方
   SUSFS 提交 `091a35be "kernel: added susfs v1.5.3"`（2024-12-24）。
   该提交基于旧版，与 v1.1.1 有 5~6 个文件冲突，按 v1.1.1 语义手工合并：
   - Kconfig：保留 v1.1.1 新选项 + 追加 SUSFS 菜单
   - Makefile：全部取 v1.1.1（其 UMOUNT/seccomp 机制更新更全）
   - core_hook.c：保留 v1.1.1 行为 + 加入 susfs 分支（prctl CMD_SUSFS_* 处理、
     setuid 的 zygote/umount 流程、导出 ksu_escape_to_root）
   - ksud.c / selinux/rules.c / sucompat.c：按 v1.1.1 重命名规则（is_zygote→ksu_is_zygote、
     setup_selinux→ksu_setup_selinux、apply_kernelsu_rules→ksu_apply_kernelsu_rules、…）
   - 驱动放入 `drivers/kernelsu/`，在 drivers/Makefile 加 `obj-$(CONFIG_KSU) += kernelsu/`，
     drivers/Kconfig 加 `source "drivers/kernelsu/Kconfig"`

2. 内核侧 SUSFS：原版 simonpunk susfs4ksu **kernel-4.19 分支（v1.5.5）**
   ```bash
   cp kernel_patches/fs/susfs.c kernel_patches/fs/sus_su.c fs/
   cp kernel_patches/include/linux/susfs*.h kernel_patches/include/linux/sus_su.h include/linux/
   patch -p1 < kernel_patches/50_add_susfs_in_kernel-4.19.patch
   # 3 处 hunk 因 4.19.325 上下文差异需要手工补：
   #  include/linux/mount.h      → vfsmount 里 KABI_USE(4, susfs_mnt_id_backup)
   #  fs/proc/task_mmu.c         → 补 susfs_def.h include
   #  fs/namespace.c             → 头文件/extern/IDA/CL_* 定义、vfs_create_mount（本树为
   #                               fs_context 新式挂载路径）、clone_mnt 的 CL_COPY_MNT_NS 逻辑
   ```

3. 配置片段（追加进 gauguin.config）：
   ```
   CONFIG_KPROBES=y
   CONFIG_KPROBE_EVENTS=y
   CONFIG_KSU=y
   CONFIG_KSU_SUSFS=y
   CONFIG_KSU_SUSFS_SUS_PATH=y
   CONFIG_KSU_SUSFS_SUS_MOUNT=y
   CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT=y
   CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT=y
   CONFIG_KSU_SUSFS_SUS_KSTAT=y
   CONFIG_KSU_SUSFS_TRY_UMOUNT=y
   CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT=y
   CONFIG_KSU_SUSFS_SPOOF_UNAME=y
   CONFIG_KSU_SUSFS_ENABLE_LOG=y
   CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS=y
   CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG=y
   CONFIG_KSU_SUSFS_OPEN_REDIRECT=y
   CONFIG_KSU_SUSFS_SUS_SU=y
   CONFIG_TMPFS_XATTR=y
   # CONFIG_CC_WERROR is not set
   CONFIG_FRAME_WARN=4096
   ```
   Hook 方式：**kprobes**（KSU-Next 官方非 GKI 方案，gauguin 4.19 工作正常）。
   配套管理器：`KernelSU_Next_v3.4.0_33294-release.apk`

### 3.2 SukiSU + SUSFS 集成步骤（02-sukisu-susfs）

> 结论先行：SukiSU 最新版（v4.2.0）的 builtin 驱动需要 susfs 2.x 内核侧接口
> （CMD_SUSFS_SHOW_VARIANT/SHOW_VERSION、susfs_add_sus_path_loop、
> `void __user**` 风格函数签名等），4.19 没有官方 susfs 2.x 补丁。
> 因此采用**已被小米10 项目（clcwpwqi/xiaomi10-kernelsu-susfs-kernel-build）验证的
> 经典组合**：SukiSU v1.5.6 扁平驱动 + ShirkNeko susfs4ksu 4.19（v1.5.9）。

1. 驱动：`ShirkNeko/KernelSU` 仓库 **susfs-dev 分支（v1.5.6，2025-04-22）**，
   扁平 tiann-KSU 布局，Kconfig 自带 KSU_SUSFS 菜单（HAS_MAGIC_MOUNT 等）。
   → 复制 `kernel/` 为 `drivers/kernelsu/`，改 drivers/Makefile + drivers/Kconfig（同上）

2. 内核侧 SUSFS：ShirkNeko/susfs4ksu **kernel-4.19 分支（v1.5.9）**
   ```bash
   cp kernel_patches/fs/susfs.c kernel_patches/fs/sus_su.c fs/
   cp kernel_patches/include/linux/susfs*.h kernel_patches/include/linux/sus_su.h include/linux/
   patch -p1 < kernel_patches/50_add_susfs_in_kernel-4.19.patch
   # 手工补：mount.h（同上）、namespace.c（1.5.9 版本的 include 块 + vfs_create_mount +
   #         clone_mnt 的 mnt_ns 遍历 fake mnt_id 逻辑）
   # 注意：1.5.9 补丁不含 sched.h，需手工加入 task_struct 的
   #       susfs_task_state / susfs_last_fake_mnt_id（ANDROID_KABI_USE 写法，同 1.5.5）
   # 注意：1.5.9 用 TIF_NON_ROOT_USER_APP_PROC（thread_info 标志）替代旧 task_struct 标志，
   #       驱动里 `current->susfs_task_state |= TASK_STRUCT_NON_ROOT_USER_APP_PROC`
   #       改为 `susfs_set_current_non_root_user_app_proc()`
   ```

3. 配置片段：
   ```
   CONFIG_KPROBES=y
   CONFIG_KPROBE_EVENTS=y
   CONFIG_KSU=y
   CONFIG_KSU_SUSFS=y
   CONFIG_KSU_SUSFS_HAS_MAGIC_MOUNT=y
   CONFIG_KSU_SUSFS_SUS_PATH=y
   CONFIG_KSU_SUSFS_SUS_MOUNT=y
   CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT=y
   CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT=y
   CONFIG_KSU_SUSFS_SUS_KSTAT=y
   CONFIG_KSU_SUSFS_TRY_UMOUNT=y
   CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT=y
   CONFIG_KSU_SUSFS_SPOOF_UNAME=y
   CONFIG_KSU_SUSFS_ENABLE_LOG=y
   CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS=y
   CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG=y
   CONFIG_KSU_SUSFS_OPEN_REDIRECT=y
   CONFIG_KSU_SUSFS_SUS_SU=y
   CONFIG_TMPFS_XATTR=y
   # CONFIG_CC_WERROR is not set
   CONFIG_FRAME_WARN=4096
   ```
   配套管理器：`SukiSU_v2.1_12572-release.apk`（与 v1.5.6 驱动同代；
   v4.2.0 管理器需要 susfs 2.x 内核，与 v1.5.9 不匹配）

### 3.3 SukiSU-Ultra v4.2.0 + SUSFS 2.3.0 集成步骤（05-sukisu-ultra，最新版）

> 用户要求最新版 SukiSU：v4.2.0 builtin 驱动/管理器需要 **susfs 2.x** 接口
> （SUSFS_MAGIC=0xFAFAFAFA、CMD 0x55553/0x55561/0x60010/0x60020、
> `void __user **` 风格函数签名），而 4.19 没有官方 2.x 补丁。
> 做法：把 **susfs v2.3.0（simonpunk gki-android12-5.10 分支，2026-09 仍活跃）
> 移植到 4.19**。

1. 驱动：`SukiSU-Ultra/SukiSU-Ultra` 仓库 **builtin 分支（v4.2.0）**
   → `drivers/kernelsu/`（新架构：LSM hook + 手工 syscall hook + reboot(2) 魔术数超调用）

2. 手工 hooks：`SukiSU_patch/4.19/ksu_hooks_sukisu_4.19.patch`（零冲突）
   但其中的 faccessat/stat/exec/input/devpts 调用点是旧式（const char** 风格）——
   v4.2.0 驱动在 CONFIG_KSU_SUSFS=y 时导出的是 struct filename** 变体，
   且 input/devpts 在该驱动里是 dead code。最终保留的 hook 组合：
   - 2.3.0 内核补丁（移植）负责：reboot 超调用、setresuid、do_faccessat、
     vfs_statx、__do_execve_file、vfs_fstat、readdir/stat/statfs/namei/namespace/
     proc/kallsyms/sys 等
   - hooks 补丁只保留 read（3 参 ksu_handle_sys_read）
   - exec.c 的 post_execveat hook 删除（v4.2.0 驱动无此符号）

3. 内核侧 SUSFS：simonpunk susfs4ksu **gki-android12-5.10（v2.3.0）**：
   `cp fs/susfs.c fs/` + `cp include/linux/susfs*.h include/linux/`
   + 手工移植 `50_add_susfs_in_gki-android12-5.10.patch`（24 个文件）
   主要适配点（4.19 与 5.10 的差异）：
   - fs/stat.c：4.19 vfs_fstat 是 include/linux/fs.h 的 static inline →
     改挂 vfs_statx_fd；本树 struct kstat 无 mnt_id（Xiaomi 删了 statx mnt_id）→
     补回字段 + STATX_MNT_ID/STATX_ATTR_MOUNT_ROOT 定义；real_mount 在内部
     fs/mount.h
   - fs/readdir.c：4.19 无 prev_reclen（用 previous 指针）→ 改写 filldir；
     FUSE 数据路径判定逻辑按 2.3.0 原样落进 old_readdir/getdents/compat_fillonedir
   - fs/namei.c：4.19 无 open_last_lookups（用 do_last + lookup_open）→
     ND_STATE_OPEN_LAST 放 do_last；path_openat 的 OPEN_REDIRECT 重定向块
     按 do_last 循环改写
   - fs/exec.c：本树 do_execveat_common 已重构为 __do_execve_file →
     hook 放进 __do_execve_file
   - fs/namespace.c：4.19 struct mount 无 mnt_stuck_children → 删对应 INIT 行
   - security/selinux：selinux_hide 特性（fake_state/status）在 4.19 上整个
     用 `LINUX_VERSION_CODE >= 5.10` 守卫禁用（4.19 selinux 内部结构不兼容）；
     status_lock/policy_mutex 均不存在
   - fs/susfs.c：sdcard fsnotify 监控（5.10+ API）用版本守卫禁用，
     4.19 上直接置“已解密”状态；DEFINE_STATIC_KEY_TRUE 移出守卫
   - include/linux/susfs_def.h：补 linux/cred.h + linux/thread_info.h include
   - include/linux/stat.h：struct kstat 补 u64 mnt_id；uapi 补 STATX_MNT_ID
   - 驱动侧：ksu.c/selinux_hide.c 在 4.19 上用 5.10 版本守卫排除
     （与内核侧 selinux hook 的守卫一致）

4. 配置片段：
   ```
   CONFIG_KSU=y
   CONFIG_KSU_SUSFS=y
   CONFIG_KSU_SUSFS_SUS_PATH=y
   CONFIG_KSU_SUSFS_SUS_MOUNT=y
   CONFIG_KSU_SUSFS_SUS_KSTAT=y
   CONFIG_KSU_SUSFS_SPOOF_UNAME=y
   CONFIG_KSU_SUSFS_ENABLE_LOG=y
   CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS=y
   CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG=y
   CONFIG_KSU_SUSFS_OPEN_REDIRECT=y
   CONFIG_KSU_SUSFS_SUS_MAP=y
   CONFIG_TMPFS_XATTR=y
   # CONFIG_CC_WERROR is not set
   CONFIG_FRAME_WARN=4096
   ```
   配套管理器：**SukiSU_v4.2.0_40900-release.apk**（最新版，与驱动同代）

## 4. boot.img 重新打包

```bash
# 解包
python3 bootimg_tool.py unpack boot-original.img work/
# 打包（替换 Image 内核）
python3 bootimg_tool.py pack work/ <新Image路径> boot-new.img
# 填充到 boot 分区大小（128MB），与原镜像一致
truncate -s 134217728 boot-new.img
```

## 5. 刷入方式

1. fastboot（bootloader 已解锁）：
   `fastboot flash boot boot-new.img && fastboot reboot`
2. 或进入 recovery 刷 AnyKernel3 卡刷包（只替换现有 boot 分区内核）：
   `adb sideload AnyKernel3-xxx.zip`
3. 开机后安装对应管理器 APK，再刷入 `ksu_module_susfs_1.5.2+.zip` 模块
   （提供 ksu_susfs 用户态工具与隐藏脚本）。
4. 救砖：任何异常直接 `fastboot flash boot boot-original.img` 即可还原。
5. vbmeta 说明：LineageOS 官方构建对已解锁 bootloader 的设备默认不强制 AVB 校验，
   正常情况下直接刷 boot 即可；若开机卡验证（红色 bootloader 警告），
   从同版本 LOS 刷机包中提取 vbmeta.img 并执行：
   `fastboot flash vbmeta --disable-verity --disable-verification vbmeta.img`

---

## 6. 编译遇到的问题与解决方法（时间线）

### 6.1 环境与下载
| # | 问题 | 解决方法 |
|---|------|----------|
| 1 | mirrorbits 下载 403 / 875 字节 JS 验证页 | mirrorbits 302 到 USTC 镜像并要求 JS 验证。直接带 `-b "addr=<IP>"` cookie 访问 `mirrors.ustc.edu.cn/lineageos/...`，SHA256 用 mirrorbits 的 `?sha256` 接口校验 |
| 2 | github.com 间歇性 GnuTLS/-110/超时 | 换网络后恢复；git 操作加 `--depth 1` 减小流量，失败就重试 |
| 3 | android.googlesource.com 超时（无法下载 AOSP 工具链） | 改用 Ubuntu 源里的 clang-18/lld-18/llvm-18 + binutils-aarch64-linux-gnu |
| 4 | Ubuntu 的 `mkbootimg` 缺 `gki` python 模块无法运行 | 自写 `bootimg_tool.py`（支持 boot header v2，解包/打包/校验，往返测试与原始镜像逐字节一致） |
| 5 | magiskboot（Magisk APK 里的是 bionic 动态库）无法在 Linux x86_64 直接跑 | 不使用 magiskboot，改用自写工具 + AK3 自带工具 |

### 6.2 KSU-Next 驱动整合
| # | 问题 | 解决方法 |
|---|------|----------|
| 6 | KSU-Next 官方已无 susfs 支持（main/dev 分支重构为 core//manager/ 子目录，且历史提交 `07692d96 kernel: purge SuSFS remnants` 删除了内核 SUSFS） | 采用 **v1.1.1 tag（扁平目录）+ cherry-pick 官方历史提交 `091a35be`（susfs v1.5.3）**；5 个冲突文件按 v1.1.1 语义手工合并 |
| 7 | 冲突中函数改名不一致（is_zygote/ksu_is_zygote、setup_selinux/ksu_setup_selinux、escape_to_root/ksu_escape_to_root、apply_kernelsu_rules/ksu_apply_kernelsu_rules…） | 以合并后的 selinux.c（已干净应用改名）为准，反向统一所有调用点 |
| 8 | sucompat.c 中 `execve_kp` 等 kprobe 变量不存在（v1.1.1 已改为 `su_kps[4]` 数组） | 把 susfs 的 enable/disable_sus_su 改为按数组下标引用（0=execve 1=faccessat 2=newfstatat 3=pts） |
| 9 | 驱动用 1.5.3 老接口：`CMD_SUSFS_SET_BOOTCONFIG`、`susfs_set_bootconfig`、`SUSFS_FAKE_BOOT_CONFIG_SIZE`、`user_struct.android_kabi_reserved2` | 统一到 1.5.5 内核侧接口：`CMD_SUSFS_SET_CMDLINE_OR_BOOTCONFIG`、`susfs_set_cmdline_or_bootconfig`、`SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE`；user_struct 标志改为 `current->susfs_task_state |= TASK_STRUCT_NON_ROOT_USER_APP_PROC`（1.5.5 机制） |
| 10 | kernel_compat.c 中 `ksu_access_ok` 重复定义（static inline vs 外部函数） | v1.1.1 的版本已兼容 4.19/5.0+，删除 susfs 补丁追加的 static inline 副本 |
| 10a | 批量改名脚本把 `escape_to_root` 二次加前缀成 `ksu_ksu_escape_to_root`（链接期 undefined reference） | 全局替换 `ksu_ksu_escape_to_root` → `ksu_escape_to_root` |
| 10b | kprobes 模式下 `try_umount` 未定义（susfs 补丁把函数在 `#ifdef CONFIG_KSU_SUSFS` 下导出为 `ksu_try_umount`，但旧调用点仍写 `try_umount`） | 所有调用点统一改为 `ksu_try_umount(...)`（内核侧 susfs 也需要该导出符号） |

### 6.3 SukiSU 方案选型
| # | 问题 | 解决方法 |
|---|------|----------|
| 11 | SukiSU-Ultra v4.2.0 builtin 驱动需要 susfs 2.x（susfs_def.h、CMD_SUSFS_SHOW_VARIANT/SHOW_VERSION、susfs_add_sus_path_loop、`void __user**` 签名、SUSFS_MAGIC…），而 4.19 只有 1.5.x 补丁；susfs 2.3.0 仅有 6.1 GKI 补丁 | 回退到被小米10 项目验证的组合：ShirkNeko/KernelSU **susfs-dev（v1.5.6）驱动** + ShirkNeko/susfs4ksu **kernel-4.19（v1.5.9）内核侧** + SukiSU v2.1 管理器。两者 API（CMD 全集 + struct 风格签名）完全匹配 |
| 12 | 先误用了新版 ksu_hooks_sukisu_4.19.patch（面向 builtin 驱动的 sucompat 风格 hook） | 换老驱动后 `patch -R` 回退该补丁；老驱动用 kprobes 方案，不需要手工 syscall hooks |
| 13 | ShirkNeko 1.5.9 补丁缺 sched.h hunk，但 fs/dcache.c 等用到 `current->susfs_task_state` | 从原版 1.5.5 补丁移植 sched.h hunk（ANDROID_KABI_USE(6/8) 写法） |
| 13a | sched.h 手工补丁易插错位置：futex 区块在 `#ifdef __GENKSYMS__` 下，正常编译走 `#else`（struct mutex）分支；且需在 `randomized_struct_fields_end` 前补 `#if defined(CONFIG_KSU_SUSFS) && !defined(ANDROID_KABI_RESERVE)` 的普通字段（本机未开 CONFIG_ANDROID_KABI_RESERVE，全靠这段） | 以已编译通过的内核树为参照，三处全部复刻：①futex 区 KABI_USE(6)+#else 普通字段 ②RESERVE(8)→KABI_USE(8, susfs_last_fake_mnt_id) ③randomized 尾部两个普通字段 |
| 14 | 驱动 1.5.6 用 task_struct 标志，1.5.9 内核侧改用 TIF（thread_info）标志 | 驱动改为调用 `susfs_set_current_non_root_user_app_proc()`（1.5.9 susfs_def.h 自带） |
| 14a | 驱动 Makefile 只在 `IS_GKI=TRUE` 分支里定义 `KSU_HOOK_WITH_KPROBES`，非 GKI 编译时 sucompat.c 走“手动 hook”分支，`su_kps`/`ksu_devpts_hook` 未定义/顺序错误 | 把 `ccflags-y += -DKSU_HOOK_WITH_KPROBES` 提到分支外无条件定义，非 GKI 也走 kprobes（与 KSU-Next 同一方案，gauguin 4.19 上 kprobes 工作正常） |
| 14b | 1.5.9 的 dcache.c 用 `TASK_STRUCT_NON_ROOT_USER_APP_PROC`（task_struct 标志）但头文件未定义该宏 | 在 susfs_def.h 补 `#define TASK_STRUCT_NON_ROOT_USER_APP_PROC BIT(24)`；驱动 setuid 时同时设置 task 标志和 TIF 标志，两套检查都能命中 |
| 14c | namespace.c 的 clone_mnt CL 块补丁脚本因断言中止导致整段未写入（`alloc_vfsmnt` 仍单参数 → 编译“too few arguments”） | 检查补丁脚本的实际落盘状态后重放该 hunk（教训：脚本中途 assert 失败时 file.write 在末尾，全部改动丢失） |

### 6.6 SukiSU-Ultra v4.2.0 + susfs 2.3.0 移植（05-sukisu-ultra）
| # | 问题 | 解决方法 |
|---|------|----------|
| 21 | v4.2.0 驱动需要 susfs 2.x（SUSFS_MAGIC=0xFAFAFAFA、CMD 0x60010/0x60020、`void __user**` 签名），4.19 无官方 2.x 补丁 | 从 simonpunk susfs4ksu 的 gki-android12-5.10 分支（v2.3.0，2026-09 仍在更新）把内核侧 24 文件补丁手工移植到 4.19 |
| 22 | 2.3.0 补丁在 4.19 上大量 hunk 冲突（56 处） | 逐文件按 4.19 结构改写：stat.c（vfs_fstat 是 inline→挂 vfs_statx_fd）、readdir.c（无 prev_reclen）、namei.c（无 open_last_lookups→do_last）、exec.c（__do_execve_file）、namespace.c（无 mnt_stuck_children）等 |
| 23 | 本树 struct kstat 没有 mnt_id、uapi 无 STATX_MNT_ID（Xiaomi 删除了 statx mnt_id 支持） | 手工补回：struct kstat 加 `u64 mnt_id`、uapi 加 STATX_MNT_ID(0x1000) + STATX_ATTR_MOUNT_ROOT(0x2000) |
| 24 | real_mount 声明在内部 fs/mount.h（不在 linux/mount.h） | stat.c 改 include "mount.h" |
| 25 | hooks 补丁的旧式调用点（const char** faccessat/stat、input/devpts hook、exec 双钩）与 2.3.0 端口冲突 | 删除 hooks 补丁的重叠调用点；v4.2.0 驱动中 input/devpts 是 dead code（__maybe_unused），保留 2.3.0 的 input 静态键 hook，删除 pty.c hook |
| 26 | selinux_hide 特性（fake_state/fake_status，用于隐藏 /sys/fs/selinux）在 4.19 不兼容：selinux_state 无 status_lock/policy_mutex、驱动侧 selinux_hide.c 被 5.10 守卫 | 内核侧 hooks.c/selinuxfs.c 的相应块整体加 `LINUX_VERSION_CODE >= 5.10` 守卫（4.19 上该隐藏功能禁用，其余 SUSFS 功能不受影响） |
| 27 | susfs.c 的 sdcard fsnotify 监控用 5.10+ API（fsnotify_ops 回调签名完全不同） | 整段加 5.10 版本守卫；4.19 上 start_sdcard_monitor_fn 直接置“已解密”（exec hook 走 sucompat 路径） |
| 28 | susfs_def.h 里 inline 函数用 current_uid() 但没 include cred.h | 补 `<linux/cred.h>` + `<linux/thread_info.h>` |
| 29 | 并行构建下偶发 ar 报缺 .o（伪错误，掩盖真实编译错误） | 以 grep error: 的稳定输出为准，逐轮修复真实错误；最终一次通过 |

### 6.4 编译链问题
| # | 问题 | 解决方法 |
|---|------|----------|
| 15 | `Makefile:135: main directory cannot contain spaces nor colons`（工作目录名含空格） | `sudo mount --bind "<原目录>" /mnt/note9pro-build`，后续全部在无空格路径下构建 |
| 16 | `merge_config.sh` 结果把 COMPAT/PREEMPT 等 arm64 配置清掉，导致 `compat_uptr_t` 未定义、`struct rcu_tasks` 不完整等诡异错误 | ① merge_config.sh 的第一个位置参数才是 BASE，必须写 `-m lito-perf_defconfig gauguin.config`（只传 gauguin.config 时它被当成基础，lito-perf 根本没进来）；② 环境变量 `CC=clang` 会被 kbuild 覆盖，必须用 `MAKEFLAGS="ARCH=arm64 CC=clang CLANG_TRIPLE=... CROSS_COMPILE=..."` 传给所有（含嵌套）make |
| 17 | qcom 驱动 `sha3_256_hmac` 栈帧超限报错（`CONFIG_CC_WERROR=y` 把 clang 的 frame 告警当错误） | gauguin.config 里 `# CONFIG_CC_WERROR is not set` + `CONFIG_FRAME_WARN=4096` |

### 6.5 SUSFS 内核补丁冲突（4.19.325 与补丁基线的差异）
| # | 文件 | 差异 | 处理 |
|---|------|------|------|
| 18 | include/linux/mount.h | vfsmount 字段顺序不同（data 在 KABI 之前） | 手工在 RESERVE(3)/RESERVE(4) 间插入 KABI_USE(4, susfs_mnt_id_backup) |
| 19 | fs/namespace.c | 本树是 fs_context 新式挂载路径（vfs_kern_mount→fc_mount→vfs_create_mount），无旧式 `alloc_vfsmnt(name)` 调用点 | 把 susfs 的 ksu/zygote 判断逻辑放进 vfs_create_mount；clone_mnt 按 1.5.5/1.5.9 各自版本完整重写 |
| 20 | fs/proc/task_mmu.c（仅 1.5.5） | include 上下文偏移 | 手工补 susfs_def.h include |

---

### 6.7 真机调试：管理器"不支持"与开机循环（SukiSU-Ultra 4.19）
| # | 问题 | 解决方法 |
|---|------|----------|
| 30 | 管理器显示"不支持"（驱动已初始化但检测不到） | 逐层排查：①管理器识别靠 pkg_observer(fsnotify 监控 packages.list)+throne_tracker 扫描 /data/app 签名匹配"加冕"；②依赖 packages.list 变更事件触发——**刷内核前已装好的管理器不会被识别**（无变更事件）→ 在 post_fs_data 和 boot_completed 主动 `track_throne(false)` 搜索 |
| 31 | 加冕找错包：旧 v2.1 管理器(shirkneko.zako.sukisu)与新 v4.2.0(com.sukisu.ultra)同签名密钥，先被扫到的是旧包 | 卸载旧管理器即可；注意 v4.2.0 的包名是 com.sukisu.ultra |
| 32 | 加冕成功但管理器仍不支持：`zyg_sid=-2060903472`（垃圾值） | v4.2.0 驱动的 `susfs_set_batch_sid()`（初始化 susfs 的 zygote/ksu/init SID）只在 5.10+ 的 apply_kernelsu_rules 分支被调用，4.19 分支漏掉 → susfs_zygote_sid 未初始化 → setresuid 钩子的 zygote 判定永远失败 |
| 33 | 补上 susfs_set_batch_sid 后开机循环：zygote 派生应用挂死（binder/wake_up 栈 + "Apps crashed" 看门狗重启） | 4.19 上 setresuid 的完整 umount 链路（ksu_handle_umount+susfs extra works+2.3.0 挂载逻辑）在应用派生时挂死。**回退**该改动，改为**最小管理器处理**：在 ksu_handle_setresuid 最前面（SID 判断之前）单独处理管理器 uid——disable_seccomp + 注入 fd，不激活 umount 链路。另外 exec 路径 fd 注入改用非 CLOEXEC（`get_unused_fd_flags(0)`）让 fd 能活过 app_process 的 execve |
| 34 | exec 路径注入的 fd 是 CLOEXEC 的，app_process execve 时被内核关闭，白注入 | supercall.c 新增 `ksu_install_fd_no_cloexec()`（fd_flags=0 + anon_inode O_RDWR），exec 注入走这个 |
| 35 | ksu.c 是单编译单元（#include 所有 .c），改了被 `#ifdef CONFIG_KSU_SUSFS` 排除分支里的函数（改错分支，编译产物无变化） | 先 grep 确认目标函数所在的条件分支；改完用 `strings ksu.o` 验证字符串确实进了二进制 |

### 6.8 最终可用方案要点（SukiSU-Ultra v4.2.0 + SUSFS 2.3.0，4.19）
- 管理器识别：开机 post_fs_data / boot_completed / packages.list 变更三种时机主动搜索加冕
- 管理器 root：setresuid 钩子最小化处理（disable_seccomp + fd 注入，不做 umount）+ exec 路径非 CLOEXEC fd 兜底
- **不可用**：susfs_set_batch_sid 在 4.19 apply_kernelsu_rules 路径（会激活 zygote umount 链路导致应用派生挂死）→ 4.19 上 SUS_PATH/SUS_MOUNT 的 zygote 侧自动 umount 相关能力受限（susfs 命令式隐藏 sus_path/sus_mount 仍可用）

## 7. 产物清单

| 文件 | 说明 | SHA256 |
|------|------|--------|
| 00-original/boot-original.img | 原版 boot（未修改备份） | `67ab48323e0438e3f317777370394a8f31622c983dff0b2aafa6d21f5a702237` |
| 00-original/android_kernel_xiaomi_gauguin/ | 未修改内核源码（git status 干净，0 处改动） | — |
| 03-ksunext-susfs/android_kernel_xiaomi_gauguin/ | **KSU-Next+SUSFS 修改后源码**（drivers/kernelsu、fs/susfs.c、include/linux/susfs*.h、sched.h、namespace.c、mount.h、task_mmu.c、gauguin.config 等全部修改已就位） | — |
| 03-ksunext-susfs/boot-03-ksunext-susfs.img | KSU-Next+SUSFS 集成 boot 镜像（128MB，可直接 fastboot 刷） | `c4eaf08c4ccece8690d8f94ed120f8fe9b20f911665168f44a057dbe8d525891` |
| 03-ksunext-susfs/AnyKernel3-03-ksunext-susfs.zip | KSU-Next+SUSFS 卡刷包（recovery 可刷） | `d22a71416726b5469c998e150dfa7f3c5fdeaf4059b68959bdf3a58f73f1b092` |
| 02-sukisu-susfs/android_kernel_xiaomi_gauguin/ | **SukiSU+SUSFS 修改后源码** | — |
| 02-sukisu-susfs/boot-02-sukisu-susfs.img | SukiSU v1.5.6 驱动 + SUSFS 1.5.9 boot 镜像（旧版方案，备用） | `19dff25a29b73881d25aa139abf1349056ecd6b9506155c5e48297191ed5cdcc` |
| 02-sukisu-susfs/AnyKernel3-02-sukisu-susfs.zip | SukiSU v1.5.6 + SUSFS 1.5.9 卡刷包 | `b01ac585999059277ae6b30b021fd3a8b6e7c9a11db2335d5299397c414d01ba` |
| **05-sukisu-ultra/android_kernel_xiaomi_gauguin/** | **SukiSU-Ultra v4.2.0 + SUSFS 2.3.0 修改后源码（最新版，推荐）** | — |
| 05-sukisu-ultra/boot-05-sukisu-ultra.img | SukiSU-Ultra v4.2.0 + SUSFS 2.3.0 boot 镜像 | `790fc84028f6f3f5c6607de4a0535fa1f7553d50cf2d34f930caeaae94a6f169` |
| 05-sukisu-ultra/AnyKernel3-05-sukisu-ultra.zip | SukiSU-Ultra v4.2.0 + SUSFS 2.3.0 卡刷包 | `817f5dbb8a7d652c7ce1c73c4652ed8d7e5a4deb0af3736d8d898e2ff3fb355e` |
| 01-tools/KernelSU_Next_v3.4.0_33294-release.apk | KSU-Next 管理器 | — |
| 01-tools/SukiSU_v4.2.0_40900-release.apk | **SukiSU-Ultra 管理器（最新版，配 05-sukisu-ultra 内核）** | — |
| 01-tools/SukiSU_v2.1_12572-release.apk | SukiSU v2.1 管理器（配 02-sukisu-susfs 旧内核） | — |
| 01-tools/ksu_module_susfs_1.5.2+.zip | SUSFS 用户态工具/隐藏模块 | — |
| 04-docs/logs/ | 完整构建日志（*_FULL.log 为干净全量重建日志） | — |

刷机建议：先 `fastboot flash boot boot-original.img` 确认原版可开机，再分别测试两个
boot 镜像；管理器安装对应 APK，隐藏功能刷入 ksu_module_susfs 模块后
用 `ksu_susfs` 命令行工具配置（sus_path / sus_mount / try_umount 等）。
