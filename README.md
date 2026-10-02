# Redmi Note 9 Pro (gauguin) — KernelSU-Next / SukiSU-Ultra + SUSFS 内核

为 Redmi Note 9 Pro（gauguin / gauguinpro / gauguininpro，SM7125）LineageOS 23.2（Android 15，内核 4.19.325 非 GKI）编译的 root 内核。

- 完整编译方法、集成步骤、全部踩坑记录：见 `docs/README-编译说明.md`
- 完整构建日志：`docs/logs/*-FULL.log`
- 各产物 SHA256：`releases/checksums-*.txt`

## 三套内核

| 目录/文件名 | 说明 |
|------------|------|
| `releases/boot-05-sukisu-ultra.img` | **SukiSU-Ultra v4.2.0 + SUSFS 2.3.0 + KPM（推荐，最新全功能）** |
| `releases/boot-03-ksunext-susfs.img` | KernelSU-Next v1.1.1 驱动 + SUSFS 1.5.5 |
| `releases/boot-02-sukisu-susfs.img` | SukiSU v1.5.6 驱动 + SUSFS 1.5.9（旧版备用） |
| `releases/kernel-*.tar.xz` | 各内核的完整修改后源码 |

## 刷入

```sh
fastboot flash boot boot-05-sukisu-ultra.img
```

开机后安装对应管理器 APK（releases/ 内）：
- SukiSU-Ultra 内核 → `SukiSU_v4.2.0_40900-release.apk`
- KSU-Next 内核 → `KernelSU_Next_v3.4.0_33294-release.apk`

隐藏功能：刷入 `ksu_module_susfs_1.5.2+.zip` 模块。
救砖：刷回 `boot-original-gauguin-los23.2.img`（官方原版）。

## 免责声明

本内核仅供学习研究。刷机有风险，请先备份原版 boot 并确保已解锁 bootloader。
