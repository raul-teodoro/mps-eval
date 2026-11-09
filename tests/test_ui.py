"""Testes de fluxo da interface (executam sem tela, com QT_QPA_PLATFORM=offscreen)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from mpseval.core import rules  # noqa: E402
from mpseval.core.model import load_model  # noqa: E402
from mpseval.core.storage import Store  # noqa: E402


@pytest.fixture(scope="module")
def app():
    QCoreApplication.setOrganizationName("ITA-test")
    QCoreApplication.setApplicationName("MPS-Eval-test")
    a = QApplication.instance() or QApplication([])
    from mpseval.ui import theme
    theme.load_fonts()
    a.setStyleSheet(theme.QSS)
    return a


@pytest.fixture()
def ws(app, tmp_path):
    from mpseval.ui.main_window import MainWindow
    model = load_model()
    store = Store(tmp_path / "ui.sqlite3")
    a = store.create("Org", "Proj", "Ana", model)
    win = MainWindow(store, model)
    win.show()
    win.open_assessment(a.id)
    QTest.qWaitForWindowExposed(win)
    yield win.workspace, store, model
    win.close()
    store.close()


def add_ev(w, text="Evidência"):
    w.editor.ev_input.setText(text)
    w.editor._add_text()


def card(w):
    return next(iter(w.editor._cards.values()))


def type_in(w, key, text):
    c = card(w)
    c.fields[key].setPlainText(text)
    c.flush()


def test_fail_safe_pelo_teclado(ws):
    w, store, model = ws
    assert w.current() == "GPR 1"
    assert not w.next_btn.isEnabled()
    w.sidebar.list.setFocus()
    QTest.keyClick(w, Qt.Key.Key_1)                       # caracteriza como T
    assert store.answers(w.aid)["GPR 1"].rating == "T"
    assert not w.next_btn.isEnabled()                      # ainda sem evidência
    assert not w.editor.find_section.isVisibleTo(w.editor)  # T não tem apontamento
    w.editor.ev_input.setFocus()
    QTest.keyClicks(w.editor.ev_input, "Termo de abertura 1")   # "1" digitado não recaracteriza
    assert store.answers(w.aid)["GPR 1"].rating == "T"
    QTest.keyClick(w.editor.ev_input, Qt.Key.Key_Return)
    assert [e.content for e in store.answers(w.aid)["GPR 1"].evidences] == ["Termo de abertura 1"]
    assert w.next_btn.isEnabled()
    QTest.keyClick(w, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert w.current() == "GPR 2"


def test_p_exige_problema_e_sugestao(ws):
    w, store, model = ws
    w.editor.rating.select("P")
    add_ev(w, "Planilha parcial")
    assert w.editor.find_section.isVisibleTo(w.editor) and len(w.editor._cards) == 1
    assert "Problema" in w.editor.find_title.title.text()
    assert not w.next_btn.isEnabled()
    type_in(w, "description", "Escopo não é mantido atualizado")
    assert not w.next_btn.isEnabled()
    type_in(w, "suggestion", "Revisar o escopo a cada mudança aprovada")
    assert w.next_btn.isEnabled()
    f = store.findings(w.aid)[0]
    assert (f.items, f.description, f.suggestion) == (("GPR 1",), "Escopo não é mantido atualizado",
                                                     "Revisar o escopo a cada mudança aprovada")


def test_l_exige_oportunidade_e_troca_de_rotulo(ws):
    w, store, model = ws
    add_ev(w)
    w.editor.rating.select("L")
    assert w.editor.find_title.title.text() == "Oportunidade de melhoria"
    assert "suggestion" not in card(w).fields
    type_in(w, "description", "Padronizar o termo de abertura")
    assert w.next_btn.isEnabled()
    w.editor.rating.select("T")                     # texto preservado, campo some
    assert not w.editor.find_section.isVisibleTo(w.editor) and w.next_btn.isEnabled()
    w.editor.rating.select("P")                     # volta como Problema, falta a sugestão
    assert card(w).fields["description"].toPlainText() == "Padronizar o termo de abertura"
    assert not w.next_btn.isEnabled() and "sugestão de correção" in w.state_lbl.text()


def test_aplicar_a_varios_resultados(ws, monkeypatch):
    w, store, model = ws
    from mpseval.ui import findings as F
    for cid in ("REQ 2", "REQ 4"):
        w.open_item(cid)
        add_ev(w, "Documento de requisitos")
        w.editor.rating.select("N" if cid == "REQ 4" else "P")
    w.open_item("REQ 2")
    type_in(w, "description", "Sem rastreabilidade")
    type_in(w, "suggestion", "Criar matriz de rastreabilidade")
    fid = card(w).f.id

    def fake_exec(self):
        assert self.rows["REQ 4"]._enabled and not self.rows["REQ 1"]._enabled   # REQ 1 sem nota
        self.rows["REQ 4"].set_checked(True)
        return True
    monkeypatch.setattr(F.LinkDialog, "exec", fake_exec)
    w._on_finding_link(fid)
    fs = store.findings(w.aid)
    assert len(fs) == 1 and fs[0].items == ("REQ 2", "REQ 4")       # o vazio de REQ 4 foi descartado
    assert "REQ 4" in card(w).shared.text()
    s = rules.load(model, store, w.aid)
    assert s.check("REQ 4").done and s.adjustments()[0].refs == "REQ 2, 4"
    w._on_finding_unlink(fid)                                         # REQ 2 ganha apontamento próprio
    fs = {f.items: f for f in store.findings(w.aid)}
    assert ("REQ 4",) in fs and ("REQ 2",) in fs and fs[("REQ 2",)].empty


def test_digitos_no_texto_nao_recaracterizam(ws):
    w, store, model = ws
    add_ev(w)
    w.editor.rating.select("N")
    ed = card(w).fields["description"]
    ed.setFocus()
    QTest.keyClicks(ed, "Faltam 2 de 4 planos")
    card(w).flush()
    assert store.answers(w.aid)["GPR 1"].rating == "N"
    assert store.findings(w.aid)[0].description == "Faltam 2 de 4 planos"
    card(w).impact.setFocus()
    QTest.keyClick(card(w).impact, Qt.Key.Key_Delete)          # não deixa o impacto vazio
    assert store.findings(w.aid)[0].impact == "-"


def test_desfazer_remocao(ws):
    w, store, model = ws
    add_ev(w, "Evidência A")
    eid = store.answers(w.aid)["GPR 1"].evidences[0].id
    w._on_evidence_removed("GPR 1", eid)
    assert not store.answers(w.aid).get("GPR 1").evidences
    w.undo_remove()
    assert [e.content for e in store.answers(w.aid)["GPR 1"].evidences] == ["Evidência A"]


def test_duas_fases(ws):
    w, store, model = ws
    for c in model.criteria:
        store.set_rating(w.aid, c.id, "T")
        store.add_evidence(w.aid, c.id, "texto", "ok")
    store.set_rating(w.aid, "GPR 5", "P")
    f = store.create_finding(w.aid, "GPR", ["GPR 5"], "Estimativas sem base")
    store.update_finding(w.aid, f.id, suggestion="Registrar a base histórica")
    w._reload("GPR 1")
    w.show_review()
    w._finalize()
    a = store.get(w.aid)
    assert a.finished and not a.in_final
    w.open_item("GPR 1")
    assert not w.editor.rating.isEnabled()
    w._rate_key("N")                                       # bloqueado após concluir
    assert store.answers(w.aid)["GPR 1"].rating == "T"
    assert w.banner.isVisibleTo(w) and w.banner_btn2.isVisibleTo(w)

    w._start_final()
    assert store.get(w.aid).in_final and w.order == ["GPR 5"] and w.current() == "GPR 5"
    assert w.editor.final_section.isVisibleTo(w.editor) and card(w).status is not None
    assert w.sidebar._rows["GPR 1"].isHidden() and not w.sidebar._rows["GPR 5"].isHidden()
    assert not w.next_btn.isEnabled()
    card(w).status.select("Não")                           # sem correção: mantém a nota inicial
    assert store.answers(w.aid)["GPR 5"].final_rating == "P"
    assert w.editor.final_rating.value() == "P" and w.next_btn.isEnabled()
    card(w).status.select("Sim")
    assert not w.next_btn.isEnabled() and "correção realizada" in w.state_lbl.text()
    type_in(w, "correction_text", "Base histórica registrada no plano")
    w.sidebar.list.setFocus()
    QTest.keyClick(w, Qt.Key.Key_1)                        # nova caracterização T pelo teclado
    assert store.answers(w.aid)["GPR 5"].final_rating == "T" and w.next_btn.isEnabled()
    w.show_review()
    w._finalize()
    a = store.get(w.aid)
    assert a.completed
    assert rules.load(model, store, w.aid).verdict().status == "aderente"
    w._reopen()
    assert not store.get(w.aid).finished and store.get(w.aid).in_final
    w._back_to_initial()
    a = store.get(w.aid)
    assert not a.in_final and store.answers(w.aid)["GPR 5"].final_rating == "T"


def test_cronometro_persiste(ws):
    w, store, model = ws
    for _ in range(3):
        w._last_tick -= 1
        w._on_tick()
    w.flush()
    assert store.get(w.aid).elapsed_seconds == 3
    w.toggle_pause()
    w._on_tick()
    w.flush()
    assert store.get(w.aid).elapsed_seconds == 3


def test_requerido_leve_na_revisita(ws):
    w, store, model = ws
    for c in model.criteria:
        store.set_rating(w.aid, c.id, "T")
        store.add_evidence(w.aid, c.id, "texto", "ok")
    store.set_rating(w.aid, "GPR 14", "P")
    f = store.create_finding(w.aid, "GPR", ["GPR 14"], "Relatório sem orçamento")
    store.update_finding(w.aid, f.id, suggestion="Incluir orçamento", impact="LEVE")
    w._reload("GPR 1")
    w._finalize()
    w._start_final()
    assert w.current() == "GPR 14"
    assert not w.editor.leve_note.isVisibleTo(w.editor)
    card(w).status.select("Não")                         # sem correção: nova nota vem como P
    assert w.editor.final_rating.value() == "P"
    assert w.editor.leve_note.isVisibleTo(w.editor) and "sem correção" in w.editor.leve_title.text()
    w.editor.final_rating.select("T")                    # leve permite T
    assert store.answers(w.aid)["GPR 14"].final_rating == "T"
    assert w.editor.leve_title.text() == "P → T por requerido leve"
    assert "GPR 14: P → T por requerido leve" in w.toast.text()
    w.show_review()
    assert w._kept == {"GPR 14"}


def test_impacto_so_em_requerido(ws):
    w, store, model = ws
    add_ev(w)
    w.editor.rating.select("L")
    assert card(w).impact is None
    w.editor.rating.select("P")
    assert card(w).impact is not None


def test_erro_na_exportacao_nao_fecha_o_app(ws, monkeypatch, tmp_path):
    w, store, model = ws
    from mpseval import errors
    from mpseval.core import report
    from mpseval.ui import export as E
    shown = []
    monkeypatch.setattr(E.QFileDialog, "getSaveFileName", lambda *a, **k: (str(tmp_path / "x.xlsx"), ""))
    monkeypatch.setattr(errors, "show_error", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(errors, "log_path", lambda: tmp_path / "erros.log")

    def boom(*a, **k):
        raise ValueError("falha simulada")
    monkeypatch.setattr(report, "export_xlsx", boom)
    assert E.export_dialog(w, store, model, w.aid, "xlsx") is None
    assert shown == ["Ocorreu um erro ao gerar o relatório."]
    assert "falha simulada" in (tmp_path / "erros.log").read_text(encoding="utf-8")

    def missing(*a, **k):
        raise ImportError("No module named 'openpyxl'")
    monkeypatch.setattr(report, "export_xlsx", missing)
    E.export_dialog(w, store, model, w.aid, "xlsx")
    assert "pip install -r requirements.txt" in shown[-1]
