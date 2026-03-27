package main

import (
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"strings"
)

const (
	red    = "\033[31m"
	green  = "\033[32m"
	bold   = "\033[1m"
	reset  = "\033[0m"
	magenta = "\033[35m"
)

type Tree struct {
	Name     string
	Children []Tree
}

type FrappeDiff struct {
	OldPath   string
	NewPath   string
	TableMode int
	baseObj   interface{}
	headObj   interface{}
	label     string
}

func (d *FrappeDiff) prep() {
	d.baseObj = d.getFile(d.OldPath)
	d.headObj = d.getFile(d.NewPath)
	d.makeLabel()
}

func (d *FrappeDiff) getFile(path string) interface{} {
	data, _ := os.ReadFile(path)
	var v interface{}
	json.Unmarshal(data, &v)
	return v
}

func (d *FrappeDiff) makeLabel() {
	parts := strings.Split(d.NewPath, "/")
	d.label = parts[len(parts)-1]
}

func (d *FrappeDiff) print() {
	var tree Tree
	if baseList, ok := d.baseObj.([]interface{}); ok {
		tree = d.listDiff(d.label, baseList, interfaceToList(d.headObj), "", "")
	} else if baseDict, ok := d.baseObj.(map[string]interface{}); ok {
		tree = d.dictDiff(d.label, baseDict, interfaceToMap(d.headObj), "", "")
	}
	if len(tree.Children) > 0 {
		printTree(tree, "")
	} else {
		fmt.Println(d.label)
	}
}

func interfaceToList(v interface{}) []interface{} {
	if l, ok := v.([]interface{}); ok {
		return l
	}
	return nil
}

func interfaceToMap(v interface{}) map[string]interface{} {
	if m, ok := v.(map[string]interface{}); ok {
		return m
	}
	return nil
}

func printTree(t Tree, indent string) {
	fmt.Print(indent)
	fmt.Print(t.Name)
	fmt.Println(reset)
	for _, c := range t.Children {
		printTree(c, indent+"  ")
	}
}

func (d *FrappeDiff) dictDiff(name string, base, head map[string]interface{}, bPath, hPath string) Tree {
	t := Tree{Name: name}
	for bk, bv := range base {
		concB := bPath + "/" + bk
		if hv, ok := head[bk]; ok {
			concH := hPath + "/" + bk
			if bl, ok := bv.([]interface{}); ok {
				if hl, ok := hv.([]interface{}); ok && (len(bl) > 0 || len(hl) > 0) {
					rt := d.listDiff(bk, bl, hl, concB, concH)
					if len(rt.Children) > 0 {
						t.Children = append(t.Children, rt)
					}
				}
			} else if bd, ok := bv.(map[string]interface{}); ok {
				if hd, ok := hv.(map[string]interface{}); ok {
					rt := d.dictDiff(bk, bd, hd, concB, concH)
					if len(rt.Children) > 0 {
						t.Children = append(t.Children, rt)
					}
				}
			} else if !reflect.DeepEqual(bv, hv) && bk != "modified" && bk != "modified_by" && bk != "creation" {
				if bk != "format_data" {
					d.modKVP(bk, fmt.Sprintf("%v", bv), fmt.Sprintf("%v", hv), &t, concB, concH)
				} else {
					rt := d.pfDiff(bk, bv, hv, concB, concH)
					if len(rt.Children) > 0 {
						t.Children = append(t.Children, rt)
					}
				}
			}
		} else {
			d.redKVP(bk, fmt.Sprintf("%v", bv), &t, concB)
		}
	}
	for hk := range head {
		if _, ok := base[hk]; !ok {
			d.grnKVP(hk, fmt.Sprintf("%v", head[hk]), &t, hPath+"/"+hk)
		}
	}
	return t
}

func (d *FrappeDiff) redKVP(k, v string, t *Tree, p string) {
	t.Children = append(t.Children, Tree{Name: red + bold + "- " + p + " " + k + " : " + v + reset})
}

func (d *FrappeDiff) grnKVP(k, v string, t *Tree, p string) {
	t.Children = append(t.Children, Tree{Name: green + bold + "+ " + p + " " + k + " : " + v + reset})
}

func (d *FrappeDiff) modKVP(k, bv, hv string, t *Tree, bp, hp string) {
	t.Children = append(t.Children, Tree{Name: k + " : " + red + bv + " => " + green + hv + reset})
}

