from questr.hello.domain import get_greeting


class HelloService:
    def get_greeting(self) -> str:  # noqa: PLR6301
        return get_greeting()
