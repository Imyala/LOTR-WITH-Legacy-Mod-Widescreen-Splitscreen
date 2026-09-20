============================================================
 War in the North - Widescreen Mod
 Author:  Imyala
 Version: 1.8.1
 Guide:   https://steamcommunity.com/sharedfiles/filedetails/?id=3786147705
 Licensed under MIT. Copyright (c) 2026 Imyala.
 Keep this header intact in forks and redistributions.
============================================================

War in the North: Legacy Edition - Ultrawide + HUD          v1.5
================================================================
For The Lord of the Rings: War in the North - Legacy Edition (Steam 2523770).

The Legacy release will not offer any resolution wider than 16:9, and forcing
one stretches the 2D layer about 34% too large, so the HUD runs off the top
and bottom of the screen - and the camera crops vertically instead of opening
up, so the view ends up tighter than it is at 16:9.  This fixes all three,
repositions the HUD for a wide screen, and adds a save key while it is in
there.

Tested at 2560x1080, 3440x1440, 3840x1600 and 5120x1440.


WHAT IT CHANGES
---------------
1  Resolution unlock.  The mode list is filtered against four hard-coded
   aspect ratios (16:9, 16:10, 4:3, 5:4) to within 0.0001, which is why
   3440x1440 (2.38889) was thrown away.

   Two edits, and one build now covers every ultrawide rather than one ratio:

   * the tolerance is widened from 0.0001 to 0.05.  That constant is the
     engine's generic float epsilon and is referenced 528 times, so it is not
     edited - only this one load is pointed at a 0.05 already sitting in the
     executable.
   * the two entries an ultrawide monitor never reports anything for are
     retargeted to one value per FAMILY:

         5:4 -> 2.36667 +- 0.05   2560x1080, 3440x1440, 3840x1600, 2520x1080,
                                  3840x1620, 5120x2160
         4:3 -> 3.55556 +- 0.05   5120x1440, 3840x1080, 7680x2160

   16:9 (1.7778) and 16:10 (1.6) are 0.178 apart and 4:3 was 0.267 from 16:10,
   so the wider window cannot make anything collide, and both come out exactly
   as before.  4:3 modes are the price; --keep-43 puts them back and drops
   32:9 instead.

   IMPORTANT: this only decides which modes the game is willing to LIST.  The
   list itself comes from your graphics driver, so a resolution still has to be
   one your monitor actually reports.  3840x1600 will not appear on a
   3440x1440 panel no matter what is patched.

2  GUI canvas.  The 2D layer is authored at 1280x720 and drawn through a
   canvas of (1280, 1280/aspect).  Above 16:9 that canvas is too short, and
   because it is stretched to the whole screen everything is drawn at
   screenW/1280 instead of screenH/720.  The maths is rewritten height-locked:

       canvasW = f * 720 * max(aspect, 16/9)
       canvasH = canvasW / aspect

   max() only engages above 16:9, so 16:9, 16:10 and 4:3 come out bit for bit
   identical to stock.  There are two copies of this in the executable because
   the engine inlines it a second time in the GUI projection setup; patching
   only the first has no visible effect at all, which costs you an afternoon
   if you miss it.

