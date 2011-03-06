try:
    from code import InteractiveConsole
except ImportError:
    from pydevconsole_code_for_ironpython import InteractiveConsole 

import os
import sys

try:
    False
    True
except NameError: # version < 2.3 -- didn't have the True/False builtins
    import __builtin__
    setattr(__builtin__, 'True', 1) #Python 3.0 does not accept __builtin__.True = 1 in its syntax
    setattr(__builtin__, 'False', 0)

try:
    try:
        import xmlrpclib
    except ImportError:
        import xmlrpc.client as xmlrpclib
except ImportError:
    import _pydev_xmlrpclib as xmlrpclib

#=======================================================================================================================
# StdIn
#=======================================================================================================================
class StdIn:
    '''
        Object to be added to stdin (to emulate it as non-blocking while the next line arrives)
    '''
    
    def __init__(self, interpreter, host, client_port):
        self.interpreter = interpreter
        self.client_port = client_port
        self.host = host
    
    def readline(self, *args, **kwargs): #@UnusedVariable
        #Ok, callback into the client to see get the new input
        server = xmlrpclib.Server('http://%s:%s' % (self.host, self.client_port))
        return server.RequestInput()
    
    def isatty(self):    
        return False #not really a file
        
    def write(self, *args, **kwargs):
        pass #not available StdIn (but it can be expected to be in the stream interface)
        
    def flush(self, *args, **kwargs):
        pass #not available StdIn (but it can be expected to be in the stream interface)
       
    #in the interactive interpreter, a read and a readline are the same.
    read = readline
        

        
try:
    class ExecState:
        FIRST_CALL = True
        PYDEV_CONSOLE_RUN_IN_UI = False #Defines if we should run commands in the UI thread.
        
    from org.python.pydev.core.uiutils import RunInUiThread #@UnresolvedImport
    from java.lang import Runnable #@UnresolvedImport
    class Command(Runnable):
    
        def __init__(self, interpreter, line):
            self.interpreter = interpreter
            self.line = line
            
        def run(self):
            if ExecState.FIRST_CALL:
                ExecState.FIRST_CALL = False
                sys.stdout.write('\nYou are now in a console within Eclipse.\nUse it with care as it can halt the VM.\n')
                sys.stdout.write('Typing a line with "PYDEV_CONSOLE_TOGGLE_RUN_IN_UI"\nwill start executing all the commands in the UI thread.\n\n')
                
            if self.line == 'PYDEV_CONSOLE_TOGGLE_RUN_IN_UI':
                ExecState.PYDEV_CONSOLE_RUN_IN_UI = not ExecState.PYDEV_CONSOLE_RUN_IN_UI
                if ExecState.PYDEV_CONSOLE_RUN_IN_UI:
                    sys.stdout.write('Running commands in UI mode. WARNING: using sys.stdin (i.e.: calling raw_input()) WILL HALT ECLIPSE.\n')
                else:
                    sys.stdout.write('No longer running commands in UI mode.\n')
                self.more = False
            else:
                self.more = self.interpreter.push(self.line)
                
            
    def Sync(runnable):
        if ExecState.PYDEV_CONSOLE_RUN_IN_UI:
            return RunInUiThread.sync(runnable)
        else:
            return runnable.run()
        
except:
    #If things are not there, define a way in which there's no 'real' sync, only the default execution.
    class Command:
    
        def __init__(self, interpreter, line):
            self.interpreter = interpreter
            self.line = line
            
        def run(self):
            self.more = self.interpreter.push(self.line)
        
    def Sync(runnable):
        runnable.run()


try:
    try:
        execfile #Not in Py3k
    except NameError:
        #We must redefine it in Py3k if it's not already there
        def execfile(file, glob=None, loc=None):
            if glob is None:
                glob = globals()
            if loc is None:
                loc = glob
            stream = open(file)
            try:
                encoding = None
                #Get encoding!
                for i in range(2):
                    line = stream.readline() #Should not raise an exception even if there are no more contents
                    #Must be a comment line
                    if line.strip().startswith('#'):
                        #Don't import re if there's no chance that there's an encoding in the line
                        if 'coding' in line:
                            import re
                            p = re.search(r"coding[:=]\s*([-\w.]+)", line)
                            if p:
                                encoding = p.group(1)
                                break
            finally:
                stream.close()
        
            if encoding:
                stream = open(file, encoding=encoding)
            else:
                stream = open(file)
            try:
                contents = stream.read()
            finally:
                stream.close()
                
            exec(compile(contents+"\n", file, 'exec'), glob, loc) #execute the script
            
        import builtins #@UnresolvedImport -- only Py3K
        builtins.execfile = execfile
        
