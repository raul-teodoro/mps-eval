# MPS-Eval

Ferramenta desktop de apoio à avaliação de conformidade com o **MPS.BR — Nível G** (processos **GPR** e **REQ** e a capacidade dos processos de projeto, **CP-Proj**), desenvolvida para o Trabalho de Graduação (ITA).

## Fluxo da avaliação (v4)

A ferramenta segue as duas rodadas do método de avaliação MA-MPS (Guia de Avaliação 2024, Parte I):

1. **Avaliação inicial.** Cada resultado recebe T, L, P ou N, com ao menos uma evidência. O campo exigido depende da nota:

   | Nota | Campos | Tipo no Relatório de Ajustes |
   |---|---|---|
   | T | nenhum | não entra no relatório |
   | L | Oportunidade de melhoria | MELHORIA |
   | P ou N | Problema + Sugestão de correção | REQUERIDO |

   Cada apontamento tem também o **Impacto na avaliação** (`-` ou `LEVE`). Um apontamento pode valer para vários resultados do mesmo processo ("Aplicar também a…"): no relatório ele vira uma linha só, por exemplo `REQ 2, 4`.
2. **Relatório de Ajustes.** Ao concluir a avaliação inicial, o XLSX sai no formato da planilha de referência (`RELATÓRIO DE AJUSTES PARA A AVALIAÇÃO FINAL`), com as mesmas colunas, larguras, cores e listas suspensas.
3. **Avaliação final (revisita).** Só os resultados com apontamento são percorridos. Em cada apontamento, o avaliador registra **Empresa realizou correção?** (Sim, Não ou Sem correção) e a **Correção realizada**, obrigatória quando é "Sim". Em cada resultado, registra a **nova caracterização** (T, L, P, N ou NA). Com "Não" ou "Sem correção", a nova caracterização já vem preenchida com a nota inicial.
4. **Veredito.** A revisão mostra o veredito da avaliação final e, abaixo, o da inicial. O tempo é medido separadamente em cada fase.

### Requerido "Leve"

O impacto só existe em apontamentos REQUERIDO. Pelo Guia de Avaliação 2024, Parte I, p. 58, um requerido classificado como **Leve** pode terminar em **T** na avaliação final, mas deve constar como ponto fraco no resultado final.

| Situação na revisita | O que o app faz |
|---|---|
| Requerido leve e a empresa corrigiu (Sim) | T comum; nada especial |
| Requerido leve, sem correção (Não ou Sem correção) e nova nota ainda não é T | Aviso azul: o guia permite T, e o problema continua como ponto fraco |
| Requerido leve, sem correção e nova nota T | Aviso laranja "P → T por requerido leve" e uma mensagem na hora; o resultado entra em **Pontos fracos que permanecem** (revisão e PDF), aparece como "T · leve" no relatório de ajustes e é citado no veredito |
| Requerido sem Leve, sem correção | Nenhuma regra especial; a nota fica a critério do avaliador |

A lógica está em `Snapshot.kept_as_weak` (`core/rules.py`), com a leitura adotada comentada no código. A ferramenta não força o T: só informa que ele é permitido e registra o ponto fraco quando acontece.

### Erros

Texto colado de PDF pode trazer caracteres de controle que o Excel recusa (no Guia MPS, o hífen vem como `\x02`). Eles são limpos ao salvar e de novo ao exportar. Qualquer erro inesperado vira uma mensagem na tela, e o detalhe fica em `erros.log`, na mesma pasta do banco. O app não fecha mais por causa de uma exceção.

## Como executar

Requer Python 3.10 ou superior.

```bash
pip install -r requirements.txt
python -m mpseval
```

Os dados ficam num banco SQLite local:

| Sistema | Caminho do banco |
|---|---|
| Windows | `%APPDATA%\MPS-Eval\mpseval.sqlite3` |
| Linux / macOS | `~/.mps-eval/mpseval.sqlite3` |

Para usar outro diretório (por exemplo, um banco separado por grupo no teste A/B), defina a variável `MPSEVAL_HOME`.

Testes automatizados (núcleo e fluxos de interface, sem abrir janela):

```bash
pip install pytest
QT_QPA_PLATFORM=offscreen python -m pytest -q tests
```

## Instalador para Windows (um único arquivo)

Para distribuir o app, gere o `MPS-Eval-Setup-<versão>.exe`. Quem recebe não precisa de Python, venv nem pip: basta dar duplo clique.