3  Field of view.  This is the one that is easy to miss.  The engine builds
   its perspective matrix from a HORIZONTAL field of view - 90 degrees by
   default - and the aspect ratio:

       m00 = 1 / tan(fovH/2)          m11 = aspect / tan(fovH/2)

   The horizontal angle is the authored one, so it stays put and the VERTICAL
   angle is whatever falls out of the aspect ratio.  Widen the screen and you
   do not gain anything at the sides, you lose the top and bottom: 58.7
   degrees vertical at 16:9, 45.4 at 21:9.  That is "Vert-", and it is why an
   ultrawide picture reads as zoomed in - the camera has not moved, the frame
   has just been cropped and then blown up to fill the screen.

   The fix scales tan(fovH/2) by max(1, aspect / (16/9)) on its way out of the
   engine's own tangent routine.  That drops m11 onto exactly the value it has
   at 16:9 and opens m00 up instead, so the vertical framing is restored to
   stock and the extra width becomes extra view.  At 3440x1440 the horizontal
   field goes 90 -> 106.7 degrees with the vertical held at 58.7.  This is
   "Hor+", what every modern game does.

   max() means it is an exact no-op at 16:9 and below, so the square shadow
   and reflection cameras that share the same routine are left alone, and so
   is anyone playing at a normal aspect ratio.

   --fov-scale nudges it either way afterwards if you want a wider or tighter
   camera than stock; 1.0 is stock framing.  (1.7: the scale is applied before
   the 16:9 floor, so it also works at plain 16:9 and can never reach the
   square shadow/reflection cameras.)

   SPLIT SCREEN (1.7).  Each half of a two-player split is half as wide, so
   the authored 90-degree horizontal view read as zoomed in next to the
   fullscreen camera.  In split the tangent term is doubled - "treat the pair
   of viewports as one screen" - so each half gets the SAME horizontal field
   of view as fullscreen single player: 106.7 degrees at 3440x1440, 126.9 on a
   2x1080p Surround pair (the 32:9 single-player figure).  Vertically that is
   the console split screen's ~97 degrees.  Keyed on the same local-player
   test as the canvas; --no-split-fov turns it off.

4  Save keys.  The game has no save button - it only saves when a level script
   fires a checkpoint.

       F5   saves out in the levels
       F6   saves in the hub towns (Bree, Rivendell, Nordinbad, Sarn Ford)

   The two are complementary rather than redundant.  The engine deliberately
   uses different routes in towns and in levels: the checkpoint save bails out
   in the six hub worlds, and the town save only arms inside them.  Press
   whichever suits where you are standing, or just press both.

   F5 and F6 both arm the engine's own save (the same call its netcode makes
   on a checkpoint): the save is written a second or two later, once you are
   somewhere quiet - not mid-combat, not in a menu.  Stand still, press the
   key, wait a moment.  (An interim 1.6 build wired F5 to the wrong routine and
   crashed; the release build does not.)

   Saves are timestamped, so neither key can ever overwrite an existing save.
   Nothing happens if you press them in a menu.

5  HUD layout.  The edge-anchored HUD clusters are pushed back out to the
   screen edges so nothing sits stranded in the middle, and the artwork is
   scaled to 85%.

   SPLIT SCREEN (1.7).  Local two-controller split screen works on the Legacy
   PC build - plug in two pads, second pad presses Start at the hero-select
   lobby.  The 2D canvas is now split-screen aware: it reads the live local-
   player count and, when it is exactly 2, gives each split viewport its own
   full page so the HUD sits complete at that viewport's own edges - the way
   the console split screen draws it.  On a dual-monitor setup presented as one
   display (e.g. NVIDIA Surround 3840x1080, or 2x 1440p), each viewport is a
   clean 16:9 half, so it comes out pixel-perfect with no stretch and the HUD
   in the true corners.  Single player, online co-op and 3-player split all
   read a count that is NOT 2, so they take the ordinary path and are
   byte-for-byte unchanged.  Nothing in the split HUD layout files is edited;
   this is one runtime branch in the executable.  --no-split-canvas keeps the
   old static behaviour if you ever want it.

   Position and size are handled as separate operations, and that separation
   is the whole trick.  Positions are only ever TRANSLATED, never scaled
   toward a corner, so the spacing between elements stays exactly as the game
   authored it - verified offset by offset against the unmodified file.  Only
   the artwork is scaled.  So making the HUD smaller opens the gaps up and can
   never close them.

   Three things it is careful about, all of which look fine at 16:9 and break
   at 21:9:

   * Elements positioned at runtime from a world position - the name floating
     over another player, floating combat numbers, the [E] use prompt - are
     never moved.  Their authored coordinate is only a template origin, so
     shifting it drags the label off the thing it labels, by an amount that
     changes with the camera angle.
   * Left-side text is moved only part of the way to the edge and is never
     scaled, then clamped inside the game's own title-safe box (the HUD data
     defines "HD Safe Left Edge" at x=64).  Moved the full distance it is
     centred on its anchor, so the far end of each string runs off screen and
     you lose the first word or two of the loot log and the combat feedback.
     Right-side text is right-aligned, so it is translated the whole way,
     which is exact.
   * The ammo counter's show/hide animation states carry their own copy of
     the position and are moved identically, so the counter does not jump
     whenever it fades in.

   It also lifts the big location title out of the middle of the screen
   (y 227 to 80, at 75% size) and drops the conversation subtitles closer to
   the bottom (y 542 to 620).  Neither is an ultrawide bug - the canvas centre
   is still 640 - but both sit awkwardly when the screen is this wide.

