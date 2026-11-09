"""Modelo normativo carregado a partir de arquivo de dados.

Os critérios (resultados esperados) ficam em JSON, separados da lógica da
aplicação: uma atualização do Guia MPS exige apenas um novo arquivo de dados,
sem reescrever código (mitigação do risco de mudança no modelo).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_MODEL = DATA_DIR / "nivel_g_2024.json"


@dataclass(frozen=True)
class Note:
    kind: str  # "requerido" | "informativo"
    text: str


@dataclass(frozen=True)
class Criterion:
    """Um item avaliável: resultado esperado ou resultado de capacidade (CP-G)."""
    id: str            # identificador estável, ex.: "GPR 5" ou "CP-Proj (ii)"
    code: str          # rótulo curto exibido, ex.: "GPR 5" ou "CP-G ii"
    title: str
    text: str
    process: str       # "GPR" | "REQ" | "CP-Proj"
    group: str         # "Planejamento", "Capacidade (CP-G)", ...
    kind: str          # "resultado" | "capacidade"
    notes: tuple[Note, ...] = ()
    hint: str = ""
    ref: str = ""      # referência usada no Relatório de Ajustes: "GPR 5" ou "ii"


@dataclass(frozen=True)
class Rating:
    code: str
    label: str
    short: str
    tone: str
    satisfies: bool
    finding: str | None = None     # tipo de apontamento exigido: None | "melhoria" | "requerido"
    neutral: bool = False          # NA: não conta a favor nem contra


@dataclass
class Process:
    code: str
    name: str
    purpose: str
    groups: list[tuple[str, list[Criterion]]] = field(default_factory=list)
    kind: str = "processo"         # "processo" | "capacidade"

    @property
    def criteria(self) -> list[Criterion]:
        return [c for _, items in self.groups for c in items]

    @property
    def sheet_name(self) -> str:
        """Nome usado na coluna PROCESSO do Relatório de Ajustes."""
        return f"{self.name} ({self.code})" if self.kind == "capacidade" else self.name


@dataclass(frozen=True)
class FindingLabels:
    requerido: str = "REQUERIDO"
    melhoria: str = "MELHORIA"
    description_req: str = "Problema"
    suggestion: str = "Sugestão de correção"
    description_mel: str = "Oportunidade de melhoria"
    impact: tuple[str, ...] = ("-", "LEVE")
    correction: tuple[str, ...] = ("Sim", "Não", "Sem Correção")
    source: str = ""


@dataclass
class NormModel:
    id: str
    name: str
    level: str
    level_name: str
    version: str
    source: str
    scope_note: str
    checksum: str
    scale: list[Rating]
    processes: list[Process]
    final_scale: list[Rating] = field(default_factory=list)
    level_processes: list[tuple[str, str]] = field(default_factory=list)   # (código, nome) exigidos no nível
    level_source: str = ""
    labels: FindingLabels = field(default_factory=FindingLabels)

    @property
    def assessed(self) -> list[Process]:
        """Processos propriamente ditos (sem o bloco de capacidade)."""
        return [p for p in self.processes if p.kind == "processo"]

    @property
    def capability(self) -> Process | None:
        return next((p for p in self.processes if p.kind == "capacidade"), None)

    @property
    def out_of_scope(self) -> list[tuple[str, str]]:
        """Processos exigidos pelo nível que esta ferramenta não avalia (ex.: CAP)."""
        assessed = {p.code for p in self.processes}
        return [(c, n) for c, n in self.level_processes if c not in assessed]

    @property
    def criteria(self) -> list[Criterion]:
        return [c for p in self.processes for c in p.criteria]

    def criterion(self, cid: str) -> Criterion:
        return self._index[cid]

    def has(self, cid: str) -> bool:
        return cid in self._index

    def rating(self, code: str | None) -> Rating | None:
        return self._ratings.get(code) if code else None

    def process(self, code: str) -> Process:
        return next(p for p in self.processes if p.code == code)

    def order(self, cid: str) -> int:
        return self._order.get(cid, 10_000)

    def __post_init__(self) -> None:
        if not self.final_scale:
            self.final_scale = list(self.scale)
        self._index = {c.id: c for c in self.criteria}
        self._order = {c.id: i for i, c in enumerate(self.criteria)}
        self._ratings = {r.code: r for r in self.final_scale}


def _rating(s: dict) -> Rating:
    return Rating(code=s["code"], label=s["label"], short=s["short"], tone=s["tone"],
                  satisfies=bool(s["satisfies"]), finding=s.get("finding"), neutral=bool(s.get("neutral", False)))


def load_model(path: Path | str = DEFAULT_MODEL) -> NormModel:
    raw_bytes = Path(path).read_bytes()
    raw = json.loads(raw_bytes.decode("utf-8"))
    meta = raw["model"]
    cap = raw.get("capability")
    block = (cap or {}).get("block")

    processes: list[Process] = []
    for p in raw["processes"]:
        by_id = {
            r["id"]: Criterion(
                id=r["id"], code=r["id"], title=r["title"], text=r["text"],
                process=p["code"], group="", kind="resultado",
                notes=tuple(Note(n["kind"], n["text"]) for n in r.get("notes", [])),
                hint=r.get("hint", ""), ref=r["id"],
            )
            for r in p["results"]
        }
        proc = Process(p["code"], p["name"], p["purpose"])
        seen: set[str] = set()
        for g in p["groups"]:
            items = []
            for rid in g["results"]:
                c = by_id[rid]
                items.append(Criterion(**{**c.__dict__, "group": g["name"]}))
                seen.add(rid)
            proc.groups.append((g["name"], items))
        missing = set(by_id) - seen
        if missing:
            raise ValueError(f"Resultados sem grupo em {p['code']}: {sorted(missing)}")
        if cap and not block:   # formato antigo: CP-G repetido em cada processo
            gname = f"Capacidade ({cap['code']})"
            proc.groups.append((gname, [
                Criterion(id=f"{p['code']} · {cap['code']} ({it['key']})", code=f"{cap['code']} {it['key']}",
                          title=it["title"], text=it["text"], process=p["code"], group=gname,
                          kind="capacidade", hint=it.get("hint", ""), ref=it["key"])
                for it in cap["items"]
            ]))
        processes.append(proc)

    if cap and block:           # processos de projeto tratados como um único processo (Figura 3)
        gname = f"{cap['name']} ({cap['code']})"
        proc = Process(block["code"], block["name"], block.get("purpose", ""), kind="capacidade")
        proc.groups.append((gname, [
            Criterion(id=f"{block['code']} ({it['key']})", code=f"{cap['code']} {it['key']}",
                      title=it["title"], text=it["text"], process=block["code"], group=gname,
                      kind="capacidade", hint=it.get("hint", ""), ref=it["key"])
            for it in cap["items"]
        ]))
        processes.append(proc)

    scale = [_rating(s) for s in raw["scale"]]
    f = raw.get("findings", {})
    labels = FindingLabels(
        requerido=f.get("requerido", {}).get("label", "REQUERIDO"),
        melhoria=f.get("melhoria", {}).get("label", "MELHORIA"),
        description_req=f.get("requerido", {}).get("description", "Problema"),
        suggestion=f.get("requerido", {}).get("suggestion", "Sugestão de correção"),
        description_mel=f.get("melhoria", {}).get("description", "Oportunidade de melhoria"),
        impact=tuple(f.get("impact", ("-", "LEVE"))),
        correction=tuple(f.get("correction", ("Sim", "Não", "Sem Correção"))),
        source=f.get("source", ""),
    )
    return NormModel(
        id=meta["id"], name=meta["name"], level=meta["level"],
        level_name=meta["level_name"], version=meta["version"],
        source=meta.get("source", ""), scope_note=meta.get("scope_note", ""),
        checksum=hashlib.sha256(raw_bytes).hexdigest()[:12],
        scale=scale, processes=processes,
        final_scale=scale + [_rating(s) for s in raw.get("final_scale_extra", [])],
        level_processes=[(p["code"], p["name"]) for p in raw.get("level_requirements", {}).get("processes", [])],
        level_source=raw.get("level_requirements", {}).get("source", ""),
        labels=labels,
    )
