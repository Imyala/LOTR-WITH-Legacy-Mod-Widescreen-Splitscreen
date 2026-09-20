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

__author__ = 'Imyala'
__license__ = 'MIT'
__credits__ = ['Imyala']
import argparse, hashlib, os, shutil, struct

HUD = os.path.join('res', 'gui', 'hud', '_bin', 'pc64', 'hud_hd.s2.sdf')
FE = os.path.join('res', 'gui', 'frontend', '_bin', 'pc64', 'frontend_hd.s2.sdf')

# The loading screens are the one part of the 2D layer that CAN be made to fill
# an ultrawide screen cleanly, because they are built out of full-page backdrop
# layers rather than positioned widgets.  Every one of them is anchored at or
# just outside the top-left of the authored page (x = -1 or -5, and -44/-19 on
# the boot screen) and stretched over it by its own Scale, with the fire and
# smoke sprites parented to those layers.  Widening a layer therefore carries
# its sprites with it, and nothing has to leave the page - which is what killed
# the attempt at doing this to the menus.
#
# So: any element whose x is NEGATIVE is a backdrop that already bleeds off the
# left edge, and gets moved out to the canvas edge and scaled to span it.
# Anything at x >= 0 is either centred (the tip line at 640, the logo) or a
# child sprite (smoke at 350, fire at 255) and is left completely alone.
LOAD = [os.path.join('res', 'gui', 'load', '_bin', 'pc64', f + '.s2.sdf')
        for f in ('load', 'new', 'quit', 'boot')]
CRC = os.path.join('res', 'engine', '_bin', 'pc64', 'stringcrctable.est')

# The video-options mode list appends a localised " (Widescreen)" to every mode
# the engine classes as wide.  The text is a string-table entry keyed
# 'widescreen' in gui_tables.s2.sdf: the ASCII key, padded to 4 bytes, then one
# null-terminated UTF-16 string per language (English, French, Spanish,
# Russian, Polish, Korean, Japanese, Chinese, then empty slots), each padded to
# 4 bytes, up to the next ASCII key.  1.8 blanks every one of them (first code
# unit -> a space, nothing moves, file size unchanged) so the list shows only the
# resolution.  Both copies the depot carries are done; the PC one is the live
# one.
GUI_TABLES = [os.path.join('res', 'gamedata', 'platform', 'files', 'pc', '_bin', 'pc64', 'gui_tables.s2.sdf'),
              os.path.join('res', 'gamedata', 'platform', '_bin', 'pc64', 'gui_tables.s2.sdf')]

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
# the skill bar and the ammo counter get an extra push into the corner.  The
# Show/HideTotalAmmo animation states hold their own copy of the ammo position,
# so they have to get the identical treatment or the counter jumps whenever the
# show/hide animation plays.
# Elements INSIDE the party-frame collections.
#
# This is the thing that was wrong for a long time: MainHud, Player_* and
# Allies_* are CollectionRefElements, and a CollectionRefElement does NOT pass
# its Scale down into the collection it references.  So every "make the HUD
# smaller" pass only ever shrank the frame's own artwork while the health, mana
# and XP bars stayed full size - which is why the bottom left kept reading as
# too big, and why shrinking the frames finally left the health bar sitting on
# top of the race emblem.
#
# The bars are ModelElements (gui\models\hud_health_meter) living inside those
# collections, with Positions that are relative offsets from the collection
# origin.  They have to be scaled directly, and the offsets scaled by the same
# factor, or the group just spreads back out around a smaller frame.
BARS = {
    'HpBar', 'HpBar1', 'HpBar2', 'ManaBar', 'ManaBar1', 'ManaBar2',
    'ExpBar', 'ExpBar1', 'ExpBar2',
    'health_number', 'mana_number', 'healthback', 'manaback', 'xpback',
    'divide1', 'divide2', 'divide3', 'divide4', 'divide5', 'divide6',
    'XPFlash', 'LevelUpIndicator', 'LevelUpIndicator1', 'LevelUpIndicator2',
    'lvl_number', 'lvlBack', 'arrowR', 'arrowL',
}

CORNER = {'SkillBacker', 'SkillBackerPC', 'Ammo', 'AmmoPC',
          'ShowTotalAmmo', 'HideTotalAmmo', 'DpadUI', 'RangedMode'}

# Never touched.  These are positioned at runtime from a world position - the
# name floating over a player, floating combat numbers, the [E] use prompt.
# Their authored Position is only a template origin, so shifting it drags the
# label away from the thing it is labelling, and by an amount that changes with
# the camera angle.
# NOT 'Popups'.  That was a bad guess from the name: it is authored at
# (1050, 59), right beside QuestStatusBarCollection at (1040, 42), and it is the
# top-right notification banner - "New Quest: ..." and friends.  Treating it as
# world-anchored left it hanging at 74% of the screen while the quest tracker
# next to it went out to 86%, which is what made the corner look wrong.  It is
# in RIGHT instead, so the two move together.
WORLD = {
    'HoveringName', 'HudCombatFeedback', 'HudCombatFeedbackHitCounter',
    'ContextTarget', 'PromptText', 'AllyArrow1', 'AllyArrow2',
}

