"""Revisão: omissões, veredito, relatório de ajustes, conclusão das fases e exportação (Módulo IV)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..core import rules
from ..core.model import NormModel
from ..core.storage import Assessment
from . import theme as T
from .findings import KIND_STYLE
from .widgets import (Card, DistributionBar, Row, SectionHeader, button, chip, clear_layout, grouped_rows, label,
                      section_footer)


class _Elided(QLabel):
    def __init__(self, text: str, color: str = T.LABEL_2):
        super().__init__()
        self._full = " ".join(text.split())
        self.setFont(T.font(T.BODY))
        self.setStyleSheet(f"color: {color}; background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setToolTip(text)

    def resizeEvent(self, e):
        self.setText(QFontMetrics(self.font()).elidedText(self._full, Qt.TextElideMode.ElideRight, self.width()))
        super().resizeEvent(e)


class ReviewPage(QWidget):
    jumpTo = pyqtSignal(str)
    finalizeRequested = pyqtSignal()
    reopenRequested = pyqtSignal()
    startFinalRequested = pyqtSignal()
    backToInitialRequested = pyqtSignal()
    exportRequested = pyqtSignal(str)   # "pdf" | "csv" | "xlsx"

    def __init__(self, model: NormModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(40, 28, 40, 40)
        self.lay.setSpacing(0)

    def _clear(self):
        clear_layout(self.lay)

    def render(self, a: Assessment, snap: rules.Snapshot):
        self._clear()
        oms = snap.omissions()
        L = self.lay
        final = a.in_final

        title = label("Revisão da avaliação final" if final else "Revisão da avaliação inicial",
                      T.LARGE_TITLE + 4, QFont.Weight.Bold, display=True)
        title.setContentsMargins(4, 0, 0, 0)
        L.addWidget(title)
        L.addSpacing(4)
        n_adj = len(snap.revisit_ids())
        if a.completed:
            sub = "Avaliação concluída nas duas fases. Os registros estão bloqueados para edição."
        elif a.finished:
            sub = ("Avaliação inicial concluída. Envie o Relatório de Ajustes à empresa e, depois das correções, "
                   "inicie a avaliação final." if n_adj else
                   "Avaliação inicial concluída. Nenhum resultado precisa de ajuste.")
        elif oms:
            n = len(oms)
            sub = (f"{n} {'item ainda impede' if n == 1 else 'itens ainda impedem'} a conclusão. "
                   "Toque em um item para ir direto a ele.")
        elif final:
            sub = "Todas as revisitas estão completas. A avaliação final pode ser concluída."
        else:
            sub = "Todos os itens estão completos. A avaliação inicial pode ser concluída."
        s = label(sub, T.BODY, color=T.LABEL_2, wrap=True)
        s.setContentsMargins(4, 0, 0, 0)
        L.addWidget(s)
        L.addSpacing(24)

        # sumário executivo (mesmo veredito do relatório PDF)
        L.addWidget(SectionHeader("Sumário executivo", "avaliação final" if final else "avaliação inicial"))
        L.addSpacing(6)
        L.addWidget(self._verdict_card(snap.verdict(), snap.verdict(rules.STAGE_INITIAL) if final else None))
        L.addSpacing(24)

        # resultado por processo
        L.addWidget(SectionHeader("Resultado por processo"))
        L.addSpacing(6)
        card = Card()
        rows = [self._process_row(pr) for pr in snap.consolidate()]
        for code, name in self.model.out_of_scope:
            rows.append(self._out_of_scope_row(code, name))
        grouped_rows(card, rows)
        L.addWidget(card)
        L.addSpacing(6)
        cap = self.model.capability
        rule = (f"GPR e REQ são satisfeitos quando seus resultados esperados e os itens de capacidade ({cap.code}, "
                "comuns aos dois) estão em T ou L." if cap else
                "O processo é satisfeito quando todos os seus itens estão em T ou L.")
        if final:
            rule += " Na avaliação final vale a nova caracterização dos resultados revisitados; NA não entra na decisão."
        L.addWidget(section_footer(rule + " " + self.model.scope_note))
        L.addSpacing(24)

        # relatório de ajustes
        adj = snap.adjustments(include_empty=True)
        req = sum(1 for r in adj if r.kind == "requerido")
        mel = len(adj) - req
        L.addWidget(SectionHeader("Relatório de ajustes",
                                  f"{req} {'requerido' if req == 1 else 'requeridos'} · {mel} "
                                  f"{'melhoria' if mel == 1 else 'melhorias'}" if adj else ""))
        L.addSpacing(6)
        acard = Card()
        if adj:
            grouped_rows(acard, [self._adjustment_row(r, final, snap) for r in adj], inset=16)
        else:
            empty = label("Nenhum apontamento: todos os resultados estão em T.", T.BODY, color=T.SECONDARY)
            empty.setContentsMargins(16, 12, 16, 12)
            acard.lay.addWidget(empty)
        L.addWidget(acard)
        L.addSpacing(6)
        L.addWidget(section_footer("Cada linha é um apontamento. REQUERIDO (P ou N) deve ser corrigido pela empresa; "
                                   "MELHORIA (L) fica a critério dela. O XLSX segue o formato do Relatório de Ajustes "
                                   "para a Avaliação Final."))
        L.addSpacing(24)

        # pontos fracos que permanecem (avaliação final): L, P, N e os T obtidos pela regra do requerido leve
        if final:
            weak = snap.remaining_weak_points()
            n_leve = sum(1 for w in weak if w.leve)
            L.addWidget(SectionHeader("Pontos fracos que permanecem",
                                      f"{len(weak)}" + (f" · {n_leve} por requerido leve" if n_leve else "")))
            L.addSpacing(6)
            wcard = Card()
            if weak:
                grouped_rows(wcard, [self._weak_row(w, snap) for w in weak], inset=16)
            else:
                empty = label("Nenhum: todos os resultados terminaram em T sem ressalvas.", T.BODY, color=T.SECONDARY)
                empty.setContentsMargins(16, 12, 16, 12)
                wcard.lay.addWidget(empty)
            L.addWidget(wcard)
            L.addSpacing(6)
            L.addWidget(section_footer("Toda caracterização diferente de T tem ponto fraco (Guia de Avaliação 2024, "
                                       "p. 59). Um requerido leve não corrigido pode terminar em T, mas o problema "
                                       "continua nesta lista (p. 58)."))
            L.addSpacing(24)

        # ações
        actions = QHBoxLayout()
        actions.setSpacing(10)
        if a.completed:
            b = button("Reabrir avaliação final", "", "unlock")
            b.clicked.connect(self.reopenRequested.emit)
            actions.addWidget(b)
        elif a.finished:
            if n_adj:
                st = button("Iniciar avaliação final", "primary", "wrench")
                st.setMinimumHeight(38)
                st.setToolTip("Revisitar os resultados com apontamento e registrar as correções da empresa")
                st.clicked.connect(self.startFinalRequested.emit)
                actions.addWidget(st)
            b = button("Reabrir avaliação inicial", "", "unlock")
            b.clicked.connect(self.reopenRequested.emit)
            actions.addWidget(b)
        else:
            fin = button("Concluir avaliação final" if final else "Concluir avaliação inicial", "primary", "check")
            fin.setMinimumHeight(38)
            fin.setEnabled(not oms)
            fin.setToolTip("Disponível quando não houver pendências" if oms else "Bloqueia a edição e registra a conclusão")
            fin.clicked.connect(self.finalizeRequested.emit)
            actions.addWidget(fin)
            if final:
                back = button("Voltar à avaliação inicial", "ghost")
                back.setToolTip("Corrigir a avaliação inicial; o que já foi registrado na avaliação final é mantido")
                back.clicked.connect(self.backToInitialRequested.emit)
                actions.addWidget(back)
        actions.addStretch(1)
        L.addLayout(actions)

        # exportação
        L.addSpacing(24)
        L.addWidget(SectionHeader("Exportar", "parcial enquanto houver pendências" if (oms and not a.finished) else ""))
        L.addSpacing(6)
        ecard = Card()
        erows = []
        for kind, title, desc in (
                ("xlsx", "Relatório de Ajustes (XLSX)", "No formato da planilha de ajustes para a avaliação final"),
                ("pdf", "Relatório completo (PDF)", "Sumário executivo, ajustes e todos os itens com evidências"),
                ("csv", "Dados brutos (CSV)", "Uma linha por item, para análise em planilha")):
            row = Row()
            ic = QLabel()
            ic.setPixmap(T.icon("share", T.BLUE, 18).pixmap(18, 18))
            ic.setStyleSheet("background: transparent;")
            row.lay.addWidget(ic)
            row.lay.addWidget(label(title, T.BODY, QFont.Weight.Medium))
            row.lay.addWidget(label(desc, T.FOOTNOTE, color=T.SECONDARY), 1)
            row.finish()
            row.clicked.connect(lambda k=kind: self.exportRequested.emit(k))
            erows.append(row)
        grouped_rows(ecard, erows, inset=46)
        L.addWidget(ecard)

        if oms:
            L.addSpacing(26)
            L.addWidget(SectionHeader("Pendências", str(len(oms))))
            L.addSpacing(6)
            pend = Card()
            rows = []
            for om in oms:
                row = Row()
                code = label(om.criterion.code, T.BODY, QFont.Weight.DemiBold)
                code.setFixedWidth(70)
                row.lay.addWidget(code)
                row.lay.addWidget(label(om.criterion.title, T.BODY, color=T.LABEL_2), 1)
                partial = om.check.state is rules.State.INCOMPLETE
                row.lay.addWidget(label("Falta " + ", ".join(om.check.missing), T.FOOTNOTE,
                                        color=T.TONE_TEXT["warn"] if partial else T.SECONDARY))
                row.finish()
                row.clicked.connect(lambda cid=om.criterion.id: self.jumpTo.emit(cid))
                rows.append(row)
            grouped_rows(pend, rows, inset=98)
            L.addWidget(pend)
        L.addStretch(1)

    # ------------------------------------------------------------ blocos
    def _verdict_card(self, v: rules.Verdict, initial: rules.Verdict | None) -> QWidget:
        tone = {"aderente": "ok", "nao_aderente": "bad", "incompleta": None}[v.status]
        icon = {"aderente": "check-circle", "nao_aderente": "x-circle", "incompleta": "alert-circle"}[v.status]
        fill = T.TONE[tone] if tone else T.GRAY
        card = Card(padding=(16, 14, 16, 14))
        row = QHBoxLayout()
        row.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(T.icon(icon, fill, 28).pixmap(28, 28))
        ic.setStyleSheet("background: transparent;")
        row.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        txt = QVBoxLayout()
        txt.setSpacing(4)
        txt.addWidget(label(v.headline, T.TITLE_3 + 1, QFont.Weight.Bold,
                            T.TONE_TEXT[tone] if tone else T.LABEL, wrap=True, display=True))
        txt.addWidget(label(v.explanation, T.CALLOUT, color=T.LABEL_2, wrap=True))
        if initial is not None:
            txt.addSpacing(4)
            txt.addWidget(label(f"Na avaliação inicial: {initial.headline}.", T.FOOTNOTE, color=T.SECONDARY, wrap=True))
        row.addLayout(txt, 1)
        card.lay.addLayout(row)
        return card

    def _weak_row(self, w: rules.WeakPoint, snap: rules.Snapshot) -> QWidget:
        row = Row()
        c = self.model.criterion(w.cid)
        code = label(c.code, T.BODY, QFont.Weight.DemiBold)
        code.setFixedWidth(78)
        row.lay.addWidget(code)
        r = self.model.rating(w.rating)
        if w.leve:
            # nota que subiu de P/N para T pela regra do requerido leve: mostra a origem para não parecer um T comum
            rt = label(f"{snap.initial(w.cid).code} → T", T.FOOTNOTE, QFont.Weight.Bold, T.TONE_TEXT["warn"])
        else:
            rt = label(w.rating, T.FOOTNOTE, QFont.Weight.Bold, T.TONE_TEXT[r.tone])
        rt.setFixedWidth(52)
        row.lay.addWidget(rt)
        text = " · ".join(w.texts) or "(sem texto)"
        row.lay.addWidget(_Elided(text), 1)
        if w.leve:
            ch = chip("Requerido leve", T.TONE_TEXT["warn"], T.TONE_SOFT["warn"])
            ch.setToolTip("T por requerido leve não corrigido (Guia de Avaliação 2024, Parte I, p. 58)")
            row.lay.addWidget(ch)
        row.finish()
        row.clicked.connect(lambda cid=w.cid: self.jumpTo.emit(cid))
        return row

    def _adjustment_row(self, r: rules.AdjustmentRow, final: bool, snap: rules.Snapshot) -> QWidget:
        row = Row()
        fg, bg = KIND_STYLE[r.kind]
        c = chip(self.model.labels.requerido if r.kind == "requerido" else self.model.labels.melhoria, fg, bg)
        c.setFixedWidth(96)
        row.lay.addWidget(c)
        refs = r.refs if r.process.kind == "processo" else f"{r.process.code} {r.refs}"
        code = label(refs, T.BODY, QFont.Weight.DemiBold)
        code.setFixedWidth(104)
        row.lay.addWidget(code)
        desc = r.finding.description.strip() or "(sem texto)"
        row.lay.addWidget(_Elided(desc, T.LABEL_2 if r.finding.description.strip() else T.TERTIARY), 1)
        if final:
            st = r.finding.correction_status
            tone = {"Sim": "ok", "Não": "bad"}.get(st or "")
            text = {"Sim": "Corrigido", "Não": "Não corrigido", "Sem Correção": "Sem correção"}.get(st or "", "Pendente")
            ch = chip(text, T.TONE_TEXT[tone] if tone else T.LABEL_2, T.TONE_SOFT[tone] if tone else T.FILL_CARD)
            ch.setFixedWidth(108)
            row.lay.addWidget(ch)
            leve = [c for c in r.items if snap.kept_as_weak(c)]
            fin = label((r.final or "—") + ("  · leve" if leve else ""), T.FOOTNOTE, QFont.Weight.Bold,
                        T.TONE_TEXT["warn"] if leve else T.LABEL_2)
            if leve:
                fin.setToolTip("T por requerido leve não corrigido: o problema continua como ponto fraco")
            fin.setFixedWidth(118)
            fin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            fin.setToolTip("Nova caracterização")
            row.lay.addWidget(fin)
        row.finish()
        row.clicked.connect(lambda cid=r.items[0]: self.jumpTo.emit(cid))
        return row

    def _out_of_scope_row(self, code: str, name: str) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        lay.addWidget(label(code, T.TITLE_3 + 1, QFont.Weight.Bold, T.SECONDARY, display=True))
        lay.addWidget(label(name, T.BODY, color=T.SECONDARY))
        lay.addStretch(1)
        lay.addWidget(label(f"Exigido no Nível {self.model.level}, fora do escopo desta ferramenta", T.FOOTNOTE,
                            color=T.SECONDARY))
        lay.addWidget(chip("Não avaliado", T.SECONDARY, T.FILL_CARD))
        return w

    def _process_row(self, pr: rules.ProcessResult) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(label(pr.code, T.TITLE_3 + 1, QFont.Weight.Bold, display=True))
        top.addWidget(label(pr.name, T.BODY, color=T.LABEL_2))
        top.addStretch(1)
        if pr.satisfied is None:
            top.addWidget(chip("Incompleto", T.LABEL_2, T.FILL_CARD))
        elif pr.satisfied:
            top.addWidget(chip("Satisfeito" if pr.kind == "processo" else "Em T ou L",
                               T.TONE_TEXT["ok"], T.TONE_SOFT["ok"]))
        else:
            top.addWidget(chip("Não satisfeito" if pr.kind == "processo" else "Com P ou N",
                               T.TONE_TEXT["bad"], T.TONE_SOFT["bad"]))
        lay.addLayout(top)

        scale = [r for r in self.model.final_scale if not r.neutral or pr.counts.get(r.code, 0)]
        bar = DistributionBar()
        segs = [(pr.counts.get(r.code, 0), T.TONE.get(r.tone, T.GRAY4)) for r in scale]
        segs.append((pr.counts["pendente"], T.GRAY5))
        bar.set_segments(segs)
        lay.addWidget(bar)

        legend = QHBoxLayout()
        legend.setSpacing(16)
        for r in scale:
            legend.addWidget(self._legend(r.code, pr.counts.get(r.code, 0), T.TONE.get(r.tone, T.GRAY4)))
        legend.addWidget(self._legend("Sem caracterização", pr.counts["pendente"], T.GRAY4))
        legend.addStretch(1)
        ok = sum(pr.counts.get(r.code, 0) for r in self.model.final_scale if r.satisfies)
        legend.addWidget(label(f"{ok} de {pr.total} em T ou L", T.FOOTNOTE, QFont.Weight.Medium, T.LABEL_2))
        lay.addLayout(legend)
        if pr.weak_points:
            lay.addWidget(label("Pontos fracos (P ou N): " + ", ".join(pr.weak_points), T.FOOTNOTE,
                                color=T.TONE_TEXT["bad"], wrap=True))
        return w

    @staticmethod
    def _legend(text: str, n: int, dot: str) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        d = QLabel()
        d.setFixedSize(8, 8)
        d.setStyleSheet(f"background: {dot}; border-radius: 4px;")
        lay.addWidget(d, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(label(f"{text}  {n}", T.FOOTNOTE, color=T.LABEL_2))
        return w
