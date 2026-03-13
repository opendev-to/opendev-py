# Provider Setup Guide

OpenDev supports 9 LLM providers out of the box. This guide covers authentication, provider configuration, and workflow model binding.

## Getting Started

The fastest way to start is to export an API key and run OpenDev:

```bash
export OPENAI_API_KEY="sk-..."
opendev
```

OpenDev will auto-detect the key and use OpenAI as your provider. You can swap to any supported provider by exporting the corresponding key instead:

```bash
# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# Fireworks
export FIREWORKS_API_KEY="fw_..."
```

Alternatively, run the interactive setup wizard to configure providers, models, and workflow bindings in one step:

```bash
opendev config setup
```

## Authentication Precedence

OpenDev resolves API keys in this order:

- **Environment variable** (highest priority) -- e.g. `OPENAI_API_KEY`
- **Stored credential** in `~/.opendev/auth.json` -- written by `opendev config setup` with `0600` permissions
- **Interactive prompt** -- if no key is found, OpenDev prompts you during setup

Environment variables always win. This lets you override stored credentials per-shell or in CI without touching config files.

## Supported Providers

### OpenAI

- Env var: `OPENAI_API_KEY`
- Provider ID: `openai`
- Popular models: `gpt-4o`, `gpt-4o-mini`, `o3`, `o4-mini`

```bash
export OPENAI_API_KEY="sk-..."
```

### Anthropic

- Env var: `ANTHROPIC_API_KEY`
- Provider ID: `anthropic`
- Popular models: `claude-sonnet-4-20250514`, `claude-opus-4-20250514`

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Fireworks

- Env var: `FIREWORKS_API_KEY`
- Provider ID: `fireworks`
- Popular models: `accounts/fireworks/models/kimi-k2-instruct-0905`
- Note: Fireworks model IDs use the `accounts/fireworks/models/` prefix. OpenDev auto-normalizes short names (e.g. `kimi-k2-instruct-0905` becomes the full path).

```bash
export FIREWORKS_API_KEY="fw_..."
```

### Other Providers

All of these follow the same pattern -- export the env var and set the provider ID in your config:

- **Google** -- `GOOGLE_API_KEY`, provider ID `google`
- **Groq** -- `GROQ_API_KEY`, provider ID `groq`
- **Mistral** -- `MISTRAL_API_KEY`, provider ID `mistral`
- **DeepInfra** -- `DEEPINFRA_API_KEY`, provider ID `deepinfra`
- **OpenRouter** -- `OPENROUTER_API_KEY`, provider ID `openrouter`
- **Azure OpenAI** -- `AZURE_OPENAI_API_KEY`, provider ID `azure`

## Workflow Model Binding

OpenDev is a compound AI system. Instead of one model doing everything, it has 5 workflow slots, each independently bound to a model and provider:

- **Normal** (`model` + `model_provider`) -- The primary execution model. Handles coding tasks, tool calls, and general conversation. This is the only required slot.
- **Thinking** (`model_thinking` + `model_thinking_provider`) -- Used for complex reasoning in plan mode and deep analysis. Falls back to Normal if not set.
- **Compact** (`model_compact` + `model_compact_provider`) -- Summarizes conversation history when context gets too long. Falls back to Normal if not set.
- **Critique** (`model_critique` + `model_critique_provider`) -- Self-critiques the agent's reasoning and output. Falls back to Thinking, then Normal if not set.
- **VLM** (`model_vlm` + `model_vlm_provider`) -- Processes images and screenshots. Falls back to Normal if the Normal model has vision capability; otherwise unavailable.

### Fallback Chains

You only need to configure the slots you want to customize. Unset slots fall back automatically:

- Thinking -> Normal
- Compact -> Normal
- Critique -> Thinking -> Normal
- VLM -> Normal (only if Normal model supports vision)

### Example: Mixed-Provider Configuration

Use Claude for execution, OpenAI o3 for thinking, and a fast Fireworks model for compaction:

```json
{
  "model_provider": "anthropic",
  "model": "claude-sonnet-4-20250514",

  "model_thinking_provider": "openai",
  "model_thinking": "o3",

  "model_compact_provider": "fireworks",
  "model_compact": "accounts/fireworks/models/kimi-k2-instruct-0905"
}
```

This requires both `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` and `FIREWORKS_API_KEY` to be set.

## Configuration Files

OpenDev uses a hierarchical config system. Settings are JSON files with optional `//` and `/* */` comments.

### Config Hierarchy (highest priority first)

- **Project config**: `.opendev/settings.json` in your project root
- **Global config**: `~/.opendev/settings.json`
- **Defaults**: Built-in default values

Project config overrides global config, which overrides defaults. The exception is `instructions` -- instructions from all levels are concatenated, not overridden.

### Variable Substitution

Config values support two substitution patterns:

- `{env:VAR_NAME}` -- replaced with the value of environment variable `VAR_NAME`
- `{file:/path/to/file}` -- replaced with the contents of the file

Example:

```json
{
  "model_provider": "openai",
  "model": "gpt-4o",
  "instructions": "Project context: {file:./CONTEXT.md}"
}
```

### Credential Storage

API keys are stored separately from config in `~/.opendev/auth.json` (mode `0600`). Keys set via `opendev config setup` go here. Environment variables always take precedence over stored keys.

Never put API keys in `settings.json` -- the config system intentionally strips `api_key` fields from config files for security.