# Text that spills outward from its anchor.  Moving one of these the full edge
# distance pushes the far end of the string past the screen edge, and scaling it
# clips the string inside its own box.  They get a reduced shift and no scaling,
# and are then clamped into the authored title-safe area.
# Text that spills outward from its anchor.  On the LEFT these are centred on
# their anchor, so moving one the full edge distance pushes half the string off
# screen - they get --text-fraction of the move and no scaling.  On the RIGHT
# they are right-aligned and the authored layout already respects the title-safe
# margin, so translating them the full distance is exactly correct.
# AllyName1/2 are deliberately NOT here: they are labels belonging to the party
# frames and have to move and scale with the cluster or they drift off it.
TEXT = {
    'StateText', 'DurabilityAlert', 'LootLog', 'QuestItemLootLog',
    'CombatLogCollection', 'QuestStatusBarCollection', 'belleram', 'MessageText',
    'Popups',
}

# Text is clipped at the authored page, [0, 1280], on BOTH sides - bitmaps are
# not, which is why the notification's backing strip reaches the screen edge
# while the words inside it stop dead at x = 1280.  Right-aligned text can be
# taken up to the page edge less a safe margin, because its anchor is the END
# of the string.  Popups is the exception: it is CENTRE-aligned and word-wraps,
# so its box sticks out both ways.  Measured off "New Quest: The Last Sons of
# Cardolan", the wrapped line is about 325 units wide, so the anchor cannot go
# past roughly 1280 - 162 without the tail being cut.  Wrapping is what makes
# that bound safe for any quest name: the box width is fixed, so a longer title
# gets another line rather than a longer line.
PAGE_RIGHT = 1280.0
CENTRED_TEXT = {'Popups': 1100.0}

# Centred elements that are not an ultrawide problem at all - the canvas centre
# is still 640 - but which sit awkwardly on a very wide screen because there is
# so much more of it.  Vertical position only; x is left alone.
#   Region         the big "The Barrow-downs" location title
#   BanterSubtitle the party's conversation subtitles
VERTICAL = {'Region': 'region_y', 'BanterSubtitle': 'subtitle_y'}

# res/gui/hud says so itself: "HD Safe Left Edge" x=64, "HD Safe Right Edge"
# x=1216 against a 1280 canvas.  Nothing readable should sit outside that.
SAFE = 64.0
RIGHT = {
    'SkillBacker', 'SkillBackerPC', 'DpadUI',
    'Ammo', 'AmmoPC', 'ShowTotalAmmo', 'HideTotalAmmo',
    'QuestStatusBarCollection', 'HudCombatFeedback',
    'HudCombatFeedbackHitCounter', 'CombatLogCollection',
    'Popups', 'RangedMode',
}


# ---------------------------------------------------------------------------
# SPLIT SCREEN  (hud_hd_split.s2.sdf, two players / hud_hd_tri.s2.sdf, three)
#
# These files are LEFT ALONE, and 1.6's attempt to edge-restore them is
# reverted.  Measured off real two-controller split screen (which works on
# the Legacy PC build - two pads, second pad presses start): each split
# viewport gets its own canvas from its OWN aspect ratio, and a vertical-split
# viewport is half the screen wide - 1720x1440 at 3440x1440, aspect 1.19 -
# which is NARROWER than 16:9.  The patched canvas maths is an exact no-op at
# or below 16:9, so the split page reaches both viewport edges and there is no
# inset to restore.  The 1.6.0 shift, built on a mis-read of two-instance
# online-co-op screenshots, pushed the party frames and ally names off the
# left viewport edge (bars visible, frame artwork gone).  Stock is correct.
#
# Open question, deliberately untouched: 3-player tri on an ultrawide (its
# quadrant viewports share the full screen's aspect).  Revisit with a real
# tri screenshot if that is ever played.
SPLIT_HUDS = [
    os.path.join('res', 'gui', 'hud', '_bin', 'pc64', 'hud_hd_split.s2.sdf'),
    os.path.join('res', 'gui', 'hud', '_bin', 'pc64', 'hud_hd_tri.s2.sdf'),
]


