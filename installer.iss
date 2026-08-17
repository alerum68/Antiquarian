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
SetupIconFile=Antiquarian.ico
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

    // Download the Canadian UNI-CEN Census Division boundaries. The original Borealis
    // Dataverse source has no single-zip download (8 separate per-year DOIs) - this is a
    // pre-zipped mirror hosted as a GitHub Release asset in this same repo instead.
    DownloadTemporaryFile('https://github.com/alerum68/Antiquarian/releases/download/gazetteer-ca-data-v1/CA_UNICEN_Counties.zip', ExpandConstant('{tmp}\CA_UNICEN_Counties.zip'), '', nil);
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
    // to extract. Using a PowerShell snippet to extract.
    Exec('powershell.exe', '-NoProfile -Command "Expand-Archive -Force -Path ''' + ExpandConstant('{tmp}\US_AtlasHCB_Counties.zip') + ''' -DestinationPath ''' + GazDir + '''"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

    // Canadian boundaries extract into their own CA_UNICEN_Counties subfolder, matching
    // Gazetteer.py's CA_SHAPEFILE_DIR expectation (the zip is flat, not nested).
    Exec('powershell.exe', '-NoProfile -Command "Expand-Archive -Force -Path ''' + ExpandConstant('{tmp}\CA_UNICEN_Counties.zip') + ''' -DestinationPath ''' + ExpandConstant('{app}\Gazetteer\CA_UNICEN_Counties') + '''"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

    GenDir := GenealogyPage.Values[0];
    RmDir := Rmpage.Values[0];

    // Portable installs assume no separate Genealogy folder exists yet (e.g. running from
    // a USB drive) - default to the portable install's own folder rather than leaving
    // GENEALOGY_DIR unset. Standard installs left blank stay unset, unchanged.
    if (GenDir = '') and PortablePage.Values[1] then
      GenDir := ExpandConstant('{app}');

    // PROGRAM_DIR is the app's own install root - always known and always written,
    // regardless of whether a Genealogy directory was provided, since standalone tool
    // runs outside the GUI need it to find Gazetteer's shapefiles the same way the
    // GUI-launched path does (see Antiquarian.py's _run_subprocess).
    EnvContent := 'PROGRAM_DIR=' + ExpandConstant('{app}') + #13#10;

    if GenDir <> '' then
    begin
      // No hardcoded "Antiquarian" folder name here - GenDir already IS the right place
      // (a dedicated Genealogy folder for Standard installs, or the portable install's own
      // folder for Portable - see the default fill-in above), so these sit directly under
      // it, matching Antiquarian.py's own MEDIA_DIR/JSON_DIR/GEDCOM_OUTPUT_PATH defaults
      // and Paleographer/engine.py's _prompt_search_dirs.
      ForceDirectories(GenDir + '\Media');
      ForceDirectories(GenDir + '\JSON');
      ForceDirectories(GenDir + '\GEDCOM');
      ForceDirectories(GenDir + '\Prompts');

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
