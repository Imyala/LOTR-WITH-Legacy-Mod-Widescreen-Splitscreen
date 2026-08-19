#!/usr/bin/env python3
"""
War in the North (Legacy Edition) - executable patches
======================================================

Patches 1-3 are the ultrawide fix and are only useful above 16:9.  Patch 4 is
the quicksave key and is useful to everyone; run with --no-res --no-gui to get
that one on its own.

Four edits to witn.exe.  See README-ultrawide.txt for the full write-up.

  1. RESOLUTION UNLOCK - the mode list is filtered against four hard-coded
     aspect ratios (16:9, 16:10, 4:3, 5:4) to within 0.0001, so 3440x1440
     (2.38889) was discarded.  The unused 5:4 entry is retargeted.

  2 & 3. GUI CANVAS - the 2D layer is authored in 1280x720 and drawn through
     a "canvas" of (1280, 1280/aspect).  Above 16:9 that makes the canvas too
     short, and since the canvas is stretched to the whole screen, every
     element is drawn screenW/1280 instead of screenH/720 - about 34% too
     big at 21:9, overflowing top and bottom.  Both copies of that maths are
     rewritten to be height-locked:

         canvasW = f * 720 * max(aspect, 16/9)
         canvasH = canvasW / aspect

     max() only engages above 16:9, so 16:9, 16:10 and 4:3 come out with the
     exact numbers they had before.  There are two copies because the engine
     inlines it a second time in the GUI projection setup - patching only the
     first one has no visible effect, which is a trap worth knowing about.

  4. QUICKSAVE KEY - the game only saves at scripted checkpoints.  A small
     code section is appended to the executable and App::Frame's once-per-
     frame call to PumpMessages() is routed through it.  The stub calls the
     original, polls a key with GetKeyState (already imported), and on the
     frame the key goes down calls the engine's own SaveCheckpoint(0) - the
     same routine behind the App_SaveGame script command and behind every
     autosave.  It is skipped unless a local player entity is live, so it
     does nothing in the menus, and checkpoint saves are timestamped, so a
     stray press can never overwrite an existing save.

Usage
    python3 witn_patch.py                            # apply everything
    python3 witn_patch.py --res 5120x1440            # a different ultrawide
    python3 witn_patch.py --no-res --no-gui          # quicksave key ONLY (16:9 etc.)
    python3 witn_patch.py --save-key 0x77            # bind F8 instead of F5
    python3 witn_patch.py --no-savekey               # ultrawide only, no save key
    python3 witn_ultrawide_patch.py --res 5120x1440  # different ultrawide
    python3 witn_ultrawide_patch.py --no-gui         # resolution unlock only
    python3 witn_ultrawide_patch.py --revert         # restore the original
    python3 witn_ultrawide_patch.py --exe /path/to/witn.exe

Run from the game folder, or pass --exe.  witn.exe.original is created on the
first run and is what --revert restores.
"""
import argparse, os, shutil, struct

ASPECTS = struct.pack('<4f', 16 / 9, 16 / 10, 4 / 3, 5 / 4)
SLOT = 3

# ---- site A: GetCanvas() tail ------------------------------------------------
A_ORIG = [
    0xF3,0x0F,0x5E,0xDD,                        # divss  xmm3,xmm5
    0x0F,0x28,0xD4,                             # movaps xmm2,xmm4
    0xF3,0x0F,0x59,0x15,None,None,None,None,    # mulss  xmm2,[1280.0]
    0x0F,0x28,0xCB,                             # movaps xmm1,xmm3
    0xF3,0x0F,0x59,0x1D,None,None,None,None,    # mulss  xmm3,[16/9]
    0xF3,0x0F,0x59,0xCA, 0xF3,0x0F,0x59,0xDC,
    0xF3,0x0F,0x11,0x11, 0xF3,0x0F,0x11,0x49,0x04,
    0x0F,0x28,0xC3, 0x48,0x81,0xC4,0x08,0x01,0x00,0x00, 0xC3,
]
A_D1280, A_ROOM = 11, 72

