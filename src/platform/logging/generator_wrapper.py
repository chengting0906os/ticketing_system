from types import TracebackType
from typing import TYPE_CHECKING, Any, Generator, Self

from src.platform.logging.loguru_io_config import GeneratorMethod
from src.platform.logging.loguru_io_utils import reset_call_depth


if TYPE_CHECKING:
    from src.platform.logging.loguru_io import LoguruIO


class GeneratorWrapper:
    def __init__(self, gen_obj: Generator[Any, Any, Any], custom_logger: 'LoguruIO') -> None:
        self.gen_obj = gen_obj  # Store the original generator object to forward calls to
        self._custom_logger: LoguruIO = custom_logger

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> Any:
        try:
            self._custom_logger.log_args_kwargs_content(None, yield_method=GeneratorMethod.NEXT)
            out = next(self.gen_obj)
            self._custom_logger.log_return_content(out, yield_method=GeneratorMethod.NEXT)
            return out
        except StopIteration as e:
            self._custom_logger.log_return_content(e.value, yield_method=GeneratorMethod.NEXT)
            raise
        except Exception:
            raise
        finally:
            reset_call_depth()

    def send(self, value: Any) -> Any:
        try:
            self._custom_logger.log_args_kwargs_content(value, yield_method=GeneratorMethod.SEND)
            out = self.gen_obj.send(value)
            self._custom_logger.log_return_content(out, yield_method=GeneratorMethod.SEND)
            return out
        except StopIteration as e:
            self._custom_logger.log_return_content(e.value, yield_method=GeneratorMethod.SEND)
            raise
        except Exception:
            raise
        finally:
            reset_call_depth()

    def throw(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException | None = None,
        tb: TracebackType | None = None,
    ) -> Any:
        try:
            self._custom_logger.log_args_kwargs_content(
                exc_type=exc_type, exc_val=exc_val, tb=tb, yield_method=GeneratorMethod.THROW
            )
            out = self.gen_obj.throw(exc_type, exc_val, tb)
            self._custom_logger.log_return_content(out, yield_method=GeneratorMethod.THROW)
            return out
        except StopIteration as e:
            self._custom_logger.log_return_content(e.value, yield_method=GeneratorMethod.THROW)
            raise
        except Exception:
            raise
        finally:
            reset_call_depth()

    def close(self) -> None:
        self.gen_obj.close()
