
# Project: Local Distributed AI Worker Cluster

You are building an extensible distributed AI worker cluster.

This is NOT another "multi-agent framework".

The goal is to build infrastructure where independent LLM workers communicate with each other through a local API, allowing concurrent work, task delegation, memory, and discovery.

Think:

* Slack
* Git
* Kubernetes
* Message Queue

combined specifically for LLMs.

---

# Overall Goals

Every model should run independently.

Examples:

* Claude
* Codex
* Gemini
* Minimax
* LLMStudio local models
* Ollama models
* OpenRouter models
* OpenAI models

Each one is represented as a Worker.

Workers should NOT know implementation details of each other.

Workers only communicate through the Cluster API.

Everything should be request-based over localhost.

No polling unless absolutely necessary.

The architecture must support adding new workers without modifying existing code.

---

# Core Components

## 1. Cluster Server

Central coordinator.

Responsibilities:

* worker registry
* task routing
* conversation routing
* message persistence
* search
* pagination
* authentication (simple local tokens)
* event streaming
* task status
* worker capabilities

Prefer:

Python + FastAPI

or

Node + Fastify

Use whichever is cleaner.

---

## 2. Worker Runtime

Each worker is an independent process.

Responsibilities:

* register itself
* advertise capabilities
* receive tasks
* send responses
* ask other workers for help
* stream outputs
* maintain local context

Workers should not directly call each other.

Everything goes through the Cluster Server.

---

## 3. Transport

Primary:

HTTP REST

Streaming:

SSE

Optional:

WebSockets

No message broker initially.

Everything should work on localhost using plain HTTP.

The architecture should allow RabbitMQ/NATS/Redis Streams later.

---

# Worker Identity

Each worker has:

id

name

provider

model

description

personality

skills

tools

context_window

max_parallel_tasks

status

heartbeat

Example:

Claude

skills:

* architecture
* reasoning
* reviewing

Codex

skills:

* coding
* debugging
* refactoring

Minimax

skills:

* brainstorming
* creative writing

LLMStudio

skills:

* local inference
* embeddings

---

# Task Object

A task contains:

task_id

title

description

creator

assigned_worker

priority

dependencies

status

created_at

updated_at

conversation_id

attachments

results

logs

Tasks can create child tasks.

Example:

Task:

Implement authentication.

Claude:

"I need API endpoints."

Creates child task for Codex.

Codex:

Implements API.

Returns.

Claude continues.

---

# Conversations

Workers can directly chat.

Conversation:

id

participants

history

timestamps

Conversation supports:

pagination

search

threading

message edits

attachments

system messages

Workers should communicate naturally.

Example:

Claude:

"Codex, can you implement pagination?"

Codex:

"Yes."

Claude:

"I'll continue architecture while you work."

---

# Message Object

id

sender

receiver

conversation

timestamp

role

content

metadata

citations

tool_calls

attachments

Messages should be searchable.

---

# Search

Implement full-text search.

Support:

messages

tasks

workers

conversations

Filter by:

worker

date

status

tags

conversation

Use SQLite FTS5 initially.

---

# Pagination

Every endpoint supports:

limit

cursor

next_cursor

Avoid page numbers.

Cursor pagination only.

---

# Worker Discovery

Workers register.

GET /workers

returns

skills

status

latency

running_tasks

health

Workers can search:

"I need someone with coding skills."

Cluster returns Codex.

---

# Capabilities

Each worker advertises capabilities.

Example:

{
"skills":[
"python",
"typescript",
"api",
"debugging"
]
}

Workers assign based on capability.

---

# Task Assignment

Workers can POST:

assign_task

Cluster validates.

Routes.

Worker accepts.

Worker rejects.

Worker completes.

Worker requests clarification.

Everything is asynchronous.

---

# Memory

Each worker has:

private memory

cluster memory

conversation memory

task memory

Keep these separate.

---

# Persistence

SQLite initially.

Tables:

workers

tasks

messages

conversations

events

attachments

logs

fts indexes

Design schema for future PostgreSQL migration.

---

# Streaming

Support streamed responses.

Client receives partial tokens.

Workers can also stream progress.

Example:

25%

50%

75%

done

---

# Event System

Every important action creates an event.

Examples:

worker_joined

worker_left

task_created

task_completed

task_failed

message_sent

conversation_started

worker_busy

Events are queryable.

---

# Local API

Example endpoints:

POST /workers/register

GET /workers

GET /workers/{id}

POST /tasks

POST /tasks/{id}/assign

POST /tasks/{id}/complete

POST /messages

GET /messages

GET /conversations

GET /search

GET /events

GET /health

---

# Worker SDK

Build a lightweight SDK.

Example:

worker = WorkerClient(...)

worker.register()

worker.send_message()

worker.assign_task()

worker.search()

worker.complete_task()

worker.stream()

Make adding new workers extremely simple.

---

# MCP Compatibility

Design the architecture so workers can expose MCP tools.

The cluster itself should also expose an MCP server.

Future goal:

Claude can invoke:

search_tasks()

assign_task()

find_worker()

through MCP.

Likewise other clients.

---

# Plugin System

Workers should be plugins.

Implement a provider interface.

Examples:

ClaudeProvider

OpenAIProvider

OllamaProvider

LLMStudioProvider

OpenRouterProvider

GeminiProvider

MinimaxProvider

Each implements:

send()

stream()

health()

metadata()

No provider-specific code outside the provider module.

---

# UI (Later)

Do not build yet.

But expose enough APIs that a frontend can show:

worker list

live chats

live tasks

task graph

conversations

worker status

search

logs

---

# Concurrency

Workers must work simultaneously.

One worker waiting should never block another.

Use async throughout.

Support multiple concurrent tasks per worker.

---

# Code Quality

Strong typing.

Modular architecture.

Comprehensive tests.

Dependency injection.

Logging.

OpenAPI documentation.

No giant files.

Clean folder structure.

---

# Milestone Plan

Milestone 1

* Cluster server
* Worker registration
* SQLite
* REST API
* Search
* Pagination

Milestone 2

* Conversations
* Messaging
* Streaming
* Events

Milestone 3

* Task assignment
* Child tasks
* Capability discovery
* Worker SDK

Milestone 4

* MCP integration
* Plugin providers
* LLMStudio
* Claude
* Codex
* OpenAI
* Ollama

Milestone 5

* Performance improvements
* PostgreSQL support
* Redis/NATS compatibility
* Distributed deployment

The implementation should prioritize extensibility, maintainability, and asynchronous request-based communication over framework-specific abstractions. The cluster should feel like an operating system for AI workers rather than an agent orchestration library.