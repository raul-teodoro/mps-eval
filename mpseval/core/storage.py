"""Persistência local em SQLite (Módulo III).

Cada alteração é gravada imediatamente, o que permite pausar e retomar uma
avaliação a qualquer momento. Uma trilha de auditoria registra toda mudança
de caracterização, evidência, apontamento ou correção (rastreabilidade).

Fases (Guia de Avaliação MPS 2024, Parte I):
* ``inicial``: o avaliador caracteriza os resultados e registra os apontamentos
  que formam o Relatório de Ajustes para a Avaliação Final;
* ``final``: revisita dos resultados com apontamento, com registro da correção
  feita pela empresa e da nova caracterização.
``status`` indica se a fase atual está concluída (``finalizada``).
"""
from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assessments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    organization    TEXT NOT NULL,
    project         TEXT NOT NULL,
    evaluator       TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    model_checksum  TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'em_andamento',
    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
    current_item    TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    finished_at     TEXT
);

CREATE TABLE IF NOT EXISTS answers (
    assessment_id INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    item_id       TEXT NOT NULL,
    rating        TEXT,
    justification TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (assessment_id, item_id)
);

CREATE TABLE IF NOT EXISTS evidences (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    item_id       TEXT NOT NULL,
    kind          TEXT NOT NULL,          -- 'texto' | 'arquivo'
    content       TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_evid ON evidences(assessment_id, item_id);

CREATE TABLE IF NOT EXISTS findings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id     INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    process           TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',   -- problema ou oportunidade de melhoria
    suggestion        TEXT NOT NULL DEFAULT '',   -- sugestão de correção (apenas problema)
    impact            TEXT NOT NULL DEFAULT '-',
    correction_status TEXT,                       -- 'Sim' | 'Não' | 'Sem Correção'
    correction_text   TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finding_items (
    finding_id INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    item_id    TEXT NOT NULL,
    PRIMARY KEY (finding_id, item_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    item_id       TEXT,
    action        TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT '',
    at            TEXT NOT NULL
);
"""

# colunas acrescentadas depois da primeira versão (migração automática)
_NEW_COLUMNS = {
    "assessments": [("phase", "TEXT NOT NULL DEFAULT 'inicial'"), ("initial_finished_at", "TEXT"),
                    ("final_started_at", "TEXT"), ("elapsed_final", "INTEGER NOT NULL DEFAULT 0")],
    "answers": [("final_rating", "TEXT")],
}

FINDING_FIELDS = ("description", "suggestion", "impact", "correction_status", "correction_text")
TEXT_FIELDS = ("description", "suggestion", "correction_text")

# Caracteres de controle que o Excel não aceita (são os mesmos que o openpyxl recusa). Aparecem quando
# se cola texto copiado de PDF: no Guia MPS, por exemplo, o hífen de "caracteriza-se" vem como \x02.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_text(text: str | None) -> str:
    """Remove caracteres de controle de texto colado (mantém quebras de linha e tabulação)."""
    if not text:
        return text or ""
    return _CONTROL.sub("", text.replace("\x02", "-").replace("\r\n", "\n"))


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def default_db_path() -> Path:
    base = os.environ.get("MPSEVAL_HOME")
    if base:
        root = Path(base)
    elif os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home())) / "MPS-Eval"
    else:
        root = Path.home() / ".mps-eval"
    root.mkdir(parents=True, exist_ok=True)
    return root / "mpseval.sqlite3"


@dataclass
class Evidence:
    id: int
    kind: str
    content: str
    created_at: str


@dataclass
class Answer:
    rating: str | None = None
    justification: str = ""            # campo legado (versão 1); migrado para apontamentos
    evidences: list[Evidence] = field(default_factory=list)
    final_rating: str | None = None


@dataclass
class Finding:
    """Linha do Relatório de Ajustes: um apontamento ligado a um ou mais resultados."""
    id: int
    process: str
    description: str = ""
    suggestion: str = ""
    impact: str = "-"
    correction_status: str | None = None
    correction_text: str = ""
    items: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not (self.description.strip() or self.suggestion.strip() or self.correction_text.strip())


@dataclass
class Assessment:
    id: int
    organization: str
    project: str
    evaluator: str
    model_id: str
    model_version: str
    model_checksum: str
    status: str
    elapsed_seconds: int
    current_item: str | None
    created_at: str
    updated_at: str
    finished_at: str | None
    phase: str = "inicial"
    initial_finished_at: str | None = None
    final_started_at: str | None = None
    elapsed_final: int = 0

    @property
    def finished(self) -> bool:
        """A fase atual está concluída (registros bloqueados)."""
        return self.status == "finalizada"

    @property
    def in_final(self) -> bool:
        return self.phase == "final"

    @property
    def completed(self) -> bool:
        """Toda a avaliação encerrada (sem avaliação final pendente)."""
        return self.finished and self.in_final

    @property
    def phase_elapsed(self) -> int:
        return self.elapsed_final if self.in_final else self.elapsed_seconds

    @property
    def total_elapsed(self) -> int:
        return self.elapsed_seconds + self.elapsed_final


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = str(path or default_db_path())
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate_columns()

    def close(self) -> None:
        self.db.close()

    def _migrate_columns(self) -> None:
        for table, cols in _NEW_COLUMNS.items():
            have = {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        self.db.commit()

    # ---------------------------------------------------------- assessments
    def create(self, organization: str, project: str, evaluator: str, model) -> Assessment:
        ts = now()
        cur = self.db.execute(
            "INSERT INTO assessments (organization, project, evaluator, model_id, model_version,"
            " model_checksum, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (clean_text(organization).strip(), clean_text(project).strip(), clean_text(evaluator).strip(), model.id,
             model.version, model.checksum, ts, ts),
        )
        self._log(cur.lastrowid, None, "criada", f"{organization} / {project}")
        self.db.commit()
        return self.get(cur.lastrowid)

    def get(self, aid: int) -> Assessment:
        row = self.db.execute("SELECT * FROM assessments WHERE id=?", (aid,)).fetchone()
        if row is None:
            raise KeyError(aid)
        return Assessment(**dict(row))

    def list(self) -> list[Assessment]:
        rows = self.db.execute("SELECT * FROM assessments ORDER BY updated_at DESC, id DESC").fetchall()
        return [Assessment(**dict(r)) for r in rows]

    def update_info(self, aid: int, organization: str, project: str, evaluator: str) -> None:
        self.db.execute(
            "UPDATE assessments SET organization=?, project=?, evaluator=?, updated_at=? WHERE id=?",
            (clean_text(organization).strip(), clean_text(project).strip(), clean_text(evaluator).strip(), now(), aid))
        self._log(aid, None, "dados_editados", f"{organization} / {project} / {evaluator}")
        self.db.commit()

    def delete(self, aid: int) -> None:
        self.db.execute("DELETE FROM assessments WHERE id=?", (aid,))
        self.db.commit()

    def set_current(self, aid: int, item_id: str) -> None:
        self.db.execute("UPDATE assessments SET current_item=? WHERE id=?", (item_id, aid))
        self.db.commit()

    def add_elapsed(self, aid: int, seconds: int) -> None:
        """Soma o tempo à fase atual (inicial ou final)."""
        if seconds <= 0:
            return
        col = "elapsed_final" if self.get(aid).in_final else "elapsed_seconds"
        self.db.execute(f"UPDATE assessments SET {col} = {col} + ? WHERE id=?", (seconds, aid))
        self.db.commit()

    def set_status(self, aid: int, finished: bool) -> None:
        """Conclui ou reabre a fase atual."""
        ts = now()
        a = self.get(aid)
        self.db.execute(
            "UPDATE assessments SET status=?, finished_at=?, updated_at=? WHERE id=?",
            ("finalizada" if finished else "em_andamento", ts if finished else None, ts, aid))
        if finished and not a.in_final:
            self.db.execute("UPDATE assessments SET initial_finished_at=? WHERE id=?", (ts, aid))
        fase = "avaliação final" if a.in_final else "avaliação inicial"
        self._log(aid, None, "finalizada" if finished else "reaberta", fase)
        self.db.commit()

    def start_final(self, aid: int) -> None:
        """Encerra a avaliação inicial e abre a revisita (avaliação final)."""
        ts = now()
        a = self.get(aid)
        self.db.execute(
            "UPDATE assessments SET phase='final', status='em_andamento', finished_at=NULL,"
            " initial_finished_at=COALESCE(initial_finished_at, ?),"
            " final_started_at=COALESCE(final_started_at, ?), updated_at=? WHERE id=?",
            (ts, ts, ts, aid))
        self._log(aid, None, "avaliacao_final_iniciada", "" if a.final_started_at is None else "retomada")
        self.db.commit()

    def back_to_initial(self, aid: int) -> None:
        """Volta à avaliação inicial (os registros da avaliação final são mantidos)."""
        ts = now()
        self.db.execute("UPDATE assessments SET phase='inicial', status='em_andamento', finished_at=NULL,"
                        " updated_at=? WHERE id=?", (ts, aid))
        self._log(aid, None, "reaberta", "retorno à avaliação inicial")
        self.db.commit()

    # -------------------------------------------------------------- answers
    def answers(self, aid: int) -> dict[str, Answer]:
        out: dict[str, Answer] = {}
        for r in self.db.execute(
                "SELECT item_id, rating, justification, final_rating FROM answers WHERE assessment_id=?", (aid,)):
            out[r["item_id"]] = Answer(r["rating"], r["justification"], final_rating=r["final_rating"])
        for r in self.db.execute(
                "SELECT id, item_id, kind, content, created_at FROM evidences"
                " WHERE assessment_id=? ORDER BY id", (aid,)):
            out.setdefault(r["item_id"], Answer()).evidences.append(
                Evidence(r["id"], r["kind"], r["content"], r["created_at"]))
        return out

    def _upsert(self, aid: int, item_id: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO answers (assessment_id, item_id, updated_at) VALUES (?,?,?)",
            (aid, item_id, now()))

    def _touch(self, aid: int, item_id: str | None = None) -> None:
        ts = now()
        if item_id:
            self.db.execute("UPDATE answers SET updated_at=? WHERE assessment_id=? AND item_id=?",
                            (ts, aid, item_id))
        self.db.execute("UPDATE assessments SET updated_at=? WHERE id=?", (ts, aid))

    def _set_answer_col(self, aid: int, item_id: str, col: str, value, action: str) -> None:
        self._upsert(aid, item_id)
        old = self.db.execute(f"SELECT {col} FROM answers WHERE assessment_id=? AND item_id=?",
                              (aid, item_id)).fetchone()[col]
        if old == value:
            return
        self.db.execute(f"UPDATE answers SET {col}=? WHERE assessment_id=? AND item_id=?", (value, aid, item_id))
        self._touch(aid, item_id)
        self._log(aid, item_id, action, f"{old or '—'} → {value or '—'}")
        self.db.commit()

    def set_rating(self, aid: int, item_id: str, rating: str | None) -> None:
        self._set_answer_col(aid, item_id, "rating", rating, "caracterizacao")

    def set_final_rating(self, aid: int, item_id: str, rating: str | None) -> None:
        self._set_answer_col(aid, item_id, "final_rating", rating, "caracterizacao_final")

    def set_justification(self, aid: int, item_id: str, text: str) -> None:
        """Campo legado, mantido para compatibilidade com bancos da versão 1."""
        self._upsert(aid, item_id)
        self.db.execute("UPDATE answers SET justification=? WHERE assessment_id=? AND item_id=?",
                        (text, aid, item_id))
        self._touch(aid, item_id)
        self.db.commit()

    def add_evidence(self, aid: int, item_id: str, kind: str, content: str) -> Evidence:
        ts = now()
        content = clean_text(content)
        self._upsert(aid, item_id)
        cur = self.db.execute(
            "INSERT INTO evidences (assessment_id, item_id, kind, content, created_at) VALUES (?,?,?,?,?)",
            (aid, item_id, kind, content.strip(), ts))
        self._touch(aid, item_id)
        self._log(aid, item_id, "evidencia_adicionada", content.strip()[:200])
        self.db.commit()
        return Evidence(cur.lastrowid, kind, content.strip(), ts)

    def remove_evidence(self, aid: int, item_id: str, evidence_id: int) -> None:
        row = self.db.execute("SELECT content FROM evidences WHERE id=? AND assessment_id=?",
                              (evidence_id, aid)).fetchone()
        self.db.execute("DELETE FROM evidences WHERE id=? AND assessment_id=?", (evidence_id, aid))
        self._touch(aid, item_id)
        self._log(aid, item_id, "evidencia_removida", (row["content"] if row else "")[:200])
        self.db.commit()

    # ------------------------------------------------------------- findings
    def findings(self, aid: int) -> list[Finding]:
        links: dict[int, list[str]] = {}
        for r in self.db.execute(
                "SELECT fi.finding_id, fi.item_id FROM finding_items fi JOIN findings f ON f.id = fi.finding_id"
                " WHERE f.assessment_id=? ORDER BY fi.rowid", (aid,)):
            links.setdefault(r["finding_id"], []).append(r["item_id"])
        out = []
        for r in self.db.execute("SELECT * FROM findings WHERE assessment_id=? ORDER BY id", (aid,)):
            out.append(Finding(r["id"], r["process"], r["description"], r["suggestion"], r["impact"],
                               r["correction_status"], r["correction_text"], tuple(links.get(r["id"], ()))))
        return out

    def finding(self, aid: int, fid: int) -> Finding:
        return next(f for f in self.findings(aid) if f.id == fid)

    def create_finding(self, aid: int, process: str, item_ids, description: str = "") -> Finding:
        ts = now()
        description = clean_text(description)
        cur = self.db.execute(
            "INSERT INTO findings (assessment_id, process, description, created_at, updated_at) VALUES (?,?,?,?,?)",
            (aid, process, description, ts, ts))
        fid = cur.lastrowid
        for item in item_ids:
            self.db.execute("INSERT OR IGNORE INTO finding_items (finding_id, item_id) VALUES (?,?)", (fid, item))
        self._touch(aid)
        self._log(aid, None, "apontamento_criado", f"#{fid} · {', '.join(item_ids)}")
        self.db.commit()
        return self.finding(aid, fid)

    def update_finding(self, aid: int, fid: int, **values) -> None:
        bad = set(values) - set(FINDING_FIELDS)
        if bad:
            raise ValueError(f"Campos inválidos: {sorted(bad)}")
        values = {k: clean_text(v) if k in TEXT_FIELDS else v for k, v in values.items()}
        row = self.db.execute("SELECT * FROM findings WHERE id=? AND assessment_id=?", (fid, aid)).fetchone()
        if row is None:
            raise KeyError(fid)
        changed = {k: v for k, v in values.items() if row[k] != v}
        if not changed:
            return
        sets = ", ".join(f"{k}=?" for k in changed)
        self.db.execute(f"UPDATE findings SET {sets}, updated_at=? WHERE id=?", (*changed.values(), now(), fid))
        self._touch(aid)
        for k, v in changed.items():
            detail = f"{len(v.strip())} caracteres" if k in ("description", "suggestion", "correction_text") \
                else f"{row[k] or '—'} → {v or '—'}"
            self._log(aid, None, f"apontamento_{k}", f"#{fid} · {detail}")
        self.db.commit()

    def set_finding_items(self, aid: int, fid: int, item_ids) -> None:
        """Define os resultados ligados ao apontamento; sem resultados, o apontamento é excluído."""
        item_ids = list(dict.fromkeys(item_ids))
        if not item_ids:
            self.delete_finding(aid, fid)
            return
        old = [r["item_id"] for r in self.db.execute(
            "SELECT item_id FROM finding_items WHERE finding_id=? ORDER BY rowid", (fid,))]
        if old == item_ids:
            return
        self.db.execute("DELETE FROM finding_items WHERE finding_id=?", (fid,))
        for item in item_ids:
            self.db.execute("INSERT INTO finding_items (finding_id, item_id) VALUES (?,?)", (fid, item))
        self.db.execute("UPDATE findings SET updated_at=? WHERE id=?", (now(), fid))
        self._touch(aid)
        self._log(aid, None, "apontamento_vinculos", f"#{fid} · {', '.join(old)} → {', '.join(item_ids)}")
        self.db.commit()

    def delete_finding(self, aid: int, fid: int) -> None:
        self.db.execute("DELETE FROM findings WHERE id=? AND assessment_id=?", (fid, aid))
        self._touch(aid)
        self._log(aid, None, "apontamento_excluido", f"#{fid}")
        self.db.commit()

    # ------------------------------------------------------------ migração
    def upgrade_data(self, model) -> None:
        """Converte dados da versão 1: CP-G por processo → CP-Proj, justificativa → apontamento."""
        cap = getattr(model, "capability", None)
        worst = {r.code: i for i, r in enumerate(model.scale)}
        if cap is not None:
            old_rows = self.db.execute(
                "SELECT * FROM answers WHERE item_id LIKE '% · CP-G (%)' ORDER BY assessment_id, item_id").fetchall()
            merged: dict[tuple[int, str], dict] = {}
            for r in old_rows:
                key = r["item_id"].rsplit("(", 1)[1].rstrip(")")
                new_id = f"{cap.code} ({key})"
                m = merged.setdefault((r["assessment_id"], new_id), {"rating": None, "just": []})
                if r["rating"] and (m["rating"] is None or worst.get(r["rating"], 0) > worst.get(m["rating"], 0)):
                    m["rating"] = r["rating"]
                if r["justification"].strip():
                    m["just"].append(f"[{r['item_id'].split(' · ')[0]}] {r['justification'].strip()}")
            for (aid, new_id), m in merged.items():
                exists = self.db.execute("SELECT 1 FROM answers WHERE assessment_id=? AND item_id=?",
                                         (aid, new_id)).fetchone()
                if not exists:
                    self.db.execute("INSERT INTO answers (assessment_id, item_id, rating, justification, updated_at)"
                                    " VALUES (?,?,?,?,?)", (aid, new_id, m["rating"], "\n\n".join(m["just"]), now()))
            for table in ("evidences", "audit_log"):
                for r in self.db.execute(f"SELECT DISTINCT item_id FROM {table} WHERE item_id LIKE '% · CP-G (%)'"
                                         ).fetchall():
                    key = r["item_id"].rsplit("(", 1)[1].rstrip(")")
                    self.db.execute(f"UPDATE {table} SET item_id=? WHERE item_id=?",
                                    (f"{cap.code} ({key})", r["item_id"]))
            self.db.execute("DELETE FROM answers WHERE item_id LIKE '% · CP-G (%)'")

        linked = {(r["assessment_id"], r["item_id"]) for r in self.db.execute(
            "SELECT f.assessment_id, fi.item_id FROM finding_items fi JOIN findings f ON f.id = fi.finding_id")}
        for r in self.db.execute("SELECT * FROM answers WHERE justification <> ''").fetchall():
            rt = model.rating(r["rating"])
            if not (rt and rt.finding and model.has(r["item_id"])) or (r["assessment_id"], r["item_id"]) in linked:
                continue
            c = model.criterion(r["item_id"])
            ts = now()
            cur = self.db.execute("INSERT INTO findings (assessment_id, process, description, created_at, updated_at)"
                                  " VALUES (?,?,?,?,?)", (r["assessment_id"], c.process, r["justification"].strip(),
                                                          ts, ts))
            self.db.execute("INSERT INTO finding_items (finding_id, item_id) VALUES (?,?)", (cur.lastrowid, c.id))
            self.db.execute("UPDATE answers SET justification='' WHERE assessment_id=? AND item_id=?",
                            (r["assessment_id"], r["item_id"]))
            self._log(r["assessment_id"], c.id, "apontamento_migrado", "justificativa da versão 1")
        self.db.commit()

    # ---------------------------------------------------------------- audit
    def _log(self, aid: int, item_id: str | None, action: str, detail: str = "") -> None:
        self.db.execute("INSERT INTO audit_log (assessment_id, item_id, action, detail, at) VALUES (?,?,?,?,?)",
                        (aid, item_id, action, detail, now()))

    def audit(self, aid: int) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM audit_log WHERE assessment_id=? ORDER BY id", (aid,)).fetchall()
