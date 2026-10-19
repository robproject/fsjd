"""Run the script the way git runs a GIT_EXTERNAL_DIFF and check what it prints.

python -m unittest discover tests
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "frappe_schema_json_diff.py"


ABSENT = object()  # the side of an added or deleted file that git gives as /dev/null


def fsjd(base, head, table_mode=0, renamed_from="", path="doc.json") -> str:
    with tempfile.TemporaryDirectory() as tmp:
        old, new = Path(tmp, "old_doc.json"), Path(tmp, "doc.json")
        # path old-file old-hex old-mode new-file new-hex new-mode [new-path xfrm-msg]
        args = [path, old, "1" * 40, "100644", new, "2" * 40, "100644"]
        if renamed_from:
            args = [renamed_from, *args[1:], path, "similarity index 90%"]
        for i, (side, value) in ((1, (old, base)), (4, (new, head))):
            if value is ABSENT:
                args[i : i + 3] = [os.devnull, ".", "."]
            else:
                side.write_text(
                    value if type(value) is str else json.dumps(value, indent=1)
                )
        result = subprocess.run(
            [sys.executable, SCRIPT, *map(str, args)],
            capture_output=True,
            text=True,
            env={**os.environ, "TABLE_MODE": str(table_mode)},
        )
    assert result.returncode == 0, result.stdout + result.stderr
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


def doctype(**kwargs) -> dict:
    return {"doctype": "DocType", "name": "Test Doc", "fields": [], **kwargs}


def line_of(obj, text: str) -> int:
    # 1-based line of text in obj written as the tests write files
    return json.dumps(obj, indent=1).splitlines().index(text) + 1


def record_starts(records: list) -> "list[int]":
    # 1-based first line of each record in a records file as the tests write it
    lines = json.dumps(records, indent=1).splitlines()
    return [i + 1 for i, line in enumerate(lines) if line == " {"]


class TestLineNumbers(unittest.TestCase):
    def test_lines_are_the_files_own(self):
        base = doctype(
            module="Stock", fields=[{"fieldname": "qty", "fieldtype": "Int"}]
        )
        head = doctype(
            module="Selling",
            fields=[{"fieldname": "qty", "fieldtype": "Float"}],
            issingle=1,
        )
        b_type = line_of(base, '   "fieldtype": "Int"')
        h_type = line_of(head, '   "fieldtype": "Float"')
        b_module = line_of(base, ' "module": "Stock"')
        h_module = line_of(head, ' "module": "Selling",')
        h_single = line_of(head, ' "issingle": 1')
        out = fsjd(base, head)
        self.assertIn(f"{b_type} => {h_type} fieldtype : Int => Float", out)
        self.assertIn(f"{b_module} => {h_module} module : Stock => Selling", out)
        self.assertIn(f"+ {h_single} issingle : 1", out)
        self.assertIn(f"+ {h_single} issingle : 1", fsjd(ABSENT, head))


class TestCommonKey(unittest.TestCase):
    def test_doctype_links(self):
        # Document links have no link_to, and one link_doctype can appear twice.
        links = [
            {
                "link_doctype": "Stock Entry Detail",
                "link_fieldname": "test_doc",
                "parent_doctype": "Stock Entry",
            },
            {
                "link_doctype": "Stock Entry Detail",
                "link_fieldname": "to_test_doc",
                "parent_doctype": "Stock Entry",
            },
        ]
        added = {
            "link_doctype": "Delivery Note",
            "link_fieldname": "test_doc",
            "group": "Shipping",
        }
        out = fsjd(doctype(links=links), doctype(links=[*links, added]))
        self.assertRegex(out, r"\+ \d+ Delivery Note / test_doc\s")
        self.assertNotIn("Stock Entry Detail", out)

    def test_workspace_links_with_card_breaks_and_repeats(self):
        card = {"type": "Card Break", "label": "Reports", "link_count": 1}
        link = {
            "type": "Link",
            "label": "Stock Entry",
            "link_to": "Stock Entry",
            "link_type": "DocType",
        }
        base = {
            "doctype": "Workspace",
            "links": [card, link, {**card, "label": "More"}, link],
        }
        head = {
            "doctype": "Workspace",
            "links": [
                {**card, "link_count": 2},
                link,
                {**card, "label": "More"},
                link,
                link,
            ],
        }
        out = fsjd(base, head)
        self.assertIn("link_count : 1 => 2", out)
        self.assertRegex(out, r"\+ \d+ Stock Entry\s")
        # the added link: title, label, link_to
        self.assertEqual(out.count("Stock Entry"), 3, out)
        self.assertNotIn("More", out)

    def test_repeated_key_blames_the_removed_copy(self):
        item = {"type": "Link", "label": "Item", "link_to": "Item", "hidden": 0}
        other = {"type": "Link", "label": "BOM", "link_to": "BOM"}
        base = {"doctype": "Workspace", "links": [item, other, {**item, "hidden": 1}]}
        head = {"doctype": "Workspace", "links": [other, {**item, "hidden": 1}]}
        out = fsjd(base, head)
        self.assertRegex(out, r"- \d+ Item\s")
        self.assertIn("- hidden : 0", out)
        self.assertNotIn("=>", out)

    def test_doctype_states(self):
        states = [
            {"title": "Open", "color": "Blue"},
            {"title": "Closed", "color": "Gray"},
        ]
        out = fsjd(
            doctype(states=states),
            doctype(states=[states[0], {**states[1], "color": "Green"}]),
        )
        self.assertIn("color : Gray => Green", out)

    def test_workflow_transitions_share_a_state(self):
        t = [
            {
                "state": "Draft",
                "action": "Submit",
                "next_state": "Pending",
                "allowed": "All",
            },
            {
                "state": "Draft",
                "action": "Cancel",
                "next_state": "Cancelled",
                "allowed": "All",
            },
        ]
        out = fsjd(
            {"doctype": "Workflow", "transitions": t},
            {"doctype": "Workflow", "transitions": t[::-1]},
        )
        self.assertEqual(out.split(), ["doc.json"])  # reordered only

    def test_workflow_transition_per_role(self):
        t = {"state": "Draft", "action": "Submit", "next_state": "Pending"}
        base = {
            "doctype": "Workflow",
            "transitions": [{**t, "allowed": "A"}, {**t, "allowed": "B"}],
        }
        out = fsjd(base, {**base, "transitions": [{**t, "allowed": "A"}]})
        self.assertRegex(out, r"- \d+ Draft / Submit / Pending / B\s")

    def test_permissions_by_role_and_permlevel(self):
        perms = [
            {"role": "System Manager", "read": 1},
            {"role": "System Manager", "permlevel": 1, "read": 1},
            {"role": "System Manager", "if_owner": 1, "read": 1},
        ]
        out = fsjd(
            doctype(permissions=perms),
            doctype(permissions=[perms[0], {**perms[1], "write": 1}, perms[2]]),
        )
        self.assertRegex(out, r"System Manager / 1\s+.*\+ \d+ write : 1")
        self.assertNotIn("System Manager / - / 1", out)

    def test_fixture_list_by_name(self):
        base = [
            {"doctype": "Role", "name": "A", "desk_access": 1},
            {"doctype": "Role", "name": "B"},
        ]
        head = [base[1], {**base[0], "desk_access": 0}]
        out = fsjd(base, head)
        self.assertRegex(out, r"A\s+.*desk_access : 1 => 0")
        self.assertNotIn("B", out)

    def test_print_format_data_insert(self):
        layout = [
            {
                "fieldname": "print_heading_template",
                "fieldtype": "Custom HTML",
                "options": "<h1></h1>",
            },
            {"fieldtype": "Section Break", "label": ""},
            {"fieldtype": "Column Break"},
            {"fieldname": "customer", "print_hide": 0},
            {"fieldtype": "Section Break", "label": ""},
            {"fieldtype": "Column Break"},
            {"fieldname": "items", "print_hide": 0},
        ]
        inserted = [
            *layout[:4],
            {"fieldname": "posting_date", "print_hide": 0},
            *layout[4:],
        ]
        base = {"doctype": "Print Format", "format_data": json.dumps(layout)}
        out = fsjd(base, {**base, "format_data": json.dumps(inserted)})
        self.assertIn("posting_date", out)
        self.assertNotIn("customer", out)
        self.assertNotIn("items", out)

    def test_values_that_change_type_or_cannot_be_hashed(self):
        base = doctype(
            links=[],
            rows=[{"ids": [1, 2]}, {"ids": [3]}],
            nested=[[1, 2], [3]],
            tags=["a"],
        )
        head = doctype(
            links=None,
            rows=[{"ids": [1, 2]}, {"ids": [4]}],
            nested=[[1, 2], [4]],
            tags=[{"a": 1}],
        )
        out = fsjd(base, head)
        self.assertIn("links : [] => None", out)
        self.assertRegex(out, r"ids\s+.*- \d+ 3\s+.*\+ \d+ 4")
        self.assertRegex(out, r"nested\s+.*- \d+ \[3\]\s+.*\+ \d+ \[4\]")
        self.assertRegex(out, r"tags\s+.*- \d+ a\s+.*\+ \d+ \{'a': 1\}")

    def test_added_key_is_reported_at_its_own_path(self):
        out = fsjd(
            doctype(issingle=0), doctype(issingle=0, track_changes=1), table_mode=1
        )
        self.assertIn("/track_changes", out)
        self.assertNotIn("/issingle", out)

    def test_table_mode_runs(self):
        links = [{"link_doctype": "Delivery Note", "link_fieldname": "test_doc"}]
        out = fsjd(doctype(links=[]), doctype(links=links), table_mode=1)
        self.assertIn("Delivery Note / test_doc", out)


class TestMarkup(unittest.TestCase):
    def test_brackets_in_data_print_as_written(self):
        field = {"fieldname": "qty", "depends_on": "eval:doc.items[i]"}
        base = doctype(fields=[field])
        head = doctype(
            fields=[{**field, "depends_on": "eval:doc.items[/x]"}],
            links=[{"link_doctype": "[bold]Note", "link_fieldname": "x"}],
        )
        for table_mode in (0, 1):
            out = fsjd(base, head, table_mode=table_mode)
            self.assertIn("eval:doc.items[i]", out)
            self.assertIn("eval:doc.items[/x]", out)
            self.assertIn("[bold]Note", out)


def lines(n: int, fmt: str = "<td>{{{{ row.col_{} }}}}</td>") -> "list[str]":
    return [fmt.format(i) for i in range(n)]


def print_format(html: str) -> dict:
    return {"doctype": "Print Format", "name": "Test PF", "html": html}


class TestText(unittest.TestCase):
    def test_changed_lines_in_context(self):
        base = lines(40)
        head = [*base[:20], "<td>{{ row.total[i] }}</td>", *base[21:]]
        out = fsjd(print_format("\n".join(base)), print_format("\n".join(head)))
        self.assertRegex(out, r"html\s+.*@@ -19,5 \+19,5 @@")
        self.assertRegex(
            out,
            r"- <td>\{\{ row.col_20 \}\}</td>\s+.*\+ <td>\{\{ row.total\[i\] \}\}</td>",
        )
        self.assertIn("row.col_18", out)  # context
        self.assertNotIn("row.col_17", out)
        self.assertNotIn("row.col_23", out)

    def test_whitespace_only(self):
        base = lines(5)
        head = ["", *("    " + line for line in base), "   "]
        out = fsjd(print_format("\n".join(base)), print_format("\n".join(head)))
        self.assertIn("whitespace only", out)
        self.assertNotIn("row.col_", out)

    def test_reindent_shows_only_real_changes(self):
        base = lines(30)
        head = (
            ["\t" + line for line in base[:10]]
            + ["\t<td>new</td>"]
            + ["\t" + line for line in base[10:]]
        )
        out = fsjd(print_format("\n".join(base)), print_format("\n".join(head)))
        self.assertRegex(out, r"\+\s+<td>new</td>")
        self.assertEqual(len(re.findall(r"^\W*[-+] ", out, re.M)), 1, out)

    def test_script_added_to_empty_value(self):
        base = {"doctype": "Server Script", "name": "S", "script": None}
        out = fsjd(base, {**base, "script": "x = 1\nif x:\n    frappe.throw('[/x]')"})
        self.assertRegex(out, r"@@ -0,0 \+1,3 @@")
        self.assertIn("+     frappe.throw('[/x]')", out)

    def test_table_mode(self):
        base = lines(10, "SELECT col_{}")
        head = [*base[:5], "SELECT changed", *base[6:]]
        out = fsjd(
            {"doctype": "Report", "query": "\n".join(base)},
            {"doctype": "Report", "query": "\n".join(head)},
            table_mode=1,
        )
        self.assertIn("SELECT changed", out)
        self.assertIn("query", out)
        self.assertNotIn("col_0", out)


def field_order(order: "list[str]") -> dict:
    setter = {"name": "Item-main-field_order", "property": "field_order"}
    return {
        "doctype": "Item",
        "property_setters": [{**setter, "value": json.dumps(order)}],
    }


class TestJsonInString(unittest.TestCase):
    def test_field_order_rename(self):
        out = fsjd(field_order(["a", "b_old", "c"]), field_order(["a", "b_new", "c"]))
        self.assertRegex(out, r"- \d+ b_old\s+.*\+ \d+ b_new")
        self.assertNotIn('"a"', out)

    def test_field_order_reorder(self):
        out = fsjd(field_order(["a", "b", "c", "d"]), field_order(["a", "c", "d", "b"]))
        self.assertIn("order changed", out)
        self.assertRegex(out, r"- b\s+.*c\s+.*d\s+.*\+ b")

    def test_formatting_only(self):
        base = {"doctype": "Number Card", "filters_json": '{"status": "Open"}'}
        out = fsjd(base, {**base, "filters_json": '{"status":"Open"}'})
        self.assertIn("formatting only", out)

    def test_workspace_content_block_added(self):
        block = {"id": "a1", "type": "shortcut", "data": {"shortcut_name": "Item"}}
        added = {"id": "b2", "type": "shortcut", "data": {"shortcut_name": "BOM"}}
        base = {"doctype": "Workspace", "content": json.dumps([block])}
        out = fsjd(base, {**base, "content": json.dumps([block, added])})
        self.assertRegex(out, r"content\s+.*\+ \d+ b2")
        self.assertNotIn("a1", out)

    def test_strings_that_are_not_json_containers(self):
        base = {"doctype": "DocType", "description": "10", "label": "Qty [i]"}
        out = fsjd(base, {**base, "description": "11", "label": "Qty [j]"})
        self.assertIn("description : 10 => 11", out)
        self.assertIn("label : Qty [i] => Qty [j]", out)

    def test_field_order_repeat_removed(self):
        out = fsjd(field_order(["a", "a", "b"]), field_order(["a", "b"]))
        self.assertEqual(len(re.findall(r"- \d+ a\s", out)), 1, out)
        self.assertNotIn("=>", out)

    def test_field_order_move_with_rename(self):
        out = fsjd(
            field_order(["a", "x", "b_old", "c"]), field_order(["a", "b_new", "c", "x"])
        )
        self.assertRegex(out, r"- \d+ b_old\s+.*\+ \d+ b_new")
        self.assertIn("order changed", out)
        hunk = out.split("order changed")[1]
        for line in ("- b_old", "+ b_new"):
            self.assertIn(line, hunk)
        self.assertRegex(hunk, r"[-+] (c|x)\s")

    def test_value_type_is_not_formatting(self):
        base = {"doctype": "Number Card", "filters_json": '{"docstatus": 1}'}
        out = fsjd(base, {**base, "filters_json": '{"docstatus": true}'})
        self.assertNotIn("formatting only", out)
        # 1 == True to the paired diff, so this falls back to both values
        self.assertIn('filters_json : {"docstatus": 1} => {"docstatus": true}', out)

    def test_json_in_table_mode(self):
        out = fsjd(
            field_order(["a", "b_old"]), field_order(["a", "b_new"]), table_mode=1
        )
        self.assertIn("b_old", out)
        self.assertIn("b_new", out)
        self.assertNotIn('"a"', out)


class TestWhitespace(unittest.TestCase):
    def test_python_dedent_counts(self):
        base = {"doctype": "Server Script", "script": "if x:\n    a()\n    b()"}
        out = fsjd(base, {**base, "script": "if x:\n    a()\nb()"})
        self.assertNotIn("whitespace only", out)
        self.assertRegex(out, r"-     b\(\)\s+.*\+ b\(\)")

    def test_spaces_inside_a_line_count(self):
        out = fsjd(
            print_format("<p>a b</p>\n<p>c</p>"), print_format("<p>a   b</p>\n<p>c</p>")
        )
        self.assertRegex(out, r"- <p>a b</p>\s+.*\+ <p>a   b</p>")

    def test_hunk_header_counts_blank_lines(self):
        out = fsjd(print_format("a\nb\n\n\nc\nd\ne"), print_format("a\nb\nc\nD\ne"))
        self.assertIn("@@ -1,7 +1,5 @@", out)
        self.assertEqual(len(re.findall(r"^[\s│├└─]*- ", out, re.M)), 3, out)
        self.assertEqual(len(re.findall(r"^[\s│├└─]*\+ ", out, re.M)), 1, out)

    def test_blank_lines_alone_make_no_hunk(self):
        out = fsjd(print_format("a\nb\nc"), print_format("a\n\nb\nc\n\n"))
        self.assertIn("whitespace only", out)

    def test_context_lines_are_the_new_version(self):
        base = print_format("keep\nold\nend")
        out = fsjd(base, print_format("\u00a0keep\nnew\nend"))
        self.assertIn("\u00a0keep", out)


class TestAddedDeleted(unittest.TestCase):
    new_doctype = doctype(
        module="Stock",
        field_order=["qty", "notes"],
        fields=[
            {"fieldname": "qty", "fieldtype": "Float"},
            {"fieldname": "notes", "fieldtype": "Text", "default": "line 1\nline [2]"},
        ],
        permissions=[{"role": "System Manager", "read": 1}],
    )

    def test_added_file_shows_its_contents(self):
        out = fsjd(ABSENT, self.new_doctype)
        self.assertIn("Added: doc.json", out)
        self.assertRegex(out, r"fields\s+.*\+ \d+ qty\s+.*\+ fieldname : qty")
        self.assertRegex(out, r"\+ \d+ System Manager")
        self.assertRegex(out, r"\+ \d+ notes\s")  # field_order
        self.assertRegex(out, r"\+ \d+ module : Stock")
        self.assertNotIn("- ", out)

    def test_deleted_document_shows_its_name(self):
        for table_mode in (0, 1):
            out = fsjd(self.new_doctype, ABSENT, table_mode=table_mode)
            self.assertIn("Removed: doc.json", out)
            self.assertRegex(out, r"- 1\s+(│ )?DocType: Test Doc")
            for content in ("qty", "Stock", "System Manager", "+ "):
                self.assertNotIn(content, out)

    def test_deleted_customizations(self):
        custom = {
            "doctype": "Item",
            "custom_fields": [{"fieldname": "x"}],
            "property_setters": [],
        }
        self.assertRegex(fsjd(custom, ABSENT), r"- 1 Customizations: Item")

    def test_multi_line_values_are_marked_line_by_line(self):
        out = fsjd(ABSENT, self.new_doctype)
        self.assertRegex(out, r"\+ default\s+.*\+ line 1\s+.*\+ line \[2\]")
        html = "<div>\n  {{ doc.name }}\n</div>"
        out = fsjd(ABSENT, print_format(html))
        self.assertRegex(out, r"\+ \d+ html\s+.*@@ -0,0 \+1,3 @@\s+.*\+ <div>")

    def test_added_print_format_layout(self):
        layout = [
            {
                "fieldname": "heading",
                "fieldtype": "Custom HTML",
                "options": "<h1>\n{{ doc.name }}\n</h1>",
            },
            {"fieldtype": "Section Break"},
        ]
        out = fsjd(
            ABSENT, {"doctype": "Print Format", "format_data": json.dumps(layout)}
        )
        self.assertRegex(
            out, r"format_data\s+.*\+ \d+ Custom HTML\s+.*\+ fieldname : heading"
        )
        self.assertRegex(out, r"\+ options\s+.*\+ <h1>\s+.*\+ \{\{ doc.name \}\}")
        self.assertRegex(out, r"\+ \d+ Section Break")

    def test_fixtures_list_their_records(self):
        roles = [
            {"doctype": "Role", "name": "Packer", "desk_access": 1},
            {"doctype": "Workspace", "title": "Shipping", "content": "[]"},
            {"doctype": "Item"},
            {
                "doctype": "Workspace Link",
                "name": "vc5r",
                "parent": "CRM",
                "label": "Reports",
            },
        ]
        # each record's first line in the file as the tests write it
        starts = [
            i + 1
            for i, l in enumerate(json.dumps(roles, indent=1).splitlines())
            if l == " {"
        ]
        for sign, base, head in (("+", ABSENT, roles), ("-", roles, ABSENT)):
            out = fsjd(base, head)
            for start, title in zip(
                starts,
                (
                    "Role: Packer",
                    "Workspace: Shipping",
                    "Item: (no name)",
                    "Workspace Link in CRM: Reports",
                ),
            ):
                self.assertRegex(out, rf"{re.escape(f'{sign} {start} {title}')} *\n")
            self.assertNotIn("desk_access", out)
        out = fsjd(ABSENT, roles, table_mode=1)
        self.assertIn("Role: Packer", out)
        self.assertNotIn("desk_access", out)

    def test_record_titles(self):
        records = [
            {"doctype": "Workspace", "name": "N", "title": "T"},
            {"doctype": "Item", "item_code": "_Test Item"},
            {"doctype": "User", "email": "a@example.com"},
            {"doctype": "Dunning Type", "dunning_type": "First Notice"},
            {"doctype": "Academic Term", "academic_term_name": "2026"},
            {"doctype": "Note", "name": "[bold]x[/bold] \\"},
            {"doctype": "Note", "title": "two\nlines"},
        ]
        for table_mode in (0, 1):
            out = fsjd(ABSENT, records, table_mode=table_mode)
            for title in (
                "Workspace: N",
                "Item: _Test Item",
                "User: a@example.com",
                "Dunning Type: First Notice",
                "Academic Term: 2026",
                "Note: [bold]x[/bold] \\",
                "Note: two lines",
            ):
                self.assertIn(title, out)
            self.assertNotIn("\\\\", out)

    def test_test_records_without_doctype(self):
        records = [{"item_code": "_Test Item"}, {"title": "Other"}]
        out = fsjd(records, ABSENT, path="stock/doctype/item/test_records.json")
        self.assertRegex(out, r"- \d+ _Test Item\s")
        self.assertRegex(out, r"- \d+ Other\s")
        self.assertIn("not a Frappe document", fsjd(records, ABSENT))  # elsewhere

    def test_many_records_are_counted(self):
        rows = [
            {"doctype": "Workspace Link", "parent": p, "label": f"L{i}"}
            for p in ("Stock", "CRM")
            for i in range(30)
        ]
        fields = [
            {"doctype": "Custom Field", "dt": "Item", "fieldname": f"f{i}"}
            for i in range(5)
        ]
        for table_mode in (0, 1):
            out = fsjd(rows + fields, ABSENT, table_mode=table_mode)
            for group in (
                "Workspace Link in Stock: 30 records",
                "Workspace Link in CRM: 30 records",
                "Custom Field for Item: 5 records",
            ):
                self.assertIn(group, out)
            self.assertNotIn("L1", out)
        self.assertIn("L1", fsjd(rows[:50], ABSENT))  # up to 50 are listed

    def test_no_records(self):
        self.assertIn("+ no records", fsjd(ABSENT, []))

    def test_fixtures_gaining_or_losing_a_few_records_show_them(self):
        kept = [{"doctype": "Role", "name": "Kept"}]
        new = [{"doctype": "Role", "name": f"R{i}", "desk_access": 1} for i in range(5)]
        for table_mode in (0, 1):
            out = fsjd(kept, kept + new, table_mode=table_mode)
            self.assertEqual(out.count("desk_access"), 5, out)  # whole
            out = fsjd(kept + new[:2], kept + new[2:], table_mode=table_mode)
            self.assertEqual(out.count("desk_access"), 5, out)  # 2 lost + 3 gained

    def test_fixtures_gaining_or_losing_more_name_them(self):
        kept = [{"doctype": "Role", "name": "Kept", "desk_access": 0}]
        lost = [
            {"doctype": "Role", "name": f"Old{i}", "desk_access": 1} for i in range(3)
        ]
        gained = [
            {"doctype": "Role", "name": f"New{i}", "desk_access": 1} for i in range(3)
        ]
        base, head = kept + lost, [{**kept[0], "desk_access": 1}] + gained
        out = fsjd(base, head)
        self.assertIn("desk_access : 0 => 1", out)  # a kept record still diffs
        for i in range(3):
            self.assertRegex(out, rf"- {record_starts(base)[i + 1]} Role: Old{i} *\n")
            self.assertRegex(out, rf"\+ {record_starts(head)[i + 1]} Role: New{i} *\n")
        self.assertEqual(out.count("desk_access"), 1, out)
        out = fsjd(base, head, table_mode=1)
        self.assertIn("Role: New2", out)
        self.assertNotIn("VALUES BELOW", out)  # no record whole

    def test_fixtures_gaining_or_losing_many_count_them(self):
        rows = [
            {
                "doctype": "Workspace Link",
                "name": f"h{i}",
                "parent": "Stock",
                "label": f"L{i}",
            }
            for i in range(60)
        ]
        for base in ([], [{"doctype": "Role", "name": "Kept"}]):
            out = fsjd(base, base + rows)
            self.assertIn("+ Workspace Link in Stock: 60 records", out)
            self.assertNotIn("L1", out)

    def test_renamed_records(self):
        # a re-export: same rows, new random names and timestamps, one row really new
        def row(name, label, modified="2025-01-01"):
            return {
                "doctype": "Workspace Link",
                "name": name,
                "parent": "Stock",
                "label": label,
                "modified": modified,
            }

        base = [row(f"h{i}", f"L{i}") for i in range(10)]
        head = [row(f"g{i}", f"L{i}", "2025-02-02") for i in range(10)]
        head.append(row("g10", "New Link"))
        for table_mode in (0, 1):
            out = fsjd(base, head + [], table_mode=table_mode)
            self.assertIn("10 records renamed only", out)
            self.assertIn("Workspace Link in Stock: New Link", out)
            self.assertNotIn("L3", out)
            self.assertNotIn("h3", out)
        self.assertRegex(
            fsjd(base, head), r"\+ \d+ Workspace Link in Stock: New Link\s"
        )

    def test_renamed_record_that_also_changed(self):
        lost = {
            "doctype": "Workspace Shortcut",
            "name": "a1",
            "parent": "CRM",
            "label": "Sales",
            "color": "Grey",
            "idx": 1,
        }
        out = fsjd([lost], [{**lost, "name": "b2", "color": "Blue"}])
        self.assertRegex(out, r"Workspace Shortcut in CRM: Sales\s+.*name : a1 => b2")
        self.assertIn("color : Grey => Blue", out)
        self.assertNotIn("renamed only", out)
        # idx counts: a row moved as well as renamed isn't only renamed
        out = fsjd([lost], [{**lost, "name": "b2", "idx": 2}])
        self.assertIn("idx : 1 => 2", out)
        self.assertNotIn("renamed only", out)

    def test_renamed_record_without_a_parent_is_a_change(self):
        out = fsjd(
            [{"doctype": "Role", "name": "Packer"}],
            [{"doctype": "Role", "name": "Loader"}],
        )
        self.assertNotIn("renamed only", out)
        self.assertRegex(out, r"- \d+ Role: Packer")
        self.assertRegex(out, r"\+ \d+ Role: Loader")

    def test_repeated_titles_are_not_paired(self):
        lost = [
            {"doctype": "Role", "name": f"x{i}", "parent": "P", "label": "Same", "n": i}
            for i in range(2)
        ]
        gained = [
            {"doctype": "Role", "name": "y", "parent": "P", "label": "Same", "n": 9}
        ]
        out = fsjd(lost, gained)
        self.assertEqual(len(re.findall(r"- \d+ Role in P: Same", out)), 2, out)
        self.assertRegex(out, r"\+ \d+ Role in P: Same")

    def test_moved_rows_show_as_order_changes(self):
        # links moved between a Workspace's cards: Frappe exports rows in order, no idx
        def rows(labels, prefix):
            return [
                {
                    "doctype": "Workspace Link",
                    "name": f"{prefix}{i}",
                    "parent": "Stock",
                    "label": l,
                }
                for i, l in enumerate(labels)
            ]

        base = rows(["A", "L1", "L2", "B", "L3", "L4"], "h")
        head = rows(["A", "L1", "L3", "B", "L2", "L4"], "g")
        for table_mode in (0, 1):
            out = fsjd(base, head, table_mode=table_mode)
            self.assertIn("6 records renamed only", out)
            self.assertIn("order changed: Workspace Link in Stock", out)
            self.assertRegex(out, r"(?s)(- L2.*\+ L2|\+ L3.*- L3)")
        self.assertNotIn(
            "order changed", fsjd(base, rows(["A", "L1", "L2", "B", "L3", "L4"], "g"))
        )

    def test_new_row_after_renames_is_shown_whole(self):
        def row(name, label):
            return {
                "doctype": "Workspace Link",
                "name": name,
                "parent": "Stock",
                "label": label,
            }

        base = [row(f"h{i}", f"L{i}") for i in range(10)]
        head = [row(f"g{i}", f"L{i}") for i in range(10)] + [row("g10", "New Link")]
        out = fsjd(
            base, head
        )  # 11 rows gained, 10 of them renames: 1 is under RECORDS_SHOWN
        self.assertIn("+ label : New Link", out)

    def test_row_moved_to_another_parent_is_not_a_rename(self):
        lost = {
            "doctype": "Workspace Link",
            "name": "h1",
            "parent": "Stock",
            "label": "L1",
        }
        out = fsjd([lost], [{**lost, "name": "g1", "parent": "CRM"}])
        self.assertNotIn("renamed only", out)
        self.assertRegex(out, r"- \d+ Workspace Link in Stock: L1")
        self.assertRegex(out, r"\+ \d+ Workspace Link in CRM: L1")

    def test_title_pairs_are_one_to_one(self):
        lost = {
            "doctype": "Workspace Link",
            "name": "h1",
            "parent": "Stock",
            "label": "X",
            "v": 0,
        }
        gained = [{**lost, "name": f"g{i}", "v": i + 1} for i in range(2)]
        out = fsjd([lost], gained)
        self.assertRegex(out, r"- \d+ Workspace Link in Stock: X")
        self.assertEqual(
            len(re.findall(r"\+ \d+ Workspace Link in Stock: X", out)), 2, out
        )

    def test_records_without_a_parent_are_not_paired_by_title(self):
        other = {"doctype": "Item", "item_code": "C", "item_name": "Other"}
        base = [{"doctype": "Item", "item_code": "A", "item_name": "Widget"}, other]
        head = [{"doctype": "Item", "item_code": "B", "item_name": "Widget"}, other]
        out = fsjd(base, head, path="stock/doctype/item/test_records.json")
        self.assertNotIn("item_code : A => B", out)
        self.assertRegex(out, r"- \d+ Item: Widget")
        self.assertRegex(out, r"\+ \d+ Item: Widget")

    def test_nameless_records_keep_their_key(self):
        base = [{"doctype": "Leave Allocation", "employee": "_T-0001", "leaves": 1}]
        out = fsjd(
            base, [{**base[0], "leaves": 2}], path="hr/doctype/x/test_records.json"
        )
        self.assertIn("leaves : 1 => 2", out)
        self.assertNotIn("(no name)", out)

    def test_rows_renamed_and_changed_alike_are_told_once(self):
        # e.g. a Frappe upgrade adds a field to every exported Workspace Link
        def rows(prefix, extra, n):
            return [
                {
                    "doctype": "Workspace Link",
                    "name": f"{prefix}{i}",
                    "parent": "Stock",
                    "label": f"L{i}",
                    **extra,
                }
                for i in range(n)
            ]

        for table_mode in (0, 1):
            out = fsjd(
                rows("h", {"v": 0}, 8),
                rows("g", {"v": 0, "new_field": 1}, 8),
                table_mode=table_mode,
            )
            self.assertIn("8 records renamed, each with these changes", out)
            self.assertIn("+ new_field : 1", out)
            self.assertNotIn("L3", out)
            out = fsjd(
                rows("h", {"v": 0}, 8), rows("g", {"v": 2}, 8), table_mode=table_mode
            )
            self.assertIn("v : 0 => 2", out)
        out = fsjd(rows("h", {"v": 0}, 5), rows("g", {"v": 2}, 5))  # a few: one by one
        self.assertNotIn("each with these changes", out)
        self.assertEqual(out.count("v : 0 => 2"), 5, out)
        out = fsjd(rows("h", {"v": 0}, 6), rows("g", {"v": 2}, 6))
        self.assertIn("6 records renamed, each with these changes", out)

    def test_renames_only_at_the_top_of_a_fixtures_file(self):
        row = {"name": "a", "parent": "W", "v": 1}
        workspace = {"doctype": "Workspace", "name": "W", "custom_rows": [row]}
        out = fsjd([workspace], [{**workspace, "custom_rows": [{**row, "name": "b"}]}])
        self.assertNotIn("renamed only", out)

    def test_only_a_fixtures_file_is_summarised(self):
        # a DocType's fields gaining many rows still show them whole
        fields = [{"fieldname": f"f{i}", "fieldtype": "Data"} for i in range(8)]
        out = fsjd(doctype(), doctype(fields=fields))
        self.assertEqual(out.count("fieldtype : Data"), 8, out)
        # and so do the child rows of a record in a fixtures file
        links = [{"link_to": f"D{i}", "link_type": "DocType"} for i in range(8)]
        workspace = {"doctype": "Workspace", "name": "Stock", "links": []}
        out = fsjd([workspace], [{**workspace, "links": links}])
        self.assertEqual(out.count("link_type : DocType"), 8, out)

    def test_other_json_shows_its_size(self):
        # the file's own lines, as written
        chart = '{\n\n "Assets": {"Current": {"Cash": {"account_type": "Cash"}}}\n}\n'
        for sign, base, head in (("+", ABSENT, chart), ("-", chart, ABSENT)):
            for table_mode in (0, 1):
                out = fsjd(base, head, table_mode=table_mode)
                self.assertIn("not a Frappe document: 4 lines", out)
                self.assertIn(sign, out)
                self.assertNotIn("Cash", out)
        self.assertIn("+ not a Frappe document: 1 line", fsjd(ABSENT, 42))

    def test_table_mode(self):
        out = fsjd(ABSENT, self.new_doctype, table_mode=1)
        self.assertIn("Added: doc.json", out)
        self.assertIn("System Manager", out)
        self.assertIn("line [2]", out)

    def test_renamed_file(self):
        base = doctype(module="Stock")
        out = fsjd(base, {**base, "module": "Selling"}, renamed_from="dir/old_doc.json")
        self.assertIn("Renamed: old_doc.json → doc.json", out)
        self.assertRegex(
            out, r"(?m)^doc\.json"
        )  # the tree is labelled with the new name
        self.assertIn("module : Stock => Selling", out)

    def test_added_file_that_is_not_json(self):
        out = fsjd(ABSENT, "{ not json")
        self.assertIn("doc.json can't be shown: JSONDecodeError", out)

    def test_modified_file_that_is_not_json_still_fails(self):
        with self.assertRaises(AssertionError):
            fsjd(self.new_doctype, "{ not json")

    def test_renamed_from_another_type(self):
        out = fsjd("var x = 1;", {"a": 1}, renamed_from="public/conf.js")
        self.assertIn("Renamed: conf.js → doc.json", out)
        self.assertIn("can't be shown: JSONDecodeError", out)

    def test_file_that_is_a_scalar(self):
        self.assertIn("1 => 2", fsjd(1, 2))
        self.assertIn("- not a Frappe document: 1 line", fsjd(None, ABSENT))

    def test_empty_values_are_shown(self):
        head = doctype(
            permissions=[], links=[], filters_json="[]", spaced="[ ]", meta={}
        )
        out = fsjd(ABSENT, head)
        for key, value in [
            ("permissions", "[]"),
            ("links", "[]"),
            ("filters_json", "[]"),
            ("spaced", "[ ]"),
            ("meta", "{}"),
        ]:
            self.assertRegex(out, rf"\+ \d+ {key} : {re.escape(value)}\s")
        self.assertNotIn("formatting only", out)

    def test_repeated_list_items(self):
        out = fsjd(ABSENT, doctype(field_order=["a", "a", "b"]))
        self.assertEqual(len(re.findall(r"\+ \d+ a\s", out)), 2, out)
        out = fsjd(
            doctype(field_order=["a", "a", "b"]), doctype(field_order=["a", "b"])
        )
        self.assertEqual(len(re.findall(r"- \d+ a\s", out)), 1, out)

    def test_added_file_prints_in_file_order(self):
        out = fsjd(ABSENT, self.new_doctype)
        top = re.findall(r"^[├└]── (?:\+ \d+ )?(\w+)", out, re.M)
        self.assertEqual(top, list(self.new_doctype), out)

    def test_escaped_key_lines(self):
        base, head = {"doctype": "DocType", "café": 1}, {
            "doctype": "DocType",
            "café": 2,
        }
        line = line_of(base, ' "caf\\u00e9": 1')
        self.assertIn(f"{line} => {line} café : 1 => 2", fsjd(base, head))

    def test_multi_line_value_added_or_removed_in_a_modified_file(self):
        out = fsjd(doctype(), doctype(description="a\nline [2]"))
        self.assertRegex(out, r"\+ \d+ description\s+.*\+ a\s+.*\+ line \[2\]")
        out = fsjd(doctype(description="a\nline [2]"), doctype(), table_mode=1)
        self.assertRegex(out, r"(?s)- a\s.*- line \[2\]")


if __name__ == "__main__":
    unittest.main()
