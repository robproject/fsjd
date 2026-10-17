#!/usr/bin/env python3
from collections import Counter, defaultdict
from dataclasses import dataclass
import difflib
from itertools import zip_longest
import os
import json
from typing import Optional
import sys

from json_source_map import calculate
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text
from rich.tree import Tree


@dataclass
class FrappeDiff:
    old_path: str
    new_path: str
    print_table: int = 0

    def prep(self) -> None:
        self.base_obj, self.base_ln = self.get_file(self.old_path)
        self.head_obj, self.head_ln = self.get_file(self.new_path)
        self.make_label()
        if self.print_table:
            self.prep_table()
        else:
            self.table = None

    def get_file(self, path: str) -> None:
        with open(path) as f:
            json_str = f.read()
            return json.loads(json_str), LineNos(json_str)

    def make_label(self) -> None:
        self.name = self.new_path.split("/")[-1]
        self.label = f"[bold]{escape(self.name)}[/bold]"

    def prep_table(self) -> None:
        table = Table(
            title=self.label,
            title_justify="left",
            show_lines=True,
            title_style="bold",
            expand=True,
        )
        table.add_column("+-, L#, Path", ratio=1)
        table.add_column("Key or Element", ratio=1)
        table.add_column("Value", ratio=1)
        self.table = table

    def print(self):
        if isinstance(self.base_obj, list):
            self.tree = self.list_diff(
                self.name,
                self.base_obj,
                self.head_obj,
            )
        elif isinstance(self.base_obj, dict):
            self.tree = self.dict_diff(
                self.name,
                self.base_obj,
                self.head_obj,
            )
        self.tree.label = self.label
        if self.tree.children:
            console.log(self.tree)
        elif self.table and self.table.rows:
            console.log(self.table)
        else:
            console.log(f"[bold]{self.label}[/bold]")

    def dict_diff(
        self,
        name: str,
        base_dict: dict,
        head_dict: dict,
        b_path: str = "",
        h_path: str = "",
    ) -> Tree:

        # Keys and values are data, not rich markup: escape them wherever they're printed.
        dict_tree = Tree(escape(name))

        for bk, bk_v in base_dict.items():
            # concatenated path for passing to table/tree constructor functions: red_kvp, grn_kvp, mod_kvp
            self.conc_b_path = f"{b_path}/{bk}"
            if bk in head_dict:
                hk_v = head_dict[bk]
                self.conc_h_path = f"{h_path}/{bk}"
                if type(bk_v) is list and type(hk_v) is list and (bk_v or hk_v):
                    # If no differences, None is returned
                    rtree = self.list_diff(
                        bk, bk_v, hk_v, self.conc_b_path, self.conc_h_path
                    )
                    if rtree.children:
                        dict_tree.add(rtree)
                elif type(bk_v) is dict and type(hk_v) is dict:
                    rtree = self.dict_diff(
                        bk, bk_v, hk_v, self.conc_b_path, self.conc_h_path
                    )
                    if rtree.children:
                        dict_tree.add(rtree)
                elif bk_v != hk_v and not bk in ("modified", "modified_by", "creation"):
                    # JSON held in a string (a Print Format's format_data, a Workspace's
                    # content, a Property Setter's value): diff the parsed values.
                    if parsed := json_values(bk_v, hk_v):
                        diff = (
                            self.list_diff
                            if type(parsed[0]) is list
                            else self.dict_diff
                        )
                        rows = len(self.table.rows) if self.print_table else 0
                        rtree = diff(bk, *parsed, self.conc_b_path, self.conc_h_path)
                        shown = bool(rtree.children) or (
                            self.print_table and len(self.table.rows) > rows
                        )
                        if rtree.children:
                            dict_tree.add(rtree)
                        # the nested diff moved them
                        self.conc_b_path = f"{b_path}/{bk}"
                        self.conc_h_path = f"{h_path}/{bk}"
                        if notes := json_notes(*parsed):
                            self.hunk_kvp(bk, notes, dict_tree)
                        elif not shown:
                            # e.g. a repeat removed, or only ignored keys changed
                            self.mod_kvp(bk, f"{bk_v}", f"{hk_v}", dict_tree)
                    elif is_text(bk_v, hk_v):
                        hunks = text_hunks(
                            bk_v or "", hk_v or "", keep_indent=bk in CODE_KEYS
                        )
                        self.hunk_kvp(
                            bk,
                            hunks or [Text("whitespace only", style="dim")],
                            dict_tree,
                        )
                    else:
                        self.mod_kvp(bk, f"{bk_v}", f"{hk_v}", dict_tree)
            else:
                self.red_kvp(bk, f"{bk_v}", dict_tree)
        for hk in head_dict:
            if hk not in base_dict:
                self.conc_h_path = f"{h_path}/{hk}"
                self.grn_kvp(hk, f"{head_dict[hk]}", dict_tree)
        return dict_tree

    def red_kvp(self, key: str, value: str, tree: Tree) -> None:
        key, value = escape(key), escape(value)
        if self.print_table:
            self.table.add_row(
                f"[bold]- {self.base_ln.key(self.conc_b_path)}[/bold] {escape(self.conc_b_path)}",
                key,
                value,
                style="red",
            )
        else:
            tree.add(
                f"[red][bold]- {self.base_ln.key(self.conc_b_path)}[/bold] {key} : {value}[/red]"
            )

    def grn_kvp(self, key: str, value: str, tree: Tree) -> None:
        key, value = escape(key), escape(value)
        if self.print_table:
            self.table.add_row(
                f"[bold]+ {self.head_ln.key(self.conc_h_path)}[/bold] {escape(self.conc_h_path)}",
                key,
                value,
                style="green",
            )
        else:
            tree.add(
                f"[green][bold]+ {self.head_ln.key(self.conc_h_path)}[/bold] {key} : {value}[/green]"
            )

    def mod_kvp(self, key: str, b_val: str, h_val: str, tree: Tree) -> None:
        key, b_val, h_val = escape(key), escape(b_val), escape(h_val)
        if self.print_table:
            self.table.add_row(
                f"[bold]- {self.base_ln.key(self.conc_b_path)}[/bold] {escape(self.conc_b_path)}",
                f"[default]{key}[/default]",
                b_val,
                style="red",
            )
            self.table.add_row(
                f"[bold]+ {self.head_ln.key(self.conc_h_path)}[/bold] {escape(self.conc_h_path)}",
                f"[default]{key}[/default]",
                h_val,
                style="green",
            )
        else:
            tree.add(
                f"[bold red]{self.base_ln.key(self.conc_b_path)}[/bold red] => "
                f"[bold green]{self.head_ln.key(self.conc_h_path)}[/bold green]"
                f" {key} : [red]{b_val}[/red] => [green]{h_val}[/green]"
            )

    def hunk_kvp(self, key: str, hunks: "list[Text]", tree: Tree) -> None:
        # Changed lines of a multi-line value (HTML, Jinja, CSS, SQL, scripts, ZPL) in place
        # of both whole values; hunk line numbers are within the value.
        lines = (
            f"[bold red]{self.base_ln.key(self.conc_b_path)}[/bold red] => "
            f"[bold green]{self.head_ln.key(self.conc_h_path)}[/bold green]"
        )
        if self.print_table:
            for hunk in hunks:
                self.table.add_row(
                    f"{lines} {escape(self.conc_h_path)}",
                    f"[default]{escape(key)}[/default]",
                    hunk,
                )
        else:
            key_tree = tree.add(f"{lines} {escape(key)}")
            for hunk in hunks:
                key_tree.add(hunk)

    def list_diff(
        self,
        name: str,
        base_list: list,
        head_list: list,
        b_path: str = "",
        h_path: str = "",
    ) -> Tree:

        list_tree = Tree(escape(name))

        if all(type(d) is dict for d in base_list + head_list):
            if common_key := self.get_common_key(name, base_list, head_list):
                # Pair dicts by common key, so reordering isn't a change.
                base_keys = keys_of(base_list, common_key)
                head_keys = keys_of(head_list, common_key)
                pairs = key_pairs(base_list, head_list, base_keys, head_keys)
                for i, bd in enumerate(base_list):
                    conc_b_path = f"{b_path}/{i}"
                    if (j := pairs.get(i)) is not None:
                        rtree = self.dict_diff(
                            key_label(base_keys[i]),
                            bd,
                            head_list[j],
                            conc_b_path,
                            f"{h_path}/{j}",
                        )
                        if rtree.children:
                            list_tree.add(rtree)
                    else:
                        self.red_dict(
                            bd, conc_b_path, list_tree, key_label(base_keys[i])
                        )
                paired = set(pairs.values())
                for j, hd in enumerate(head_list):
                    if j not in paired:
                        self.grn_dict(
                            hd, f"{h_path}/{j}", list_tree, key_label(head_keys[j])
                        )
            else:
                self.aligned_diff(list_tree, base_list, head_list, b_path, h_path)
        else:
            # Compare elements as JSON text: they may be unhashable, or a mix of types.
            del_set, add_set = symmetric_diff_sep(
                set(map(canonical, base_list)), set(map(canonical, head_list))
            )
            for i, e in enumerate(base_list):
                if (c := canonical(e)) in del_set:
                    self.red_elem(f"{e}", f"{b_path}/{i}", list_tree)
                    del_set.remove(c)
            for i, e in enumerate(head_list):
                if (c := canonical(e)) in add_set:
                    self.grn_elem(f"{e}", f"{h_path}/{i}", list_tree)
                    add_set.remove(c)

        return list_tree

    def aligned_diff(
        self,
        tree: Tree,
        base_list: list,
        head_list: list,
        b_path: str,
        h_path: str,
    ) -> None:
        # No key fits: align the lists like a line diff, and compare the dicts of each
        # replaced run by position.
        matcher = difflib.SequenceMatcher(
            None,
            list(map(canonical, base_list)),
            list(map(canonical, head_list)),
            autojunk=False,
        )
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            for i, j in zip_longest(range(i1, i2), range(j1, j2)):
                if j is None:
                    self.red_dict(base_list[i], f"{b_path}/{i}", tree, f"[{i}]")
                elif i is None:
                    self.grn_dict(head_list[j], f"{h_path}/{j}", tree, f"[{j}]")
                else:
                    rtree = self.dict_diff(
                        f"[{i}]",
                        base_list[i],
                        head_list[j],
                        f"{b_path}/{i}",
                        f"{h_path}/{j}",
                    )
                    if rtree.children:
                        tree.add(rtree)

    def get_common_key(
        self, name: str, base_list: list, head_list: list
    ) -> "Optional[tuple[str, ...]]":
        # Candidate keys per parent, in order of preference. A candidate's first field must be
        # set in every dict and the rest may be missing; the first unique in both lists wins.
        # One parent name can hold different doctypes: Workspace links have link_to and
        # DocType links have link_doctype; Workflow states have state and DocType states title.
        common_keys = {
            "custom_fields": [("fieldname",)],
            "fields": [("fieldname",)],
            "actions": [("label",)],
            # A Workspace's Card Breaks have a label and no link_to.
            "links": [
                ("link_to",),
                ("label", "link_to"),
                ("link_doctype", "link_fieldname", "parent_doctype"),
            ],
            "property_setters": [("name",)],
            "custom_perms": [("role",), ("role", "permlevel", "if_owner")],
            "permissions": [("role",), ("role", "permlevel", "if_owner")],
            "roles": [("role",)],
            "states": [("state",), ("title",)],
            # A transition may be repeated once per role.
            "transitions": [
                ("state", "action", "next_state"),
                ("state", "action", "next_state", "allowed"),
            ],
            "format_data": [("fieldname",)],
        }
        dicts = base_list + head_list
        # Then any single key every dict has, identifier-like keys first. idx would only pair by position.
        shared = set.intersection(*map(set, dicts)) - {"idx"} if dicts else set()
        preferred = [
            k
            for k in ("name", "fieldname", "id", "key", "label", "title")
            if k in shared
        ]
        known = common_keys.get(name, [("name",)] if ".json" in name else [])
        usable = [
            key
            for key in [
                *known,
                *((k,) for k in [*preferred, *sorted(shared - set(preferred))]),
            ]
            if all(d.get(key[0]) is not None for d in dicts) and is_hashable(dicts, key)
        ]
        for key in usable:
            if is_unique(keys_of(base_list, key)) and is_unique(
                keys_of(head_list, key)
            ):
                return key
        # A known key still pairs a list with a few repeats, e.g. a link in two Workspace cards.
        return next((key for key in usable if key in known), None)

    def red_elem(self, elem: str, path: str, tree: Tree) -> None:
        elem = escape(elem)
        if self.print_table:
            self.table.add_row(
                f"[bold]- {self.base_ln.val(path)}[/bold] {escape(path)}",
                elem,
                "",
                style="red",
            )
        else:
            tree.add(f"[red][bold]- {self.base_ln.val(path)}[/bold] {elem}[/red]")

    def grn_elem(self, elem: str, path: str, tree: Tree) -> None:
        elem = escape(elem)
        if self.print_table:
            self.table.add_row(
                f"[bold]+ {self.head_ln.val(path)}[/bold] {escape(path)}",
                elem,
                "",
                style="green",
            )
        else:
            tree.add(f"[green][bold]+ {self.head_ln.val(path)}[/bold] {elem}[/green]")

    def red_dict(self, bdict: dict, path: str, tree: Tree, label: str) -> None:
        label = escape(label)
        if self.print_table:
            self.table.add_row(
                f"[bold]- {self.base_ln.val(path)}[/bold] {escape(path)}",
                label,
                "[bold magenta]VALUES BELOW[/bold magenta]",
                style="red",
            )
            for k, v in bdict.items():
                self.table.add_row(
                    f"[bold magenta]In Dict:[/bold magenta] {label}",
                    escape(k),
                    escape(f"{v}"),
                    style="red",
                )
        else:
            dict_tree = tree.add(
                f"[red][bold]- {self.base_ln.val(path)}[/bold] {label}[/red]"
            )
            for k, v in bdict.items():
                dict_tree.add(f"[red]- {escape(k)} : {escape(f'{v}')}[/red]")

    def grn_dict(self, hdict: dict, path: str, tree: Tree, label: str) -> None:
        label = escape(label)
        if self.print_table:
            self.table.add_row(
                f"[bold]+ {self.head_ln.val(path)}[/bold] {escape(path)}",
                label,
                "[bold magenta]VALUES BELOW[/bold magenta]",
                style="green",
            )
            for k, v in hdict.items():
                self.table.add_row(
                    f"[bold magenta]In Dict:[/bold magenta] {label}",
                    escape(k),
                    escape(f"{v}"),
                    style="green",
                )
        else:
            dict_tree = tree.add(
                f"[green][bold]+ {self.head_ln.val(path)}[/bold] {label}[/green]"
            )
            for k, v in hdict.items():
                dict_tree.add(f"[green]+ {escape(k)} : {escape(f'{v}')}[/green]")


