# Specification Expression Rules

## Core Principle: No Speculation or Arbitrary Assumptions
**Strictly adhere to raw specification text content. If fields, rules, conditions, or behaviors are not explicitly stated in the requirements, do not add them. Do not assume, speculate, or supplement any content that does not exist in the requirements.**

---

# Specification Expression Formats

## DBML Format (Data Model)
Used to describe the Entity-Relationship Model (ERM). All entities are written in a single `spec/domain/erm.dbml` file.

Basic structure:
- **Table**: Represents an entity
- **Column**: Contains name and data type (int, long, float, bool, string)
- **Note**: Definitions and descriptions for entities and attributes; can additionally list cross-attribute invariants
- **Relationship**: Associations between entities

## Gherkin Language Format (Functional Model)
Used to describe functional specifications using a three-tier structure: Feature > Rule > Example. Each feature has its own file at `tests/{module}/<feature-name>.feature`.

### Feature
- Definition: A request interaction point between the user and the system; must have a clear interaction trigger

### Rule
- Each feature contains 1..* rules

### Example
- Uses Gherkin syntax (Given-When-Then) to describe specific cases for rules
- If no examples are available in the specification text, mark `#TODO` under the Rule; that Rule's status is listed as Missing
- Should cover boundary conditions and different value domain categories

---

# Data Model Extraction Rules

## A. Identify "Entities"
Each entity is a data object that needs to be persisted in the system.

- Only extract entities explicitly mentioned in the specification
- Use terminology from the specification for entity names; do not create your own
- Do not add entities not mentioned in the specification

## B. Extract Entity "Attributes"
For each entity, extract its attributes:

- Only extract attributes explicitly mentioned or directly derivable from the specification
- Each attribute must specify a data type: **int, long, float, bool, string**
- Each attribute must have a **note** explaining its definition and purpose
- If the specification mentions constraints on attributes (e.g., > 0, >= 0, must be unique), explicitly annotate them in the note
- Do not add "reserved fields" or "potentially needed fields" not mentioned in the specification

## C. Annotate "Cross-Attribute Invariants"
If the specification explicitly mentions computational relationships or constraints between attributes:

- List cross-attribute invariants in the entity's Note
- Example: Total = Unit Price × Quantity
- Only record constraints explicitly mentioned in the specification; do not speculate

## D. Identify "Relationships" Between Entities
- Only annotate relationships explicitly mentioned in the specification
- Use DBML's ref syntax to describe associations
- Clearly indicate relationship types (one-to-one, one-to-many, many-to-many)

## E. Document Overall Entity Descriptions
- Briefly describe the entity's purpose in the Table's Note
- If entities have relationships, note them in the Note (e.g., Cart 1:N CartItem)

---

# Functional Model Extraction Rules

## A. Extract "Features"
Each feature is a request interaction point between the user and the system. If there is no clear interaction trigger, it is not considered a feature.

- For example, in a membership system, users can register, login, and logout with the system—each of these is an independent feature
- Only extract features explicitly mentioned in the specification; do not speculate about "potentially needed features"
- Feature naming should be clear and reflect user intent

## B. Extract Feature "Rules"
For each feature, extract its "Rules" from the raw specification text. Rules are conditions the system must comply with when actually executing the feature.

### Rule Categories
- **Pre-condition**: Validations performed before feature execution; if validation fails, the feature is not fulfilled
- **Post-condition**: Conditions the system must guarantee if pre-conditions pass, such as system state updates

### Rule Extraction Principles
- Each pre-condition or post-condition must be an independent Rule
- **Rules must be atomic**—split until indivisible; each Rule validates only one thing
- Extract at least one rule for each feature
- Only extract rules explicitly mentioned in the specification; do not add "reasonable validations" or "checks that should exist"
- Rule descriptions must be verifiable; avoid using vague adjectives

## C. Extract Rule "Examples"
For each rule, search the raw specification text for "Examples" that illustrate the rule.

- Use **Gherkin syntax (Given-When-Then)** to describe each Example
- If no examples can be found in the text, do not force any examples; mark **#TODO** under the Rule
- Do not fabricate examples or assume test scenarios
- Examples should cover boundary conditions and different value domain categories (if provided in the specification)
- Each Example must have at least a "When step"; When relates to the system interaction of that Feature. For example, if the Feature is "Login", then When must be the interaction trigger for this feature, i.e., "Login"
- Each step must be easily translatable into test code; do not include overly descriptive rather than data-oriented strings (e.g., writing in Then: `Then the execution order should be as follows:`—order is difficult to verify through test automation)
- Sentence patterns in Feature Files should be as consistent as possible to avoid disorder in subsequent test implementation or "different sentence patterns with same semantics causing duplicate StepDef implementations"
- `Then` statements can only describe actual system state data; do not write descriptive statements. For example:
  - Incorrect:
    ```
      Then the customer receives a rice ball meal
      And this meal does not include a complimentary snack
    ```
  - Correct:
    ```
    Then the customer receives the following meals
      | name      |
      | rice ball |
    ```
- If the operation is not allowed by the system in this scenario and an error needs to be expressed, always use this format for Then: `Then the operation fails`
- `Then` must use "data" to describe business function acceptance; do not describe what "should" happen, but describe "what the value must be". For example:
  - Incorrect: `Then discount of 1000 should be applied successfully`
  - Correct:
    ```
    Then the order's original total is 1500
    And the order's discounted price is 500
    ```

---

# Output Format Specifications

## DBML Format Requirements
Output the data model in DBML format to `spec/domain/erm.dbml` (all entities in the same file).

**Format requirements:**
- File must strictly follow DBML syntax format
- Each **Table** represents one entity
- Each **Column** must include:
  - Name
  - Data type (int, long, float, bool, string)
  - **note** description (definition, purpose, constraints)
- Each **Table** must have a **Note** explaining its purpose
- Cross-attribute invariants can be additionally listed in the Table Note
- Use **ref** to describe relationships between entities

## Gherkin Language Format Requirements
Output each Feature along with its Rules/Examples in Gherkin Language sequentially to `tests/{module}/`.

**File organization:**
- Each feature has its own file
- File name is `<feature-name>.feature`

**Format requirements:**
- File must strictly follow Gherkin Language format
- Hierarchical structure: Feature > Rule > Example
- Use English version of Given/When/Then keywords
- Each step statement is primarily described in the domain language
- If there is a DataTable, column names are described in English
- Rules missing Examples must be marked with `#TODO`
