#import <Foundation/Foundation.h>
#include <Python.h>
#include <unistd.h>


static int fail(NSString *message) {
    fprintf(stderr, "[ERRO] %s\n", message.UTF8String);
    return 1;
}


int main(int argc, char *argv[]) {
    @autoreleasepool {
        NSBundle *bundle = NSBundle.mainBundle;
        NSString *projectRoot = [bundle objectForInfoDictionaryKey:@"M87ProjectRoot"];
        NSString *pythonPath = [bundle objectForInfoDictionaryKey:@"M87PythonExecutable"];
        NSString *mainPath = [projectRoot stringByAppendingPathComponent:@"main.py"];

        if (projectRoot.length == 0 || pythonPath.length == 0) {
            return fail(@"Configuração do aplicativo incompleta.");
        }
        if (![[NSFileManager defaultManager] fileExistsAtPath:mainPath]) {
            return fail([NSString stringWithFormat:@"main.py não encontrado em %@", projectRoot]);
        }
        if (chdir(projectRoot.fileSystemRepresentation) != 0) {
            return fail(@"Não foi possível acessar a pasta do M87 Terminal.");
        }

        PyStatus status;
        PyConfig config;
        PyConfig_InitPythonConfig(&config);
        config.parse_argv = 0;

        status = PyConfig_SetBytesString(
            &config,
            &config.program_name,
            pythonPath.fileSystemRepresentation
        );
        if (!PyStatus_Exception(status)) {
            status = PyConfig_SetBytesString(
                &config,
                &config.executable,
                pythonPath.fileSystemRepresentation
            );
        }
        if (!PyStatus_Exception(status)) {
            status = PyConfig_SetBytesString(
                &config,
                &config.run_filename,
                mainPath.fileSystemRepresentation
            );
        }
        if (PyStatus_Exception(status)) {
            PyConfig_Clear(&config);
            Py_ExitStatusException(status);
        }

        status = Py_InitializeFromConfig(&config);
        PyConfig_Clear(&config);
        if (PyStatus_Exception(status)) {
            Py_ExitStatusException(status);
        }

        return Py_RunMain();
    }
}
