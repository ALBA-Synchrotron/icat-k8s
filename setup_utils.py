from __future__ import print_function

import os
import re
import subprocess
import io
import threading
import shlex
import sys
import shutil
import filecmp
from optparse import OptionParser
import stat
import glob
import platform
import zipfile
from xml.dom.minidom import parse
import contextlib

def abort(msg):
    """Print to stderr and stop with exit 1"""
    #print >> sys.stderr, "\n", msg, "\nSetup is not complete\n"
    print("\n", msg, "\nSetup is not complete\n", file=sys.stderr)
    sys.exit(1)
    
def getProperties(fileName, needed):
     """Read properties files and check that the properties in the needed list are present"""
 
     if not os.path.exists(fileName): 
         abort (fileName + " file not found")
     
     p = re.compile(r"")
     f = open(fileName)
     props = {}
     for line in f:
         line = line.strip()
         if line and not line.startswith("#") and not line.startswith("!"):
             nfirst = len(line)
             for sep in [r"\s*=\s*", r"\s*:\s*", r"\s+"]:
                 match = re.search(sep, line)
                 if match and match.start() < nfirst: 
                     nfirst = match.start()
                     nlast = match.end()
             if nfirst == len(line):
                 key = line
                 value = ""
             else:
                 key = line[:nfirst]
                 value = line[nlast:]
             props[key] = value
     f.close()
     
     for item in needed:
         if (item not in props):
             abort(item + " must be specified in " + fileName)
            
     return props
    
def getActions(file_name=None, required=[], binDir=False, appDir=False):
    if not os.path.exists ("setup"): abort ("This must be run from the unpacked distribution directory")
    parser = OptionParser("usage: %prog [options] configure | install | uninstall")
    try:
        root = os.getuid() == 0
    except:  # Probably windows
        root = 1 
   
    if binDir: 
        if root: default = '/usr/bin'
        else: default = '~/bin'
        parser.add_option("--binDir", "-b", help="location to store executables [" + default + "]", default=default)
 
    if appDir: 
       if root: default = '/usr/share'
       else: default = '~/java'
       parser.add_option("--appDir", "-a", help="location to store java applications [" + default + "]", default=default)

    parser.add_option("--verbose", "-v", help="produce more output - this may appear twice to get even more", action="count")
    
    options, args = parser.parse_args()
    
    if len(args) != 1:abort("Must have one argument: install' or 'uninstall'")
    
    arg = args[0].upper()
    if arg not in ["CONFIGURE", "INSTALL", "UNINSTALL"]: abort("Must have one argument: 'install' or 'uninstall'")
    
    if binDir and not os.path.isdir(os.path.expanduser(options.binDir)): abort("Please create directory " + options.binDir + " or specify --binDir")
    if appDir and not os.path.isdir(os.path.expanduser(options.appDir)): abort("Please create directory " + options.appDir + " or specify --appDir")
    
    if file_name:
        if not os.path.exists(file_name):
            shutil.copy(file_name + ".example", file_name) 
            if platform.system() != "Windows": os.chmod(file_name, stat.S_IRUSR | stat.S_IWUSR)
            abort ("\nPlease edit " + file_name + " to meet your requirements then re-run the command")
        if os.stat(file_name).st_mode & stat.S_IROTH:
            if platform.system() == "Windows":
                print("Warning: '" + file_name + "' should not be world readable")
            else:
                os.chmod(file_name, stat.S_IRUSR | stat.S_IWUSR)
                print("'" + file_name + "' mode changed to 0600")
        props = getProperties(file_name, required + ["secure", "home", "container", "port"])
        
        if props["secure"].lower() == "true": secure = True
        elif props["secure"].lower() == "false": secure = False
        else : abort ("Secure must be true or false")
        
        if "db.vendor" in props: 
            abort("db.vendor should no longer be specified in " + file_name + " - consider setting db.target")
    
        container = props["container"]
        if container == "Glassfish": actions = GlassfishActions(props, options)
        elif container == "JBoss": actions = WildflyActions(props, options)
        else : abort ("container must be Glassfish or JBoss")
    else:
        props = {"secure":"NA"}
        actions = Actions(props, options)
    
    return actions, arg, props

