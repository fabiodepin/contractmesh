"""Example application service for ContractMesh basic workspace smoke tests."""


class ExampleService:
    """Provides greeting behavior referenced by APP-CONTRACT-001."""

    def greet(self, name: str) -> str:
        if not name or not name.strip():
            raise ValueError("name is required")
        return f"Hello, {name.strip()}"
