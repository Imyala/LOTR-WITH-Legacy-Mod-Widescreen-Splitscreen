#!/usr/bin/env python3
# ============================================================
#  War in the North - Widescreen Mod
#  Author:  Imyala
#  Version: 1.8.1
#  Guide:   https://steamcommunity.com/sharedfiles/filedetails/?id=3786147705
#  Licensed under MIT. Copyright (c) 2026 Imyala.
#  Keep this header intact in forks and redistributions.
# ============================================================
"""
War in the North (Legacy Edition) - executable patches
======================================================

Patches 1-3 are the ultrawide fix and are only useful above 16:9.  Patch 4 is
the save keys, which are useful to everyone; run with --save-only to get those
on their own.

Five edits to witn.exe.  See README-ultrawide.txt for the full write-up.

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

  4. FIELD OF VIEW (Hor+) - the perspective matrix is built from a HORIZONTAL
     field of view (pi/2 = 90 degrees by default) and the aspect ratio:

         m00 = 1 / tan(fovH/2)          m11 = aspect / tan(fovH/2)

     so the horizontal angle is fixed and the vertical one shrinks as the
     screen widens - Vert-.  At 21:9 the vertical FOV falls from 58.7 to 45.4
     degrees, which reads as the camera being shoved in behind the character.
     The call to tanf() inside that routine is routed through a shim that
     scales the tangent by max(1, aspect/(16:9)), which lands m11 on exactly
     its 16:9 value and opens m00 up instead: vertical framing preserved,
     horizontal view widened.  The max() makes it an exact no-op at 16:9 and
     below, so the square shadow and reflection cameras that share the routine
     are left alone.

  5. QUICKSAVE KEY - the game only saves at scripted checkpoints.  A small
     code section is appended to the executable and App::Frame's once-per-
     frame call to PumpMessages() is routed through it.  The stub calls the
     original, polls a key with GetKeyState (already imported), and on the
     frame the key goes down calls the engine's own CheckpointMgr::RequestSave -
     the exact call the netcode makes on a checkpoint.  It sets a pending-save
     flag and a short countdown on the manager; the game's own per-frame update
     then writes the save through DoCheckpointSave (the routine behind every
     autosave, timestamped lotr_/auto_ pair and all) once its readiness gate is
     quiet.  So the save lands a second or two after the press and only when
     nothing is in progress - stand somewhere safe, not mid-combat or in a menu.
     RequestSave needs only the manager pointer, so it can never fault the way a
     script-command handler does when handed a null context.  F5 is also skipped
     unless a local player entity is live, so it does nothing in the menus, and
     the saves are timestamped, so a stray press can never overwrite an existing
     save.

     (History: up to 1.5.2 the key called SaveCheckpoint(0), which only
     re-captures the respawn point in memory and writes no file.  A 1.6 interim
     build wired it to a script-command handler that needs a command context in
     rcx; called with a null context it CRASHED.  1.6 final uses RequestSave,
     which the engine itself calls with just the manager pointer.)

Usage
    python3 witn_patch.py                            # apply everything
    python3 witn_patch.py --res 5120x1440            # a different ultrawide
    python3 witn_patch.py --save-only                # save keys ONLY, nothing else
    python3 witn_patch.py --save-key 0x77            # bind F8 instead of F5
    python3 witn_patch.py --fov-scale 1.1            # a little wider than stock
    python3 witn_patch.py --no-fov                   # leave the camera alone
    python3 witn_patch.py --no-savekey               # ultrawide only, no save key
    python3 witn_patch.py --revert                   # restore the original
    python3 witn_patch.py --exe /path/to/witn.exe

Run from the game folder, or pass --exe.  witn.exe.original is created on the
first run and is what --revert restores.
"""

__author__ = 'Imyala'
__license__ = 'MIT'
__credits__ = ['Imyala']
import argparse
import hashlib, os, shutil, struct

ASPECTS = struct.pack('<4f', 16 / 9, 16 / 10, 4 / 3, 5 / 4)
SLOT_219, SLOT_329 = 3, 2      # the 5:4 entry, and the 4:3 entry

# One value per ultrawide FAMILY rather than per resolution.  The mode filter
# compares w/h against each table entry within +-EPS, so a single entry can
# cover a whole family once EPS is widened from the shipped 0.0001:
#
#   2.36667 +- 0.05  ->  2.3167 .. 2.4167   21:9   2560x1080  (2.37037)
#                                                  3440x1440  (2.38889)
#                                                  3840x1600  (2.4)
#                                                  2520x1080  (2.33333)
#                                                  3840x1620, 5120x2160
#   3.55556 +- 0.05  ->  3.5056 .. 3.6056   32:9   5120x1440, 3840x1080,
#                                                  7680x2160
#
# 16:9 (1.7778) and 16:10 (1.6) are 0.178 apart and 4:3 (1.3333) is 0.267 from
# 16:10, so +-0.05 cannot make any of the shipped entries collide.
FAMILY_219 = 2.3666667
FAMILY_329 = 3.5555556
EPS = 0.05

# --- the display-mode filter's tolerance -------------------------------------
# movss xmm6,[0.0001] just before the per-mode loop.  That constant is the
# engine's generic float epsilon and is referenced 528 times, so it is never
# edited - only this one load is retargeted at a 0.05 already sitting in
# .rdata.  xmm6 is used in exactly two places in this function: the aspect
# match, and a de-duplication pass that compares integer pixel counts, where a
# 0.05 window still means "the same integer".
EPSLOAD = [
    0x41,0x8B,0xEE,                          # mov   ebp,r14d
    0xF3,0x0F,0x10,0x35,None,None,None,None, # movss xmm6,[rip+eps]
    0x44,0x8B,0xE0,                          # mov   r12d,eax
    0x85,0xD2,                               # test  edx,edx
    0x0F,0x84,                               # je    ...
]
EPS_DISP = 7

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


def patch_resolution(data, secs, res, keep43=False):
    try:
        w, h = (int(x) for x in res.lower().split('x'))
    except ValueError:
        raise SystemExit("--res must look like 3440x1440")
    a = w / h
    is219 = 2.30 <= a <= 2.45
    is329 = 3.45 <= a <= 3.65

    # ---- widen the tolerance ------------------------------------------------
    off = find(data, EPSLOAD, "display-mode filter (aspect tolerance)")
    o = off + EPS_DISP
    cur = off2vma(secs, o + 4) + struct.unpack_from('<i', data, o)[0]
    if round(read_f32(data, secs, cur), 8) != 0.0001:
        raise SystemExit("the mode filter's tolerance is not the 0.0001 it should "
                         "be - refusing to widen something else")
    tgt = None
    for va, size, rp in secs:
        i = data.find(struct.pack('<f', EPS), rp, rp + size)
        if i >= 0 and (i - rp) % 4 == 0:
            tgt = va + (i - rp)
            break
    if tgt is None:
        raise SystemExit(f"no {EPS} constant in the image to point the filter at")
    struct.pack_into('<i', data, o, tgt - off2vma(secs, o + 4))

    # ---- retarget the unused table entries ----------------------------------
    tab = find(data, list(ASPECTS[:12]) + [None] * 4, "aspect-ratio table")
    wrote = []
    if keep43:
        v = FAMILY_329 if is329 else (FAMILY_219 if is219 else a)
        struct.pack_into('<f', data, tab + SLOT_219 * 4, v)
        wrote.append((SLOT_219, '5:4', v))
    else:
        struct.pack_into('<f', data, tab + SLOT_329 * 4, FAMILY_329)
        wrote.append((SLOT_329, '4:3', FAMILY_329))
        v = FAMILY_219 if (is219 or is329) else a
        struct.pack_into('<f', data, tab + SLOT_219 * 4, v)
        wrote.append((SLOT_219, '5:4', v))
    # a ratio the shipped table already covers needs no slot of its own
    for sl, was, v in list(wrote):
        for k in range(2):
            if abs(struct.unpack_from('<f', data, tab + k * 4)[0] - v) <= EPS:
                struct.pack_into('<f', data, tab + sl * 4,
                                 struct.unpack_from('<f', ASPECTS, sl * 4)[0])
                wrote.remove((sl, was, v))
                print(f"               {v:.6f} is already covered by slot {k} - "
                      f"slot {sl} ({was}) left alone")
                break

    print(f"  resolution : tolerance @ 0x{o - 4:X} 0.0001 -> {EPS:g} "
          f"(constant 0x{tgt:X})")
    for sl, was, v in wrote:
        print(f"               table @ 0x{tab:X} slot {sl} ({was}) -> {v:.6f}  "
              f"covers {v - EPS:.4f}..{v + EPS:.4f}")
    if not (is219 or is329) and any(abs(v - a) < 1e-6 for _, _, v in wrote):
        print(f"               NOTE: {res} is {a:.4f}:1, which is neither the 21:9 "
              f"nor the 32:9 family - that exact ratio was written instead")


