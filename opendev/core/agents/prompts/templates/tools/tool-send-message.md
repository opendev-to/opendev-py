<!--
name: 'Tool Description: send_message'
description: Send messages to configured channels
version: 1.0.0
-->

Send messages to configured channels (Slack, Discord, or generic webhooks).

## Usage notes

- Requires webhook URLs configured in ~/.opendev/settings.json under "channels"
- Configuration example: {"channels": {"slack": {"webhook_url": "https://hooks.slack.com/..."}}}
- Supports "text" and "markdown" formats
- For Slack, markdown format uses Block Kit mrkdwn
- Can also pass webhook URL directly via the "target" parameter
