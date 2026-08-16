#define MyAppVersion GetEnv("APP_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "0.0.0-dev"
#endif

[Setup]
AppName=Antiquarian
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\Antiquarian
DefaultGroupName=Antiquarian
OutputBaseFilename=Antiquarian_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes

[Files]
Source: "dist\Antiquarian\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Code]
var
  GenealogyPage: TInputDirWizardPage;
  Rmpage: TInputDirWizardPage;
  PortablePage: TInputOptionWizardPage;

procedure InitializeWizard;
begin
  // Anchored at wpWelcome (not wpSelectDir) so the Portable/Standard choice - and the
  // Genealogy directory it depends on for the portable install path - are both known
  // BEFORE the built-in directory-selection page is reached. Getting this order backwards
  // is what silently sent Portable installs to Program Files: the choice was being made
  // after the directory had already been fixed.
  PortablePage := CreateInputOptionPage(wpWelcome,
    'Installation Type', 'Choose your installation type.',
    'Please choose whether to install Antiquarian normally or in Portable mode.', True, False);
  PortablePage.Add('Standard Installation (Recommended)');
  PortablePage.Add('Portable Installation');
  PortablePage.Values[0] := True;

  GenealogyPage := CreateInputDirPage(PortablePage.ID,
    'Genealogy Directory', 'Where is your Genealogy folder?',
    'Select your primary Genealogy directory where Antiquarian will scaffold its folders.',
    False, '');
  GenealogyPage.Add('');

  Rmpage := CreateInputDirPage(GenealogyPage.ID,
    'RootsMagic Directory', 'Where is your RootsMagic folder?',
    'Select the folder containing your RootsMagic files.',
    False, '');
  Rmpage.Add('');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  // Portable mode bypasses Program Files entirely - the install directory is computed
  // from the Genealogy directory instead (see CurPageChanged), so the built-in
  // directory-selection page has nothing left to ask.
  Result := (PageID = wpSelectDir) and PortablePage.Values[1];
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  // Fires once GenealogyPage's own value is final (whether or not wpSelectDir ends up
  // shown) so {app} reflects the Portable/Standard choice either way.
  if CurPageID = Rmpage.ID then
  begin
    if PortablePage.Values[1] then
      WizardForm.DirEdit.Text := AddBackslash(GenealogyPage.Values[0]) + 'Antiquarian'
    else
      WizardForm.DirEdit.Text := ExpandConstant('{autopf}\Antiquarian');
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
begin
  if CurPageID = wpReady then
  begin
    // Antigravity CLI (agy) ships as a single native binary with no Node.js/npm
    // dependency - installed via its own PowerShell script, not a package manager.
    // Skip reinstalling if it's already on PATH. Note: a fresh install may not be
    // visible to this same running Setup process's PATH until the user's next shell -
    // this is a limitation of how Windows propagates PATH changes, not something a
    // single installer run can fully work around.
    Exec('cmd.exe', '/c agy --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if ResultCode <> 0 then
      Exec('powershell.exe', '-NoProfile -Command "irm https://antigravity.google/cli/install.ps1 | iex"', '',
          SW_HIDE, ewWaitUntilTerminated, ResultCode);

    // Download the US Newberry Atlas historical county boundaries
    DownloadTemporaryFile('https://publications.newberry.org/ahcb/downloads/gis/US_AtlasHCB_Counties.zip', ExpandConstant('{tmp}\US_AtlasHCB_Counties.zip'), '', nil);
  end;
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  GenDir, RmDir, GazDir, EnvContent: String;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if PortablePage.Values[1] then
      SaveStringToFile(ExpandConstant('{app}\.portable'), '', False);

    // The US Newberry Atlas shapefiles ship alongside the app itself - Gazetteer.py
    // resolves them via PROGRAM_DIR ({app}), not the Genealogy directory - so this always
    // runs, regardless of whether a Genealogy directory is provided below.
    GazDir := ExpandConstant('{app}\Gazetteer');
    ForceDirectories(GazDir);
    // We would ideally extract the zip here, but Inno Setup requires a plugin or PowerShell
    // to extract. Using a PowerShell snippet to extract. The Canadian county dataset isn't
    // bundled here - it's multiple per-year files with no single-zip source to fetch (see
    // Gazetteer/CA_UNICEN_Counties/LICENSE_AND_ATTRIBUTION.txt) - Gazetteer already runs
    // US-only when that folder is absent, exactly as it would here.
    Exec('powershell.exe', '-NoProfile -Command "Expand-Archive -Force -Path ''' + ExpandConstant('{tmp}\US_AtlasHCB_Counties.zip') + ''' -DestinationPath ''' + GazDir + '''"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

    GenDir := GenealogyPage.Values[0];
    RmDir := Rmpage.Values[0];

    // PROGRAM_DIR is the app's own install root - always known and always written,
    // regardless of whether a Genealogy directory was provided, since standalone tool
    // runs outside the GUI need it to find Gazetteer's shapefiles the same way the
    // GUI-launched path does (see Antiquarian.py's _run_subprocess).
    EnvContent := 'PROGRAM_DIR=' + ExpandConstant('{app}') + #13#10;

    if GenDir <> '' then
    begin
      ForceDirectories(GenDir + '\Antiquarian\Media');
      ForceDirectories(GenDir + '\Antiquarian\JSON');
      ForceDirectories(GenDir + '\Antiquarian\GEDCOM');

      // Plain KEY=value, no surrounding quotes (matching how the app's own settings
      // save/load already writes .env).
      EnvContent := EnvContent + 'GENEALOGY_DIR=' + GenDir + #13#10;
      if RmDir <> '' then
        EnvContent := EnvContent + 'RM_DIR=' + RmDir + #13#10;
    end;

    if PortablePage.Values[1] then
      SaveStringToFile(ExpandConstant('{app}\.env'), EnvContent, False)
    else
    begin
      ForceDirectories(ExpandConstant('{localappdata}\Antiquarian'));
      SaveStringToFile(ExpandConstant('{localappdata}\Antiquarian\.env'), EnvContent, False);
    end;
  end;
end;
