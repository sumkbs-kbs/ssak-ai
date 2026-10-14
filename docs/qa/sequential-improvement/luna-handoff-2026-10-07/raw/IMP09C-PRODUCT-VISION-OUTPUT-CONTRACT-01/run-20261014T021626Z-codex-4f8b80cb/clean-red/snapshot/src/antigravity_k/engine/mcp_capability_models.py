from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class MCPFinding:
    server: str
    severity: str
    code: str
    message: str
    recommendation: str


@dataclass(frozen=True, slots=True)
class MCPCapability:
    name: str
    why_it_matters: str
    antigravity_action: str
    priority: str
    evidence_url: str


@dataclass(frozen=True, slots=True)
class MCPAuditReport:
    source: str
    servers_total: int
    servers_ready: int
    findings: list[MCPFinding] = field(default_factory=list)
    capabilities: list[MCPCapability] = field(default_factory=list)

    @property
    def blocking_count(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "warning")