# --- the engine's local-player count, and its split-screen test --------------
# The GUI script command IsSplitscreen is "count local players > 1": it calls
# a counting getter over the engine's handle table.  That table (base pointer
# at a global, 16-byte entries) turned out to be SHARED by several registries
# - five sibling count functions walk it with different iterator index lists -
# so 1.7's "slot 1 occupied" shortcut also fired in plain single player and
# pushed the fill canvas + split FOV onto solo play.  The only precise signal
# is the return value of the exact getter IsSplitscreen calls: it walks just
# the local-player index list and returns the count in eax (1 = solo / online
# co-op, 2 = two-player split, 3 = tri).  The per-frame hook caches that count
# in .wsave; the canvas / FOV stubs read the cache passively.
#
# The table base pointer (used only as an is-initialised guard before calling
# the getter) is resolved by majority vote over every "load table / index
# it / test the slot" site (48 8B 15 <ptr> ... 48 83 3C CA 00): 87 of 91 such
# sites name one address, so a stray inlined copy cannot mislead it.
SPLITTAB_SITE = [
    0x3B,0xD8,                            # cmp  ebx,eax        (idx vs sentinel)
    0x0F,0x84,None,None,None,None,        # je   ...
    0x48,0x8B,0x15,None,None,None,None,   # mov  rdx,[table ptr]
    0x8B,0xCB,                            # mov  ecx,ebx
    0x48,0x03,0xC9,                       # add  rcx,rcx
    0x48,0x83,0x3C,0xCA,0x00,             # cmp  qword [rdx+rcx*8],0
]


def find_splitscreen_table(data):
    """VMA of the global holding the local-player table base, by majority vote
    across every site that loads-and-indexes it (see SPLITTAB_SITE)."""
    from collections import Counter
    pe = _PE(data)
    votes = Counter()
    i = 0
    n = len(SPLITTAB_SITE)
    while True:
        i = data.find(b'\x3b\xd8\x0f\x84', i)
        if i < 0 or i + n > len(data):
            break
        if all(b is None or data[i + k] == b for k, b in enumerate(SPLITTAB_SITE)):
            votes[pe.off2vma(i + 15) + struct.unpack_from('<i', data, i + 11)[0]] += 1
        i += 1
    if not votes:
        raise SystemExit("local-player table not found - unsupported build")
    tab, v = votes.most_common(1)[0]
    if v < 8 or v < sum(votes.values()) * 0.5:
        raise SystemExit("local-player table base is ambiguous - refusing")
    return tab


# GetNumLocalPlayers() is one of five near-identical count functions (same
# prologue, same handle table); the right one is pinned through its single
# distinctive caller - the IsSplitscreen script command's "cmp count,r12"
# site - then verified against its own prologue and table load.
GETTER_TAIL = [0x33,0xDB, 0x44,0x8B,0xEB, 0x41,0x3B,0xC4, 0x76]
GETTER_HEAD = [0x48,0x89,0x5C,0x24,0x10, 0x57, 0x48,0x83,0xEC,0x20,
               0x33,0xFF, 0x48,0x8D,0x4C,0x24,0x30, 0xE8]


def find_localcount_getter(data, splittab):
    """VMA of GetNumLocalPlayers() - the exact function IsSplitscreen calls."""
    pe = _PE(data)
    tail = bytes(GETTER_TAIL)
    hits = set()
    i = 0
    while True:
        i = data.find(tail, i)
        if i < 0:
            break
        if data[i - 5] == 0xE8:
            hits.add(pe.off2vma(i) + struct.unpack_from('<i', data, i - 4)[0])
        i += 1
    if len(hits) != 1:
        raise SystemExit(f"IsSplitscreen's player-count call is not unique "
                         f"({len(hits)} candidates) - unsupported build")
    getter = hits.pop()
    off = pe.rva2off(getter - pe.base)
    if not all(data[off + k] == b for k, b in enumerate(GETTER_HEAD)):
        raise SystemExit("player-count getter prologue changed - refusing")
    if bytes(data[off + 0x32:off + 0x35]) != b'\x48\x8b\x15':
        raise SystemExit("player-count getter body changed - refusing")
    tab = pe.off2vma(off + 0x32 + 7) + struct.unpack_from('<i', data, off + 0x35)[0]
    if tab != splittab:
        raise SystemExit("player-count getter walks a different table - refusing")
    return getter


def find_canvas_sites(data, secs):
    """Locate and verify both canvas sites WITHOUT patching them, for the
    split-aware detour built in patch_appendix.  Returns everything the stub
    emitters need."""
    a_off = find(data, A_ORIG, "canvas routine (site A)")
    c1280, c720 = constants(data, secs, a_off, A_D1280)
    disp = struct.unpack_from('<i', data, a_off + 22)[0]
    c169 = off2vma(secs, a_off + 26) + disp
    if round(read_f32(data, secs, c169), 4) != 1.7778:
        raise SystemExit("16/9 constant not where expected")
    if any(b != 0xCC for b in data[a_off + len(A_ORIG):a_off + A_ROOM]):
        raise SystemExit("expected int3 padding after site A; aborting")
    b_off = find(data, B_ORIG, "canvas routine (site B, gui projection)")
    constants(data, secs, b_off, B_D1280)       # verifies the pool again
    return {'a_off': a_off, 'b_off': b_off,
            'c1280': c1280, 'c720': c720, 'c169': c169}


def _emit_canvas_a(m, mode, c1280, c720, c169):
    """Site A body (the GetCanvas tail), ending with its own epilogue+ret.
    Byte-for-byte the maths patch_site_a writes in place."""
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
    else:
        m(b'\xF3\x0F\x5E\xDD')                 # divss  xmm3,xmm5   1/aspect
        m(b'\x0F\x28\xD4')                      # movaps xmm2,xmm4   f
        m.rip(b'\xF3\x0F\x59\x15', c1280)      # mulss  xmm2,[1280.0]
        m(b'\xF3\x0F\x59\xD3')                 # mulss  xmm2,xmm3   f*1280/aspect
        m(b'\x0F\x28\xCC')                      # movaps xmm1,xmm4
        m.rip(b'\xF3\x0F\x59\x0D', c720)       # mulss  xmm1,[720.0]  f*720
        m(b'\xF3\x0F\x5F\xD1')                 # maxss  xmm2,xmm1   canvasH
        m(b'\x0F\x28\xCA')                      # movaps xmm1,xmm2
        m(b'\xF3\x0F\x59\xCD')                 # mulss  xmm1,xmm5   canvasW = H*aspect
        m(b'\xF3\x0F\x11\x09')                 # movss  [rcx],xmm1
        m(b'\xF3\x0F\x11\x51\x04')            # movss  [rcx+4],xmm2
        m(b'\x0F\x28\xC2')                      # movaps xmm0,xmm2
        m.rip(b'\xF3\x0F\x5E\x05', c720)       # divss  xmm0,[720.0]  return H/720
    m(b'\x48\x81\xC4\x08\x01\x00\x00')      # add    rsp,0x108
    m(b'\xC3')                                    # ret