class Actions(object):   
    def __init__(self, props, options):
        self.verbosity = options.verbose or 0
        self.secure = props["secure"].lower() == "true"
        try: self.binDir = os.path.expanduser(options.binDir)
        except: pass
        try: self.appDir = os.path.expanduser(options.appDir)
        except: pass
        self.clashes = 0
        
    def _fix_persistence_xml(self, container, target, logging):
        f = os.path.join("unzipped", "WEB-INF", "classes", "META-INF", "persistence.xml")
        if os.path.exists(f):
            with open(f) as fi:
                doc = parse(fi)
                for prop in doc.getElementsByTagName("property"):
                    if prop.getAttribute("name") == "eclipselink.target-server":
                        prop.setAttribute("value", container)
                    if target and prop.getAttribute("name") == "eclipselink.target-database":
                        prop.setAttribute("value", target)
                    if prop.getAttribute("name") == "eclipselink.logging.level":
                        if logging:
                            prop.setAttribute("value", logging)
                        else:
                            prop.setAttribute("value", "OFF")
                    if prop.getAttribute("name") == "eclipselink.logging.level.sql":
                        if logging:
                            prop.setAttribute("value", logging)
                        else:
                            prop.setAttribute("value", "OFF")
                    if prop.getAttribute("name") == "eclipselink.logging.parameters":
                        if logging:
                            prop.setAttribute("value", "true")
                        else:
                            prop.setAttribute("value", "false")
            with open(f, "w") as fi:
                fi.write(doc.toxml())
        
    def _zip(self, war):
        z = zipfile.ZipFile("zip", "w")
        for dirName, subdirList, fileList in os.walk("unzipped"):
            shortd = dirName[9:]
            for fname in fileList:
                z.write(os.path.join(dirName, fname), os.path.join(shortd, fname))
        z.close()
        if platform.system() == "Windows": os.remove(war)
        os.rename("zip", war)
        shutil.rmtree("unzipped")
        if self.verbosity:
            print("\nConverted ", war)
        
    def _unzip(self):
        if os.path.exists("unzipped"):
            shutil.rmtree("unzipped")
        files = glob.glob("*.war")
        if len(files) != 1: abort("Exactly one war file must be present")
        war = files[0]
        with contextlib.closing(zipfile.ZipFile(war)) as z: z.extractall("unzipped")
        return war
        
    def restartApp(self, appName):
        self.disableApp(appName)
        self.enableApp(appName)
        
    def getBinDir(self):
        return self.binDir
    
    def execute(self, cmd):    
        if platform.system() == "Windows": 
            cmd = cmd.split()
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            cmd = shlex.split(cmd)
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stringOut = io.StringIO()
       
        mstdout = Tee(proc.stdout, stringOut)
        mstdout.start()
        stringErr = io.StringIO()
        mstderr = Tee(proc.stderr, stringErr)
        mstderr.start()
        rc = proc.wait()
    
        mstdout.join()
        mstderr.join()
        
        out = stringOut.getvalue().strip()
        stringOut.close()
        
        err = stringErr.getvalue().strip()
        stringErr.close()
        
        return out, err, rc
           
    def configure(self, file_name, expected):
        if not os.path.exists(file_name):
            shutil.copy(file_name + ".example", file_name)
            print("\nCopied " + file_name + ".example" + " to " + file_name)
            print("Please edit", file_name, "to meet your requirements")
            abort("... and then re-run the command")

        props = getProperties(file_name, [])
        example = getProperties(file_name + ".example", [])
        for key in expected:
            prop = props.get(key)
            if not prop:
                self.clashes += 1
                print("Error: property", key, "is not set in", file_name)

        if self.verbosity > 1:
            for key in props.keys():
                if key in example:
                    if props[key] != example[key]: print("\nValue for" , key, "in", file_name, "is", "'" + props[key] + "'", "which differs from example:", "'" + example[key] + "'")
                else:  print("\nValue for" , key, "in", file_name, "is", "'" + props[key] + "'", "is not in example")
            for key in example.keys():
                if key not in props: print("\nValue for" , key, "not in", file_name, "but is in example:", "'" + example[key] + "'")
    
    def configureFileForWar(self, f):
        if not os.path.exists(f):
            shutil.copy(f + ".example", f)
            print("\nCopied", f + ".example", "to", f)
            print("Please edit", f, "to meet your requirements")
            self.clashes += 1
            
    def checkNoErrors(self):
        if self.clashes:
            if self.clashes == 1:
                abort("Please edit configuration file and try again as an error was reported.")
            else:
                abort("Please edit configuration files and try again as " + str(self.clashes) + " errors were reported.")
                  
    def installFile(self, file, dir):
        if not os.path.isdir(dir): abort ("Please create directory " + dir + " to install " + file)
        if not os.path.exists(file): abort (file + " not found")
        shutil.copy(file , dir)
        if self.verbosity:
            print("\n", file, "copied to", dir)
            
    def removeFile(self, file, dir):
        dest = os.path.join(dir, file)
        if os.path.exists(dest): 
            os.remove(dest)
            if self.verbosity:
                print("\n", file, "removed from", dir)
                
    def installDir(self, file, dir):
        if not os.path.isdir(dir): abort ("Please create directory " + dir + " to install " + file)
        if not os.path.exists(file): abort (file + " not found") 
        if not os.path.isdir(file): abort (file + " is not a directory")
        dest = os.path.join(dir, file)
        if os.path.exists(dest): shutil.rmtree(dest)
        shutil.copytree(file , dest)
        if self.verbosity:
            print("\n", file, "copied to", dir)
            
    def removeDir(self, file, dir):
        dest = os.path.join(dir, file)
        if os.path.exists(dest): 
            shutil.rmtree(dest)
            if self.verbosity:
                print("\n", directory, "removed from", dir)
 
    
