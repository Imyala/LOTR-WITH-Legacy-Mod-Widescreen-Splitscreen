War in the North: Legacy Edition - Ultrawide + HUD
===================================================
For The Lord of the Rings: War in the North - Legacy Edition (Steam 2523770).

The Legacy release will not offer any resolution wider than 16:9, and forcing
one stretches the 2D layer ~34% too large so the HUD runs off the top and
bottom of the screen.  This fixes both, and adds a quicksave key while it is
in there.

WHAT IT CHANGES
  1  Resolution unlock.  The mode list is filtered against four hard-coded
     aspect ratios (16:9, 16:10, 4:3, 5:4) to within 0.0001, which is why
     3440x1440 (2.38889) was thrown away.  The unused 5:4 entry is retargeted
     to your ratio - four bytes.
  2  GUI canvas, two sites.  The 2D layer is authored at 1280x720 and drawn
     through a canvas of (1280, 1280/aspect).  Above 16:9 that canvas is too
     short, and because it is stretched to the whole screen everything is
     drawn at screenW/1280 instead of screenH/720.  Both copies of the maths
     are rewritten height-locked:
         canvasW = f * 720 * max(aspect, 16/9)
         canvasH = canvasW / aspect
     max() only engages above 16:9, so 16:9, 16:10 and 4:3 come out bit for
     bit identical to stock.  There are two copies because the engine inlines
     it a second time in the GUI projection setup; patching only the first has
     no visible effect at all, which costs you an afternoon if you miss it.
  4  Quicksave key - see the co-op package's README, or just press F5.

  witn_hud_shift.py then pushes the edge-anchored HUD clusters back out to the
  screen edges and scales them to 85%, so nothing looks cramped in the middle.

REQUIREMENTS
  Python 3 (any recent version) - https://www.python.org/downloads/
  On the installer page tick "Add python.exe to PATH".

INSTALL
  1  Copy every file in this folder into your game folder, the one containing
     witn.exe:
         ...\steamapps\common\LORWIN
  2  Double-click install.bat and answer the resolution question.

  Or from a command prompt in that folder:
     python witn_patch.py --res 3440x1440
     python witn_hud_shift.py --res 3440x1440

UNINSTALL
     python witn_patch.py --revert
     python witn_hud_shift.py --revert

  Both keep a .original of anything they touch and restore from it.  Steam's
  "Verify integrity of game files" also puts everything back.

NOTES
  * Fully quit the game before relaunching - it caches settings on exit.
  * Both scripts always rebuild from the .original backup, so re-running them
    is safe and repeatable.
  * If a Steam update replaces witn.exe, run  python witn_patch.py --rebase
    once to adopt the new build as the baseline, then patch normally.
  * If you install another mod that replaces witn.exe, use --rebase the same
    way, and do not re-run witn_hud_shift.py until you have checked whether
    that mod also replaced hud_hd.s2.sdf.
  * HUD size and position are adjustable:
        python witn_hud_shift.py --hud-scale 0.9 --corner-nudge 40,40
        python witn_hud_shift.py --list      (prints every element, no edit)

This is a patcher, not a modified game.  It edits your own installed copy in
place, which is why no game file is included here.
