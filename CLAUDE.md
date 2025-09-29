# Core Development Philosophy
## Test-Driven Development (TDD)
- Write the test first - Define expected behavior before implementation
- Watch it fail - Ensure the test actually tests something
- Write minimal code - Just enough to make the test pass
- Refactor - Improve code while keeping tests green
- Repeat - One test at a time


## KISS (Keep It Simple, Stupid)
Simplicity should be a key goal in design. Choose straightforward solutions over complex ones whenever possible. Simple solutions are easier to understand, maintain, and debug.

## YAGNI (You Aren't Gonna Need It)
Avoid building functionality on speculation. Implement features only when they are needed, not when you anticipate they might be useful in the future.

## Design Principles
- Dependency Inversion: High-level modules should not depend on low-level modules. Both should depend on abstractions.
- Open/Closed Principle: Software entities should be open for extension but closed for modification.
- Single Responsibility: Each function, class, and module should have one clear purpose.
- Fail Fast: Check for potential errors early and raise exceptions immediately when issues occur.

## Code Organization Rules
### Import Organization
- All imports must be placed at the top of the file, never inside functions or methods
- Follow PEP 8 import ordering: standard library, third-party packages, local modules