# ---- site B: the inlined copy in the GUI projection setup --------------------
B_ORIG = [
    0xF3,0x0F,0x5E,0xFB,                        # divss  xmm7,xmm3
    0x0F,0x28,0xC4,                             # movaps xmm0,xmm4
    0x0F,0x57,0xC9,                             # xorps  xmm1,xmm1
    0xF3,0x0F,0x59,0x05,None,None,None,None,    # mulss  xmm0,[1280.0]
    0x0F,0x28,0xF7, 0xF3,0x0F,0x59,0xF5, 0xF3,0x0F,0x59,0xF8,
    0xF3,0x44,0x0F,0x59,0xC8,
    0xF3,0x41,0x0F,0x10,0x41,0x04, 0xF3,0x41,0x0F,0x5C,0x01,
    0x41,0x0F,0x28,0xD1, 0xF3,0x0F,0x11,0x4C,0x24,0x28,
    0xF3,0x41,0x0F,0x5C,0xD0, 0xF3,0x0F,0x11,0x4C,0x24,0x20,
    0xF3,0x0F,0x59,0xF4, 0xF3,0x0F,0x59,0xF8,
    0x0F,0x28,0xDF, 0xF3,0x41,0x0F,0x5C,0xD8,
]
B_D1280 = 14


def sections(data):
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    nsec = struct.unpack_from('<H', data, pe + 6)[0]
    opt = struct.unpack_from('<H', data, pe + 20)[0]
    base = struct.unpack_from('<Q', data, pe + 24 + 24)[0]
    tab = pe + 24 + opt
    out = []
    for i in range(nsec):
        e = tab + i * 40
        vs, va, rs, rp = struct.unpack_from('<IIII', data, e + 8)
        out.append((base + va, max(vs, rs), rp))
    return out


def off2vma(secs, off):
    for va, size, rp in secs:
        if rp <= off < rp + size:
            return va + (off - rp)
    raise SystemExit(f"offset 0x{off:X} outside every section")


def read_f32(data, secs, vma):
    for va, size, rp in secs:
        if va <= vma < va + size:
            return struct.unpack_from('<f', data, rp + (vma - va))[0]
    raise SystemExit("constant outside the image")


def find(data, pattern, what):
    n, hits, start = len(pattern), [], 0
    while True:
        i = data.find(bytes([pattern[0]]), start)
        if i < 0 or i + n > len(data):
            break
        start = i + 1
        if all(p is None or data[i + k] == p for k, p in enumerate(pattern)):
            hits.append(i)
    if not hits:
        raise SystemExit(f"{what}: not found - wrong file, already patched, or "
                         f"the game was updated")
    if len(hits) > 1:
        raise SystemExit(f"{what}: {len(hits)} candidates {hits}; refusing to guess")
    return hits[0]


class Asm:
    def __init__(self, vma):
        self.b, self.a = bytearray(), vma

    def __call__(self, raw):
        self.b.extend(raw)
        self.a += len(raw)

    def rip(self, pfx, tgt):
        self(pfx + struct.pack('<i', tgt - (self.a + len(pfx) + 4)))


def constants(data, secs, off, idx):
    disp = struct.unpack_from('<i', data, off + idx)[0]
    c1280 = off2vma(secs, off + idx + 4) + disp
    c720 = c1280 - 4          # the shipped pool stores 720.0 just before 1280.0
    if round(read_f32(data, secs, c1280), 3) != 1280.0 or \
       round(read_f32(data, secs, c720), 3) != 720.0:
        raise SystemExit("constant pool does not look as expected")
    return c1280, c720


def patch_resolution(data, res):
    off = find(data, list(ASPECTS[:12]) + [None] * 4, "aspect-ratio table")
    slot = off + SLOT * 4
    old = struct.unpack_from('<f', data, slot)[0]
    try:
        w, h = (int(x) for x in res.lower().split('x'))
    except ValueError:
        raise SystemExit("--res must look like 3440x1440")
    new = struct.unpack('<f', struct.pack('<f', w / h))[0]
    struct.pack_into('<f', data, slot, new)
    print(f"  resolution : table @ 0x{off:X} slot {SLOT}  {old:.6f} -> {new:.6f}")