6  A note on the menus, because the obvious fix does not work.

   The 2D layer is one canvas shared by the HUD and every menu, and there are
   only two things it can do at 21:9:

     fit (default, what this ships with)
       Correct proportions everywhere.  The 1280x720 page is centred, so menus
       stop about 440px short of each screen edge at 3440x1440.  The in-game
       HUD is pushed back out to the edges by witn_hud_shift.py, so only the
       menus sit inset.

     fill (--hud fill)
       The page spans the whole screen, so menus reach both edges - but the
       horizontal pixel scale becomes screenW/1280 against a vertical
       screenH/720, and everything is drawn 34% wider than tall.

   Two attempts were made to get both, and both are documented here so nobody
   repeats them:

   * Moving the menu elements out to the edges under `fit`.  The engine DROPS
     flagged elements that leave the authored 1280x720 page instead of
     clipping them - the bottom-left button column disappeared entirely while
     the right-hand column of the same block, moved by the identical amount but
     landing at x=70, was fine.
   * Cancelling the stretch under `fill` by multiplying each element's Scale.X
     by 1280/(720*aspect).  The maths is right, but scale propagates down the
     tree and the container format's child counts are not consistent enough to
     tell a parent from a child reliably, so nested bars were compensated
     twice.  Even with that fixed the result was worse than `fit`.

   So `fit` is the shipped default and the menus stay pillarboxed.  --hud fill
   and witn_hud_shift.py --fill are still there if you want to try it.

7  Loading screens.  Still pillarboxed, and I could not fix them.

   Their layout is built from full-page backdrop layers anchored just off the
   top-left of the page (Layer0/2/3 at x = -5, scale 1.01), so stretching those
   across the canvas looks like it should work - and it changes nothing at all.
   Tried twice, verified the edited file was the one on disk and that load.s2.sdf
   is the only layout in the game defining those elements.  So whatever draws
   the picture is not those layers.

   The lead worth chasing next is ViewportOffset, which sits in the Settings
   block of every one of these layouts.  A hard 16:9 viewport would explain both
   the bars and why they are pure black rather than smeared edge pixels.

   witn_hud_shift.py --loading still does the layer stretch for anyone who wants
   to pick it up.  It is off by default because it does nothing.


REQUIREMENTS
------------
Python 3, any recent version, from python.org/downloads
On the first page of the installer, tick "Add python.exe to PATH".


INSTALL
-------
1  Copy every file from this package into your game folder, the one that
   contains witn.exe:

       ...\steamapps\common\LORWIN

2  Double-click install.bat and answer the resolution question.

Or from a command prompt in that folder:

       python witn_patch.py --res 3440x1440
       python witn_hud_shift.py --res 3440x1440

witn_patch.py only needs --res to pick which family goes in the primary slot;
one run covers every resolution in that family.  witn_hud_shift.py is baked for
one aspect ratio and has to be re-run if you change screens.


UNINSTALL
---------
       python witn_patch.py --revert
       python witn_hud_shift.py --revert

Both keep a .original of anything they touch and restore from it.  Steam's
"Verify integrity of game files" also puts everything back.


FIELD OF VIEW KEYS (1.8)
------------------------
       Numpad -   zoom out (wider view)      Numpad +   zoom in
       Numpad *   back to the default (--fov-scale)
Hold a key and the camera glides; the range is 0.5x to 2.0x of the Hor+
default.  1.8 also fixes the floor that stopped a scale under 1.0 from having
any effect: zooming IN now works at every aspect ratio, and the shadow /
reflection cameras stay untouched as before.  The value is not written
anywhere yet, so a fresh launch starts at --fov-scale again (pass
--fov-scale 0.9 to make a zoom-in the default).  A slider in the video
options would need a new engine setting wired into settings.s2.sdf and the
option-page script, which is a much bigger job than a key - it is not in 1.8.


