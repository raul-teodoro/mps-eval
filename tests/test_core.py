import csv
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mpseval.core import report, rules  # noqa: E402
from mpseval.core.model import load_model  # noqa: E402
from mpseval.core.storage import Store  # noqa: E402


@pytest.fixture()
def model():
    return load_model()


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "t.sqlite3")
    yield s
    s.close()


def snap(model, store, aid):
    return rules.load(model, store, aid)


def preencher(store, model, aid, rating="T"):
    """Caracteriza todos os itens, com evidência e o apontamento que a nota exige."""
    for c in model.criteria:
        store.set_rating(aid, c.id, rating)
        store.add_evidence(aid, c.id, "texto", f"Evidência de {c.id}")
        if rating != "T":
            f = store.create_finding(aid, c.process, [c.id], f"Ponto fraco de {c.id}")
            store.update_finding(aid, f.id, suggestion="Corrigir")


def test_cobertura_normativa_nivel_g(model):
    gpr = [c.id for c in model.process("GPR").criteria]
    req = [c.id for c in model.process("REQ").criteria]
    cap = model.capability
    assert gpr == [f"GPR {i}" for i in range(1, 20)]          # GPR 1–19 (Guia 2024, nível G)
    assert req == [f"REQ {i}" for i in range(1, 6)]           # REQ 1–5
    assert cap.code == "CP-Proj" and [c.ref for c in cap.criteria] == ["i", "ii", "iii"]
    assert len(model.criteria) == 19 + 5 + 3                  # CP-G uma vez para os processos de projeto
    assert [r.code for r in model.final_scale] == ["T", "L", "P", "N", "NA"]
    assert [r.finding for r in model.scale] == [None, "melhoria", "requerido", "requerido"]


def test_fail_safe_exige_evidencia(model, store):
    a = store.create("Org", "Proj", "Ana", model)
    store.set_rating(a.id, "GPR 1", "T")
    ck = snap(model, store, a.id).check("GPR 1")
    assert ck.state is rules.State.INCOMPLETE and ck.missing == ("evidência",)
    store.add_evidence(a.id, "GPR 1", "texto", "Documento de escopo v2")
    assert snap(model, store, a.id).check("GPR 1").done


def test_campos_por_nota(model, store):
    a = store.create("Org", "Proj", "Ana", model)
    for cid in ("REQ 4", "GPR 2"):
        store.add_evidence(a.id, cid, "texto", "Matriz parcial")
    store.set_rating(a.id, "REQ 4", "P")
    store.set_rating(a.id, "GPR 2", "L")
    s = snap(model, store, a.id)
    assert s.check("REQ 4").missing == ("problema", "sugestão de correção")
    assert s.check("GPR 2").missing == ("oportunidade de melhoria",)
    f = store.create_finding(a.id, "REQ", ["REQ 4"], "Rastreabilidade só no sentido requisito→código")
    assert snap(model, store, a.id).check("REQ 4").missing == ("sugestão de correção",)
    store.update_finding(a.id, f.id, suggestion="Rastrear também código→requisito")
    store.create_finding(a.id, "GPR", ["GPR 2"], "Estimativas sem registro de método")
    s = snap(model, store, a.id)
    assert s.check("REQ 4").done and s.check("GPR 2").done
    # T não exige apontamento
    store.set_rating(a.id, "GPR 2", "T")
    assert snap(model, store, a.id).check("GPR 2").done


def test_apontamento_compartilhado(model, store):
    a = store.create("Org", "Proj", "Ana", model)
    for cid, r in (("REQ 2", "P"), ("REQ 4", "N")):
        store.set_rating(a.id, cid, r)
        store.add_evidence(a.id, cid, "texto", "Documento de requisitos")
    f = store.create_finding(a.id, "REQ", ["REQ 2"], "Sem priorização nem rastreabilidade")
    store.update_finding(a.id, f.id, suggestion="Mapear refinamento e rastreio", impact="LEVE")
    store.set_finding_items(a.id, f.id, ["REQ 2", "REQ 4"])
    s = snap(model, store, a.id)
    assert s.check("REQ 2").done and s.check("REQ 4").done
    [row] = s.adjustments()
    assert (row.refs, row.kind, row.process.sheet_name) == ("REQ 2, 4", "requerido", "Engenharia de Requisitos")
    # desvincular o último resultado exclui o apontamento
    store.set_finding_items(a.id, f.id, [])
    assert store.findings(a.id) == []


