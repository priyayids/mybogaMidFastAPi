# Nuveq Access Control Middle Service — Agent AI Documentation Workspace

This directory (`/Agent`) serves as the single centralized hub for all AI agent specifications, design documents, architecture blueprints, research briefs, and implementation progress trackers.

## Contents

1. [`nuveq-integration-brief.md`](nuveq-integration-brief.md)
   - Original comprehensive research brief, live webhook capture schemas, hardware notes, and discovery findings from testing the Nuveq REST API (`https://api-v2.nuveq.cloud`).

2. [`ARCHITECTURE.md`](ARCHITECTURE.md)
   - Middle Service (BFF) architectural design: FastAPI stack, async database layer, background scheduler, event-driven state transitions, and security boundary.

3. [`API_SPEC.md`](API_SPEC.md)
   - Complete API contract specifications: REST endpoints for rooms, bookings, QR credentials, webhooks, and Nuveq sync proxy.

4. [`PROGRESS.md`](PROGRESS.md)
    - Step-by-step progress tracking, test verification results, and operational checklists.

5. [`SCHEMA_REFERENCE.md`](SCHEMA_REFERENCE.md)
    - Field-level dictionary for every schema: origin (Custom vs Original vs Derived), format/constraints, usage, and cross-endpoint ID relationships.
