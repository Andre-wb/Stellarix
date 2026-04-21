# `bots_workspace/` — Gravitix Bot Projects (Runtime State)

On-disk workspace that the Vortex node uses to hold Gravitix bot source files and per-project permission metadata. **Runtime directory** — not source control, not hand-edited. Content here is created and rewritten by the node's IDE endpoints (`app/bots/ide_*`).

## File pairs

Each bot project is stored as a pair of files sharing a common prefix:

| File                           | Contains                                                             |
| ------------------------------ | -------------------------------------------------------------------- |
| `<prefix>_<slug>.grav`         | The Gravitix source code the user wrote / committed.                 |
| `<prefix>_<slug>_roles.json`   | Per-project permissions: who can edit, run, publish, read secrets.  |

`<prefix>` is one of:

| Prefix             | Meaning                                                               |
| ------------------ | --------------------------------------------------------------------- |
| `audit_proj_*`     | Sandboxed audit / linter test projects created by the CI pipeline.    |
| `e2e_comp_proj_*`  | Projects produced by the Playwright E2E compiler test suite.         |
| `<user>_*`         | Real user projects (owner slug + random suffix).                      |
| `marketplace_*`    | Staged copies of published marketplace bots.                          |

## Not for editing

- **Gitignore-worthy.** This directory shouldn't ship to end-users; PyInstaller explicitly omits it from the bundle.
- **Concurrent writes.** The node serialises writes behind `app/bots/ide_projects.py`; bypassing that and hand-editing may race with the IDE runner.
- **Permissions live here, not in the DB.** The `_roles.json` sibling is the single source of truth for who can do what inside a project. The DB has only the project metadata — name, owner, last commit hash.

## Cleaning

The IDE endpoint `DELETE /api/bots/ide/projects/<id>` removes both files atomically. For a full reset during development:

```bash
rm -rf bots_workspace/*                # dev only — stops all running bots
```

On production nodes, prefer the admin endpoint `/api/admin/bots/reset` — it tears down running interpreters and rotates any project-scoped secrets before deleting the files.

## Relation to marketplace

When a user publishes a bot to the marketplace (`POST /api/bots/marketplace/publish`), a signed snapshot of the `.grav` file is uploaded to the publisher's node. The local workspace copy is not shipped — every install is a fresh clone from the publisher's signed payload.

---

## License

Vortex is released under the **Apache License 2.0**.

```
Copyright 2026 Andrey Karavaev, Boris Maltsev

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## Authors

**Boris Maltsev**

[![GitHub](https://img.shields.io/badge/GitHub-BorisMalts-181717?style=flat-square&logo=github)](https://github.com/BorisMalts)

**Andrey Karavaev**

[![GitHub](https://img.shields.io/badge/GitHub-Andre--wb-181717?style=flat-square&logo=github)](https://github.com/Andre-wb)
