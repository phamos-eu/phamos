"""
Remove synthetic labels from Section Break / Column Break / Tab Break fields.

Root cause: a previous version of phamos/public/js/frappe_list_bulk_edit_override.js
patched frappe.meta.add_field to assign a fallback label (= fieldname) to every
field whose label was null.  Layout fields are intentionally label-less, but that
patch labelled them too.  When anyone saved a DocType form while that script was
active, Frappe serialised the in-memory labels back to the database, producing:

  - tabDocField rows:        label = fieldname   (e.g. "section_break_ovpv")
  - tabCustom Field rows:    label = fieldname
  - tabProperty Setter rows: value = field_name  (same thing, via Customize Form)

A separate variation set label / value to the fieldtype string ("Section Break",
"Column Break") instead of the fieldname; those are caught by the second block.

This patch clears all such synthetic values so layout fields become invisible
separators again, as intended.
"""

import frappe


_LAYOUT_TYPES = ("Section Break", "Column Break", "Tab Break")
_LAYOUT_SQL   = "('Section Break', 'Column Break', 'Tab Break')"


def execute():
    # ── 1. tabDocField ────────────────────────────────────────────────────────
    # label was set to fieldname by the JS patch, then persisted via DocType save.
    frappe.db.sql(f"""
        UPDATE `tabDocField`
           SET label = ''
         WHERE fieldtype IN {_LAYOUT_SQL}
           AND label != ''
           AND label = fieldname
    """)

    # ── 2. tabCustom Field ────────────────────────────────────────────────────
    frappe.db.sql(f"""
        UPDATE `tabCustom Field`
           SET label = ''
         WHERE fieldtype IN {_LAYOUT_SQL}
           AND label != ''
           AND label = fieldname
    """)

    # ── 3. tabProperty Setter — value == field_name ───────────────────────────
    # Covers doctypes customised via Customize Form while the bad JS was running.
    # We join with tabDocField / tabCustom Field to confirm the field is a
    # layout type before deleting, so we never touch data fields accidentally.
    frappe.db.sql(f"""
        DELETE ps
          FROM `tabProperty Setter` ps
         INNER JOIN `tabDocField` df
                 ON df.parent   = ps.doc_type
                AND df.fieldname = ps.field_name
                AND df.fieldtype IN {_LAYOUT_SQL}
         WHERE ps.property = 'label'
           AND ps.value    != ''
           AND ps.value     = ps.field_name
    """)

    frappe.db.sql(f"""
        DELETE ps
          FROM `tabProperty Setter` ps
         INNER JOIN `tabCustom Field` cf
                 ON cf.dt        = ps.doc_type
                AND cf.fieldname = ps.field_name
                AND cf.fieldtype IN {_LAYOUT_SQL}
         WHERE ps.property = 'label'
           AND ps.value    != ''
           AND ps.value     = ps.field_name
    """)

    # ── 4. tabProperty Setter — value == fieldtype string ────────────────────
    # A second variant set value to the fieldtype string literal, e.g.
    # property=label, value="Section Break" on a Section Break field.
    frappe.db.sql(f"""
        DELETE ps
          FROM `tabProperty Setter` ps
         INNER JOIN `tabDocField` df
                 ON df.parent    = ps.doc_type
                AND df.fieldname = ps.field_name
         WHERE ps.property    = 'label'
           AND ps.value       = df.fieldtype
           AND df.fieldtype   IN {_LAYOUT_SQL}
    """)

    frappe.db.sql(f"""
        DELETE ps
          FROM `tabProperty Setter` ps
         INNER JOIN `tabCustom Field` cf
                 ON cf.dt        = ps.doc_type
                AND cf.fieldname = ps.field_name
         WHERE ps.property    = 'label'
           AND ps.value       = cf.fieldtype
           AND cf.fieldtype   IN {_LAYOUT_SQL}
    """)

    frappe.db.commit()
