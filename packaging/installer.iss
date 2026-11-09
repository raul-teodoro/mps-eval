; Instalador do MPS-Eval (Inno Setup 6.3 ou superior)
; Gera dist\MPS-Eval-Setup-<versão>.exe a partir de dist\MPS-Eval\ (saída do PyInstaller).
; Normalmente compilado por build_windows.py, que passa /DAppVersion=x.y.z.

#define AppName "MPS-Eval"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppExe "MPS-Eval.exe"
; Deve ser idêntico a APP_ID em mpseval/windows.py: é o que une janela e atalho na barra de tarefas
#define AppUserModelID "ITA.MPSEval.Desktop.1"

[Setup]
; GUID fixo: identifica o app entre versões (atualizações substituem a instalação anterior)
AppId={{6E2B9C41-7D3A-4F58-9B0E-2A1C5D8F3E77}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Instituto Tecnológico de Aeronáutica — Trabalho de Graduação
AppComments=Avaliação de conformidade MPS.BR — Nível G (GPR e REQ)
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
; Instala por usuário, sem pedir administrador (em %LOCALAPPDATA%\Programs\MPS-Eval).
; Quem tiver permissão pode escolher "para todos os usuários" no diálogo.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=MPS-Eval-Setup-{#AppVersion}
SetupIconFile=..\mpseval\assets\icon\mpseval.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Fecha o app aberto antes de atualizar
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\MPS-Eval\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; AppUserModelID no atalho = mesmo ID que o app define ao abrir → um único ícone na barra de tarefas
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; \
    AppUserModelID: "{#AppUserModelID}"; Comment: "Avaliação de conformidade MPS.BR"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; \
    AppUserModelID: "{#AppUserModelID}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
{ As avaliações ficam em %APPDATA%\MPS-Eval e são preservadas por padrão.
  Ao desinstalar, pergunta (com "Não" como padrão) se devem ser apagadas. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
  begin
    DataDir := ExpandConstant('{userappdata}\MPS-Eval');
    if DirExists(DataDir) then
      if MsgBox('Deseja apagar também as avaliações salvas em:' + #13#10 + DataDir + #13#10#13#10 +
                'Esta ação não pode ser desfeita.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
