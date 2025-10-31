from typing import Any

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
from uuid_utils import UUID


class UtilsUUID7(UUID):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Define how Pydantic should validate and serialize this type."""

        def validate_uuid(value: Any) -> UUID:
            if isinstance(value, UUID):
                return value
            try:
                return UUID(str(value))
            except Exception as e:
                raise ValueError(f'Invalid UUID: {value}') from e

        return core_schema.with_info_plain_validator_function(
            lambda v, _: validate_uuid(v),
            serialization=core_schema.plain_serializer_function_ser_schema(
                str,
                when_used='always',
                return_schema=core_schema.str_schema(),
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(schema)
        json_schema.update(type='string', format='uuid')
        return json_schema