class WildflyActions(Actions):
    def __init__(self, props, options):
        super(WildflyActions, self).__init__(props, options)
        
        wildfly = props["home"]
        if not os.path.exists(wildfly): abort("wildfly directory " + wildfly + " does not exist")
        
        self.cliCommand = os.path.join(wildfly, "bin", "jboss-cli.sh -c")
        
        cmd = self.cliCommand + " --version"
        out, err, rc = self.execute(cmd)
        if rc: abort(out + err)
        version = "Unknown!!!"
        for line in out.splitlines():
            if line.startswith("JBoss AS product"): version = line[18:]
        if self.verbosity: print("You are using", version)
               
    def enableApp(self, appName):
        self._cli("deploy --name=" + appName)
        
    def disableApp(self, appName):
        self._cli("undeploy " + appName + " --keep-content", tolerant=True, printOutput=True)
    
    def getAppName(self, app):
        cmd = self.cliCommand + " " + "'ls deployment'"
        out, err, rc = self.execute(cmd)
        if rc: abort(err)
        for line in out.splitlines():
            if (line.startswith(app + "-")):
                return line
            
    def _cli(self, command, tolerant=False, printOutput=False):
        cmd = self.cliCommand + " '" + command + "'"
        if self.verbosity: print("\nexecute: " + cmd )
        out, err, rc = self.execute(cmd)
        if self.verbosity > 1 or printOutput:
            if out: print(out)
            if err: print(err)
     
        if not tolerant and rc:
            if not self.verbosity: print(cmd, " ->")
            abort(err)
            
    def deploy(self, deploymentorder=100, libraries=[], jmsTopicConnectionFactory=None, target=None, logging=None):
        war = self._unzip()
        # Fix the web.xml
        f = os.path.join("unzipped", "WEB-INF", "web.xml")
        if os.path.exists(f):
            with open(f) as fi:
                doc = parse(fi)
                tg = doc.getElementsByTagName("transport-guarantee")[0].firstChild
                if self.secure:
                    tg.replaceWholeText("CONFIDENTIAL")
                else:
                    tg.replaceWholeText("NONE")
                    
                wap = doc.getElementsByTagName("web-app")[0]
                
                servlet = doc.getElementsByTagName("servlet")[0]
                sc = servlet.getElementsByTagName("servlet-class")[0].firstChild
                sc.replaceWholeText("org.jboss.resteasy.plugins.server.servlet.HttpServletDispatcher")
                
                cp = doc.getElementsByTagName("context-param")
                if cp:
                    cp[0].parentNode.removeChild(cp[0])
                wap.appendChild(doc.createElement("context-param"))
                cp = wap.getElementsByTagName("context-param")[0]
                cp.appendChild(doc.createElement("param-name"))
                cpn = cp.getElementsByTagName("param-name")[0]
                cpn.appendChild((doc.createTextNode("resteasy.scan")))
                cp.appendChild(doc.createElement("param-value"))
                cpv = cp.getElementsByTagName("param-value")[0]
                cpv.appendChild((doc.createTextNode("true")))
         
            with open(f, "w") as fi:
                fi.write(doc.toprettyxml(indent="  "))
                
            self._fix_persistence_xml("JBoss", target, logging)    
                
        self._zip(war)
        
        cmd = self.cliCommand + " " + "'deploy"
        cmd = cmd + " " + war + "'"
        if self.verbosity: print("\nexecute: " + cmd )
        out, err, rc = self.execute(cmd)
        if self.verbosity > 1 or rc:
            if out: print(out)
        if err:
            for line in err.splitlines():
                line = line.strip()
                if line:
                    if line.startswith("PER01"): continue
                    print(line)
        if rc: abort("Deployment failed")
        
    def undeploy(self, appName):
        self._cli("undeploy " + appName)
        
    def unregisterDB(self, name):
        self._cli("/subsystem=datasources/data-source=" + name + ":remove", tolerant=True)
                
    def registerDB(self, name, driver, url, username, password):
        dProps = "driver-name=" + driver
        dProps += ",jndi-name=java:/jdbc/" + name
        dProps += ",connection-url=" + url
        dProps += ",user-name=" + username
        dProps += ",password=" + password
        dProps += ",min-pool-size=5,max-pool-size=15,enabled=true,background-validation=true, background-validation-minutes=1"
        if "mysql" in driver:
            dProps += ",valid-connection-checker-class-name=org.jboss.jca.adapters.jdbc.extensions.mysql.MySQLValidConnectionChecker"
            dProps += ",exception-sorter-class-name=org.jboss.jca.adapters.jdbc.extensions.mysql.MySQLExceptionSorter"
        elif driver.startswith("oracle"):
            dProps += ",valid-connection-checker-class-name=org.jboss.jca.adapters.jdbc.extensions.oracle.OracleValidConnectionChecker"
            dProps += ",exception-sorter-class-name=org.jboss.jca.adapters.jdbc.extensions.oracle.OracleExceptionSorter"
        print(dProps)
        self._cli("/subsystem=datasources/data-source=" + name + ":add(" + dProps + ")", printOutput=True)
      
    def createJMSResource(self, type, name):
        self._cli("jms-topic add --topic-address=" + name + " --entries=java:jboss/exported/" + name + "\ " + name, printOutput=True)
        self._cli("reload")
    
    def deleteJMSResource(self, name):
        self._cli("jms-topic remove --topic-address=" + name, tolerant=True)
        self._cli("reload")
        
