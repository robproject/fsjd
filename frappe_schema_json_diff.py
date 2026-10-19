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
    name: str = ""
    only: str = ""  # "+" for an added file, "-" for a deleted one

    def prep(self) -> None:
        # An added Frappe document is shown whole: diffed against a hollow copy of itself
        # (see hollow), all of it shows as added. Other added or deleted files are summed
        # up instead (see sum_up).
        self.whole = self.records_file = False
        if self.only == "+":
            self.head_obj, self.head_ln = self.get_file(self.new_path)
            self.whole = shape(self.head_obj, self.name) == "document"
            if self.whole:
                self.base_obj, self.base_ln = hollow_file(self.head_obj)
        elif self.only == "-":
            self.base_obj, self.base_ln = self.get_file(self.old_path)
        else:
            self.base_obj, self.base_ln = self.get_file(self.old_path)
            self.head_obj, self.head_ln = self.get_file(self.new_path)
            self.records_file = all(
                shape(obj, self.name) == "records"
                for obj in (self.base_obj, self.head_obj)
            )
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
        self.name = self.name or self.new_path.split("/")[-1]
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
        if self.only and not self.whole:
            self.tree = Tree("")
            self.sum_up()
        elif isinstance(self.base_obj, list):
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
        else:
            # a file that's just a JSON scalar
            self.tree = Tree("")
            if self.base_obj != self.head_obj:
                b_val, h_val = escape(f"{self.base_obj}"), escape(f"{self.head_obj}")
                self.tree.add(f"[red]{b_val}[/red] => [green]{h_val}[/green]")
        self.tree.label = self.label
        if self.tree.children:
            console.log(self.tree)
        elif self.table and self.table.rows:
            console.log(self.table)
        else:
            console.log(f"[bold]{self.label}[/bold]")

    def sum_up(self) -> None:
        # An added or deleted file other than an added document: the documents in it by
        # name, or for JSON that isn't Frappe documents, its size.
        obj, ln = (
            (self.head_obj, self.head_ln)
            if self.only == "+"
            else (self.base_obj, self.base_ln)
        )
        if (kind := shape(obj, self.name)) == "document":
            entries = [("", doc_title(obj))]
        elif kind == "records":
            entries = record_entries(list(enumerate(obj))) or [(None, "no records")]
        else:
            lines = len(ln.json_str.splitlines())
            entries = [(None, f"not a Frappe document: {plural(lines, 'line')}")]
        self.add_entries(self.tree, self.only, ln, entries)

    def add_entries(self, tree: Tree, sign: str, ln: "LineNos", entries: list) -> None:
        # (path or None, text) lines that name or count records rather than show them
        color = "green" if sign == "+" else "red"
        for path, text in entries:
            # Text, not markup: titles are data
            mark = f"{sign} " + ("" if path is None else f"{ln.val(path)} ")
            if self.print_table:
                self.table.add_row(
                    Text(mark + (path or ""), style="bold"), Text(text), "", style=color
                )
            else:
                tree.add(Text(mark, style=f"bold {color}") + Text(text, style=color))

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

        # An added file prints in its own order; otherwise the base's, then head's new keys.
        if self.only == "+":
            keys = list(head_dict)
        else:
            keys = [*base_dict, *(k for k in head_dict if k not in base_dict)]
        for bk in keys:
            if bk not in base_dict:
                self.conc_h_path = f"{h_path}/{bk}"
                self.grn_kvp(bk, f"{head_dict[bk]}", dict_tree)
                continue
            bk_v = base_dict[bk]
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
        return dict_tree

    def red_kvp(self, key: str, value: str, tree: Tree) -> None:
        text = side_text("-", value) if "\n" in value else None
        key, value = escape(key), escape(value)
        if self.print_table:
            self.table.add_row(
                f"[bold]- {self.base_ln.key(self.conc_b_path)}[/bold] {escape(self.conc_b_path)}",
                key,
                text or value,
                style="red",
            )
        elif text:
            tree.add(
                f"[red][bold]- {self.base_ln.key(self.conc_b_path)}[/bold] {key}[/red]"
            ).add(text)
        else:
            tree.add(
                f"[red][bold]- {self.base_ln.key(self.conc_b_path)}[/bold] {key} : {value}[/red]"
            )

    def grn_kvp(self, key: str, value: str, tree: Tree) -> None:
        text = side_text("+", value) if "\n" in value else None
        key, value = escape(key), escape(value)
        if self.print_table:
            self.table.add_row(
                f"[bold]+ {self.head_ln.key(self.conc_h_path)}[/bold] {escape(self.conc_h_path)}",
                key,
                text or value,
                style="green",
            )
        elif text:
            tree.add(
                f"[green][bold]+ {self.head_ln.key(self.conc_h_path)}[/bold] {key}[/green]"
            ).add(text)
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
        b_line = f"[bold red]{self.base_ln.key(self.conc_b_path)}[/bold red]"
        h_line = f"[bold green]{self.head_ln.key(self.conc_h_path)}[/bold green]"
        # In an added file, only the new side's line numbers are real.
        if self.only == "+":
            lines = f"[bold green]+[/bold green] {h_line}"
        else:
            lines = f"{b_line} => {h_line}"
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
                paired = set(pairs.values())
                removed = [i for i in range(len(base_list)) if i not in pairs]
                added = [j for j in range(len(head_list)) if j not in paired]
                renamed = 0
                if not b_path and self.records_file:  # same test as top_records below
                    # Re-exporting gives child rows new random names: a row lost and one
                    # gained that are otherwise the same were only renamed.
                    removed, added, renamed = drop_renames(
                        base_list, head_list, removed, added
                    )
                    # and one renamed that changed too keeps its title: diff the two
                    by_title = pair_by_title(base_list, head_list, removed, added)
                    pairs.update(by_title)
                    removed = [i for i in removed if i not in by_title]
                    added = [j for j in added if j not in by_title.values()]
                lost = set(removed)
                # a fixtures file's records are labelled as when named (see doc_title),
                # rather than by a child row's random name
                top_records = not b_path and self.records_file

                def label(records: list, keys: list, i: int) -> str:
                    return doc_title(records[i]) if top_records else key_label(keys[i])

                # The records a fixtures file gains or loses are shown whole if there are
                # only a few, else named or counted (see record_entries).
                brief = (
                    not b_path
                    and self.records_file
                    and len(removed) + len(added) > RECORDS_SHOWN
                )
                for i, bd in enumerate(base_list):
                    conc_b_path = f"{b_path}/{i}"
                    if (j := pairs.get(i)) is not None:
                        rtree = self.dict_diff(
                            label(base_list, base_keys, i),
                            bd,
                            head_list[j],
                            conc_b_path,
                            f"{h_path}/{j}",
                        )
                        if rtree.children:
                            list_tree.add(rtree)
                    elif i in lost and not brief:
                        self.red_dict(
                            bd, conc_b_path, list_tree, label(base_list, base_keys, i)
                        )
                if renamed:
                    note = Text(
                        f"{plural(renamed, 'record')} renamed only", style="dim"
                    )
                    if self.print_table:
                        self.table.add_row("", note, "")
                    else:
                        list_tree.add(note)
                if brief:
                    for sign, ln, side, indexes in (
                        ("-", self.base_ln, base_list, removed),
                        ("+", self.head_ln, head_list, added),
                    ):
                        entries = record_entries([(i, side[i]) for i in indexes])
                        self.add_entries(list_tree, sign, ln, entries)
                else:
                    for j in added:
                        self.grn_dict(
                            head_list[j],
                            f"{h_path}/{j}",
                            list_tree,
                            label(head_list, head_keys, j),
                        )
            else:
                self.aligned_diff(list_tree, base_list, head_list, b_path, h_path)
        else:
            # Compare elements as JSON text, as they may be unhashable or a mix of types, and
            # count them, so each repeat added or removed shows.
            b_items, h_items = list(map(canonical, base_list)), list(
                map(canonical, head_list)
            )
            removed = Counter(b_items) - Counter(h_items)
            added = Counter(h_items) - Counter(b_items)
            for i, (e, c) in enumerate(zip(base_list, b_items)):
                if removed[c]:
                    self.red_elem(f"{e}", f"{b_path}/{i}", list_tree)
                    removed[c] -= 1
            for i, (e, c) in enumerate(zip(head_list, h_items)):
                if added[c]:
                    self.grn_elem(f"{e}", f"{h_path}/{i}", list_tree)
                    added[c] -= 1

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
                    side_text("-", v) if is_text(v) else escape(f"{v}"),
                    style="red",
                )
        else:
            dict_tree = tree.add(
                f"[red][bold]- {self.base_ln.val(path)}[/bold] {label}[/red]"
            )
            for k, v in bdict.items():
                if is_text(v):
                    dict_tree.add(f"[red]- {escape(k)}[/red]").add(side_text("-", v))
                else:
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
                    side_text("+", v) if is_text(v) else escape(f"{v}"),
                    style="green",
                )
        else:
            dict_tree = tree.add(
                f"[green][bold]+ {self.head_ln.val(path)}[/bold] {label}[/green]"
            )
            for k, v in hdict.items():
                if is_text(v):
                    dict_tree.add(f"[green]+ {escape(k)}[/green]").add(
                        side_text("+", v)
                    )
                else:
                    dict_tree.add(f"[green]+ {escape(k)} : {escape(f'{v}')}[/green]")


