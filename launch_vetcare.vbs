Option Explicit

Dim shell, fileSystem, projectDirectory, executablePath, pythonwPath, applicationPath, command
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

projectDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
executablePath = fileSystem.BuildPath(projectDirectory, "VetCare.exe")
pythonwPath = fileSystem.BuildPath(projectDirectory, ".venv\Scripts\pythonw.exe")
applicationPath = fileSystem.BuildPath(projectDirectory, "VetCare.pyw")

shell.CurrentDirectory = projectDirectory
If fileSystem.FileExists(executablePath) Then
    command = """" & executablePath & """"
Else
    If Not fileSystem.FileExists(pythonwPath) Then
        MsgBox "No se encontró VetCare.exe ni el entorno virtual. Instale las dependencias primero.", 16, "VetCare"
        WScript.Quit 1
    End If
    command = """" & pythonwPath & """ """ & applicationPath & """"
End If
shell.Run command, 0, False