class GlassfishActions(Actions):
    
    def __init__(self, props, options):
        super(GlassfishActions, self).__init__(props, options)
        
        glassfish = props["home"]
        if not os.path.exists(glassfish): abort("glassfish directory " + glassfish + " does not exist")
        
        self.asadminCommand = os.path.join(glassfish, "bin", "asadmin") + " --port " + props["port"]
        
        # Test that domain is running and that password set up
        out, err, rc = self.execute(self.asadminCommand + " get property.administrative.domain.name")
        if rc:
            if err.startswith("Remote server does not listen"): abort('Please use the "asadmin start-domain" command to start your domain')
            if err.startswith("Authentication failed for user: null"): abort ('Please use the "asadmin login" command and accept the default user name to be able to access your domain')
            abort(err)
        
        
        self.domain = self.getAsadminProperty("property.administrative.domain.name")
        
        domain_path = os.path.join(glassfish, "glassfish", "domains", self.domain)
        if not os.path.exists(domain_path): abort("Domain directory " + domain_path + " does not exist")
        self.lib_path = os.path.join(domain_path, "lib", "applibs")
        if not os.path.exists(self.lib_path): abort("Domain's lib directory " + self.lib_path + " does not exist")
        
        cmd = self.asadminCommand + " version"
        out, err, rc = self.execute(cmd)
        if rc: abort(err)
        vline = out.splitlines()[0]
        if self.verbosity: print("You are using:", vline.split("=")[1].strip())
      
    def deleteFileRealmUser(self, username):
        self._asadmin("delete-file-user " + username, tolerant=True)
        
    def stopDomain(self):
        cmd = self.asadminCommand + " stop-domain " + self.domain
        if self.verbosity: print("\nexecute: " + cmd )
        out, err, rc = self.execute(cmd)
        if rc:
            print(cmd, " ->" + err)
            out, err, rc = self.execute("jps")
            if rc:
                abort(err)
            for line in out.splitlines():
                line = line.strip().split()
                if line[1] == "ASMain":
                    cmd = "kill -9 " + line[0]
                    if self.verbosity: print("\nexecute: " + cmd )
                    self.execute(cmd)
                    
    def startDomain(self):
        self._asadmin("start-domain " + self.domain)
        
    def installToApplibs(self, jar):
        files = glob.glob(jar)
        if len(files) != 1: abort("Exactly one file must match " + jar)
        shutil.copy(files[0] , self.lib_path)
        if self.verbosity:
            print("\n", files[0], "copied to", self.lib_path)
        
    def removeFromApplibs(self, jar):
        dest = os.path.join(self.lib_path, jar)
        files = glob.glob(dest)
        if len(files) > 1: abort("Exactly one file must match " + dest)
        if len(files) == 1: 
            os.remove(files[0])
            if self.verbosity:
                print("\n", os.path.basename(files[0]), "removed from", self.lib_path)
                  
    def unregisterDB(self, name):
        self._asadmin("delete-jdbc-resource jdbc/" + name, tolerant=True)
        self._asadmin("delete-jdbc-connection-pool " + name, tolerant=True)
                
    def registerDB(self, name, driver, url, username, password):
        dProps = "url=" + url.replace(":", "\\\\:")
        dProps += ":user=" + username
        dProps += ":password=" + password.replace(":", "\\\\:")
      
        eProps = " --restype javax.sql.DataSource --failconnection=true --steadypoolsize 2"
        eProps += " --maxpoolsize 32 --ping"
        if driver.startswith("oracle"):
            eProps += " --validateatmostonceperiod=60 --validationtable=dual --creationretryattempts=10 --isconnectvalidatereq=true"
        self._asadmin('create-jdbc-connection-pool --datasourceclassname ' + driver + ' --property ' + dProps + ' ' + eProps + " " + name, printOutput=True)
        self._asadmin("create-jdbc-resource --connectionpoolid " + name + " jdbc/" + name)
    
    def createJMSResource(self, type, name):
        self._asadmin("create-jms-resource --restype " + type + " " + name, printOutput=True)
    
    def deleteJMSResource(self, name):
        self._asadmin("delete-jms-resource " + name, tolerant=True)
        
    def createMailResource(self, name, host, user, mfrom , property):
        self._asadmin("create-javamail-resource --mailhost " + host + " --mailuser " + user + 
                      " --fromaddress " + mfrom + " --property " + property + " " + name)

    def deleteMailResource(self, name):
        self._asadmin("delete-javamail-resource " + name, tolerant=True)
                     
    def addFileRealmUser(self, username, password, group):
        if self.getAsadminProperty("configs.config.server-config.security-service.activate-default-principal-to-role-mapping") == "false":
            self.setAsadminProperty("configs.config.server-config.security-service.activate-default-principal-to-role-mapping", "true")
            self.stopDomain()
            self._asadmin("start-domain " + self.domain)
            
        digit = False
        lc = False
        uc = False
        for c in password:
            if c.isdigit(): digit = True
            elif c.islower(): lc = True
            elif c.isupper(): uc = True
        if not (digit and lc and uc) : abort("password must contain at least one digit, a lower case character and an upper case character")
            
        self._asadmin("delete-file-user " + username, tolerant=True)
        f = open("pw", "w")
        print("AS_ADMIN_USERPASSWORD=" + password, file=f)
        f.close() 
        self._asadmin("--passwordfile pw create-file-user --groups " + group + " " + username)
        os.remove("pw")
        
    def deploy(self, deploymentorder=100, libraries=[], files=[], jmsTopicConnectionFactory=None, target=None, logging=None):
        if not jmsTopicConnectionFactory: jmsTopicConnectionFactory = 'jms/__defaultConnectionFactory'
        
        war = self._unzip()
        
        # Add specific files
        for src, dir in files:
            dir = os.path.join("unzipped", dir)
            try:
                os.makedirs(dir)
            except:
                pass
            shutil.copy(src , dir)
            if self.verbosity:
                print("\n", src, "copied to", dir)
        
        # Fix the web.xml
        f = os.path.join("unzipped", "WEB-INF", "web.xml")
        if os.path.exists(f):
            with open(f) as fi:
                doc = parse(fi)
                tg = doc.getElementsByTagName("transport-guarantee")[0].firstChild
                if self.secure:
                    tg.replaceWholeText("CONFIDENTIAL")
                else:
                    tg.replaceWholeText("NONE")
                    
                wap = doc.getElementsByTagName("web-app")[0]
                
                servlet = doc.getElementsByTagName("servlet")[0]
                sc = servlet.getElementsByTagName("servlet-class")[0].firstChild
                sc.replaceWholeText("org.glassfish.jersey.servlet.ServletContainer")
                
                cp = doc.getElementsByTagName("context-param")
                if cp:
                    cp[0].parentNode.removeChild(cp[0])
                    
            with open(f, "w") as fi:
                fi.write(doc.toxml())
                
        # Fix the glassfish-ejb-jar.xml if needed
        f = os.path.join("unzipped", "WEB-INF", "glassfish-ejb-jar.xml")
        if os.path.exists(f):
            with open(f) as fi:
                doc = parse(fi)
                tg = doc.getElementsByTagName("transport-guarantee")[0].firstChild
                if self.secure:
                    tg.replaceWholeText("CONFIDENTIAL")
                else:
                    tg.replaceWholeText("NONE")
                mcf = doc.getElementsByTagName("mdb-connection-factory")
                if mcf:
                    jndiText = mcf[0].getElementsByTagName("jndi-name")[0].firstChild
                    jndiText.replaceWholeText(jmsTopicConnectionFactory)
                    
            with open(f, "w") as fi:
                fi.write(doc.toxml())
                
        self._fix_persistence_xml("Glassfish", target, logging)                        
            
        self._zip(war) 
        
        cmd = self.asadminCommand + " " + "deploy --deploymentorder " + str(deploymentorder)
        if libraries:
            libstring = ""
            for library in libraries:
                path = os.path.join(self.lib_path, library)
                libs = glob.glob(path)
                if len(libs) != 1: abort("Exactly one library must match " + path)
                libadd = os.path.basename(libs[0])
                if libstring:
                    libstring += "," + libadd
                else:
                    libstring = "--libraries " + libadd
            cmd = cmd + " " + libstring
        cmd = cmd + " " + war
        if self.verbosity: print("\nexecute: " + cmd )
        out, err, rc = self.execute(cmd)
        if self.verbosity > 1:
            if out: print(out)
        if err:
            for line in err.splitlines():
                line = line.strip()
                if line:
                    if line.startswith("PER01"): continue
                    print(line)
        if rc: abort("Deployment failed")              
       
    def _asadmin(self, command, tolerant=False, printOutput=False):
        cmd = self.asadminCommand + " " + command
        if self.verbosity: print("\nexecute: " + cmd )
        out, err, rc = self.execute(cmd)
        if self.verbosity > 1 or printOutput:
            if out: print(out)
            if err: print(err)
     
        if not tolerant and rc:
            if not self.verbosity: print(cmd, " ->")
            abort(err)
           
    def getAppName(self, app):
        cmd = self.asadminCommand + " " + "list-applications"
        out, err, rc = self.execute(cmd)
        if rc: abort(err)
        for line in out.splitlines():
            if (line.startswith(app + "-")):
                return line.split()[0]
        
    def enableApp(self, appName):
        self._asadmin("enable " + appName)
        
    def disableApp(self, appName):
        self._asadmin("disable " + appName, tolerant=True, printOutput=True)
    
    def undeploy(self, appName):
        self._asadmin("undeploy " + appName)
        
    def getAsadminProperty(self, name):
        cmd = self.asadminCommand + " get " + name
        if self.verbosity: print("\nexecute: " + cmd)
        out, err, rc = self.execute(cmd)
        if rc: abort(err)
        return out.splitlines()[0].split("=")[1]
    
    def setAsadminProperty(self, name, value):
        cmd = self.asadminCommand + " set " + name + "=" + value
        if self.verbosity: print("\nexecute: " + cmd )
        out, err, rc = self.execute(cmd)
        if rc: abort(err)

class Tee(threading.Thread):
    
    def __init__(self, inst, *out):
        threading.Thread.__init__(self)
        self.inst = inst
        self.out = out
        
    def run(self):
        while 1:
            line = self.inst.readline()
            if not line: break
            for out in self.out:
                out.write(line.decode("utf8"))
