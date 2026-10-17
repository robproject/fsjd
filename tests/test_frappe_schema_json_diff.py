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


def fsjd(base, head, table_mode=0, renamed_from="") -> str:
    with tempfile.TemporaryDirectory() as tmp:
        old, new = Path(tmp, "old_doc.json"), Path(tmp, "doc.json")
        # path old-file old-hex old-mode new-file new-hex new-mode [new-path xfrm-msg]
        args = ["doc.json", old, "1" * 40, "100644", new, "2" * 40, "100644"]
        if renamed_from:
            args = [renamed_from, *args[1:], "doc.json", "similarity index 90%"]
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

    def test_deleted_file_shows_its_contents(self):
        out = fsjd(self.new_doctype, ABSENT)
        self.assertIn("Removed: doc.json", out)
        self.assertRegex(out, r"- \d+ qty\s+.*- fieldname : qty")
        self.assertRegex(out, r"- \d+ module : Stock")
        self.assertNotIn("+ ", out)

    def test_multi_line_values_are_marked_line_by_line(self):
        out = fsjd(self.new_doctype, ABSENT)
        self.assertRegex(out, r"- default\s+.*- line 1\s+.*- line \[2\]")
        html = "<div>\n  {{ doc.name }}\n</div>"
        out = fsjd(ABSENT, print_format(html))
        self.assertRegex(out, r"\+ \d+ html\s+.*@@ -0,0 \+1,3 @@\s+.*\+ <div>")

    def test_deleted_print_format_layout(self):
        layout = [
            {
                "fieldname": "heading",
                "fieldtype": "Custom HTML",
                "options": "<h1>\n{{ doc.name }}\n</h1>",
            },
            {"fieldtype": "Section Break"},
        ]
        out = fsjd(
            {"doctype": "Print Format", "format_data": json.dumps(layout)}, ABSENT
        )
        self.assertRegex(
            out, r"format_data\s+.*- \d+ Custom HTML\s+.*- fieldname : heading"
        )
        self.assertRegex(out, r"- options\s+.*- <h1>\s+.*- \{\{ doc.name \}\}")
        self.assertRegex(out, r"- \d+ Section Break")

    def test_added_fixture_list(self):
        out = fsjd(ABSENT, [{"doctype": "Role", "name": "Packer", "desk_access": 1}])
        self.assertRegex(out, r"(?s)\+ \d+ Packer\s.*\+ desk_access : 1")

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
        self.assertRegex(fsjd(ABSENT, 42), r"\+ 42\s")
        self.assertRegex(fsjd(None, ABSENT), r"- None\s")
        self.assertIn("1 => 2", fsjd(1, 2))

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
