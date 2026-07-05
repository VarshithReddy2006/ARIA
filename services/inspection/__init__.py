"""Modular Inspection Packs exports."""

from services.inspection.base import InspectionPack
from services.inspection.architecture import ArchitectureInspector
from services.inspection.security import SecurityInspector
from services.inspection.performance import PerformanceInspector
from services.inspection.dependency import DependencyInspector
from services.inspection.complexity import ComplexityInspector
from services.inspection.dead_code import DeadCodeInspector
from services.inspection.documentation import DocumentationInspector
from services.inspection.testing import TestingInspector

__all__ = [
    "InspectionPack",
    "ArchitectureInspector",
    "SecurityInspector",
    "PerformanceInspector",
    "DependencyInspector",
    "ComplexityInspector",
    "DeadCodeInspector",
    "DocumentationInspector",
    "TestingInspector",
]