def patch_site_a(data, secs, mode):
    off = find(data, A_ORIG, "canvas routine (site A)")
    c1280, c720 = constants(data, secs, off, A_D1280)
    c169 = c1280 + (0x1409FE5AC - 0x1409F5FF0)   # resolved properly below
    disp = struct.unpack_from('<i', data, off + 22)[0]
    c169 = off2vma(secs, off + 26) + disp        # from 'mulss xmm3,[16/9]'
    if round(read_f32(data, secs, c169), 4) != 1.7778:
        raise SystemExit("16/9 constant not where expected")
    m = Asm(off2vma(secs, off))
    if mode == 'fill':
        m(b'\xF3\x0F\x5E\xDD')                 # divss  xmm3,xmm5   1/aspect
        m(b'\x0F\x28\xD4')                      # movaps xmm2,xmm4   f
        m.rip(b'\xF3\x0F\x59\x15', c1280)      # mulss  xmm2,[1280] canvasW
        m(b'\x0F\x28\xCD')                      # movaps xmm1,xmm5   aspect
        m.rip(b'\xF3\x0F\x5F\x0D', c169)       # maxss  xmm1,[16/9] M
        m(b'\xF3\x0F\x59\xCB')                 # mulss  xmm1,xmm3   k = M/aspect
        m(b'\x0F\x28\xC1')                      # movaps xmm0,xmm1
        m(b'\xF3\x0F\x59\xC4')                 # mulss  xmm0,xmm4   return f*k
        m(b'\x0F\x28\xC8')                      # movaps xmm1,xmm0
        m.rip(b'\xF3\x0F\x59\x0D', c720)       # mulss  xmm1,[720]  canvasH
        m(b'\xF3\x0F\x11\x11')                 # movss  [rcx],xmm2
        m(b'\xF3\x0F\x11\x49\x04')            # movss  [rcx+4],xmm1
        m(b'\x48\x81\xC4\x08\x01\x00\x00')
        m(b'\xC3')
        _finish_a(data, off, m)
        return
    m(b'\xF3\x0F\x5E\xDD')                  # divss  xmm3,xmm5      1/aspect
    m(b'\x0F\x28\xD4')                      # movaps xmm2,xmm4      f  
    m.rip(b'\xF3\x0F\x59\x15', c1280)       # mulss  xmm2,[1280.0]
    m(b'\xF3\x0F\x59\xD3')                  # mulss  xmm2,xmm3      f*1280/aspect
    m(b'\x0F\x28\xCC')                      # movaps xmm1,xmm4
    m.rip(b'\xF3\x0F\x59\x0D', c720)        # mulss  xmm1,[720.0]   f*720
    m(b'\xF3\x0F\x5F\xD1')                  # maxss  xmm2,xmm1      canvasH
    m(b'\x0F\x28\xCA')                      # movaps xmm1,xmm2
    m(b'\xF3\x0F\x59\xCD')                  # mulss  xmm1,xmm5      canvasW = H*aspect
    m(b'\xF3\x0F\x11\x09')                  # movss  [rcx],xmm1
    m(b'\xF3\x0F\x11\x51\x04')              # movss  [rcx+4],xmm2
    m(b'\x0F\x28\xC2')                      # movaps xmm0,xmm2
    m.rip(b'\xF3\x0F\x5E\x05', c720)        # divss  xmm0,[720.0]   return H/720
    m(b'\x48\x81\xC4\x08\x01\x00\x00')      # add    rsp,0x108
    m(b'\xC3')                              # ret
    _finish_a(data, off, m)


def _finish_a(data, off, m):
    if len(m.b) > A_ROOM:
        raise SystemExit("site A does not fit")
    if any(b != 0xCC for b in data[off + len(A_ORIG):off + A_ROOM]):
        raise SystemExit("expected int3 padding after site A; aborting")
    m.b.extend(b'\xCC' * (A_ROOM - len(m.b)))
    data[off:off + A_ROOM] = m.b
    print(f"  gui canvas : site A @ 0x{off:X} ({len(A_ORIG)} -> {A_ROOM} bytes)")