# ---------------------------------------------------------------------------
# FRONT END  (--frontend, off by default - see the warning on the flag)
#
# TESTED AND PARTLY BROKEN.  Moving the menu furniture out to the screen edges
# works for the mode/difficulty/chapter block (authored x 70 -> -150, drawn at
# 5% of the screen) and for the player list, but the bottom-left button column
# vanishes entirely once it crosses x = 0.  The right-hand column of the same
# block moved by the identical -220 and is fine at x = 70/80, so the engine is
# dropping flagged elements that leave the authored 1280x720 page rather than
# clipping them.  Until that boundary is pinned down the front end is left
# alone by default.
#
# The menus are drawn through the same canvas as the HUD, so with `fit` they
# are pillarboxed too: at 3440x1440 every menu element stops 440px short of the
# screen edge.  The dark scrims behind them are part of the background scene
# rather than the 2D layer, so those DO reach the real screen edge, and the gap
# between the two is what makes the character select screen read as stretched.
#
# Verified against the shipped coordinates: the three race symbols are authored
# at x = 86 / 470 / 791 and land at 17.8% / 40.1% / 58.8% of the screen, and the
# two button columns are authored at 85 and 300 and land at 17.7% and 30.2% -
# which is the `fit` mapping exactly, not a stretch.
#
# Only named, verified elements are moved.  Everything that labels a 3D
# character (the race symbols, the name plates, the mouse regions that pick a
# hero) is deliberately left alone: those have to stay with the models.
FE_LEFT = {
    # the mode / difficulty / chapter block, top left.  All three move together
    # even though only the first has an absolute coordinate - a translation is a
    # translation whatever the origin, so the block stays aligned.
    'LobbyMode', 'LobbySubMode', 'LobbyDifficulty',
    # the lobby chat
    'ChatLog', 'ChatTxtEntry',
    # the bottom-left button column, shared by every front-end screen
    'BackButtonTop', 'BackButtonBottom', 'Con_PC_BackButtonText', 'PC_BackButtonText',
    'AButtonTop', 'AButtonBottom', 'Con_PC_AButtonText', 'PC_AButtonText',
    'YButtonTop', 'YButtonBottom', 'Con_PC_YButtonText', 'PC_YButtonText',
    'XButtonTop', 'XButtonBottom', 'Con_PC_XButtonText', 'PC_XButtonText',
    'BButtonTop', 'BButtonBottom', 'Con_PC_BButtonText', 'PC_BButtonText',
}
FE_RIGHT = {'PlayerList'}
# the hover / show / hide animation states keep their own copy of a button
# position.  Same trap as the ammo counter in the HUD: miss them and the button
# jumps back to the middle the moment the mouse touches it.  They are matched by
# the button column's x values, which nothing else in the file uses.
FE_KEYFRAME = {'OnHoverOn', 'OnHoverOff', 'ShowLobbyButtons', 'HideLobbyButtons'}
FE_BUTTON_X = {75.0, 85.0, 290.0, 300.0}


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
    def __init__(self, path, tab):
        self.h = bytearray(open(path, 'rb').read())
        # header: +0x10 holds the start of the data section.  The record list
        # begins 0x10 past it, string offsets are relative to +8 past it, and
        # the flat 4-byte value pool starts at ds + the dword stored at ds+8.
        ds = struct.unpack_from('<I', self.h, 0x10)[0]
        self.BASE, self.STR = ds + 0x10, ds + 8
        self.POOL = ds + struct.unpack_from('<I', self.h, ds + 8)[0]
        if not (0 < self.BASE < self.POOL <= len(self.h)):
            raise SystemExit(f"{path} does not parse as a GUI layout file")
        self.tab = tab
        self.recs = []
        o = self.BASE
        # walk the whole record area.  Not every name CRC is in the shared
        # table - unknown ones are labelled and skipped over rather than
        # ending the walk, which used to truncate the file at the first one
        # and leave the entire second half unparsed.
        while o + 16 <= self.POOL:
            f0, cr, t, v = struct.unpack_from('<4I', self.h, o)
            self.recs.append((o, f0, tab.get(cr, '?%08x' % cr), t, v))
            o += 16
        if len(self.recs) < 200:
            raise SystemExit(f"{path} does not parse as expected - wrong version?")

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


_IO_HELP = (
    "\n"
    "Windows error codes that mean the drive itself is not answering:\n"
    "  0xc000000e / 0x800701B1  'a device which does not exist was specified'\n"
    "  Errno 22 'Invalid argument' while reading a file nothing else is using\n"
    "\n"
    "If you are seeing those, the problem is the disk, not the patch.  Reboot\n"
    "first - that alone clears a drive that has dropped off the bus.  If the\n"
    "folder is still unreadable afterwards, run  chkdsk X: /f  on that drive\n"
    "(X: being the drive the game is on) before touching the game again.")


def _read_whole(path, what):
    """Read a file completely, or fail before anything has been destroyed."""
    try:
        with open(path, 'rb') as f:
            blob = f.read()
    except OSError as e:
        raise SystemExit(f"could not read {path}\n({what}): {e}{_IO_HELP}")
    if not blob:
        raise SystemExit(f"{path}\n({what}) is zero bytes, so there is nothing to "
                         f"copy from.{_IO_HELP}")
    return blob


def _write_atomic(path, blob, what):
    """Write via a temp file and rename it into place.

    shutil.copyfile opens the destination for writing - truncating it - before
    it has read a single byte of the source.  If the read then fails, the
    destination is left at zero bytes and whatever was there is gone.  Writing
    a temp file and renaming means the target is either the old contents or the
    new ones, never nothing.  The read-back check afterwards catches a drive
    that accepted the write and did not store it.
    """
    tmp = path + '.tmp'
    try:
        with open(tmp, 'wb') as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise SystemExit(f"could not write {path}\n({what}): {e}{_IO_HELP}")
    if _read_whole(tmp, 'the file just written') != blob:
        os.remove(tmp)
        raise SystemExit(f"{path}\n({what}) did not read back as what was just "
                         f"written - the drive is not storing data reliably.\n"
                         f"Nothing was changed.{_IO_HELP}")
    os.replace(tmp, path)


def _is_key_run(d, p):
    """an ASCII string-table key starts here: 6+ bytes of [A-Za-z0-9_] then \\0"""
    n = 0
    while p + n < len(d) and (chr(d[p + n]).isalnum() or d[p + n] == 0x5F):
        n += 1
    return n >= 6 and p + n < len(d) and d[p + n] == 0