func (d *FrappeDiff) listDiff(name string, base, head []interface{}, bPath, hPath string) Tree {
	t := Tree{Name: name}
	if len(base) == 0 && len(head) == 0 {
		return t
	}
	mt := base
	if len(base) == 0 {
		mt = head
	}
	isDict := false
	if len(mt) > 0 {
		_, isDict = mt[0].(map[string]interface{})
	}
	if len(base) > 0 && len(head) > 0 && isDict {
		key := d.getCommonKey(name, mt)
		bSet := map[string]bool{}
		hSet := map[string]bool{}
		for _, item := range base {
			if m, ok := item.(map[string]interface{}); ok {
				if v, ok := m[key].(string); ok {
					bSet[v] = true
				}
			}
		}
		for _, item := range head {
			if m, ok := item.(map[string]interface{}); ok {
				if v, ok := m[key].(string); ok {
					hSet[v] = true
				}
			}
		}
		del := map[string]bool{}
		add := map[string]bool{}
		for k := range bSet {
			if !hSet[k] {
				del[k] = true
			}
		}
		for k := range hSet {
			if !bSet[k] {
				add[k] = true
			}
		}
		diff := map[string]bool{}
		for k := range hSet {
			if !add[k] {
				diff[k] = true
			}
		}
		for i, bd := range base {
			if m, ok := bd.(map[string]interface{}); ok {
				if kv, ok := m[key].(string); ok {
					concB := fmt.Sprintf("%s/%d", bPath, i)
					if del[kv] {
						d.redDict(m, concB, &t, key)
						delete(del, kv)
					} else if diff[kv] {
						for j, hd := range head {
							if m2, ok := hd.(map[string]interface{}); ok {
								if hv, ok := m2[key].(string); ok && kv == hv {
									rt := d.dictDiff(kv, m, m2, concB, fmt.Sprintf("%s/%d", hPath, j))
									if len(rt.Children) > 0 {
										t.Children = append(t.Children, rt)
									}
									delete(diff, kv)
									break
								}
							}
						}
					}
				}
			}
		}
		for i, hd := range head {
			if m, ok := hd.(map[string]interface{}); ok {
				if kv, ok := m[key].(string); ok && add[kv] {
					d.grnDict(m, fmt.Sprintf("%s/%d", hPath, i), &t, key)
					delete(add, kv)
				}
			}
		}
	} else if isDict {
		key := d.getCommonKey(name, mt)
		for i, item := range base {
			if m, ok := item.(map[string]interface{}); ok {
				d.redDict(m, fmt.Sprintf("%s/%d", bPath, i), &t, key)
			}
		}
		for i, item := range head {
			if m, ok := item.(map[string]interface{}); ok {
				d.grnDict(m, fmt.Sprintf("%s/%d", hPath, i), &t, key)
			}
		}
	} else {
		del := map[interface{}]bool{}
		for _, e := range base {
			del[e] = true
		}
		for _, e := range head {
			if del[e] {
				delete(del, e)
			}
		}
		add := map[interface{}]bool{}
		for _, e := range head {
			add[e] = true
		}
		for i, e := range base {
			if del[e] {
				d.redElem(e, fmt.Sprintf("%s/%d", bPath, i), &t)
				delete(del, e)
			}
		}
		for i, e := range head {
			if add[e] {
				d.grnElem(e, fmt.Sprintf("%s/%d", hPath, i), &t)
				delete(add, e)
			}
		}
	}
	return t
}

func (d *FrappeDiff) getCommonKey(name string, list []interface{}) string {
	m := map[string]string{
		"custom_fields":    "fieldname",
		"fields":           "fieldname",
		"actions":          "label",
		"links":            "link_to", // fixed
		"property_setters": "name",
		"custom_perms":     "role",
		"permissions":      "role",
		"roles":            "role",
		"states":           "state",
		"transitions":      "state",
		"format_data":      "fieldname",
	}
	if k, ok := m[name]; ok {
		return k
	}
	if strings.Contains(name, ".json") {
		return "name"
	}
	return "name"
}

func (d *FrappeDiff) redDict(m map[string]interface{}, path string, t *Tree, key string) {
	kv := fmt.Sprintf("%v", m[key])
	dt := Tree{Name: red + bold + "- " + path + " " + kv + reset}
	for k, v := range m {
		dt.Children = append(dt.Children, Tree{Name: red + "- " + k + " : " + fmt.Sprintf("%v", v) + reset})
	}
	t.Children = append(t.Children, dt)
}

func (d *FrappeDiff) grnDict(m map[string]interface{}, path string, t *Tree, key string) {
	kv := fmt.Sprintf("%v", m[key])
	dt := Tree{Name: green + bold + "+ " + path + " " + kv + reset}
	for k, v := range m {
		dt.Children = append(dt.Children, Tree{Name: green + "+ " + k + " : " + fmt.Sprintf("%v", v) + reset})
	}
	t.Children = append(t.Children, dt)
}

func (d *FrappeDiff) redElem(e interface{}, path string, t *Tree) {
	t.Children = append(t.Children, Tree{Name: red + bold + "- " + path + " " + fmt.Sprintf("%v", e) + reset})
}

func (d *FrappeDiff) grnElem(e interface{}, path string, t *Tree) {
	t.Children = append(t.Children, Tree{Name: green + bold + "+ " + path + " " + fmt.Sprintf("%v", e) + reset})
}

func (d *FrappeDiff) pfDiff(name string, base, head interface{}, bPath, hPath string) Tree {
	bl := interfaceToList(base)
	hl := interfaceToList(head)
	return d.listDiff(name, bl, hl, bPath, hPath)
}

func main() {
	if len(os.Args) < 6 {
		return
	}
	oldPath := os.Args[2]
	newPath := os.Args[5]
	newHex := os.Args[6]
	if !strings.HasSuffix(oldPath, ".json") {
		return
	}
	if newHex == "." {
		fmt.Printf("%s[bold][red]Removed: %s%s\n", red, strings.Split(oldPath, "/")[len(strings.Split(oldPath, "/"))-1], reset)
		return
	}
	if strings.Contains(newPath, "custom") {
		fmt.Printf("%s[bold][magenta]Custom File:%s\n", magenta, reset)
	}
	fd := FrappeDiff{OldPath: oldPath, NewPath: newPath}
	fd.prep()
	fd.print()
	fmt.Println()
}
