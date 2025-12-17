---
description: Scan current specifications, identify all unclarified or uncovered areas, and record clarification items in structured format in the .clarify/ folder for use in the subsequent formulation phase.
---

Objective: Detect ambiguities or missing decision points in active specifications, record clarification questions as files in the `.clarify/` folder, and generate `overview.md` explaining the clarification prioritization strategy.

# Execution Steps

## 1. Ambiguity and Coverage Scan

Perform a structured scan of current specification files using the following checklist. Mark each check item with a status: Clear / Partial / Missing. Generate an internal coverage map for priority ranking.

### A. Domain and Data Model Check (corresponds to spec/domain/erm.dbml)

#### A1. Entity Completeness
- [ ] Are all core business concepts modeled as entities?
- [ ] Are entity names clear and unambiguous?
- [ ] Are there implicit but not explicitly defined entities?

#### A2. Attribute Definition
- [ ] Does each attribute have a clear data type (int, long, float, bool, string)?
- [ ] Does each attribute have sufficient definition (using note)?
- [ ] Are attribute names clear and unambiguous?

#### A3. Attribute Value Boundary Conditions
- [ ] Are range constraints for numeric attributes clear (>=, <=, =, ≠)?
- [ ] Are minimum/maximum values defined?
- [ ] Are boundary cases clarified (just meeting threshold vs. just missing)?
- [ ] Is special value handling defined (null, zero, negative)?

#### A4. Cross-Attribute Invariants
- [ ] Are computational relationships between attributes clear (e.g., Total = Unit Price × Quantity)?
- [ ] Are formulas for derived attributes clearly defined?
- [ ] Are there multi-attribute constraints that must be satisfied simultaneously?

#### A5. Relationships and Uniqueness
- [ ] Are relationships between entities complete (one-to-one, one-to-many, many-to-many)?
- [ ] Are primary key and uniqueness rules clear?
- [ ] Are foreign key associations correctly defined?

#### A6. Lifecycle and State
- [ ] Do entities with state define all possible states?
- [ ] Are state transition rules complete (which transitions are valid, which are not)?
- [ ] Are initial and terminal states clearly defined?

### B. Functional Model Check (corresponds to tests/{module}/*.feature)

#### B1. Feature Identification
- [ ] Are all user-system interaction points identified as features?
- [ ] Do feature definitions truly have interaction triggers (not just rules)?
- [ ] Are feature names clear and reflect user intent?
- [ ] Are boundaries between features clear (no overlap or gaps)?

#### B2. Rule Completeness
- [ ] Does each feature have at least one rule?
- [ ] Are rules atomic (split until indivisible, each Rule validates only one thing)?
- [ ] Is each pre-condition an independent Rule?
- [ ] Is each post-condition an independent Rule?
- [ ] Are pre-conditions complete (all necessary validations listed)?
- [ ] Are post-conditions complete (all state changes listed)?
- [ ] Are rule descriptions verifiable (not vague adjectives)?

#### B3. Example Coverage (must be done, no compromise)
- [ ] Does each rule have at least one Example?
- [ ] Do Examples use correct Gherkin syntax (Given-When-Then)?
- [ ] Are rules missing Examples marked with #TODO?

#### B4. Boundary Condition Coverage
- [ ] **Numeric boundaries**: Are critical value cases covered (just meeting threshold, just missing, exceeding)?
- [ ] **Combination boundaries**: Are intersections and conflicts when multiple rules coexist handled?
- [ ] **Category boundaries**: Do different value domain data classifications have corresponding Examples?
- [ ] **Time boundaries**: Do time-related operations consider different time points?
- [ ] **State boundaries**: Are state transition boundary cases covered?

#### B5. Error and Exception Handling
- [ ] Is behavior when pre-conditions fail clearly defined?
- [ ] Do all exceptional cases have corresponding rules and Examples?
- [ ] Are error messages or feedback defined?

### C. Terminology and Consistency Check

#### C1. Glossary
- [ ] Is a standard terminology glossary established?
- [ ] Do core concepts have consistent naming?

#### C2. Terminology Conflicts
- [ ] Are there synonyms being mixed (same concept, multiple names)?
- [ ] Are there homonyms (different concepts using same name)?
- [ ] Are deprecated terms marked and uniformly replaced?

### D. Other Quality Checks

#### D1. Pending Items
- [ ] Are there TODO markers or unresolved items?
- [ ] Is the impact scope of unresolved items assessed?

#### D2. Vague Descriptions
- [ ] Are there unquantified adjectives (such as "robust", "intuitive", "appropriate")?
- [ ] Are vague "should" or "may" converted to explicit rules?

---

**Clarification Item Filtering Principles**:
For check items with Partial or Missing status, create clarification items unless:
- Clarification would not materially change implementation or verification strategy, or
- The information is better deferred to the planning phase (internal note)

Only include questions whose answers would materially affect architecture, data modeling, task breakdown, test design, UX behavior, operational readiness, or compliance verification.

**Avoid Duplicate Questions Principle**:
Before creating new clarification items, you must first check the `.clarify/resolved/` directory:
- Scan all resolved clarification items in `.clarify/resolved/data/` and `.clarify/resolved/features/`
- Check if the question topic has already been answered (even if phrased slightly differently)
- If the question already has a resolution record in resolved, do not create a duplicate clarification item
- If the question has a different angle but is related, note the related resolved items in the new clarification item's "Location" or "Impact Scope"

## 2. Generate Clarification Item Files

**Pre-step: Check Resolved Items**

