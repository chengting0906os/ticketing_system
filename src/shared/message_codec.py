import json
from typing import Any, Dict, Union

import msgpack


class MessageCodec:
    """Handles encoding/decoding of messages with binary optimization support

    Protocol-agnostic message codec that supports both MessagePack (binary)
    and JSON (text) encoding. Can be used with WebSocket, SSE, Kafka, or any
    other messaging protocol.
    """

    @staticmethod
    def encode_message(*, data: Dict[str, Any], use_binary: bool = True) -> Union[str, bytes]:
        if use_binary:
            return msgpack.packb(data)  # type: ignore
        else:
            return json.dumps(data)

    @staticmethod
    def decode_message(*, raw_data: Union[str, bytes]) -> Dict[str, Any]:
        try:
            if isinstance(raw_data, bytes):
                # Try MessagePack first
                return msgpack.unpackb(raw_data, raw=False)
            else:
                # Text message, use JSON
                return json.loads(raw_data)
        except Exception as e:
            raise ValueError(f'Failed to decode message: {e}')

    @staticmethod
    def get_message_size(*, data: Dict[str, Any]) -> Dict[str, Union[int, float]]:
        json_size = len(json.dumps(data).encode('utf-8'))
        msgpack_size = len(msgpack.packb(data))  # type: ignore

        return {
            'json': json_size,
            'msgpack': msgpack_size,
            'compression_ratio': round(msgpack_size / json_size, 2),
        }
