#!/usr/bin/env python3
from dataclasses import dataclass
import difflib
import os
import json
from typing import Optional
import sys

from json_source_map import calculate
from rich.console import Console
from rich.table import Table
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
        self.label = f"[bold]{new_path.split('/')[-1]}[/bold]"

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
                self.label,
                self.base_obj,
                self.head_obj,
            )
        elif isinstance(self.base_obj, dict):
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
                elif bk_v != hk_v and not bk in ("modified", "modified_by", "creation"):
                    # for value diff of html, code, text fields:
                    # feed difflib with the 'printed' version; don't include so many json escapes. need to expand the 'options' field for Custom HTML dicts and put it in the list
                    if bk != "format_data":
                        self.mod_kvp(bk, f"{bk_v}", f"{hk_v}", dict_tree)
                    else:
                        rtree = self.pf_diff(
                            bk, bk_v, hk_v, self.conc_b_path, self.conc_h_path
                        )
                        if rtree.children:
                            dict_tree.add(rtree)
            else:
                self.red_kvp(bk, f"{bk_v}", dict_tree)
        for hk in list(set(head_dict) - set(base_dict)):
            self.grn_kvp(hk, f"{head_dict[hk]}", dict_tree)
        return dict_tree

    def red_kvp(self, key: str, value: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]- {self.base_ln.key(self.conc_b_path)}[/bold] {self.conc_b_path}",
                key,
                value,
                style="red",
            )
        else:
            tree.add(
                f"[red][bold]- {self.base_ln.key(self.conc_b_path)}[/bold] {key} : {value}[/red]"
            )

    def grn_kvp(self, key: str, value: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]+ {self.head_ln.key(self.conc_h_path)}[/bold] {self.conc_h_path}",
                key,
                value,
                style="green",
            )
        else:
            tree.add(
                f"[green][bold]+ {self.head_ln.key(self.conc_h_path)}[/bold] {key} : {value}[/green]"
            )

    def mod_kvp(self, key: str, b_val: str, h_val: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]- {self.base_ln.key(self.conc_b_path)}[/bold] {self.conc_b_path}",
                f"[default]{key}[/default]",
                b_val,
                style="red",
            )
            self.table.add_row(
                f"[bold]+ {self.head_ln.key(self.conc_h_path)}[/bold] {self.conc_h_path}",
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
        b_path: str = "",
        h_path: str = "",
    ) -> Tree:

        list_tree = Tree(name)

        # one (and only one) list may be empty
        mt_handler = base_list or head_list
        if isdict := type(mt_handler[0]) is dict:
            # New common_key per call of list_diff.
            common_key = self.get_common_key(name, mt_handler)

        if base_list and head_list and isdict:
            # Create sets of values of common keys for lists of dicts
            head_dicts = {k[common_key] for k in head_list}
            base_dicts = {k[common_key] for k in base_list}
            deleted_dict_keys, added_dict_keys = symmetric_diff_sep(
                base_dicts, head_dicts
            )
            diff_dict_keys = head_dicts - added_dict_keys

            for i, bd in enumerate(base_list):
                bd_kv = bd[common_key]
                conc_b_path = f"{b_path}/{i}"
                if bd_kv in deleted_dict_keys:
                    self.red_dict(bd, conc_b_path, list_tree, common_key)
                    deleted_dict_keys.remove(bd_kv)
                else:
                    for j, hd in enumerate(head_list):
                        hd_kv = hd[common_key]
                        conc_h_path = f"{h_path}/{j}"
                        if bd_kv == hd_kv and bd_kv in diff_dict_keys:
                            rtree = self.dict_diff(
                                bd_kv, bd, hd, conc_b_path, conc_h_path
                            )
                            diff_dict_keys.remove(bd_kv)
                            if rtree.children:
                                list_tree.add(rtree)
                        elif hd_kv in added_dict_keys:
                            self.grn_dict(hd, conc_h_path, list_tree, common_key)
                            added_dict_keys.remove(hd_kv)
        elif isdict:
            for i, d in enumerate(base_list):
                self.red_dict(d, f"{b_path}/{i}", list_tree, common_key)
            for i, d in enumerate(head_list):
                self.grn_dict(d, f"{h_path}/{i}", list_tree, common_key)
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

    def pf_diff(
        self,
        name: str,
        base_list: str,
        head_list: str,
        b_path: str,
        h_path: str,
    ) -> Tree:

        list_tree = Tree(name)
        base_list = json.loads(base_list)  # dict value =
        head_list = json.loads(head_list)

        # each list contains dicts with keys "fieldname" and "fieldtype", and any number of additions, deletions, modifications, and duplications
        # group by field type such that common key can be added via hash of name, type, and position for standard fields
        # common key is only name and type for custom fields

        for i, bd in enumerate(base_list):
            if bd["fieldtype"] == "Custom HTML":
                bd_kv = bd["fieldname"]
                conc_b_path = f"{b_path}/{i}"
                if (len(head_list) - 1) > i and head_list[i][
                    "fieldtype"
                ] == "Custom HTML":
                    hd_kv = head_list[i]["fieldname"]
                    conc_h_path = f"{h_path}/{i}"
                    if bd_kv == hd_kv:
                        rtree = self.dict_diff(
                            bd_kv, bd, head_list[i], conc_b_path, conc_h_path
                        )
                        if rtree.children:
                            list_tree.add(rtree)
                for j, hd in enumerate(head_list):
                    if hd["fieldtype"] == "Custom HTML":
                        hd_kv = hd["fieldname"]
                        conc_h_path = f"{h_path}/{j}"
                        if bd_kv == hd_kv:
                            rtree = self.dict_diff(
                                bd_kv, bd, hd, conc_b_path, conc_h_path
                            )
                            if rtree.children:
                                list_tree.add(rtree)
            conc_b_path = f"{b_path}/{i}"
            if bd_kv in deleted_dict_keys:
                self.red_dict(bd, conc_b_path, list_tree, common_key)
                deleted_dict_keys.remove(bd_kv)
            else:
                for j, hd in enumerate(head_list):
                    # !!! hd_kv = hd[self.common_key]
                    conc_h_path = f"{h_path}/{j}"
                    if bd_kv == hd_kv and bd_kv in diff_dict_keys:
                        rtree = self.dict_diff(bd_kv, bd, hd, conc_b_path, conc_h_path)
                        diff_dict_keys.remove(bd_kv)
                        if rtree.children:
                            list_tree.add(rtree)
                    elif hd_kv in added_dict_keys:
                        self.grn_dict(hd, conc_h_path, list_tree)
                        added_dict_keys.remove(hd_kv)
        # elif isdict:
        #    for i, d in enumerate(base_list):
        #        self.red_dict(d, f"{b_path}/{i}", list_tree)
        #    for i, d in enumerate(head_list):
        #        self.grn_dict(d, f"{h_path}/{i}", list_tree)
        # else:
        #    del_set, add_set = symmetric_diff_sep(set(base_list), set(head_list))
        #    for i, e in enumerate(base_list):
        #        if e in del_set:
        #            self.red_elem(e, f"{b_path}/{i}", list_tree)
        #            del_set.remove(e)
        #    for i, e in enumerate(head_list):
        #        if e in add_set:
        #            self.grn_elem(e, f"{h_path}/{i}", list_tree)
        #            add_set.remove(e)

        # return list_tree

    def get_common_key(self, name: str, dict_list: list) -> True:
        # Map parent to common key.
        common_keys = {
            "custom_fields": "fieldname",
            "fields": "fieldname",
            "actions": "label",
            # "links": "link_doctype",
            "links": "link_to",
            "property_setters": "name",
            "custom_perms": "role",
            "permissions": "role",
            "roles": "role",
            "states": "state",
            "transitions": "state",
        }
        if (key := common_keys.get(name)) is not None:
            return key
        elif ".json" in name:
            return "name"
        else:
            # Find common keys then return the first one with all unique values.
            # https://stackoverflow.com/a/13985856/14410691
            common_keys = set.intersection(*map(set, dict_list))
            for key in common_keys:
                if len(dict_list) == len(
                    set(d[key] for d in dict_list if d[key] is not None)
                ):
                    return key
            print(
                "No unique common_key : values - dictionaries can't be diffed based on content"
            )
            return

    def red_elem(self, elem: str, path: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]- {self.base_ln.val(path)}[/bold] {path}", elem, "", style="red"
            )
        else:
            tree.add(f"[red][bold]- {self.base_ln.val(path)}[/bold] {elem}[/red]")

    def grn_elem(self, elem: str, path: str, tree: Tree) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]+ {self.head_ln.val(path)}[/bold] {path}",
                elem,
                "",
                style="green",
            )
        else:
            tree.add(f"[green][bold]+ {self.head_ln.val(path)}[/bold] {elem}[/green]")

    def red_dict(self, bdict: dict, path: str, tree: Tree, common_key: str) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]- {self.base_ln.val(path)}[/bold] {path}",
                bdict[common_key],
                "[bold magenta]VALUES BELOW[/bold magenta]",
                style="red",
            )
            for k, v in bdict.items():
                self.table.add_row(
                    f"[bold magenta]In Dict:[/bold magenta] {bdict[common_key]}",
                    k,
                    f"{v}",
                    style="red",
                )
        else:
            dict_tree = tree.add(
                f"[red][bold]- {self.base_ln.val(path)}[/bold] {bdict[common_key]}[/red]"
            )
            for k, v in bdict.items():
                dict_tree.add(f"[red]- {k} : {v}[/red]")

    def grn_dict(self, hdict: dict, path: str, tree: Tree, common_key: str) -> None:
        if self.print_table:
            self.table.add_row(
                f"[bold]+ {self.head_ln.val(path)}[/bold] {path}",
                hdict[common_key],
                "[bold magenta]VALUES BELOW[/bold magenta]",
                style="green",
            )
            for k, v in hdict.items():
                self.table.add_row(
                    f"[bold magenta]In Dict:[/bold magenta] {hdict[common_key]}",
                    k,
                    f"{v}",
                    style="green",
                )
        else:
            dict_tree = tree.add(
                f"[green][bold]+ {self.head_ln.val(path)}[/bold] {hdict[common_key]}[/green]"
            )
            for k, v in hdict.items():
                dict_tree.add(f"[green]+ {k} : {v}[/green]")


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
            console.log(f"[bold][red]Removed: {old_path.split('/')[-1]}[/red][/bold]")
        else:
            if "custom" in new_path:
                console.log(f"[bold][magenta]Custom File:[/magenta][/bold]")
            diff = FrappeDiff(old_path, new_path, table_mode)
            diff.prep()
            diff.print()
        console.log()