def test_avaliacao_final(model, store):
    a = store.create("Org", "Proj", "Ana", model)
    preencher(store, model, a.id, "T")
    store.set_rating(a.id, "GPR 11", "P")
    f = store.create_finding(a.id, "GPR", ["GPR 11"], "Viabilidade só de RH")
    store.update_finding(a.id, f.id, suggestion="Incluir análise de viabilidade completa")
    store.set_rating(a.id, "CP-Proj (iii)", "L")
    g = store.create_finding(a.id, "CP-Proj", ["CP-Proj (iii)"], "Registro de treinamentos incompleto")
    s = snap(model, store, a.id)
    assert s.can_finalize() and s.verdict().status == "nao_aderente"
    assert [p.satisfied for p in s.verdict().processes] == [False, True]

    store.set_status(a.id, True)
    store.start_final(a.id)
    s = snap(model, store, a.id)
    assert s.in_final and s.scope() == ["GPR 11", "CP-Proj (iii)"]
    assert s.check("GPR 11").state is rules.State.PENDING
    assert s.check("GPR 1").done                                  # T: não é revisitado
    store.update_finding(a.id, f.id, correction_status="Sim")
    assert snap(model, store, a.id).check("GPR 11").missing == ("correção realizada", "nova caracterização")
    store.update_finding(a.id, f.id, correction_text="Planos revisados")
    store.set_final_rating(a.id, "GPR 11", "T")
    store.update_finding(a.id, g.id, correction_status="Sem Correção")
    store.set_final_rating(a.id, "CP-Proj (iii)", "L")
    s = snap(model, store, a.id)
    assert s.can_finalize()
    assert s.verdict().status == "aderente" and s.verdict(rules.STAGE_INITIAL).status == "nao_aderente"
    rows = {r.refs: r for r in s.adjustments()}
    assert rows["GPR 11"].final == "T" and rows["iii"].process.sheet_name.endswith("(CP-Proj)")
    # NA é neutro
    store.set_final_rating(a.id, "GPR 11", "NA")
    v = snap(model, store, a.id).verdict()
    assert v.status == "aderente" and "NA" in v.explanation
    # tempo por fase
    store.add_elapsed(a.id, 30)
    a2 = store.get(a.id)
    assert (a2.elapsed_seconds, a2.elapsed_final, a2.total_elapsed) == (0, 30, 30)


def test_capacidade_reprova_os_dois_processos(model, store):
    a = store.create("Org", "Proj", "Ana", model)
    preencher(store, model, a.id, "T")
    store.set_rating(a.id, "CP-Proj (ii)", "N")
    store.create_finding(a.id, "CP-Proj", ["CP-Proj (ii)"], "Sem monitoramento")
    f = store.findings(a.id)[0]
    store.update_finding(a.id, f.id, suggestion="Monitorar")
    v = snap(model, store, a.id).verdict()
    assert v.status == "nao_aderente" and [p.satisfied for p in v.processes] == [False, False]
    assert v.weak_points == ("CP-Proj (ii)",)


def test_veredito(model, store):
    a = store.create("Org", "Proj", "Ana", model)
    v = snap(model, store, a.id).verdict()
    assert v.status == "incompleta" and v.pending == len(model.criteria)
    assert v.out_of_scope == (("CAP", "Capacitação"),) and "CAP" in v.explanation

    preencher(store, model, a.id, "L")
    v = snap(model, store, a.id).verdict()
    assert v.status == "aderente" and "GPR e REQ" in v.headline
    gpr = v.processes[0]
    assert (gpr.results_ok, gpr.results_total, gpr.capability_ok, gpr.capability_total) == (19, 19, 3, 3)
    assert "Capacitação (CAP)" in v.explanation          # nunca afirma Nível G completo sem CAP

    store.set_rating(a.id, "REQ 4", "P")
    v = snap(model, store, a.id).verdict()
    assert v.status == "nao_aderente" and v.weak_points == ("REQ 4",)
    assert "O processo REQ não é satisfeito" in v.explanation

    store.set_rating(a.id, "GPR 1", None)
    v = snap(model, store, a.id).verdict()
    assert v.status == "incompleta" and "REQ 4" in v.explanation