except:
    pass

#=======================================================================================================================
# InterpreterInterface
#=======================================================================================================================
class InterpreterInterface:
    '''
        The methods in this class should be registered in the xml-rpc server.
    '''
    
    def __init__(self, host, client_port):
        self.client_port = client_port
        self.host = host
        self.namespace = globals()
        self.interpreter = InteractiveConsole(self.namespace)


        
    def addExec(self, line):
        #f_opened = open('c:/temp/a.txt', 'a')
        #f_opened.write(line+'\n')
        
        original_in = sys.stdin
        try:
            help = None
            if 'pydoc' in sys.modules:
                pydoc = sys.modules['pydoc'] #Don't import it if it still is not there.
                
                
                if hasattr(pydoc, 'help'):
                    #You never know how will the API be changed, so, let's code defensively here
                    help = pydoc.help
                    if not hasattr(help, 'input'):
                        help = None
        except:
            #Just ignore any error here
            pass
            
        sys.stdin = StdIn(self, self.host, self.client_port)
        try:
            if help is not None:
                #This will enable the help() function to work.
                help.input = sys.stdin 
            
            try:
                command = Command(self.interpreter, line)
                Sync(command)
                more = command.more
            finally:
                if help is not None:
                    help.input = original_in
                    
        finally:
            sys.stdin = original_in
        
        #it's always false at this point
        need_input = False
        return more, need_input
        
            
    def getCompletions(self, text):
        from _completer import Completer
        completer = Completer(self.namespace, None)
        return completer.complete(text)
        
    
    def getDescription(self, text):
        obj = None
        if '.' not in text:
            try:
                obj = self.namespace[text]
            except KeyError:
                return ''
                
        else:
            try:
                splitted = text.split('.')
                obj = self.namespace[splitted[0]]
                for t in splitted[1:]:
                    obj = getattr(obj, t)
            except:
                return ''
                
            
        if obj is not None:
            try:
                if sys.platform.startswith("java"):
                    #Jython
                    doc = obj.__doc__
                    if doc is not None:
                        return doc
                    
                    import jyimportsTipper
                    is_method, infos = jyimportsTipper.ismethod(obj)
                    ret = ''
                    if is_method:
                        for info in infos:
                            ret += info.getAsDoc()
                        return ret
                        
                else:
                    #Python and Iron Python
                    import inspect #@UnresolvedImport
                    doc = inspect.getdoc(obj) 
                    if doc is not None:
                        return doc
            except:
                pass
                
        try:
            #if no attempt succeeded, try to return repr()... 
            return repr(obj)
        except:
            try:
                #otherwise the class 
                return str(obj.__class__)
            except:
                #if all fails, go to an empty string 
                return ''
        
    
    def close(self):
        sys.exit(0)
        
    
    
#=======================================================================================================================
# _DoExit
#=======================================================================================================================
def _DoExit(*args):
    '''
        We have to override the exit because calling sys.exit will only actually exit the main thread,
        and as we're in a Xml-rpc server, that won't work.
    '''
    
    try:
        import java.lang.System
        java.lang.System.exit(1)
    except ImportError:
        if len(args) == 1:
            os._exit(args[0])
        else:
            os._exit(0)
    
#=======================================================================================================================
# StartServer
#=======================================================================================================================
def StartServer(host, port, client_port):
    #replace exit (see comments on method)
    #note that this does not work in jython!!! (sys method can't be replaced).
    sys.exit = _DoExit
    
    try:
        try:
            from SimpleXMLRPCServer import SimpleXMLRPCServer
        except ImportError:
            from xmlrpc.server import SimpleXMLRPCServer
    except ImportError:
        from _pydev_SimpleXMLRPCServer import SimpleXMLRPCServer
        
    interpreter = InterpreterInterface(host, client_port)
    server = SimpleXMLRPCServer((host, port), logRequests=False)
        
    server.register_function(interpreter.addExec)
    server.register_function(interpreter.getCompletions)
    server.register_function(interpreter.getDescription)
    server.register_function(interpreter.close)
    
    server.serve_forever()

    
#=======================================================================================================================
# main
#=======================================================================================================================
if __name__ == '__main__':
    port, client_port = sys.argv[1:3]
    StartServer('localhost', int(port), int(client_port))
    
