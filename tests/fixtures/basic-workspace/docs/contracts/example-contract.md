---
id: APP-CONTRACT-001
title: Example application contract
status: draft
owner:
  team: app-team
  service: app
  domain: app
  contact: app-team@example.com
related_anchors:
  - ExampleService
---

# Example application contract

## Responsibilities

`ExampleService` provides the core example behavior for this workspace.

## Non-responsibilities

- External integrations — not implemented in the example scaffold.

## Inputs

- `name` string passed to `ExampleService.greet`.

## Outputs

- A greeting string returned to the caller.

## Known gaps

- APP-KG-001