RESOLUTION LABELS (1.8)
-----------------------
The video-options mode list no longer says "(Widescreen)" after every wide
mode - just the resolution.  The text is a string-table entry (key
'widescreen' in res\gamedata\platform\files\pc\_bin\pc64\gui_tables.s2.sdf, one
string per language); witn_hud_shift.py blanks all of them, keeps a
.original, and puts them back on --revert.  --keep-labels leaves them.


LOADING SCREENS (1.8.1)
-----------------------
Full width now, and nothing else is touched.  The pages that actually draw
are NOT the four under res\gui\load (which is why the old --loading
experiment changed nothing): every level carries its own page,
res\worlds\<level>\...\_bin\pc64\load_NN.s2.sdf - the painting as parallax
layers (Layer0..4 bitmaps), the fades and letterbox bars, the rain / fire /
magic sprites, the tip line and its bar, and the logo.  33 of them, plus the
4 generic ones.  witn_hud_shift.py now scales every picture element on those
pages uniformly about the page centre (x1.3438 at 21:9) - painting keeps its
proportions, spans the canvas, and loses a strip top and bottom (17% each at
21:9) exactly as other games crop art on an ultrawide.  The animation
keyframes (the slow parallax drift) are transformed with their elements so
the picture cannot snap back part way through.  The tip line, its bar, the
spinner and the logo stay where they were; the HUD and the menus are not
involved at all - these are separate files.
    --loading fill      the default, described above
    --loading stretch   widen on X only, nothing cropped, picture 34% wider
    --loading off       leave the 16:9 pages alone
Every page gets a .original beside it and --revert puts them all back.


AFTER A GAME UPDATE
-------------------
Steam replaces witn.exe when the game updates (Patch 1 landed on 15 Sep 2026),
so the exe half of this mod is gone until you run install.bat again.  Nothing
else is needed: every address the patcher writes is found by byte signature in
whatever executable is there, and it refuses rather than guesses if a pattern
is missing or not unique.  The GUI layout files it edits are not part of the
update, so witn_hud_shift.py finds them as it left them.