def patch_site_b(data, secs, mode):
    off = find(data, B_ORIG, "canvas routine (site B, gui projection)")
    c1280, c720 = constants(data, secs, off, B_D1280)
    m = Asm(off2vma(secs, off))
    if mode == 'fill':
        m(b'\x0F\x28\xC4')                  # movaps xmm0,xmm4      f
        m.rip(b'\xF3\x0F\x59\x05', c1280)  # mulss  xmm0,[1280.0]  canvasW
        m(b'\x0F\x28\xF3')                  # movaps xmm6,xmm3      aspect
        m(b'\xF3\x0F\x5F\xF5')             # maxss  xmm6,xmm5      M
        m(b'\xF3\x0F\x5E\xF3')             # divss  xmm6,xmm3      k = M/aspect
        m(b'\x0F\x28\xF8')                  # movaps xmm7,xmm0
        m(b'\xF3\x0F\x5E\xFD')             # divss  xmm7,xmm5      f*720
        m(b'\xF3\x0F\x59\xFE')             # mulss  xmm7,xmm6      canvasH
    else:
        m(b'\x0F\x28\xC4')                  # movaps xmm0,xmm4      f
        m.rip(b'\xF3\x0F\x59\x05', c720)   # mulss  xmm0,[720.0]   f*720
        m(b'\x0F\x28\xF3')                  # movaps xmm6,xmm3      aspect
        m(b'\xF3\x0F\x5F\xF5')             # maxss  xmm6,xmm5      max(aspect,16/9)
        m(b'\xF3\x0F\x59\xC6')             # mulss  xmm0,xmm6      canvasW
        m(b'\xF3\x0F\x5E\xF3')             # divss  xmm6,xmm3      k = max/aspect
        m(b'\x0F\x28\xF8')                  # movaps xmm7,xmm0
        m(b'\xF3\x0F\x5E\xFB')             # divss  xmm7,xmm3      canvasH = W/aspect
    m(b'\x0F\x57\xC9')                       # xorps  xmm1,xmm1
    m(b'\xF3\x44\x0F\x59\xC8')              # mulss  xmm9,xmm0
    m(b'\xF3\x41\x0F\x10\x41\x04')          # movss  xmm0,[r9+4]
    m(b'\xF3\x41\x0F\x5C\x01')              # subss  xmm0,[r9]
    m(b'\x41\x0F\x28\xD1')                  # movaps xmm2,xmm9
    m(b'\x0F\x11\x4C\x24\x20')              # movups [rsp+0x20],xmm1  (zeroes 20h..2Fh)
    m(b'\xF3\x41\x0F\x5C\xD0')              # subss  xmm2,xmm8
    m(b'\xF3\x0F\x59\xF4')                  # mulss  xmm6,xmm4      f*k
    m(b'\xF3\x0F\x59\xF8')                  # mulss  xmm7,xmm0
    m(b'\x0F\x28\xDF')                      # movaps xmm3,xmm7
    m(b'\xF3\x41\x0F\x5C\xD8')              # subss  xmm3,xmm8
    if len(m.b) != len(B_ORIG):
        raise SystemExit(f"site B is {len(m.b)} bytes, window is {len(B_ORIG)}")
    data[off:off + len(m.b)] = m.b
    print(f"  gui canvas : site B @ 0x{off:X} ({len(B_ORIG)} bytes, in place)")



SEC_NAME = b'.wsave\0\0'

# --- App::Frame: ... mov rdi,rcx ; call PumpMessages ; test eax,eax ; jne ---
HOOK = [
    0x48,0x89,0x5C,0x24,0x18,             # mov [rsp+0x18],rbx
    0x55, 0x56, 0x57,                     # push rbp/rsi/rdi
    0x48,0x83,0xEC,0x50,                  # sub rsp,0x50
    0x48,0x8B,0xF9,                       # mov rdi,rcx
    0xE8,None,None,None,None,             # call PumpMessages   <- retargeted
    0x85,0xC0,                            # test eax,eax
    0x75,                                 # jne short
]
HOOK_CALL = 15

# --- SaveCheckpoint(int slot) ------------------------------------------------
SAVE = [
    0x48,0x89,0x5C,0x24,0x08,             # mov [rsp+8],rbx
    0x57,                                 # push rdi
    0x48,0x83,0xEC,0x20,                  # sub rsp,0x20
    0x8B,0xD9,                            # mov ebx,ecx
    0xE8,None,None,None,None,             # call CheckpointArray()
    0x48,0x8B,0xF8,                       # mov rdi,rax
    0x39,0x58,0x10,                       # cmp [rax+0x10],ebx
    0x75,0x05,                            # jne +5
    0xE8,None,None,None,None,             # call AppendCheckpoint()
    0x48,0x69,0xCB,0x58,0x01,0x00,0x00,   # imul rcx,rbx,0x158
    0x48,0x03,0x0F,                       # add rcx,[rdi]
]

