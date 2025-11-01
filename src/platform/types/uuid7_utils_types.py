"""
https://docs.pydantic.dev/latest/concepts/types/#customizing-validation-with-__get_pydantic_core_schema__
https://docs.pydantic.dev/latest/concepts/json_schema/#implementing-__get_pydantic_json_schema__
UUID7 Pydantic Type Integration

This module integrates uuid_utils.UUID with Pydantic to enable proper UUID7 usage in FastAPI.

## Problem Solved

uuid_utils.UUID doesn't natively support Pydantic validation or OpenAPI schema generation.
This wrapper class (UtilsUUID7) provides the necessary Pydantic integration.

## Usage

```python
from pydantic import BaseModel
from src.platform.types.uuid7_utils_types import UtilsUUID7

class BookingRequest(BaseModel):
    booking_id: UtilsUUID7  # FastAPI handles validation and serialization automatically

# FastAPI automatically handles:
# - Request validation: JSON string → UUID object
# - Response serialization: UUID object → JSON string
# - OpenAPI schema: Display as type: string, format: uuid
```

## Technical Details

1. **json_or_python_schema**: Separates validation logic for JSON and Python modes
2. **OpenAPI Compatible**: Returns JSON schema directly without relying on handler(schema)
"""

from typing import Any

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
from uuid_utils import UUID


class UtilsUUID7(UUID):
    """
    Pydantic-compatible UUID7 type

    Inherits from uuid_utils.UUID and implements Pydantic's required schema generation methods.

    ## Why is this class needed?

    uuid_utils.UUID is a pure Python UUID class that doesn't support:
    - Pydantic model validation
    - FastAPI automatic serialization/deserialization
    - OpenAPI schema generation

    This class implements two core Pydantic v2 methods:
    1. __get_pydantic_core_schema__: Defines validation and serialization logic
    2. __get_pydantic_json_schema__: Defines schema for OpenAPI documentation
    ```
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """
        Define how Pydantic validates and serializes this type

        ## Why use json_or_python_schema?

        Pydantic has two validation modes:
        1. **JSON mode**: Handles HTTP requests (parsed from JSON)
        2. **Python mode**: Handles internal code (created from Python objects)

        Using json_or_python_schema allows different validation logic for each mode:
        - JSON mode: Only accepts string (JSON has no UUID type)
        - Python mode: Accepts UUID objects or strings (more flexible)

        ## Why not use with_info_plain_validator_function?

        with_info_plain_validator_function returns PlainValidatorFunctionSchema
        which cannot be converted to JSON schema (required by FastAPI OpenAPI), causing:
        ```
        PydanticInvalidForJsonSchema: Cannot generate a JsonSchema for core_schema.PlainValidatorFunctionSchema
        ```

        ## Schema Structure

        ```python
        json_or_python_schema(
            json_schema=chain_schema([
                str_schema(),              # Step 1: Check if string
                validator(validate_json),  # Step 2: Convert to UUID
            ]),
            python_schema=union_schema([
                is_instance(UUID),         # Option 1: Already UUID object
                chain_schema([
                    str_schema(),          # Option 2 Step 1: Is string
                    validator(validate),   # Option 2 Step 2: Convert to UUID
                ])
            ]),
            serialization=always_str,      # Serialization: Always convert to string
        )
        ```

        ## Example Flows

        **FastAPI Request** (JSON mode):
        ```
        HTTP Request: {"booking_id": "019a3fa5-..."}
                ↓ str_schema() validation
                ↓ validate_uuid_json() conversion
        Python: booking_id = UUID("019a3fa5-...")
        ```

        **Internal Creation** (Python mode):
        ```
        Code: MyModel(booking_id=uuid7())
                ↓ is_instance(UUID) check
        Result: Use directly, no conversion needed
        ```

        **FastAPI Response** (serialization):
        ```
        Python: booking_id = UUID("019a3fa5-...")
                ↓ serialization=str
        HTTP Response: {"booking_id": "019a3fa5-..."}
        ```

        Args:
            source_type: Source type (UtilsUUID7)
            handler: Pydantic's schema handler

        Returns:
            core_schema.CoreSchema: Pydantic validation schema
        """

        def _to_uuid(value: Any) -> UUID:
            try:
                return UUID(str(value))
            except Exception as e:
                raise ValueError(f'Invalid UUID: {value}') from e

        def validate_uuid_python(value: Any) -> UUID:
            """
            Python mode validator: Accepts UUID objects or strings

            Use case: Internal code directly creates Pydantic models
            ```python
            # Case 1: Accepts UUID object
            booking = Booking(id=uuid7())

            # Case 2: Accepts string
            booking = Booking(id="019a3fa5-...")
            ```

            Args:
                value: UUID object or string

            Returns:
                UUID: uuid_utils.UUID object

            Raises:
                ValueError: If cannot convert to valid UUID
            """
            # If already UUID object, return directly (most common case)
            if isinstance(value, UUID):
                return value

            # If string, attempt to convert to UUID
            return _to_uuid(value)

        def validate_uuid_json(value: str) -> UUID:
            """
            JSON standard has no UUID type, so it must be a string.

            Args:
                value: UUID string

            Returns:
                UUID: uuid_utils.UUID object

            Raises:
                ValueError: If string is not valid UUID format
            """
            return _to_uuid(value)

        # Build Pydantic schema
        # Note: This schema must be convertible to JSON schema (for OpenAPI)
        return core_schema.json_or_python_schema(
            # === JSON Mode (HTTP requests) ===
            # Use chain_schema to chain multiple validation steps
            json_schema=core_schema.chain_schema(
                [
                    # Step 1: Validate input is string
                    core_schema.str_schema(),
                    # Step 2: Convert string to UUID object
                    core_schema.no_info_plain_validator_function(validate_uuid_json),
                ]
            ),
            # === Python Mode (internal code) ===
            # Use union_schema to support multiple input types
            python_schema=core_schema.union_schema(
                [
                    # Option 1: If already UUID object, accept directly
                    core_schema.is_instance_schema(UUID),
                    # Option 2: If string, convert to UUID
                    core_schema.chain_schema(
                        [
                            core_schema.str_schema(),
                            core_schema.no_info_plain_validator_function(validate_uuid_python),
                        ]
                    ),
                ]
            ),
            # === Serialization (HTTP responses) ===
            # Regardless of input, output is always string
            # when_used='always': Serialize to string even in Python mode
            # return_schema=str_schema(): Tell Pydantic serialization result is string
            serialization=core_schema.plain_serializer_function_ser_schema(
                str,  # Use built-in str() function for serialization
                when_used='always',
                return_schema=core_schema.str_schema(),
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """
        We bypass `handler(schema)` intentionally:
        - It would expand the full internal `core_schema` structure
          (json_or_python_schema, chain_schema, validators, etc.)
        - Those details are irrelevant to OpenAPI
        - They often produce overly verbose or invalid JSON Schema
        Instead, we return a clean, OpenAPI-compatible schema definition.

        """
        return {'type': 'string', 'format': 'uuid'}
