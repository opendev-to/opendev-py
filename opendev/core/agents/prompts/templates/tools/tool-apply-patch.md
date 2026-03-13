<!--
name: 'Tool Description: apply_patch'
description: Apply unified diff patches to files
version: 1.0.0
-->

Apply a unified diff patch to one or more files. Supports both git-style and standard unified diffs.

## Usage notes

- Accepts patch content in unified diff format (output of `git diff` or `diff -u`)
- Uses `git apply` first, falls back to standard `patch` command
- Set dry_run=true to validate a patch without applying it
- Multi-file patches are supported
- Patch must have proper --- / +++ / @@ headers