The patcher notices the new build on its own.  witn.exe.original from before
the update is a copy of the OLD game, so it is kept aside as
witn.exe.original.build-<stamp> and a fresh backup of the new stock exe is
taken; --revert refuses to restore a backup from a different build (it would
downgrade the game - use Steam's verify for that).  Confirmed on the launch
build and on Patch 1 (v1.000.003): all nine patch sites live in functions
that are instruction-for-instruction identical between the two.


USING THIS WITH OTHER MODS
--------------------------

Both scripts always rebuild from their .original backup rather than editing
whatever is currently on disk.  That is what makes re-running them safe and
makes --revert exact, but on its own it would also mean quietly undoing any
other mod that has touched the same file since.  So they check first.

If another mod has replaced witn.exe (or edited the HUD file) since the last
run, the script stops and tells you, instead of overwriting it.  You then pick:

       python witn_patch.py --rebase --res 3440x1440
       python witn_hud_shift.py --rebase --res 3440x1440

--rebase adopts what is currently on disk as the new baseline and layers these
patches on top of it.  The other mod stays, .original then holds the other
mod's version, and --revert later returns you to it rather than to stock.

Install order is what decides how much you have to think about this:

  * install the other mod FIRST, then this one - nothing special needed, and
    --revert still gives the other mod back cleanly.
  * install this one first and the other mod second - the other mod's installer
    will overwrite our work, so re-run install.bat afterwards and it will stop
    and point you at --rebase.

Mods that only add or replace files under res\ without touching witn.exe or
hud_hd.s2.sdf do not interact with this at all - install them in any order.

My own packages are a special case.  The Ultrawide package already contains
the save keys from the Save Keys package, so Ultrawide is a superset and you
want one or the other, never both.  Running the Save Keys installer over an
Ultrawide install is refused rather than allowed to silently strip the
widescreen fix.  Going the other way - Save Keys first, Ultrawide later - is
just an upgrade and is never blocked.

The .wpatch file each script leaves next to the file it edited is how it knows
what it last wrote.  Deleting it is harmless; it only weakens the check.


GUI TEXT CLIP  (why the level numbers and potion counts were missing)
---------------------------------------------------------------------
Bitmaps and models draw anywhere on the canvas.  Text does not.  Right before
it hands a string to the font renderer, the GUI text path sets a clip rectangle
to the AUTHORED PAGE and nothing wider:

    0x1402E74D3   movss xmm1,[1280.0]        -> r8d
    0x1402E7508   movss xmm2,[720.0]         -> r9d
    0x1402E75BB   mov   edx,r14d
    0x1402E75BE   xor   ecx,ecx
    0x1402E75C0   call  SetClipRect(0, 0, 1280, 720)
    0x1402E75C8   ...   and then the string is drawn

SetClipRect (0x14008F8F0) does nothing but store those four ints per viewport
at +0xBC.  That one rectangle is the whole reason a HUD readout disappears once
its cluster is moved out to the screen edge: at 21:9 the canvas is wider than
the page, so anything past x=0 or x=1280 falls outside it.  It is also why the
level BADGE still draws while the number inside it does not - the badge is a
bitmap and never goes through this path.

The call is retargeted at a 25-byte shim in the appended section:

    cmp   r8d,1280          ; only the page rectangle, nothing else
    jne   pass
    mov   ecx,-4096         ; left
    mov   r8d,8192          ; right
  pass:
    jmp   SetClipRect

Horizontal bounds only, and only when it recognises the page rectangle, so any
per-element clip box the same routine sets - a list clipped to its own frame,
say - is passed straight through.  Vertical bounds are never changed.  The shim
never touches rsp, so it is a leaf and needs no unwind entry.

At 16:9 nothing sits outside the page in the first place, so this is a no-op
there.  --no-text-clip leaves the rectangle as shipped.

Brings back: the three party level numbers, both potion counts, the two ally
names and the two ally status lines - all of which sit outside the page once
the HUD is edge-restored, and none of which were being drawn.


OPTIONS
-------
       python witn_hud_shift.py --icon-scale 0.75      smaller HUD artwork
       python witn_hud_shift.py --cluster-scale 0.9    party frames only
       python witn_hud_shift.py --corner-nudge 0,40    skill bar further down
       python witn_hud_shift.py --text-fraction 0.4    pull left-side text in
       python witn_hud_shift.py --region-y 150         location title height
       python witn_hud_shift.py --region-scale 0.6     location title size
       python witn_hud_shift.py --subtitle-y 640       subtitle height
       python witn_hud_shift.py --no-vertical          leave those two alone
       python witn_hud_shift.py --list                 every element, no edit

       python witn_patch.py --no-split-fov             keep the stock 90-degree
                                                       camera in split halves
       python witn_patch.py --no-split-canvas          keep the canvas static
                                                       (no per-viewport fill in
                                                       two-player split screen)
       python witn_patch.py --no-text-clip             leave the text clip
                                                      rectangle as shipped

       python witn_patch.py --fov-scale 1.1            wider camera than stock
       python witn_patch.py --fov-scale 0.95           tighter camera
       python witn_patch.py --no-fov                   leave the camera alone
       python witn_patch.py --keep-43                  keep 4:3, drop 32:9
       python witn_patch.py --save-key 0x77            F8 instead of F5
       python witn_patch.py --client-save-key 0        drop the second key
       python witn_patch.py --no-savekey               ultrawide only
       python witn_patch.py --save-only                save keys only, no
                                                       ultrawide changes

Virtual-key codes: F1 0x70 through F12 0x7B, Insert 0x2D, Home 0x24,
Page Up 0x21, NumPad 0 0x60.

Three switches exist but are off by default because they were tried and did not
work.  They are documented in sections 6 and 7 and left in only so the work is
not lost: --frontend and --fill in witn_hud_shift.py, and --loading.  There is
no reason to use them.

NOTES
-----
* Fully quit the game before relaunching - it caches settings on exit.
* Both scripts always rebuild from the .original backup, so re-running them
  is safe and repeatable, and options can be changed as many times as you
  like without uninstalling first.
* witn_hud_shift.py refuses to run at 16:9 or narrower, where there is no
  edge to restore and it would only shrink your HUD for nothing.  --force
  overrides that if it is what you actually want.
* If a Steam update replaces witn.exe, run  python witn_patch.py --rebase
  once to adopt the new build as the baseline, then patch normally.
* If you install another mod that replaces witn.exe, use --rebase the same
  way, and do not re-run witn_hud_shift.py until you have checked whether
  that mod also replaced hud_hd.s2.sdf.


CHANGES
-------
1.8.1  Loading screens fill the ultrawide screen (uniform scale, cropped top
     and bottom; --loading stretch / off).  The per-level pages under
     res\worlds are the ones that draw; the four under res\gui\load never were.

1.8  FOV zoom keys (Numpad - / + / *), 0.5x..2.0x, zoom-in now works below
     the Hor+ floor.  "(Widescreen)" dropped from the resolution list
     (gui_tables.s2.sdf, all languages, --keep-labels to keep).

1.7.2  Game-update aware.  Steam's Patch 1 (15 Sep 2026) replaced witn.exe;
     the patcher already found every site by signature in the new build, but
     it would have rebuilt from the stale witn.exe.original of the OLD game.
     It now identifies the game build (PE link stamp + .text size), parks a
     backup that belongs to a different build as witn.exe.original.build-<stamp>,
     takes a fresh one, and --revert refuses to downgrade the game.  Verified
     on both builds; no change to what is patched.

1.7.1  FIX: 1.7's split-screen test also fired in SINGLE PLAYER (HUD pushed
     to the far screen edges, camera pulled back - the fill canvas and split
     FOV on solo play).  The address 1.7 read is the engine's handle table,
     SHARED by several registries, so "slot 1 occupied" is true even solo.
     The patch now does what the engine itself does: the per-frame hook calls
     the engine's own local-player counter (the exact function behind the
     IsSplitscreen script command), caches the count, and the canvas / FOV
     branches take the split path only when it is exactly 2.  Single player
     and online co-op read 1 and take the stock path; the fit maths is still
     instruction-for-instruction identical to 1.5.