def test_retomada_de_sessao(model, tmp_path):
    db = tmp_path / "r.sqlite3"
    s1 = Store(db)
    a = s1.create("Org", "Proj", "Ana", model)
    s1.set_rating(a.id, "GPR 2", "L")
    s1.add_evidence(a.id, "GPR 2", "arquivo", "/docs/processo.pdf")
    s1.create_finding(a.id, "GPR", ["GPR 2"], "Padronizar")
    s1.set_current(a.id, "GPR 2")
    s1.add_elapsed(a.id, 125)
    s1.close()
    s2 = Store(db)
    a2 = s2.get(a.id)
    assert a2.current_item == "GPR 2" and a2.elapsed_seconds == 125 and a2.phase == "inicial"
    ans = s2.answers(a.id)["GPR 2"]
    assert ans.rating == "L" and ans.evidences[0].content == "/docs/processo.pdf"
    assert s2.findings(a.id)[0].items == ("GPR 2",)
    actions = [r["action"] for r in s2.audit(a.id)]
    assert actions[:4] == ["criada", "caracterizacao", "evidencia_adicionada", "apontamento_criado"]
    s2.close()


def test_migracao_da_versao_1(model, tmp_path):
    db = tmp_path / "v1.sqlite3"
    old = sqlite3.connect(db)
    old.executescript("""
    CREATE TABLE assessments (id INTEGER PRIMARY KEY AUTOINCREMENT, organization TEXT NOT NULL, project TEXT NOT NULL,
      evaluator TEXT NOT NULL, model_id TEXT NOT NULL, model_version TEXT NOT NULL, model_checksum TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'em_andamento', elapsed_seconds INTEGER NOT NULL DEFAULT 0, current_item TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, finished_at TEXT);
    CREATE TABLE answers (assessment_id INTEGER NOT NULL, item_id TEXT NOT NULL, rating TEXT,
      justification TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL, PRIMARY KEY (assessment_id, item_id));
    CREATE TABLE evidences (id INTEGER PRIMARY KEY AUTOINCREMENT, assessment_id INTEGER NOT NULL, item_id TEXT NOT NULL,
      kind TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
    INSERT INTO assessments VALUES (1,'Org','Proj','Ana','MPS-SW-2024-G','2024.1','x','em_andamento',10,NULL,
      '2026-10-01T10:00:00','2026-10-01T10:00:00',NULL);
    INSERT INTO answers VALUES (1,'REQ 3','N','Sem compromisso registrado','2026-10-01T10:00:00');
    INSERT INTO answers VALUES (1,'GPR · CP-G (ii)','T','','2026-10-01T10:00:00');
    INSERT INTO answers VALUES (1,'REQ · CP-G (ii)','P','Sem plano do processo','2026-10-01T10:00:00');
    INSERT INTO evidences VALUES (1,1,'REQ · CP-G (ii)','texto','Plano','2026-10-01T10:00:00');
    """)
    old.commit()
    old.close()
    s = Store(db)
    s.upgrade_data(model)
    s.upgrade_data(model)                                  # idempotente
    ans = s.answers(1)
    assert "GPR · CP-G (ii)" not in ans and ans["CP-Proj (ii)"].rating == "P"     # vale a pior nota
    assert [e.content for e in ans["CP-Proj (ii)"].evidences] == ["Plano"]
    fs = {f.items: f for f in s.findings(1)}
    assert fs[("REQ 3",)].description == "Sem compromisso registrado"
    assert "[REQ] Sem plano do processo" in fs[("CP-Proj (ii)",)].description
    assert len(s.findings(1)) == 2 and s.get(1).phase == "inicial"
    s.close()


