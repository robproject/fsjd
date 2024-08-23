# CHANGELOG

## v2.1.1 (2024-08-23)

### Fix

* fix: finish common key var separation (#17) ([`6053cef`](https://github.com/robproject/fsjd/commit/6053cef15965f4d638a2090b9897a36560455940))

## v2.1.0 (2024-08-23)

### Feature

* feat: handle fixtures (#15) ([`6e93e1c`](https://github.com/robproject/fsjd/commit/6e93e1c0d288a79ef05c2f5fc708a62b48032afd))

### Unknown

* Fix tree add green kvp (#13)

* test: add launch config

* fix: head path for tree view ([`81fd1c6`](https://github.com/robproject/fsjd/commit/81fd1c64058b87424dbff342fce2012ce311ff6d))

## v2.0.5 (2024-03-23)

### Fix

* fix: release v2.0.5 ([`b0ddfd5`](https://github.com/robproject/fsjd/commit/b0ddfd5201b684de4244e83544dc20e54a0b2b8f))

## v2.0.4 (2024-03-23)

### Fix

* fix: v2.0.4 ([`3de3a9b`](https://github.com/robproject/fsjd/commit/3de3a9b056e60df2b877473bddaad0ad1b9240fe))

* fix: remove console detection draft ([`dd8af8b`](https://github.com/robproject/fsjd/commit/dd8af8bdfb366a1af9761b161057e92ec262a26a))

* fix: refactor diff, release, and ci

Remove unused regex in diff.
Refactor release ci.
Upgrade diff ci script version and refactor branch. ([`bcfb91a`](https://github.com/robproject/fsjd/commit/bcfb91a12be4b32dedd815b41e88ccecd39187da))

* fix: v2 update ci (#9)

Co-authored-by: Robert Duncan &lt;robir@puter.lan&gt; ([`4461a74`](https://github.com/robproject/fsjd/commit/4461a7498ca10f323e217781697ad544ffb5878b))

* fix: clear history, refactor, and fix issues

Fix common key handling; add key for custom permission.
Fix table mode dictionary deletion.

Refs: #7, #8 ([`ac998c2`](https://github.com/robproject/fsjd/commit/ac998c24b5e4f2c6971acc4f979575afb8503fc9))

### Unknown

* V2 update ci (#10)

* fix: v2 update ci

* fix: ci release

---------

Co-authored-by: Robert Duncan &lt;robir@puter.lan&gt; ([`8ff8df0`](https://github.com/robproject/fsjd/commit/8ff8df0e112000373661c70c7b4f85591ecb866d))

## v2.0.1 (2023-10-21)

### Fix

* fix: update workflow

Should have been committed in v2.0.0 release ([`d35e7ea`](https://github.com/robproject/fsjd/commit/d35e7eae925655ef65dafd678356bc6db3f5ed02))

## v2.0.0 (2023-10-21)

### Breaking

* feat!: use GIT_EXTERNAL_DIFF

Remove all file preparation, now handled by git.
Remove submodule.
Rework sample workflow.
Update doc.
Rework diff script to be used by GIT_EXTERNAL_DIFF.
Remove VSCode launch config.

BREAKING CHANGE: Total rework ([`850cc7b`](https://github.com/robproject/fsjd/commit/850cc7b5a9cf92b3f0bbe8e89667d9cc4cb2979b))

### Chore

* chore: update submodule, gha example ([`acf3d67`](https://github.com/robproject/fsjd/commit/acf3d67e0231ca8ac99125b0bd2bf7d6a651c966))

* chore: update submodule ([`34cce12`](https://github.com/robproject/fsjd/commit/34cce1241a4d146ae729bc01b756fb12ece5d089))

* chore: update submodule ([`d78d7cc`](https://github.com/robproject/fsjd/commit/d78d7ccc0967d9e902d5b416cdcea72d2aa0c506))

### Test

* test: modified file ([`046ae06`](https://github.com/robproject/fsjd/commit/046ae068afe1df27291634c54cc6e516c7734e05))

### Unknown

* Update README.md ([`45faf55`](https://github.com/robproject/fsjd/commit/45faf55ab4ffeea37482da01add8a5610d09c631))

* Update README.md ([`f52442a`](https://github.com/robproject/fsjd/commit/f52442af2f057d0a16cc26fff3a363b760bc1b6a))

## v1.0.2 (2022-08-12)

### Chore

* chore: update submodule ([`fb4b9c0`](https://github.com/robproject/fsjd/commit/fb4b9c0fe2f2363c148df68be3e049681e89e171))

* chore: update submodule ([`d69a7db`](https://github.com/robproject/fsjd/commit/d69a7db5505204f7915b646c038c6313537283a9))

### Fix

* fix: modified and modified_by keys ignored ([`e4f6634`](https://github.com/robproject/fsjd/commit/e4f66341c4e56395f31bf9f81bd28bc90a0b6e63))

## v1.0.1 (2022-08-12)

### Fix

* fix: script clone depth 1 ([`6f0a277`](https://github.com/robproject/fsjd/commit/6f0a277dd5ba4d6e584f756e29fdc989ea214b80))

### Unknown

* wip: readme format ([`d859094`](https://github.com/robproject/fsjd/commit/d859094e7e573f8c6dbd1528f86e6308196c1e59))

## v1.0.0 (2022-08-11)

### Chore

* chore: update submodule ([`a81f43c`](https://github.com/robproject/fsjd/commit/a81f43cfbc9a62b3fa88a7c410461eb35f1eb18b))

### Feature

* feat: v1.0.0 ([`f4e6bb6`](https://github.com/robproject/fsjd/commit/f4e6bb69d6f6e83cd04000c2b720ff36ae6f37af))

* feat: v1.0.0 ([`30a0b6a`](https://github.com/robproject/fsjd/commit/30a0b6a3aabad494fe8f494455f6fc77b0a2ee07))

* feat: readme, test config ([`2fdca7a`](https://github.com/robproject/fsjd/commit/2fdca7a586f43ed829725391adab172689b41c00))

### Fix

* fix: submodule update to handle json decode errors&#39; ([`a367378`](https://github.com/robproject/fsjd/commit/a367378295b481f0155fecd0019fd2f5ec15f240))

* fix: formatting ([`3a2a3ed`](https://github.com/robproject/fsjd/commit/3a2a3ed74bbba9799ba4ffe006d706602febcddc))

* fix: update paths ([`aa1c7b9`](https://github.com/robproject/fsjd/commit/aa1c7b903ee452d3beff097bcac736451897024a))

* fix: remove tree sample run ([`6646f96`](https://github.com/robproject/fsjd/commit/6646f968f1c8e34df2c156e1b5838792f9a3047d))

* fix: separate diff runs ([`0bbe4d5`](https://github.com/robproject/fsjd/commit/0bbe4d5353c11616526b79bc16e7b12256b4c28e))

* fix: main.yml ([`0eeb2ad`](https://github.com/robproject/fsjd/commit/0eeb2adb12542067221482e0d05a17f1601e7a7b))

* fix: add both output views ([`6903b4b`](https://github.com/robproject/fsjd/commit/6903b4bbc024adcf7b685bda513311454baee2f3))

* fix: update file path ([`0fdd3fb`](https://github.com/robproject/fsjd/commit/0fdd3fb7d3656f79d0746b3feb686b85576b2e01))

* fix: base commit won&#39;t conflict ([`0fe5b79`](https://github.com/robproject/fsjd/commit/0fe5b79b76c270680f592a0ff7ad2fb9e54a64b2))

### Unknown

* wip: update readme CI example ([`6b79d9d`](https://github.com/robproject/fsjd/commit/6b79d9d0c4d847c27dbce149a8912cc0aec7920d))

* wip: readme format ([`3d31d03`](https://github.com/robproject/fsjd/commit/3d31d039ed2aecc1ff79d7c37596dcd03cfc92ee))

* wip: readme photos ([`eafe230`](https://github.com/robproject/fsjd/commit/eafe23048d49de1bd56c3584fed59b29be331a46))

* wip: update readme ([`32fd300`](https://github.com/robproject/fsjd/commit/32fd3001a81a66e274b6202efe2ef23232e0e0bf))

* wip: sample doctype json ([`5e15c6f`](https://github.com/robproject/fsjd/commit/5e15c6fc446c2de8549191f52d00655585c7d6b2))

* wip: formatting ([`130bd85`](https://github.com/robproject/fsjd/commit/130bd852147b3df4768ba365d6a5cf9f79566067))

* wip: update submodule ([`dcb2128`](https://github.com/robproject/fsjd/commit/dcb21283b282018a150ea3bc6a1a1f603f8a88b0))

* first commit ([`9644d25`](https://github.com/robproject/fsjd/commit/9644d258c927b13df1e31ff7b651a7105477b9c9))

* Initial commit ([`035eae4`](https://github.com/robproject/fsjd/commit/035eae400ecf7ddc8a15b4c3b9cc32b03cda3f7d))
