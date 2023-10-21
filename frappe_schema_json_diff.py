#!/usr/bin/env python3
import sys
import os
import json
import re
from dataclasses import dataclass

from json_source_map import calculate

from rich.console import Console
from rich.tree import Tree
from rich.table import Table

@dataclass
class FrappeDiff:
    old_path: str
    old_hex: str
    new_path: str
    new_hex: str
    print_table: str

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
        self.label = f"[bold]{new_path.split('/')[-1]}[/bold]"

    def prep_table(self) -> None:
        table = Table(
            title=self.label,
            title_justify="left",
            show_lines=True,
            title_style="bold",
            expand=True,
        )
        table.add_column("L#, Path", ratio=1)
        table.add_column("Key or Element", ratio=1)
        table.add_column("Value", ratio=1)
        self.table = table

    def print(self):
        self.tree = self.dict_diff(
            self.label,
            self.base_obj,
            self.head_obj,
        )
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

        dict_tree = Tree(name)

        for bk, bk_v in base_dict.items():
            # concatenated path for passing to table/tree constructor functions: red_kvp, grn_kvp, mod_kvp
            self.conc_b_path = f"{b_path}/{bk}"
            if bk in head_dict:
                hk_v = head_dict[bk]
                self.conc_h_path = f"{h_path}/{bk}"
                if type(bk_v) is list and (bk_v or hk_v):
                    # If no differences, None is returned
                    rtree = self.list_diff(
                        bk, bk_v, hk_v, self.conc_b_path, self.conc_h_path
                    )
                    if rtree.children:
                        dict_tree.add(rtree)
                elif type(bk_v) is dict:
                    rtree = self.dict_diff(
                        bk, bk_v, hk_v, self.conc_b_path, self.conc_h_path
                    )
                    if rtree.children:
                        dict_tree.add(rtree)
                elif bk_v != hk_v and not (bk == "modified" or bk == "modified_by"):
                    self.mod_kvp(bk, f"{bk_v}", f"{hk_v}", dict_tree)
            else:
                self.red_kvp(bk, f"{bk_v}", dict_tree)
        for hk in list(set(head_dict) - set(base_dict)):
            self.grn_kvp(hk, f"{head_dict[hk]}", dict_tree)
        return dict_tree

    def red_kvp(self, key: str, value: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]{self.base_ln.key(self.conc_b_path)}[/bold] {self.conc_b_path}",
                key,
                value,
                style="red",
            )
        else:
            tree.add(
                f"[red][bold]{self.base_ln.key(self.conc_b_path)}[/bold] {key} : {value}[/red]"
            )

    def grn_kvp(self, key: str, value: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]{self.head_ln.key(self.conc_h_path)}[/bold] {self.conc_h_path}",
                key,
                value,
                style="green",
            )
        else:
            tree.add(
                f"[green][bold]{self.base_ln.key(self.conc_h_path)}[/bold] {key} : {value}[/green]"
            )

    def mod_kvp(self, key: str, b_val: str, h_val: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]{self.base_ln.key(self.conc_b_path)}[/bold] {self.conc_b_path}",
                f"[default]{key}[/default]",
                b_val,
                style="red",
            )
            self.table.add_row(
                f"[bold]{self.head_ln.key(self.conc_h_path)}[/bold] {self.conc_h_path}",
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

    def list_diff(
        self,
        name: str,
        base_list: list,
        head_list: list,
        b_path: str,
        h_path: str,
    ) -> Tree:

        list_tree = Tree(name)
        self.common_key = None
        isdict = False

        # one (and only one) list may be empty
        mt_handler = base_list or head_list
        if type(mt_handler[0]) is dict:
            isdict = self.get_common_key(name, mt_handler)

        if base_list and head_list and isdict:
            # Create sets of values of common keys for lists of dicts
            head_dicts = {k[self.common_key] for k in head_list}
            base_dicts = {k[self.common_key] for k in base_list}
            deleted_dict_keys, added_dict_keys = symmetric_diff_sep(
                base_dicts, head_dicts
            )
            diff_dict_keys = head_dicts - added_dict_keys

            for i, bd in enumerate(base_list):
                bd_kv = bd[self.common_key]
                conc_b_path = f"{b_path}/{i}"
                if bd_kv in deleted_dict_keys:
                    self.red_dict(bd, conc_b_path, list_tree)
                    deleted_dict_keys.remove(bd_kv)
                else:
                    for j, hd in enumerate(head_list):
                        hd_kv = hd[self.common_key]
                        conc_h_path = f"{h_path}/{j}"
                        if bd_kv == hd_kv and bd_kv in diff_dict_keys:
                            rtree = self.dict_diff(
                                bd_kv, bd, hd, conc_b_path, conc_h_path
                            )
                            diff_dict_keys.remove(bd_kv)
                            if rtree.children:
                                list_tree.add(rtree)
                        elif hd_kv in added_dict_keys:
                            self.grn_dict(hd, conc_h_path, list_tree)
                            added_dict_keys.remove(hd_kv)
        elif isdict:
            for i, d in enumerate(base_list):
                self.red_dict(d, f"{b_path}/{i}", list_tree)
            for i, d in enumerate(head_list):
                self.grn_dict(d, f"{h_path}/{i}", list_tree)
        else:
            del_set, add_set = symmetric_diff_sep(set(base_list), set(head_list))
            for i, e in enumerate(base_list):
                if e in del_set:
                    self.red_elem(e, f"{b_path}/{i}", list_tree)
                    del_set.remove(e)
            for i, e in enumerate(head_list):
                if e in add_set:
                    self.grn_elem(e, f"{h_path}/{i}", list_tree)
                    add_set.remove(e)

        return list_tree

    def get_common_key(self, name: str, dict_list: list) -> True:
        common_keys = {
            "fields": "fieldname",
            "permissions": "role",
            "actions": "label",
            "links": "link_doctype",
            "custom_fields": "fieldname",
            "property_setters": "field_name",
        }

        if name in common_keys:
            self.common_key = common_keys[name]
        else:
            # https://stackoverflow.com/a/13985856/14410691
            common_keys = set.intersection(*map(set, dict_list))
            final_keys = []
            for key in self.common_keys:
                # find common keys with unique values. If multiple, pick one to use
                if len(dict_list) == len({[d[key] for d in dict_list]}):
                    final_keys.append(key)
                try:
                    self.common_key = final_keys[0]
                except IndexError:
                    print(
                        "No unique common_key : values - dictionaries can't be diffed based on content"
                    )
        return True

    def red_elem(self, elem: str, path: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]{self.base_ln.val(path)}[/bold] {path}", elem, "", style="red"
            )
        else:
            tree.add(f"[red][bold]{self.base_ln.val(path)}[/bold] {elem}[/red]")

    def grn_elem(self, elem: str, path: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]{self.head_ln.val(path)}[/bold] {path}", elem, "", style="green"
            )
        else:
            tree.add(f"[green][bold]{self.head_ln.val(path)}[/bold] {elem}[/green]")

    def red_dict(self, bdict: dict, path: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]{self.head_ln.val(path)}[/bold] {path}",
                bdict[self.common_key],
                "[bold magenta]VALUES BELOW[/bold magenta]",
                style="red",
            )
            for k, v in bdict.items():
                self.table.add_row(
                    f"[bold magenta]In Dict:[/bold magenta] {bdict[self.common_key]}",
                    k,
                    f"{v}",
                    style="red",
                )
        else:
            dict_tree = tree.add(
                f"[red][bold]{self.base_ln.val(path)}[/bold] {bdict[self.common_key]}[/red]"
            )
            for k, v in bdict.items():
                dict_tree.add(f"[red]{k} : {v}[/red]")

    def grn_dict(self, hdict: dict, path: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]{self.head_ln.val(path)}[/bold] {path}",
                hdict[self.common_key],
                "[bold magenta]VALUES BELOW[/bold magenta]",
                style="green",
            )
            for k, v in hdict.items():
                self.table.add_row(
                    f"[bold magenta]In Dict:[/bold magenta] {hdict[self.common_key]}",
                    k,
                    f"{v}",
                    style="green",
                )
        else:
            dict_tree = tree.add(
                f"[green][bold]{self.head_ln.val(path)}[/bold] {hdict[self.common_key]}[/green]"
            )
            for k, v in hdict.items():
                dict_tree.add(f"[green]{k} : {v}[/green]")


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


def print_custom(path: str) -> None:
    if re.search("\/custom\/.*\.json", path):
        console.log(f"[bold magenta]Custom File[/bold magenta]")


if __name__ == "__main__":

    # https://github.com/azrafe7/test_python_rich_on_gh_pages/blob/0015be3b6b1925c4d4c9acbaed319666ff7cec89/main.py
    console = Console(force_terminal=True, log_time=False, log_path=False)
    
    print(sys.argv)
    old_path = sys.argv[2]
    old_hex = sys.argv[3]
    new_path = sys.argv[5]
    new_hex = sys.argv[6]
    table_mode = os.getenv("TABLE_MODE")

    try:
        if sys.argv[2].split('.')[-1] == 'json' or sys.argv[5].split('.')[-1] == 'json':
            if sys.argv[6] == '.':
                console.log(f"[bold][red]Removed: {sys.argv[2].split('/')[-1]}[/red][/bold]")
            else:
                diff = FrappeDiff(old_path, old_hex, new_path, new_hex, table_mode)
                diff.prep()
                diff.print()
    except Exception as e:
        print(e)
    console.log("\n")


