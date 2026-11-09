"""Geração de relatórios (Módulo IV): CSV, PDF e o Relatório de Ajustes em XLSX."""
from __future__ import annotations

import csv
import html
import math
from datetime import datetime
from pathlib import Path

from . import rules
from .model import NormModel
from .storage import Assessment, clean_text

TONE = {"ok": "#248A3D", "warn": "#C93400", "bad": "#D70015", "pending": "#8A8A8E"}
CORRECTION_TEXT = {"Sim": "Corrigido", "Não": "Não corrigido", "Sem Correção": "Sem correção"}


def fmt_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def fmt_dt(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


def phase_label(a: Assessment) -> str:
    if a.completed:
        return "Concluída (avaliação inicial e final)"
    if a.in_final:
        return "Avaliação final em andamento (parcial)"
    if a.finished:
        return "Avaliação inicial concluída"
    return "Avaliação inicial em andamento (parcial)"


# ------------------------------------------------------------------ CSV
CSV_HEADER = [
    "avaliacao_id", "organizacao", "projeto", "avaliador", "modelo", "versao_modelo", "fase",
    "processo", "grupo", "item", "titulo", "caracterizacao", "caracterizacao_descricao",
    "situacao", "pendencias", "evidencias", "tipo_ajuste", "problema_ou_oportunidade", "sugestao_correcao",
    "impacto", "empresa_realizou_correcao", "correcao_realizada", "caracterizacao_final",
    "ponto_fraco_mantido",
]


def export_csv(path: Path | str, model: NormModel, a: Assessment, snap: rules.Snapshot) -> Path:
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(CSV_HEADER)
        for c in model.criteria:
            ans = snap.answer(c.id)
            ck = snap.check(c.id)
            r = model.rating(ans.rating)
            fs = [f for f in snap.item_findings(c.id) if snap.finding_kind(f)]
            kind = snap.item_kind(c.id)
            join = " || ".join
            w.writerow([
                a.id, a.organization, a.project, a.evaluator, model.id, model.version, a.phase,
                c.process, c.group, c.id, c.title, ans.rating or "", r.label if r else "",
                ck.state.value, ", ".join(ck.missing),
                " | ".join(e.content for e in ans.evidences),
                (model.labels.requerido if kind == "requerido" else model.labels.melhoria) if kind else "",
                join(f.description.strip() for f in fs),
                join(f.suggestion.strip() for f in fs if snap.finding_kind(f) == "requerido"),
                join(f.impact if snap.finding_kind(f) == "requerido" else "-" for f in fs),
                join(f.correction_status or "" for f in fs) if a.in_final else "",
                join(f.correction_text.strip() for f in fs) if a.in_final else "",
                (ans.final_rating or "") if snap.revisit(c.id) else (ans.rating or "") if a.in_final else "",
                # T obtido pela regra do requerido leve: o problema continua como ponto fraco
                "requerido leve" if a.in_final and snap.kept_as_weak(c.id) else "",
            ])
    return path


# ------------------------------------------------------------------ PDF
def _e(s: str) -> str:
    return html.escape(s or "").replace("\n", "<br/>")


def build_html(model: NormModel, a: Assessment, snap: rules.Snapshot) -> str:
    cons = snap.consolidate()
    prog = snap.progress()
    om = snap.omissions()
    lb = model.labels

    v = snap.verdict()
    by_code = {pr.code: pr for pr in cons}
    accent = {"aderente": TONE["ok"], "nao_aderente": TONE["bad"], "incompleta": "#8A8A8E"}[v.status]
    tint = {"aderente": "#E6F7EB", "nao_aderente": "#FFE8E6", "incompleta": "#F2F2F7"}[v.status]
    codes = [r.code for r in model.final_scale]

    def dist(pr: rules.ProcessResult) -> str:
        d = " · ".join(f"{k}: {pr.counts.get(k, 0)}" for k in codes
                       if k in [r.code for r in model.scale] or pr.counts.get(k, 0))
        if pr.counts["pendente"]:
            d += f" · sem caracterização: {pr.counts['pendente']}"
        return d

    def result(sat: bool | None, kind: str = "processo") -> tuple[str, str]:
        if sat is None:
            return "Incompleto", "#8A8A8E"
        if kind == "capacidade":
            return ("Em T ou L", TONE["ok"]) if sat else ("Com P ou N", TONE["bad"])
        return ("Satisfeito", TONE["ok"]) if sat else ("Não satisfeito", TONE["bad"])

    rows_summary = ""
    for pv in v.processes:
        text, color = result(pv.satisfied)
        rows_summary += (
            f"<tr class='item'><td><b>{pv.code}</b> — {_e(pv.name)}</td>"
            f"<td align='center'>{pv.results_ok} de {pv.results_total}</td>"
            f"<td align='center'>{pv.capability_ok} de {pv.capability_total}</td>"
            f"<td>{dist(by_code[pv.code])}</td><td style='color:{color}'><b>{text}</b></td></tr>")
    cap = model.capability
    if cap:
        pr = by_code[cap.code]
        text, color = result(pr.satisfied, "capacidade")
        ok = sum(pr.counts.get(r.code, 0) for r in model.final_scale if r.satisfies)
        rows_summary += (
            f"<tr class='item'><td><b>{cap.code}</b> — {_e(cap.name)}<br/><span class='muted'>comum a GPR e REQ"
            f"</span></td><td align='center' class='muted'>—</td><td align='center'>{ok} de {pr.total}</td>"
            f"<td>{dist(pr)}</td><td style='color:{color}'><b>{text}</b></td></tr>")
    for code, name in v.out_of_scope:
        rows_summary += (f"<tr class='item'><td><b>{code}</b> — {_e(name)}</td><td align='center' class='muted'>—</td>"
                         f"<td align='center' class='muted'>—</td><td class='muted'>Exigido no Nível {model.level}; "
                         f"fora do escopo desta ferramenta</td><td class='muted'><b>Não avaliado</b></td></tr>")

    sat = [r for r in model.scale if r.satisfies]
    unsat = [r for r in model.scale if not r.satisfies]
    legend = (" · ".join(f"<b>{r.code}</b> {_e(r.label.lower())}" for r in model.final_scale) +
              f"<br/>Satisfazem o resultado: {', '.join(r.code for r in sat)}. "
              f"Não satisfazem (pontos fracos): {', '.join(r.code for r in unsat)}. NA não entra na decisão.")

    initial_line = ""
    if snap.in_final:
        vi = snap.verdict(rules.STAGE_INITIAL)
        initial_line = f"<br/><span class='muted'>Na avaliação inicial: {_e(vi.headline)}.</span>"
    times = f"<b>{fmt_duration(a.elapsed_seconds)}</b>"
    if a.in_final or a.elapsed_final:
        times = f"inicial <b>{fmt_duration(a.elapsed_seconds)}</b> · final <b>{fmt_duration(a.elapsed_final)}</b>"
    noun = "Revisitas completas" if snap.in_final else "Itens completos"

    parts = [f"""
<html><head><style>
 body {{ font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 9pt; color: #1C1C1E; }}
 h1 {{ font-size: 18pt; color: #000000; margin: 0; }}
 h2 {{ font-size: 12pt; color: #000000; margin-top: 18px; margin-bottom: 4px; }}
 h3 {{ font-size: 10pt; color: #3C3C43; margin-top: 10px; margin-bottom: 2px; }}
 .muted {{ color: #8A8A8E; }}
 table {{ border-collapse: collapse; }}
 td, th {{ padding: 5px 6px; vertical-align: top; }}
 th {{ background: #F2F2F7; color: #3C3C43; text-align: left; font-weight: 600; }}
 .item td {{ border-bottom: 1px solid #E5E5EA; }}
 .fin td {{ background: #F2F7FF; border-bottom: 1px solid #E5E5EA; }}
</style></head><body>
<table width='100%' cellspacing='0'><tr>
 <td><h1>Relatório de Avaliação de Conformidade</h1>
 <span class='muted'>{_e(model.name)} · Nível {model.level} ({_e(model.level_name)}) · GPR, REQ e capacidade (CP-Proj)</span></td>
 <td align='right' class='muted'>MPS-Eval<br/>Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}</td>
</tr></table>
<hr/>
<table width='100%' cellspacing='0'>
 <tr><td width='18%' class='muted'>Organização</td><td width='32%'><b>{_e(a.organization)}</b></td>
     <td width='18%' class='muted'>Situação</td><td><b>{phase_label(a)}</b></td></tr>
 <tr><td class='muted'>Projeto</td><td><b>{_e(a.project)}</b></td>
     <td class='muted'>{noun}</td><td><b>{prog.done} de {prog.total}</b> ({prog.percent}%)</td></tr>
 <tr><td class='muted'>Avaliador(a)</td><td><b>{_e(a.evaluator)}</b></td>
     <td class='muted'>Tempo de avaliação</td><td>{times}</td></tr>
 <tr><td class='muted'>Início</td><td>{fmt_dt(a.created_at)}</td>
     <td class='muted'>Conclusão</td><td>inicial {fmt_dt(a.initial_finished_at)}{
        f" · final {fmt_dt(a.finished_at)}" if a.completed else ""}</td></tr>
</table>

<h2>Sumário executivo — nível de aderência{" (avaliação final)" if snap.in_final else ""}</h2>
<table width='100%' cellspacing='0' cellpadding='0' style='background:{tint}'>
 <tr><td width='5' style='background:{accent}'>&nbsp;</td>
     <td style='padding:10px 14px'>
       <span style='font-size:14pt; font-weight:700; color:{accent}'>{_e(v.headline)}</span><br/>
       <span style='color:#1C1C1E'>{_e(v.explanation)}</span>{initial_line}
     </td></tr>
</table>
<br/>
<table width='100%' cellspacing='0'>
 <tr><th>Processo</th><th align='center'>Resultados esperados<br/>em T ou L</th>
     <th align='center'>Capacidade CP-G<br/>em T ou L</th><th>Distribuição</th><th>Resultado</th></tr>
 {rows_summary}
</table>
<p class='muted'><b>Escala de caracterização</b> (MA-MPS, Tabela 7): {legend}<br/>
<b>Regras:</b> GPR e REQ são satisfeitos quando seus resultados esperados e os itens de capacidade CP-Proj (os
processos de projeto tratados como um único processo para a capacidade) estão em T ou L.
Exigências do Nível {model.level}: {_e(", ".join(f"{n} ({c})" for c, n in model.level_processes))},
com capacidade CP-G — {_e(model.level_source)}</p>
"""]
    if om:
        parts.append("<h2>Pendências</h2><table width='100%' cellspacing='0'><tr><th>Item</th><th>Falta</th></tr>")
        for o in om:
            parts.append(f"<tr class='item'><td><b>{o.criterion.code}</b> — {_e(o.criterion.title)}</td>"
                         f"<td>{', '.join(o.check.missing)}</td></tr>")
        parts.append("</table>")

    # relatório de ajustes
    adj = snap.adjustments(include_empty=True)
    parts.append("<h2>Relatório de ajustes para a avaliação final</h2>")
    if not adj:
        parts.append("<p class='muted'>Nenhum apontamento: todos os resultados foram caracterizados como T.</p>")
    else:
        parts.append("<table width='100%' cellspacing='0'><tr><th width='13%'>Resultado</th><th width='11%'>Tipo</th>"
                     "<th width='9%'>Impacto</th><th width='34%'>Problema ou oportunidade de melhoria</th>"
                     "<th>Sugestão para corrigir</th></tr>")
        for r in adj:
            f = r.finding
            color = TONE["warn"] if r.kind == "requerido" else "#0066D6"
            refs = r.refs if r.process.kind == "processo" else f"{r.process.code} {r.refs}"
            parts.append(
                f"<tr class='item'><td><b>{_e(refs)}</b><br/><span class='muted'>{_e(r.process.name)}</span></td>"
                f"<td style='color:{color}'><b>{lb.requerido if r.kind == 'requerido' else lb.melhoria}</b></td>"
                f"<td>{_e(f.impact) if r.kind == 'requerido' else '-'}</td>"
                f"<td>{_e(f.description.strip()) or '<span class=muted>—</span>'}</td>"
                f"<td>{_e(f.suggestion.strip()) if r.kind == 'requerido' else '<span class=muted>—</span>'}</td></tr>")
            if snap.in_final:
                st = CORRECTION_TEXT.get(f.correction_status or "", "Pendente")
                leve = [model.criterion(c).code for c in r.items if snap.kept_as_weak(c)]
                leve_txt = (f" · <span style='color:{TONE['warn']}'><b>requerido leve:</b> T sem correção "
                            f"({', '.join(leve)}); o problema continua como ponto fraco</span>") if leve else ""
                parts.append(f"<tr class='fin'><td colspan='2' class='muted'>Avaliação final</td>"
                             f"<td colspan='3'><b>{st}</b> · nova caracterização: <b>{_e(r.final) or '—'}</b>{leve_txt}"
                             f"{'<br/>' + _e(f.correction_text.strip()) if f.correction_text.strip() else ''}</td></tr>")
        parts.append("</table>")

    if snap.in_final:
        # pontos fracos do resultado final: L, P, N e os T obtidos pela regra do requerido leve (p. 58-59)
        weak = snap.remaining_weak_points()
        parts.append("<h2>Pontos fracos que permanecem</h2>")
        if not weak:
            parts.append("<p class='muted'>Nenhum: todos os resultados terminaram em T sem ressalvas.</p>")
        else:
            parts.append("<table width='100%' cellspacing='0'><tr><th width='13%'>Resultado</th>"
                         "<th width='14%'>Caract. final</th><th>Ponto fraco</th></tr>")
            for w in weak:
                c = model.criterion(w.cid)
                if w.leve:
                    rt = (f"<b style='color:{TONE['warn']}'>{snap.initial(w.cid).code} → T</b><br/>"
                          f"<span class='muted'>requerido leve não corrigido</span>")
                else:
                    rr = model.rating(w.rating)
                    rt = f"<b style='color:{TONE[rr.tone]}'>{rr.code}</b>"
                parts.append(f"<tr class='item'><td><b>{c.code}</b></td><td>{rt}</td>"
                             f"<td>{'<br/>'.join(_e(t) for t in w.texts) or '—'}</td></tr>")
            parts.append("</table>")
        parts.append("<p class='muted'>Toda caracterização diferente de T tem ponto fraco associado (Guia de Avaliação "
                     "2024, Parte I, p. 59). Um requerido classificado como Leve pode terminar em T sem correção, "
                     "e o problema continua listado aqui (p. 58).</p>")

    for p in model.processes:
        parts.append(f"<h2>{p.code} — {_e(p.name)}</h2>")
        for gname, items in p.groups:
            parts.append(f"<h3>{_e(gname)}</h3><table width='100%' cellspacing='0'>"
                         "<tr><th width='9%'>Item</th><th width='39%'>Resultado esperado</th>"
                         "<th width='13%'>Caract.</th><th>Evidências e apontamento</th></tr>")
            for c in items:
                ans = snap.answer(c.id)
                r = model.rating(ans.rating)
                rc = f"<b style='color:{TONE[r.tone]}'>{r.code}</b><br/><span class='muted'>{r.short}</span>" if r \
                    else "<span class='muted'>—</span>"
                if snap.in_final and snap.revisit(c.id):
                    fr = model.rating(ans.final_rating)
                    rc += (f"<br/><span class='muted'>final:</span> <b style='color:{TONE.get(fr.tone, '#8A8A8E')}'>"
                           f"{fr.code}</b>" if fr else "<br/><span class='muted'>final: —</span>")
                    if snap.kept_as_weak(c.id):
                        rc += f"<br/><span style='color:{TONE['warn']}'>requerido leve</span>"
                ev = "".join(f"• {_e(e.content)}<br/>" for e in ans.evidences) or \
                     "<span style='color:#D70015'>Sem evidência registrada</span><br/>"
                for f in snap.item_findings(c.id):
                    kind = snap.finding_kind(f)
                    if not kind:
                        continue
                    if kind == "requerido":
                        ev += (f"<span class='muted'>{lb.description_req}:</span> {_e(f.description.strip()) or '—'}<br/>"
                               f"<span class='muted'>{lb.suggestion}:</span> {_e(f.suggestion.strip()) or '—'}<br/>")
                    else:
                        ev += f"<span class='muted'>{lb.description_mel}:</span> {_e(f.description.strip()) or '—'}<br/>"
                    if snap.in_final:
                        ev += (f"<span class='muted'>Correção:</span> {CORRECTION_TEXT.get(f.correction_status or '', '—')}"
                               f"{' — ' + _e(f.correction_text.strip()) if f.correction_text.strip() else ''}<br/>")
                parts.append(f"<tr class='item'><td><b>{c.code}</b></td><td><b>{_e(c.title)}</b><br/>"
                             f"<span class='muted'>{_e(c.text)}</span></td><td>{rc}</td><td>{ev}</td></tr>")
            parts.append("</table>")

    parts.append(f"<p class='muted'><br/>Modelo de critérios: {model.id} v{model.version} "
                 f"(checksum {a.model_checksum}). Fonte: {_e(model.source)}</p></body></html>")
    return "".join(parts)


def export_pdf(path: Path | str, model: NormModel, a: Assessment, snap: rules.Snapshot) -> Path:
    """Requer uma QGuiApplication/QApplication ativa (renderização via Qt)."""
    from PyQt6.QtCore import QMarginsF, QSizeF
    from PyQt6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

    path = Path(path)
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(14, 14, 14, 16), QPageLayout.Unit.Millimeter)
    writer.setResolution(110)
    writer.setTitle(f"MPS-Eval — {a.organization} / {a.project}")
    writer.setCreator("MPS-Eval")

    doc = QTextDocument()
    doc.setDocumentMargin(0)
    doc.setHtml(build_html(model, a, snap))
    layout = writer.pageLayout()
    rect = layout.paintRectPixels(writer.resolution())
    doc.setPageSize(QSizeF(rect.width(), rect.height()))
    doc.print(writer)
    return path


