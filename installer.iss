[Setup]
AppName=Antiquarian
AppVersion=0.3.28
DefaultDirName={autopf}\Antiquarian
DefaultGroupName=Antiquarian
OutputBaseFilename=Antiquarian_Installer
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
  PortablePage := CreateInputOptionPage(wpSelectDir,
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

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
begin
  if CurPageID = wpReady then
  begin
    // Check for npm
    if not Exec('cmd.exe', '/c npm -v', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      DownloadTemporaryFile('https://nodejs.org/dist/v20.11.1/node-v20.11.1-x64.msi', ExpandConstant('{tmp}\node.msi'), '', nil);
      Exec('msiexec.exe', '/i "' + ExpandConstant('{tmp}\node.msi') + '" /qn', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
    
    // Install AGY-cli
    Exec('cmd.exe', '/c npm install -g @google/antigravity-cli', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

    // Download Gazetteer DBs
    DownloadTemporaryFile('https://publications.newberry.org/ahcb/downloads/gis/US_AtlasHCB_Counties.zip', ExpandConstant('{tmp}\US_AtlasHCB_Counties.zip'), '', nil);
    DownloadTemporaryFile('https://github.com/alerum68/Antiquarian/raw/main/Sys/Gazetteer/Canada_Counties.zip', ExpandConstant('{tmp}\Canada_Counties.zip'), '', nil);
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

    GenDir := GenealogyPage.Values[0];
    RmDir := Rmpage.Values[0];
    
    if GenDir <> '' then
    begin
      GazDir := GenDir + '\Antiquarian\Sys\Gazetteer';
      ForceDirectories(GazDir);
      ForceDirectories(GenDir + '\Antiquarian\Media');
      ForceDirectories(GenDir + '\Antiquarian\JSON');
      ForceDirectories(GenDir + '\Antiquarian\GEDCOM');
      
      // We would ideally extract the zips here, but Inno Setup requires a plugin or PowerShell to extract.
      // Using PowerShell snippet to extract
      Exec('powershell.exe', '-NoProfile -Command "Expand-Archive -Force -Path ''' + ExpandConstant('{tmp}\US_AtlasHCB_Counties.zip') + ''' -DestinationPath ''' + GazDir + '''"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec('powershell.exe', '-NoProfile -Command "Expand-Archive -Force -Path ''' + ExpandConstant('{tmp}\Canada_Counties.zip') + ''' -DestinationPath ''' + GazDir + '''"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

      // Write the selected paths to the .env file
      EnvContent := 'GENEALOGY_DIR=''' + GenDir + '''' + #13#10;
      if RmDir <> '' then
        EnvContent := EnvContent + 'RM_DIR=''' + RmDir + '''' + #13#10;
      
      if PortablePage.Values[1] then
        SaveStringToFile(ExpandConstant('{app}\.env'), EnvContent, False)
      else
      begin
        ForceDirectories(ExpandConstant('{localappdata}\Antiquarian'));
        SaveStringToFile(ExpandConstant('{localappdata}\Antiquarian\.env'), EnvContent, False);
      end;
    end;
  end;
end;
