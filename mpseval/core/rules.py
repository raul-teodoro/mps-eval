"""Motor de regras: validação de cada item, omissões, consolidação, veredito e ajustes.

Regras implementadas
--------------------
Avaliação inicial
* Fail-safe de evidência: um item só está completo com caracterização E ao
  menos uma evidência registrada.
* T não exige apontamento. L exige "Oportunidade de melhoria"; P e N exigem
  "Problema" e "Sugestão de correção" (Relatório de Ajustes, Guia de
  Avaliação 2024, Parte I, p. 43).
* Um apontamento pode valer para vários resultados do mesmo processo.

Avaliação final (revisita)
* Só os resultados com apontamento (L, P ou N) são revisitados.
* Cada apontamento exige a situação da correção (Sim, Não, Sem Correção) e,
  quando corrigido, a descrição da correção realizada.
* Cada resultado revisitado exige a nova caracterização (T, L, P, N ou NA).

Requerido "Leve" (Guia de Avaliação 2024, Parte I, p. 58)
* Um ajuste REQUERIDO pode ser classificado com impacto LEVE. Se a empresa não
  o corrigir, o resultado ainda pode terminar em T, mas o problema continua
  existindo e é listado como ponto fraco no resultado final. Ver
  ``Snapshot.kept_as_weak``.

Consolidação
* Um processo é satisfeito quando todos os seus resultados esperados e os
  itens de capacidade (CP-Proj, comuns a GPR e REQ) estão em T ou L. NA não
  conta a favor nem contra.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .model import Criterion, NormModel, Process, Rating
from .storage import Answer, Finding

STAGE_INITIAL = "inicial"
STAGE_FINAL = "final"

# Valores do Relatório de Ajustes usados pela regra do requerido "Leve" (os mesmos do JSON de critérios).
IMPACT_LEVE = "LEVE"                       # coluna "IMPACTO NA AVALIAÇÃO"
NOT_CORRECTED = ("Não", "Sem Correção")    # coluna "EMPRESA REALIZOU CORREÇÃO?" sem correção feita


class State(str, Enum):
    PENDING = "pendente"        # nada registrado
    INCOMPLETE = "incompleto"   # algo registrado, mas falta requisito
    DONE = "completo"


@dataclass(frozen=True)
class ItemCheck:
    state: State
    missing: tuple[str, ...]   # mensagens curtas do que falta

    @property
    def done(self) -> bool:
        return self.state is State.DONE


@dataclass(frozen=True)
class Progress:
    done: int
    total: int

    @property
    def ratio(self) -> float:
        return self.done / self.total if self.total else 0.0

    @property
    def percent(self) -> int:
        return round(100 * self.ratio)


@dataclass(frozen=True)
class Omission:
    criterion: Criterion
    check: ItemCheck


@dataclass(frozen=True)
class ProcessResult:
    code: str
    name: str
    counts: dict[str, int]        # por código da escala + "pendente"
    total: int
    complete: bool                # todos os itens completos
    satisfied: bool | None        # None enquanto incompleto
    weak_points: tuple[str, ...]  # ids caracterizados com P/N
    kind: str = "processo"


@dataclass(frozen=True)
class ProcessVerdict:
    code: str
    name: str
    results_ok: int          # resultados esperados em T ou L
    results_total: int
    capability_ok: int       # itens de capacidade em T ou L
    capability_total: int
    pending: int
    weak_points: tuple[str, ...]
    satisfied: bool | None   # None enquanto houver pendência
    neutral: int = 0         # itens NA


@dataclass(frozen=True)
class Verdict:
    status: str                       # "incompleta" | "aderente" | "nao_aderente"
    headline: str
    explanation: str
    processes: tuple[ProcessVerdict, ...]
    weak_points: tuple[str, ...]
    pending: int
    out_of_scope: tuple[tuple[str, str], ...]
    stage: str = STAGE_INITIAL


@dataclass(frozen=True)
class WeakPoint:
    """Ponto fraco que permanece no resultado final (Guia de Avaliação 2024, Parte I, p. 58-59)."""
    cid: str
    rating: str                     # caracterização final (T, L, P ou N)
    leve: bool                      # True: T por requerido leve não corrigido
    texts: tuple[str, ...]          # problema ou oportunidade registrados nos apontamentos


@dataclass(frozen=True)
class AdjustmentRow:
    """Uma linha do Relatório de Ajustes para a Avaliação Final."""
    finding: Finding
    process: Process
    kind: str                       # "requerido" | "melhoria"
    items: tuple[str, ...]
    refs: str                       # "REQ 2, 4" ou "i, iii"
    final: str                      # nova caracterização ("L" ou "REQ 2: L; REQ 4: P")


@dataclass
class Snapshot:
    """Estado de uma avaliação num instante: respostas, apontamentos e fase."""
    model: NormModel
    answers: dict[str, Answer]
    findings: list[Finding] = field(default_factory=list)
    phase: str = STAGE_INITIAL

    def __post_init__(self) -> None:
        self._by_item: dict[str, list[Finding]] = {}
        for f in self.findings:
            for cid in f.items:
                self._by_item.setdefault(cid, []).append(f)

    # ------------------------------------------------------------ acesso
    @property
    def in_final(self) -> bool:
        return self.phase == STAGE_FINAL

    @property
    def stage(self) -> str:
        return STAGE_FINAL if self.in_final else STAGE_INITIAL

    def answer(self, cid: str) -> Answer:
        return self.answers.get(cid) or Answer()

    def initial(self, cid: str) -> Rating | None:
        return self.model.rating(self.answer(cid).rating)

    def final(self, cid: str) -> Rating | None:
        return self.model.rating(self.answer(cid).final_rating)

    def item_findings(self, cid: str) -> list[Finding]:
        return list(self._by_item.get(cid, ()))

    def active_items(self, f: Finding) -> list[str]:
        """Resultados do apontamento cuja caracterização inicial exige apontamento (L, P ou N)."""
        ids = [c for c in f.items if self.model.has(c) and (r := self.initial(c)) and r.finding]
        return sorted(ids, key=self.model.order)

    def finding_kind(self, f: Finding) -> str | None:
        kinds = {self.initial(c).finding for c in self.active_items(f)}
        if "requerido" in kinds:
            return "requerido"
        return "melhoria" if kinds else None

    def item_kind(self, cid: str) -> str | None:
        r = self.initial(cid)
        return r.finding if r else None

    def revisit(self, cid: str) -> bool:
        return bool(self.item_kind(cid))

    def revisit_ids(self) -> list[str]:
        return [c.id for c in self.model.criteria if self.revisit(c.id)]

    def scope(self) -> list[str]:
        """Itens percorridos na fase atual."""
        return self.revisit_ids() if self.in_final else [c.id for c in self.model.criteria]

    def effective(self, cid: str, stage: str | None = None) -> Rating | None:
        stage = stage or self.stage
        if stage == STAGE_FINAL and self.revisit(cid):
            return self.final(cid)
        return self.initial(cid)

    # ------------------------------------------------------------ requerido "Leve"
    # Guia de Avaliação MPS 2024, Parte I, p. 58:
    #   "Quando o Requerido for classificado como 'Leve' poderá ser caracterizado como T (totalmente
    #    implementado) e deve constar como ponto fraco na 'Apresentação Resultados Final'."
    # Leitura adotada (a confirmar com o orientador):
    #   * vale para apontamentos REQUERIDO (nota inicial P ou N) com impacto LEVE;
    #   * se a empresa corrigiu (Sim), o T é um T comum: o problema deixou de existir;
    #   * se a empresa NÃO corrigiu (Não ou Sem Correção), o avaliador ainda pode dar T. O problema,
    #     porém, continua existindo, então o resultado entra na lista de pontos fracos que permanecem
    #     (relatório PDF e revisão) e o veredito informa que o T veio dessa regra.
    # A ferramenta não força o T: só informa que ele é permitido e registra o ponto fraco quando ocorre.
    def is_leve(self, f: Finding) -> bool:
        return self.finding_kind(f) == "requerido" and f.impact == IMPACT_LEVE

    def leve_uncorrected(self, cid: str) -> list[Finding]:
        """Apontamentos requeridos leves deste resultado que a empresa não corrigiu."""
        return [f for f in self.item_findings(cid) if self.is_leve(f) and f.correction_status in NOT_CORRECTED]

    def leve_allows_t(self, cid: str) -> bool:
        """O guia permite T mesmo sem correção (há requerido leve não corrigido neste resultado)."""
        return self.item_kind(cid) == "requerido" and bool(self.leve_uncorrected(cid))

    def kept_as_weak(self, cid: str) -> bool:
        """Resultado que foi de P/N para T pela regra do requerido leve: T, mas com ponto fraco mantido."""
        r = self.final(cid)
        return self.leve_allows_t(cid) and r is not None and r.code == "T"

    def remaining_weak_points(self) -> list[WeakPoint]:
        """Pontos fracos do resultado final.

        * toda caracterização diferente de T tem ponto fraco associado (Guia de Avaliação, p. 59);
        * um T obtido pela regra do requerido leve também mantém o ponto fraco (p. 58).
        """
        out = []
        for c in self.model.criteria:
            r = self.effective(c.id, STAGE_FINAL)
            if r is None or r.neutral:
                continue
            leve = self.kept_as_weak(c.id)
            if r.code == "T" and not leve:
                continue
            texts = tuple(f.description.strip() for f in self.item_findings(c.id)
                          if self.finding_kind(f) and f.description.strip())
            out.append(WeakPoint(c.id, r.code, leve, texts))
        return out

    # ------------------------------------------------------------ checagens
    def _labels(self, kind: str) -> list[str]:
        lb = self.model.labels
        if kind == "requerido":
            return [lb.description_req.lower(), lb.suggestion.lower()]
        return [lb.description_mel.lower()]

    def check_initial(self, cid: str) -> ItemCheck:
        ans = self.answer(cid)
        fs = self.item_findings(cid)
        if not ans.rating and not ans.evidences and all(f.empty for f in fs):
            return ItemCheck(State.PENDING, ("caracterização", "evidência"))
        missing: list[str] = []
        if not ans.rating:
            missing.append("caracterização")
        if not ans.evidences:
            missing.append("evidência")
        kind = self.item_kind(cid)
        if kind:
            desc, *sugg = self._labels(kind)
            if not fs or any(not f.description.strip() for f in fs):
                missing.append(desc)
            if sugg and (not fs or any(not f.suggestion.strip() for f in fs)):
                missing.append(sugg[0])
        return ItemCheck(State.DONE if not missing else State.INCOMPLETE, tuple(missing))

    def check_final(self, cid: str) -> ItemCheck:
        if not self.revisit(cid):
            return ItemCheck(State.DONE, ())
        ans = self.answer(cid)
        fs = [f for f in self.item_findings(cid) if self.finding_kind(f)]
        missing: list[str] = []
        if any(not f.correction_status for f in fs):
            missing.append("situação da correção")
        if any(f.correction_status == "Sim" and not f.correction_text.strip() for f in fs):
            missing.append("correção realizada")
        if not ans.final_rating:
            missing.append("nova caracterização")
        if not missing:
            return ItemCheck(State.DONE, ())
        touched = ans.final_rating or any(f.correction_status or f.correction_text.strip() for f in fs)
        return ItemCheck(State.INCOMPLETE if touched else State.PENDING, tuple(missing))

    def check(self, cid: str, stage: str | None = None) -> ItemCheck:
        stage = stage or self.stage
        return self.check_final(cid) if stage == STAGE_FINAL else self.check_initial(cid)

    def progress(self, items: list[Criterion] | list[str] | None = None) -> Progress:
        scope = self.scope()
        if items is not None:
            wanted = {c if isinstance(c, str) else c.id for c in items}
            scope = [c for c in scope if c in wanted]
        return Progress(sum(1 for c in scope if self.check(c).done), len(scope))

    def omissions(self) -> list[Omission]:
        out = []
        for cid in self.scope():
            ck = self.check(cid)
            if not ck.done:
                out.append(Omission(self.model.criterion(cid), ck))
        return out

    def can_finalize(self) -> bool:
        return not self.omissions()

    # ------------------------------------------------------------ consolidação
    def _done(self, cid: str, stage: str) -> bool:
        if stage == STAGE_FINAL:
            return self.check_initial(cid).done and self.check_final(cid).done
        return self.check_initial(cid).done

    def consolidate(self, stage: str | None = None) -> list[ProcessResult]:
        stage = stage or self.stage
        results = []
        for p in self.model.processes:
            counts = {r.code: 0 for r in self.model.final_scale}
            counts["pendente"] = 0
            weak = []
            complete = True
            for c in p.criteria:
                if not self._done(c.id, stage):
                    complete = False
                r = self.effective(c.id, stage)
                if r:
                    counts[r.code] = counts.get(r.code, 0) + 1
                    if not r.satisfies and not r.neutral:
                        weak.append(c.id)
                else:
                    counts["pendente"] += 1
            satisfied = (not weak) if complete else None
            results.append(ProcessResult(p.code, p.name, counts, len(p.criteria), complete, satisfied,
                                         tuple(weak), p.kind))
        return results

    def verdict(self, stage: str | None = None) -> Verdict:
        """Sumário executivo do nível de aderência do projeto.

        * um item satisfaz quando caracterizado com T ou L (NA é neutro);
        * GPR e REQ são satisfeitos quando seus resultados esperados e os itens CP-Proj satisfazem;
        * havendo pendência, não há veredito de aderência;
        * processos exigidos pelo nível e fora do escopo (CAP) são sempre declarados.
        """
        stage = stage or self.stage
        model = self.model
        cap = model.capability
        procs = []
        for p in model.assessed:
            res = [c for c in p.criteria if c.kind == "resultado"]
            capitems = cap.criteria if cap else [c for c in p.criteria if c.kind == "capacidade"]

            def ok(c):
                r = self.effective(c.id, stage)
                return bool(r and r.satisfies and self._done(c.id, stage))

            items = res + capitems
            weak, neutral = [], 0
            for c in items:
                r = self.effective(c.id, stage)
                if r and r.neutral:
                    neutral += 1
                elif r and not r.satisfies:
                    weak.append(c.id)
            pending = sum(1 for c in items if not self._done(c.id, stage))
            sat = None if pending else not weak
            procs.append(ProcessVerdict(p.code, p.name, sum(map(ok, res)), len(res), sum(map(ok, capitems)),
                                        len(capitems), pending, tuple(weak), sat, neutral))

        weak_all = tuple(dict.fromkeys(w for pv in procs for w in pv.weak_points))
        pending_all = sum(1 for c in model.criteria if not self._done(c.id, stage))
        neutral_all = sum(1 for c in model.criteria if (r := self.effective(c.id, stage)) and r.neutral)
        oos = tuple(model.out_of_scope)
        assessed = " e ".join(pv.code for pv in procs)
        oos_txt = ", ".join(f"{n} ({c})" for c, n in oos)
        level = f"Nível {model.level}"

        if pending_all:
            status = "incompleta"
            headline = "Avaliação incompleta"
            explanation = (f"{pending_all} {'item ainda não foi avaliado' if pending_all == 1 else 'itens ainda não foram avaliados'}"
                           f" por completo. Não é possível concluir a aderência ao {level}.")
            if weak_all:
                explanation += f" Já há resultados caracterizados como P ou N: {', '.join(weak_all)}."
        elif weak_all:
            status = "nao_aderente"
            failed = [pv.code for pv in procs if pv.satisfied is False]
            one = len(failed) == 1
            headline = f"Não aderente ao {level}"
            explanation = (f"{'O processo' if one else 'Os processos'} {' e '.join(failed)} "
                           f"{'não é satisfeito' if one else 'não são satisfeitos'}: "
                           f"há resultados caracterizados como P ou N ({', '.join(weak_all)}).")
        else:
            status = "aderente"
            headline = f"Aderente ao {level} nos processos avaliados ({assessed})"
            cap_txt = f" e os itens de capacidade ({cap.code})" if cap else " e itens de capacidade"
            explanation = f"Todos os resultados esperados de {assessed}{cap_txt} foram caracterizados como T ou L."
        if stage == STAGE_FINAL and not pending_all:
            # regra do requerido leve: deixa explícito que o T não apagou o problema
            leve = [c.id for c in model.criteria if self.kept_as_weak(c.id)]
            if leve:
                one = len(leve) == 1
                explanation += (f" {', '.join(leve)} {'foi caracterizado' if one else 'foram caracterizados'} como T "
                                f"por {'ser requerido leve não corrigido' if one else 'serem requeridos leves não corrigidos'}"
                                f" (Guia de Avaliação, p. 58); o problema continua como ponto fraco.")
        if neutral_all and not pending_all:
            explanation += (" 1 resultado caracterizado como NA não entra na decisão." if neutral_all == 1 else
                            f" {neutral_all} resultados caracterizados como NA não entram na decisão.")
        if oos:
            explanation += (f" Para declarar o {level} atingido, o modelo também exige {oos_txt}, "
                            "que não é avaliado por esta ferramenta.")
        return Verdict(status, headline, explanation, tuple(procs), weak_all, pending_all, oos, stage)

    # ------------------------------------------------------------ relatório de ajustes
    def adjustments(self, include_empty: bool = False) -> list[AdjustmentRow]:
        rows = []
        porder = {p.code: i for i, p in enumerate(self.model.processes)}
        for f in self.findings:
            kind = self.finding_kind(f)
            if not kind or (not include_empty and not f.description.strip()):
                continue
            items = tuple(self.active_items(f))
            proc = self.model.process(f.process)
            rows.append(AdjustmentRow(f, proc, kind, items, self._refs(proc, items), self._finals(items)))
        rows.sort(key=lambda r: (porder.get(r.process.code, 99), self.model.order(r.items[0]), r.finding.id))
        return rows

    def _refs(self, proc: Process, items: tuple[str, ...]) -> str:
        refs = [self.model.criterion(c).ref for c in items]
        prefix = f"{proc.code} "
        if refs and all(r.startswith(prefix) for r in refs):
            return prefix + ", ".join(r[len(prefix):] for r in refs)
        return ", ".join(refs)

    def _finals(self, items: tuple[str, ...]) -> str:
        vals = [self.answer(c).final_rating for c in items]
        if all(v is None for v in vals):
            return ""
        if len(set(vals)) == 1:
            return vals[0]
        return "; ".join(f"{self.model.criterion(c).ref}: {v or '—'}" for c, v in zip(items, vals))


def load(model: NormModel, store, aid: int) -> Snapshot:
    """Lê do banco o estado atual de uma avaliação."""
    return Snapshot(model, store.answers(aid), store.findings(aid), store.get(aid).phase)