@dataclass
class LineNos:
    json_str: str

    def __post_init__(self) -> None:
        self.calc_obj = calculate(self.json_str)

    def val(self, path: str) -> int:
        return self.eval_path(path, "value")

    def key(self, path: str) -> int:
        return self.eval_path(path, "key")

    def eval_path(self, path: str, type: str) -> "dict[int]":
        key = type + "_start"
        # '/path_parent/path_child': Entry(value_start=Location(line=int, column=int, position=int), value_end=L..., key_start=L..., key_end=L...)
        # '/path_parent/path_child': {value_start : {line : int}, value_end: {...}, key_start: {...}, key_end: {...}}
        # Paths inside a JSON string value (format_data) aren't mapped: use the nearest ancestor's line.
        while path and path not in self.calc_obj:
            path = path.rsplit("/", maxsplit=1)[0]
        return eval(f"{self.calc_obj[path]}")[key]


def Entry(**kwargs: str) -> dict:
    return kwargs


def Location(**kwargs: str) -> int:
    return kwargs["line"]


# gets symmetric difference while maintaining original group membership
def symmetric_diff_sep(
    set1: "set[str]", set2: "set[str]"
) -> "tuple[set[str], set[str]]":
    exclusive_set1 = set1 - set2
    exclusive_set2 = set2 - set1
    return exclusive_set1, exclusive_set2