def _emit_canvas_b(m, mode, c1280, c720):
    """Site B body (the inlined copy), WITHOUT the trailing jmp back."""
    if mode == 'fill':
        m(b'\x0F\x28\xC4')                      # movaps xmm0,xmm4      f
        m.rip(b'\xF3\x0F\x59\x05', c1280)      # mulss  xmm0,[1280.0]  canvasW
        m(b'\x0F\x28\xF3')                      # movaps xmm6,xmm3      aspect
        m(b'\xF3\x0F\x5F\xF5')                 # maxss  xmm6,xmm5      M
        m(b'\xF3\x0F\x5E\xF3')                 # divss  xmm6,xmm3      k = M/aspect
        m(b'\x0F\x28\xF8')                      # movaps xmm7,xmm0
        m(b'\xF3\x0F\x5E\xFD')                 # divss  xmm7,xmm5      f*720
        m(b'\xF3\x0F\x59\xFE')                 # mulss  xmm7,xmm6      canvasH
    else:
        m(b'\x0F\x28\xC4')                      # movaps xmm0,xmm4      f
        m.rip(b'\xF3\x0F\x59\x05', c720)       # mulss  xmm0,[720.0]   f*720
        m(b'\x0F\x28\xF3')                      # movaps xmm6,xmm3      aspect
        m(b'\xF3\x0F\x5F\xF5')                 # maxss  xmm6,xmm5      max(aspect,16/9)
        m(b'\xF3\x0F\x59\xC6')                 # mulss  xmm0,xmm6      canvasW
        m(b'\xF3\x0F\x5E\xF3')                 # divss  xmm6,xmm3      k = max/aspect
        m(b'\x0F\x28\xF8')                      # movaps xmm7,xmm0
        m(b'\xF3\x0F\x5E\xFB')                 # divss  xmm7,xmm3      canvasH = W/aspect
    m(b'\x0F\x57\xC9')                          # xorps  xmm1,xmm1
    m(b'\xF3\x44\x0F\x59\xC8')                # mulss  xmm9,xmm0
    m(b'\xF3\x41\x0F\x10\x41\x04')           # movss  xmm0,[r9+4]
    m(b'\xF3\x41\x0F\x5C\x01')                # subss  xmm0,[r9]
    m(b'\x41\x0F\x28\xD1')                     # movaps xmm2,xmm9
    m(b'\x0F\x11\x4C\x24\x20')                # movups [rsp+0x20],xmm1
    m(b'\xF3\x41\x0F\x5C\xD0')                # subss  xmm2,xmm8
    m(b'\xF3\x0F\x59\xF4')                     # mulss  xmm6,xmm4      f*k
    m(b'\xF3\x0F\x59\xF8')                     # mulss  xmm7,xmm0
    m(b'\x0F\x28\xDF')                          # movaps xmm3,xmm7
    m(b'\xF3\x41\x0F\x5C\xD8')                # subss  xmm3,xmm8


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



# --- the GUI text clip rectangle -------------------------------------------
# Right before it hands a string to the font renderer, the GUI text path sets a
# clip rectangle to the AUTHORED PAGE and nothing else:
#
#   1402e74d3  movss xmm1,[1280.0]      -> r8d
#   1402e7508  movss xmm2,[720.0]       -> r9d
#   1402e75bb  mov   edx,r14d
#   1402e75be  xor   ecx,ecx
#   1402e75c0  call  SetClipRect(0, 0, 1280, 720)
#   1402e75c8  ...   then the string is drawn
#
# SetClipRect (0x14008F8F0) just stores the four ints per viewport at +0xBC.
# This is the whole reason a HUD number vanishes when its cluster is moved out
# to the screen edge: at 21:9 the canvas is wider than the page, so anything
# past x=0 or x=1280 is outside that rectangle.  Bitmaps never go through this
# path, which is why the level badge still draws while the number inside it
# does not.
#
# The call is retargeted at a shim that widens the HORIZONTAL pair only, and
# only when it recognises the page rectangle (r8d == 1280), so any per-element
# clip box the same routine sets is left exactly as it was.  Vertical bounds
# are never touched.
TEXTCLIP = [
    0x41,0x8B,0xD6,                      # mov  edx,r14d
    0x33,0xC9,                           # xor  ecx,ecx
    0xE8,None,None,None,None,            # call SetClipRect   <- retargeted
    0x48,0x8B,0xCB,                      # mov  rcx,rbx
    0xE8,None,None,None,None,            # call (string length)
    0x85,0xC0,                           # test eax,eax
    0x7E,                                # jle
]
TEXTCLIP_CALL = 5

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

# --- (removed) An earlier 1.6 build wired the save key to ResaveLastCheckpoint
# at 0x14042E090.  That entry looks argument-free but is a script-command
# handler: it forwards its rcx to an argument parser and reads a parsed-args
# object, so calling it from the stub with rcx=0 FAULTED - the key crashed the
# game.  The save key now arms the engine's own deferred save instead
# (CheckpointMgr::RequestSave, resolved below from RequestSaveMsg::Handle),
# which the netcode itself calls with only the manager pointer and cannot fault.

# --- RequestSaveMsg::Handle -------------------------------------------------
# The host broadcasts RequestSaveMsg when a checkpoint fires; this is what the
# joined client runs on receipt.  It is the client's only route to a save, and
# it is the thing the Steam "merchant trick" guide is really groping for.  The
# handler is unique in the image and hands us both addresses we need:
#     call CheckpointMgr()      the singleton
#     jmp  RequestSave(mgr)     sets the pending-save flag + its timer
CSAVE = [
    0x48,0x83,0xEC,0x28,                  # sub rsp,0x28
    0xE8,None,None,None,None,             # call Session()
    0x48,0x8B,0x08,                       # mov rcx,[rax]
    0x48,0x8B,0x91,0xF8,0x00,0x00,0x00,   # mov rdx,[rcx+0xF8]
    0x48,0x8B,0xC8,                       # mov rcx,rax
    0xFF,0xD2,                            # call rdx
    0x85,0xC0,                            # test eax,eax
    0x74,0x11,                            # je  +0x11
    0xE8,None,None,None,None,             # call CheckpointMgr()   <- [30]
    0x48,0x8B,0xC8,                       # mov rcx,rax
    0x48,0x83,0xC4,0x28,                  # add rsp,0x28
    0xE9,None,None,None,None,             # jmp RequestSave        <- [42]
]
CSAVE_MGR, CSAVE_REQ = 28, 40      # offsets of the two rel32 operands

