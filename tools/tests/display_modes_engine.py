# Headless check of the display modes: the lines of a "(Lines)" display are not drawn in Material Preview and
# Rendered, and are back when the view returns to a solid display.
#   BLENDER_USER_CONFIG=<scratch> Blender -b --factory-startup --python tools/tests/display_modes_engine.py
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from blenda4d import bars, display_modes  # noqa: E402

FAIL = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what, flush=True)
    if not ok:
        FAIL.append(what)


sp = next(a.spaces.active for s in bpy.data.screens for a in s.areas if a.type == "VIEW_3D")
for key in "BDF":
    name = display_modes.NAMES[key]
    for mode in ("MATERIAL", "RENDERED"):
        display_modes.set_shading(sp, key)
        check(sp.overlay.show_wireframes, f"{name} draws its lines")
        bars.set_shading(sp, mode)
        check(sp.shading.type == mode and not sp.overlay.show_wireframes, f"{name} -> {mode}: no lines")
        bars.set_shading(sp, "SOLID")                    # as the way back from a render view does: only the type
        check(display_modes.shading_of(sp) == key, f"{mode} -> back: {name} again, with its lines")
display_modes.set_shading(sp, "B")
bars.set_shading(sp, "MATERIAL")
bars.set_shading(sp, "RENDERED")
bars.set_shading(sp, "SOLID")
check(display_modes.shading_of(sp) == "B", "through both and back: the lines are there again")
bars.set_shading(sp, "MATERIAL")
display_modes.set_shading(sp, "A")
check(display_modes.shading_of(sp) == "A", "a plain display picked from Material Preview stays plain")
display_modes.set_shading(sp, "A")
bars.set_shading(sp, "RENDERED")
bars.set_shading(sp, "SOLID")
check(display_modes.shading_of(sp) == "A", "a plain display comes back plain")
display_modes.set_shading(sp, "B")
bars.set_shading(sp, "MATERIAL")
display_modes.set_shading(sp, "G")
display_modes.set_shading(sp, "A")
check(display_modes.shading_of(sp) == "A", "Lines picked from Material Preview, then a plain display: no lines left over")
print("B4D DISPLAY", "FAIL" if FAIL else "ok", len(FAIL), "failed", flush=True)