# ------------------------------------------------------------------ XLSX (Relatório de Ajustes)
XLSX_SHEET = "RELATÓRIO_DE_AJUSTES"
XLSX_TITLE = "RELATÓRIO DE AJUSTES PARA A AVALIAÇÃO FINAL – MPS.Br"
XLSX_HEADER = ["PROCESSO", "REQUERIDO/\n MELHORIA", "RESULTADO\n ESPERADO", "IMPACTO NA AVALIAÇÃO",
               "PROBLEMA ou OPORTUNIDADE DE MELHORIA", "SUGESTÃO PARA CORRIGIR (APENAS SE FOR PROBLEMA)",
               "EMPRESA REALIZOU CORREÇÃO?", "T, L, P, N", "CORREÇÃO REALIZADA"]
XLSX_WIDTHS = {"A": 16.6, "B": 14.4, "C": 14.3, "D": 14.6, "E": 29.9, "F": 32.6, "G": 16.1, "H": 13.0, "I": 26.4}
# alinhamento (horizontal, vertical) por coluna, como no modelo
XLSX_ALIGN = {"A": (None, "center"), "B": ("center", "center"), "C": ("center", "center"), "D": ("center", "top"),
              "E": ("left", "center"), "F": ("left", "center"), "G": ("center", "top"), "H": ("center", "top"),
              "I": ("center", "top")}