@dataclass
class LineNos:
    json_str: str

    def __post_init__(self) -> None:
        # json_source_map keeps keys as written, escapes and all ("café"), while
        # fsjd's paths hold them as parsed.
        self.calc_obj = {
            unescape_pointer(p): entry for p, entry in calculate(self.json_str).items()
        }

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
    # json_source_map counts lines from 0
    return kwargs["line"] + 1


def unescape_pointer(pointer: str) -> str:
    if "\\" not in pointer:
        return pointer
    try:
        return "/".join(json.loads(f'"{part}"') for part in pointer.split("/"))
    except ValueError:  # e.g. an escaped "/" split in two
        return pointer


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


def hollow(value):
    # The containers of a value with nothing in them and no scalars: diffed against it,
    # every value shows as added. Text keeps an empty string, so it shows as lines, and
    # JSON in a string an empty JSON container, so it shows as structure.
    # Empty containers are left out, like scalars, so they show as values: "x : []".
    if type(value) is dict:
        return {
            k: h
            for k, v in value.items()
            if v not in ([], {}) and (h := hollow(v)) is not None
        }
    if type(value) is list:
        return []
    if parsed := json_values(value):
        if not parsed[0]:
            return None
        return "[]" if type(parsed[0]) is list else "{}"
    if is_text(value):
        return ""
    return None


