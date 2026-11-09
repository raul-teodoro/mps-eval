"""Diálogo de exportação compartilhado entre a tela inicial e a área de trabalho."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from .. import errors
from ..core import report, rules
from ..core.model import NormModel
from ..core.storage import Store


def export_dialog(parent: QWidget, store: Store, model: NormModel, aid: int, kind: str) -> Path | None:
    a = store.get(aid)
    settings = QSettings()
    last_dir = settings.value("export_dir", str(Path.home()))
    slug = re.sub(r"[^\w-]+", "_", f"{a.organization}_{a.project}").strip("_")[:60] or "avaliacao"
    suffix = "" if a.finished else "_parcial"
    if kind == "xlsx":
        name = f"RELATORIO_DE_AJUSTES_{slug}{'_FINAL' if a.in_final else '_INICIAL'}{suffix}.xlsx"
    else:
        name = f"MPS-Eval_{slug}{suffix}.{kind}"
    filters = {"pdf": "PDF (*.pdf)", "csv": "CSV (*.csv)", "xlsx": "Planilha do Excel (*.xlsx)"}
    path, _ = QFileDialog.getSaveFileName(parent, "Exportar relatório", str(Path(last_dir) / name), filters[kind])
    if not path:
        return None
    if not path.lower().endswith(f".{kind}"):
        path += f".{kind}"
    settings.setValue("export_dir", str(Path(path).parent))
    try:
        fn = {"pdf": report.export_pdf, "csv": report.export_csv, "xlsx": report.export_xlsx}[kind]
        return fn(path, model, a, rules.load(model, store, aid))
    except ImportError as e:
        # o XLSX usa o pacote openpyxl; num venv antigo ele pode não estar instalado
        errors.show_error(parent, "Não foi possível exportar",
                          "Falta um componente para gerar a planilha. No terminal, com o venv ativo, rode:\n\n"
                          "pip install -r requirements.txt", e)
    except PermissionError as e:
        QMessageBox.warning(parent, "Não foi possível exportar",
                            f"O arquivo está aberto em outro programa (por exemplo, no Excel) ou a pasta não "
                            f"permite gravação. Feche o arquivo e tente de novo.\n\n{e}")
    except OSError as e:
        QMessageBox.warning(parent, "Não foi possível exportar", f"O arquivo não pôde ser gravado:\n{e}")
    except Exception as e:      # noqa: BLE001 — nunca derrubar o app por causa de uma exportação
        log = errors.log_exception(*sys.exc_info(), context=f"exportação {kind}")
        errors.show_error(parent, "Não foi possível exportar", "Ocorreu um erro ao gerar o relatório.", e, log)
    return None
