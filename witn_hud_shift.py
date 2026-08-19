#!/usr/bin/env python3
"""
War in the North (Legacy Edition) - ultrawide HUD reposition
============================================================

Companion to witn_patch.py --hud fit.

With the `fit` patch the 2D layer keeps its correct proportions but the whole
1280x720 layout is centred, so at 21:9 the HUD sits ~220 layout units (440px)
in from each screen edge.  This tool pushes the edge-anchored HUD clusters
back out by that same amount, so they sit exactly as far from the screen edge
as they did at 16:9 - without stretching anything.

It edits res/gui/hud/_bin/pc64/hud_hd.s2.sdf in place (a backup .original is
made first).  The file is a property tree: 16-byte records of
(childCount, nameCRC, type, slot) with values in a flat 4-byte slot pool, and
names resolved through res/engine/_bin/pc64/stringcrctable.est.  Only the
Position (vec3) of the whitelisted top-level elements is touched - two floats
per element, nothing is inserted or moved.

Usage (from the game folder):
    python3 witn_hud_shift.py                 # shift for 3440x1440
    python3 witn_hud_shift.py --res 5120x1440
    python3 witn_hud_shift.py --list          # show elements + positions, no edit
    python3 witn_hud_shift.py --revert
"""
import argparse, os, shutil, struct

HUD = os.path.join('res', 'gui', 'hud', '_bin', 'pc64', 'hud_hd.s2.sdf')
CRC = os.path.join('res', 'engine', '_bin', 'pc64', 'stringcrctable.est')

# top-level HUD clusters that hug a screen edge.  Everything else - anything
# centred, anything that is a child of one of these, and the editor guides -
# is deliberately left alone.
LEFT = {
    'MainHud', 'MainHud1', 'MainHud2', 'MainHudPC',
    'Player_Human', 'Player_Elf', 'Player_Dwarf',
    'Allies_Human', 'Allies_Elf', 'Allies_Dwarf',
    'AllyStatus1', 'AllyStatus2', 'BloodMeter1', 'BloodMeter2',
    'AllyName1', 'AllyName2', 'PlayerCharacterBuffs',
    'LootLog', 'QuestItemLootLog', 'DurabilityAlert',
    'StateText', 'HoveringName', 'belleram',
}

# the bottom-left party cluster: shrunk together, anchored to the bottom-left
# corner so it stays hugged into it as it gets smaller.
CLUSTER = {
    'MainHud', 'MainHud1', 'MainHud2', 'MainHudPC',
    'Player_Human', 'Player_Elf', 'Player_Dwarf',
    'Allies_Human', 'Allies_Elf', 'Allies_Dwarf',
    'AllyStatus1', 'AllyStatus2', 'BloodMeter1', 'BloodMeter2',
    'AllyName1', 'AllyName2', 'PlayerCharacterBuffs',
}
# pushed further into the bottom-right corner than the plain edge-restore
CORNER = {'SkillBacker', 'SkillBackerPC', 'Ammo', 'AmmoPC'}
RIGHT = {
    'SkillBacker', 'SkillBackerPC', 'DpadUI',
    'Ammo', 'AmmoPC', 'ShowTotalAmmo', 'HideTotalAmmo',
    'QuestStatusBarCollection', 'HudCombatFeedback',
    'HudCombatFeedbackHitCounter', 'CombatLogCollection',
    'Popups', 'RangedMode',
}


def load_crc(path):
    d = open(path, 'rb').read()
    n = struct.unpack_from('<Q', d, 0x88)[0]
    strs = []
    for k in range(n):
        so, ln, _ = struct.unpack_from('<QQQ', d, 0x98 + k * 24)
        strs.append(d[so + 0x80:so + 0x80 + ln].split(b'\x00')[0].decode('latin1'))
    tab = {struct.unpack_from('<I', d, 0x90)[0]: strs[0]}
    for k in range(n - 1):
        tab[struct.unpack_from('<QQQ', d, 0x98 + k * 24)[2]] = strs[k + 1]
    return tab