def hollow_file(doc: dict) -> "tuple":
    shell = hollow(doc)
    return shell, LineNos(json.dumps(shell, indent=1))


# Records a fixtures file gains or loses are shown whole up to RECORDS_SHOWN, named up to
# RECORDS_LISTED, and counted beyond that. Records in an added or deleted file are named.
RECORDS_SHOWN = 5
RECORDS_LISTED = 50


# What a re-export changes in a record it only renames
RENAME_FIELDS = ("name", "modified", "creation", "owner", "modified_by")


def drop_renames(base_list: list, head_list: list, removed: list, added: list) -> tuple:
    # Match each lost child table row (a record with a parent, named at random) to a gained
    # one with the same content but for RENAME_FIELDS: (records still lost, records still
    # gained, how many were matched). Other records' names are what they are: a renamed
    # Role is a change.
    def content(record: dict) -> str:
        return canonical({k: v for k, v in record.items() if k not in RENAME_FIELDS})

    gained = defaultdict(list)
    for j in added:
        gained[content(head_list[j])].append(j)  # parent is content: rows match rows
    still_removed, matched = [], set()
    for i in removed:
        if base_list[i].get("parent") and (same := gained.get(content(base_list[i]))):
            matched.add(same.pop(0))
        else:
            still_removed.append(i)
    return still_removed, [j for j in added if j not in matched], len(matched)


def pair_by_title(base_list: list, head_list: list, removed: list, added: list) -> dict:
    # lost index -> gained index, for titles (see doc_title) only one of each has
    lost = Counter(doc_title(base_list[i]) for i in removed)
    gained = Counter(doc_title(head_list[j]) for j in added)
    gained_at = {doc_title(head_list[j]): j for j in added}
    return {
        i: gained_at[title]
        for i in removed
        if lost[title := doc_title(base_list[i])] == 1 and gained[title] == 1
    }


