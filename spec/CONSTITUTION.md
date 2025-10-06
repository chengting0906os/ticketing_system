# Before You Start

**Read First**:
- [Makefile](../Makefile) - Available commands
- [pyproject.toml](../pyproject.toml) - Dependencies and tooling
- [KAFKA_SPEC.md](KAFKA_SPEC.md) - Event-driven messaging
- [KVROCKS_SPEC.md](KVROCKS_SPEC.md) - State storage
- [TICKETING_SERVICE_SPEC.md](TICKETING_SERVICE_SPEC.md) - Ticketing service architecture
- [SEAT_RESERVATION_SPEC.md](SEAT_RESERVATION_SPEC.md) - Seat reservation service architecture

**Architecture**: Use `tree` command to understand hexagonal structure

# Must-Do Rules

- **Imports**: Always at top of file, never inside functions
- **Async**: Prefer `anyio` > `asyncio`, prefer `async` > `sync`
- **Dependency Inversion**: High-level modules depend on abstractions, not low-level modules

# Core Development Philosophy

## BDD (Behavior-Driven Development)
**Before Writing Tests**: Read [tests/conftest.py](../tests/conftest.py) for fixtures and test setup
- **Integration Tests**: Write in `.feature` files using Gherkin steps (Given/When/Then)
- **Unit Tests**: Write in `tests/*/unit/` directories

## TDD (Test-Driven Development)
1. **Write the test first** - Define expected behavior
2. **Watch it fail** - Ensure the test actually tests something
3. **Write minimal code** - Just enough to make it pass
4. **Refactor** - Improve while keeping tests green
5. **Repeat** - One test at a time

## KISS (Keep It Simple, Stupid)
Choose straightforward solutions over complex ones. Simple code is easier to understand, maintain, and debug.

## YAGNI (You Aren't Gonna Need It)
Implement features only when needed, not when you think they might be useful later.

## Design Principles
- **Open/Closed**: Open for extension, closed for modification
- **Single Responsibility**: Each function/class/module has one clear purpose
- **Fail Fast**: Check for errors early and raise exceptions immediately
