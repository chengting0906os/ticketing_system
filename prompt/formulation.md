# Formulation: Producing Specification Models from Specification Text

## Objective
Extract and structure specification models from raw specification text, including:
1. **Data Model**: Describe the Entity-Relationship Model (ERM) in DBML format
2. **Functional Model**: Describe functional specifications in Gherkin Language

---

## Execution Steps

### 1. Extract Data Model from Specification
Identify and extract data entities and their relationships from raw specification text, following the "Data Model Extraction Rules" in [`formulation-rules.md`](./formulation-rules.md):
- A. Identify "Entities"
- B. Extract entity "Attributes"
- C. Annotate "Cross-Attribute Invariants"
- D. Identify "Relationships" between entities
- E. Document overall entity descriptions

### 2. Extract Feature Hierarchy from Specification: Feature > Rule > Example
Follow the "Functional Model Extraction Rules" in [`formulation-rules.md`](./formulation-rules.md):
- A. Extract "Features"
- B. Extract "Rules" for each feature
- C. Extract "Examples" for each rule

### 3. Output Specification Files
Follow the "Output Format Specifications" in [`formulation-rules.md`](./formulation-rules.md):
- A. Output Data Model (DBML format) → `spec/domain/erm.dbml`
- B. Output Functional Model (Gherkin Language format) → `tests/{module}/*.feature`

---

## Core Principles

**See [`formulation-rules.md`](./formulation-rules.md) for details**. Key principles include:
- **No Speculation or Arbitrary Assumptions**: Strictly adhere to raw specification text content; do not assume or supplement on your own
- **Specification Expression Formats**: DBML (Data Model) and Gherkin Language (Functional Model)
- **Atomicity Rule**: Each Rule validates only one thing
- **Syntax Consistency**: Step definitions in Feature Files maintain consistent syntax
