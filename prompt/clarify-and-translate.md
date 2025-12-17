---
description: Based on clarification items in the .clarify/ folder, conduct interactive clarification with users and update answers in real-time to corresponding specification model files (erm.dbml or features/*.feature).
---

Objective: Based on clarification items generated during the Discovery phase, clarify each item through an interactive Q&A process and integrate clarification results into specification files in real-time.

# Execution Steps

## 0. Initialization and Loading

1. **Load Clarification Strategy**: Load `.clarify/overview.md` to obtain:
   - Total clarification items and distribution
   - Recommended clarification order (from core to extended)
   - Priority distribution and dependencies

2. **Load Clarification Items**: Following the order recommended in `overview.md`, read all clarification item files (`.clarify/data/*.md` and `.clarify/features/*.md`)

3. **Load Existing Specifications**: Load the following specification files into memory:
   - `spec/domain/erm.dbml`
   - `tests/{module}/*.feature`
   - Maintain original format and structure for subsequent incremental updates
   - **Build Terminology Reference Table**: Extract all domain terminology (entity names, attribute notes, Feature names, step wording) for reference during translation

## 1. Build Clarification Queue

Based on the recommended order in `overview.md`, build a prioritized clarification queue:

### Sorting Principles

1. **Core First**: Prioritize High priority items
2. **From Core to Extended**: Handle core entities and features first, then boundary conditions and details
3. **Balanced Distribution**: Alternate between data model and functional model to avoid consecutively processing same category questions
4. **Dependencies**: If item B depends on item A's clarification result, ensure A is processed before B

### Queue Management

- Initial queue contains all clarification items
- Each item is marked with status: Pending / In-Progress / Resolved / Skipped
- Users can choose to skip low priority items
- Upon early termination, unprocessed items are marked as Deferred

## 2. Question-by-Question Loop (Interactive)

### 2.1 Questioning Flow

**Present one question at a time**, formatted as follows:

\`\`\`
---
[Clarification Progress: Question X / Total Y] [Priority: High/Medium/Low]

# Question

<Plain language version of the question>

## Location

<ERM: Which entity's which attribute? Or which relationship?>
<Feature: Which feature's which rule? Or which Example?>

## Options

<Present multiple choice table>

| Option | Description |
|--------|-------------|
| A | <Option A plain language description> |
| B | <Option B plain language description> |
| C | <Option C plain language description> |
| D | <Option D plain language description> (if applicable) |
| E | <Option E plain language description> (if applicable) |
| Short | Provide other short answer (<=5 words) |

---
\`\`\`

- For short answer questions (no clear discrete options), add note after options table: `Format: Short answer (<=5 words)`

#### Translation Guidelines

Before presenting questions and options, plain language translation must be performed following these guidelines:

1. **Terminology Consistency Check**:
   - Load relevant sections from `spec/domain/erm.dbml` and `tests/{module}/*.feature` for that entity/feature
   - Extract domain terminology already in use (such as entity names, attribute notes, Feature names, step wording)
   - Build a "technical term ↔ specification terminology" reference table

2. **Question Plain Language Conversion**:
   - Replace English field names (such as `price`, `quantity`) with domain terminology already in use (such as "price", "quantity")
   - May note English names in parentheses on first mention, e.g., "price (price)"
   - Convert technical terms (such as "attribute", "field", "relationship", "constraint") to domain language (such as "information", "item", "association", "restriction")
   - Maintain complete semantics of the question; do not simplify technical details

3. **Option Plain Language Conversion**:
   - Convert technical descriptions to user scenario language
   - Remove programming syntax symbols (such as `>=`, `!=`), replace with "greater than or equal to", "not equal to"
   - Maintain clear contrast between options

4. **Strictly Prohibited**:
   - **Do not invent new terms**: If the specification has not defined a term for that concept, keep the English and add parenthetical note
   - **No semantic drift**: Plain language conversion must not change the technical meaning of the original question
   - **No inconsistent wording**: Same concept must use same terminology across different clarification questions

5. **Translation Verification**:
   - After translation, cross-check specification files to confirm all terms have been used in the specification
   - If multiple terms for same concept are found in specification (e.g., "customer" and "client"), prefer wording from Feature files (as it's closer to user language)

#### Translation Example

**Original Question** (from clarification item file):
> Does the `Product` entity's `price` attribute allow `null` values?

**Translated Question**:
> Can the product's price (price) be blank (unset)?

**Original Options**:
- A: Allow `null`, indicating price is pending
- B: Not allowed, must be `>= 0`

**Translated Options**:
- A: Can be blank, indicating price is not yet determined
- B: Cannot be blank, must be a number greater than or equal to 0

### 2.2 Answer Processing

After user answers:

1. **Validate Answer**:
   - Check if answer corresponds to an option (A/B/C/D/E)
   - If Short, confirm it meets the 5-10 word limit (not strictly enforced)
   - If vague or unclear, immediately request clarification (still counts as same question, do not advance to next)

2. **Record Answer**:
   - Temporarily store answer in working memory
   - Mark that clarification item as Resolved

3. **Immediate Integration** (see Step 3)

4. **Update Progress**:
   - Change that clarification item from Pending to Resolved
   - Move to next item in queue

### 2.3 Termination Conditions

Stop questioning under the following conditions:

- All clarification items have been processed
- User explicitly indicates termination (e.g., "done", "stop", "no more", "proceed")
- Remaining items are only Low priority and user chooses to skip

**Never reveal subsequent questions in advance**; maintain one question at a time pace.

### 2.4 Interaction Principles

- **Single Focus**: Focus on only one clarification item at a time to avoid confusion
- **Quick Validation**: If answer is vague, immediately request clarification; do not speculate
- **Progress Transparency**: Show progress on each question (Question X / Total Y)
- **Priority Visibility**: Show priority on each question so users understand importance

## 3. Immediate Integration (Incremental Update)

**After each** answer is accepted, immediately perform incremental update:

### 3.0 Follow Specification Expression Rules

**All** specification file updates must follow the specifications in [`formulation-rules.md`](../prompts/formulation-rules.md), including:
- **Core Principle**: No speculation or arbitrary assumptions principle
- **Data Model Extraction Rules**: Extraction and annotation methods for entities, attributes, relationships
- **Functional Model Extraction Rules**: Extraction and description methods for Feature, Rule, Example
- **Output Format Specifications**: Format requirements for DBML and Gherkin Language

When converting clarification results to specification content, ensure compliance with all requirements of the above rules.

### 3.1 Update Strategy

Based on the clarification item's location, determine update target:

- **Data Model Clarification** → Update `spec/domain/erm.dbml` (following DBML format specifications in `formulation-rules.md`)
  - Update entity attribute definitions (type, note, constraints)
  - Add or modify relationship definitions
  - Update cross-attribute invariants
  - Add state transition rules

- **Functional Model Clarification** → Update `tests/{module}/<feature-name>.feature` (following Gherkin Language format specifications in `formulation-rules.md`)
  - Add or modify Rule
  - Add or modify Example (following Given-When-Then format)
  - Update pre/post-conditions
  - Add error handling scenarios

- **SPEC Document Clarification** → Synchronously update `spec/domain/{MODULE}_SPEC.md`
  - Update acceptance criteria in Acceptance section
  - Update error code definitions in API Endpoints
  - Update business rules in Business Rules section

- **Terminology Conflict Clarification** → Full-text normalization
  - Unify terminology across all specification files
  - Retain "(previously called 'X')" note if necessary (only once)

### 3.2 Update Principles

- **Follow Expression Rules**: All updates must comply with [`formulation-rules.md`](../prompts/formulation-rules.md) specifications
- **Replace Rather Than Accumulate**: If clarification invalidates previous vague statements, replace directly; do not retain contradictory content
- **Preserve Format**: Maintain original heading hierarchy, section order, indentation style
- **Keep Testable and Concise**: Inserted clarification content should be concise and verifiable; avoid narrative drift
- **Atomic Overwrite**: Save specification file immediately after each integration to reduce risk of context loss
- **Consistent Syntax Patterns**: Step definitions in Feature files should maintain consistent syntax patterns to avoid duplicate implementations due to same semantics but different patterns

### 3.3 Integration Steps
Each step must be thoroughly completed; no skipping steps.
1. **Locate Target Section**: Based on the clarification item's "Location" field, find the entity/attribute/feature/rule to update
2. **Apply Clarification**: Convert answer to corresponding DBML or Gherkin syntax, **must follow [`formulation-rules.md`](../prompts/formulation-rules.md) specifications**
3. **Validate Syntax**: Ensure updated content complies with DBML or Gherkin format
4. **Check Consistency**: Ensure no contradictory statements, unified terminology
5. **Save Specification File**: Atomic overwrite of corresponding specification file
6. **Update Clarification Item Status**: Archive processed clarification item (see 3.6)

### 3.4 DBML Update Example

**Original Clarification Question** (technical): "Does MenuItem's price allow negative values?"

**Translated Question** (plain language): "Can the menu item's price (price) be negative?"

**User Answer**: "A - No, must be a number greater than or equal to 0"

**Specification Update**:

Before update:
\`\`\`dbml
Table MenuItem {
  id int [pk]
  price float [note: "Menu item price"]
}
\`\`\`

After update:
\`\`\`dbml
Table MenuItem {
  id int [pk]
  price float [note: "Menu item price, must be >= 0"]
}
\`\`\`

### 3.5 Gherkin Update Example

**Original Clarification Question** (technical): "How to handle quantity of 0 when adding menu item to order?"

**Translated Question** (plain language): "How should we handle when quantity (quantity) is 0 when adding a menu item to order?"

**User Answer**: "B - Not allowed to add, should display error message"

**Specification Update**:

Before update:
\`\`\`gherkin
Feature: Add item to cart

  Rule: Customer can add item to cart
    Example: Successfully add item
      Given a product "Laptop" exists in catalog
      When customer adds "Laptop" to cart with quantity 2
      Then cart should contain "Laptop" with quantity 2
\`\`\`

After update (added rule and example):
\`\`\`gherkin
Feature: Add item to cart

  Rule: Customer can add item to cart
    Example: Successfully add item
      Given a product "Laptop" exists in catalog
      When customer adds "Laptop" to cart with quantity 2
      Then cart should contain "Laptop" with quantity 2

  Rule: Quantity must be greater than 0
    Example: Reject item with quantity 0
      Given a product "Laptop" exists in catalog
      When customer adds "Laptop" to cart with quantity 0
      Then error message "Quantity must be greater than 0" should be displayed
      And cart should not contain "Laptop"
\`\`\`

### 3.6 Clarification Item Status Update

**After each** specification file update is complete, immediately archive the clarification item to maintain `.clarify/` folder manageability:

#### Step 1: Record Answer at Bottom of Clarification Item File

Before moving the clarification item file, first append resolution record at the bottom of that file:

\`\`\`markdown
---
# Resolution Record

- **Answer**: <User's selected option, e.g., A - Option description>
- **Updated Specification File**: <spec/erm.dbml or spec/features/*.feature>
- **Change Content**: <Brief description of specification file changes>
\`\`\`

Example:
\`\`\`markdown
---
# Resolution Record

- **Answer**: B - Order must belong to a user (User 1:N Order)
- **Updated Specification File**: spec/erm.dbml
- **Change Content**: Added user_id foreign key to Order entity, established User 1:N Order relationship
\`\`\`

#### Step 2: Remove Item from overview.md

- Locate all occurrences of that clarification item in `.clarify/overview.md`:
  - Item entry in "3. Recommended Clarification Order"
  - References in "5. Coverage Summary" (if applicable)
- Completely remove that item's entry (including number, description, impact explanation, dependency/combination markers)
- Do not renumber remaining items; keep original numbering for tracking
- Update counts in "1. Clarification Item Statistics" (total -1, corresponding category -1)
- Save updated `overview.md`

#### Step 3: Archive Clarification Item File

- Based on original file path, determine target archive path:
  - Original path: `.clarify/data/<filename>.md` → Target: `.clarify/resolved/data/<filename>.md`
  - Original path: `.clarify/features/<filename>.md` → Target: `.clarify/resolved/features/<filename>.md`
- Ensure target directory exists (create `.clarify/resolved/data/` or `.clarify/resolved/features/` if necessary)
- Move file to target path (file bottom already contains resolution record from Step 1)

#### Purpose and Benefits

- **Record Decision History**: Recording answers at bottom of clarification item files preserves complete decision context
- **Keep overview.md Concise**: Avoid accumulating resolved items over time; easy to quickly view remaining pending items
- **Preserve History**: Archive to `resolved/` folder for long-term maintenance and decision traceability
- **Structured Management**: Maintain `data/` and `features/` layering for easy querying of historical clarifications by domain

## 4. Validation (After Each Write and Final Completion)

### 4.1 Immediate Validation (After Each Update)

- [ ] Updated section has removed original vague placeholder text
- [ ] No contradictory statements exist
- [ ] Format is valid:
  - `spec/domain/erm.dbml` follows DBML syntax
  - `tests/{module}/*.feature` follows Gherkin syntax (strict hierarchy Feature > Rule > Example)
  - New Examples contain at least a When step related to that Feature's system interaction
- [ ] Terminology consistency: Updated content uses standard terminology
- [ ] Clarification item status updated:
  - Resolution record appended to bottom of clarification item file (including answer, updated specification file, change content)
  - Item removed from `.clarify/overview.md`
  - Clarification item file moved to corresponding `.clarify/resolved/` folder
  - `overview.md` statistics updated

### 4.2 Final Validation (After Clarification Process Ends)

- [ ] Each Resolved clarification item corresponds to one specification update
- [ ] Step syntax patterns in Feature files are consistent
- [ ] All DBML entity attributes have type and note
- [ ] All Feature Rules have at least one Example (or marked #TODO)
- [ ] Terminology is consistent across files

## 5. Report Completion (After Question Loop Ends or Early Termination)

Generate detailed completion report:

### 5.1 Clarification Statistics

- Total clarification items: X items
- Resolved: Y items
- Skipped: Z items
- Deferred: W items

### 5.2 Updated Specification File Paths

List all updated specification files:
- `spec/domain/erm.dbml` - Updated entities A, B, C
- `tests/{module}/add_item_to_order.feature` - Added 2 rules and 3 examples
- `tests/{module}/confirm_order.feature` - Updated 1 rule and 2 examples

### 5.3 Touched Sections

List all touched entity, attribute, feature, and rule names

### 5.4 Coverage Summary Table

List final status for each check category (A1-A6, B1-B5, C1-C2, D1-D2):

| Category | Status | Description |
|----------|--------|-------------|
| A1. Entity Completeness | Resolved | Was Partial, clarified Customer and Order relationship |
| A2. Attribute Definition | Resolved | Was Missing, added price constraint |
| A3. Attribute Value Boundary Conditions | Clear | Was already sufficient |
| B1. Feature Identification | Resolved | Was Partial, clarified discount application timing |
| B2. Rule Completeness | Deferred | Beyond user termination point, 2 Low priority items remaining |
| ... | ... | ... |

Status descriptions:
- **Resolved**: Was Partial/Missing and has been clarified
- **Deferred**: Delayed due to user termination or question limit
- **Clear**: Was already sufficient, no clarification needed
- **Outstanding**: Still Partial/Missing but lower impact

### 5.5 Follow-up Recommendations

- If all High priority items are Resolved, recommend proceeding to next phase (planning or implementation)
- If High priority items are Deferred, recommend explaining risks and suggesting re-running Formulation
- If new ambiguities were discovered (emerged during clarification process), recommend re-running Discovery

## 6. Clarification Item File Management

### Default Behavior: Real-time Archiving

This process uses **real-time archiving** strategy:
- After each clarification item is resolved, immediately move to `.clarify/resolved/` folder
- Simultaneously remove that item from `overview.md`
- Preserve history records in `.clarify/resolved/data/` or `.clarify/resolved/features/`

### Archive Structure

\`\`\`
.clarify/
├── overview.md          # Contains only pending items
├── data/                # Pending data model clarification items
├── features/            # Pending functional model clarification items
├── specs/               # Pending SPEC document clarification items
└── resolved/            # Resolved clarification items
    ├── data/            # Resolved data model clarification items
    ├── features/        # Resolved functional model clarification items
    └── specs/           # Resolved SPEC document clarification items
\`\`\`

### Update Target Reference

| Clarification Item Type | Update Target File |
|------------------------|-------------------|
| Data Model Clarification | `spec/domain/erm.dbml` |
| Functional Model Clarification | `tests/{module}/<feature-name>.feature` |
| SPEC Document Clarification | `spec/domain/{MODULE}_SPEC.md` |

# Behavioral Rules

- **Strict Order**: Ask questions in the order recommended by `overview.md`; do not skip
- **Single Question Focus**: Present one question at a time; wait for answer before proceeding to next
- **Must Translate First**: Before each question, must perform plain language translation to ensure question and options comply with translation guidelines
- **Precise Terminology**: When translating, must use domain terminology already in specification files; strictly prohibited from inventing new terms
- **Terminology Reference**: Before each translation, extract domain terminology reference table from specification files
- **Immediate Integration**: Update specification file and clarification item status immediately after each answer is accepted; no delay
- **Real-time Archiving**: After each clarification item is resolved, immediately remove from `overview.md` and move to `.clarify/resolved/`
- **Quick Validation**: If answer is vague, immediately request clarification; do not speculate on user intent
- **Respect Termination**: User can terminate at any time; processed clarification items marked as Resolved, unprocessed marked as Deferred
- **Preserve Format**: When updating specification files, maintain original format and structure; do not reorder unrelated sections
- **Consistent Terminology**: Use unified terminology throughout; normalize previously inconsistent wording if necessary
- **Unified Syntax Patterns**: Step definitions in Feature files should maintain consistent syntax patterns
- **Avoid Duplication**: If clarification invalidates previous statements, replace directly; do not retain contradictory content
- **Testability**: All inserted clarification content should be concise and verifiable

# Output Format Requirements

1. **Interactive Questions** → Terminal output or chat interface
2. **Specification Updates** → `spec/domain/erm.dbml` and `tests/{module}/*.feature`
3. **Clarification Item Archiving** (automatic) → Real-time update `.clarify/overview.md` and move items to `.clarify/resolved/`
4. **Completion Report** → Terminal output or reply message
