# SPDX-License-Identifier: GPL-3.0-or-later
"""C4D's display menu (N, then a letter) and the display icons in the viewport header.

Shading: A Gouraud, B Gouraud (Lines), C Quick, D Quick (Lines), E Constant, F Hidden Line, G Lines.
Line style: H Wireframe (every edge), I Isoparms (a subdivided object shows only its cage), K Box.
Toggles: P Backface Culling, Q Materials, R X-Ray. S shows or hides the sidebar, which N opens in Blender."""
import bpy

MENU = "BLENDA4D_MT_display"
ISO_KEY = "b4d_isoparms"
BOX_KEY = "_b4d_display_was"

SHADING = (("A", "Gouraud Shading", "SHADING_SOLID"), ("B", "Gouraud Shading (Lines)", "MESH_UVSPHERE"),
           ("C", "Quick Shading", "MATSPHERE"), ("D", "Quick Shading (Lines)", "MESH_ICOSPHERE"),
           ("E", "Constant Shading", "MATPLANE"), ("F", "Hidden Line", "MESH_CUBE"), ("G", "Lines", "SHADING_WIRE"))
STYLE = (("H", "Wireframe", "MOD_WIREFRAME"), ("I", "Isoparms", "MOD_SUBSURF"), ("K", "Box", "SHADING_BBOX"))
TOGGLES = (("P", "Backface Culling", "NORMALS_FACE"), ("Q", "Materials", "MATERIAL"), ("R", "X-Ray", "XRAY"))
NAMES = {k: n for k, n, _i in SHADING + STYLE + TOGGLES}
TIPS = {"A": "smooth shading under the viewport light",
        "B": "smooth shading with the edges drawn on top",
        "C": "simple shading, no shadows or highlights",
        "D": "simple shading with the edges drawn on top",
        "E": "flat colour, no light or shadow",
        "F": "flat surfaces with only their visible edges drawn",
        "G": "edges only, including the ones behind",
        "H": "the lines show every edge",
        "I": "a subdivided object shows only its cage",
        "K": "objects are drawn as boxes",
        "P": "hide the back side of polygons",
        "Q": "show the materials' colours",
        "R": "see through surfaces",
        "S": "show or hide the sidebar"}

_colors = {}                                             # a view's own colour setting, kept while it shows Hidden Line
_lines = set()                                           # views whose lines are put away (keep_lines)


def _space(context):
    sp = context.space_data
    if sp is not None and sp.type == "VIEW_3D":
        return sp
    area = next((a for a in context.screen.areas if a.type == "VIEW_3D"), None) if context.screen else None
    return area.spaces.active if area else None


def shading_of(sp):
    sh, ov = sp.shading, sp.overlay
    if sh.type == "WIREFRAME":
        return "G"
    if sh.type != "SOLID":
        return None
    lines = ov.show_overlays and ov.show_wireframes
    if sh.light == "FLAT":
        return "F" if lines and sh.color_type == "SINGLE" and sp.as_pointer() in _colors else "E"
    quick = not sh.show_specular_highlight
    return ("D" if lines else "C") if quick else ("B" if lines else "A")


def style_of(scene):
    if any(BOX_KEY in ob for ob in scene.objects):
        return "K"
    return "I" if scene.get(ISO_KEY) else "H"


def works(sp, key):
    """Blender has X-Ray in Solid and Wireframe only, and Backface Culling in Solid only."""
    t = sp.shading.type
    return t == "SOLID" if key == "P" else t in ("SOLID", "WIREFRAME") if key == "R" else True


def is_on(sp, key):
    sh = sp.shading
    if key == "P":
        return sh.show_backface_culling
    if key == "Q":
        return sh.color_type in ("MATERIAL", "TEXTURE")
    if key == "R":
        return sh.show_xray_wireframe if sh.type == "WIREFRAME" else sh.show_xray
    return False


def _keep_color(sp, keep):
    sh, ptr = sp.shading, sp.as_pointer()
    if keep and ptr not in _colors:
        _colors[ptr] = (sh.color_type, tuple(sh.single_color))
        sh.color_type = "SINGLE"
        sh.single_color = (0.8, 0.8, 0.8)
    elif not keep and ptr in _colors:
        sh.color_type, sh.single_color = _colors.pop(ptr)


def keep_lines(sp, mode):
    """The lines of a "(Lines)" display belong to that display: they are put away while the view shows Material
    Preview or Rendered, and are back when it shows a solid display again."""
    ov, ptr = sp.overlay, sp.as_pointer()
    if mode in ("MATERIAL", "RENDERED"):
        if ov.show_wireframes:
            _lines.add(ptr)
            ov.show_wireframes = False
    elif ptr in _lines:
        _lines.discard(ptr)
        ov.show_wireframes = mode == "SOLID"


def _set_type(sp, mode):
    """Through bars.set_shading: Octane's own copy of each view's mode is put right first (a quad view crashed)."""
    if sp.shading.type != mode:
        from . import bars
        bars.set_shading(sp, mode)


