"""``class B(A): def foo(self): super().foo()`` fixture."""


class A:
    def foo(self) -> int:
        return 1


class B(A):
    def foo(self) -> int:
        return super().foo()