def test_relatorios(model, store, tmp_path):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    a = store.create("Org Ç", "Proj", "Ana", model)
    preencher(store, model, a.id, "P")
    s = snap(model, store, a.id)
    out = report.export_csv(tmp_path / "r.csv", model, store.get(a.id), s)
    rows = list(csv.reader(out.open(encoding="utf-8-sig"), delimiter=";"))
    assert rows[0] == report.CSV_HEADER and len(rows) == 1 + len(model.criteria)
    assert rows[1][report.CSV_HEADER.index("tipo_ajuste")] == "REQUERIDO"
    pdf = report.export_pdf(tmp_path / "r.pdf", model, store.get(a.id), s)
    assert pdf.read_bytes()[:4] == b"%PDF" and pdf.stat().st_size > 5000


def test_relatorio_tem_sumario_executivo_e_ajustes(model, store):
    a = store.create("Org", "Proj", "Ana", model)
    preencher(store, model, a.id)
    store.set_rating(a.id, "GPR 4", "L")
    store.create_finding(a.id, "GPR", ["GPR 4"], "Padronizar o registro das estimativas")
    html = report.build_html(model, store.get(a.id), snap(model, store, a.id))
    assert "Sumário executivo" in html and "Aderente ao Nível G nos processos avaliados" in html
    assert "Capacitação" in html and "Não avaliado" in html and "Tabela 2" in html
    assert "Relatório de ajustes" in html and "Padronizar o registro das estimativas" in html and "MELHORIA" in html


def test_xlsx_no_formato_do_relatorio_de_ajustes(model, store, tmp_path):
    from openpyxl import load_workbook
    a = store.create("Empresa X", "Projeto Y", "Ana", model)
    preencher(store, model, a.id)
    store.set_rating(a.id, "REQ 2", "P")
    store.set_rating(a.id, "REQ 4", "N")
    f = store.create_finding(a.id, "REQ", ["REQ 2", "REQ 4"], "Requisitos sem rastreabilidade")
    store.update_finding(a.id, f.id, suggestion="Mapear o refinamento", impact="LEVE")
    store.set_rating(a.id, "CP-Proj (iii)", "L")
    store.create_finding(a.id, "CP-Proj", ["CP-Proj (iii)"], "Treinamentos sem registro de participantes")
    store.set_rating(a.id, "GPR 11", "P")
    g = store.create_finding(a.id, "GPR", ["GPR 11"], "Viabilidade incompleta")
    store.update_finding(a.id, g.id, suggestion="Revisar os planos")
    store.set_status(a.id, True)
    store.start_final(a.id)
    store.update_finding(a.id, g.id, correction_status="Sim", correction_text="Planos revisados")
    store.set_final_rating(a.id, "GPR 11", "T")

    path = report.export_xlsx(tmp_path / "aj.xlsx", model, store.get(a.id), snap(model, store, a.id))
    wb = load_workbook(path)
    assert wb.sheetnames == [report.XLSX_SHEET, "PARAMETROS"]
    ws = wb[report.XLSX_SHEET]
    assert ws["A1"].value.startswith("RELATÓRIO DE AJUSTES PARA A AVALIAÇÃO FINAL") and "A1:I1" in ws.merged_cells
    assert [ws.cell(2, c).value for c in range(1, 10)] == report.XLSX_HEADER
    assert ws.freeze_panes == "A3" and ws.auto_filter.ref.startswith("A2:I")
    assert {k: round(ws.column_dimensions[k].width, 1) for k in "ABCDEFGHI"} == report.XLSX_WIDTHS
    assert ws["A2"].font.name == "Arial" and ws["A2"].font.b and ws["A2"].fill.fgColor.rgb == "FFEFEFEF"
    data = [[ws.cell(r, c).value for c in range(1, 10)] for r in range(3, 6)]
    assert data[0][:4] == ["Gerência de Projetos", "REQUERIDO", "GPR 11", "-"]
    assert data[0][6:] == ["Sim", "T", "Planos revisados"]
    assert data[1][:6] == ["Engenharia de Requisitos", "REQUERIDO", "REQ 2, 4", "LEVE",
                           "Requisitos sem rastreabilidade", "Mapear o refinamento"]
    assert data[2][:4] == ["Capacidade de Processos de Projetos (CP-Proj)", "MELHORIA", "iii", "-"]
    assert data[2][5] is None                               # sugestão só para problema
    assert ws.cell(6, 1).value is None
    dv = {str(d.sqref).split(":")[0]: d.formula1 for d in ws.data_validations.dataValidation}
    assert dv == {"A3": "ProcessosModeloAvaliado", "B3": "TipoAjuste", "D3": "ImpactoAvaliacao",
                  "G3": "CorrecaoRealizada", "H3": "Caracterizacao"}
    names = {n: wb.defined_names[n].attr_text for n in wb.defined_names}
    p = wb["PARAMETROS"]
    tipo = [c.value for row in p[names["TipoAjuste"].split("!")[1].replace("$", "")] for c in row]
    assert tipo == ["MELHORIA", "REQUERIDO"]
    corr = [c.value for row in p[names["CorrecaoRealizada"].split("!")[1].replace("$", "")] for c in row]
    assert corr == ["Sim", "Não", "Sem Correção"]