def record_entries(indexed: "list[tuple[int, dict]]") -> list:
    # (path, title) per (index, record), or past RECORDS_LISTED, (None, count) per group
    if len(indexed) <= RECORDS_LISTED:
        return [(f"/{i}", doc_title(doc)) for i, doc in indexed]
    groups = Counter(record_group(doc) for _, doc in indexed)
    return [(None, f"{g}: {plural(n, 'record')}") for g, n in groups.items()]


def shape(obj, file_name: str = "") -> str:
    # "document": one Frappe document (a DocType, Report, Print Format, Workspace, a
    # customize file); "records": a list of them (fixtures, test records, whose doctype
    # Frappe may take from their folder); else "other", e.g. a chart of accounts.
    if type(obj) is dict:
        return "document" if "doctype" in obj else "other"
    if type(obj) is list and all(
        type(d) is dict and ("doctype" in d or file_name == "test_records.json")
        for d in obj
    ):
        return "records"
    return "other"


def doc_title(doc: dict) -> str:
    # A child table row (a Workspace Link, say) is named by a hash: use its label, and
    # say whose row it is. A test record often has no name: try the fields that name
    # one of its doctype.
    doctype = doc.get("doctype")
    scrubbed = f"{doctype}".lower().replace(" ", "_").replace("-", "_")
    keys = (
        ("label", "title", "name") if doc.get("parent") else ("name", "title", "label")
    )
    keys += (f"{scrubbed}_name", scrubbed, "item_code", "email", "subject")
    name = next((doc[k] for k in keys if doc.get(k)), None)
    if name is None and ("custom_fields" in doc or "property_setters" in doc):
        title = f"Customizations: {doctype}"
    else:
        title = f"{name}" if name is not None else "(no name)"
        if doctype is not None:
            parent = f" in {doc['parent']}" if doc.get("parent") else ""
            title = f"{doctype}{parent}: {title}"
    return " ".join(title.split())  # one line


def record_group(doc: dict) -> str:
    # what a record belongs to: a child row's parent, a Custom Field's or Property
    # Setter's doctype
    group = f"{doc.get('doctype', 'Record')}"
    if doc.get("parent"):
        group += f" in {doc['parent']}"
    if for_doctype := doc.get("dt") or doc.get("doc_type"):
        group += f" for {for_doctype}"
    return " ".join(group.split())


def plural(n: int, noun: str) -> str:
    return f"{n} {noun}{'s' * (n != 1)}"


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


def side_text(sign: str, text: str) -> Text:
    # A multi-line value only one side has: each line marked, as in a hunk.
    style = "red" if sign == "-" else "green"
    lines = (f"{sign} {line}" for line in text.splitlines())
    return Text("\n".join(lines), style=style, tab_size=4)


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

    # path old-file old-hex old-mode new-file new-hex new-mode [new-path xfrm-msg]: an added
    # or deleted file has /dev/null and "." on its missing side, and a renamed one gets
    # its new path after them
    path = sys.argv[1]
    old_path = sys.argv[2]
    old_hex = sys.argv[3]
    new_path = sys.argv[5]
    new_hex = sys.argv[6]
    renamed_to = sys.argv[8] if len(sys.argv) > 8 else ""
    table_mode = int(os.getenv("TABLE_MODE"))

    extensions = [p.rsplit(".", maxsplit=1)[-1] for p in (path, renamed_to or path)]
    if "json" in extensions:
        name = (renamed_to or path).split("/")[-1]
        only = "+" if old_hex == "." else "-" if new_hex == "." else ""
        if only == "-":
            console.log(f"[bold][red]Removed: {escape(name)}[/red][/bold]")
        elif only == "+":
            console.log(f"[bold][green]Added: {escape(name)}[/green][/bold]")
        elif renamed_to:
            old_name = escape(path.split("/")[-1])
            console.log(f"[bold]Renamed: {old_name} → {escape(name)}[/bold]")
        if "custom" in (old_path if only == "-" else new_path):
            console.log(f"[bold][magenta]Custom File:[/magenta][/bold]")
        diff = FrappeDiff(old_path, new_path, table_mode, name, only)
        try:
            diff.prep()
            diff.print()
        except (ValueError, RecursionError) as e:
            # Files added, deleted, or renamed from or to another type were skipped before:
            # don't fail on one that can't be read or shown.
            if not only and extensions[0] == extensions[1]:
                raise
            console.log(f"{escape(name)} can't be shown: {type(e).__name__}")
        console.log()
