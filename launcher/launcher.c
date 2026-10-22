#include <windows.h>
#include <stdio.h>
#include <string.h>

int WINAPI WinMain(HINSTANCE h, HINSTANCE p, LPSTR cmd, int show) {
    char dir[MAX_PATH], py[MAX_PATH * 2], line[MAX_PATH * 4];
    GetModuleFileNameA(NULL, dir, MAX_PATH);
    char *s = strrchr(dir, '\\');
    if (s) *s = 0;

    snprintf(py, sizeof py, "%s\\python\\pythonw.exe", dir);
    if (GetFileAttributesA(py) == INVALID_FILE_ATTRIBUTES) {
        MessageBoxA(NULL, "MoxyVPN files are incomplete (python folder missing).\nPlease reinstall.",
                    "MoxyVPN", MB_ICONERROR);
        return 1;
    }
    {
        char tcl[MAX_PATH * 2];
        snprintf(tcl, sizeof tcl, "%s\\python\\tcl\\tcl8.6", dir);
        SetEnvironmentVariableA("TCL_LIBRARY", tcl);
        snprintf(tcl, sizeof tcl, "%s\\python\\tcl\\tk8.6", dir);
        SetEnvironmentVariableA("TK_LIBRARY", tcl);
    }
    snprintf(line, sizeof line, "\"%s\" \"%s\\app\\moxyvpn_gui.py\" --auto --tun", py, dir);

    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    if (!CreateProcessA(NULL, line, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        MessageBoxA(NULL, "Could not start MoxyVPN.", "MoxyVPN", MB_ICONERROR);
        return 1;
    }
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return 0;
}
