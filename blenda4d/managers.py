# SPDX-License-Identifier: GPL-3.0-or-later
"""The managers: Object Manager, Attribute Manager (follows the selection), Material Manager, Asset Browser,
Variations. Each is a panel drawn with Blender's UI elements in its own role area."""
import math
import time

import bpy

from . import matman, menus, roles

TYPE_ICON = {"MESH": "MESH_DATA", "CURVE": "CURVE_BEZCURVE", "SURFACE": "OUTLINER_OB_SURFACE", "META": "OUTLINER_OB_META",
             "FONT": "OUTLINER_OB_FONT", "EMPTY": "OUTLINER_OB_EMPTY", "LIGHT": "LIGHT_AREA", "CAMERA": "OUTLINER_OB_CAMERA",
             "ARMATURE": "OUTLINER_OB_ARMATURE", "LATTICE": "OUTLINER_OB_LATTICE", "VOLUME": "OUTLINER_OB_VOLUME",
             "POINTCLOUD": "OUTLINER_OB_POINTCLOUD", "CURVES": "OUTLINER_OB_CURVES", "GREASEPENCIL": "OUTLINER_OB_GREASEPENCIL"}
TYPE_LABEL = {"MESH": "Polygon Object", "CURVE": "Spline", "FONT": "Text Spline Object", "EMPTY": "Null", "LIGHT": "Light Object",
              "CAMERA": "Camera Object", "ARMATURE": "Joint", "LATTICE": "FFD", "VOLUME": "Volume", "SURFACE": "Surface",
              "META": "Metaball", "POINTCLOUD": "Point Cloud", "CURVES": "Hair", "GREASEPENCIL": "Sketch"}


PRIM_ICON = {"cube": "MESH_CUBE", "sphere": "MESH_UVSPHERE", "cylinder": "MESH_CYLINDER", "plane": "MESH_PLANE", "disc": "MESH_CIRCLE",
             "cone": "MESH_CONE", "torus": "MESH_TORUS", "pyramid": "MESH_CONE", "tube": "MESH_CYLINDER", "oiltank": "MESH_CAPSULE",
             "capsule": "MESH_CAPSULE", "platonic": "MESH_ICOSPHERE", "relief": "IMAGE_DATA", "landscape": "RNDCURVE",
             "figure": "ARMATURE_DATA", "bezier": "SURFACE_NSURFACE", "cyc": "MESH_GRID"}


def type_icon(ob):
    from . import kinds
    if kinds.kind_of(ob):
        return kinds.KINDS[kinds.kind_of(ob)]["icon"]
    k = ob.get("b4d_type")
    if k in PRIM_ICON:
        return PRIM_ICON[k]
    if ob.type == "LIGHT":
        return {"POINT": "LIGHT_POINT", "SUN": "LIGHT_SUN", "SPOT": "LIGHT_SPOT", "AREA": "LIGHT_AREA"}.get(ob.data.type, "LIGHT")
    return TYPE_ICON.get(ob.type, "OBJECT_DATA")


def type_icon_kw(ob):
    """Layout keywords for an object's row icon: its type icon tinted by the create-column group (icons.py), or
    Blender's plain icon."""
    from . import icons
    return icons.object_icon(ob, type_icon(ob))


# --- manager menus ------------------------------------------------------------------------------------------------
I = menus.item
OM_MENUS = [menus.simple_menu("File", [I("Merge Objects...", "wm.append", "APPEND_BLEND"), I("Save Selected Objects As...")], "om"),
            menus.simple_menu("Edit", [I("Undo", "ed.undo"), I("Redo", "ed.redo"), menus.SEP, I("Rename...", "blenda4d.om_rename"), I("Copy", "view3d.copybuffer"),
                                        I("Paste", "view3d.pastebuffer"), I("Delete", "object.delete"), menus.SEP,
                                        I("Select All", "object.select_all", action="SELECT"), I("Deselect All", "object.select_all", action="DESELECT")], "om"),
            menus.simple_menu("View", [I("Expand All", "blenda4d.om_expand", open=True), I("Collapse All", "blenda4d.om_expand", open=False)], "om"),
            menus.simple_menu("Object", [I("Group Objects", "blenda4d.group", "OUTLINER_OB_EMPTY"),
                                          I("Ungroup Objects", "blenda4d.ungroup", "X"),
                                          I("Delete Without Children", "blenda4d.delete_without_children", "TRASH"),
                                          I("Select Children", "blenda4d.select_children", "OUTLINER"), menus.SEP,
                                          I("Make Editable", "blenda4d.make_editable", "MESH_DATA"),
                                          I("Current State to Object", "blenda4d.current_state", "FREEZE"),
                                          I("Duplicate", "object.duplicate_move", "DUPLICATE")], "om"),
            menus.simple_menu("Tags", [I("Material", "blenda4d.mat_tag", "MATERIAL"), I("Smoothing", "object.shade_auto_smooth", "SHADING_SMOOTH")], "om"),
            menus.simple_menu("Bookmarks", [I("Add Bookmark")], "om")]
AM_MENUS = [menus.simple_menu("Mode", [I("Object"), I("Tag"), I("Material")], "am"),
            menus.simple_menu("Edit", [I("Copy"), I("Paste")], "am"),
            menus.simple_menu("User Data", [I("Add User Data...")], "am")]
MM_MENUS = [menus.simple_menu(n, [I("New Material", "blenda4d.new_material", "ADD")] if n == "Create" else [I("…")], "mm")
            for n in ("Create", "Edit", "View", "Select", "Material")]


MANAGER_TIPS = {"Objects": "Object Manager: every object in the scene, how they are grouped, and their tags",
                "Attributes": "Attribute Manager: the settings of what is selected",
                "Materials": "Material Manager: the scene's materials",
                "Asset Browser": "Asset Browser: models, materials and more to add to the scene"}


def manager_title(layout, title, right_tabs=None):
    """The manager's own tab strip: its name (and the other managers grouped with it)."""
    row = layout.row(align=True)
    row.alignment = "LEFT"
    if right_tabs:
        wm = bpy.context.window_manager
        row.prop(wm, right_tabs, expand=True)
    else:
        row.operator("blenda4d.title", text=title, depress=True).what = MANAGER_TIPS.get(title, title)


# --- Object Manager -------------------------------------------------------------------------------------------------
CAMERA_PAGES = {}            # tab -> fn(col, ob): the camera's own pages (cameras.py)
FONT_PAGE = []               # [fn(col, ob)]: the text object's Object page (texts.py)
OCTANE_PAGE = []             # [fn(col, ob)]: the installed renderer's page for an object (octane_live.py)
CAMERA_TABS = []             # its extra tabs after Basic, Coord., Object
CAMERA_TITLES = {}
AM_SUBJECTS = {}             # "TAG" -> fn(layout, context, ob) -> True when it drew the page (wm.b4d_am_subject "TAG:...")
OM_TAG_PICK = []             # [fn(layout, ob, tag key, icon)]: a menu-made tag as a button that shows its page
OM_DROP = []                 # [fn(context, objects, event) -> True]: a drag out of the Object Manager let go elsewhere
OM_TAG_BUTTON = []           # [fn(layout, ob, slot_index, material)]: draws a material swatch as a clickable tag
_clicks = ["", 0.0]          # last Object Manager click: row name, time (two on one row = rename)
_renamed = [0.0]