def keys_of(dict_list: list, common_key: "tuple[str, ...]") -> "list[tuple]":
    return [tuple(d.get(field) for field in common_key) for d in dict_list]


def key_pairs(
    base_list: list, head_list: list, base_keys: list, head_keys: list
) -> "dict[int, int]":
    # Base index -> head index of the dict with the same key value. The copies of a repeated
    # value are aligned by content, so the copy that changed or went is the one reported.
    base_at, head_at = defaultdict(list), defaultdict(list)
    for i, kv in enumerate(base_keys):
        base_at[kv].append(i)
    for j, kv in enumerate(head_keys):
        head_at[kv].append(j)
    pairs = {}
    for kv, base_is in base_at.items():
        head_js = head_at.get(kv, [])
        if len(base_is) == len(head_js) == 1:
            pairs[base_is[0]] = head_js[0]
            continue
        matcher = difflib.SequenceMatcher(
            None,
            [canonical(base_list[i]) for i in base_is],
            [canonical(head_list[j]) for j in head_js],
            autojunk=False,
        )
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ("equal", "replace"):
                pairs.update(zip(base_is[i1:i2], head_js[j1:j2]))
    return pairs


def key_label(kv: tuple) -> str:
    # Trailing unset fields are dropped and inner ones shown as "-". A Workspace link's
    # label usually repeats its link_to: show it once.
    values = list(kv)
    while len(values) > 1 and values[-1] is None:
        values.pop()
    if len(values) > 1 and values[1] == values[0]:
        del values[1]
    return " / ".join("-" if v is None else f"{v}" for v in values)


