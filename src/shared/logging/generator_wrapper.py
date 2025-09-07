"""Generator wrapper for LoguruIO."""

from typing import TYPE_CHECKING

from src.shared.logging.loguru_io_constants import GeneratorMethod
from src.shared.logging.loguru_io_utils import reset_call_depth


if TYPE_CHECKING:
    from src.shared.logging.loguru_io import LoguruIO


class GeneratorWrapper:
    def __init__(self, gen, custom_logger):
        self.gen = gen
        self._logger: LoguruIO = custom_logger

    def __iter__(self):
        return self

    def __next__(self):
        try:
            self._logger.log_args_kwargs(None, yield_method=GeneratorMethod.NEXT)
            out = next(self.gen)
            self._logger.log_return(out, yield_method=GeneratorMethod.NEXT)
            return out
        except StopIteration as e:
            self._logger.log_return(e.value, yield_method=GeneratorMethod.NEXT)
            raise
        except Exception as e:
            self._logger.log_error(e)
        finally:
            reset_call_depth()

    def send(self, value):
        try:
            self._logger.log_args_kwargs(value, yield_method=GeneratorMethod.SEND)
            out = self.gen.send(value)
            self._logger.log_return(out, yield_method=GeneratorMethod.SEND)
            return out
        except StopIteration as e:
            self._logger.log_return(e.value, yield_method=GeneratorMethod.SEND)
            raise
        except Exception as e:
            self._logger.log_error(e)
        finally:
            reset_call_depth()

    def throw(self, exc_type, exc_val=None, tb=None):
        try:
            self._logger.log_args_kwargs(exc_type=exc_type, exc_val=exc_val, tb=tb, yield_method=GeneratorMethod.THROW)
            out = self.gen.throw(exc_type, exc_val, tb)
            self._logger.log_return(out, yield_method=GeneratorMethod.THROW)
            return out
        except StopIteration as e:
            self._logger.log_return(e.value, yield_method=GeneratorMethod.THROW)
            raise
        except Exception as e:
            self._logger.log_error(e)
        finally:
            reset_call_depth()

    def close(self):
        self.gen.close()
