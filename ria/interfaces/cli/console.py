"""CLI Console output formatter."""


class ConsoleFormatter:
    """Formatter for terminal console output."""

    @staticmethod
    def print_success(msg: str) -> str:
        out = f"[SUCCESS] {msg}"
        print(out)
        return out

    @staticmethod
    def print_error(msg: str) -> str:
        out = f"[ERROR] {msg}"
        print(out)
        return out

    @staticmethod
    def print_info(msg: str) -> str:
        out = f"[INFO] {msg}"
        print(out)
        return out
