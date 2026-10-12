Option Explicit

Dim shell, fileSystem, projectDirectory, pythonwPath, applicationPath, command
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

projectDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = fileSystem.BuildPath(projectDirectory, ".venv\Scripts\pythonw.exe")
applicationPath = fileSystem.BuildPath(projectDirectory, "VetCare.pyw")

If Not fileSystem.FileExists(pythonwPath) Then
    MsgBox "No se encontró el entorno virtual de VetCare. Instale las dependencias primero.", 16, "VetCare"
    WScript.Quit 1
End If

shell.CurrentDirectory = projectDirectory
command = """" & pythonwPath & """ """ & applicationPath & """"
shell.Run command, 0, False
