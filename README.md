# SukiSU-Ultra v4.2.0 + SUSFS 2.3.0 + KPM — Redmi Note 9 Pro (gauguin)

Redmi Note 9 Pro（gauguin / gauguinpro / gauguininpro，SM7125）LineageOS 23.2（Android 15）内核，Linux 4.19.325 非 GKI。

- `android_kernel_xiaomi_gauguin/`：完整修改后内核源码（SukiSU-Ultra v4.2.0 驱动 + SUSFS 2.3.0 + KPM 全功能）
- `docs/`：编译方法与全部踩坑记录
- `scripts/`：boot.img 打包工具
- 预编译产物（boot 镜像 / 卡刷包 / 管理器）见 Releases

## 编译

```sh
export MAKEFLAGS="ARCH=arm64 CC=clang CLANG_TRIPLE=aarch64-linux-gnu- CROSS_COMPILE=aarch64-linux-gnu-"
cd android_kernel_xiaomi_gauguin
make O=out vendor/lito-perf_defconfig
./scripts/kconfig/merge_config.sh -O out -m arch/arm64/configs/vendor/lito-perf_defconfig arch/arm64/configs/vendor/xiaomi/gauguin.config
make O=out olddefconfig
make O=out -j10   # 产物 out/arch/arm64/boot/Image
```

## 许可

GPL-2.0（内核本体与 KernelSU/SukiSU 驱动均为 GPL-2.0）