# RequestSave's opening, used to confirm the jmp above really lands on it and
# as the reference for the WorldName/IsHubWorld cross-check (calls at +14/+22)
REQSAVE_HEAD = [
    0x40,0x53, 0x48,0x83,0xEC,0x30, 0x48,0x8B,0xD9,
    0x48,0x8D,0x4C,0x24,0x20, 0xE8,None,None,None,None,
    0x48,0x8B,0xC8, 0xE8,None,None,None,None, 0x85,0xC0, 0x74,0x1A,
    0xC7,0x83,0xF4,0x01,0x00,0x00,0x01,0x00,0x00,0x00,   # mov [mgr+0x1F4],1
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


# --- MatrixPerspectiveFov(out, zNear, zFar, fovH, aspect, scale) -------------
# rcx=out, xmm1=zNear, xmm2=zFar, xmm3=fovH (radians), [rsp+28h]=aspect,
# [rsp+30h]=scale.  Builds m00 = scale/tan(fovH/2), m11 = aspect*m00, i.e. the
# horizontal angle is authored and the vertical one falls out of the aspect.
FOVP = [
    0x48,0x8B,0xC4,                         # mov  rax,rsp
    0x53,                                   # push rbx
    0x48,0x81,0xEC,0xB0,0x00,0x00,0x00,     # sub  rsp,0xB0
    0xF3,0x0F,0x59,0x1D,None,None,None,None,# mulss xmm3,[0.5]      fovH/2
    0x0F,0x28,0xC2,                         # movaps xmm0,xmm2
    0x48,0x8B,0xD9,                         # mov  rbx,rcx
    0x0F,0x29,0x70,0xE8,                    # movaps [rax-0x18],xmm6
    0x0F,0x28,0xF1,                         # movaps xmm6,xmm1
    0x0F,0x29,0x78,0xD8,                    # movaps [rax-0x28],xmm7
    0xF3,0x0F,0x5C,0xC6,                    # subss xmm0,xmm6       zf-zn
    0x44,0x0F,0x29,0x40,0xC8,               # movaps [rax-0x38],xmm8
    0x0F,0x28,0xFA,                         # movaps xmm7,xmm2
    0x44,0x0F,0x29,0x48,0xB8,               # movaps [rax-0x48],xmm9
    0x44,0x0F,0x29,0x50,0xA8,               # movaps [rax-0x58],xmm10
    0xF3,0x0F,0x5E,0xF8,                    # divss xmm7,xmm0       zf/(zf-zn)
    0x0F,0x28,0xC3,                         # movaps xmm0,xmm3
    0xE8,None,None,None,None,               # call  tanf            <- retargeted
]
FOV_HALF, FOV_CALL = 15, 66    # offsets of the two rel32 operands


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

    def read_f32(self, vma):
        return struct.unpack_from('<f', self.d, self.rva2off(vma - self.base))[0]

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


def patch_appendix(data, find, vk=0x74, vk_client=0x75, fov=True, fov_scale=1.0,
                   textclip=True, canvas_sites=None, split_fov=True):
    """Append .wsave and wire up whichever stubs are enabled.

    data: bytearray of a clean witn.exe.  find: the module's pattern matcher.
    Must run last - it extends the file and adds a section header.
    """
    p = _PE(data)
    save_stub = bool(vk)
    if not save_stub and not fov and not textclip and not canvas_sites:
        return

    # ---- resolve the save-key targets ---------------------------------------
    # Both keys arm the ENGINE'S OWN deferred save: CheckpointMgr()::RequestSave,
    # the exact call the netcode makes on a checkpoint.  It sets a pending-save
    # flag and a short countdown on the manager; the game's own per-frame update
    # then writes the save through DoCheckpointSave (behind every autosave) once
    # its readiness gate is quiet - which is why a save lands a few seconds after
    # the press, and only when nothing is in progress.  It needs only the manager
    # pointer, so it can never fault the way a script-command handler does when
    # handed a null context (which is what crashed the 1.6 F5).
    pump = player = gks = cpmgr = reqsave = None
    call_off = None
    need_split = bool(canvas_sites) or (fov and split_fov)
    fov_keys = bool(fov)
    if save_stub or need_split or fov_keys:
        hook_off = find(data, HOOK, "frame loop (per-frame hook site)")
        call_off = hook_off + HOOK_CALL
        disp = struct.unpack_from('<i', data, call_off + 1)[0]
        pump = p.off2vma(call_off + 5) + disp
    if save_stub:
        play_off = find(data, PLAYER, "GetLocalPlayerEntity()")
        cs_off = find(data, CSAVE, "RequestSaveMsg::Handle (save path)")
        player = p.off2vma(play_off)

        o = cs_off + CSAVE_MGR
        cpmgr = p.off2vma(o + 5) + struct.unpack_from('<i', data, o + 1)[0]
        o = cs_off + CSAVE_REQ
        reqsave = p.off2vma(o + 5) + struct.unpack_from('<i', data, o + 1)[0]
        ro = None
        for e, vs, va, rs, rp in p.secs:
            if p.base + va <= reqsave < p.base + va + max(vs, rs):
                ro = rp + (reqsave - p.base - va); break
        if ro is None or not all(b is None or data[ro + k] == b
                                 for k, b in enumerate(REQSAVE_HEAD)):
            raise SystemExit("RequestSave() does not look as expected - the "
                             "save path has changed; this build is not supported")

    if save_stub or fov_keys:
        gks = p.import_vma(b'GetKeyState')
        if gks is None:
            raise SystemExit("GetKeyState is not imported by this executable")

    # ---- resolve the FOV target ---------------------------------------------
    tanf = None
    fov_call_off = None
    if fov:
        fov_off = find(data, FOVP, "perspective projection builder")
        h = fov_off + FOV_HALF
        c_half = p.off2vma(h + 4) + struct.unpack_from('<i', data, h)[0]
        if round(p.read_f32(c_half), 6) != 0.5:
            raise SystemExit("the half-angle constant is not 0.5 - "
                             "this is not the projection builder")
        fov_call_off = fov_off + FOV_CALL
        tanf = p.off2vma(fov_call_off + 4) + \
            struct.unpack_from('<i', data, fov_call_off)[0]
        to = p.rva2off(tanf - p.base)
        if bytes(data[to:to + 2]) != b'\x83\x3d' or \
           bytes(data[to + 7:to + 9]) != b'\x0f\x84':
            raise SystemExit("tanf() does not look as expected - refusing to "
                             "redirect it; use --no-fov")

    # ---- resolve the split-screen counter -----------------------------------
    splittab = getter = None
    if need_split:
        splittab = find_splitscreen_table(data)
        getter = find_localcount_getter(data, splittab)

    # ---- resolve the text-clip target ---------------------------------------
    clip_call_off = clip_target = None
    if textclip:
        tc_off = find(data, TEXTCLIP, "GUI text clip rectangle")
        clip_call_off = tc_off + TEXTCLIP_CALL
        clip_target = p.off2vma(clip_call_off + 5) + \
            struct.unpack_from('<i', data, clip_call_off + 1)[0]

    # ---- new section geometry ------------------------------------------------
    if p.sectab + 40 * (p.nsec + 1) > min(s[4] for s in p.secs):
        raise SystemExit("no room in the PE header for another section")
    new_va = _align(max(va + vs for e, vs, va, rs, rp in p.secs), p.secalign)
    new_rp = _align(len(data), p.filealign)
    if new_rp != len(data):
        data.extend(b'\0' * (new_rp - len(data)))
    vma = p.base + new_va

    funcs = []           # (start_off_in_blob, end_off_in_blob) for .pdata
    m = _Asm(vma)
    state_fix = state2_fix = None
    fov_asp = fov_one = fov_scl = None

    # ---- stub 1: the per-frame hook (save keys + local-player count) --------
    cnt_guard = cnt_store = None
    cnt_reads = []
    frame_hook = save_stub or need_split or fov_keys
    fovkey_fix = []          # (blob offset of an 8-byte SSE op, constant name)
    if frame_hook:
        f0 = len(m.b)
        m(b'\x48\x83\xEC\x28')                       # sub  rsp,0x28
        m.rel(b'\xE8', pump)                          # call PumpMessages
        m(b'\x89\x44\x24\x20')                       # mov  [rsp+0x20],eax
    if save_stub:
        m(b'\xB9' + struct.pack('<I', vk))            # mov  ecx,VK
        m.rel(b'\xFF\x15', gks)                       # call [GetKeyState]
        m(b'\x31\xD2')                               # xor  edx,edx
        m(b'\xF6\xC4\x80')                           # test ah,0x80        key down?
        m(b'\x74\x02')                               # je   +2
        m(b'\xB2\x01')                               # mov  dl,1
        state_fix = len(m.b)
        m(b'\x48\x8D\x0D\x00\x00\x00\x00')          # lea  rcx,[rip+state]
        m(b'\x8A\x01')                               # mov  al,[rcx]        previous
        m(b'\x88\x11')                               # mov  [rcx],dl        remember
        m(b'\x84\xD2')                               # test dl,dl
        j1 = len(m.b); m(b'\x74\x00')                # je   done
        m(b'\x84\xC0')                               # test al,al
        j2 = len(m.b); m(b'\x75\x00')                # jne  done            still held
        m.rel(b'\xE8', player)                        # call GetLocalPlayerEntity
        m(b'\x48\x85\xC0')                           # test rax,rax
        j3 = len(m.b); m(b'\x74\x00')                # je   done            not in game
        m.rel(b'\xE8', cpmgr)                         # call CheckpointMgr()
        m(b'\x48\x8B\xC8')                           # mov  rcx,rax
        m.rel(b'\xE8', reqsave)                       # call RequestSave    arm the save
        done = len(m.b)
        for j in (j1, j2, j3):
            d = done - (j + 2)
            assert 0 <= d < 128
            m.b[j + 1] = d

        if vk_client:
            # second key: hand the engine the same request a host sends a client,
            # which is the only save path a joined client actually has
            m(b'\xB9' + struct.pack('<I', vk_client))     # mov  ecx,VK
            m.rel(b'\xFF\x15', gks)                       # call [GetKeyState]
            m(b'\x31\xD2')                               # xor  edx,edx
            m(b'\xF6\xC4\x80')                          # test ah,0x80
            m(b'\x74\x02')                               # je   +2
            m(b'\xB2\x01')                               # mov  dl,1
            state2_fix = len(m.b)
            m(b'\x48\x8D\x0D\x00\x00\x00\x00')      # lea  rcx,[rip+state2]
            m(b'\x8A\x01')                               # mov  al,[rcx]
            m(b'\x88\x11')                               # mov  [rcx],dl
            m(b'\x84\xD2')                               # test dl,dl
            k1 = len(m.b); m(b'\x74\x00')                # je   done2
            m(b'\x84\xC0')                               # test al,al
            k2 = len(m.b); m(b'\x75\x00')                # jne  done2
            m.rel(b'\xE8', cpmgr)                          # call CheckpointMgr()
            m(b'\x48\x8B\xC8')                          # mov  rcx,rax
            m.rel(b'\xE8', reqsave)                        # call RequestSave
            done2 = len(m.b)
            for j in (k1, k2):
                d = done2 - (j + 2)
                assert 0 <= d < 128
                m.b[j + 1] = d

    if fov_keys:
        # ---- FOV zoom keys (1.8) ------------------------------------------
        # Numpad -  zooms out (the user scale in .wsave goes up), Numpad +
        # zooms in, Numpad * puts it back to --fov-scale.  Held keys glide:
        # 0.004 per frame, clamped to 0.5 .. 2.0.  The value lives in the
        # same .wsave slot the Hor+ shim multiplies by, so the camera follows
        # on the next frame; it is not written anywhere, so a fresh launch
        # starts at --fov-scale again.
        for zvk, op, lim in ((0x6D, b'\xF3\x0F\x58\x05', 'fov_max'),   # addss / minss
                            (0x6B, b'\xF3\x0F\x5C\x05', 'fov_min')):   # subss / maxss
            m(b'\xB9' + struct.pack('<I', zvk))           # mov  ecx,VK
            m.rel(b'\xFF\x15', gks)                       # call [GetKeyState]
            m(b'\xF6\xC4\x80')                           # test ah,0x80
            jk = len(m.b); m(b'\x74\x00')                 # je   next
            fovkey_fix.append((len(m.b), 'fov_scl')); m(b'\xF3\x0F\x10\x05\x00\x00\x00\x00')  # movss xmm0,[scale]
            fovkey_fix.append((len(m.b), 'fov_step')); m(op + b'\x00\x00\x00\x00')                # addss/subss xmm0,[step]
            fovkey_fix.append((len(m.b), lim)); m((b'\xF3\x0F\x5D\x05' if lim == 'fov_max' else b'\xF3\x0F\x5F\x05') + b'\x00\x00\x00\x00')  # minss/maxss
            fovkey_fix.append((len(m.b), 'fov_scl')); m(b'\xF3\x0F\x11\x05\x00\x00\x00\x00')  # movss [scale],xmm0
            m.b[jk + 1] = len(m.b) - (jk + 2)
        m(b'\xB9' + struct.pack('<I', 0x6A))              # mov  ecx,VK_MULTIPLY
        m.rel(b'\xFF\x15', gks)                           # call [GetKeyState]
        m(b'\xF6\xC4\x80')                               # test ah,0x80
        jk = len(m.b); m(b'\x74\x00')                     # je   next
        fovkey_fix.append((len(m.b), 'fov_dflt')); m(b'\xF3\x0F\x10\x05\x00\x00\x00\x00')   # movss xmm0,[default]
        fovkey_fix.append((len(m.b), 'fov_scl')); m(b'\xF3\x0F\x11\x05\x00\x00\x00\x00')    # movss [scale],xmm0
        m.b[jk + 1] = len(m.b) - (jk + 2)

    if need_split:
        # refresh the cached local-player count once per frame, on the game
        # thread, exactly the way IsSplitscreen does - a no-op until the
        # player registry exists (table pointer still null).
        cnt_guard = len(m.b)
        m(b'\x48\x8B\x05\x00\x00\x00\x00')           # mov  rax,[rip+table ptr]
        m(b'\x48\x85\xC0')                           # test rax,rax
        cj = len(m.b); m(b'\x74\x00')                 # je   skip
        m.rel(b'\xE8', getter)                        # call GetNumLocalPlayers
        cnt_store = len(m.b)
        m(b'\x89\x05\x00\x00\x00\x00')               # mov  [rip+count],eax
        m.b[cj + 1] = len(m.b) - (cj + 2)
    if frame_hook:
        m(b'\x8B\x44\x24\x20')                       # mov  eax,[rsp+0x20]
        m(b'\x48\x83\xC4\x28')                       # add  rsp,0x28
        m(b'\xC3')                                    # ret
        funcs.append((f0, len(m.b)))

    # ---- stub 2: Hor+ FOV ----------------------------------------------------
    #
    # The engine builds its perspective matrix from a HORIZONTAL field of view
    # (default pi/2 = 90 deg) and an aspect ratio:
    #
    #     m00 = 1 / tan(fovH/2)            m11 = aspect / tan(fovH/2)
    #
    # so the horizontal angle is fixed and the VERTICAL angle shrinks as the
    # screen gets wider - Vert-.  At 21:9 the vertical FOV drops from 58.7 to
    # 45.4 degrees, which reads as the camera being pushed in.
    #
    # Scaling tan(fovH/2) by aspect/(16/9) makes m11 land on exactly the value
    # it has at 16:9 while m00 opens up: vertical FOV preserved, horizontal FOV
    # widened.  That is Hor+, the behaviour every other modern game uses.  The
    # max() floor makes it an exact no-op at 16:9 and below, so square shadow
    # and reflection cameras that share this routine are untouched.
    if fov:
        while len(m.b) % 16:
            m(b'\xCC')
        f0 = len(m.b)
        m(b'\x48\x83\xEC\x28')                       # sub  rsp,0x28
        m.rel(b'\xE8', tanf)                          # call tanf   -> tan(fov/2)
        asp_fix = len(m.b)
        m(b'\xF3\x0F\x10\x8C\x24\x10\x01\x00\x00')  # movss xmm1,[rsp+0x110] aspect
        r1 = len(m.b); m(b'\xF3\x0F\x59\x0D\x00\x00\x00\x00')  # mulss xmm1,[9/16]
        # ---- split screen: give each half the whole screen's camera ------
        # In two-player split each viewport is half as wide, so the authored
        # 90-degree horizontal view reads as zoomed in next to the fullscreen
        # Hor+ camera.  Doubling the tangent term here is exactly "treat the
        # pair of viewports as one screen": at 3440x1440 a 1720x1440 half gets
        # the same 106.7-degree horizontal view as fullscreen; on a 2x1080p
        # Surround pair each 16:9 half gets the 126.9 degrees of 32:9 single
        # player.  Guarded by aspect > 1 so the square shadow / reflection
        # cameras that share this routine are never touched, and by the cached
        # engine local-player count (== 2 only in two-player split, so plain
        # single player and online co-op can never take this branch).
        # square shadow / reflection cameras (aspect <= 1) are never touched:
        # their term would be under 1.0, so skip the whole scaling for them.
        rc = len(m.b); m(b'\x0F\x2F\x0D\x00\x00\x00\x00')      # comiss xmm1,[9/16]
        jsq = len(m.b); m(b'\x76\x00')                             # jbe  done (aspect<=1)
        # the Hor+ floor comes FIRST: at 16:9 and below the term is 1.0 (stock
        # camera), above it opens up.  The user scale is applied after it, so
        # zooming IN (scale < 1) works at every aspect ratio - up to 1.7.2 the
        # floor came last and a scale under 1 could not get past it.
        r3 = len(m.b); m(b'\xF3\x0F\x5F\x0D\x00\x00\x00\x00')  # maxss xmm1,[1.0]
        r4 = None
        if split_fov:
            cnt_reads.append(len(m.b))
            m(b'\x83\x3D\x00\x00\x00\x00\x02')                # cmp dword [rip+count],2
            jn2 = len(m.b); m(b'\x75\x00')                         # jne  norm  (not 2P split)
            r4 = len(m.b); m(b'\xF3\x0F\x59\x0D\x00\x00\x00\x00')  # mulss xmm1,[2.0]
            m.b[jn2 + 1] = len(m.b) - (jn2 + 2)
        r2 = len(m.b); m(b'\xF3\x0F\x59\x0D\x00\x00\x00\x00')  # mulss xmm1,[scale]  user zoom
        m(b'\xF3\x0F\x59\xC1')                       # mulss xmm0,xmm1
        m.b[jsq + 1] = len(m.b) - (jsq + 2)           # done:
        m(b'\x48\x83\xC4\x28')                       # add  rsp,0x28
        m(b'\xC3')                                    # ret
        funcs.append((f0, len(m.b)))

    # ---- stub 3: the text clip ----------------------------------------------
    # A leaf: it never touches rsp and tail-jumps to the original, so it needs
    # no unwind entry and is not added to `funcs`.
    if textclip:
        while len(m.b) % 16:
            m(b'\xCC')
        clip_stub = len(m.b)
        m(b'\x41\x81\xF8\x00\x05\x00\x00')       # cmp  r8d,1280
        m(b'\x75\x0B')                              # jne  pass
        m(b'\xB9\x00\xF0\xFF\xFF')                # mov  ecx,-4096
        m(b'\x41\xB8\x00\x20\x00\x00')            # mov  r8d,8192
        m.rel(b'\xE9', clip_target)                  # pass: jmp SetClipRect
    else:
        clip_stub = None

    # ---- stubs 4+5: the split-aware canvas ----------------------------------
    # Both canvas sites are detoured here.  Each stub checks the cached engine
    # local-player count: EXACTLY 2 (two-player split screen) takes the FILL maths so
    # each split viewport's page spans that viewport - the HUD sits complete at
    # the viewport edges, as the console split screen draws it, and on a
    # 16:9-per-player monitor pair it is pixel-perfect.  Any other count
    # (1 = normal play and online co-op, 3 = tri, 0 = boot) takes FIT, which is
    # byte-for-byte the 1.5 behaviour.
    canvas_a_stub = canvas_b_stub = None
    if canvas_sites:
        cs = canvas_sites
        m.rip = m.rel                      # the emitters call Asm.rip(...)
        # rax and flags are dead at both detour points (site A is the GetCanvas
        # tail about to return; site B sits immediately before its epilogue),
        # so we can freely test the cached count.
        def _split_test():
            # cmp dword [rip+count],2   (7 bytes; disp fixed up with the blob)
            cnt_reads.append(len(m.b))
            m(b'\x83\x3D\x00\x00\x00\x00\x02')
        while len(m.b) % 16:
            m(b'\xCC')
        canvas_a_stub = len(m.b)
        _split_test()
        ja = len(m.b); m(b'\x75\x00')                # jne fit (count != 2)
        _emit_canvas_a(m, 'fill', cs['c1280'], cs['c720'], cs['c169'])
        m.b[ja + 1] = len(m.b) - (ja + 2)
        _emit_canvas_a(m, 'fit', cs['c1280'], cs['c720'], cs['c169'])
        while len(m.b) % 16:
            m(b'\xCC')
        canvas_b_stub = len(m.b)
        b_back = p.off2vma(cs['b_off']) + len(B_ORIG)
        _split_test()
        jb_ = len(m.b); m(b'\x75\x00')               # jne fit (count != 2)
        _emit_canvas_b(m, 'fill', cs['c1280'], cs['c720'])
        m.rel(b'\xE9', b_back)                        # jmp back
        m.b[jb_ + 1] = len(m.b) - (jb_ + 2)
        _emit_canvas_b(m, 'fit', cs['c1280'], cs['c720'])
        m.rel(b'\xE9', b_back)                        # jmp back

    code_len = len(m.b)
    blob = bytearray(m.b)
    while len(blob) % 4:
        blob.append(0xCC)
    unwind_rva = new_va + len(blob)
    blob += bytes([0x01, 0x04, 0x01, 0x00, 0x04, 0x42, 0x00, 0x00])
    if fov:
        fov_asp = new_va + len(blob); blob += struct.pack('<f', 9 / 16)
        fov_one = new_va + len(blob); blob += struct.pack('<f', 1.0)
        fov_scl = new_va + len(blob); blob += struct.pack('<f', fov_scale)
        fov_two = new_va + len(blob); blob += struct.pack('<f', 2.0)
        fov_consts = {'fov_scl': fov_scl,
                      'fov_dflt': new_va + len(blob)}; blob += struct.pack('<f', fov_scale)
        fov_consts['fov_step'] = new_va + len(blob); blob += struct.pack('<f', 0.004)
        fov_consts['fov_min'] = new_va + len(blob); blob += struct.pack('<f', 0.5)
        fov_consts['fov_max'] = new_va + len(blob); blob += struct.pack('<f', 2.0)
        # 8-byte SSE ops: disp at +4, rip = +8
        for slot, tgt in [(r1, fov_asp), (r2, fov_scl), (r3, fov_one), (r4, fov_two)] + \
                         [(off, fov_consts[name]) for off, name in fovkey_fix]:
            if slot is None:
                continue
            ip = vma + slot + 8
            struct.pack_into('<i', blob, slot + 4, (p.base + tgt) - ip)
        if rc is not None:      # comiss: 7 bytes, disp at +3
            struct.pack_into('<i', blob, rc + 3, (p.base + fov_asp) - (vma + rc + 7))
    cnt_rva = None
    if need_split:
        cnt_rva = new_va + len(blob)
        blob += struct.pack('<I', 0)                  # cached local-player count
        ctgt = p.base + cnt_rva
        for cs_ in cnt_reads:   # cmp dword [rip+d],2 : 7 bytes, disp at +2
            struct.pack_into('<i', blob, cs_ + 2, ctgt - (vma + cs_ + 7))
        # frame hook: mov rax,[rip+table] (disp +3, len 7) then
        # mov [rip+count],eax (disp +2, len 6)
        struct.pack_into('<i', blob, cnt_guard + 3, splittab - (vma + cnt_guard + 7))
        struct.pack_into('<i', blob, cnt_store + 2, ctgt - (vma + cnt_store + 6))
    state_rva = state2_rva = None
    if save_stub:
        state_rva = new_va + len(blob)
        blob.append(0x00)                             # previous key state
        state2_rva = new_va + len(blob)
        blob.append(0x00)                             # previous key state, 2nd key
        ip = vma + state_fix + 7
        struct.pack_into('<i', blob, state_fix + 3, (p.base + state_rva) - ip)
        if state2_fix is not None:
            ip2 = vma + state2_fix + 7
            struct.pack_into('<i', blob, state2_fix + 3, (p.base + state2_rva) - ip2)

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

    # ---- .pdata entries so SEH can unwind through the stubs ------------------
    # both stubs open with 'sub rsp,0x28', so they share one UNWIND_INFO
    pd_rva, pd_size = p.datadir(3)
    tail = p.rva2off(pd_rva) + pd_size
    need = 12 * len(funcs)
    if any(data[tail:tail + need]):
        raise SystemExit(".pdata has no slack for the stubs' unwind entries")
    for i, (s, en) in enumerate(funcs):
        struct.pack_into('<III', data, tail + 12 * i,
                         new_va + s, new_va + en, unwind_rva)
    p.set_datadir(3, pd_rva, pd_size + need)
    for ent, vs, va, rs, rp in p.secs:                # grow .pdata's VirtualSize
        if va <= pd_rva < va + max(vs, rs):
            if pd_size + need > rs:
                raise SystemExit(".pdata raw block is full")
            struct.pack_into('<I', data, ent + 8, max(vs, pd_size + need))
            break

    # ---- redirect the call sites --------------------------------------------
    if frame_hook:
        struct.pack_into('<i', data, call_off + 1,
                         (vma + funcs[0][0]) - p.off2vma(call_off + 5))
    if fov:
        fs = funcs[-1][0]
        struct.pack_into('<i', data, fov_call_off,
                         (vma + fs) - p.off2vma(fov_call_off + 4))

    if textclip:
        struct.pack_into('<i', data, clip_call_off + 1,
                         (vma + clip_stub) - p.off2vma(clip_call_off + 5))

    if canvas_sites:
        cs = canvas_sites
        ao, bo = cs['a_off'], cs['b_off']
        if not all(b is None or data[ao + k] == b for k, b in enumerate(A_ORIG)) \
           or not all(b is None or data[bo + k] == b for k, b in enumerate(B_ORIG)):
            raise SystemExit("canvas sites changed underfoot - refusing")
        jmp = b'\xE9' + struct.pack('<i', (vma + canvas_a_stub) - (p.off2vma(ao) + 5))
        data[ao:ao + A_ROOM] = jmp + b'\xCC' * (A_ROOM - 5)
        jmp = b'\xE9' + struct.pack('<i', (vma + canvas_b_stub) - (p.off2vma(bo) + 5))
        data[bo:bo + len(B_ORIG)] = jmp + b'\xCC' * (len(B_ORIG) - 5)

    # ---- PE checksum ---------------------------------------------------------
    # the shipped executable stores 0 (Windows only enforces this for drivers);
    # only recompute if the vendor actually filled it in.
    if struct.unpack_from('<I', data, p.opt + 64)[0]:
        struct.pack_into('<I', data, p.opt + 64, 0)
        struct.pack_into('<I', data, p.opt + 64, _checksum(data))

    nm = SEC_NAME.rstrip(b'\x00').decode()
    if textclip:
        print(f"  text clip  : SetClipRect call @ 0x{clip_call_off:X} -> shim "
              f"0x{vma + clip_stub:X} (page rect 0/1280 -> -4096/8192 on X only; "
              f"real routine 0x{clip_target:X})")
    if save_stub:
        print(f"  save key   : hook @ 0x{call_off:X} -> section {nm} @ 0x{new_rp:X} "
              f"(VK 0x{vk:02X}); RequestSave=0x{reqsave:X} mgr=0x{cpmgr:X} "
              f"guard=0x{player:X})")
        if vk_client:
            print(f"  client save: VK 0x{vk_client:02X} -> RequestSave 0x{reqsave:X} "
                  f"on mgr 0x{cpmgr:X}")
    if canvas_sites:
        print(f"  gui canvas : split-aware @ 0x{canvas_sites['a_off']:X}/"
              f"0x{canvas_sites['b_off']:X} -> stubs 0x{vma + canvas_a_stub:X}/"
              f"0x{vma + canvas_b_stub:X} (FILL when GetNumLocalPlayers() == 2, "
              f"else FIT)")
    if need_split:
        print(f"  player count: getter 0x{getter:X} called per frame, cached @ "
              f"0x{p.base + cnt_rva:X} (guard: table ptr 0x{splittab:X})")
    if fov:
        print(f"  fov (hor+) : tan call @ 0x{fov_call_off - 1:X} -> shim "
              f"0x{vma + funcs[-1][0]:X} (tanf 0x{tanf:X}, extra scale "
              f"{fov_scale:g})")
        print(f"               zoom keys: Numpad - out, Numpad + in, Numpad * reset "
              f"(0.5 .. 2.0 x, not saved between launches)")
        if split_fov:
            print(f"               split screen: each half gets the whole-screen "
                  f"camera (tangent x2 when the cached player count is 2, aspect>1)")


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


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _build_id(path):
    """(PE link timestamp, .text VirtualSize) - identifies the GAME BUILD and
    survives everything the mods append (.wsave, .byoh), so two files with
    different ids are different releases of the game, not different mods."""
    try:
        with open(path, 'rb') as f:
            hdr = f.read(0x600)
        pe = struct.unpack_from('<I', hdr, 0x3C)[0]
        ts = struct.unpack_from('<I', hdr, pe + 8)[0]
        nsec = struct.unpack_from('<H', hdr, pe + 6)[0]
        opt = struct.unpack_from('<H', hdr, pe + 20)[0]
        for i in range(nsec):
            e = pe + 24 + opt + i * 40
            if hdr[e:e + 8].rstrip(b'\0') == b'.text':
                return ts, struct.unpack_from('<I', hdr, e + 8)[0]
        return ts, 0
    except (OSError, struct.error):
        return None


def _build_name(bid):
    return {(1784922545, 0x9e46af): 'launch build (linked 2026-07-24)',
            (1787159334, 0x9e5c1f): 'Patch 1 / v1.000.003 (linked 2026-08-19)'
            }.get(bid, f'unknown build {bid}')


def _looks_like_ours(path):
    """True if this executable already carries our appended section."""
    try:
        with open(path, 'rb') as f:
            return b'.wsave' in f.read(0x600)
    except OSError:
        return False


def _stamp_read(stamp):
    """(sha, mode) from the stamp file; mode is '' for a pre-mode stamp."""
    try:
        parts = open(stamp).read().split()
    except OSError:
        return ('', '')
    return (parts[0] if parts else '', parts[1] if len(parts) > 1 else '')


def guard_downgrade(exe, stamp, mode, force):
    """Stop a save-keys-only run from quietly stripping an ultrawide install.

    Both packages drive this same script, so a user who installs Ultrawide and
    then runs the save-keys installer would get exactly what they asked for and
    lose the widescreen fix without being told.
    """
    if force or mode != 'save-only' or not os.path.isfile(stamp):
        return
    sha, was = _stamp_read(stamp)
    if was != 'ultrawide' or not os.path.isfile(exe) or _sha(exe) != sha:
        return
    raise SystemExit(
        f"{exe} already has the ultrawide patches, and those already include\n"
        f"these save keys - the Ultrawide package is a superset of the Save Keys\n"
        f"package, so there is nothing here to add.\n"
        f"\n"
        f"Going ahead would strip the widescreen fix back out, so this is a\n"
        f"refusal rather than a guess.  You already have F5 and F6; just play.\n"
        f"\n"
        f"If you really do want to drop the ultrawide patches and keep only the\n"
        f"save keys, say so explicitly:\n"
        f"      python witn_patch.py --save-only --force")


def guard_foreign(exe, backup, stamp):
    """Refuse to rebuild from a stale backup if another mod replaced the exe.

    Every run rebuilds from witn.exe.original, which is right when we are the
    only thing editing witn.exe and destructive when we are not: another mod's
    installer overwriting witn.exe would be silently undone on our next run.
    So compare what is on disk against what we last wrote and stop if they
    disagree.
    """
    if not os.path.isfile(backup):
        return                              # first run: nothing to protect
    current = _sha(exe)
    if current == _sha(backup):
        return                              # untouched, or freshly reverted
    if os.path.isfile(stamp):
        if current == _stamp_read(stamp)[0]:
            return                          # exactly what we wrote last time
    elif _looks_like_ours(exe):
        return                              # our build, from an older script
    # A GAME UPDATE: Steam put down a stock executable of a different build.
    # The backup is now a stale copy of the OLD game and must never be the
    # baseline again (rebuilding from it would silently downgrade the game).
    # Keep it under a build-tagged name and let the caller take a fresh one.
    cur_id, bak_id = _build_id(exe), _build_id(backup)
    if cur_id and bak_id and cur_id != bak_id and not _looks_like_ours(exe):
        keep = f"{backup}.build-{bak_id[0]}"
        if not os.path.exists(keep):
            os.replace(backup, keep)
        else:
            os.remove(backup)
        if os.path.isfile(stamp):
            os.remove(stamp)
        print(f"GAME UPDATE detected: {exe} is {_build_name(cur_id)}, the old backup was\n"
              f"  {_build_name(bak_id)}.  The old backup is kept as {keep}; the\n"
              f"  current executable becomes the new stock baseline.  Every address is\n"
              f"  re-found by byte signature, so the patches land on the new build.")
        return
    raise SystemExit(
        f"{exe} has been changed by something other than this script - another\n"
        f"mod has replaced it since the last run.\n"
        f"\n"
        f"Rebuilding from {backup} would silently undo that mod, so this is a\n"
        f"refusal rather than a guess.  Pick one:\n"
        f"\n"
        f"  keep the other mod, and put these patches on top of it:\n"
        f"      python witn_patch.py --rebase <your usual options>\n"
        f"  {backup} then holds the other mod, and --revert goes back to it.\n"
        f"\n"
        f"  or drop the other mod and start clean:\n"
        f"      python witn_patch.py --revert\n"
        f"  then run this again.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe', default='witn.exe')
    ap.add_argument('--res', default='3440x1440')
    ap.add_argument('--no-res', action='store_true',
                    help='skip the resolution unlock - use with --no-gui when you play '
                         'at a normal aspect ratio and only want the quicksave key')
    ap.add_argument('--no-gui', action='store_true')
    ap.add_argument('--save-only', action='store_true',
                    help='apply ONLY the save keys - no resolution unlock, no GUI '
                         'canvas fix, no field-of-view change.  Shorthand for '
                         '--no-res --no-gui --no-fov, for players who are not on '
                         'an ultrawide monitor')
    ap.add_argument('--keep-43', action='store_true',
                    help='leave the 4:3 entry alone.  By default BOTH unused-ish '
                         'entries are retargeted - 5:4 to the 21:9 family and 4:3 to '
                         'the 32:9 family - so one build covers every ultrawide.  '
                         'Pass this if you actually want 4:3 modes in the list, at '
                         'the cost of 32:9 support.')
    ap.add_argument('--hud', choices=['fit', 'fill'], default='fit',
                    help="fit = correct proportions with side bars (default); "
                         "fill = 2D layer spans the full width, ~34%% wider at 21:9")
    ap.add_argument('--no-split-canvas', action='store_true',
                    help="in the default 'fit' mode, do NOT make the canvas "
                         "split-screen-aware.  By default the two canvas sites "
                         "are detoured so that TWO-PLAYER local split screen "
                         "fills each viewport (each half-screen gets its own "
                         "page), while single player, online co-op and 3-player "
                         "tri stay exactly as before.  Pass this to keep the old "
                         "static fit patch.  Ignored with --hud fill.")
    ap.add_argument('--no-split-fov', action='store_true',
                    help="in two-player split screen, do NOT widen each half's "
                         "camera to the whole screen's field of view.  Default: "
                         "each half gets the same horizontal FOV as fullscreen "
                         "single player, so split does not read as zoomed in.")
    ap.add_argument('--no-savekey', action='store_true')
    ap.add_argument('--no-text-clip', action='store_true',
                    help='leave the GUI text clip rectangle alone.  It is set to the authored 1280x720 page before every string, which is why HUD numbers vanish once their cluster is moved out to the screen edge at 21:9.')
    ap.add_argument('--no-fov', action='store_true',
                    help='skip the Hor+ field-of-view fix (it is a no-op at 16:9 '
                         'and below, so there is rarely a reason to)')
    ap.add_argument('--fov-scale', type=float, default=1.0,
                    help='extra field-of-view multiplier on top of the Hor+ fix; '
                         '1.0 = stock framing (default), 1.1 = a little wider, '
                         '0.95 = a little tighter')
    ap.add_argument('--save-key', default='0x74',
                    help='virtual-key code for the quicksave key (default 0x74 = F5)')
    ap.add_argument('--client-save-key', default='0x75',
                    help='virtual-key code that asks the engine for a CLIENT-side '
                         'save - the path a joined player normally only gets when '
                         'the host requests it (default 0x75 = F6; 0 disables)')
    ap.add_argument('--force', action='store_true',
                    help='go ahead even if this would strip patches the exe '
                         'already has (see --save-only)')
    ap.add_argument('--revert', action='store_true')
    ap.add_argument('--rebase', action='store_true',
                    help='adopt the CURRENT witn.exe as the new stock baseline before '
                         'patching - use after installing a mod that replaces witn.exe')
    a = ap.parse_args()

    if a.save_only:
        if a.no_savekey:
            raise SystemExit("--save-only and --no-savekey together would leave "
                             "nothing to do")
        a.no_res = a.no_gui = a.no_fov = True

    if not os.path.isfile(a.exe):
        raise SystemExit(f"{a.exe} not found - run from the game folder or use --exe")
    backup = a.exe + '.original'
    stamp = a.exe + '.wpatch'

    if a.revert:
        if not os.path.isfile(backup):
            raise SystemExit(f"{backup} is missing - use Steam's "
                             f"'Verify integrity of game files' instead")
        cur_id, bak_id = _build_id(a.exe), _build_id(backup)
        if cur_id and bak_id and cur_id != bak_id:
            raise SystemExit(
                f"{backup} is from {_build_name(bak_id)} but the game is now\n"
                f"{_build_name(cur_id)} - restoring it would DOWNGRADE the game.\n"
                f"Use Steam's 'Verify integrity of game files' to get a stock exe.")
        shutil.copyfile(backup, a.exe)
        if os.path.isfile(stamp):
            os.remove(stamp)
        print(f"restored {a.exe} from {backup}")
        return

    if a.rebase:
        probe = bytearray(open(a.exe, 'rb').read())
        for pat, what in ((list(ASPECTS[:12]) + [None] * 4, 'aspect table'),
                          (A_ORIG, 'canvas site A'), (B_ORIG, 'canvas site B'),
                          (HOOK, 'frame loop')):
            find(probe, pat, what)      # raises if this exe is already patched
        shutil.copyfile(a.exe, backup)
        if os.path.isfile(stamp):
            os.remove(stamp)
        print(f"rebased: {backup} now holds the current (modded) executable")
    else:
        guard_foreign(a.exe, backup, stamp)
        guard_downgrade(a.exe, stamp,
                        'save-only' if (a.no_res and a.no_gui) else 'ultrawide',
                        a.force)
    if not os.path.exists(backup):
        shutil.copyfile(a.exe, backup)
        print(f"backup written: {backup}")
    data = bytearray(open(backup, 'rb').read())   # always patch a clean copy
    secs = sections(data)
    if a.no_res and not a.no_gui:
        raise SystemExit("--no-res without --no-gui makes no sense: the canvas fix "
                         "only matters once an ultrawide mode is selectable")
    if not a.no_res:
        patch_resolution(data, secs, a.res, a.keep_43)
    # The split-aware canvas detour and the in-place canvas patch are mutually
    # exclusive - both own sites A and B.  Use the detour by default in fit
    # mode; fall back to the static patch for --hud fill or --no-split-canvas.
    split_canvas = (not a.no_gui and a.hud == 'fit' and not a.no_split_canvas)
    canvas_sites = None
    if not a.no_gui:
        if split_canvas:
            canvas_sites = find_canvas_sites(data, secs)   # detour, don't patch
        else:
            patch_site_a(data, secs, a.hud)
            patch_site_b(data, secs, a.hud)
    if not (0.25 <= a.fov_scale <= 4.0):
        raise SystemExit("--fov-scale must be between 0.25 and 4.0")
    patch_appendix(data, find,
                   0 if a.no_savekey else int(str(a.save_key), 0),
                   int(str(a.client_save_key), 0),
                   not a.no_fov, a.fov_scale,
                   textclip=not a.no_text_clip and not a.no_gui,
                   canvas_sites=canvas_sites,
                   split_fov=not a.no_split_fov)                 # must be last
    open(a.exe, 'wb').write(bytes(data))
    open(stamp, 'w').write(
        _sha(a.exe) + ' ' +
        ('save-only' if (a.no_res and a.no_gui) else 'ultrawide') + '\n')
    print("done - fully quit the game before relaunching")


if __name__ == '__main__':
    main()
