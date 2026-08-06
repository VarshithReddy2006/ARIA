"""Unit tests verifying Protocol abstractions in Phase 2 Ports Layer."""

from ria.ports import (
    ClockPort,
    FilesystemPort,
    GitClientPort,
    HashingPort,
    LoggerPort,
    MetricsPort,
    ParserPluginPort,
    ParserRegistryPort,
    RepositoryLockPort,
    RepositoryRegistryPort,
    ScannerPort,
    SyncSchedulerPort,
    WorkspacePort,
)


def test_ports_exports_exist() -> None:
    """Verify all 12 core ports are imported and exposed."""
    protocols = [
        ClockPort,
        LoggerPort,
        MetricsPort,
        GitClientPort,
        RepositoryRegistryPort,
        RepositoryLockPort,
        WorkspacePort,
        SyncSchedulerPort,
        FilesystemPort,
        HashingPort,
        ParserPluginPort,
        ParserRegistryPort,
        ScannerPort,
    ]
    for proto in protocols:
        assert hasattr(proto, "_is_protocol") or getattr(proto, "__isprotocol__", False)