def test_requerido_leve(model, store):
    """Guia de Avaliação 2024, p. 58: requerido leve pode terminar em T sem correção, mantendo o ponto fraco."""
    a = store.create("Org", "Proj", "Ana", model)
    preencher(store, model, a.id, "T")
    for cid, impact in (("GPR 14", "LEVE"), ("GPR 15", "-")):
        store.set_rating(a.id, cid, "P")
        f = store.create_finding(a.id, "GPR", [cid], f"Problema de {cid}")
        store.update_finding(a.id, f.id, suggestion="Corrigir", impact=impact)
    store.set_status(a.id, True)
    store.start_final(a.id)
    leve, normal = store.findings(a.id)
    store.update_finding(a.id, leve.id, correction_status="Não")
    store.update_finding(a.id, normal.id, correction_status="Não")
    s = snap(model, store, a.id)
    assert s.leve_allows_t("GPR 14") and not s.leve_allows_t("GPR 15")
    assert not s.kept_as_weak("GPR 14")                       # ainda sem nova caracterização
    store.set_final_rating(a.id, "GPR 14", "T")
    store.set_final_rating(a.id, "GPR 15", "T")               # T sem leve: decisão da equipe, sem a regra
    s = snap(model, store, a.id)
    assert s.kept_as_weak("GPR 14") and not s.kept_as_weak("GPR 15")
    weak = {w.cid: w for w in s.remaining_weak_points()}
    assert set(weak) == {"GPR 14"} and weak["GPR 14"].leve and weak["GPR 14"].texts == ("Problema de GPR 14",)
    v = s.verdict()
    assert v.status == "aderente" and "GPR 14 foi caracterizado como T" in v.explanation
    # corrigido: T comum, sem ponto fraco mantido
    store.update_finding(a.id, leve.id, correction_status="Sim", correction_text="Feito")
    s = snap(model, store, a.id)
    assert not s.kept_as_weak("GPR 14") and s.remaining_weak_points() == []


def test_xlsx_aceita_texto_colado_de_pdf(model, store, tmp_path):
    from openpyxl import load_workbook
    a = store.create("Org", "Proj", "Ana", model)
    store.set_rating(a.id, "GPR 1", "P")
    f = store.create_finding(a.id, "GPR", ["GPR 1"], "ok")
    # dado gravado por versão anterior, com caracteres de controle de um PDF (\x02 é o hífen do Guia)
    store.db.execute("UPDATE findings SET description=?, suggestion=? WHERE id=?",
                     ("caracteriza\x02se\x0b o projeto", "revisar\x0c", f.id))
    store.db.commit()
    p = report.export_xlsx(tmp_path / "x.xlsx", model, store.get(a.id), snap(model, store, a.id))
    ws = load_workbook(p)[report.XLSX_SHEET]
    assert ws["E3"].value == "caracteriza-se o projeto" and ws["F3"].value == "revisar"
    store.update_finding(a.id, f.id, description="a\x02b\x0cc\r\nd")
    assert store.findings(a.id)[0].description == "a-bc\nd"   # limpo já na entrada