def is_unique(values: list) -> bool:
    return len(set(values)) == len(values)


def is_hashable(dict_list: list, common_key: "tuple[str, ...]") -> bool:
    try:
        set(keys_of(dict_list, common_key))
    except TypeError:  # e.g. a list value
        return False
    return True


def canonical(elem) -> str:
    return json.dumps(elem, sort_keys=True)


def json_values(*texts: str) -> "Optional[tuple]":
    # The values parsed, if every text is JSON for a list, or every one for a dict, and
    # not nested so deep that diffing them would hit the recursion limit.
    if not all(type(t) is str for t in texts):
        return None
    try:
        values = tuple(json.loads(t) for t in texts)
    except (ValueError, RecursionError):
        return None
    types = {type(v) for v in values}
    if types not in ({list}, {dict}) or max(map(depth, values)) > 100:
        return None
    return values


def depth(value) -> int:
    deepest, stack = 0, [(value, 1)]
    while stack:
        value, d = stack.pop()
        if type(value) in (list, dict):
            deepest = max(deepest, d)
            children = value.values() if type(value) is dict else value
            stack.extend((child, d + 1) for child in children)
    return deepest


def json_notes(b_val, h_val) -> "list[Text]":
    # What the paired diff of JSON values doesn't show. It pairs list items regardless of
    # order, but in e.g. field_order the order is the content.
    if canonical(b_val) == canonical(h_val):
        return [Text("formatting only", style="dim")]
    if type(b_val) is not list:
        return []
    b_items, h_items = list(map(canonical, b_val)), list(map(canonical, h_val))
    shared = Counter(b_items) & Counter(h_items)
    if in_order(b_items, shared) == in_order(h_items, shared):
        return []
    b_lines, h_lines = (
        "\n".join(e if type(e) is str else canonical(e) for e in v)
        for v in (b_val, h_val)
    )
    return [Text("order changed", style="dim"), *text_hunks(b_lines, h_lines)]