def set_shading(sp, key):
    sh, ov = sp.shading, sp.overlay
    if key == "G":
        _keep_color(sp, False)
        _set_type(sp, "WIREFRAME")
        sh.show_xray_wireframe = True
        return
    _set_type(sp, "SOLID")
    _keep_color(sp, key == "F")
    sh.light = "FLAT" if key in ("E", "F") else "STUDIO"
    if key in "ABCD":
        quick = key in "CD"
        sh.show_specular_highlight = not quick
        if quick:
            sh.show_shadows = sh.show_cavity = False
    ov.show_wireframes = key in "BDF"
    if key in "BDF":
        ov.show_overlays = True
        ov.wireframe_threshold = 1.0


def set_style(scene, key):
    for ob in scene.objects:
        if key == "K" and ob.type == "MESH" and ob.display_type in ("TEXTURED", "SOLID") and BOX_KEY not in ob:
            ob[BOX_KEY] = ob.display_type
            ob.display_type = "BOUNDS"
        elif key != "K" and BOX_KEY in ob:
            ob.display_type = ob[BOX_KEY]
            del ob[BOX_KEY]
    if bool(scene.get(ISO_KEY)) != (key == "I"):
        scene[ISO_KEY] = key == "I"
        from . import generators
        generators.sync_modifiers(scene)


def toggle(sp, key):
    sh = sp.shading
    if key == "P":
        sh.show_backface_culling = not sh.show_backface_culling
    elif key == "Q":
        _keep_color(sp, False)
        sh.color_type = "OBJECT" if sh.color_type in ("MATERIAL", "TEXTURE") else "MATERIAL"
    elif key == "R":
        if sh.type == "WIREFRAME":
            sh.show_xray_wireframe = not sh.show_xray_wireframe
        else:
            sh.show_xray = not sh.show_xray


class BLENDA4D_OT_display(bpy.types.Operator):
    bl_idname = "blenda4d.display"
    bl_label = "Display"
    bl_description = "How the viewport draws the scene, as in C4D's Display menu"
    mode: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        key = properties.mode
        if key == "S":
            return "Sidebar: " + TIPS[key]
        return f"{NAMES[key]}: {TIPS[key]}" if key in NAMES else cls.bl_description

    def execute(self, context):
        key = self.mode
        if key == "S":
            sp = _space(context)
            if sp:
                sp.show_region_ui = not sp.show_region_ui
            return {"FINISHED"}
        if key in "HIK":
            set_style(context.scene, key)
            return {"FINISHED"}
        sp = _space(context)
        if sp is None:
            return {"CANCELLED"}
        if key in "PQR":
            if not works(sp, key):
                where = "the shaded displays" if key == "P" else "the shaded and line displays"
                self.report({"INFO"}, f"{NAMES[key]} works in {where} only, not in Material Preview or Rendered")
                return {"CANCELLED"}
            toggle(sp, key)
        elif key in NAMES:
            set_shading(sp, key)
        return {"FINISHED"}


class BLENDA4D_MT_display(bpy.types.Menu):
    bl_idname = MENU
    bl_label = "Display"

    def draw(self, context):
        layout = self.layout
        sp = _space(context)
        now = shading_of(sp) if sp else None
        style = style_of(context.scene)

        def item(key, name, on):
            col = layout.column()
            col.active = not sp or works(sp, key)
            col.operator("blenda4d.display", text=f"{key}   {name}", icon="CHECKMARK" if on else "BLANK1").mode = key

        for key, name, _icon in SHADING:
            item(key, name, key == now)
        layout.separator()
        for key, name, _icon in STYLE:
            item(key, name, key == style)
        layout.separator()
        for key, name, _icon in TOGGLES:
            item(key, name, bool(sp) and is_on(sp, key))
        layout.separator()
        item("S", "Sidebar", bool(sp) and sp.show_region_ui)


def draw_strip(layout, context):
    """The viewport header's display icons: C4D's shading modes, Blender's Material Preview and Rendered, the toggles,
    and the whole Display menu."""
    sp = context.space_data
    now = shading_of(sp)
    row = layout.row(align=True)
    for key in "ABEFG":
        _k, name, icon = next(s for s in SHADING if s[0] == key)
        row.operator("blenda4d.display", text="", icon=icon, depress=(now == key)).mode = key
    row = layout.row(align=True)
    for mode, icon in (("MATERIAL", "SHADING_TEXTURE"), ("RENDERED", "SHADING_RENDERED")):
        row.operator("blenda4d.shading", text="", icon=icon, depress=(sp.shading.type == mode)).mode = mode
    row = layout.row(align=True)
    for key in "PR":
        _k, name, icon = next(t for t in TOGGLES if t[0] == key)
        sub = row.row(align=True)
        sub.active = works(sp, key)
        sub.operator("blenda4d.display", text="", icon=icon, depress=is_on(sp, key) and works(sp, key)).mode = key
    layout.menu(MENU, text="", icon="DOWNARROW_HLT")


CLASSES = (BLENDA4D_OT_display, BLENDA4D_MT_display)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