# --- GetLocalPlayerEntity() : 0 unless a player entity is live ---------------
PLAYER = [
    0x40,0x53,                            # push rbx
    0x48,0x83,0xEC,0x20,                  # sub rsp,0x20
    0x8B,0x15,None,None,None,None,        # mov edx,[localPlayerIndex]
    0x48,0x8D,0x4C,0x24,0x30,             # lea rcx,[rsp+0x30]
    0xE8,None,None,None,None,             # call MakeHandle
    0x48,0x8D,0x4C,0x24,0x30,             # lea rcx,[rsp+0x30]
    0xE8,None,None,None,None,             # call HandleValid
    0x85,0xC0,                            # test eax,eax
    0x74,0x3B,                            # je  ...
]


def _align(v, a):
    return (v + a - 1) & ~(a - 1)


class _PE:
    def __init__(self, data):
        self.d = data
        self.pe = struct.unpack_from('<I', data, 0x3C)[0]
        self.nsec_off = self.pe + 6
        self.opt = self.pe + 24
        self.optsz = struct.unpack_from('<H', data, self.pe + 20)[0]
        self.base = struct.unpack_from('<Q', data, self.opt + 24)[0]
        self.secalign = struct.unpack_from('<I', data, self.opt + 32)[0]
        self.filealign = struct.unpack_from('<I', data, self.opt + 36)[0]
        self.sectab = self.opt + self.optsz
        self.nsec = struct.unpack_from('<H', data, self.nsec_off)[0]
        self.secs = []
        for i in range(self.nsec):
            e = self.sectab + 40 * i
            vs, va, rs, rp = struct.unpack_from('<IIII', data, e + 8)
            self.secs.append((e, vs, va, rs, rp))

    def off2vma(self, off):
        for e, vs, va, rs, rp in self.secs:
            if rp <= off < rp + rs:
                return self.base + va + (off - rp)
        raise SystemExit(f"offset 0x{off:X} outside every section")

    def rva2off(self, rva):
        for e, vs, va, rs, rp in self.secs:
            if va <= rva < va + max(vs, rs):
                return rp + (rva - va)
        raise SystemExit(f"rva 0x{rva:X} outside every section")

    def datadir(self, i):
        o = self.opt + 112 + 8 * i
        return struct.unpack_from('<II', self.d, o)

    def set_datadir(self, i, rva, size):
        struct.pack_into('<II', self.d, self.opt + 112 + 8 * i, rva, size)

    def import_vma(self, want):
        rva, _ = self.datadir(1)
        o = self.rva2off(rva)
        i = 0
        while True:
            olt, ts, fc, nrva, first = struct.unpack_from('<IIIII', self.d, o + 20 * i)
            if olt == 0 and nrva == 0:
                return None
            t = self.rva2off(olt or first)
            j = 0
            while True:
                q = struct.unpack_from('<Q', self.d, t + 8 * j)[0]
                if q == 0:
                    break
                if not q >> 63:
                    no = self.rva2off(q & 0x7FFFFFFF)
                    end = self.d.find(b'\0', no + 2)
                    if bytes(self.d[no + 2:end]) == want:
                        return self.base + first + 8 * j
                j += 1
            i += 1


class _Asm:
    def __init__(self, vma):
        self.b, self.a = bytearray(), vma

    def __call__(self, raw):
        self.b.extend(raw)
        self.a += len(raw)

    def rel(self, pfx, tgt):
        self(pfx + struct.pack('<i', tgt - (self.a + len(pfx) + 4)))

    def here(self):
        return self.a


