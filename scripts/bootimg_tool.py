#!/usr/bin/env python3
"""bootimg v2 packer/unpacker for gauguin LOS boot.img repacking.

Usage:
  bootimg_tool.py unpack <boot.img> <outdir>
  bootimg_tool.py pack <outdir> <new-kernel-Image> <out.img>
  bootimg_tool.py info <boot.img>
"""
import struct, sys, os, hashlib

BOOT_MAGIC = b"ANDROID!"

# boot_img_hdr_v2 layout
def parse_header(buf):
    assert buf[:8] == BOOT_MAGIC, "bad magic"
    (kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size,
     second_addr, tags_addr, page_size, header_version, os_version) = \
        struct.unpack_from("<11I", buf, 8)[:10]
    name = buf[48:48+16]
    cmdline = buf[64:64+512]
    ident = buf[576:576+32]
    extra_cmdline = buf[608:608+1024]
    hdr = {}
    if header_version >= 1:
        recovery_dtbo_size = struct.unpack_from("<I", buf, 1632)[0]
        recovery_dtbo_offset = struct.unpack_from("<Q", buf, 1636)[0]
        header_size = struct.unpack_from("<I", buf, 1644)[0]
    else:
        recovery_dtbo_size = 0; recovery_dtbo_offset = 0; header_size = 0
    hdr.update(dict(kernel_size=kernel_size, kernel_addr=kernel_addr,
        ramdisk_size=ramdisk_size, ramdisk_addr=ramdisk_addr,
        second_size=second_size, second_addr=second_addr,
        tags_addr=tags_addr, page_size=page_size,
        header_version=header_version, os_version=os_version,
        name=name, cmdline=cmdline, ident=ident, extra_cmdline=extra_cmdline))
    if header_version >= 1:
        hdr["recovery_dtbo_size"] = recovery_dtbo_size
        hdr["recovery_dtbo_offset"] = recovery_dtbo_offset
        hdr["header_size"] = header_size
    if header_version >= 2:
        dtb_size = struct.unpack_from("<I", buf, 1648)[0]
        dtb_addr = struct.unpack_from("<Q", buf, 1652)[0]
        hdr["dtb_size"] = dtb_size; hdr["dtb_addr"] = dtb_addr
    else:
        hdr["dtb_size"] = 0; hdr["dtb_addr"] = 0
    return hdr

def align(x, page):
    return (x + page - 1) // page * page

def build_header(hdr):
    buf = bytearray(1636 if hdr["header_version"] == 0 else 1660)
    buf[0:8] = BOOT_MAGIC
    struct.pack_into("<10I", buf, 8, hdr["kernel_size"], hdr["kernel_addr"],
        hdr["ramdisk_size"], hdr["ramdisk_addr"], hdr["second_size"],
        hdr["second_addr"], hdr["tags_addr"], hdr["page_size"],
        hdr["header_version"], hdr["os_version"])
    buf[48:48+16] = hdr["name"].ljust(16, b"\0")[:16]
    buf[64:64+512] = hdr["cmdline"].ljust(512, b"\0")[:512]
    buf[576:576+32] = hdr.get("ident", b"\0"*32)[:32]
    buf[608:608+1024] = hdr["extra_cmdline"].ljust(1024, b"\0")[:1024]
    if hdr["header_version"] >= 1:
        struct.pack_into("<I", buf, 1632, hdr["recovery_dtbo_size"])
        struct.pack_into("<Q", buf, 1636, hdr["recovery_dtbo_offset"])
        struct.pack_into("<I", buf, 1644, hdr["header_size"])
    if hdr["header_version"] >= 2:
        struct.pack_into("<I", buf, 1648, hdr["dtb_size"])
        struct.pack_into("<Q", buf, 1652, hdr["dtb_addr"])
    return bytes(buf)

