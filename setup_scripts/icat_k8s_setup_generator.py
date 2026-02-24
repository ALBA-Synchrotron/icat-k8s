import os
import sys

from icat_k8s_setup_utils import get_arguments, register_db, get_properties, \
    deploy, get_setup_parameters, load_libraries, \
    create_jms_resource_server_full

args: dict = get_arguments()
component: str = args["component"]

prop_name: str = "run.properties"
overwrite_files: list = [[prop_name, "WEB-INF/classes"]]
post_boot_asadmin_commands: list = []
pre_boot_asadmin_commands: list = []
container_type: str = os.getenv("CONTAINER_TYPE")

match component:
    case "authn.anon":
        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])

        deploy(files=overwrite_files)
    case "authn.db":
        prop_list: list = ["db.driver", "db.url", "db.username", "db.password"]
        setup_props: dict = get_setup_parameters("setup.properties", prop_list)
        db_commands: list = register_db(setup_props, "authn_db")
        post_boot_asadmin_commands.extend(db_commands)

        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])

        deploy(files=overwrite_files)
    case "authn.ldap":
        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])
        deploy(files=overwrite_files)
    case "authn.oidc":
        prop_list: list = ["wellKnownUrl", "tokenIssuer", "icatUserClaim"]
        run_props: dict = get_setup_parameters(prop_name, prop_list)

        try:
            icat_user_claim_exception: str = run_props["icatUserClaimException"]
        except KeyError:
            icat_user_claim_exception = ""

        try:
            mechanism: str = run_props["mechanism"]
        except KeyError:
            mechanism = ""

        try:
            icat_user_prepend_mechanism: str = run_props["icatUserPrependMechanism"]
        except KeyError:
            icat_user_prepend_mechanism = ""

        if icat_user_prepend_mechanism == "true":
            if mechanism == "":
                sys.exit("icatUserPrependMechanism is 'true' but no mechanism is defined in run.properties")

        if mechanism != "":
            if icat_user_prepend_mechanism != "true":
                if icat_user_claim_exception == "true":
                    print(
                        "Warning: the mechanism defined in run.properties is never used because icatUserPrependMechanism=false and icatUserClaimException=true")

        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])

        deploy(files=overwrite_files)
    case "authn.simple":
        prop_list: list = ["user.list"]
        run_props: dict = get_setup_parameters(prop_name, prop_list)

        for i in run_props["user.list"].split():
            if f"user.{i}.password" not in run_props:
                sys.exit(f"user.list included {i} but user.{i}.password is not defined")

        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])
        deploy(files=overwrite_files)
    case "icat.lucene":
        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])
        if os.path.exists("logback.xml"): overwrite_files.append(["synonym.txt", "WEB-INF/classes"])

        deploy(files=overwrite_files)
    case "icat.oaipmh":
        prop_list: list = ["icat.url", "icat.auth", "repositoryName", "adminEmails", "requestUrl", "maxResults",
                           "icatDateTimeFormat",
                           "icatDateTimeZone", "metadataPrefixes", "data.configurations"]
        run_props: dict = get_setup_parameters(prop_name, prop_list)

        metadata_prefixes: str = run_props["metadataPrefixes"].split()
        data_configurations: str = run_props["data.configurations"].split()
        try:
            sets: list = run_props["sets"].split()
        except KeyError:
            sets: list = []

        try:
            val: int = int(run_props["maxResults"])
            if val < 1:
                sys.exit("The value for 'maxResults' is less than 1 in run.properties")
        except ValueError:
            sys.exit("The value for 'maxResults' is no integer in run.properties")

        if "oai_dc" not in metadata_prefixes:
            sys.exit("Support for the metadataPrefix 'oai_dc' is missing in run.properties")

        for v in data_configurations:
            if "," in v:
                sys.exit(f"The value '{v}' in data.configurations list must not contain a comma in run.properties")
            if f"data.{v}.mainObject" not in run_props:
                sys.exit(
                    f"data.configurations include '{v}' but 'data.{v}.mainObject' is not defined in run.properties")
            if f"data.{v}.metadataPrefixes" not in run_props:
                sys.exit(
                    f"data.configurations include '{v}' but 'data.{v}.metadataPrefixes' is not defined in run.properties")

            data_configuration_metadata_prefixes: list = run_props[f"data.{v}.metadataPrefixes"].split()
            if "oai_dc" not in data_configuration_metadata_prefixes:
                sys.exit(f"Support for 'oai_dc' is missing under 'data.{v}.metadataPrefixes' in run.properties")
            for w in data_configuration_metadata_prefixes:
                if w not in metadata_prefixes:
                    sys.exit(
                        f"data.{v}.metadataPrefixes include '{w}' but this metadataPrefix is not defined in run.properties")

        for v in metadata_prefixes:
            if f"{v}.xslt" not in run_props:
                sys.exit(f"metadataPrefixes include '{v}' but '{v}.xslt' is not defined in run.properties")
            if f"{v}.namespace" not in run_props:
                sys.exit(f"metadataPrefixes include '{v}' but '{v}'.namespace' is not defined in run.properties")
            if f"{v}.schema" not in run_props:
                sys.exit(f"metadataPrefixes include '{v}' but '{v}.schema' is not defined in run.properties")
            if "responseDebug" not in run_props or run_props["responseDebug"] != "true":
                if not os.path.exists(run_props[v + ".xslt"]):
                    sys.exit(
                        f"The file '{run_props[f"{v}.xslt"]}' as listed in run.properties for '{v}.xslt' does not exist on your system")

        for v in sets:
            if "," in v:
                sys.exit(f"The value '{v}' in sets list must not contain a comma in run.properties")
            if f"sets.{v}.name" not in run_props:
                sys.exit(f"sets include '{v}' but 'sets.{v}.name' is not defined in run.properties")
            if f"sets.{v}.configurations" not in run_props:
                sys.exit(f"sets include '{v}' but 'sets.{v}.configurations' is not defined in run.properties")

            set_data_configurations: list = run_props[f"sets.{v}.configurations"].split()
            for w in set_data_configurations:
                if w not in data_configurations:
                    sys.exit(
                        f"sets.{v}.configurations include '{w}' but this data configuration is not defined in run.properties")

        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])

        deploy(files=overwrite_files)
    case "icat.server":
        if container_type == "micro":
            exit(1)
        elif container_type == "serverfull":
            libs: list = load_libraries()
            post_boot_asadmin_commands.extend(libs)

            icat_jms_topic: str = create_jms_resource_server_full("jakarta.jms.Topic", "jms/ICAT/Topic")
            post_boot_asadmin_commands.append(icat_jms_topic)

            icat_jms_log: str = create_jms_resource_server_full("jakarta.jms.Topic", "jms/ICAT/log")
            post_boot_asadmin_commands.append(icat_jms_log)

        prop_list: list = ["lifetimeMinutes", "rootUserNames", "authn.list", "notification.list", "log.list"]
        icat_properties: dict = get_properties(prop_name, prop_list)

        for v in icat_properties["authn.list"].split():
            if f"authn.{v}.jndi" not in icat_properties and f"authn.{v}.url" not in icat_properties:
                sys.exit(f"authn.list included {v} but neither authn.{v}.url nor authn.{v}.jndi is not defined")

        if icat_properties["notification.list"]:
            for v in icat_properties["notification.list"].split():
                if f"notification.{v}" not in icat_properties:
                    sys.exit(f"notification.list included {v} but notification.{v} is not defined")

        setup_props: dict = get_setup_parameters("setup.properties",
                                                 ["db.driver", "db.url", "db.username", "db.password", "secure", "home",
                                                  "container", "port"])
        db_commands: list = register_db(setup_props, "icat")
        post_boot_asadmin_commands.extend(db_commands)

        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])

        secure: bool = setup_props.get("secure", "false") == "true"
        port: int = setup_props.get("port", 8080)

        deploy(files=overwrite_files,
               jms_topic_connection_factory=icat_properties.get("jms.topicConnectionFactory"),
               target=setup_props.get("db.target"), logging=setup_props.get("db.logging"), secure=secure)
    case "ids.server":
        prop_list: list = ["icat.url", "plugin.zipMapper.class", "plugin.main.class", "cache.dir",
                           "preparedCount", "processQueueIntervalSeconds", "rootUserNames", "sizeCheckIntervalSeconds",
                           "reader",
                           "maxIdsInQuery"]
        run_props: dict = get_setup_parameters(prop_name, prop_list)

        # Cache dir is only mounted in the final container, not in the initContainer
        if not os.path.exists(os.path.expandvars(run_props.get("cache.dir"))) and 5 == 6:
            sys.exit(f"Please create directory {run_props.get("cache.dir")} as specified in run.properties")

        if run_props.get("plugin.archive.class"):
            if not run_props.get("startArchivingLevel1024bytes"): sys.exit(
                "startArchivingLevel1024bytes is not set in run.properties")
            if not run_props.get("stopArchivingLevel1024bytes"): sys.exit(
                "stopArchivingLevel1024bytes is not set in run.properties")
            if not run_props.get("tidyBlockSize"): sys.exit("tidyBlockSize is not set in ids.properties")
            if not run_props.get("storageUnit"): sys.exit("storageUnit is not set in run.properties")
            if run_props["storageUnit"].lower == "dataset":
                if not (run_props.get("delayDatasetWritesSeconds")):
                    sys.exit("delayDatasetWritesSeconds is not set in run.properties")
            if run_props["storageUnit"].lower == "datafile":
                if not (run_props.get("delayDatafileOperationsSeconds")):
                    sys.exit("delayDatafileOperationsSeconds is not set in run.properties")

        if int(run_props.get("filesCheck.parallelCount", 0)) > 0:
            if not run_props.get("filesCheck.gapSeconds"): sys.exit(
                "filesCheck.gapSeconds is not set in run.properties")
            if not run_props.get("filesCheck.lastIdFile"): sys.exit(
                "filesCheck.lastIdFile is not set in run.properties")
            parent = os.path.dirname(os.path.expandvars(run_props["filesCheck.lastIdFile"]))
            if not os.path.exists(parent):
                sys.exit(f"Please create directory {parent} for filesCheck.lastIdFile specified in run.properties")
            if not run_props.get("filesCheck.errorLog"): sys.exit("filesCheck.errorLog is not set in run.properties")
            parent = os.path.dirname(os.path.expandvars(run_props["filesCheck.errorLog"]))
            if not os.path.exists(parent):
                sys.exit(f"Please create directory {parent} for filesCheck.errorLog specified in run.properties")
            if not run_props.get("reader"): sys.exit("reader is not set in run.properties")

        if container_type == "micro":
            exit(1)
        elif container_type == "serverfull":
            libs: list = load_libraries()
            post_boot_asadmin_commands.extend(libs)

            icat_jms_log: str = create_jms_resource_server_full("jakarta.jms.Topic", "jms/IDS/log")
            post_boot_asadmin_commands.append(icat_jms_log)

        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])

        deploy(files=overwrite_files,
               jms_topic_connection_factory=run_props.get("jms.topicConnectionFactory"))
    case _:
        print(f"Unknown component: {component}")
        exit(1)

with open("pre_boot_asadmin_commands", "w") as f:
    f.write("\n".join(pre_boot_asadmin_commands))
    f.write("\n")

with open("post_boot_asadmin_commands", "w") as f:
    f.write("\n".join(post_boot_asadmin_commands))
    f.write("\n")
