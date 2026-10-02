#!/bin/bash
# 构建完成后的一键打包脚本
# 用法: finalize.sh <02-sukisu-susfs|03-ksunext-susfs>
set -e
B=/mnt/note9pro-build
T="$B/$1"
cd "$T/android_kernel_xiaomi_gauguin"
IMG=out/arch/arm64/boot/Image
[ -f "$IMG" ] || { echo "Image 不存在"; exit 1; }
echo "== Image 信息:"
ls -lh "$IMG"
strings "$IMG" | grep "Linux version" | head -1
strings "$IMG" | grep -iE "KernelSU|SukiSU|ksu" | head -3

# 解包原版 boot（一次性）
W="$T/boot-work"
[ -d "$W" ] || python3 "$B/01-tools/bootimg_tool.py" unpack "$B/00-original/boot-original.img" "$W"

# 打包含新内核的 boot.img
OUT="$T/boot-$1.img"
python3 "$B/01-tools/bootimg_tool.py" pack "$W" "$IMG" "$OUT"
truncate -s 134217728 "$OUT"
echo "== 打包完成: $OUT"
ls -lh "$OUT"

# AnyKernel3 zip
AK="$T/AnyKernel3"
cp "$IMG" "$AK/Image"
cd "$AK"
zip -r9 "$T/AnyKernel3-$1.zip" . -x '*.git*' >/dev/null
cd "$T"
echo "== AK3 包: $T/AnyKernel3-$1.zip"
ls -lh "$T/AnyKernel3-$1.zip" "$OUT"
sha256sum "$OUT" "$T/AnyKernel3-$1.zip" | tee "$T/checksums-$1.txt"
