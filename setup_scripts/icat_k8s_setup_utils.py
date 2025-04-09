import argparse
import contextlib
import glob
import os
import platform
import re
import shutil
import sys
import zipfile
from typing import Optional
from xml.dom.minidom import parse


def get_arguments() -> dict:
    """
    Get the arguments from the command line
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="ICAT Kubernetes setup")
    parser.add_argument("--component", type=str, required=True, help="to the configuration file")

    args: argparse.Namespace = parser.parse_args()
    return vars(args)


def get_setup_parameters(filename: str, params: list) -> dict:
    if filename:
        if not os.path.exists(filename):
            sys.exit(f"{filename} file not found")
        return get_properties(filename, params)


def register_db(db_params: dict, db_name: str) -> list:
    """
    Register the database
    """
    ret_commands: list = []

    db_url: str = db_params["db.url"]
    db_username: str = db_params["db.username"]
    db_password: str = db_params["db.password"]
    db_driver: str = db_params["db.driver"]

    d_props: str = f"user={db_username}:"
    d_props += f"password={db_password}:"
    d_props += f"url=\"{db_url}\""

    e_props = " --restype javax.sql.DataSource --failconnection=true --steadypoolsize 2"
    e_props += " --maxpoolsize 32 --ping"
    if db_driver.startswith("oracle"):
        e_props += " --validateatmostonceperiod=60 --validationtable=dual --creationretryattempts=10 --isconnectvalidatereq=true"

    ret_commands.append(
        f"create-jdbc-connection-pool --datasourceclassname {db_driver}  --property {d_props} {e_props} {db_name}")
    ret_commands.append(f"create-jdbc-resource --connectionpoolid {db_name} jdbc/{db_name}")
    return ret_commands


def get_broker_props() -> dict:
    ret: dict = {}
    broker_username: Optional[str] = os.getenv("BROKER_USERNAME")
    broker_password: Optional[str] = os.getenv("BROKER_PASSWORD")
    broker_host: Optional[str] = os.getenv("BROKER_HOST")

    if broker_username:
        ret["username"] = broker_username
    if broker_password:
        ret["password"] = broker_password
    if broker_host:
        ret["host"] = broker_host

    if not broker_username or not broker_password or not broker_host:
        sys.exit("BROKER_USERNAME / BROKER_PASSWORD / BROKER_HOST must be set")
    return ret


def create_elastic_jvm_options(elastic_apm_jar_path: str = "/opt/payara/libs/elastic-apm-agent.jar", packages_str: Optional[str]=None) -> list:
    ret: list = []
    if not packages_str:
        packages_str = "es.cells.icat.authn_alba,org.icatproject.authn_anon,org.icatproject.authn_db,org.icatproject.icat_oaipmh,org.icatproject.exposed,org.icatproject.ids"

    ret.append(f"create-jvm-options '-javaagent\:{elastic_apm_jar_path}'")
    ret.append(f"create-jvm-options '-Delastic.apm.service_name={os.getenv('APM_SERVICE_NAME')}'")
    ret.append(f"create-jvm-options '-Delastic.apm.application_packages={packages_str}'")
    ret.append(f"create-jvm-options '-Delastic.apm.server_url={os.getenv('ELASTIC_APM_SERVER_URL')}'")
    return ret


def create_jms_connection_pool(props: dict, name: str, rar_dir: str = "/opt/payara/rar",
                               rar_name: str = "activemq-rar") -> list:
    ret: list = []
    rar_path: str = os.path.join(rar_dir, f"{rar_name}.rar")
    if not os.path.exists(rar_path):
        sys.exit(f"{rar_path} file not found")

    ret.append(f"deploy --type rar --name {rar_name} {rar_dir}/{rar_name}.rar")
    ret.append(
        f"create-resource-adapter-config  --property ServerUrl=tcp\://{props.get("host")}\:61616:UserName='{props.get("username")}':Password='{props.get("password")}' {rar_name}")

    ret.append(
        f"create-connector-connection-pool  --raname {rar_name} --connectiondefinition jakarta.jms.ConnectionFactory --ping true --isconnectvalidatereq true {name}Pool")
    ret.append(f"create-connector-resource --poolname {name}Pool {name}")

    return ret


def create_jms_resource_micro(resource_type: str, name: str, rar_name: str = "activemq-rar") -> str:
    physical_name: str = name.replace("jms/", "").replace("/", "")
    return f"create-admin-object --raname {rar_name} --restype {resource_type} --property PhysicalName={physical_name} {name}"


def load_libraries(lib_dir: str = "/opt/payara/libs") -> list:
    ret: list = []
    for lib in os.listdir(lib_dir):
        if lib.endswith(".jar"):
            ret.append(f"add-library --type app {lib_dir}/{lib}")
    return ret


def create_jms_resource_server_full(resource_type: str, name: str) -> str:
    return f"create-jms-resource --restype {resource_type} {name}"

def get_properties(file_name: str, needed) -> dict:
    """Read properties files and check that the properties in the needed list are present"""

    if not os.path.exists(file_name):
        sys.exit(f"{file_name} file not found")

    p = re.compile(r"")
    f = open(file_name)
    props = {}
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("!"):
            first = len(line)
            for sep in [r"\s*=\s*", r"\s*:\s*", r"\s+"]:
                match = re.search(sep, line)
                if match and match.start() < first:
                    first = match.start()
                    last = match.end()
            if first == len(line):
                key = line
                value = ""
            else:
                key = line[:first]
                value = line[last:]
            props[key] = value
    f.close()

    for item in needed:
        if (item not in props):
            sys.exit(f"{item} must be specified in {file_name}")

    return props


def zip_war(war: str) -> None:
    z: zipfile.ZipFile = zipfile.ZipFile("zip", "w")
    for dir_name, subdir_list, file_list in os.walk("unzipped"):
        short_d: str = dir_name[9:]
        for f_name in file_list:
            z.write(os.path.join(dir_name, f_name), os.path.join(short_d, f_name))
    z.close()
    if platform.system() == "Windows": os.remove(war)
    os.rename("zip", war)
    shutil.rmtree("unzipped")


def unzip_war() -> str:
    if os.path.exists("unzipped"):
        shutil.rmtree("unzipped")
    files: list = glob.glob("*.war")
    if len(files) != 1: sys.exit("Exactly one war file must be present")
    war = files[0]
    with contextlib.closing(zipfile.ZipFile(war)) as z:
        z.extractall("unzipped")
    return war


def fix_persistence_xml(container, target, logging):
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


def deploy(files=None, jms_topic_connection_factory=None,
           target=None, logging=None, secure=False) -> None:
    if not jms_topic_connection_factory: jms_topic_connection_factory = 'jms/__defaultConnectionFactory'
    if files is None: files = []

    war: str = unzip_war()

    for src, dir in files:
        dir = os.path.join("unzipped", dir)
        try:
            os.makedirs(dir)
        except:
            pass
        shutil.copy(src, dir)

    f = os.path.join("unzipped", "WEB-INF", "web.xml")
    if os.path.exists(f):
        with open(f) as fi:
            doc = parse(fi)
            tg = doc.getElementsByTagName("transport-guarantee")[0].firstChild
            if secure:
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

    f = os.path.join("unzipped", "WEB-INF", "glassfish-ejb-jar.xml")
    if os.path.exists(f):
        with open(f) as fi:
            doc = parse(fi)
            tg = doc.getElementsByTagName("transport-guarantee")[0].firstChild
            if secure:
                tg.replaceWholeText("CONFIDENTIAL")
            else:
                tg.replaceWholeText("NONE")
            mcf = doc.getElementsByTagName("mdb-connection-factory")
            if mcf:
                jndiText = mcf[0].getElementsByTagName("jndi-name")[0].firstChild
                jndiText.replaceWholeText(jms_topic_connection_factory)

        with open(f, "w") as fi:
            fi.write(doc.toxml())

    fix_persistence_xml("Glassfish", target, logging)

    zip_war(war)
