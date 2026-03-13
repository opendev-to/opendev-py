<!--
name: 'Tool Description: git'
description: Structured git operations with safety checks
version: 1.0.0
-->

Perform structured git operations with built-in safety checks. Provides structured output instead of raw git command output.

## Available actions

- status: Show branch, ahead/behind, and changed files
- diff: Show file differences (params: file, staged)
- log: Show commit history (params: limit, oneline)
- branch: List/create/delete branches (params: name, delete)
- checkout: Switch branches (params: branch, create) -- warns if working tree is dirty
- commit: Create a commit (params: message) -- requires staged changes
- push: Push to remote (params: remote, branch, force) -- refuses force-push to main/master
- pull: Pull from remote (params: remote, branch)
- stash: Stash operations (params: action=list/push/pop/drop/show, message)
- merge: Merge a branch (params: branch)
- create_pr: Create a pull request via gh CLI (params: title, body, base)

## Safety checks

- Refuses force-push to protected branches (main, master, develop, production, staging)
- Warns about uncommitted changes before checkout
- Requires staged changes before commit
- Uses --force-with-lease instead of --force for safer push
