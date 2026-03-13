<!--
name: 'Tool Description: schedule'
description: Manage scheduled recurring tasks
version: 1.0.0
-->

Manage scheduled recurring tasks with cron-like expressions. Tasks are persisted to ~/.opendev/schedules.json.

## Available actions

- list: Show all scheduled tasks
- add: Create a new schedule (params: name, cron, command)
- remove: Delete a schedule (params: name)
- run_now: Execute a scheduled task immediately (params: name)
- status: Show scheduler summary

## Cron expression format

Standard 5-field cron: minute hour day-of-month month day-of-week
- "0 * * * *" — every hour
- "*/15 * * * *" — every 15 minutes
- "0 9 * * 1-5" — 9 AM weekdays