def patch_savekey(data, find, vk=0x74):
    """data: bytearray of a clean witn.exe.  find: the module's pattern matcher."""
    p = _PE(data)

    hook_off = find(data, HOOK, "frame loop (save-key hook site)")
    save_off = find(data, SAVE, "SaveCheckpoint()")
    play_off = find(data, PLAYER, "GetLocalPlayerEntity()")

    call_off = hook_off + HOOK_CALL
    disp = struct.unpack_from('<i', data, call_off + 1)[0]
    pump = p.off2vma(call_off + 5) + disp
    save = p.off2vma(save_off)
    player = p.off2vma(play_off)
    gks = p.import_vma(b'GetKeyState')
    if gks is None:
        raise SystemExit("GetKeyState is not imported by this executable")

    # ---- new section geometry ------------------------------------------------
    if p.sectab + 40 * (p.nsec + 1) > min(s[4] for s in p.secs):
        raise SystemExit("no room in the PE header for another section")
    new_va = _align(max(va + vs for e, vs, va, rs, rp in p.secs), p.secalign)
    new_rp = _align(len(data), p.filealign)
    if new_rp != len(data):
        data.extend(b'\0' * (new_rp - len(data)))
    vma = p.base + new_va

    # ---- the stub ------------------------------------------------------------
    m = _Asm(vma)
    m(b'\x48\x83\xEC\x28')                       # sub  rsp,0x28
    m.rel(b'\xE8', pump)                          # call PumpMessages
    m(b'\x89\x44\x24\x20')                       # mov  [rsp+0x20],eax
    m(b'\xB9' + struct.pack('<I', vk))            # mov  ecx,VK
    m.rel(b'\xFF\x15', gks)                       # call [GetKeyState]
    m(b'\x31\xD2')                               # xor  edx,edx
    m(b'\xF6\xC4\x80')                           # test ah,0x80        key down?
    m(b'\x74\x02')                               # je   +2
    m(b'\xB2\x01')                               # mov  dl,1
    state_fix = len(m.b)
    m(b'\x48\x8D\x0D\x00\x00\x00\x00')          # lea  rcx,[rip+state]  (patched below)
    m(b'\x8A\x01')                               # mov  al,[rcx]        previous
    m(b'\x88\x11')                               # mov  [rcx],dl        remember
    m(b'\x84\xD2')                               # test dl,dl
    j1 = len(m.b); m(b'\x74\x00')                # je   done
    m(b'\x84\xC0')                               # test al,al
    j2 = len(m.b); m(b'\x75\x00')                # jne  done            still held
    m.rel(b'\xE8', player)                        # call GetLocalPlayerEntity
    m(b'\x48\x85\xC0')                           # test rax,rax
    j3 = len(m.b); m(b'\x74\x00')                # je   done            not in game
    m(b'\x31\xC9')                               # xor  ecx,ecx         slot 0
    m.rel(b'\xE8', save)                          # call SaveCheckpoint
    done = len(m.b)
    for j in (j1, j2, j3):
        d = done - (j + 2)
        assert 0 <= d < 128
        m.b[j + 1] = d
    m(b'\x8B\x44\x24\x20')                       # mov  eax,[rsp+0x20]
    m(b'\x48\x83\xC4\x28')                       # add  rsp,0x28
    m(b'\xC3')                                    # ret
    code_len = len(m.b)

    blob = bytearray(m.b)
    while len(blob) % 4:
        blob.append(0xCC)
    unwind_rva = new_va + len(blob)
    blob += bytes([0x01, 0x04, 0x01, 0x00, 0x04, 0x42, 0x00, 0x00])
    state_rva = new_va + len(blob)
    blob.append(0x00)                             # previous key state

    # fix up lea rcx,[rip+state]
    ip = vma + state_fix + 7
    struct.pack_into('<i', blob, state_fix + 3, (p.base + state_rva) - ip)

    raw = bytes(blob) + b'\0' * (_align(len(blob), p.filealign) - len(blob))
    data.extend(raw)

    # ---- section header ------------------------------------------------------
    e = p.sectab + 40 * p.nsec
    data[e:e + 40] = (SEC_NAME + struct.pack('<IIII', len(blob), new_va, len(raw), new_rp)
                      + b'\0' * 12 + struct.pack('<I', 0xE0000020))
    struct.pack_into('<H', data, p.nsec_off, p.nsec + 1)
    struct.pack_into('<I', data, p.opt + 56,
                     new_va + _align(len(blob), p.secalign))          # SizeOfImage
    struct.pack_into('<I', data, p.opt + 4,
                     struct.unpack_from('<I', data, p.opt + 4)[0] + len(raw))  # SizeOfCode

    # ---- .pdata entry so SEH can unwind through the stub ---------------------
    pd_rva, pd_size = p.datadir(3)
    tail = p.rva2off(pd_rva) + pd_size
    if any(data[tail:tail + 12]):
        raise SystemExit(".pdata has no slack for the stub's unwind entry")
    struct.pack_into('<III', data, tail, new_va, new_va + code_len, unwind_rva)
    p.set_datadir(3, pd_rva, pd_size + 12)
    for ent, vs, va, rs, rp in p.secs:                # grow .pdata's VirtualSize
        if va <= pd_rva < va + max(vs, rs):
            if pd_size + 12 > rs:
                raise SystemExit(".pdata raw block is full")
            struct.pack_into('<I', data, ent + 8, max(vs, pd_size + 12))
            break

    # ---- redirect the frame call --------------------------------------------
    struct.pack_into('<i', data, call_off + 1, vma - p.off2vma(call_off + 5))

    # ---- PE checksum ---------------------------------------------------------
    # the shipped executable stores 0 (Windows only enforces this for drivers);
    # only recompute if the vendor actually filled it in.
    if struct.unpack_from('<I', data, p.opt + 64)[0]:
        struct.pack_into('<I', data, p.opt + 64, 0)
        struct.pack_into('<I', data, p.opt + 64, _checksum(data))

    nm = SEC_NAME.rstrip(b'\x00').decode()
    print(f"  save key   : hook @ 0x{call_off:X} -> section {nm} @ 0x{new_rp:X} "
          f"(VK 0x{vk:02X}); save=0x{save:X} guard=0x{player:X}")