class Sdf:
    BASE, POOL, STR = 0x1b10, 0x351bc, 0x1b08

    def __init__(self, path, tab):
        self.h = bytearray(open(path, 'rb').read())
        self.tab = tab
        self.recs = []
        o = self.BASE
        while o + 16 <= len(self.h):
            f0, cr, t, v = struct.unpack_from('<4I', self.h, o)
            if cr not in tab:
                break
            self.recs.append((o, f0, tab[cr], t, v))
            o += 16
        if len(self.recs) < 1000:
            raise SystemExit("hud file does not parse as expected - wrong version?")

    def s(self, slot):
        a = self.STR + struct.unpack_from('<I', self.h, self.POOL + slot * 4)[0]
        j = a
        while j < len(self.h) and self.h[j] != 0:
            j += 1
        return self.h[a:j].decode('latin1', 'replace')

    def pos(self, slot):
        return struct.unpack_from('<3f', self.h, self.POOL + slot * 4)

    def setx(self, slot, x):
        struct.pack_into('<f', self.h, self.POOL + slot * 4, x)

    def sety(self, slot, y):
        struct.pack_into('<f', self.h, self.POOL + slot * 4 + 4, y)

    def nodes(self):
        """[(name, {'Position': [slots], 'Scale': [slots]})] - a node runs from
        one Name record to the next.  A node can hold several Position/Scale
        records: those are animation keyframes and must all move together."""
        out, cur = [], None
        for _, _, nm, t, v in self.recs:
            if nm == 'Name' and t == 4:
                try:
                    cur = (self.s(v), {'Position': [], 'Scale': []})
                except Exception:
                    cur = ('?', {'Position': [], 'Scale': []})
                out.append(cur)
            elif cur is not None and t == 64 and nm in ('Position', 'Scale'):
                cur[1][nm].append(v)
        return out

    def elements(self):
        """(name, slot, x, y) for every Position, tagged with the preceding Name."""
        cur, out = '?', []
        for _, _, nm, t, v in self.recs:
            if nm == 'Name' and t == 4:
                try:
                    cur = self.s(v)
                except Exception:
                    cur = '?'
            elif nm == 'Position' and t == 64:
                x, y, _z = self.pos(v)
                out.append((cur, v, x, y))
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--res', default='3440x1440')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--revert', action='store_true')
    ap.add_argument('--hud-scale', type=float, default=0.85,
                    help='size of the whole in-game HUD (1.0 = unchanged)')
    ap.add_argument('--cluster-scale', type=float, default=1.0,
                    help='extra factor applied to the bottom-left party cluster only')
    ap.add_argument('--corner-nudge', default='30,30',
                    help='extra dx,dy in layout units pushing the skill bar into the corner')
    a = ap.parse_args()

    hud = os.path.join(a.root, HUD)
    bak = hud + '.original'
    if not os.path.isfile(hud):
        raise SystemExit(f"{hud} not found - run from the game folder")

    if a.revert:
        if not os.path.isfile(bak):
            raise SystemExit(f"{bak} missing - use Steam's Verify integrity instead")
        shutil.copyfile(bak, hud)
        print(f"restored {hud}")
        return

    w, h = (int(x) for x in a.res.lower().split('x'))
    aspect = w / h
    shift = (720.0 * max(aspect, 16 / 9) - 1280.0) / 2.0
    print(f"{a.res}: canvas {720*max(aspect,16/9):.0f}x720, edge shift {shift:.1f} layout units "
          f"({shift * w / (720*max(aspect,16/9)):.0f}px)")

    tab = load_crc(os.path.join(a.root, CRC))
    if not os.path.exists(bak):
        shutil.copyfile(hud, bak)
        print(f"backup written: {bak}")
    d = Sdf(bak, tab)          # always start from the pristine copy

    if a.list:
        for nm, slot, x, y in d.elements():
            if abs(x - 640) > 150 or abs(y - 360) > 150:
                print(f"  {nm[:36]:<36} x={x:<9.1f} y={y:<8.1f} slot={slot}")
        return

    g_all = a.hud_scale
    g_cluster = a.cluster_scale
    dx, dy = (float(t) for t in a.corner_nudge.split(','))
    left_edge, right_edge = -shift, 1280.0 + shift

    moved = scaled = nudged = 0
    for name, props in d.nodes():
        if name not in LEFT and name not in RIGHT:
            continue
        g = g_all * (g_cluster if name in CLUSTER else 1.0)
        ax = left_edge if name in LEFT else right_edge
        for ps in props['Position']:
            x, y, _z = d.pos(ps)
            # 1. put the element back at its 16:9 distance from the screen edge
            if name in LEFT and x < 640:
                x -= shift; moved += 1
            elif name in RIGHT and x > 640:
                x += shift; moved += 1
            # 2. shrink toward the corner this element is anchored to
            if abs(g - 1.0) > 1e-6:
                ay = 0.0 if y < 360 else 720.0
                x = ax + (x - ax) * g
                y = ay + (y - ay) * g
            # 3. push the skill bar that bit further into the corner
            if name in CORNER:
                x += dx; y += dy; nudged += 1
            d.setx(ps, x); d.sety(ps, y)
        if abs(g - 1.0) > 1e-6:
            for ss in props['Scale']:
                for k in range(3):
                    off = d.POOL + (ss + k) * 4
                    v = struct.unpack_from('<f', d.h, off)[0]
                    struct.pack_into('<f', d.h, off, v * g)
                scaled += 1
    print(f"  edge-restored {moved} positions, scaled {scaled} nodes "
          f"(hud {g_all:g}, party cluster {g_all*g_cluster:g}), corner-nudged {nudged}")
    open(hud, 'wb').write(bytes(d.h))
    print("done - fully quit the game before relaunching")


if __name__ == '__main__':
    main()