def in_order(items: "list[str]", shared: Counter) -> "list[str]":
    # The items the other list also has, in this list's order.
    left, kept = Counter(shared), []
    for item in items:
        if left[item]:
            left[item] -= 1
            kept.append(item)
    return kept


def is_text(*values) -> bool:
    # Strings or nothing, at least one of them over several lines.
    return all(v is None or type(v) is str for v in values) and any(
        type(v) is str and "\n" in v for v in values
    )


# Fields holding Python, where indentation is logic.
CODE_KEYS = {"script", "report_script", "condition", "code"}


def text_hunks(
    b_text: str, h_text: str, context: int = 2, keep_indent: bool = False
) -> "list[Text]":
    # Whitespace at the ends of a line doesn't count, so a re-indent matches; with
    # keep_indent only trailing whitespace. Hunks with nothing but blank lines changed
    # are skipped. difflib's autojunk keeps very long values fast.
    b_lines, h_lines = b_text.splitlines(), h_text.splitlines()
    trim = str.rstrip if keep_indent else str.strip
    matcher = difflib.SequenceMatcher(
        None,
        [trim(line) for line in b_lines],
        [trim(line) for line in h_lines],
        autojunk=max(len(b_lines), len(h_lines)) > 2000,
    )

    def blank(tag, a1, a2, c1, c2) -> bool:
        return tag == "equal" or not "".join(b_lines[a1:a2] + h_lines[c1:c2]).strip()

    hunks = []
    for group in matcher.get_grouped_opcodes(context):
        if all(blank(*op) for op in group):
            continue
        i1, i2, j1, j2 = group[0][1], group[-1][2], group[0][3], group[-1][4]
        hunk = Text(
            f"@@ -{hunk_range(i1, i2)} +{hunk_range(j1, j2)} @@",
            style="cyan",
            tab_size=4,
        )
        for tag, a1, a2, c1, c2 in group:
            if tag == "equal":
                for line in h_lines[c1:c2]:
                    hunk.append(f"\n  {line}", style="dim")
                continue
            for line in b_lines[a1:a2]:
                hunk.append(f"\n- {line}", style="red")
            for line in h_lines[c1:c2]:
                hunk.append(f"\n+ {line}", style="green")
        hunks.append(hunk)
    return hunks


def hunk_range(start: int, stop: int) -> str:
    # As in a unified diff: 1-based, and an empty range is placed after the line before it.
    length = stop - start
    return f"{start + 1 if length else start},{length}"


def is_json(text):
    try:
        json.loads(text)
    except ValueError as e:
        return False
    return True


if __name__ == "__main__":

    # https://github.com/azrafe7/test_python_rich_on_gh_pages/blob/0015be3b6b1925c4d4c9acbaed319666ff7cec89/main.py
    console = Console(force_terminal=True, width=150, log_time=False, log_path=False)

    old_path = sys.argv[2]
    old_hex = sys.argv[3]
    new_path = sys.argv[5]
    new_hex = sys.argv[6]
    table_mode = int(os.getenv("TABLE_MODE"))

    if old_path.rsplit(".", maxsplit=1)[-1] == "json":
        if new_hex == ".":
            console.log(
                f"[bold][red]Removed: {escape(old_path.split('/')[-1])}[/red][/bold]"
            )
        else:
            if "custom" in new_path:
                console.log(f"[bold][magenta]Custom File:[/magenta][/bold]")
            diff = FrappeDiff(old_path, new_path, table_mode)
            diff.prep()
            diff.print()
        console.log()