def _checksum(data):
    total = 0
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    csum_off = pe + 24 + 64
    for i in range(0, len(data) & ~1, 2):
        if i == csum_off or i == csum_off + 2:
            continue
        total += struct.unpack_from('<H', data, i)[0]
        total = (total & 0xFFFF) + (total >> 16)
    if len(data) & 1:
        total += data[-1]
        total = (total & 0xFFFF) + (total >> 16)
    return (total + len(data)) & 0xFFFFFFFF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe', default='witn.exe')
    ap.add_argument('--res', default='3440x1440')
    ap.add_argument('--no-res', action='store_true',
                    help='skip the resolution unlock - use with --no-gui when you play '
                         'at a normal aspect ratio and only want the quicksave key')
    ap.add_argument('--no-gui', action='store_true')
    ap.add_argument('--hud', choices=['fit', 'fill'], default='fit',
                    help="fit = correct proportions with side bars (default); "
                         "fill = 2D layer spans the full width, ~34%% wider at 21:9")
    ap.add_argument('--no-savekey', action='store_true')
    ap.add_argument('--save-key', default='0x74',
                    help='virtual-key code for the quicksave key (default 0x74 = F5)')
    ap.add_argument('--revert', action='store_true')
    ap.add_argument('--rebase', action='store_true',
                    help='adopt the CURRENT witn.exe as the new stock baseline before '
                         'patching - use after installing a mod that replaces witn.exe')
    a = ap.parse_args()

    if not os.path.isfile(a.exe):
        raise SystemExit(f"{a.exe} not found - run from the game folder or use --exe")
    backup = a.exe + '.original'

    if a.revert:
        if not os.path.isfile(backup):
            raise SystemExit(f"{backup} is missing - use Steam's "
                             f"'Verify integrity of game files' instead")
        shutil.copyfile(backup, a.exe)
        print(f"restored {a.exe} from {backup}")
        return

    if a.rebase:
        probe = bytearray(open(a.exe, 'rb').read())
        for pat, what in ((list(ASPECTS[:12]) + [None] * 4, 'aspect table'),
                          (A_ORIG, 'canvas site A'), (B_ORIG, 'canvas site B'),
                          (HOOK, 'frame loop')):
            find(probe, pat, what)      # raises if this exe is already patched
        shutil.copyfile(a.exe, backup)
        print(f"rebased: {backup} now holds the current (modded) executable")
    if not os.path.exists(backup):
        shutil.copyfile(a.exe, backup)
        print(f"backup written: {backup}")
    data = bytearray(open(backup, 'rb').read())   # always patch a clean copy
    secs = sections(data)
    if a.no_res and not a.no_gui:
        raise SystemExit("--no-res without --no-gui makes no sense: the canvas fix "
                         "only matters once an ultrawide mode is selectable")
    if not a.no_res:
        patch_resolution(data, a.res)
    if not a.no_gui:
        patch_site_a(data, secs, a.hud)
        patch_site_b(data, secs, a.hud)
    if not a.no_savekey:
        patch_savekey(data, find, int(str(a.save_key), 0))   # must be last
    open(a.exe, 'wb').write(bytes(data))
    print("done - fully quit the game before relaunching")


if __name__ == '__main__':
    main()