def unpack(path, outdir):
    data = open(path, "rb").read()
    hdr = parse_header(data)
    page = hdr["page_size"]
    off = align(hdr["header_size"] or (1636 if hdr["header_version"]==0 else 1660), page)
    sections = []
    os.makedirs(outdir, exist_ok=True)
    def dump(name, size, off):
        if size > 0:
            open(os.path.join(outdir, name), "wb").write(data[off:off+size])
            off = align(off + size, page)
        return off
    off = dump("kernel", hdr["kernel_size"], off)
    off = dump("ramdisk", hdr["ramdisk_size"], off)
    off = dump("second", hdr["second_size"], off)
    if hdr["header_version"] >= 1:
        off = dump("recovery_dtbo", hdr["recovery_dtbo_size"], off)
    if hdr["header_version"] >= 2:
        off = dump("dtb", hdr["dtb_size"], off)
    with open(os.path.join(outdir, "header.json"), "w") as f:
        import json
        h = dict(hdr)
        for k in ("cmdline", "extra_cmdline", "name", "ident"):
            h[k] = h[k].split(b"\0")[0].decode("utf-8", "replace") if isinstance(h[k], bytes) else ""
        json.dump(h, f, indent=2)
    print("unpacked to", outdir)
    print("kernel_size=%d ramdisk_size=%d dtb_size=%d page=%d hdr_ver=%d os_version=%#x" % (
        hdr["kernel_size"], hdr["ramdisk_size"], hdr["dtb_size"], page,
        hdr["header_version"], hdr["os_version"]))

def pack(indir, kernel_path, outimg):
    import json
    hdr = json.load(open(os.path.join(indir, "header.json")))
    hdr["cmdline"] = hdr["cmdline"].encode()
    hdr["extra_cmdline"] = hdr["extra_cmdline"].encode()
    hdr["name"] = hdr["name"].encode()
    page = hdr["page_size"]

    kernel = open(kernel_path, "rb").read()
    def rd(name):
        p = os.path.join(indir, name)
        return open(p, "rb").read() if os.path.exists(p) else b""
    ramdisk = rd("ramdisk")
    second = rd("second")
    recovery_dtbo = rd("recovery_dtbo")
    dtb = rd("dtb")

    hdr["kernel_size"] = len(kernel)
    hdr["ramdisk_size"] = len(ramdisk)
    hdr["second_size"] = len(second)
    hdr["recovery_dtbo_size"] = len(recovery_dtbo)
    hdr["dtb_size"] = len(dtb)

    # compute image id = sha256 over the blob of all sections+headers per AOSP
    m = hashlib.sha256()
    m.update(kernel); m.update(struct.pack("<I", len(kernel)))
    m.update(ramdisk); m.update(struct.pack("<I", len(ramdisk)))
    m.update(second); m.update(struct.pack("<I", len(second)))
    if hdr["header_version"] >= 1:
        m.update(recovery_dtbo); m.update(struct.pack("<I", len(recovery_dtbo)))
    if hdr["header_version"] >= 2:
        m.update(dtb); m.update(struct.pack("<I", len(dtb)))
    hdr["ident"] = m.digest()
    hdr["header_size"] = 1660

    hdrb = build_header(hdr)
    out = bytearray()
    out += hdrb
    out += b"\0" * (align(len(hdrb), page) - len(hdrb))
    for blob in (kernel, ramdisk, second, recovery_dtbo, dtb):
        if blob:
            out += blob
            out += b"\0" * (align(len(blob), page) - len(blob))
    open(outimg, "wb").write(bytes(out))
    print("wrote %s (%d bytes): kernel=%d ramdisk=%d dtb=%d" % (
        outimg, len(out), len(kernel), len(ramdisk), len(dtb)))

def info(path):
    data = open(path, "rb").read()
    hdr = parse_header(data)
    for k, v in hdr.items():
        if isinstance(v, bytes):
            v = v.split(b"\0")[0].decode("utf-8", "replace")
        print("%-22s %s" % (k, hex(v) if isinstance(v, int) and k.endswith(("addr","offset","size","version")) and v > 0xffff else v))

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "unpack":
        unpack(sys.argv[2], sys.argv[3])
    elif cmd == "pack":
        pack(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "info":
        info(sys.argv[2])
    else:
        print(__doc__)