XLSX_MIN_ROWS = 194      # linhas com listas de validação, como no modelo


def _row_height(values: list[str], widths: list[float]) -> float:
    lines = 1
    for text, w in zip(values, widths):
        cap = max(4.0, w * 1.05)
        n = sum(max(1, math.ceil(len(par) / cap)) for par in str(text or "").split("\n"))
        lines = max(lines, n)
    return max(30.0, round(lines * 12.75 + 6, 2))


def xlsx_rows(model: NormModel, snap: rules.Snapshot) -> list[list[str]]:
    lb = model.labels
    out = []
    for r in snap.adjustments():
        f = r.finding
        final = snap.in_final
        out.append([
            r.process.sheet_name,
            lb.requerido if r.kind == "requerido" else lb.melhoria,
            r.refs,
            (f.impact or "-") if r.kind == "requerido" else "-",     # impacto só se aplica a REQUERIDO
            f.description.strip(),
            f.suggestion.strip() if r.kind == "requerido" else "",
            (f.correction_status or "") if final else "",
            r.final if final else "",
            f.correction_text.strip() if final else "",
        ])
    return out


def export_xlsx(path: Path | str, model: NormModel, a: Assessment, snap: rules.Snapshot) -> Path:
    """Relatório de Ajustes para a Avaliação Final no formato da planilha de referência."""
    from openpyxl import Workbook
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.workbook.defined_name import DefinedName
    from openpyxl.worksheet.datavalidation import DataValidation

    path = Path(path)
    lb = model.labels
    wb = Workbook()
    ws = wb.active
    ws.title = XLSX_SHEET
    arial = Font(name="Arial", size=10)
    arial_b = Font(name="Arial", size=10, bold=True)
    thin = Side(style="thin", color="FF000000")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    gray_title = PatternFill("solid", fgColor="FFCCCCCC")
    gray_head = PatternFill("solid", fgColor="FFEFEFEF")
    green = PatternFill("solid", fgColor="FFB7E1CD")

    for col, w in XLSX_WIDTHS.items():
        ws.column_dimensions[col].width = w

    title = clean_text(f"{XLSX_TITLE} – {a.organization} / {a.project}")
    if not a.finished:
        title += " (PARCIAL)"
    ws["A1"] = title
    ws.merge_cells("A1:I1")
    ws["A1"].font = Font(name="Arial", size=12, bold=True)
    ws["A1"].fill = gray_title
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 20

    for i, text in enumerate(XLSX_HEADER):
        c = ws.cell(row=2, column=i + 1, value=text)
        c.font = arial_b
        c.fill = gray_head
        c.border = box
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[2].height = 38.25

    rows = xlsx_rows(model, snap)
    widths = [XLSX_WIDTHS[c] for c in "ABCDEFGHI"]
    for ri, values in enumerate(rows, start=3):
        for ci, (col, v) in enumerate(zip("ABCDEFGHI", values), start=1):
            # clean_text: dados gravados antes da limpeza na entrada podem ter caracteres que o Excel recusa
            c = ws.cell(row=ri, column=ci, value=clean_text(v) if v != "" else None)
            c.font = arial
            h, vert = XLSX_ALIGN[col]
            c.alignment = Alignment(horizontal=h, vertical=vert, wrap_text=True)
            if col == "A":
                c.fill = green
        ws.row_dimensions[ri].height = _row_height(values, widths)

    last = max(XLSX_MIN_ROWS, 2 + len(rows))
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:I{last}"
    ws.conditional_formatting.add(f"A3:A{last}", FormulaRule(formula=['LEN(TRIM(A3))>0'], fill=green))

    # ---- PARAMETROS (listas das validações)
    p = wb.create_sheet("PARAMETROS")
    for col, w in {"A": 6.7, "B": 47.6, "C": 2.9, "D": 20.4}.items():
        p.column_dimensions[col].width = w

    def head(cell, text, fill=gray_title):
        p[cell] = text
        p[cell].font = arial_b
        p[cell].fill = fill
        p[cell].border = box
        p[cell].alignment = Alignment(horizontal="center")

    def val(cell, text):
        p[cell] = text
        p[cell].font = arial
        p[cell].border = box

    head("A1", f"Processos avaliados — Nível {model.level}")
    p.merge_cells("A1:B1")
    head("A2", "Sigla", gray_head)
    head("B2", "Processos", gray_head)
    for i, proc in enumerate(model.processes, start=3):
        val(f"A{i}", proc.code)
        val(f"B{i}", proc.sheet_name)
    proc_end = 2 + len(model.processes)

    lists = [("Impacto Avaliação", "ImpactoAvaliacao", list(lb.impact)),
             ("Correção Realizada", "CorrecaoRealizada", list(lb.correction)),
             ("Tipo de Ajuste", "TipoAjuste", [lb.melhoria, lb.requerido]),
             ("Caracterização", "Caracterizacao", [r.code for r in model.final_scale]),
             ("Níveis MPS", "NiveisMPS", [model.level])]
    row = 1
    for header, name, values in lists:
        head(f"D{row}", header)
        for j, v in enumerate(values, start=1):
            val(f"D{row + j}", v)
        ref = f"PARAMETROS!$D${row + 1}:$D${row + len(values)}"
        wb.defined_names[name] = DefinedName(name, attr_text=ref)
        row += len(values) + 2
    wb.defined_names["ProcessosModeloAvaliado"] = DefinedName(
        "ProcessosModeloAvaliado", attr_text=f"PARAMETROS!$B$3:$B${proc_end}")

    for formula, rng, err in (("ProcessosModeloAvaliado", f"A3:A{last}", True), ("TipoAjuste", f"B3:B{last}", False),
                              ("ImpactoAvaliacao", f"D3:D{last}", False), ("CorrecaoRealizada", f"G3:G{last}", False),
                              ("Caracterizacao", f"H3:H{last}", False)):
        dv = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=err)
        dv.add(rng)
        ws.add_data_validation(dv)

    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "2:2"
    ws.print_options.gridLines = True             # como no modelo: grade impressa nas células
    wb.properties.title = "Relatório de Ajustes para a Avaliação Final"
    wb.properties.creator = "MPS-Eval"
    wb.properties.subject = clean_text(f"{a.organization} / {a.project}")
    wb.save(path)
    return path