1.7  Split screen fills each viewport.  Local two-controller split screen works
     on the Legacy PC build; the 2D canvas is now split-screen aware and gives
     each viewport its own full page when exactly two local players are active,
     so on a dual-monitor / Surround setup each half fills its screen with the
     HUD in the corners and no stretch.  Everything else (single player, online
     co-op, 3-player) reads a different count and is byte-for-byte unchanged.
     One runtime branch in the exe; no HUD layout file is touched.
     New --no-split-canvas.  (1.7's split test read a fixed slot of an engine
     table that turned out to be shared - see 1.7.1 below for the fix.)

     SPLIT FOV.  Each split half now gets the fullscreen camera's horizontal
     field of view instead of the authored 90 degrees, so split no longer
     reads as zoomed in.  --fov-scale is applied before the 16:9 floor (works
     at 16:9 now; shadow cameras untouched).  New --no-split-fov.

     Also: reverted 1.6.0's edit of the split HUD *layout* files (that shift was
     based on a mis-read screenshot and pushed the party frames off the
     viewport edge); the split layouts are stock again and the chat listener is
     no longer installed into them, so a controller button can't open the chat
     box in couch co-op.

1.6  Split screen, and the save key actually saves.

     * SPLIT SCREEN.  Local two-controller split screen works on the Legacy
       PC build (plug in two pads, second pad presses start).  Its HUD layouts
       are left stock, and the chat mod no longer installs its listener into
       them: split viewports are 16:9 or narrower, so the ultrawide edge
       restore does not apply there - an interim build shifted them anyway and
       pushed the party frames off screen; the tool now restores stock if it
       finds that edit.

     * SAVE KEY FIX.  F5 was wired to SaveCheckpoint(0), which only re-captures
       the respawn point in memory - it never writes a file, so the key looked
       dead.  Both F5 and F6 now arm the engine's own CheckpointMgr::RequestSave
       (the exact call the netcode makes on a checkpoint), which needs only the
       manager pointer and writes the save through the same path as every
       autosave, a moment later once you are somewhere quiet.  An interim build
       tried a script-command routine needing a context argument and crashed
       when handed none; the release does not.

