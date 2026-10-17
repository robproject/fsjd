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


def fsjd(base, head, table_mode=0) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        old, new = Path(tmp, "old_doc.json"), Path(tmp, "doc.json")
        old.write_text(json.dumps(base, indent=1))
        new.write_text(json.dumps(head, indent=1))
        # path old-file old-hex old-mode new-file new-hex new-mode
        args = ["doc.json", old, "1" * 40, "100644", new, "2" * 40, "100644"]
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


if __name__ == "__main__":
    unittest.main()