**O que o instalador faz:**
- **Instalação sem administrador:** instala em `%LOCALAPPDATA%\Programs\MPS-Eval`. Quem tiver permissão pode escolher instalar para todos os usuários.
- **Atalhos:** cria o atalho no Menu Iniciar e, opcionalmente, na Área de Trabalho, já com o AppUserModelID, para janela e atalho virarem um único ícone na barra de tarefas.
- **Desinstalador:** registra o app em "Aplicativos instalados" do Windows.
- **Final da instalação:** oferece abrir o app.
- **Atualização:** uma versão nova substitui a anterior e fecha o app se ele estiver aberto.
- **Dados preservados:** as avaliações em `%APPDATA%\MPS-Eval` sobrevivem a atualizações e desinstalações. Ao desinstalar, o instalador pergunta, com "Não" como padrão, se deve apagá-las.

### Opção A: gerar no seu Windows

Uma vez só, instale o [Inno Setup 6.3+](https://jrsoftware.org/isdl.php) (ou `winget install JRSoftware.InnoSetup`). Depois, na pasta do projeto, com o venv ativo:

```
python -m pip install -r requirements.txt -r requirements-build.txt
python build_windows.py
```

O `build_windows.py` faz quatro etapas:
1. Grava nome e versão nas propriedades do `.exe`.
2. Empacota o app com o PyInstaller.
3. Abre o executável em modo de autoteste: carrega os critérios, o ícone e as fontes, gera um PDF e fecha.
4. Compila o instalador.

O resultado sai em `dist\MPS-Eval-Setup-1.0.0.exe`.

### Opção B: gerar no GitHub, sem instalar nada

Com o projeto num repositório do GitHub, vá em **Actions → Instalador Windows → Run workflow**, ou crie uma tag `v1.0.0`. O workflow (`.github/workflows/build-windows.yml`) roda os testes, gera o instalador numa máquina Windows e deixa o `.exe` em **Artifacts**.

### Versão

A versão fica em `mpseval/__init__.py` (`__version__`). Mude-a antes de gerar uma nova versão, para o instalador substituir a anterior corretamente.

### Aviso do SmartScreen

O executável não tem assinatura digital. Por isso, na primeira execução o Windows pode mostrar "O Windows protegeu o computador". Clique em **Mais informações → Executar assim mesmo**. Para eliminar o aviso, é preciso assinar o instalador com um certificado de assinatura de código. Em máquinas corporativas, a TI pode exigir isso ou liberar o arquivo.

## Atalho no Windows rodando pelo código-fonte

Com o instalador, esta seção não é necessária: ele já cria os atalhos. Ela vale para quem roda o app direto do código, num venv.

O app usa um **AppUserModelID** fixo (`ITA.MPSEval.Desktop.1`, em `mpseval/windows.py`). Para o Windows tratar a janela e o atalho como **um único app**, com ícone próprio e não como "python.exe", o mesmo ID fica em três lugares:

1. **Processo.** `SetCurrentProcessExplicitAppUserModelID` é chamado na abertura, antes de criar qualquer janela.
2. **Atalho `.lnk`.** O ID é gravado na propriedade `System.AppUserModel.ID` do atalho.
3. **Janela.** Recebe o ID e o comando de relançamento. Assim, "Fixar na barra de tarefas" com o app aberto fixa o MPS-Eval, e não um Python solto.

Para criar os atalhos (Menu Iniciar e Área de Trabalho), rode o `criar_atalho.py` **com o Python do venv que vai abrir o app**:

```
.venv\Scripts\python criar_atalho.py
```

Com o venv ativado, `python criar_atalho.py` dá no mesmo. O script:

1. **Reconhece o venv.** Usa o ambiente que o está executando. Se rodar fora de um venv, procura `.venv`, `venv` ou `env` na pasta do projeto. Se não achar nenhum, para e explica como criar.
2. **Confere o ambiente.** Testa, dentro desse venv, se PyQt6 e pywin32 estão instalados. Se faltar algo, mostra o comando `pip` exato.
3. **Cria o atalho.** O atalho executa `pythonw.exe -m mpseval` desse venv, sem janela de console, com o ícone e o AppUserModelID do app.

| Opção | Efeito |
|---|---|
| `--verificar` | Mostra venv, comando e locais, sem criar nada |
| `--python CAMINHO` | Usa outro venv (a pasta ou o `python.exe` dele) |
| `--exe CAMINHO` | Aponta para o executável do PyInstaller |
| `--sem-desktop` / `--sem-menu` | Pula um dos atalhos |
| `--remover` | Apaga os atalhos |

- **Fixar na barra.** Desde o Windows 10 isso não pode ser feito por código. Clique com o botão direito no atalho do Menu Iniciar e escolha **Fixar na barra de tarefas**.
- **Se o venv for recriado ou mudar de pasta,** rode o script de novo.
- **A janela aberta usa o mesmo comando** como "comando de relançamento". Por isso, fixar a partir do app aberto dá o mesmo resultado.
- **Ícone:** fica em `mpseval/assets/icon/`. Para regenerá-lo, rode `python tools/gerar_icone.py` (requer Pillow).

## Estrutura

```
mpseval/
  data/nivel_g_2024.json   critérios do Guia Geral MPS 2024 (dados, não código)
  core/model.py            carga e versionamento do modelo normativo
  core/storage.py          SQLite: avaliações, respostas, evidências, apontamentos, fases, auditoria
  core/rules.py            fail-safe, campos por nota, revisita, consolidação, veredito e ajustes
  core/report.py           relatórios PDF, CSV e o Relatório de Ajustes em XLSX
  ui/                      interface PyQt6 no padrão visual iOS/iPadOS
  windows.py               AppUserModelID e integração com a barra de tarefas
  assets/icon/             ícone do app (.ico multi-resolução e PNGs)
criar_atalho.py            atalhos .lnk presos ao venv (uso a partir do código-fonte)
run_mpseval.py             ponto de entrada do executável
build_windows.py           gera o executável e o instalador
packaging/mpseval.spec     receita do PyInstaller
packaging/installer.iss    script do instalador (Inno Setup)
.github/workflows/         build do instalador no GitHub Actions
tools/gerar_icone.py       gera o ícone
tests/                     testes do núcleo, da interface e do módulo Windows
```

## Requisitos do TG1 e onde estão atendidos

| Requisito (relatório / apresentação TG1) | Implementação |
|---|---|
| Cobertura de 100% dos resultados GPR e REQ do Nível G | `nivel_g_2024.json`: GPR 1–19, REQ 1–5 e CP-Proj i–iii (teste `test_cobertura_normativa_nivel_g`) |
| Módulo I: navegação guiada e revisão não linear | Lista lateral com busca; Próximo/Anterior; salto direto a qualquer item |
| Módulo II: registro com evidência obrigatória (fail-safe) | "Próximo" e "Concluir" travados sem caracterização + evidência |
| Validação automática e alertas de omissão | Estado por item na lista, contador de pendentes, tela de revisão com pendências clicáveis |
| Módulo III: persistência, retomada e alteração | Gravação imediata em SQLite; reabre no último item; avaliação concluída pode ser reaberta |
| Rastreabilidade | Trilha de auditoria de cada caracterização, evidência e justificativa |
| Módulo IV: relatório consolidado PDF/CSV | Revisão final e menu da lista; CSV com `;` e UTF-8 (abre direto no Excel) |
| Relatório de Ajustes (pedido do orientador) | XLSX no formato da planilha de referência, com revisita e "Correção realizada" |
| Métrica de tempo do teste A/B | Cronômetro por avaliação, persistido, com pausa; vai para o relatório |
| Modelo atualizável sem reescrever a lógica | Critérios em JSON com versão e checksum gravados em cada avaliação |
| Stack Python + PyQt6 + SQLite | Dependências: PyQt6, openpyxl (XLSX) e, só no Windows, pywin32 (atalhos) |

## Decisões que merecem validação com o orientador

1. **GPR tem 19 resultados no Nível G, não 10.** No Guia 2024 valem, para o Nível G, os resultados marcados "A partir do nível G" e "Até nível E". Isso dá GPR 1–19 e REQ 1–5. O relatório do TG1 menciona "GPR 1 ao GPR 10".
2. **Capacidade avaliada uma vez (CP-Proj).** Os processos de projeto são tratados como um único processo para a capacidade (Guia Geral 2024, Figura 3; Guia de Avaliação 2024, p. 56), como na planilha de ajustes do orientador. Os itens CP-G i–iii valem para GPR e REQ: um item de capacidade em P ou N reprova os dois.
3. **Escala T/L/P/N/NA.** Tabela 7 do Guia de Avaliação 2024, Parte I. NA só existe na nova caracterização da avaliação final e não conta a favor nem contra.
4. **Campos por nota.** Decisão da reunião com o orientador: T sem campo; L com Oportunidade de melhoria; P e N com Problema e Sugestão de correção. Todos obrigatórios (fail-safe).
5. **Um projeto por avaliação.** A ferramenta avalia um projeto; a agregação de vários projetos (Tabela 8) fica como trabalho futuro.
6. **Regra de consolidação e veredito.** GPR e REQ são satisfeitos quando seus resultados esperados e os itens CP-Proj estão em T ou L. O sumário executivo tem três vereditos possíveis:
   - **Avaliação incompleta:** ainda há pendências;
   - **Não aderente ao Nível G:** algum item está em P ou N;
   - **Aderente ao Nível G nos processos avaliados (GPR e REQ):** tudo em T ou L.
7. **CAP fora do escopo.** O processo Capacitação também é exigido no Nível G (Tabela 2 do Guia Geral 2024). Por isso a ferramenta nunca afirma "Nível G atingido", apenas "aderente" em GPR e REQ. Para passar a "atingido", é preciso avaliar o CAP.
8. **Quem preenche a correção.** No método oficial, a empresa registra os ajustes realizados (Guia de Avaliação, p. 43). Aqui o avaliador digita a correção na revisita; importar a planilha preenchida pela empresa fica como trabalho futuro.
9. **Sugestões de evidência.** Os textos "Onde procurar evidências" são sugestões do protótipo e não fazem parte do Guia. Revisá-los é a mitigação do risco de interpretação ambígua citado no relatório.

**Migração automática.** Bancos da versão anterior são convertidos ao abrir: o CP-G que era repetido em GPR e REQ vira CP-Proj, ficando com a pior nota e as evidências dos dois, e a antiga "Justificativa" de itens L, P e N vira o texto do apontamento.

## Revisão de interface (v1 → v2)

Depois do protótipo, a interface foi revisada em capturas de tela e ajustada:

- **Indicador de salvamento:** o horário fixo "Salvo 09:39:50" virou um aviso transitório "Salvo".
- **Cronômetro pausado:** passou a ter destaque em âmbar, para não distorcer a métrica de tempo sem ser percebido.
- **Botão de evidência:** vira "Adicionar" quando há texto digitado, e não confunde mais com "Anexar arquivo".
- **Remoção de evidência:** agora pode ser desfeita com Ctrl+Z.
- **Pendências no rodapé:** o rodapé mostra quantos itens faltam e salta para o próximo pendente (Ctrl+Shift+Enter).
- **Orientação de evidência:** alinhada ao texto e com estado lembrado entre itens e sessões.
- **Atalhos:** painel de atalhos de teclado (F1 ou ícone no topo).
- **Lista lateral:** mais larga, com menos títulos cortados; Enter na busca abre o primeiro resultado.
- **Orientação no item:** o cabeçalho mostra a posição ("Item 5 de 30").
- **Revisão final:** pontos fracos em linha própria e contagem de itens em T ou L.
- **Correções de bugs:** removidos widgets "fantasma" ao trocar de item ou de lista.

Medições no ambiente de desenvolvimento: abertura em cerca de 140 ms, abrir avaliação em cerca de 80 ms e troca de item em cerca de 3 ms.

## Estética (v3, padrão iOS/iPadOS)

- **Cores:** paleta de sistema da Apple (azul `#007AFF`, verde, laranja, vermelho). Para texto colorido sobre branco, usa as variantes de alto contraste.
- **Superfícies:** fundo cinza agrupado (`#F2F2F7`) com listas em cartões brancos arredondados, cabeçalhos de seção e notas de rodapé.
- **Barras:** barra de navegação e barra de ferramentas translúcidas, com separadores finos.
- **Barra lateral:** estilo iPadOS, com seleção em azul sólido.
- **Controles:** caracterização T/L/P/N num controle segmentado com polegar deslizante e switch para as dicas de evidência.
- **Tipografia:** SF Pro quando instalada (macOS). No Windows, usa Inter, que acompanha o app e tem desenho muito próximo, já que a licença da SF Pro não permite distribuí-la.

## Atalhos de teclado

| Atalho | Ação |
|---|---|
| `1` `2` `3` `4` ou `Alt+1…4` | Caracterizar como T, L, P ou N |
| `5` ou `Alt+5` | NA, na nova caracterização da avaliação final |
| `←` `→` | Trocar a caracterização com o controle em foco |
| `Ctrl+Enter` | Próximo item (exige o item completo) |
| `Ctrl+Shift+Enter` | Próximo item pendente |
| `Ctrl+↑` / `Ctrl+↓` | Navegar livremente |
| `Ctrl+F` | Buscar critério |
| `Ctrl+E` | Ir para o campo de evidência |
| `Ctrl+Z` | Desfazer remoção de evidência |
| `Ctrl+R` | Revisão da fase atual |
| `Ctrl+P` | Pausar ou retomar o cronômetro |
| `F1` | Lista de atalhos |

A fonte Inter é distribuída sob a SIL Open Font License 1.1.