1.5.1  The GUI text clip.  Text is clipped to the authored 1280x720 page right
     before it is drawn, which is why the three party level numbers, both potion
     counts, the ally names and the ally status lines were missing once the HUD
     was moved out to the screen edges - bitmaps are not clipped, so the level
     badge kept drawing while the number inside it did not.  The clip call is
     retargeted at a shim that widens the horizontal bounds, and only when it
     recognises the page rectangle, so per-element clip boxes are untouched.
     No HUD element moves; nothing else changes.  New --no-text-clip.

1.5  Field of view, one build for every ultrawide, and a pile of HUD corrections.

     * FIELD OF VIEW.  The camera was Vert-: a wider screen cropped the top and
       bottom instead of showing more at the sides, which is why ultrawide read
       as zoomed in compared to 16:9.  It is Hor+ now - vertical framing matches
       16:9 exactly at every resolution (58.72 degrees) and the extra width is
       extra view.  Exact no-op at 16:9 and below.  New --fov-scale, --no-fov.

     * ONE BUILD FOR EVERY ULTRAWIDE.  2560x1080, 3440x1440, 3840x1600 and
       5120x1440 all pass the mode filter without rebuilding.  The filter's
       tolerance is widened from 0.0001 to 0.05 and the two spare aspect entries
       now hold one value per family rather than one exact ratio.  New
       --keep-43 if you would rather have 4:3 modes than 32:9.

     * NOTIFICATION BANNER.  "New Quest: ..." was hanging at 74% of the screen
       while the quest tracker beside it sat at 86%.  It is a separate element
       called Popups, authored right next to the tracker, and it had been
       wrongly classed as world-anchored.  Moved.

     * TEXT NO LONGER CLIPS.  The engine clips text at the authored 1280x720
       page on BOTH edges - bitmaps are not clipped, which is why a
       notification's backing strip reaches the screen edge while the words
       inside stop dead.  Left-side text is now never pushed more than one safe
       margin past x=0 ("Farin: Inventory" was arriving as "arin: Inventory"),
       and right-side text is capped inside x=1280.  The combat log came back
       from 1436 to 1216 for the same reason.

     * LOCATION TITLE out of the middle of the screen (y 227 -> 80) and down to
       75% size; subtitles closer to the bottom (y 542 -> 620).  New
       --region-scale.

     Two things were tried and did not work, and are written up in sections 6
     and 7 so nobody repeats them: pushing the MENU furniture out to the screen
     edges (the engine deletes flagged elements that leave the authored page),
     and making the loading screens full width (the layer stretch does nothing).

1.4  Position and size are separate operations now.  The HUD is 85% size with
     stock spacing, so shrinking it opens the gaps instead of closing them.
     --hud-scale is replaced by --icon-scale, which does what its name says.
     The bottom-right group - skill bar, ammo, d-pad and ranged toggle - moves
     into the corner together; the d-pad and ranged toggle used to be left
     behind.  Only X and Y of a scale are touched, since several elements are
     authored with z=1 against x=y=0.66 and scaling z moved them in the draw
     order for nothing.

1.3  Fixed the bottom-left party frames overlapping each other.

1.2  Quest tracker and combat log sit at their proper distance from the right
     edge instead of hanging toward the middle.  Location title moved up out
     of the centre of the screen, subtitles moved down.  Ally name labels move
     with the frames they label instead of drifting off them.

1.1  Nameplates, floating combat numbers and the use prompt stay attached to
     what they belong to at every camera angle.  Loot log, quest tracker,
     combat feedback and the durability warning no longer have their first
     characters cut off at the screen edge.  Ammo counter no longer jumps when
     its show/hide animation plays.  Added F6.  The HUD parser was stopping at
     the first unrecognised name and silently reading only half the layout
     file; it now walks all of it, and skips nested copies of an element
     instead of shifting them a second time.

1.0  First release.


This is a patcher, not a modified game.  It edits your own installed copy in
place, which is why no game file is included here.