Before creating any clarification item files:
1. Read the `.clarify/resolved/data/` and `.clarify/resolved/features/` directory structure
2. List all resolved clarification item file names
3. For each clarification item to be created, compare its question topic against those in resolved
4. If already exists, skip creating that clarification item

For each identified Partial or Missing check item, create a corresponding clarification item file:

### File Path Rules

- **Data Model (ERM) related**: `.clarify/data/<entity-name>_<full-question-with-underscores>.md`
  - Example: `.clarify/data/Product_can_product_price_be_negative.md`
  - Example: `.clarify/data/Order_what_are_order_status_transition_rules.md`

- **Feature related**: `.clarify/features/<feature-name>_<full-question-with-underscores>.md`
  - Example: `.clarify/features/add_product_to_cart_how_to_handle_zero_quantity.md`
  - Example: `.clarify/features/place_order_what_is_discount_rule_application_order.md`

### Clarification Item File Format

Each clarification item file uses the following unified format:

\`\`\`markdown
# Clarification Question

<Complete sentence of the clarification question>

# Location

<ERM: Which entity's which attribute? Or which relationship?>
<Feature: Which feature's which rule? Or which Example?>

# Multiple Choice

| Option | Description |
|--------|-------------|
| A | <Option A description> |
| B | <Option B description> |
| C | <Option C description> |
| D | <Option D description> (optional) |
| E | <Option E description> (optional) |
| Short | Provide other short answer (<=5 words) |

Note: Maximum 5 options (including Short). If no clear options, keep only Short and note `Format: Short answer (<=5 words)`.

# Impact Scope

<Explain which entities, features, rules, or test cases this clarification will affect>

# Priority

<High / Medium / Low>
- High: Blocks core feature definition or data modeling
- Medium: Affects boundary conditions or test completeness
- Low: Optimization or detail adjustment
\`\`\`

## 3. Generate Overview Document

Generate a clarification strategy overview in `.clarify/overview.md`, including:

### 3.1 Clarification Item Statistics

- Data model related: X items
- Functional model related: Y items
- Total: Z items

### 3.2 Priority Distribution

- High: X items
- Medium: Y items
- Low: Z items

### 3.3 Recommended Clarification Order

**Core Principle**: From core to extended, balanced distribution between data and features.

1. **Phase 1: Core Data Model** (Prioritize entities and relationships with greatest impact)
   - List High priority data model clarification items
   - Reason: Core entity and attribute definitions affect all subsequent feature design

2. **Phase 2: Core Feature Rules** (Handle rule completeness for main business flows)
   - List High priority functional model clarification items
   - Reason: Ensure main interaction flows are clearly defined

3. **Phase 3: Boundary Conditions and Cross-Model Associations** (Handle data and feature boundary cases)
   - List Medium priority items (interleave data and features)
   - Reason: Complete boundary cases and cross-entity/cross-feature interactions

4. **Phase 4: Details and Optimization** (Handle remaining low priority items)
   - List Low priority items
   - Reason: Refine specification details

### 3.4 Clarification Strategy Notes

- **Balance Principle**: Avoid consecutively processing same category questions; alternate between data model and functional model
- **Dependencies**: Mark clarification items with prerequisites (must clarify A before handling B)
- **Combined Clarification**: Mark related clarification items that can be handled together

### 3.5 Coverage Summary

List status for each check category (A1-A6, B1-B5, C1-C2, D1-D2):
- **Clear**: Fully defined
- **Partial**: Partially defined, X clarification items created
- **Missing**: Not yet defined, Y clarification items created

## 4. Validate Output

Ensure generated clarification items meet the following standards:

- [ ] Each clarification item file follows the unified format
- [ ] File paths follow naming rules (entity name/feature name clear, question description precise)
- [ ] Each question has clear location (points to specific entity/attribute/feature/rule)
- [ ] Multiple choice options are mutually exclusive and cover main possibilities
- [ ] Impact scope is clearly marked
- [ ] Priority is reasonably assessed (follows impact × uncertainty principle)
- [ ] `overview.md` clarification order is concrete and feasible, following "from core to extended, balanced distribution" principle

## 5. Report Completion

Generate concise report including:

- List of scanned specification files
- Total clarification items (by data model / functional model)
- Priority distribution (High / Medium / Low)
- `.clarify/` folder structure overview
- Prompt user to execute `formulation.md` prompt for next phase clarification interaction

# Behavioral Rules

- **Detection Role Only**: This phase does not perform any interactive clarification, only generates clarification item files
- **Complete Scan**: Not limited to 5 questions; all Partial or Missing check items should create clarification items
- **Structured Output**: Strictly follow file path and format specifications to ensure formulation phase can read smoothly
- **Priority Assessment**: Assess each clarification item's priority based on "impact × uncertainty"
- **Strategy Planning**: Provide clear clarification order recommendations in `overview.md`
- **Avoid Speculation**: If tech stack questions don't block feature clarification, don't include as clarification items
- **Keep Focused**: Each clarification question should focus on a single decision point; avoid compound questions
- **Testability**: Ensure each question's answer can be directly converted to specification updates (DBML or Gherkin)

# Output Format Requirements

1. **Clarification Item Files** → `.clarify/data/*.md` or `.clarify/features/*.md`
2. **Overview Document** → `.clarify/overview.md`
3. **Completion Report** → Terminal output or reply message

# Integration with Formulation Phase

- Clarification item files generated by Discovery will be read by the Formulation phase
- Clarification order in `overview.md` will guide the questioning order in the Formulation phase
- File format design ensures Formulation can directly parse and present to users
- Priority and impact scope information helps Formulation decide whether to terminate clarification flow early
