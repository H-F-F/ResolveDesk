from __future__ import annotations

from typing import Any, Callable, TypeVar


F = TypeVar("F", bound=Callable[..., Any])


try:
    from langsmith import traceable as _traceable
except ImportError:

    def traceable(*args: Any, **kwargs: Any) -> Callable[[F], F] | F:
        if args and callable(args[0]) and not kwargs:
            return args[0]

        def decorator(func: F) -> F:
            return func

        return decorator

else:

    def traceable(*args: Any, **kwargs: Any) -> Callable[[F], F] | F:
        return _traceable(*args, **kwargs)