class BLENDA4D_OT_om_select(bpy.types.Operator):
    bl_idname = "blenda4d.om_select"
    bl_label = "Select"
    bl_description = ("Select the object. Cmd or Ctrl adds or removes one object, Shift selects every row from the active "
                      "object to this one. A click below the list deselects all")
    bl_options = {"UNDO"}
    name: bpy.props.StringProperty(options={"SKIP_SAVE"})
    extend: bpy.props.BoolProperty(options={"SKIP_SAVE"})
    range: bpy.props.BoolProperty(options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return roles.role(context.area) == "OBJECTS"

    def invoke(self, context, event):
        self.extend = event.ctrl or event.oskey
        self.range = event.shift and not self.extend
        if not self.name and roles.role(context.area) == "OBJECTS" and context.region is not None:
            rows = visible_rows(context)
            i = row_at(context, context.region, event.mouse_y)
            x = event.mouse_x - context.region.x
            hit = tag_at(context, context.region, rows, i, x) if 0 <= i < len(rows) else None
            if hit is not None:                           # a material tag's swatch: show the tag (C4D); Shift/Cmd adds
                if event.shift or event.ctrl or event.oskey:
                    toggle_tag(context, hit[0], hit[1])
                    return {"FINISHED"}
                return bpy.ops.blenda4d.mat_tag_pick(name=hit[0].name, slot=hit[1])
            if 0 <= i < len(rows):
                sx, u = status_x(context, context.region, rows), _unit(context.region)
                ob = rows[i][0]
                if sx - 2 <= x < sx + u:                  # the dots: upper the viewport, lower the render
                    b, t = _row_y(context.region, i)
                    y = event.mouse_y - context.region.y
                    return bpy.ops.blenda4d.om_dot(name=ob.name, render=y < (b + t) / 2, both=event.alt)
                if sx + u <= x < sx + 2 * u:              # the check (a selected row: every selected object)
                    ob.b4d_enabled = not ob.b4d_enabled
                    for a in context.screen.areas:
                        a.tag_redraw()
                    return {"FINISHED"}
        if not self.name:
            ob = object_at(context, event)
            now = time.monotonic()
            last, _clicks[:] = list(_clicks), [ob.name if ob else "", now]
            if (ob is not None and not (self.extend or self.range) and last[0] == ob.name
                    and now - last[1] < context.preferences.inputs.mouse_double_click_time / 1000
                    and now - _renamed[0] > 0.6):
                _clicks[0] = ""
                return bpy.ops.blenda4d.om_rename("INVOKE_DEFAULT", name=ob.name)
            if ob is None:
                if self.extend or self.range:
                    return {"CANCELLED"}
                context.window_manager.b4d_am_subject = ""
                for o in context.view_layer.objects:
                    o.select_set(False)
                return {"FINISHED"}
            self.name = ob.name
        return self.execute(context)

    def execute(self, context):
        ob = bpy.data.objects.get(self.name)
        if ob is None:
            return {"CANCELLED"}
        context.window_manager.b4d_am_subject = ""         # a click on the object shows the object again, not its tag
        context.window_manager.b4d_tag_sel = ""
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        act = context.view_layer.objects.active
        if self.range and act is not None and act != ob:
            names = [o.name for o, _d in visible_rows(context)]
            if act.name in names and ob.name in names:
                a, b = sorted((names.index(act.name), names.index(ob.name)))
                for o in context.view_layer.objects:
                    o.select_set(False)
                for n in names[a:b + 1]:
                    try:
                        bpy.data.objects[n].select_set(True)
                    except RuntimeError:
                        pass
                return {"FINISHED"}                       # the active object stays where the range started
        if not self.extend:
            for o in context.view_layer.objects:
                o.select_set(False)
        was = ob.select_get()
        try:
            ob.select_set(not (self.extend and was))
        except RuntimeError:
            pass
        if ob.select_get() or not ob.visible_get() and not (self.extend and act == ob):
            context.view_layer.objects.active = ob        # switched off (hidden): Blender cannot select it, but it is
                                                          # the active object, shown in the Attribute Manager (C4D)
        elif act == ob:                                   # took the active object out: the next selected one leads
            context.view_layer.objects.active = next((o for o in context.selected_objects), None)
        return {"FINISHED"}


class BLENDA4D_OT_om_delete(bpy.types.Operator):
    bl_idname = "blenda4d.om_delete"
    bl_label = "Delete"
    bl_description = "Delete the selected objects"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        from . import material_tag
        return roles.role(context.area) == "OBJECTS" and (any(o.select_get() for o in context.view_layer.objects)
                                                          or bool(picked_tags(context)))

    def execute(self, context):
        tags = picked_tags(context)
        if tags:                                          # selected material tags: Delete removes them (C4D)
            for ob, slot in sorted(tags, key=lambda t: (t[0].name, -t[1])):
                remove_tag(ob, slot)
            context.window_manager.b4d_am_subject = ""
            context.window_manager.b4d_tag_sel = ""
            for a in context.screen.areas:
                a.tag_redraw()
            return {"FINISHED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        context.window_manager.b4d_am_subject = ""
        return bpy.ops.object.delete(confirm=False)


class BLENDA4D_OT_om_fold(bpy.types.Operator):
    bl_idname = "blenda4d.om_fold"
    bl_label = "Fold"
    bl_description = "Show or hide the objects under this one"
    name: bpy.props.StringProperty()

    def execute(self, context):
        ob = bpy.data.objects.get(self.name)
        if ob:
            ob.b4d_om_closed = not ob.b4d_om_closed
        return {"FINISHED"}


class BLENDA4D_OT_om_expand(bpy.types.Operator):
    bl_idname = "blenda4d.om_expand"
    bl_label = "Expand"
    bl_description = "Open or close every object that has objects under it"
    open: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        for ob in context.scene.objects:
            ob.b4d_om_closed = not self.open
        return {"FINISHED"}


class BLENDA4D_OT_group(bpy.types.Operator):
    bl_idname = "blenda4d.group"
    bl_label = "Group Objects"
    bl_description = "Put the selected objects under a new Null"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        sel = list(context.selected_objects)
        if not sel:
            return {"CANCELLED"}
        null = bpy.data.objects.new("Null", None)
        context.collection.objects.link(null)
        for ob in sel:
            mw = ob.matrix_world.copy()
            ob.parent = null
            ob.matrix_parent_inverse.identity()
            ob.matrix_world = mw
        return {"FINISHED"}


TOP_LEVEL = "\x00top"
ROWS_TOP_APART = 0.35        # with the title, menus and tools in their own strip above (OM_HEAD)
ROWS_TOP_UNITS = 4.40        # where the first object row starts, in row heights below the top of the panel area (measured
#                               on Blender 5.2 and 5.3, Mac, Windows and Linux, at every Size: icon centres sit at 4.40 + i + 0.5)
STRIPE = (0.02, 0.02, 0.02, 1.0)      # added to every other Object Manager row: +5 grey levels, as in the original (Joseph, Nov 19)


def om_key(ob):
    """Object Manager order: the place it was dropped (b4d_om_order), then the name for objects never moved."""
    return (ob.get("b4d_om_order", 1e9), ob.name)


def siblings(parent, scene):
    return sorted([o for o in scene.objects if o.parent == parent and not o.get("b4d_internal")], key=om_key)


def place(objs, parent, before=None, after=None, scene=None):
    """objs go under parent (None: top level) at that place among its children: before or after another child, or last.
    Every child gets a number for its place, so the order stays as dropped."""
    scene = scene or bpy.context.scene
    reparent(objs, parent)
    rest = [o for o in siblings(parent, scene) if o not in objs]
    if before is not None and before in rest:
        i = rest.index(before)
    elif after is not None and after in rest:
        i = rest.index(after) + 1
    else:
        i = len(rest)
    order = rest[:i] + [o for o in sorted(objs, key=om_key)] + rest[i:]
    for n, o in enumerate(order):
        o["b4d_om_order"] = float(n)


def visible_rows(context):
    """The Object Manager's rows in drawing order: (object, depth). Folded objects hide their children; the search
    keeps an object when it or anything under it matches. One pass over the scene builds who is under whom (asking
    Blender for each object's children scans the whole scene every time, which made big scenes slow to draw)."""
    needle = context.window_manager.b4d_om_search.lower()
    kids = {}
    for ob in context.scene.objects:
        if not ob.get("b4d_internal"):
            kids.setdefault(ob.parent, []).append(ob)
    for v in kids.values():
        v.sort(key=om_key)
    out = []

    def matches(ob):
        if needle in ob.name.lower():
            return True
        return any(matches(c) for c in kids.get(ob, ()))

    def walk(ob, depth):
        if needle and not matches(ob):
            return
        out.append((ob, depth))
        if not ob.b4d_om_closed:
            for c in kids.get(ob, ()):
                walk(c, depth + 1)
    for ob in kids.get(None, ()):
        walk(ob, 0)
    return out


def head_apart(screen):
    return any(roles.role(a) == "OM_HEAD" for a in screen.areas)


def rows_top(screen=None):
    """Where the first object row starts, in row heights below the top of the Object Manager's panel area."""
    screen = screen or bpy.context.window.screen
    return ROWS_TOP_APART if head_apart(screen) else ROWS_TOP_UNITS


def row_height():
    s = bpy.context.preferences.system
    # Blender's own row height (U.widget_unit): C rounding, half away from zero. Python's round() rounds halves to even,
    # so at scales where 18 * scale ends in .5 (e.g. 125% on Windows) the rows came out a pixel short and drifted (#4).
    return int(math.floor(18 * s.ui_scale + 0.5) + 2 * s.pixel_size)


def row_at(context, region, mouse_y):
    """Index of the Object Manager row under a window y (len(rows) or more = below the last row, -1 = above)."""
    y = region.view2d.region_to_view(0, mouse_y - region.y)[1]
    h = row_height()
    return int((-y - rows_top() * h) // h)


def object_at(context, event):
    """The object on the Object Manager row under the mouse, or None."""
    if roles.role(context.area) != "OBJECTS" or context.region is None or context.region.type != "WINDOW":
        return None
    rows = visible_rows(context)
    i = row_at(context, context.region, event.mouse_y)
    return rows[i][0] if 0 <= i < len(rows) else None


def _is_under(ob, other):
    p = other
    while p is not None:
        if p == ob:
            return True
        p = p.parent
    return False


def reparent(objs, target):
    """Put objs under target (None = top level), keeping where they are in the world."""
    done = 0
    for ob in objs:
        if target is not None and (ob == target or _is_under(ob, target)):
            continue
        mw = ob.matrix_world.copy()
        ob.parent = target
        ob.matrix_parent_inverse.identity()        # no hidden parent inverse: the local values are the real ones
        ob.matrix_world = mw
        done += 1
    return done


def duplicate_tree(context, objs):
    """Independent copies of objs with everything under them (C4D copies the whole group). Returns the copies of objs
    themselves, selected, the first one active."""
    keep = set()

    def walk(o):
        keep.add(o)
        for c in o.children:
            walk(c)
    for o in objs:
        walk(o)
    vl = context.view_layer
    for o in vl.objects:
        try:
            o.select_set(o in keep)
        except RuntimeError:
            pass
    vl.objects.active = objs[0] if objs else None
    before = set(bpy.data.objects)
    bpy.ops.object.duplicate(linked=False)
    new = [o for o in bpy.data.objects if o not in before]
    tops = [o for o in new if o.parent not in new]
    order = {o.name: i for i, o in enumerate(objs)}

    def src_of(c):                               # Blender names a copy "Name.001": match it to its original by order
        return min((order.get(o.name.rsplit(".", 1)[0], 99), o.name) for o in [c])[0]
    tops.sort(key=src_of)
    for o in vl.objects:
        try:
            o.select_set(o in tops)
        except RuntimeError:
            pass
    if tops:
        vl.objects.active = tops[0]
    from . import generators
    generators.sync_all()
    return tops


def picked_tags(context):
    """Every selected material tag as (object, slot): the one the Attribute Manager shows and any others added with a
    box, Shift or Cmd/Ctrl."""
    from . import material_tag
    out = []
    for part in context.window_manager.b4d_tag_sel.split("|"):
        name, _sep, slot = part.rpartition(":")
        ob = bpy.data.objects.get(name)
        if ob is not None and slot.isdigit() and int(slot) < len(ob.material_slots):
            out.append((ob, int(slot)))
    sub = material_tag.subject(context)
    if sub is not None and sub not in out:
        out.append(sub)
    return out


def set_tags(context, tags):
    context.window_manager.b4d_tag_sel = "|".join(f"{ob.name}:{slot}" for ob, slot in tags)
    for a in context.screen.areas:
        a.tag_redraw()


def toggle_tag(context, ob, slot):
    tags = picked_tags(context)
    if (ob, slot) in tags:
        tags.remove((ob, slot))
    else:
        tags.append((ob, slot))
    set_tags(context, tags)


def status_x(context, region, rows=None):
    """Where the first status cell (the dots) starts, in region pixels: the divider plus the panel's own inset."""
    return divider_x(context, region, rows) + 8 * context.preferences.system.ui_scale * _zoom(region)


def tag_cell(context, region, rows, ob, k):
    """(x0, x1) of the object's k-th tag cell on its row."""
    u = _unit(region)
    x0 = status_x(context, region, rows) + (2 + (ob.type == "CAMERA") + k) * u
    return x0, x0 + u


def tag_at(context, region, rows, i, x):
    """(object, slot) of the material tag swatch at region x on row i, or None. The status side starts at the column
    divider: the dots, the check, the camera's switch, then one cell per tag (_tags order)."""
    ob = rows[i][0]
    u = _unit(region)
    k = int((x - status_x(context, region, rows)) // u) - 2 - (ob.type == "CAMERA")
    tags = _tags(ob)
    if 0 <= k < len(tags) and tags[k][1] is not None:
        return ob, tags[k][2]
    return None


def move_tag(context, src, slot, dst, copy=False):
    """A material tag from one object to another (copy: the source keeps it), with its settings (C4D)."""
    from . import material_tag
    if not hasattr(getattr(dst, "data", None), "materials") or slot >= len(src.material_slots):
        return False
    material_tag.ensure(src)
    mat = src.material_slots[slot].material
    dst.data.materials.append(mat)
    material_tag.ensure(dst)
    a, b = src.b4d_mat_tags[slot], dst.b4d_mat_tags[len(dst.material_slots) - 1]
    for p in a.bl_rna.properties:
        if p.identifier != "rna_type" and not p.is_readonly:
            try:
                setattr(b, p.identifier, getattr(a, p.identifier))
            except (AttributeError, TypeError):
                pass
    if not copy and src != dst:
        remove_tag(src, slot)
    show_last(dst)
    dst.update_tag()
    return True


def remove_tag(ob, slot):
    from . import material_tag
    material_tag.ensure(ob)
    if len(ob.data.materials) <= 1:
        ob.data.materials.clear()                         # pop() of the last one leaves the object an empty slot
    else:
        ob.data.materials.pop(index=slot)
    if slot < len(ob.b4d_mat_tags):
        ob.b4d_mat_tags.remove(slot)
    show_last(ob)
    ob.update_tag()


def show_last(ob):
    """C4D: the rightmost material tag is the one that shows. Generators follow it on their own (primitives.py); a
    plain mesh whose faces all wear one material is moved to the last tag. A mesh with materials by face is left as
    it is."""
    me = getattr(ob, "data", None)
    if ob.type != "MESH" or me is None or not len(ob.material_slots) or any(
            m.type == "NODES" and m.node_group and m.node_group.name.startswith("Blenda ") for m in ob.modifiers):
        return
    if len(me.polygons) and len({p.material_index for p in me.polygons}) <= 1:
        me.polygons.foreach_set("material_index", [len(ob.material_slots) - 1] * len(me.polygons))
        me.update()


class BLENDA4D_OT_om_drag(bpy.types.Operator):
    bl_idname = "blenda4d.om_drag"
    bl_label = "Drag in the Object Manager"
    bl_description = "Drag objects onto another object to put them under it; drop below the list for the top level"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return roles.role(context.area) == "OBJECTS"

    def _target(self, context, event):
        """Where a drop would go, as the Object Manager shows it while dragging:
        SELF (over the dragged objects: nothing), INTO:name (the middle of a row: under it), BEFORE:name / AFTER:name
        (the top or bottom quarter of a row: a line there, the same level as that row), END (below the list: last at
        the top level)."""
        v = self.region.view2d.region_to_view(0, event.mouse_y - self.region.y)[1]
        h = row_height()
        f = -v / h - rows_top()                          # rows from the first row's top, with the fraction
        i = int(f // 1) if f >= 0 else -1
        if i >= len(self.rows):
            return "END"
        if i < 0:
            return ""
        ob = self.rows[i][0]
        if ob in self.objs or any(_is_under(o, ob) for o in self.objs):
            return "SELF"
        part = f - i
        if part < 0.25:
            return "BEFORE:" + ob.name
        if part > 0.75:
            return "AFTER:" + ob.name
        return "INTO:" + ob.name

    def invoke(self, context, event):
        self.region = context.region
        self.rows = visible_rows(context)
        i = row_at(context, self.region, event.mouse_prev_press_y)
        if not 0 <= i < len(self.rows):
            return {"PASS_THROUGH"}
        x = event.mouse_prev_press_x - self.region.x
        dxx = divider_x(context, self.region, self.rows)
        sxx = status_x(context, self.region, self.rows)
        if (_name_end(context, self.region, i, self.rows) + 0.4 * _unit(self.region) < x < dxx - 3
                or dxx - 3 <= x < sxx + 2 * _unit(self.region)):     # empty space: a box; the dots and checks: paint
            return {"PASS_THROUGH"}                       # empty space right of the name: om_box draws a box
        hit = tag_at(context, self.region, self.rows, i, x)
        if hit is None and x >= sxx + 2 * _unit(self.region):
            return {"PASS_THROUGH"}                       # empty space in the tag column: om_box draws a box of tags
        self.tag = (hit[0].name, hit[1]) if hit else None          # a material tag swatch: the tag is dragged
        src = self.rows[i][0]
        self.src_name = src.name
        self.objs = [src] + ([o for o in context.selected_objects if o != src] if src.select_get() else [])
        self.objs = [o for o in self.objs if not any(_is_under(p, o) for p in self.objs if p != o)]  # a child goes with its parent
        self.copy = event.ctrl or event.oskey
        context.window_manager.b4d_om_drop = "SELF"
        _drag_mouse[:] = [event.mouse_x - self.region.x, event.mouse_y - self.region.y]
        context.window.cursor_modal_set("STOP")
        context.window_manager.modal_handler_add(self)
        self.region.tag_redraw()
        return {"RUNNING_MODAL"}

    def _end(self, context):
        context.window_manager.b4d_om_drop = ""
        _drag_mouse[:] = []
        context.window.cursor_modal_restore()
        self.region.tag_redraw()

    def modal(self, context, event):
        wm = context.window_manager
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            t = self._target(context, event)
            _drag_mouse[:] = [event.mouse_x - self.region.x, event.mouse_y - self.region.y]
            if t != wm.b4d_om_drop:
                context.window.cursor_modal_set("STOP" if t in ("SELF", "") else "DEFAULT")
                wm.b4d_om_drop = t
            self.region.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._end(context)
            if any(f(context, self.objs, event) for f in OM_DROP):     # let go over a tag's page: fills its object field
                return {"FINISHED"}
            if self.tag:                                  # a tag let go on a row: it goes to that object (Cmd/Ctrl: a copy)
                i = row_at(context, self.region, event.mouse_y)
                dst = self.rows[i][0] if 0 <= i < len(self.rows) else None
                src = bpy.data.objects.get(self.tag[0])
                if dst is None or src is None or (dst == src and not (self.copy or event.ctrl or event.oskey)):
                    return {"CANCELLED"}
                move_tag(context, src, self.tag[1], dst, copy=self.copy or event.ctrl or event.oskey)
                from . import material_tag
                context.window_manager.b4d_am_subject = f"{material_tag.SUBJECT}:{dst.name}:{len(dst.material_slots) - 1}"
                for o in context.view_layer.objects:
                    if o is not None:
                        o.select_set(o == dst)
                context.view_layer.objects.active = dst
                for a in context.screen.areas:
                    a.tag_redraw()
                return {"FINISHED"}
            t = self._target(context, event)
            kind, _sep, name = t.partition(":")
            target = bpy.data.objects.get(name) if name else None
            if (self.copy or event.ctrl or event.oskey) and kind in ("INTO", "BEFORE", "AFTER", "END", "SELF"):
                self.objs = duplicate_tree(context, self.objs)          # Ctrl/Cmd: drop a copy, its children too (C4D)
                if kind == "SELF":
                    kind, target = "AFTER", None
            if kind == "INTO" and target is not None:
                place(self.objs, target)
            elif kind == "AFTER" and target is None:
                src = bpy.data.objects.get(getattr(self, "src_name", ""))
                place(self.objs, src.parent if src else None, after=src)
            elif kind in ("BEFORE", "AFTER") and target is not None:
                place(self.objs, target.parent, before=target if kind == "BEFORE" else None, after=target if kind == "AFTER" else None)
            elif kind == "END":
                place(self.objs, None)
            else:
                return {"CANCELLED"}
            from . import generators
            generators.sync_all()                       # a generator reads its children in this order
            return {"FINISHED"}
        if event.type in {"ESC", "RIGHTMOUSE"}:
            self._end(context)
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}


_drag_mouse = []                 # the mouse in the Object Manager's region while dragging (for the cursor badge)


def _name_end(context, region, i, rows):
    """Where row i's name text ends, in region pixels."""
    import blf
    ob, d = rows[i]
    size = context.preferences.ui_styles[0].widget.points * context.preferences.system.ui_scale * _zoom(region)
    blf.size(0, size)
    return _name_x(context, region, d)[1] + blf.dimensions(0, ob.name)[0]


class BLENDA4D_OT_om_box(bpy.types.Operator):
    bl_idname = "blenda4d.om_box"
    bl_label = "Box Select"
    bl_description = ("Drag from empty space (right of the names or below the list) to select every row the box "
                      "touches. Shift, Cmd or Ctrl adds to the selection")
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return roles.role(context.area) == "OBJECTS"

    def invoke(self, context, event):
        region = context.region
        if region is None or region.type != "WINDOW":
            return {"PASS_THROUGH"}
        rows = visible_rows(context)
        x = event.mouse_prev_press_x - region.x
        i = row_at(context, region, event.mouse_prev_press_y)
        if i < 0:
            return {"PASS_THROUGH"}
        u = _unit(region)
        self.tags_mode = x >= status_x(context, region, rows) + 2 * u            # from the tag column: a box of tags
        if i < len(rows):
            if self.tags_mode:
                if tag_at(context, region, rows, i, x) is not None:
                    return {"PASS_THROUGH"}                # on a tag: om_drag moves it
            elif x < _name_end(context, region, i, rows) + 0.4 * u or x > divider_x(context, region, rows) - 3:
                return {"PASS_THROUGH"}                    # on a name or the status columns: om_drag moves it
        self.region, self.rows = region, rows
        if self.tags_mode:
            self.tags_before = picked_tags(context) if (event.shift or event.ctrl or event.oskey) else []
            _box[:] = [x, event.mouse_prev_press_y - region.y, event.mouse_x - region.x, event.mouse_y - region.y]
            context.window_manager.modal_handler_add(self)
            self._apply(context, event)
            return {"RUNNING_MODAL"}
        self.add = event.shift or event.ctrl or event.oskey
        self.before = {o.name for o in context.selected_objects} if self.add else set()
        _box[:] = [x, event.mouse_prev_press_y - region.y, event.mouse_x - region.x, event.mouse_y - region.y]
        context.window_manager.modal_handler_add(self)
        self._apply(context, event)
        return {"RUNNING_MODAL"}

    def _hit(self, context):
        h = row_height()
        v2d = self.region.view2d
        y0, y1 = sorted((_box[1], _box[3]))
        out = []
        for i in range(len(self.rows)):
            bottom, top = _row_y(self.region, i)
            if top >= y0 and bottom <= y1:
                out.append(self.rows[i][0])
        return out

    def _tag_hits(self, context):
        x0, x1 = sorted((_box[0], _box[2]))
        y0, y1 = sorted((_box[1], _box[3]))
        out = []
        for i, (ob, _d) in enumerate(self.rows):
            b, t = _row_y(self.region, i)
            if t < y0 or b > y1:
                continue
            for k, (_icon, mat, slot) in enumerate(_tags(ob)):
                if mat is None:
                    continue
                a0, a1 = tag_cell(context, self.region, self.rows, ob, k)
                if a1 >= x0 and a0 <= x1:
                    out.append((ob, slot))
        return out

    def _apply(self, context, event):
        _box[2:] = [event.mouse_x - self.region.x, event.mouse_y - self.region.y]
        if self.tags_mode:
            hits = self._tag_hits(context)
            set_tags(context, self.tags_before + [h for h in hits if h not in self.tags_before])
            from . import material_tag
            if hits and not self.tags_before:            # the Attribute Manager shows the first tag of the box
                ob, slot = hits[0]
                context.window_manager.b4d_am_subject = f"{material_tag.SUBJECT}:{ob.name}:{slot}"
                context.view_layer.objects.active = ob
            self.region.tag_redraw()
            return
        hit = self._hit(context)
        for o in context.view_layer.objects:
            try:
                o.select_set(o.name in self.before or o in hit)
            except RuntimeError:
                pass
        if hit and (context.view_layer.objects.active not in hit or not self.add):
            if context.view_layer.objects.active is None or not context.view_layer.objects.active.select_get():
                context.view_layer.objects.active = hit[0]
        self.region.tag_redraw()

    def modal(self, context, event):
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            self._apply(context, event)
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE" and self.tags_mode:
            self._apply(context, event)
            _box[:] = []
            self.region.tag_redraw()
            return {"FINISHED"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._apply(context, event)
            hit = self._hit(context)
            if hit and not self.add:
                context.view_layer.objects.active = hit[0]
            context.window_manager.b4d_am_subject = ""
            _box[:] = []
            self.region.tag_redraw()
            return {"FINISHED"}
        if event.type in {"ESC", "RIGHTMOUSE"}:
            for o in context.view_layer.objects:
                try:
                    o.select_set(o.name in self.before)
                except RuntimeError:
                    pass
            _box[:] = []
            self.region.tag_redraw()
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}


_box = []                        # the box being dragged in the Object Manager: x0, y0, x1, y1 in region pixels


class BLENDA4D_OT_om_rename(bpy.types.Operator):
    bl_idname = "blenda4d.om_rename"
    bl_label = "Rename"
    bl_description = "Rename the active object"
    bl_options = {"UNDO"}
    name: bpy.props.StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return roles.role(context.area) == "OBJECTS"

    def invoke(self, context, event):
        _renamed[0] = time.monotonic()
        ob = bpy.data.objects.get(self.name) or object_at(context, event) or context.active_object
        if ob is None:
            return {"CANCELLED"}
        self.name = ob.name
        return context.window_manager.invoke_popup(self, width=220)

    def draw(self, context):
        ob = bpy.data.objects.get(self.name)
        if ob is not None:
            self.layout.activate_init = True
            self.layout.prop(ob, "name", text="", **type_icon_kw(ob))

    def execute(self, context):
        return {"FINISHED"}


def _tags(ob):
    """The icons after an object's row: one per material, plus smoothing and modifiers."""
    out = []
    for i, slot in enumerate(getattr(ob, "material_slots", [])):
        if slot.material:
            out.append(("MATERIAL", slot.material, i))
    if ob.type == "MESH" and any(m.type == "SMOOTH_BY_ANGLE" or m.name.startswith("Smooth") for m in ob.modifiers):
        out.append(("SHADING_SMOOTH", None, -1))
    from . import om_menu
    out += [(icon, None, key) for icon, key in om_menu.tags(ob)]     # the slot is the tag's key
    return out


def _main_view(context):
    """The largest 3D view in the window, with its drawing region."""
    views = [a for a in context.window.screen.areas if a.type == "VIEW_3D" and len(a.spaces)]
    if not views:
        return None, None
    area = max(views, key=lambda a: a.width * a.height)
    return area, next((r for r in area.regions if r.type == "WINDOW"), None)


def _in_solo(context):
    from . import solo
    return solo.is_on(context.scene)


class BLENDA4D_OT_om_solo(bpy.types.Operator):
    bl_idname = "blenda4d.om_solo"
    bl_label = "Solo"
    bl_description = ("Show only the selected objects and what is under them; the camera does not move. Press again "
                      "to show everything")

    def execute(self, context):
        from . import solo
        if not solo.run(context, "TOGGLE"):
            self.report({"INFO"}, "Select the objects to solo first")
            return {"CANCELLED"}
        solo.redraw(context)
        return {"FINISHED"}


class BLENDA4D_OT_om_scroll_active(bpy.types.Operator):
    bl_idname = "blenda4d.om_scroll_active"
    bl_label = "Scroll to First Active"
    bl_description = "Open the folders above the active object and scroll the Object Manager to it"

    def execute(self, context):
        ob = context.view_layer.objects.active
        if ob is None:
            return {"CANCELLED"}
        p = ob.parent
        while p is not None:
            p.b4d_om_closed = False
            p = p.parent
        area = next((a for a in context.window.screen.areas if roles.role(a) == "OBJECTS"), None)
        region = next((r for r in area.regions if r.type == "WINDOW"), None) if area else None
        if region is None:
            return {"CANCELLED"}
        rows = [r[0] for r in visible_rows(context)]
        if ob not in rows:
            return {"CANCELLED"}
        h = row_height()
        row_top = -(rows_top() + rows.index(ob)) * h
        v2d = region.view2d
        top = v2d.region_to_view(0, region.height)[1]
        bottom = v2d.region_to_view(0, 0)[1]
        if bottom + h <= row_top <= top:
            return {"FINISHED"}                          # already in sight
        with context.temp_override(area=area, region=region):
            for _ in range(400):                         # Blender moves a little per scroll: step until the row shows
                top = v2d.region_to_view(0, region.height)[1]
                bottom = v2d.region_to_view(0, 0)[1]
                if bottom + 2 * h <= row_top <= top - h:
                    break
                before = top
                if row_top > top - h:
                    bpy.ops.view2d.scroll_up(deltay=40)
                else:
                    bpy.ops.view2d.scroll_down(deltay=40)
                if v2d.region_to_view(0, region.height)[1] == before:
                    break                                # at the end of the list
        area.tag_redraw()
        return {"FINISHED"}


ZOOM_LIMIT = 2.0             # Blender's own largest zoom for this kind of area


def _om_fit_zoom(context, region):
    """The largest zoom at which the widest row (indent, icons, its name and the status columns) still fits the
    Object Manager's width, so a larger Size never pushes anything out of the panel."""
    import blf
    rows = visible_rows(context)
    h = row_height()
    style = context.preferences.ui_styles[0].widget
    blf.size(0, style.points * context.preferences.system.ui_scale)
    widest = 0.0
    for ob, depth in rows:
        widest = max(widest, h * (2.4 + 0.8 * depth) + blf.dimensions(0, ob.name)[0])
    tags = max((len(_tags(ob)) for ob, _d in rows), default=0)
    content = widest + (2 + tags) * h + 1.2 * h       # the stacked dots and the check, then the tags
    return max(1.0, min(ZOOM_LIMIT, region.width / max(content, 1.0)))


def _om_zoom(self, context):
    """The size slider: Blender's own area zoom (as Ctrl+scroll), so names, icons and rows grow together, smoothly
    from the normal size up to the largest size at which every row still fits the panel."""
    area = next((a for a in context.window.screen.areas if roles.role(a) == "OBJECTS"), None)
    region = next((r for r in area.regions if r.type == "WINDOW"), None) if area else None
    if region is None:
        return
    target = 1.0 + (_om_fit_zoom(context, region) - 1.0) * self.b4d_om_zoom / 100.0
    fac = (1.0 - 1.0 / target) / 2.0                     # Blender's zoom_in: new scale = 1 / (1 - 2 * fac)
    with context.temp_override(area=area, region=region):
        try:
            bpy.ops.view2d.reset()
            if fac > 0.0005:
                bpy.ops.view2d.zoom_in(zoomfacx=fac, zoomfacy=fac)
        except RuntimeError as ex:
            print("Blenda 4D: Object Manager size", ex)
    area.tag_redraw()


class BLENDA4D_OT_size_step(bpy.types.Operator):
    bl_idname = "blenda4d.size_step"
    bl_label = "Size"
    bl_description = "Make the names and icons smaller or larger"
    prop: bpy.props.StringProperty(options={"SKIP_SAVE"})
    step: bpy.props.FloatProperty(default=1.0, options={"SKIP_SAVE"})

    def execute(self, context):
        wm = context.window_manager
        rna = wm.bl_rna.properties[self.prop]
        v = max(rna.hard_min, min(rna.hard_max, getattr(wm, self.prop) + self.step))
        setattr(wm, self.prop, int(round(v)) if rna.type == "INT" else v)
        return {"FINISHED"}


def size_bar(row, prop, step=1):
    """A manager's size bar: zoom out button, the slider, zoom in button (the buttons step it, the slider drags)."""
    o = row.operator("blenda4d.size_step", text="", icon="ZOOM_OUT", emboss=False)
    o.prop, o.step = prop, -step
    row.prop(bpy.context.window_manager, prop, text="Size", slider=True)
    o = row.operator("blenda4d.size_step", text="", icon="ZOOM_IN", emboss=False)
    o.prop, o.step = prop, step


class BLENDA4D_PT_om_bar(roles.RolePanel, bpy.types.Panel):
    """The Object Manager's bottom strip: an area of its own so the Size slider stays at the bottom."""
    bl_label = "Object Manager Size"
    role = "OM_BAR"

    def draw(self, context):
        sp = self.layout.split(factor=0.35)              # a short slider on the right, as in the Material Manager
        sp.label(text="")
        row = sp.row(align=True)                         # zoom out / Size / zoom in: says what it does at a glance
        size_bar(row, "b4d_om_zoom", step=10)


def _status_split(context, buttons):
    """The split factor that leaves exactly `buttons` icon widths (plus a little room) for the status side of a row,
    whatever the panel width and the Size (zoom)."""
    region = context.region
    try:
        v2d = region.view2d
        zoom = (v2d.view_to_region(0, 0, clip=False)[1] - v2d.view_to_region(0, -1000, clip=False)[1]) / 1000
    except (AttributeError, ZeroDivisionError):
        zoom = 1.0
    width = region.width / max(zoom, 0.01)               # the panel's width in layout units
    need = buttons * row_height() + row_height() * 0.6
    return max(0.25, min(0.9, 1 - need / max(width, 1)))


def divider_x(context, region, rows=None):
    """Where the Object Manager's column divider sits, in region pixels: the dots, check and tags start right after
    it (C4D). Dragged by the user (b4d_om_divider, in row units, so it keeps its place at any Size), or just past the
    longest name until then."""
    import blf
    rows = visible_rows(context) if rows is None else rows
    u = _unit(region)
    want = context.window_manager.b4d_om_divider
    if want > 0:
        x = want * u
    else:
        size = context.preferences.ui_styles[0].widget.points * context.preferences.system.ui_scale * _zoom(region)
        blf.size(0, size)
        x = max((_name_x(context, region, d)[1] + blf.dimensions(0, ob.name)[0] for ob, d in rows), default=4 * u) + 0.8 * u
    tags = max((len(_tags(ob)) + (ob.type == "CAMERA") for ob, _d in rows), default=0)
    return max(3.0 * u, min(x, region.width - (2.6 + tags) * u))


_press_alt = [False]


class BLENDA4D_OT_om_divider(bpy.types.Operator):
    bl_idname = "blenda4d.om_divider"
    bl_label = "Move Column Divider"
    bl_description = "Drag the line between the names and the status columns to move the dots, checks and tags"

    @classmethod
    def poll(cls, context):
        return roles.role(context.area) == "OBJECTS"

    def invoke(self, context, event):
        _press_alt[0] = event.alt                          # a drag begun here paints both dots: Blender's drag event
        region = context.region                            # does not carry the press's Alt (Option on a Mac)
        if region is None or region.type != "WINDOW":
            return {"PASS_THROUGH"}
        x = event.mouse_x - region.x
        if abs(x - divider_x(context, region)) > 5 * context.preferences.system.ui_scale:
            return {"PASS_THROUGH"}
        self.region = region
        context.window.cursor_modal_set("MOVE_X")
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            u = _unit(self.region)
            context.window_manager.b4d_om_divider = max(3.0, (event.mouse_x - self.region.x) / max(u, 1.0))
            for a in context.screen.areas:
                if roles.role(a) == "OBJECTS":
                    a.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE" or event.type in {"ESC", "RIGHTMOUSE"}:
            context.window.cursor_modal_restore()
            return {"FINISHED"}
        return {"RUNNING_MODAL"}


OM_MENU_SHARE = 0.915


def _icon_px():
    """An icon-only label's width: one unit."""
    return 20 * bpy.context.preferences.system.ui_scale


OM_SEARCH_MIN_PX = 120                                    # the search box always shows as a field, never only its icon


def _om_menu_share():
    """The menus' share of the Object Manager's title line. The search box keeps at least OM_SEARCH_MIN_PX; menus that
    no longer fit go into the » menu."""
    w = menus.panel_width()
    if not w:
        return OM_MENU_SHARE
    need = OM_SEARCH_MIN_PX * bpy.context.preferences.system.ui_scale
    return max(0.35, min(OM_MENU_SHARE, 1 - need / max(w, 1)))


def draw_om_head(layout, context):
    """The Object Manager's title, menus, search and tool row."""
    manager_title(layout, "Objects")
    from . import build                                   # a short window: whole rows go, none is cut in half
    room = context.area.height / max(1.0, build.px(build.OM_HEAD_PX)) if roles.role(context.area) == "OM_HEAD" else 1.0
    if room < 0.55:
        return
    share = _om_menu_share()
    sp = layout.split(factor=share, align=True)           # menus on the left, the search box at the right edge
    bar = sp.row(align=True)
    bar.label(text="", icon="COLLAPSEMENU")
    menus.menu_bar(bar, OM_MENUS, avail=menus.panel_width(share, _icon_px()))
    sp.prop(context.window_manager, "b4d_om_search", text="", icon="VIEWZOOM", placeholder="Search")
    if room < 0.8:
        return
    tools = layout.row(align=True)                        # the tool row: scroll to the active object, solo
    tools.alignment = "LEFT"                              # its icons keep their size however narrow the panel is
    tools.operator("blenda4d.om_scroll_active", text="", icon="ZOOM_SELECTED", emboss=False)
    tools.operator("blenda4d.om_solo", text="", icon="SELECT_INTERSECT", emboss=False,
                   depress=_in_solo(context))
    tools.operator("blenda4d.solo", text="", icon="HIDE_OFF", emboss=False).mode = "OFF"   # Solo Off
    tools.separator(factor=1.5)
    tools.operator("blenda4d.scene_to_octane", text="", icon="SHADING_RENDERED", emboss=False)   # whole scene
    tools.operator("blenda4d.scene_to_blender", text="", icon="BLENDER", emboss=False)


class BLENDA4D_PT_om_head(roles.RolePanel, bpy.types.Panel):
    """The Object Manager's top strip, an area of its own so the Size slider zooms only the object rows."""
    bl_label = "Object Manager"
    role = "OM_HEAD"

    def draw(self, context):
        draw_om_head(self.layout, context)


class BLENDA4D_PT_objects(roles.RolePanel, bpy.types.Panel):
    bl_label = "Objects"
    role = "OBJECTS"

    def draw(self, context):
        layout = self.layout
        if not head_apart(context.window.screen):          # a layout saved before the head had its own strip
            draw_om_head(layout, context)
            layout.separator(factor=0.3)
        col = layout.column(align=True)
        drop = context.window_manager.b4d_om_drop
        rows = visible_rows(context)
        tags = max((len(_tags(ob)) + (ob.type == "CAMERA") for ob, _d in rows), default=0)   # every row keeps room for the most tags,
        region = context.region
        split = max(0.05, min(0.95, divider_x(context, region, rows) / max(region.width, 1)))   # the column divider
        for ob, depth in rows:
            self._row(col, ob, depth, tags, split)



    def _row(self, col, ob, depth, tag_room=0, split=0.6):
        sp = col.split(factor=split, align=True)          # name side | a fixed-width status side: a long name or a
        row = sp.row(align=True)                          # larger Size never squeezes the dots and checks together
        if depth:
            row.separator(factor=1.6 * depth)
        if ob.children:                                   # the fold box is drawn over this button (_draw_rows)
            row.operator("blenda4d.om_fold", text="", icon="BLANK1", emboss=False).name = ob.name
        else:
            row.label(text="", icon="BLANK1")
        name = row.row(align=True)
        name.alignment = "LEFT"
        name.label(text="", **type_icon_kw(ob))          # the name is drawn in its colour by _draw_rows (C4D look)
        right = sp.row(align=True)
        right.alignment = "LEFT"                          # the status columns start at the divider (C4D)
        right.label(text="", icon="BLANK1")              # the dots (viewport over render) and the check are painted
        right.label(text="", icon="BLANK1")              # by _draw_status and clicked through om_select / om_paint:
                                                         # a button would take the mouse and stop a drag down the list
        if ob.type == "CAMERA":                            # the camera's view switch: filled while looking through it
            right.operator("blenda4d.om_look_through", text="", emboss=False,
                           icon="VIEW_CAMERA" if looking_through(bpy.context, ob) else "VIEW_CAMERA_UNSELECTED").name = ob.name
        for icon, mat, slot in _tags(ob):
            if mat is not None and OM_TAG_BUTTON:
                OM_TAG_BUTTON[0](right, ob, slot, mat)
            elif mat is not None:
                right.label(text="", icon_value=right.icon(mat))
            elif isinstance(slot, str) and OM_TAG_PICK:
                OM_TAG_PICK[0](right, ob, slot, icon)
            else:
                right.label(text="", icon=icon)
        for _ in range(tag_room - len(_tags(ob)) - (ob.type == "CAMERA")):
            right.label(text="", icon="BLANK1")


def _big_view(context):
    views = [a for a in context.screen.areas if a.type == "VIEW_3D" and len(a.spaces)]
    if len(views) > 1:                                     # four views: the Perspective one, the view a render shows
        from . import build
        return build._persp(context.screen)
    return views[0] if views else None


def _region_3d(area):
    """The 3D view's view data, or None while the area is being changed (it can have no editor then)."""
    if area is None or not len(area.spaces):
        return None
    space = area.spaces.active
    return getattr(space, "region_3d", None) if space is not None and space.type == "VIEW_3D" else None


def looking_through(context, ob):
    """True while the viewport looks through this camera."""
    if context.scene.camera != ob:
        return False
    from . import magnify
    area = _big_view(context)
    r3 = _region_3d(area)
    return r3 is not None and r3.view_perspective == "CAMERA" and not magnify.on(area.spaces.active)


class BLENDA4D_OT_om_look_through(bpy.types.Operator):
    bl_idname = "blenda4d.om_look_through"
    bl_label = "Look Through Camera"
    bl_description = "Look through this camera in the viewport; click again to go back to the free view"
    bl_options = {"REGISTER", "UNDO"}
    name: bpy.props.StringProperty(options={"SKIP_SAVE"})

    def execute(self, context):
        ob = context.scene.objects.get(self.name)
        area = _big_view(context)
        if ob is None or ob.type != "CAMERA" or area is None:
            return {"CANCELLED"}
        r3 = _region_3d(area)
        if r3 is None:
            return {"CANCELLED"}
        from . import viewmenus
        if looking_through(context, ob):
            viewmenus.back_to_editor(area, area.spaces.active)    # back where the editor camera was left
        else:
            viewmenus.look_through(area, area.spaces.active, ob)  # orbit / pan / zoom now move this camera
        for a in context.screen.areas:
            a.tag_redraw()
        return {"FINISHED"}


# --- Attribute Manager ------------------------------------------------------------------------------------------
TABS_COMMON = [("BASIC", "Basic", ""), ("COORD", "Coord.", ""), ("OBJECT", "Object", "")]


def _page_tabs(ob):
    from . import kinds
    k = kinds.kind_of(ob)
    if k:
        own = [(t[0], t[1], "") for t in kinds.KINDS[k]["tabs"]]
        if own and kinds.KINDS[k].get("own_tabs_only"):
            return own
        return (TABS_COMMON[:2] + own if own else list(TABS_COMMON)) + _octane_tab()
    tabs = list(TABS_COMMON)
    if ob.type == "MESH":
        tabs.append(("PHONG", "Phong", ""))
        from . import uvtab
        if uvtab.editor(getattr(bpy.context, "screen", None)) is not None:
            tabs.append(("UV", "UV", ""))
    if ob.type == "CAMERA" and CAMERA_PAGES:
        tabs += CAMERA_TABS
    if ob.type == "LIGHT":
        tabs[2] = ("OBJECT", "General", "")
        tabs += [("DETAILS", "Details", ""), ("SHADOW", "Shadow", "")]
    return tabs + _octane_tab()


def _octane_tab():
    return [("OCTANE", "Octane", "")] if OCTANE_PAGE and bpy.context.scene.render.engine == "octane" else []


def _tab_items(self, context):
    ob = context.view_layer.objects.active if context else None
    return _page_tabs(ob) if ob is not None else TABS_COMMON


def _vec(col, data, prop, label, axes="XYZ"):
    sub = col.column(align=True)
    for i, a in enumerate(axes):
        sub.prop(data, prop, index=i, text=f"{label} . {a}")


def page_basic(col, ob):
    col.prop(ob, "name", text="Name")
    col.prop(ob, "b4d_vis_editor", text="Visible in Editor")
    col.prop(ob, "b4d_vis_render", text="Visible in Renderer")
    col.separator()
    col.prop(ob, "color", text="Display Color")
    col.prop(ob, "show_in_front", text="X-Ray")


def page_coord(col, ob):
    _vec(col, ob, "b4d_pos", "P")
    col.separator()
    _vec(col, ob, "b4d_scale", "S")
    col.separator()
    _vec(col, ob, "b4d_rot", "R")
    col.separator()
    col.prop(ob, "rotation_mode", text="Rotation Order")


def prim_kind(ob):
    from . import primitives
    k = ob.get("b4d_type")
    return k if k in primitives.PRIMS else None


def _generator(ob):
    return next((m for m in ob.modifiers if m.type == "NODES" and m.node_group and m.node_group.name.startswith("Blenda ")), None)


# rows a page greys out until the switch they belong to is on
_NEEDS = {"Fillet Radius": "Fillet", "Fillet Segments": "Fillet", "Fillet Subdivision": "Fillet", "From": "Slice", "To": "Slice",
          "Regular Grid": "Slice", "Width": None, "Radius Y": None}


def page_primitive(col, ob, kind):
    """A primitive's Object page: its generator's settings, in order, with Blender's own fields."""
    from . import primitives
    mod = _generator(ob)
    if mod is None or mod.node_group is None:
        col.label(text="This object's generator is missing")
        return
    items = mod.node_group.interface.items_tree
    values = {}
    for sname, stype, _default, _key in primitives.PRIMS[kind][2]:
        if sname not in items:
            continue
        try:
            owner, attr = primitives.input_slot(mod, items[sname].identifier)
        except KeyError:
            continue
        values[sname] = (owner, attr)
    for sname, stype, _default, _key in primitives.PRIMS[kind][2]:
        if sname not in values:
            continue
        owner, attr = values[sname]
        row = col.row(align=True)
        switch = _NEEDS.get(sname)
        if switch and switch in values:
            o2, a2 = values[switch]
            try:
                row.active = bool(getattr(o2, a2))
            except (AttributeError, TypeError):
                pass
        if stype == "VECTOR":
            sub = col.column(align=True)
            for i, axis in enumerate("XYZ"):
                sub.prop(owner, attr, index=i, text=f"{sname} . {axis}")
        else:
            row.prop(owner, attr, text=sname)


VOLUME_LOOK = (("Density", "Density"), ("Color", "Color"), ("Anisotropy", "Light Scattering"),
               ("Absorption Color", "Absorption Color"), ("Emission Strength", "Emission"),
               ("Emission Color", "Emission Color"), ("Blackbody Intensity", "Glow"), ("Temperature", "Glow Temperature"))


def _volume_shader(ob):
    """The volume shader the object renders with: the first Principled Volume (or Volume Scatter) on its material's
    Volume input, else anywhere in the material."""
    mat = ob.active_material
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return mat, None
    nodes = mat.node_tree.nodes
    for kind in ("PRINCIPLED_VOLUME", "VOLUME_SCATTER"):
        node = next((n for n in nodes if n.type == kind), None)
        if node is not None:
            return mat, node
    return mat, None


def _volume_look(col, ob):
    """Top-level controls for how the volume looks, plus its render detail."""
    mat, node = _volume_shader(ob)
    col.label(text="Look")
    if node is None:
        col.label(text="Add a volume material to set density and colour" if mat is None
                  else f"{mat.name} has no volume shader")
    else:
        for name, label in VOLUME_LOOK:
            sock = node.inputs.get(name)
            if sock is None or not hasattr(sock, "default_value"):
                continue
            if sock.is_linked:
                row = col.row()
                row.active = False
                row.label(text=f"{label}: set by the material's nodes")
            else:
                col.prop(sock, "default_value", text=label)
    col.prop(ob.data.render, "step_size", text="Detail (Step Size)")


def page_volume(col, ob):
    """A volume (OpenVDB) object: its file, sequence, viewport display and render quality, and the grids it holds.
    The Look rows are the volume material's own shader inputs, so changing them here changes the material."""
    d = ob.data
    _volume_look(col, ob)
    col.separator()
    col.prop(d, "filepath", text="File")
    col.prop(d, "is_sequence", text="Sequence")
    if d.is_sequence:
        col.prop(d, "frame_start", text="Start Frame")
        col.prop(d, "frame_offset", text="Offset")
        col.prop(d, "sequence_mode", text="Mode")
    col.separator()
    col.label(text="Viewport")
    col.prop(d.display, "density", text="Density")
    col.prop(d.display, "wireframe_type", text="Wireframe")
    if d.display.wireframe_type in ("BOXES", "POINTS"):
        col.prop(d.display, "wireframe_detail", text="Detail")
    col.prop(d.display, "interpolation_method", text="Interpolation")
    col.separator()
    col.label(text="Render")
    col.prop(d.render, "space", text="Space")
    col.prop(d.render, "precision", text="Precision")
    col.prop(d.render, "clipping", text="Clipping")
    col.separator()
    try:                                                  # reading the file's grid list is cheap: names and types only
        if d.filepath and not d.grids.is_loaded:
            d.grids.load()
        grids = [(g.name, g.data_type) for g in d.grids]
    except (AttributeError, RuntimeError, ReferenceError):
        grids = []
    if grids:
        col.label(text="Grids")
        for name, kind in grids:
            col.label(text=f"{name}    {kind.replace('_', ' ').title()}", icon="DOT")
    elif d.filepath:
        col.label(text="Grids: none loaded (check the file path)")


def page_object(col, ob):
    from . import kinds
    d = ob.data
    kind = prim_kind(ob)
    if kind:
        return page_primitive(col, ob, kind)
    if ob.type == "MESH":
        col.label(text=f"Points: {len(d.vertices)}    Polygons: {len(d.polygons)}")
        _vec(col, ob, "b4d_size", "Size")
    elif ob.type == "LIGHT":
        col.prop(d, "color", text="Color")
        col.prop(d, "energy", text="Intensity")
        col.prop(d, "type", text="Type")
        col.prop(d, "use_shadow", text="Shadow")
        if d.type == "AREA":
            col.prop(d, "shape", text="Area Shape")
            col.prop(d, "size", text="Size")
    elif ob.type == "CAMERA":
        col.prop(d, "type", text="Projection")
        col.prop(d, "lens", text="Focal Length")
        col.prop(d, "sensor_width", text="Sensor Size")
        col.prop(d, "clip_start", text="Near Clipping")
        col.prop(d, "clip_end", text="Far Clipping")
    elif ob.type == "EMPTY":
        col.prop(ob, "empty_display_type", text="Display")
        col.prop(ob, "empty_display_size", text="Radius")
    elif ob.type == "CURVE" and "spline" in kinds.KINDS:          # the splines module draws any curve's page
        kinds.KINDS["spline"]["pages"]["OBJECT"](col, ob)
    elif ob.type == "CURVE":
        col.prop(d, "resolution_u", text="Intermediate Points")
        col.prop(d, "dimensions", text="Type")
        col.prop(d, "extrude", text="Extrude")
        col.prop(d, "bevel_depth", text="Thickness")
    elif ob.type == "FONT" and FONT_PAGE:
        FONT_PAGE[0](col, ob)
    elif ob.type == "FONT":
        col.prop(d, "body", text="Text")
        col.prop(d, "size", text="Height")
        col.prop(d, "extrude", text="Depth")
        col.prop(d, "align_x", text="Align")
    elif ob.type == "VOLUME":
        page_volume(col, ob)
    else:
        col.label(text="No settings for this object type yet")


def page_phong(col, ob):
    from . import primitives
    mod = _generator(ob) if prim_kind(ob) else None
    items = mod.node_group.interface.items_tree if mod is not None and mod.node_group else {}
    slots = {}
    for name in (primitives.PHONG_LIMIT, primitives.PHONG_ANGLE):
        if name in items:
            try:
                slots[name] = primitives.input_slot(mod, items[name].identifier)
            except KeyError:
                pass
    if slots:
        if primitives.PHONG_LIMIT in slots:
            col.prop(*slots[primitives.PHONG_LIMIT], text="Angle Limit")
        if primitives.PHONG_ANGLE in slots:
            row = col.row()
            if primitives.PHONG_LIMIT in slots:
                row.active = bool(getattr(*slots[primitives.PHONG_LIMIT]))
            row.prop(*slots[primitives.PHONG_ANGLE], text="Phong Angle")
        col.separator()
    col.operator("object.shade_smooth", text="Smooth")
    col.operator("object.shade_flat", text="Flat")
    col.operator("object.shade_auto_smooth", text="Smooth by Angle")


def page_uv(col, ob):
    from . import uvtab
    uvtab.page(col, bpy.context, ob)


def page_light_details(col, ob):
    d = ob.data
    col.prop(d, "diffuse_factor", text="Diffuse")
    col.prop(d, "specular_factor", text="Specular")
    col.prop(d, "volume_factor", text="Volume")
    if d.type == "SPOT":
        col.prop(d, "spot_size", text="Outer Angle")
        col.prop(d, "spot_blend", text="Falloff")


def page_light_shadow(col, ob):
    d = ob.data
    col.prop(d, "use_shadow", text="Cast Shadows")
    col.prop(d, "shadow_soft_size", text="Shadow Radius")


PAGES = {"BASIC": page_basic, "COORD": page_coord, "OBJECT": page_object, "PHONG": page_phong, "UV": page_uv, "OCTANE": lambda col, ob: None,
         "DETAILS": page_light_details, "SHADOW": page_light_shadow}


class BLENDA4D_PT_attributes(roles.RolePanel, bpy.types.Panel):
    bl_label = "Attributes"
    role = "ATTRIBUTES"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        manager_title(layout, "Attributes", right_tabs="b4d_right_tab")
        if wm.b4d_right_tab == "VARIATIONS":
            return draw_variations(layout, context)
        bar = layout.row(align=True)
        bar.label(text="", icon="COLLAPSEMENU")
        menus.menu_bar(bar, AM_MENUS, avail=menus.panel_width(1.0, _icon_px()))
        ob = context.view_layer.objects.active
        layout.separator(factor=0.3)
        from . import phong
        if phong.draw_page(layout, context):              # the Phong Break Selection tool's options
            return
        fn = AM_SUBJECTS.get(wm.b4d_am_subject.partition(":")[0])
        if fn is not None and wm.b4d_am_subject.startswith(("MAT:", "OTAG:")) and fn(layout, context, ob):
            return                                         # a material picked in the Material Manager
        if ob is None:
            layout.label(text="Nothing selected")
            return
        if fn is not None and fn(layout, context, ob):
            return
        from . import sculpttools
        if sculpttools.draw_page(layout, context, ob):     # sculpting: the brush
            return
        head = layout.row(align=True)
        kind = prim_kind(ob)
        from . import primitives
        from . import kinds
        own = kinds.kind_of(ob)
        label = (kinds.KINDS[own]["label"] if own else
                 (primitives.PRIMS[kind][1] + " Object") if kind else TYPE_LABEL.get(ob.type, "Object"))
        head.label(text=f"{label} [{ob.name}]", **type_icon_kw(ob))
        if len(_page_tabs(ob)) > 5:                       # many pages: tabs wrap onto two rows of four
            tg = layout.grid_flow(row_major=True, columns=4, even_columns=True, align=True)
            for key, label, _d in _page_tabs(ob):
                tg.prop_enum(wm, "b4d_am_tab", key, text=label)
        else:
            layout.row(align=True).prop(wm, "b4d_am_tab", expand=True)
        tab = wm.b4d_am_tab
        tabs = [t[0] for t in _page_tabs(ob)]
        if tab not in tabs:
            tab = "OBJECT" if "OBJECT" in tabs else tabs[min(2, len(tabs) - 1)]
        layout.separator(factor=0.5)
        page = kinds.KINDS[own]["pages"].get(tab) if own else None
        if tab == "OCTANE" and OCTANE_PAGE:
            page = OCTANE_PAGE[0]
        if page is None and ob.type == "CAMERA" and tab in CAMERA_PAGES:
            page = CAMERA_PAGES[tab]
        title = (kinds.KINDS[own]["titles"].get(tab) if own else None) or (
            CAMERA_TITLES.get(tab) if ob.type == "CAMERA" else None) or {
            "BASIC": "Basic Properties", "COORD": "Coordinates", "OBJECT": "Object Properties", "PHONG": "Phong",
            "DETAILS": "Details", "SHADOW": "Shadow"}.get(tab, dict((t[0], t[1]) for t in _page_tabs(ob)).get(tab, tab))
        layout.label(text=title)
        col = layout.column()
        col.use_property_split = True
        col.use_property_decorate = True
        (page or PAGES.get(tab, lambda c, o: None))(col, ob)


def draw_variations(layout, context):
    layout.label(text="Variations of this scene appear here.")
    layout.operator("blenda4d.noop", text="New Variation", icon="ADD")


# --- Material Manager --------------------------------------------------------------------------------------------
class BLENDA4D_OT_new_material(bpy.types.Operator):
    bl_idname = "blenda4d.new_material"
    bl_label = "New Material"
    bl_description = "Make a new material"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        mat = bpy.data.materials.new("Mat")
        mat.use_nodes = True
        context.window_manager.b4d_material = mat.name
        return {"FINISHED"}


class BLENDA4D_OT_mat_pick(bpy.types.Operator):
    bl_idname = "blenda4d.mat_pick"
    bl_label = "Material"
    bl_description = "Select this material; Cmd/Ctrl-click adds or takes one away, Shift-click selects a range"
    name: bpy.props.StringProperty()

    def invoke(self, context, event):
        mat = bpy.data.materials.get(self.name)
        if mat is None:
            return {"CANCELLED"}
        from . import matman, matpage
        if roles.role(context.area) == "MATERIALS":
            matman.click_select(context, mat, event)       # Cmd/Ctrl adds or takes away, Shift selects a range
        else:
            context.window_manager.b4d_material = mat.name
        cur = matman.current(context)
        if cur is not None:
            matpage.show(context, cur)                     # the Attribute Manager shows the material
        matman._tag_redraw()
        return {"FINISHED"}


class BLENDA4D_OT_mat_tag(bpy.types.Operator):
    bl_idname = "blenda4d.mat_tag"
    bl_label = "Material Tag"
    bl_description = "Give the selected objects the current material"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        mat = bpy.data.materials.get(context.window_manager.b4d_material) or bpy.data.materials.new("Mat")
        for ob in context.selected_objects:
            if hasattr(ob.data, "materials"):
                ob.data.materials.append(mat)
        return {"FINISHED"}


class BLENDA4D_PT_materials(roles.RolePanel, bpy.types.Panel):
    bl_label = "Materials"
    role = "MATERIALS"

    def draw(self, context):
        layout = self.layout
        manager_title(layout, "Materials")
        bar = layout.row(align=True)
        bar.label(text="", icon="COLLAPSEMENU")
        menus.menu_bar(bar, MM_MENUS, avail=menus.panel_width(1.0, _icon_px()))
        matman.draw_tools(layout, context)
        layout.separator(factor=0.4)
        matman.draw_materials(layout, context)


# --- Asset Browser (layout per the approved mock-up; Blender's asset libraries underneath) ------------------------
AB_TIPS = {"AUTO": "Assets that suit what is selected", "ALL": "Every asset", "MODELS": "Objects to add to the scene",
           "MATERIALS": "Materials", "MEDIA": "Images, movies and sounds", "NODES": "Node groups",
           "OPERATORS": "Saved commands", "SCENES": "Whole scenes and templates", "PRESETS": "Saved settings",
           "HDRIS": "Environment images that light the scene", "POSES": "Character poses", "BRUSHES": "Sculpt and paint brushes"}
AB_TABS = (("AUTO", "Auto"), ("ALL", "All"), ("MODELS", "Models"), ("MATERIALS", "Materials"), ("MEDIA", "Media"), ("NODES", "Nodes"),
           ("OPERATORS", "Operators"), ("SCENES", "Scenes"), ("PRESETS", "Presets"), ("HDRIS", "HDRIs"), ("POSES", "Poses"), ("BRUSHES", "Brushes"))
AB_GREY = {"MEDIA", "OPERATORS", "PRESETS"}
AB_SMART = (("FUND", "Favorites", True), ("VIEWZOOM", "Featured Content", False), ("BOOKMARKS", "Keywords", True),
            ("NEWFOLDER", "New Assets", False), ("FILE_FOLDER", "Other", False), ("TIME", "Recently Created", True), ("TIME", "Recently Used", True))
AB_MENUS = [menus.simple_menu(n, [I("…")], "ab") for n in ("Create", "Edit", "View", "Libraries")]


class BLENDA4D_PT_assets(roles.RolePanel, bpy.types.Panel):
    bl_label = "Asset Browser"
    role = "ASSETS"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        from . import kinds
        if "ASSETS" in kinds.PANELS:
            return kinds.PANELS["ASSETS"](layout, context)
        manager_title(layout, "Asset Browser")
        bar = layout.row(align=True)
        menus.menu_bar(bar, AB_MENUS)
        grid = layout.grid_flow(row_major=True, columns=6, even_columns=True, align=True)
        for key, label in AB_TABS:
            cell = grid.row(align=True)
            cell.enabled = key not in AB_GREY
            cell.prop_enum(wm, "b4d_ab_tab", key, text=label)
        nav = layout.row(align=True)
        nav.operator("blenda4d.noop", text="", icon="BACK")
        nav.operator("blenda4d.noop", text="", icon="FORWARD")
        nav.operator("blenda4d.noop", text="", icon="HOME")
        nav.operator("blenda4d.noop", text="", icon="SOLO_OFF")
        nav.prop(wm, "b4d_ab_search", text="", icon="VIEWZOOM")
        split = layout.split(factor=0.48)
        tree = split.column(align=True)
        tree.label(text="Smart Searches", icon="DISCLOSURE_TRI_DOWN")
        for icon, label, ok in AB_SMART:
            r = tree.row(align=True)
            r.enabled = ok
            r.separator(factor=2.0)
            r.label(text=label, icon=icon)
        tree.separator()
        for lib in context.preferences.filepaths.asset_libraries:
            r = tree.row(align=True)
            r.label(text=lib.name, icon="FILE_FOLDER")
        right = split.column()
        right.label(text="Home")
        homes = (("MATERIAL", "Materials", "MATERIALS"), ("MESH_CUBE", "Models", "MODELS"), ("WORLD", "HDRIs", "HDRIS"),
                 ("FILE_BLEND", "Templates", "SCENES"), ("ARMATURE_DATA", "Motion Capture", "POSES"), ("NODETREE", "Nodes", "NODES"),
                 ("BRUSH_DATA", "Brushes", "BRUSHES"), ("ASSET_MANAGER", "All Assets", "ALL"))
        hg = right.grid_flow(row_major=True, columns=2, even_columns=True)
        for icon, label, tab in homes:
            b = hg.column(align=True)
            b.scale_y = 2.2
            b.prop_enum(wm, "b4d_ab_tab", tab, text=label, icon=icon)


classes = (BLENDA4D_OT_om_look_through, BLENDA4D_OT_size_step, BLENDA4D_OT_om_delete, BLENDA4D_OT_om_solo, BLENDA4D_OT_om_scroll_active, BLENDA4D_OT_om_select, BLENDA4D_OT_om_box, BLENDA4D_OT_om_divider, BLENDA4D_OT_om_drag, BLENDA4D_OT_om_rename, BLENDA4D_OT_om_fold, BLENDA4D_OT_om_expand, BLENDA4D_OT_group, BLENDA4D_OT_new_material,
           BLENDA4D_OT_mat_pick, BLENDA4D_OT_mat_tag, *OM_MENUS, *AM_MENUS, *MM_MENUS, *AB_MENUS,
           *(menus.make_more(m) for m in (OM_MENUS, AM_MENUS, MM_MENUS)),
           BLENDA4D_PT_objects, BLENDA4D_PT_om_bar, BLENDA4D_PT_om_head, BLENDA4D_PT_attributes, BLENDA4D_PT_materials, BLENDA4D_PT_assets)


# --- the visibility dots: 0 default (as the parent), 1 on (always shown), 2 off (hidden) -----------------------------
_VIS_KEY = {"hide_viewport": "_b4d_vis_e", "hide_render": "_b4d_vis_r"}
VIS_STATES = ("default", "on", "off")


def vis_state(ob, attr):
    """The dot's state; an object Blenda never set reads from Blender's own switch (hidden = off)."""
    v = ob.get(_VIS_KEY[attr])
    return int(v) if v is not None else (2 if getattr(ob, attr) else 0)


def _hidden(ob, attr):
    s = vis_state(ob, attr)
    if s == 2 or (not ob.get("_b4d_enabled", True) and _switch_kind(ob) is None):
        return True                                   # switched off: only lights, cameras, nulls are hidden for it
    if s == 1:
        return False
    return _hidden(ob.parent, attr) if ob.parent is not None else False


def apply_vis(ob, attr):
    """Set Blender's switch on the object and everything under it from the dots: a default dot follows its parent."""
    tree = [ob, *ob.children_recursive]
    for o in tree:                                   # keep each object's own state before any switch changes
        if o.get(_VIS_KEY[attr]) is None:
            o[_VIS_KEY[attr]] = vis_state(o, attr)
    for o in tree:
        if attr == "hide_render" and "b4d_consumed" in o:     # a generator's input stays out of renders
            continue
        h = _hidden(o, attr)
        if getattr(o, attr) != h:
            setattr(o, attr, h)


def _vis_get(attr):
    def get(self):
        return vis_state(self, attr)
    return get


def _vis_set(attr):
    def put(self, v):
        self[_VIS_KEY[attr]] = int(v)
        apply_vis(self, attr)
    return put


def set_vis(ob, attr, state):
    ob[_VIS_KEY[attr]] = state
    apply_vis(ob, attr)


_enabling = [False]


OFF_MOD = "B4D Switched Off"        # not "Blenda ...": those names mark an object's own generator


def _switch_kind(ob):
    """How the check switches this object off without hiding it (a hidden object cannot be picked in the Object
    Manager): "self" for deformers (they stop working on their own), "geometry" for objects drawn (generators too)
    from geometry (an empty-geometry step at the end of their modifiers), None for the rest (lights, cameras, nulls:
    hidden as before)."""
    from . import deformers, generators
    if deformers.is_deformer(ob):                         # its effect stops; its cage stays in view, as in C4D
        return "self"
    if ob.get("b4d_type") in generators.MOD_KINDS:        # Subdivision Surface, Reduce, Remesh: their effect stops
        return "self"                                     # (generators.enabled), what is under them shows as it is
    if ob.type in ("MESH", "CURVE", "FONT", "SURFACE", "META", "CURVES", "POINTCLOUD", "VOLUME", "GREASEPENCIL"):
        return "geometry"
    return None


def _off_group():
    ng = bpy.data.node_groups.get(OFF_MOD)
    if ng is None:
        ng = bpy.data.node_groups.new(OFF_MOD, "GeometryNodeTree")
        ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        ng.nodes.new("NodeGroupInput"); ng.nodes.new("NodeGroupOutput")     # nothing wired: no geometry out
    return ng


def apply_switch(ob):
    """The check's effect on the object itself (see _switch_kind)."""
    on = bool(ob.get("_b4d_enabled", True))
    if _switch_kind(ob) != "geometry":
        return
    m = ob.modifiers.get(OFF_MOD)
    if on:
        if m is not None:
            ob.modifiers.remove(m)
        return
    if m is None:
        try:
            m = ob.modifiers.new(OFF_MOD, "NODES")
        except (RuntimeError, TypeError):
            return
        m.node_group = _off_group()
        m.show_in_editmode = False
    while ob.modifiers.find(m.name) < len(ob.modifiers) - 1:     # last, after everything else
        try:
            ob.modifiers.move(ob.modifiers.find(m.name), len(ob.modifiers) - 1)
        except (AttributeError, RuntimeError):
            break


@bpy.app.handlers.persistent
def _switch_refresh(*_args):
    """Files saved while a switched-off object was hidden for it: it shows the new way (selectable in the Object
    Manager, drawn as nothing)."""
    try:
        for ob in bpy.data.objects:
            if not ob.get("_b4d_enabled", True):
                apply_switch(ob)
                for attr in _VIS_KEY:
                    apply_vis(ob, attr)
    except (AttributeError, ReferenceError, RuntimeError):
        pass


def _enabled_set(self, v):
    if not _enabling[0] and self.select_get():           # the check of a selected object sets every selected object
        _enabling[0] = True
        try:
            for o in bpy.context.selected_objects:
                if o != self:
                    o.b4d_enabled = v
        finally:
            _enabling[0] = False
    self["_b4d_enabled"] = bool(v)
    apply_switch(self)
    for attr in _VIS_KEY:
        apply_vis(self, attr)
    self.update_tag()


class BLENDA4D_OT_om_dot(bpy.types.Operator):
    bl_idname = "blenda4d.om_dot"
    bl_label = "Visibility"
    bl_options = {"UNDO", "INTERNAL"}
    name: bpy.props.StringProperty(options={"SKIP_SAVE"})
    render: bpy.props.BoolProperty(options={"SKIP_SAVE"})
    both: bpy.props.BoolProperty(options={"SKIP_SAVE"})       # Alt: both dots (C4D; from Marden's patch)

    @classmethod
    def description(cls, context, props):
        return ("Visibility: the upper dot is the viewport, the lower dot renders. Grey follows the object above it, "
                "green always shows it, red hides it; click a dot to step through them, Alt+click sets both "
                "(Blender: Hide in Viewport, Disable in Renders)")

    def invoke(self, context, event):
        """A click on the upper dot steps the viewport's, on the lower dot the render's."""
        r = context.region
        if roles.role(context.area) == "OBJECTS" and r is not None and r.type == "WINDOW":
            y = r.view2d.region_to_view(0, event.mouse_y - r.y)[1]
            h = row_height()
            self.render = ((-y - rows_top() * h) / h) % 1.0 >= 0.5
        return self.execute(context)

    def execute(self, context):
        ob = bpy.data.objects.get(self.name)
        if ob is None:
            return {"CANCELLED"}
        attr = "hide_render" if self.render else "hide_viewport"
        state = (vis_state(ob, attr) + 1) % 3
        group = [o for o in context.selected_objects] if ob.select_get() else []
        for o in (group if len(group) > 1 else [ob]):      # a dot of a selected object sets every selected object
            for a in (tuple(_VIS_KEY) if self.both else (attr,)):
                set_vis(o, a, state)
        for a in context.screen.areas if context.screen else ():
            a.tag_redraw()
        return {"FINISHED"}


classes += (BLENDA4D_OT_om_dot,)


class BLENDA4D_OT_drag_copy(bpy.types.Operator):
    """C4D's Move tool: Ctrl/Cmd-drag duplicates. Armed while Ctrl or Cmd is held over the viewport (a window-level
    watcher hears the press before the move gizmo does): at the press the selection is copied, with everything under
    it, and Blender's own move then carries the copy. A press that moved nothing (a plain Ctrl/Cmd-click) removes the
    copy again."""
    bl_idname = "blenda4d.drag_copy"
    bl_label = "Drag a Copy"
    bl_options = {"INTERNAL"}

    @staticmethod
    def armed(context):
        if context.mode != "OBJECT" or not context.selected_objects:
            return False
        try:
            tool = context.workspace.tools.from_space_view3d_mode("OBJECT", create=False)
        except (AttributeError, TypeError):
            return False
        return tool is not None and tool.idname in ("builtin.move", "builtin.transform")

    def invoke(self, context, event):
        if not self.armed(context):
            return {"PASS_THROUGH"}
        self.copies, self.origs = [], []
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL", "PASS_THROUGH"}

    def _settle(self, context):
        """After the move: copies that did not move are taken back, the originals selected again."""
        if not self.copies:
            return
        try:
            still = all((c.matrix_world.translation - o.matrix_world.translation).length < 1e-6
                        for c, o in zip(self.copies, self.origs))
        except ReferenceError:
            self.copies = []
            return
        if still:
            doomed = set()

            def walk(o):
                doomed.add(o)
                for c in o.children:
                    walk(c)
            for c in self.copies:
                walk(c)
            for o in doomed:
                bpy.data.objects.remove(o, do_unlink=True)
            for o in context.view_layer.objects:
                if o is not None:
                    o.select_set(o in self.origs)
            if self.origs:
                context.view_layer.objects.active = self.origs[0]
        self.copies, self.origs = [], []

    def modal(self, context, event):
        held = event.oskey or event.ctrl
        if event.type == "LEFTMOUSE" and event.value == "PRESS" and held and not self.copies:
            area = context.area
            if area is None or area.type != "VIEW_3D" or not self.armed(context):
                return {"PASS_THROUGH"}
            sel = context.selected_objects
            tops = [o for o in sel if not any(_is_under(p, o) for p in sel if p != o)]
            act = context.view_layer.objects.active
            if act in tops:
                tops.remove(act)
                tops.insert(0, act)
            self.origs = tops
            self.saw_move = self.released = False
            self.copies = duplicate_tree(context, tops)
            return {"PASS_THROUGH"}                       # the move gizmo (or the tool's drag) now moves the copies
        if self.copies:
            moving = any(op.bl_idname.startswith("TRANSFORM_OT") for op in context.window.modal_operators)
            self.saw_move = getattr(self, "saw_move", False) or moving
            if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                self.released = True                      # a click: the move never started
            if not moving and (self.saw_move or getattr(self, "released", False)):
                self._settle(context)                     # the move has ended, or there was none: keep or take back
                self.saw_move = self.released = False
        if not held and event.type in {"OSKEY", "LEFT_CTRL", "RIGHT_CTRL", "MOUSEMOVE"} and not self.copies:
            return {"FINISHED", "PASS_THROUGH"}
        return {"PASS_THROUGH"}


classes += (BLENDA4D_OT_drag_copy,)


class BLENDA4D_OT_om_paint(bpy.types.Operator):
    bl_idname = "blenda4d.om_paint"
    bl_label = "Paint Visibility"
    bl_description = ("Drag down the dots or the checks to give every row you pass the same state as the first one "
                      "(the first row steps on, as a click would); with Alt both dots are painted")
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return roles.role(context.area) == "OBJECTS"

    def _cell(self, event):
        """(row index, column) under the mouse: column DOT_VIEW / DOT_RENDER / CHECK, or None off those columns."""
        r = self.region
        x = event.mouse_x - r.x
        u = _unit(r)
        v = r.view2d.region_to_view(0, event.mouse_y - r.y)[1]
        h = row_height()
        f = -v / h - rows_top()
        i = int(f // 1) if f >= 0 else -1
        if not 0 <= i < len(self.rows):
            return i, None
        if self.dx - 3 <= x < self.dx + u:
            return i, "DOT_RENDER" if f % 1.0 >= 0.5 else "DOT_VIEW"
        if self.dx + u <= x < self.dx + 2 * u:
            return i, "CHECK"
        return i, None

    def invoke(self, context, event):
        r = context.region
        if r is None or r.type != "WINDOW":
            return {"PASS_THROUGH"}
        self.region, self.rows = r, visible_rows(context)
        self.dx = status_x(context, r, self.rows)

        class E:                                          # where the button went down, not where the drag began
            mouse_x, mouse_y = event.mouse_prev_press_x, event.mouse_prev_press_y
        i, col = self._cell(E)
        if col is None:
            return {"PASS_THROUGH"}
        ob = self.rows[i][0]
        self.col = col if col == "CHECK" else "DOT_VIEW" if col == "DOT_VIEW" else "DOT_RENDER"
        self.both = (event.alt or _press_alt[0]) and col != "CHECK"
        if col == "CHECK":
            self.value = not ob.b4d_enabled
        else:
            attr = "hide_render" if col == "DOT_RENDER" else "hide_viewport"
            self.value = (vis_state(ob, attr) + 1) % 3
        self.done = set()
        self._apply(context, ob)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _apply(self, context, ob):
        if ob.name in self.done:
            return
        self.done.add(ob.name)
        if self.col == "CHECK":
            _enabling[0] = True                          # one row at a time here, not the whole selection
            try:
                ob.b4d_enabled = self.value
            finally:
                _enabling[0] = False
        elif self.both:
            for attr in _VIS_KEY:
                set_vis(ob, attr, self.value)
        else:
            set_vis(ob, "hide_render" if self.col == "DOT_RENDER" else "hide_viewport", self.value)
        for a in context.screen.areas:
            a.tag_redraw()

    def modal(self, context, event):
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            v = self.region.view2d.region_to_view(0, event.mouse_y - self.region.y)[1]
            f = -v / row_height() - rows_top()
            i = int(f // 1) if f >= 0 else -1
            if 0 <= i < len(self.rows):
                self._apply(context, self.rows[i][0])
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE" or event.type in {"ESC", "RIGHTMOUSE"}:
            return {"FINISHED"}
        return {"RUNNING_MODAL"}


classes += (BLENDA4D_OT_om_paint,)


def dots_kw(ob):
    from . import icons as _icons
    iv = _icons.icon(f"dots_{VIS_STATES[vis_state(ob, 'hide_viewport')]}_{VIS_STATES[vis_state(ob, 'hide_render')]}", "om")
    return {"icon_value": iv} if iv else {"icon": "HIDE_ON" if ob.hide_viewport else "HIDE_OFF"}


def register():
    for c in classes:
        bpy.utils.register_class(c)
    O, W = bpy.types.Object, bpy.types.WindowManager
    vis = [("DEFAULT", "Default", "As the object above it (shown at the top level)"), ("ON", "On", "Always shown"), ("OFF", "Off", "Hidden")]
    O.b4d_om_closed = bpy.props.BoolProperty(description='Whether the objects under this one are folded away in the Object Manager', default=False)
    O.b4d_enabled = bpy.props.BoolProperty(description='Switch the object on or off in the viewport and in renders', name="Enabled", get=lambda self: self.get("_b4d_enabled", True), set=_enabled_set)
    O.b4d_vis_editor = bpy.props.EnumProperty(description='Show or hide the object in the viewport (Blender: Hide in Viewport)', items=vis, get=_vis_get("hide_viewport"), set=_vis_set("hide_viewport"))
    O.b4d_vis_render = bpy.props.EnumProperty(description='Show or hide the object in renders (Blender: Disable in Renders)', items=vis, get=_vis_get("hide_render"), set=_vis_set("hide_render"))
    W.b4d_om_search = bpy.props.StringProperty(description='Show only objects whose name contains this', name="Search", options={"TEXTEDIT_UPDATE"})
    W.b4d_tag_sel = bpy.props.StringProperty(description="The selected material tags besides the one shown", options={"SKIP_SAVE"})
    W.b4d_om_divider = bpy.props.FloatProperty(name="Column Divider", description="Where the Object Manager's status "
                                               "columns start, in rows from the left (0: just past the longest name)", default=0.0, min=0.0)
    W.b4d_om_drop = bpy.props.StringProperty(description='Where a dragged object will be dropped', )
    W.b4d_om_zoom = bpy.props.FloatProperty(name="Size", description="Size of the Object Manager's names and icons, "
                                            "up to the largest that still fits the panel",
                                            default=0.0, min=0.0, max=100.0, subtype="PERCENTAGE", precision=0,
                                            update=_om_zoom)
    W.b4d_am_tab = bpy.props.EnumProperty(description='The page of settings the Attribute Manager shows', items=_tab_items, name="Page")
    W.b4d_right_tab = bpy.props.EnumProperty(description='Show the Attribute Manager or the Variations', items=[("ATTRIBUTES", "Attributes", "The selected object's, tag's or material's settings"),
                                                ("VARIATIONS", "Variations", "Versions of the scene to switch between")])
    W.b4d_material = bpy.props.StringProperty(description='The material selected in the Material Manager', )
    W.b4d_am_subject = bpy.props.StringProperty(description='What the Attribute Manager shows besides the object: a tag or a material', )      # what the Attribute Manager shows besides the object (a tag)
    W.b4d_ab_tab = bpy.props.EnumProperty(description='Which kind of asset the Asset Browser lists', items=[(k, l, AB_TIPS.get(k, f"Show {l.lower()}")) for k, l in AB_TABS], default="ALL")
    W.b4d_ab_search = bpy.props.StringProperty(description='Show only assets whose name contains this', name="Search")
    _add_keymap()
    if _switch_refresh not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_switch_refresh)
    from . import multiedit, fontpick
    multiedit.register()
    fontpick.register()
    _draw.append(bpy.types.SpaceProperties.draw_handler_add(_draw_rows, (), "WINDOW", "POST_PIXEL"))


_keymaps = []
_draw = []


def _draw_rows():
    """Row highlights in the Object Manager (selected, active, drop target), like Blender's own lists."""
    context = bpy.context
    if roles.role(context.area) != "OBJECTS":
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    region = context.region
    c = context.preferences.themes[0].user_interface.wcol_regular.inner_sel     # the theme's pressed-button colour
    drop = context.window_manager.b4d_om_drop
    h = row_height()
    rects = []
    active = context.view_layer.objects.active
    rows = visible_rows(context)
    i = 0
    while True:
        top = region.view2d.view_to_region(0, -(rows_top() + i) * h, clip=False)[1]
        bottom = region.view2d.view_to_region(0, -(rows_top() + i + 1) * h, clip=False)[1]   # zoomed rows are taller
        if bottom > region.height:           # above the visible part: skip on
            i += 1
            continue
        if top < 0:
            break
        if i % 2:                            # alternating dark and mid grey, to the bottom of the list (the selection
                                             # shows in the names' colour, as in C4D)
            rects.append((bottom, top, STRIPE))
        i += 1
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    if rects:
        gpu.state.blend_set("ADDITIVE")        # lightens the row behind the text instead of covering it
        for y0, y1, col in rects:
            batch = batch_for_shader(shader, "TRIS", {"pos": [(0, y0), (region.width, y0), (region.width, y1), (0, y1)]},
                                     indices=[(0, 1, 2), (0, 2, 3)])
            shader.uniform_float("color", col)
            batch.draw(shader)
        gpu.state.blend_set("NONE")
    _draw_tree(context, region, rows, drop, shader)
    _draw_swatches(context, region, rows)
    for ob, slot in picked_tags(context):                          # the selected tags: framed
        if ob not in [o for o, _d in rows]:
            continue
        i = [o for o, _d in rows].index(ob)
        k = next((n for n, t in enumerate(_tags(ob)) if t[1] is not None and t[2] == slot), None)
        if k is not None:
            u = _unit(region)
            x0 = tag_cell(context, region, rows, ob, k)[0]
            b, t = _row_y(region, i)
            gpu.state.blend_set("ALPHA")
            shader.uniform_float("color", (1.0, 0.77, 0.18, 1.0))
            batch_for_shader(shader, "LINE_LOOP", {"pos": [(x0, b + 1), (x0 + u - 1, b + 1), (x0 + u - 1, t - 1), (x0, t - 1)]}).draw(shader)
            gpu.state.blend_set("NONE")
    dx = divider_x(context, region, rows) - 2 * context.preferences.system.ui_scale
    gpu.state.blend_set("ALPHA")
    _rect(shader, dx, 0, dx + max(1.0, context.preferences.system.ui_scale), region.height, (0.0, 0.0, 0.0, 0.35))
    gpu.state.blend_set("NONE")
    if _box:
        x0, x1 = sorted((_box[0], _box[2]))
        y0, y1 = sorted((_box[1], _box[3]))
        gpu.state.blend_set("ALPHA")
        _rect(shader, x0, y0, x1, y1, (1.0, 1.0, 1.0, 0.08))
        shader.uniform_float("color", (1.0, 1.0, 1.0, 0.6))
        batch_for_shader(shader, "LINE_LOOP", {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}).draw(shader)
        gpu.state.blend_set("NONE")
    if drop:
        _draw_drop(context, region, rows, drop, shader)


_swatch_tex = {}             # material name -> (pixel key, GPU texture) for the tag swatches


def _swatch_pixels(mat):
    """(width, height, flat RGBA floats) of the material's picture: the renderer's ball, else Blender's preview icon."""
    import numpy as np
    from . import matman
    ball = next((b for fn in matman.BALLS for b in (fn(mat),) if b is not None), None)
    if ball is not None:
        h, w = ball.shape[:2]
        return w, h, np.ascontiguousarray(ball, dtype=np.float32).reshape(-1)
    p = mat.preview_ensure() if hasattr(mat, "preview_ensure") else mat.preview
    if p is None:
        return None
    w, h = p.icon_size
    if not w or not h:
        return None
    a = np.empty(w * h * 4, np.float32)
    p.icon_pixels_float.foreach_get(a)
    if not a[3::4].any():
        return None
    return w, h, a


def _swatch(mat):
    import gpu
    px = _swatch_pixels(mat)
    if px is None:
        return None
    w, h, a = px
    key = (w, h, float(a[::97].sum()))
    old = _swatch_tex.get(mat.name)
    if old and old[0] == key:
        return old[1]
    tex = gpu.types.GPUTexture((w, h), format="RGBA16F", data=gpu.types.Buffer("FLOAT", w * h * 4, a))
    _swatch_tex[mat.name] = (key, tex)
    return tex


def _draw_swatches(context, region, rows):
    """The material tags after each row, painted here (a picture in the panel would be a Blender drag source and take
    the mouse away from the Object Manager's own click and drag)."""
    import gpu
    from gpu_extras.batch import batch_for_shader
    u = _unit(region)
    pad = 0.12 * u
    flat = gpu.shader.from_builtin("UNIFORM_COLOR")
    img = gpu.shader.from_builtin("IMAGE")
    gpu.state.blend_set("ALPHA")
    sx = status_x(context, region, rows)
    lines = []
    for i, (ob, _d) in enumerate(rows):
        b, t = _row_y(region, i)
        if t < 0 or b > region.height:
            continue
        cy = (b + t) / 2
        for attr, dy in (("hide_viewport", 0.17), ("hide_render", -0.17)):     # C4D's stacked visibility dots
            col = DOT_COLORS[vis_state(ob, attr)]
            _disc(flat, sx + 0.5 * u, cy + dy * u, 0.12 * u, col)
        cx = sx + 1.5 * u
        if ob.b4d_enabled:                                # the check, or a red X when switched off
            pts = [(cx - 0.22 * u, cy), (cx - 0.06 * u, cy - 0.17 * u), (cx - 0.06 * u, cy - 0.17 * u), (cx + 0.24 * u, cy + 0.2 * u)]
            lines.append((pts, CHECK_ON))
        else:
            h = 0.17 * u
            lines.append(([(cx - h, cy - h), (cx + h, cy + h), (cx - h, cy + h), (cx + h, cy - h)], CHECK_OFF))
        for k, (_icon, mat, _slot) in enumerate(_tags(ob)):
            if mat is None:
                continue
            x0, x1 = tag_cell(context, region, rows, ob, k)
            s = min(x1 - x0, t - b) - 2 * pad
            cx, cy = (x0 + x1) / 2, (b + t) / 2
            q = [(cx - s / 2, cy - s / 2), (cx + s / 2, cy - s / 2), (cx + s / 2, cy + s / 2), (cx - s / 2, cy + s / 2)]
            tex = _swatch(mat)
            if tex is not None:
                img.bind()
                img.uniform_sampler("image", tex)
                batch_for_shader(img, "TRI_FAN", {"pos": q, "texCoord": [(0, 0), (1, 0), (1, 1), (0, 1)]}).draw(img)
            else:
                c = mat.diffuse_color
                flat.uniform_float("color", (c[0], c[1], c[2], 1.0))
                batch_for_shader(flat, "TRI_FAN", {"pos": q}).draw(flat)
    gpu.state.line_width_set(max(1.5, 2.0 * context.preferences.system.ui_scale))
    for pts, col in lines:
        flat.uniform_float("color", col)
        batch_for_shader(flat, "LINES", {"pos": pts}).draw(flat)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")


DOT_COLORS = {0: (0.42, 0.42, 0.42, 1.0), 1: (0.30, 0.82, 0.32, 1.0), 2: (0.90, 0.26, 0.20, 1.0)}   # default / on / off
CHECK_ON = (0.96, 0.60, 0.16, 1.0)
CHECK_OFF = (0.90, 0.26, 0.20, 1.0)


def _disc(shader, x, y, r, col):
    import math
    from gpu_extras.batch import batch_for_shader
    pts = [(x, y)] + [(x + r * math.cos(a * math.pi / 8), y + r * math.sin(a * math.pi / 8)) for a in range(17)]
    shader.uniform_float("color", col)
    batch_for_shader(shader, "TRI_FAN", {"pos": pts}).draw(shader)


def _row_y(region, i):
    h = row_height()
    top = region.view2d.view_to_region(0, -(rows_top() + i) * h, clip=False)[1]
    bottom = region.view2d.view_to_region(0, -(rows_top() + i + 1) * h, clip=False)[1]
    return bottom, top


def _zoom(region):
    v2d = region.view2d
    try:
        return (v2d.view_to_region(0, 0, clip=False)[1] - v2d.view_to_region(0, -1000, clip=False)[1]) / 1000
    except Exception:
        return 1.0


# Where the panel lays out a row's parts, in row heights from the region's left edge (measured on drawn rows)
FOLD_CX, ICON_X, TEXT_X, INDENT = 0.9, 1.55, 2.75, 0.45
SELECTED_NAME = (1.0, 0.769, 0.18, 1.0)             # C4D: the active object's name, #FFC42E
OTHER_SELECTED_NAME = (0.96, 0.56, 0.2, 1.0)        # C4D: the other selected objects' names, orange
PARENT_NAME = (0.663, 0.4, 0.133, 1.0)              # C4D: the selected object's parents, #A96622
TREE = (0.33, 0.33, 0.33, 1.0)                      # the hierarchy lines
BOX = (0.58, 0.58, 0.58, 1.0)                       # the fold box


def _unit(region):
    return row_height() * _zoom(region)


def _name_x(context, region, depth):
    """Where a row's tree line starts, and where its name text starts, in region pixels."""
    u = _unit(region)
    return (FOLD_CX - 0.25 + depth * INDENT) * u, (TEXT_X + depth * INDENT) * u


def _draw_tree(context, region, rows, drop, shader):
    """The C4D look of the rows: hierarchy lines, fold boxes, and the names in white, yellow (selected) or orange
    (a selected object's parents)."""
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader
    if not rows:
        return
    u = _unit(region)
    s = context.preferences.system.ui_scale
    sel = {o for o in context.selected_objects}
    parents = set()
    for o in sel:
        p = o.parent
        while p is not None:
            parents.add(p)
            p = p.parent
    theme = context.preferences.themes[0].user_interface.wcol_regular.text
    normal = (theme[0], theme[1], theme[2], 1.0)
    kind, _sep, into = drop.partition(":") if drop else ("", "", "")
    # which rows have a sibling below them (the line goes on down), level by level
    n = len(rows)
    nxt = [False] * n
    for i in range(n):
        d = rows[i][1]
        for j in range(i + 1, n):
            if rows[j][1] < d:
                break
            if rows[j][1] == d:
                nxt[i] = True
                break
    lines, boxes, names = [], [], []
    cont = {}                                            # level -> does the line at that level go on below
    size = context.preferences.ui_styles[0].widget.points * s * _zoom(region)
    for i, (ob, d) in enumerate(rows):
        bottom, top = _row_y(region, i)
        cont[d] = nxt[i]
        if bottom > region.height or top < 0:
            continue
        mid = (top + bottom) / 2
        cx = (FOLD_CX + d * INDENT) * u
        for k in range(d):                               # the lines of the levels above that go on past this row
            if cont.get(k):
                kx = (FOLD_CX + k * INDENT) * u
                lines += [(kx, bottom), (kx, top)]
        lines += [(cx, top), (cx, mid), (cx, mid), ((ICON_X + d * INDENT) * u - 0.1 * u, mid)]
        if nxt[i]:
            lines += [(cx, mid), (cx, bottom)]
        if ob.children:
            boxes.append((cx, mid, ob.b4d_om_closed))
        if kind == "INTO" and ob.name == into:
            continue                                     # the drop target's name is drawn white on black (_draw_drop)
        act = context.view_layer.objects.active
        col = SELECTED_NAME if ob == act and (ob in sel or not ob.visible_get()) else OTHER_SELECTED_NAME if ob in sel \
            else PARENT_NAME if ob in parents else normal
        names.append(((TEXT_X + d * INDENT) * u, bottom + (top - bottom - size * 0.72) / 2, ob.name, col))
    gpu.state.blend_set("ALPHA")
    gpu.state.line_width_set(max(1.0, s))
    shader.uniform_float("color", TREE)
    if lines:
        batch_for_shader(shader, "LINES", {"pos": lines}).draw(shader)
    half = 0.21 * u
    bg = context.preferences.themes[0].properties.space.back
    for cx, cy, closed in boxes:
        _rect(shader, cx - half, cy - half, cx + half, cy + half, (bg[0], bg[1], bg[2], 1.0))
        box = [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy - half), (cx + half, cy + half),
               (cx + half, cy + half), (cx - half, cy + half), (cx - half, cy + half), (cx - half, cy - half),
               (cx - half * 0.55, cy), (cx + half * 0.55, cy)]
        if closed:
            box += [(cx, cy - half * 0.55), (cx, cy + half * 0.55)]
        shader.uniform_float("color", BOX)
        batch_for_shader(shader, "LINES", {"pos": box}).draw(shader)
    gpu.state.line_width_set(1.0)
    fid = 0
    blf.size(fid, size)
    for x, y, text, col in names:
        blf.color(fid, *col)
        blf.position(fid, x, y, 0)
        blf.draw(fid, text)
    gpu.state.blend_set("NONE")


def _rect(shader, x0, y0, x1, y1, col):
    from gpu_extras.batch import batch_for_shader
    shader.uniform_float("color", col)
    batch_for_shader(shader, "TRIS", {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}, indices=[(0, 1, 2), (0, 2, 3)]).draw(shader)


def _draw_drop(context, region, rows, drop, shader):
    """While dragging in the Object Manager: a white line where the objects will go between rows (its left end at the
    level they will take), or the target's name in white on black when they go under it; a badge at the pointer."""
    import blf
    import gpu
    kind, _sep, name = drop.partition(":")
    names = [o.name for o, _d in rows]
    s = context.preferences.system.ui_scale
    z = _zoom(region)
    gpu.state.blend_set("ALPHA")
    name_end = divider_x(context, region, rows) - 4 * s
    if kind in ("BEFORE", "AFTER", "END") and (name in names or kind == "END") and rows:
        i = len(rows) - 1 if kind == "END" else names.index(name)
        depth = 0 if kind == "END" else rows[i][1]
        bottom, top = _row_y(region, i)
        y = top if kind == "BEFORE" else bottom
        x0, _tx = _name_x(context, region, depth)
        _rect(shader, x0, y - 1 * s, name_end, y + 1 * s, (0.92, 0.92, 0.92, 1.0))
    elif kind == "INTO" and name in names:
        i = names.index(name)
        bottom, top = _row_y(region, i)
        _x0, tx = _name_x(context, region, rows[i][1])
        fid = 0
        size = context.preferences.ui_styles[0].widget.points * s * z
        blf.size(fid, size)
        w = blf.dimensions(fid, name)[0]
        _rect(shader, tx - 3 * s * z, bottom + 1, min(tx + w + 4 * s * z, name_end), top - 1, (0.0, 0.0, 0.0, 1.0))
        blf.color(fid, 1.0, 1.0, 1.0, 1.0)
        blf.position(fid, tx, bottom + (top - bottom - size * 0.72) / 2, 0)
        blf.draw(fid, name)
    if _drag_mouse and kind in ("SELF", ""):
        # can't drop here: a grey circle with a slash at the pointer
        import math
        from gpu_extras.batch import batch_for_shader
        mx, my = _drag_mouse
        cx, cy, r = mx + 12 * s, my - 14 * s, 6 * s
        ring = []
        for k in range(24):
            a0, a1 = 2 * math.pi * k / 24, 2 * math.pi * (k + 1) / 24
            ring += [(cx + math.cos(a0) * r, cy + math.sin(a0) * r), (cx + math.cos(a1) * r, cy + math.sin(a1) * r)]
        d = r * 0.7
        ring += [(cx - d, cy + d), (cx + d, cy - d)]
        disc = [(cx, cy)] + [(cx + math.cos(2 * math.pi * k / 24) * r, cy + math.sin(2 * math.pi * k / 24) * r) for k in range(25)]
        shader.uniform_float("color", (0.55, 0.55, 0.55, 1.0))
        batch_for_shader(shader, "TRI_FAN", {"pos": disc}).draw(shader)
        gpu.state.line_width_set(2.0 * s)
        shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
        batch_for_shader(shader, "LINES", {"pos": ring}).draw(shader)
        gpu.state.line_width_set(1.0)
    if _drag_mouse and kind not in ("SELF", ""):
        # the badge: a small box with an arrow, left for "goes here", down for "goes under"
        mx, my = _drag_mouse
        bx, by, b = mx + 14 * s, my - 22 * s, 7 * s
        lines = [(bx, by), (bx + b, by), (bx + b, by), (bx + b, by + b), (bx + b, by + b), (bx, by + b), (bx, by + b), (bx, by)]
        if kind == "INTO":
            ax, ay = bx + b / 2, by + b + 9 * s
            lines += [(ax, ay), (ax, by + b + 2 * s), (ax, by + b + 2 * s), (ax - 2.5 * s, by + b + 4.5 * s), (ax, by + b + 2 * s), (ax + 2.5 * s, by + b + 4.5 * s)]
        else:
            ay = by + b + 5 * s
            lines += [(bx + b + 3 * s, ay), (bx + 1 * s, ay), (bx + 1 * s, ay), (bx + 3.5 * s, ay + 2.5 * s), (bx + 1 * s, ay), (bx + 3.5 * s, ay - 2.5 * s)]
        from gpu_extras.batch import batch_for_shader
        for col, wd in (((0, 0, 0, 0.8), 3.0), ((1, 1, 1, 1), 1.0)):
            gpu.state.line_width_set(wd * s)
            shader.uniform_float("color", col)
            batch_for_shader(shader, "LINES", {"pos": lines}).draw(shader)
        gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")


def _add_keymap():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return
    km = kc.keymaps.new(name="Property Editor", space_type="PROPERTIES")
    _keymaps.append((km, km.keymap_items.new("blenda4d.om_divider", "LEFTMOUSE", "PRESS", any=True)))   # passes on away from the line; notes Alt
    for mods in ({}, {"shift": True}, {"ctrl": True}, {"oskey": True}, {"alt": True}):   # a drag down the dots or checks paints them
        _keymaps.append((km, km.keymap_items.new("blenda4d.om_paint", "LEFTMOUSE", "CLICK_DRAG", **mods)))
    for mods in ({}, {"shift": True}, {"ctrl": True}, {"oskey": True}):     # a drag from empty space draws a box
        _keymaps.append((km, km.keymap_items.new("blenda4d.om_box", "LEFTMOUSE", "CLICK_DRAG", **mods)))
    _keymaps.append((km, km.keymap_items.new("blenda4d.om_drag", "LEFTMOUSE", "CLICK_DRAG")))  # after om_box: it passes on a name
    for mods in ({"ctrl": True}, {"oskey": True}):        # Ctrl/Cmd-drag a name: drop a copy (C4D)
        _keymaps.append((km, km.keymap_items.new("blenda4d.om_drag", "LEFTMOUSE", "CLICK_DRAG", **mods)))
    _keymaps.append((km, km.keymap_items.new("blenda4d.om_select", "LEFTMOUSE", "CLICK")))
    _keymaps.append((km, km.keymap_items.new("blenda4d.om_select", "LEFTMOUSE", "CLICK", shift=True)))
    _keymaps.append((km, km.keymap_items.new("blenda4d.om_select", "LEFTMOUSE", "CLICK", ctrl=True)))
    _keymaps.append((km, km.keymap_items.new("blenda4d.om_select", "LEFTMOUSE", "CLICK", oskey=True)))
    _keymaps.append((km, km.keymap_items.new("blenda4d.om_select", "LEFTMOUSE", "CLICK", alt=True)))   # Alt on the dots: both
    _keymaps.append((km, km.keymap_items.new("blenda4d.om_rename", "LEFTMOUSE", "DOUBLE_CLICK")))
    _keymaps.append((km, km.keymap_items.new("blenda4d.om_rename", "F2", "PRESS")))
    vkm = kc.keymaps.new(name="3D View", space_type="VIEW_3D")             # C4D Move tool: Ctrl/Cmd-drag copies
    for key in ("OSKEY", "LEFT_CTRL", "RIGHT_CTRL"):
        _keymaps.append((vkm, vkm.keymap_items.new("blenda4d.drag_copy", key, "PRESS", any=True)))
    for key in ("DEL", "BACK_SPACE"):                      # Delete and Backspace delete the selection (issue #2)
        _keymaps.append((km, km.keymap_items.new("blenda4d.om_delete", key, "PRESS")))


def unregister():
    if _switch_refresh in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_switch_refresh)
    from . import multiedit, fontpick
    multiedit.unregister()
    fontpick.unregister()
    for h in _draw:
        bpy.types.SpaceProperties.draw_handler_remove(h, "WINDOW")
    _draw.clear()
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    _keymaps.clear()
    O, W = bpy.types.Object, bpy.types.WindowManager
    for n in ("b4d_om_closed", "b4d_enabled", "b4d_vis_editor", "b4d_vis_render"):
        delattr(O, n)
    for n in ("b4d_om_search", "b4d_tag_sel", "b4d_om_divider", "b4d_om_drop", "b4d_om_zoom", "b4d_am_tab", "b4d_right_tab", "b4d_material", "b4d_ab_tab", "b4d_ab_search", "b4d_am_subject"):
        delattr(W, n)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