def blank_widescreen_label(root, revert=False):
    """Empty every language's ' (Widescreen)' suffix in gui_tables.s2.sdf."""
    done = 0
    for rel in GUI_TABLES:
        f = os.path.join(root, rel)
        if not os.path.isfile(f):
            continue
        bak = f + '.original'
        if revert:
            if os.path.isfile(bak):
                _write_atomic(f, _read_whole(bak, 'the backup'), 'restoring')
                print(f"restored {f}")
            continue
        if not os.path.exists(bak):
            _write_atomic(bak, _read_whole(f, 'the string table'), 'saving the backup')
        d = bytearray(_read_whole(bak, 'the string table'))
        key = d.find(b'\0widescreen\0')
        if key < 0:
            print(f"  labels     : 'widescreen' key not found in {os.path.basename(rel)} - left alone")
            continue
        p = key + len(b'\0widescreen\0')
        p = (p + 3) & ~3
        n = 0
        while p + 1 < len(d) and not _is_key_run(d, p):
            if d[p] == 0 and d[p + 1] == 0:      # an empty language slot / padding
                p += 4
                continue
            e = p
            while e + 1 < len(d) and not (d[e] == 0 and d[e + 1] == 0):
                e += 2
            for q in range(p, e, 2):              # every code unit -> U+0020: reads as
                d[q], d[q + 1] = 0x20, 0x00       # nothing whether the engine stops at
                                                   # the terminator or uses a stored length
            n += 1
            p = (e + 2 + 3) & ~3
        _write_atomic(f, bytes(d), 'writing the string table')
        done += 1
        print(f"  labels     : {os.path.basename(rel)}: blanked the '(Widescreen)' suffix in "
              f"{n} languages - the mode list shows the bare resolution")
    return done


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def guard_foreign(target, bak, stamp):
    """Refuse to rebuild from a stale backup if another mod replaced the file.

    Every run rebuilds from the .original, which silently undoes any other mod
    that has edited the same file since.  Compare what is on disk against what
    we last wrote and stop if they disagree.
    """
    if not os.path.isfile(bak):
        return                              # first run: nothing to protect
    current = _sha(target)
    if current == _sha(bak):
        return                              # untouched, or freshly reverted
    if not os.path.isfile(stamp):
        return                              # predates stamping - cannot tell
    if current == open(stamp).read().strip():
        return                              # exactly what we wrote last time
    raise SystemExit(
        f"{target}\nhas been changed by something other than this script - another "
        f"mod has\nedited it since the last run.\n"
        f"\n"
        f"Rebuilding from {os.path.basename(bak)} would silently undo that mod, so this\n"
        f"is a refusal rather than a guess.  Pick one:\n"
        f"\n"
        f"  keep the other mod and put this layout on top of it:\n"
        f"      python witn_hud_shift.py --rebase <your usual options>\n"
        f"  the .original then holds the other mod, and --revert goes back to it.\n"
        f"\n"
        f"  or drop the other mod and start clean:\n"
        f"      python witn_hud_shift.py --revert\n"
        f"  then run this again.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--res', default='3440x1440')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--revert', action='store_true')
    ap.add_argument('--icon-scale', type=float, default=0.85,
                    help='size of the HUD artwork, 1.0 = stock (default 0.85). This '
                         'only scales the elements themselves - where they sit is '
                         'never scaled, so the spacing stays exactly as authored and '
                         'shrinking can only open the gaps up, never close them.')
    ap.add_argument('--cluster-scale', type=float, default=1.0,
                    help='extra size factor on the bottom-left party frames only')
    ap.add_argument('--corner-nudge', default='0,28',
                    help='dx,dy in layout units moving the bottom-right group (skill '
                         'bar, ammo, d-pad, ranged toggle) further into the corner. '
                         'Positive dy = further down the screen')
    ap.add_argument('--text-fraction', type=float, default=0.6,
                    help='how far LEFT-side text follows the edge, 0..1 (default 0.6). '
                         'Lower this if the loot log or state text still runs off. '
                         'Right-side text always moves the full distance - it is '
                         'right-aligned, so translating it is exact')
    ap.add_argument('--region-y', type=float, default=80.0,
                    help='height of the big location title, in 720-space '
                         '(stock 227, lower number = closer to the top)')
    ap.add_argument('--region-scale', type=float, default=0.75,
                    help='size of the big location title, 1.0 = stock (default 0.75). '
                         'It is not actually drawn any larger at 21:9 than at 16:9, '
                         'but it is the only thing in the middle of a very wide screen, '
                         'so it reads as oversized')
    ap.add_argument('--subtitle-y', type=float, default=620.0,
                    help='height of the conversation subtitles, in 720-space '
                         '(stock 542, higher number = closer to the bottom)')
    ap.add_argument('--no-vertical', action='store_true',
                    help='leave the location title and subtitles where they are')
    ap.add_argument('--frontend', action='store_true',
                    help='EXPERIMENTAL and off by default: also push the front-end '
                         'menu furniture out to the screen edges.  Known broken - '
                         'the engine drops the bottom-left button column once it is '
                         'moved past the left edge of the authored 1280-wide page, '
                         'so "Select / Options / Select Game" disappear.  The '
                         'mode/difficulty block and the player list do move '
                         'correctly.  Left in so the boundary can be found.')
    ap.add_argument('--fill', action='store_true',
                    help='companion to witn_patch.py --hud fill.  In fill mode the '
                         '2D layer already spans the whole screen, so the HUD is '
                         'exactly where it sits at 16:9 and must NOT be edge-restored '
                         '- this switches the edge shift off and leaves the artwork at '
                         'stock size, while still applying the location-title and '
                         'subtitle moves.')
    ap.add_argument('--bar-scale', type=float, default=1.0,
                    help='EXPERIMENTAL, 1.0 = off.  Scales the health/mana/XP bars '
                         'INSIDE the party-frame collections, which is the only way '
                         'to make the bottom-left group genuinely smaller (a '
                         'CollectionRefElement does not scale what it references).  '
                         'Known to come out misaligned - the bars are ModelElements '
                         'and their backing plates are BitmapElements and the two do '
                         'not share an anchor.')
    ap.add_argument('--keep-labels', action='store_true',
                    help="leave the ' (Widescreen)' suffix on the video-options "
                         "mode list (1.8 blanks it by default)")
    ap.add_argument('--loading', choices=['fill', 'stretch', 'off'], default='fill',
                    help="loading screens on an ultrawide: 'fill' (default) scales "
                         "each level's painting uniformly to the full canvas and crops "
                         "a strip top and bottom; 'stretch' widens it on X only; 'off' "
                         "leaves the 16:9 pages alone.  (1.8: the pages that actually "
                         "draw are res\\worlds\\<level>\\..\\load_NN.s2.sdf, one per "
                         "level - the four under res\\gui\\load were the wrong target.)")
    ap.add_argument('--no-frontend-scale', action='store_true',
                    help='in --fill mode, leave the menus stretched instead of '
                         'un-stretching them.  Only Scale.X is ever changed there, '
                         'never a position.')
    ap.add_argument('--force', action='store_true',
                    help='run even at 16:9 or narrower, where there is no edge to '
                         'restore and only the scaling has any effect')
    ap.add_argument('--rebase', action='store_true',
                    help='adopt the CURRENT hud file as the new baseline before '
                         'editing - use after installing another mod that edits '
                         'the same file')
    ap.add_argument('--scale-text', action='store_true',
                    help='also scale text elements (off by default - scaling them '
                         'clips the string inside its own box)')
    a = ap.parse_args()

    hud = os.path.join(a.root, HUD)
    bak = hud + '.original'
    stamp = hud + '.wpatch'
    if not os.path.isfile(hud):
        raise SystemExit(f"{hud} not found - run from the game folder")

    if a.revert:
        if not os.path.isfile(bak):
            raise SystemExit(f"{bak} missing - use Steam's Verify integrity instead")
        _write_atomic(hud, _read_whole(bak, 'the backup'), 'restoring')
        if os.path.isfile(stamp):
            os.remove(stamp)
        print(f"restored {hud}")
        for rel in [FE] + LOAD + SPLIT_HUDS:
            f = os.path.join(a.root, rel)
            if os.path.isfile(f + '.original'):
                _write_atomic(f, _read_whole(f + '.original', 'the backup'),
                              'restoring')
                print(f"restored {f}")
        blank_widescreen_label(a.root, revert=True)
        for rel in _load_pages(a.root):
            f = os.path.join(a.root, rel)
            if os.path.isfile(f + '.original'):
                _write_atomic(f, _read_whole(f + '.original', 'the backup'), 'restoring')
                if os.path.isfile(f + '.wpatch'):
                    os.remove(f + '.wpatch')
                print(f"restored {f}")
        return

    w, h = (int(x) for x in a.res.lower().split('x'))
    aspect = w / h
    shift = (720.0 * max(aspect, 16 / 9) - 1280.0) / 2.0
    if a.fill:
        # the fill canvas is 1280 wide, so the authored page already reaches both
        # screen edges: there is no inset to restore and moving anything would
        # push it off.  Artwork stays stock size too - fill reproduces the 16:9
        # layout, it does not enlarge it vertically.
        shift = 0.0
        if a.corner_nudge == '0,28':
            a.corner_nudge = '0,0'
    elif shift < 1.0 and not a.force:
        raise SystemExit(
            f"{a.res} is {aspect:.3f}:1, which is 16:9 or narrower - the HUD already\n"
            f"sits where it should and there is nothing to move.  This tool is only for\n"
            f"ultrawide.  Pass --force if you want the {a.icon_scale:g} icon scaling anyway.")
    # In fill mode the canvas is 1280x720 whatever the screen is, so the
    # horizontal pixel scale is screenW/1280 while the vertical one is
    # screenH/720 - the 2D layer reaches both screen edges (which is the point)
    # but every element comes out aspect/(16:9) too wide.  Multiplying each
    # top-level element's Scale.X by the inverse cancels that exactly, without
    # touching a single position: artwork and text end up the shape they are at
    # 16:9 while still sitting where the full-width canvas puts them.
    xcomp = 1280.0 / (720.0 * aspect) if a.fill else 1.0
    if a.fill:
        print(f"{a.res}: fill canvas 1280x720 - no edge shift; horizontal "
              f"un-stretch {xcomp:.4f} on X, artwork at {a.icon_scale:g}")
    else:
        print(f"{a.res}: canvas {720*max(aspect,16/9):.0f}x720, edge shift {shift:.1f} "
              f"layout units ({shift * w / (720*max(aspect,16/9)):.0f}px)")

    tab = load_crc(os.path.join(a.root, CRC))
    if a.rebase:
        _write_atomic(bak, _read_whole(hud, 'the hud file'),
                      'saving the new baseline')
        if os.path.isfile(stamp):
            os.remove(stamp)
        print(f"rebased: {bak} now holds the current (modded) file")
    else:
        guard_foreign(hud, bak, stamp)
    if not os.path.exists(bak):
        _write_atomic(bak, _read_whole(hud, 'the hud file'), 'saving the backup')
        print(f"backup written: {bak}")
    d = Sdf(bak, tab)          # always start from the pristine copy

    if a.list:
        for nm, slot, x, y in d.elements():
            if abs(x - 640) > 150 or abs(y - 360) > 150:
                print(f"  {nm[:36]:<36} x={x:<9.1f} y={y:<8.1f} slot={slot}")
        return

    dx, dy = (float(t) for t in a.corner_nudge.split(','))
    left_edge, right_edge = -shift, 1280.0 + shift

    moved = scaled = nudged = clamped = skipped = nested = 0
    vmoved = []
    for name, props in d.nodes():
        if name in WORLD:
            skipped += 1
            continue
        if name not in LEFT and name not in RIGHT:
            continue
        is_text = name in TEXT
        # Only ever move an absolute canvas position.  The same node name can
        # appear again nested inside a parent, where Position is a small
        # relative offset - shifting one of those drags the child away from
        # its parent, and scaling it shrinks artwork that is already being
        # scaled by the parent.  An absolute position lies inside the authored
        # 1280x720 page; a relative offset generally does not.  If a node has
        # no absolute position at all it is a nested copy: leave it entirely.
        abs_pos = [ps for ps in props['Position']
                   if 0.0 <= d.pos(ps)[0] <= 1280.0 and 0.0 <= d.pos(ps)[1] <= 720.0]
        if not abs_pos:
            nested += 1
            continue
        frac = a.text_fraction if (is_text and name in LEFT) else 1.0
        s_here = shift * frac
        for ps in abs_pos:
            x, y, _z = d.pos(ps)
            # 1. translate to put the element back at its 16:9 distance from the
            # screen edge.  Positions are only ever translated, never scaled
            # toward a corner: scaling them pulls neighbouring clusters into
            # each other, which is what made the party frames overlap.
            if name in LEFT and x < 640:
                x -= s_here; moved += 1
            elif name in RIGHT and x > 640:
                x += s_here; moved += 1
            # 2. drop the bottom-right corner group a little further down
            if name in CORNER:
                x += dx; y += dy; nudged += 1
            # 3. keep anything readable inside the authored title-safe area.
            # Only meaningful when something was actually moved: with no edge
            # shift the authored layout is already correct and clamping would
            # drag stock positions around for nothing.
            if is_text and shift > 0.0:
                # The engine CLIPS text at the authored page edge (x = 0), even
                # though it happily draws bitmaps outside it - the party frames
                # sit at x = -95 and are fine.  So a left-side text anchor is
                # never pushed more than one safe margin past that edge, or the
                # first characters get cut: "Farin: Inventory" was arriving as
                # "arin: Inventory" with the F sliced in half.
                lo = max(left_edge + SAFE, -SAFE)
                hi = min(right_edge - SAFE, PAGE_RIGHT - SAFE)
                if name in CENTRED_TEXT:
                    hi = CENTRED_TEXT[name]
                if x < lo:
                    x = lo; clamped += 1
                elif x > hi:
                    x = hi; clamped += 1
            d.setx(ps, x); d.sety(ps, y)
        # 4. shrink the artwork itself.  Scale propagates to child elements, so
        # this makes the cluster smaller without touching where anything sits -
        # spacing stays exactly as authored, so shrinking can only ever open the
        # gaps up, never close them.
        g = a.icon_scale * (a.cluster_scale if name in CLUSTER else 1.0)
        if abs(g - 1.0) > 1e-6 and not (is_text and not a.scale_text):
            for ss in props['Scale']:
                # X and Y only.  Z is depth for these elements and several are
                # authored with z=1 against x=y=0.66; scaling it too would move
                # them in the draw order for no visual benefit.
                for k in range(2):
                    off = d.POOL + (ss + k) * 4
                    v = struct.unpack_from('<f', d.h, off)[0]
                    struct.pack_into('<f', d.h, off, v * g)
                scaled += 1
    # the insides of the party-frame collections - see BARS.  Off by default:
    # scaling these was tried and came out misaligned, because the bars are
    # ModelElements and the plates behind them are BitmapElements, and the two
    # do not appear to share an anchor - so scaling their relative offsets by
    # the same factor moves them by different visual amounts.
    g = a.bar_scale
    bars = barpos = 0
    if abs(g - 1.0) > 1e-6:
        for name, props in d.nodes():
            if name not in BARS:
                continue
            for ps in props['Position']:
                x, y, _z = d.pos(ps)
                d.setx(ps, x * g)
                d.sety(ps, y * g)
                barpos += 1
            for ss in props['Scale']:
                for k in range(2):
                    off = d.POOL + (ss + k) * 4
                    v = struct.unpack_from('<f', d.h, off)[0]
                    struct.pack_into('<f', d.h, off, v * g)
            bars += 1
        print(f"  party bars : {bars} elements inside the frame collections scaled "
              f"to {g:g} with their {barpos} relative offsets (a CollectionRef does "
              f"not scale what it references, so these were never being touched)")

    if not a.no_vertical:
        for name, props in d.nodes():
            key = VERTICAL.get(name)
            if not key:
                continue
            target = getattr(a, key)
            for ps in props['Position']:
                x, y, _z = d.pos(ps)
                if 0.0 <= x <= 1280.0 and 0.0 <= y <= 720.0:
                    d.sety(ps, target)
            # the location title is also the only thing sitting alone in the
            # middle of the screen, so it gets its own size control.  Scale
            # propagates to the text inside it, and its position is centred,
            # so shrinking it cannot move it off anything.
            if name == 'Region' and abs(a.region_scale - 1.0) > 1e-6:
                for ss in props['Scale']:
                    for k in range(2):
                        off = d.POOL + (ss + k) * 4
                        v = struct.unpack_from('<f', d.h, off)[0]
                        struct.pack_into('<f', d.h, off, v * a.region_scale)
            vmoved.append(f"{name} y ->{target:g}"
                          + (f" scale {a.region_scale:g}" if name == 'Region' else ""))
    if vmoved:
        print("  repositioned vertically: " + ", ".join(vmoved))
    print(f"  left world-anchored elements alone: {sorted(WORLD)}")
    print(f"  {'left in place' if shift <= 0 else 'edge-restored'} {moved} positions, "
          f"scaled {scaled} nodes "
          f"(icons {a.icon_scale:g}, party frames {a.icon_scale*a.cluster_scale:g})")
    print(f"  corner-nudged {nudged}, text at {a.text_fraction:g} of the edge shift, "
          f"{clamped} clamped into the title-safe area,\n"
          f"  {skipped} world-anchored and {nested} nested copies left alone")
    if xcomp != 1.0:
        n = unstretch(d, xcomp, LEFT | RIGHT | CORNER | TEXT | WORLD
                      | set(VERTICAL) | CLUSTER)
        print(f"  un-stretched {n} top-level Scale records on X (children skipped - "
              f"scale already propagates to them from their parent)")
    _write_atomic(hud, bytes(d.h), 'writing the hud file')
    open(stamp, 'w').write(_sha(hud) + '\n')

    # Split-screen layouts are never edited (see the SPLIT SCREEN note above).
    # If a 1.6.0 run shifted them, quietly put them back to their baseline.
    for rel in SPLIT_HUDS:
        f = os.path.join(a.root, rel)
        bak = f + '.original'
        if os.path.isfile(f) and os.path.isfile(bak) and _sha(f) != _sha(bak):
            _write_atomic(f, _read_whole(bak, 'the split baseline'),
                          'restoring ' + os.path.basename(rel))
            open(f + '.wpatch', 'w').write(_sha(f) + '\n')
            print(f"  {os.path.basename(rel)}: restored to stock (split viewports "
                  f"are 16:9 or narrower - no edge restore applies)")

    if not a.keep_labels:
        blank_widescreen_label(a.root)
    if a.loading != 'off' and shift > 0.0:
        fill_loadscreens(a, tab, 720.0 * max(aspect, 16 / 9) / 1280.0, a.loading)
    if a.frontend:
        shift_frontend(a, tab, shift)
    elif xcomp != 1.0 and not a.no_frontend_scale:
        unstretch_frontend(a, tab, xcomp)
    print("done - fully quit the game before relaunching")


def unstretch(d, xcomp, names=None):
    """Multiply Scale.X by xcomp so the fill canvas stops drawing things wide.

    `names` limits it to a known-top-level set.  That limit matters: scale
    propagates down the tree, so compensating a parent already compensates its
    children, and doing both applies it twice.  The first attempt guessed top
    level from "has a Position inside the authored 1280x720 page" and wrongly
    caught HpBar / ManaBar / ExpBar - those are children of the party frames
    but their offsets happen to land inside the page.  They came out at 0.7442
    squared, which is why the player's health and mana bars stopped matching
    their frames.

    The container format's child counts turned out not to be trustworthy enough
    to walk the tree properly, so for the HUD this is driven by the same element
    list the edge restore uses - every name in it was verified top-level when
    that was built.  Positions are never touched, so nothing can move or fall
    off.

    Animation states that carry their own copy of a Scale (the ammo counter's
    show/hide, the menu hover states) are separate named nodes and are covered
    the same way, so nothing springs back to full width mid-animation."""
    n = 0
    for name, props in d.nodes():
        if names is not None and name not in names:
            continue
        if not any(0.0 <= d.pos(ps)[0] <= 1280.0 and 0.0 <= d.pos(ps)[1] <= 720.0
                   for ps in props['Position']):
            continue
        if not props['Scale']:
            continue
        for ss in props['Scale']:
            off = d.POOL + ss * 4
            v = struct.unpack_from('<f', d.h, off)[0]
            struct.pack_into('<f', d.h, off, v * xcomp)
        n += 1
    return n


LOAD_KEEP = {'LoadScreenTip', 'TipBar', 'LoadingText', 'Titles', 'title_logos',
             'MainTitle', 'load_title', 'LocalizedImageMainLogo', 'Master Scene',
             'Center', 'Exit', 'Main'}


def _load_pages(root):
    """every loading page: one per level under res/worlds, plus the four
    generic ones under res/gui/load"""
    out = []
    wroot = os.path.join(root, 'res', 'worlds')
    for dp, _dn, fn in os.walk(wroot):
        if os.path.basename(dp) != 'pc64':
            continue
        for f in sorted(fn):
            if f.startswith('load_') and f.endswith('.s2.sdf'):
                out.append(os.path.relpath(os.path.join(dp, f), root))
    out += [rel for rel in LOAD if os.path.isfile(os.path.join(root, rel))]
    return out


def fill_loadscreens(a, tab, k, mode):
    """Make the loading screens span the whole canvas.

    Each level carries its own page (res\\worlds\\<level>\\_bin\\pc64\\load_NN.s2.sdf:
    the parallax painting as Layer0..N bitmaps, the fades and letterbox bars,
    the rain/fire/magic sprites, the tip text and its bar, and the logo).
    Everything is authored to the 1280x720 page, so on the fit canvas the
    painting stops at the page edge and the 3D world shows either side.

    mode 'fill'    every picture element is scaled UNIFORMLY by k about the
                   page centre: the painting keeps its proportions, spans the
                   canvas, and loses a strip top and bottom (17% each at 21:9)
                   the way every other game crops its art on an ultrawide.
    mode 'stretch' x only: nothing is cropped, the painting is k times wider
                   than drawn.
    The tip line, its bar, the spinner and the logo collection are left where
    they are - they are not part of the picture.  Animation keyframes carry
    their own copy of every position and scale and are transformed with the
    element they belong to, so the parallax drift cannot snap the picture back
    to page size part way through."""
    total = files = 0
    cx, cy = 640.0, 360.0
    for rel in _load_pages(a.root):
        p = os.path.join(a.root, rel)
        bak = p + '.original'
        if not os.path.exists(bak):
            _write_atomic(bak, _read_whole(p, 'a loading page'), 'saving the backup')
        d = Sdf(bak, tab)
        n = 0
        cur = None
        for _o, _f0, nm, t, v in d.recs:
            if t == 4 and nm in ('Name', 'ElementName'):
                try:
                    cur = d.s(v)
                except Exception:
                    cur = None
                continue
            if cur is None or cur in LOAD_KEEP or t != 64:
                continue
            if nm == 'Position':
                x, y, _z = d.pos(v)
                if -1.0 <= x <= 1.0 and -1.0 <= y <= 1.0 and (x, y) != (0.0, 0.0):
                    continue                     # a fractional (anchor-mode) position
                d.setx(v, cx + (x - cx) * k)
                if mode == 'fill':
                    d.sety(v, cy + (y - cy) * k)
                n += 1
            elif nm == 'Scale':
                off = d.POOL + v * 4
                sx, sy, sz = struct.unpack_from('<3f', d.h, off)
                struct.pack_into('<3f', d.h, off, sx * k, sy * (k if mode == 'fill' else 1.0), sz)
        _write_atomic(p, bytes(d.h), 'writing a loading page')
        open(p + '.wpatch', 'w').write(_sha(p) + '\n')
        total += n
        files += 1
    print(f"  loading    : {files} loading pages {'scaled uniformly x%.4f, art cropped top/bottom' % k if mode == 'fill' else 'stretched x%.4f on X' % k}"
          f" ({total} positions moved); tip line, spinner and logo untouched")


def unstretch_frontend(a, tab, xcomp):
    """The same horizontal un-stretch over the menu layout.

    Positions are deliberately not touched here - that is what made the button
    column disappear last time.  Only Scale.X changes, so nothing can move out
    of the page and nothing can be dropped."""
    fe = os.path.join(a.root, FE)
    bak = fe + '.original'
    if not os.path.isfile(fe):
        print(f"  frontend   : {FE} not found, skipped")
        return
    if not os.path.exists(bak):
        _write_atomic(bak, _read_whole(fe, 'a layout file'), 'saving the backup')
    d = Sdf(bak, tab)
    n = unstretch(d, xcomp)
    _write_atomic(fe, bytes(d.h), 'writing a layout file')
    print(f"  frontend   : un-stretched {n} menu elements on X "
          f"({os.path.basename(FE)}, positions untouched)")


def shift_frontend(a, tab, shift):
    """Push the front-end menu furniture back out to the screen edges.

    Same idea as the HUD, and deliberately much more conservative: only named
    elements that were checked against the shipped coordinates are moved, and
    nothing that labels or picks a 3D character is touched."""
    fe = os.path.join(a.root, FE)
    bak = fe + '.original'
    if not os.path.isfile(fe):
        print(f"  frontend   : {FE} not found, skipped")
        return
    if not os.path.exists(bak):
        _write_atomic(bak, _read_whole(fe, 'a layout file'), 'saving the backup')
    d = Sdf(bak, tab)
    moved = 0
    for name, props in d.nodes():
        if name in FE_LEFT or name in FE_RIGHT:
            sgn = -1.0 if name in FE_LEFT else 1.0
            for ps in props['Position']:
                x, y, _z = d.pos(ps)
                if (sgn < 0 and x >= 640.0) or (sgn > 0 and x <= 640.0):
                    continue          # a copy of the name on the wrong side
                d.setx(ps, x + sgn * shift); moved += 1
        elif name in FE_KEYFRAME:
            for ps in props['Position']:
                x, y, _z = d.pos(ps)
                if x in FE_BUTTON_X:
                    d.setx(ps, x - shift); moved += 1
    _write_atomic(fe, bytes(d.h), 'writing a layout file')
    print(f"  frontend   : edge-restored {moved} menu positions in {os.path.basename(FE)} "
          f"(character symbols, name plates and hero mouse regions left alone)")


if __name__ == '__main__':
    main()
